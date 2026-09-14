"""Purchase Goals -- named "gear setups" a player plans/saves toward,
ported from the original single-user Maintrius tool's osrs_tracker.py
(see build_gear_setups, _resolve_gear_slot_item, _still_to_purchase_summary
there for the code this is a direct port of). The mechanic is unchanged;
only where the inputs come from has:

- Character data (bank/inventory/equipment/potion storage) came from
  JSON files a separate RuneLite Character Exporter plugin wrote to
  disk; here it comes from the BankItem/InventoryItem/EquipmentItem/
  PotionStorageItem tables this app's own plugin syncs (see
  app/main.py's sync endpoints).
- Item mapping/prices came from local JSON file caches with a
  last-fetched timestamp; here the exact same OSRS Wiki Real-time Prices
  API is fetched into in-memory, process-level caches instead (this app
  has many players sharing one process, not one person's single-user
  server, and there's nothing about wiki prices that needs to survive a
  restart -- refetching after one is cheap and harmless).
- Gear setups themselves came from one JSON file holding every setup;
  here each is a GearSetup row (see app/models.py), scoped to the
  player who owns it.

Everything about the actual mechanic -- the three slot-item shapes
(plain tradeable, plain untradeable, composed "combo"), the owned-pool
bookkeeping, the affordability/still-to-purchase/next-purchase
computation -- is unchanged from the original. (A fourth shape,
"supplies" -- always assumed owned, a manual workaround for potions the
plugin couldn't yet see in Potion Storage -- existed here too, but is
gone now that the plugin reads Potion Storage for real; see
PotionStorageItem's docstring in app/models.py.)
"""
import json
import re
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.item_ids import find_item_icon, find_item_ids, search_item_names
from app.models import BankItem, EquipmentItem, GearSetup, InventoryItem, Player, PotionStorageItem
from app.recipes import find_recipe, search_recipe_names
from app.schemas import EQUIPMENT_SLOTS, INVENTORY_SIZE

# OSRS's own item id for coins -- used to read "gp in the bank" straight
# off the synced bank_items rows, the same way the original tool's
# load_character_snapshot() read it straight off bank.json.
COINS_ITEM_ID = 995

# The OSRS Wiki Real-time Prices API requires a descriptive User-Agent
# identifying the tool and how to reach whoever runs it -- see
# https://prices.runescape.wiki/osrs/faqs
API_BASE = "https://prices.runescape.wiki/api/v2/osrs"
# Icons are hotlinked directly by the browser rather than fetched by this
# server -- the wiki's image hosting sits behind a Cloudflare bot
# challenge that a plain server-side request can never pass (it requires
# executing JS), but a real browser loading the page normally isn't a
# bot and goes straight through.
ICON_PATH_BASE = "https://oldschool.runescape.wiki/w/Special:FilePath"
USER_AGENT = "myscape.io/1.0 (Purchase Goals; contact: chandler@myscape.io)"

# How long cached data is considered fresh before hitting the wiki API
# again -- same values the original tool used.
PRICE_TTL_SECONDS = 60
MAPPING_TTL_SECONDS = 24 * 60 * 60  # item mapping barely changes; once a day is plenty

# Process-level caches, shared across every player (wiki prices/mapping
# aren't player-specific) -- {"fetchedAt": float, "byId": {...}, "error": str|None}.
# Module-level rather than per-request: refetching the ~860KB mapping
# payload on every single request would be both slow and unnecessary
# when it changes maybe once a day.
_mapping_cache: Optional[dict] = None
_price_cache: Optional[dict] = None


def _fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_mapping(force: bool = False) -> Tuple[Dict[str, dict], Optional[str]]:
    """Returns ({itemId: {"name":..., "icon":...}}, error|None), refreshing
    from the wiki at most once a day (item metadata rarely changes)."""
    global _mapping_cache
    fresh = _mapping_cache and (time.time() - _mapping_cache["fetchedAt"]) < MAPPING_TTL_SECONDS
    if _mapping_cache and fresh and not force:
        return _mapping_cache["byId"], _mapping_cache.get("error")

    try:
        raw = _fetch_json(f"{API_BASE}/mapping")
        by_id = {
            str(entry["id"]): {"name": entry.get("name"), "icon": entry.get("icon")}
            for entry in raw
        }
        _mapping_cache = {"fetchedAt": time.time(), "byId": by_id, "error": None}
        return by_id, None
    except Exception as exc:  # noqa: BLE001 -- surface any failure to the UI
        err = f"{type(exc).__name__}: {exc}"
        if _mapping_cache:
            # Serve stale data rather than nothing if the network hiccups.
            return _mapping_cache["byId"], err
        return {}, err


def get_latest_prices(force: bool = False) -> Tuple[Dict[str, dict], Optional[str]]:
    """Returns ({itemId: {"high":..., "low":...}}, error|None)."""
    global _price_cache
    fresh = _price_cache and (time.time() - _price_cache["fetchedAt"]) < PRICE_TTL_SECONDS
    if _price_cache and fresh and not force:
        return _price_cache["byId"], _price_cache.get("error")

    try:
        raw = _fetch_json(f"{API_BASE}/latest")
        data = raw.get("data", raw)  # tolerate either shape
        by_id = {
            str(item_id): {"high": v.get("high"), "low": v.get("low")}
            for item_id, v in data.items()
        }
        _price_cache = {"fetchedAt": time.time(), "byId": by_id, "error": None}
        return by_id, None
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        if _price_cache:
            return _price_cache["byId"], err
        return {}, err


_ICON_EXT_RE = re.compile(r"\.(png|gif|jpg|jpeg)$", re.IGNORECASE)


def item_icon_url(icon_filename: Optional[str]) -> Optional[str]:
    if not icon_filename:
        return None
    if not _ICON_EXT_RE.search(icon_filename):
        icon_filename = icon_filename + ".png"
    return ICON_PATH_BASE + "/" + urllib.parse.quote(icon_filename)


def unit_price_for(item_id: int, prices: dict) -> Tuple[Optional[int], Optional[str]]:
    p = prices.get(str(item_id))
    if not p:
        return None, None
    if p.get("high") is not None:
        return p["high"], "high (instant-buy)"
    if p.get("low") is not None:
        return p["low"], "low (instant-sell, no recent buy trades)"
    return None, None


def search_items(query: str, limit: int = 20) -> List[dict]:
    mapping, _ = get_mapping()
    q = query.strip().lower()
    if not q:
        return []
    starts, contains = [], []
    for item_id, meta in mapping.items():
        name = meta.get("name") or ""
        low = name.lower()
        if low.startswith(q):
            starts.append((item_id, meta))
        elif q in low:
            contains.append((item_id, meta))
    starts.sort(key=lambda kv: len(kv[1].get("name") or ""))
    contains.sort(key=lambda kv: len(kv[1].get("name") or ""))
    combined = (starts + contains)[:limit]
    results = [
        {"id": int(item_id), "name": meta.get("name"), "icon": item_icon_url(meta.get("icon")), "tradeable": True}
        for item_id, meta in combined
    ]

    # Fill any remaining slots with known item-combination recipes (see
    # app/recipes.py) -- e.g. "Neitiznot faceguard" has no Grand
    # Exchange listing of its own, so it would never show up above, but
    # a player should still be able to find it by name and see its icon
    # rather than being told to type it in blind as an untradeable item.
    # Names already matched as a real tradeable item above are skipped
    # so nothing appears twice.
    if len(results) < limit:
        seen_names = {r["name"].lower() for r in results}
        for entry in search_recipe_names(q, limit - len(results), exclude=seen_names):
            results.append({"id": None, "name": entry["name"], "icon": item_icon_url(entry.get("icon")), "tradeable": False})

    # Still short? Fall back to the broader item-id snapshot (see
    # app/item_ids.py), which covers every item in the game -- tradeable
    # or not, recipe output or not (a quest reward, a minigame-only
    # item, anything else neither of the two tiers above knows about).
    # This is what lets search find literally any known OSRS item by
    # name, closing the gap the old "add as an untradeable item"
    # fallback used to paper over for exactly this case.
    if len(results) < limit:
        seen_names = {r["name"].lower() for r in results}
        for entry in search_item_names(q, limit - len(results), exclude=seen_names):
            if entry.get("name"):
                results.append({"id": None, "name": entry["name"], "icon": item_icon_url(entry.get("icon")), "tradeable": False})

    return results


# Crystal armour (helm/body/legs) can be recolored to match any of the
# eight Iorwerth Clan houses (e.g. worn as "Crystal helm (ithell)" for
# the default white/silver look) -- purely cosmetic, so what the plugin
# actually reports off the client's item id never carries that suffix.
# Typed into a gear-setup slot as "Crystal helm (ithell)", it would
# otherwise never name-match what's owned -- see Maintrius's own
# _strip_cosmetic_item_suffix in osrs_tracker.py for the original of
# this exact rule, ported unchanged.
_CRYSTAL_ARMOUR_COLOR_SUFFIX_RE = re.compile(
    r"\s*\((?:ithell|amlodd|cadarn|crwys|hefin|iorwerth|meilyr|trahaearn)\)\s*$",
    re.IGNORECASE,
)


def _strip_cosmetic_item_suffix(name: str) -> str:
    stripped = _CRYSTAL_ARMOUR_COLOR_SUFFIX_RE.sub("", name or "").strip()
    return stripped if stripped.lower().startswith("crystal ") else name


def _normalize_item_name(name: Optional[str]) -> str:
    return _strip_cosmetic_item_suffix((name or "").strip()).strip().lower()


def _take_owned(pool_by_id: dict, pool_by_name: dict, item_id: Optional[int], item_name: Optional[str], qty: int) -> int:
    """Claim up to qty units of an item from the shared "already own"
    pool (built from bank+inventory+equipment+potion storage -- see
    _build_owned_pools below), returning how many were actually
    available. Pools are mutated in place so a physical item can only
    satisfy one requirement, not several.

    A tradeable item is matched by its real item id, which is exact by
    definition. An untradeable item (no id passed in) is matched by its
    real game item id too when we know one -- see app/item_ids.py,
    which covers every item in the game, not just GE-tradeable ones --
    since an id either is or isn't the same physical item, with no room
    for the kind of near-miss that breaks a name comparison (an
    apostrophe encoded differently, incidental whitespace, a
    capitalization difference between however the RuneLite plugin
    reported it and however a gear slot names it). Only when an item
    isn't in that id snapshot at all (e.g. something added to the game
    since it was last generated) does this fall back to the original
    case-insensitive name match, exactly as before -- once id data IS
    available for a name, matching sticks to ids alone rather than also
    dipping into the name pool for whatever's left unmatched, since
    pool_by_id and pool_by_name are built from the very same physical
    items (see _build_owned_pools) and mixing the two for one call
    risks claiming the same physical item twice over. An item can have
    more than one real id (a quest-reward variant, a minigame-only
    version, etc.) -- owning it under any of them counts, and this
    tries them in order until qty is satisfied or they're exhausted."""
    if qty <= 0:
        return 0
    if item_id is not None:
        avail = pool_by_id.get(item_id, 0)
        take = min(avail, qty)
        if take:
            pool_by_id[item_id] = avail - take
        return take

    candidate_ids = find_item_ids(item_name)
    if candidate_ids:
        remaining = qty
        for candidate_id in candidate_ids:
            if remaining <= 0:
                break
            avail = pool_by_id.get(candidate_id, 0)
            take = min(avail, remaining)
            if take:
                pool_by_id[candidate_id] = avail - take
                remaining -= take
        return qty - remaining

    key = _normalize_item_name(item_name)
    if not key:
        return 0
    avail = pool_by_name.get(key, 0)
    take = min(avail, qty)
    if take:
        pool_by_name[key] = avail - take
    return take


def _resolve_gear_component(raw_component: dict, mapping: dict, prices: dict, pool_by_id: dict, pool_by_name: dict) -> dict:
    comp_id = raw_component.get("itemId")
    qty = raw_component.get("quantity") or 1
    if comp_id is None:
        name = raw_component.get("itemName") or "Unknown item"
        owned_qty = _take_owned(pool_by_id, pool_by_name, None, name, qty)
        return {
            "itemId": None, "itemName": name, "icon": _untradeable_item_icon(name), "quantity": qty,
            "unitPrice": None, "fullCost": 0, "cost": 0,
            "ownedQty": owned_qty, "owned": owned_qty >= qty,
        }
    meta = mapping.get(str(comp_id), {})
    name = raw_component.get("itemName") or meta.get("name") or f"Item #{comp_id}"
    icon = item_icon_url(meta.get("icon"))
    unit_price, _ = unit_price_for(comp_id, prices)
    price = unit_price if unit_price is not None else 0
    owned_qty = _take_owned(pool_by_id, pool_by_name, comp_id, name, qty)
    remaining = max(qty - owned_qty, 0)
    return {
        "itemId": comp_id, "itemName": name, "icon": icon, "quantity": qty,
        "unitPrice": unit_price, "fullCost": price * qty, "cost": price * remaining,
        "ownedQty": owned_qty, "owned": owned_qty >= qty,
    }


def _resolve_gear_component_display_only(raw_component: dict, mapping: dict, prices: dict) -> dict:
    """Resolve a component purely for display (tooltip) purposes, used
    when the whole combined item is already owned outright -- in that
    case the individual components are never claimed from the owned
    pool, since the assembled item itself was."""
    comp_id = raw_component.get("itemId")
    qty = raw_component.get("quantity") or 1
    if comp_id is None:
        name = raw_component.get("itemName") or "Unknown item"
        return {
            "itemId": None, "itemName": name, "icon": _untradeable_item_icon(name), "quantity": qty,
            "unitPrice": None, "fullCost": 0, "cost": 0, "ownedQty": qty, "owned": True,
        }
    meta = mapping.get(str(comp_id), {})
    name = raw_component.get("itemName") or meta.get("name") or f"Item #{comp_id}"
    icon = item_icon_url(meta.get("icon"))
    unit_price, _ = unit_price_for(comp_id, prices)
    price = unit_price if unit_price is not None else 0
    return {
        "itemId": comp_id, "itemName": name, "icon": icon, "quantity": qty,
        "unitPrice": unit_price, "fullCost": price * qty, "cost": 0,
        "ownedQty": qty, "owned": True,
    }


# A handful of top-end weapons/staves exist as two separate real OSRS
# items -- an "uncharged" form that IS Grand Exchange tradeable, and a
# "charged" form (filled with its consumable resource -- blood runes,
# zulrah scales, coins, etc.) that can never be traded and so has no GE
# listing of its own. The charged form still has its own real, permanent
# item id (see app/data/item_ids.json), so _take_owned already matches
# it correctly -- the only gap was that _resolve_gear_slot_item's plain-
# untradeable branch had nothing to price it against, leaving it at
# unitPrice: null / cost: 0 even though it's easily the most expensive
# thing in the setup.
#
# The wiki also documents a "(full)" recharge recipe for a few of these
# (uncharged item + the full rune/coin cost to fill it), but that's
# deliberately NOT used here -- it would price in the entire recharge
# cost on top of the uncharged item, when charges are a separate,
# variable, consumed resource rather than a one-time acquisition cost.
# Instead this pins the charged item's displayed price to its uncharged
# counterpart's live price alone, exactly as asked.
#
# Keys are lowercased charged-item names (as the plugin/game itself
# names them); values are the uncharged counterpart's real name, spelled
# exactly as it appears in app/data/item_ids.json so find_item_ids can
# resolve it to a real item id. Every pair below was verified directly
# against that snapshot rather than assumed from the naming pattern,
# since the convention isn't consistent across items (some are
# "X (uncharged)", tridents are "Uncharged X", a few bowfa-family bows
# are "X (u)", and the blowpipe is "X (empty)"). Scoped to weapons/
# staves specifically, matching what was asked -- other items that also
# happen to have an "(uncharged)" name (jewellery, ammo-slot charges,
# degradable armour, etc.) work on a different mechanic and aren't
# included here.
CHARGED_TO_UNCHARGED_ITEM_NAME: Dict[str, str] = {
    "scythe of vitur": "Scythe of Vitur (uncharged)",
    "corrupted scythe of vitur": "Corrupted scythe of vitur (uncharged)",
    "holy scythe of vitur": "Holy scythe of vitur (uncharged)",
    "sanguine scythe of vitur": "Sanguine scythe of vitur (uncharged)",
    "sanguinesti staff": "Sanguinesti staff (uncharged)",
    "holy sanguinesti staff": "Holy sanguinesti staff (uncharged)",
    "tumeken's shadow": "Tumeken's shadow (uncharged)",
    "corrupted tumeken's shadow": "Corrupted tumeken's shadow (uncharged)",
    "toxic staff of the dead": "Toxic staff (uncharged)",
    "warped sceptre": "Warped sceptre (uncharged)",
    "toxic blowpipe": "Toxic blowpipe (empty)",
    "trident of the seas": "Uncharged trident",
    "trident of the swamp": "Uncharged toxic trident",
    "venator bow": "Venator bow (uncharged)",
    "echo venator bow": "Echo venator bow (uncharged)",
    "lithic sceptre": "Lithic sceptre (uncharged)",
    "pharaoh's sceptre": "Pharaoh's sceptre (uncharged)",
    "tonalztics of ralos": "Tonalztics of Ralos (uncharged)",
    "craw's bow": "Craw's bow (u)",
    "webweaver bow": "Webweaver bow (u)",
    "thammaron's sceptre": "Thammaron's sceptre (u)",
    "accursed sceptre": "Accursed sceptre (u)",
}


def _charged_item_price(name: Optional[str], prices: dict) -> Tuple[Optional[int], Optional[str]]:
    """For a charged weapon (see CHARGED_TO_UNCHARGED_ITEM_NAME above),
    returns the live price of its uncharged counterpart -- same shape as
    unit_price_for, (unit_price, price_source), both None if name isn't
    a known charged variant or its uncharged counterpart has no current
    price. A name can resolve to more than one real item id (e.g. a
    Pharaoh's sceptre's several charge-count variants); every id is
    tried in turn until one has a live GE price."""
    uncharged_name = CHARGED_TO_UNCHARGED_ITEM_NAME.get((name or "").strip().lower())
    if not uncharged_name:
        return None, None
    for candidate_id in find_item_ids(uncharged_name) or []:
        unit_price, price_source = unit_price_for(candidate_id, prices)
        if unit_price is not None:
            return unit_price, price_source
    return None, None


# Crystal helm/body/legs (see _CRYSTAL_ARMOUR_COLOR_SUFFIX_RE above for
# the eight house colours each comes in) are made from a single Crystal
# armour seed plus 50 Crystal shards sung together at a singing bowl --
# no GE listing of their own, same shape as the charged weapons above.
# The wiki's own item-combination recipe data for these three items
# (app/data/recipes.json) is unreliable, though: for the plain/undyed
# form specifically, it documents the *recolouring* recipe (turning an
# already-owned Amlodd-coloured piece back to the default colour with a
# Crystal of Meilyr) rather than how to acquire the piece in the first
# place -- and since that recipe's own material is itself an
# (also-recipe-having) coloured variant of the very same item, walking
# it via _expand_materials terminates (the depth/seen guards see to
# that) but bottoms out treating "Crystal helm" as one of its own,
# unpriced (cost 0) components. Rather than trying to fix that data in
# place, this bypasses the recipe/components path entirely for these
# three items and, per how the user wants this priced, just pins them
# to the Crystal armour seed's own live price (the 50 crystal shards
# are comparatively minor and highly variable in value -- even the
# wiki's own page for these prices them with a multi-line fallback
# formula -- so left out, same simplification as the charged weapons'
# uncharged-price-only pricing above).
_CRYSTAL_ARMOUR_PIECE_NAMES = {"crystal helm", "crystal body", "crystal legs"}
_CRYSTAL_ARMOUR_SEED_NAME = "Crystal armour seed"


def is_crystal_armour_piece(name: Optional[str]) -> bool:
    """True for "Crystal helm"/"Crystal body"/"Crystal legs", in any of
    their eight house colours (e.g. "Crystal helm (ithell)") -- see
    _CRYSTAL_ARMOUR_PIECE_NAMES above for why these specifically need
    special handling."""
    return _strip_cosmetic_item_suffix((name or "").strip()).strip().lower() in _CRYSTAL_ARMOUR_PIECE_NAMES


def _crystal_armour_seed_price(name: Optional[str], prices: dict) -> Tuple[Optional[int], Optional[str]]:
    """For a crystal helm/body/legs (any colour), returns the live price
    of a Crystal armour seed -- same shape as unit_price_for,
    (unit_price, price_source), both None if name isn't one of these
    three items or the seed currently has no live price."""
    if not is_crystal_armour_piece(name):
        return None, None
    for candidate_id in find_item_ids(_CRYSTAL_ARMOUR_SEED_NAME) or []:
        unit_price, price_source = unit_price_for(candidate_id, prices)
        if unit_price is not None:
            return unit_price, price_source
    return None, None


def _untradeable_item_icon(name: str) -> Optional[str]:
    """An untradeable item obviously has no Grand Exchange icon of its
    own, but we may still know its real wiki icon regardless -- either
    because it's a known item-combination recipe's output (see
    app/recipes.py, checked first since that's the more specific,
    already-loaded lookup) or, more generally, because it's simply a
    known OSRS item at all (see app/item_ids.py, which covers every
    item in the game, tradeable or not). Without this, every
    untradeable/combo slot would fall back to the frontend's plain
    text-abbreviation placeholder even for an item we can picture
    perfectly well, which is exactly the gap that made Avernic treads
    (max) (and friends) look broken once actually placed into a slot
    despite showing correctly in search."""
    recipe = find_recipe(name)
    if recipe and recipe.get("icon"):
        return item_icon_url(recipe["icon"])
    return item_icon_url(find_item_icon(name))


def _resolve_gear_slot_item(raw_item: Optional[dict], mapping: dict, prices: dict, pool_by_id: dict, pool_by_name: dict) -> Optional[dict]:
    """Turn a stored slot item (or None, for an empty slot) into the
    priced/iconed shape the frontend renders. See GearSlotItemIn's
    docstring in app/schemas.py for the three possible shapes -- this
    is a direct port of Maintrius's own _resolve_gear_slot_item.

    A stored item may still carry a leftover "supplies" key from before
    that shape was removed (see PotionStorageItem's docstring in
    app/models.py) -- there's nothing to do about that here, it's
    simply ignored, and the item resolves normally based on its actual
    item id/components exactly as if that key had never been set."""
    if not raw_item:
        return None
    item_id = raw_item.get("itemId")
    components_raw = raw_item.get("components")

    # Crystal helm/body/legs specifically -- checked first, ahead of
    # both the combo and plain-untradeable branches below, so this
    # takes over regardless of whatever (possibly still the old, wrong)
    # components a setup saved earlier may already have stored for one
    # -- see _crystal_armour_seed_price's docstring for why that data
    # can't be trusted. Falls through to the normal handling below only
    # if the seed itself currently has no live price to pin to.
    if item_id is None:
        name = raw_item.get("itemName") or ""
        crystal_price, crystal_price_source = _crystal_armour_seed_price(name, prices)
        if crystal_price is not None:
            owned = _take_owned(pool_by_id, pool_by_name, None, name, 1) >= 1
            return {
                "itemId": None, "itemName": name, "icon": _untradeable_item_icon(name), "tradeable": False,
                "unitPrice": crystal_price, "priceSource": crystal_price_source, "fullCost": crystal_price,
                "cost": 0 if owned else crystal_price, "owned": owned, "components": None,
            }

    if item_id is None and components_raw:
        name = raw_item.get("itemName") or "Combined item"
        icon = _untradeable_item_icon(name)
        whole_owned = _take_owned(pool_by_id, pool_by_name, None, name, 1) >= 1
        if whole_owned:
            components = [_resolve_gear_component_display_only(c, mapping, prices) for c in components_raw]
            total_full = sum(c["fullCost"] for c in components)
            return {
                "itemId": None, "itemName": name, "icon": icon, "tradeable": False,
                "unitPrice": None, "priceSource": None, "fullCost": total_full,
                "cost": 0, "owned": True, "components": components,
            }
        components = [_resolve_gear_component(c, mapping, prices, pool_by_id, pool_by_name) for c in components_raw]
        total_full = sum(c["fullCost"] for c in components)
        total_cost = sum(c["cost"] for c in components)
        return {
            "itemId": None, "itemName": name, "icon": icon, "tradeable": False,
            "unitPrice": None, "priceSource": None, "fullCost": total_full,
            "cost": total_cost, "owned": total_cost == 0 and all(c["owned"] for c in components),
            "components": components,
        }
    if item_id is None:
        name = raw_item.get("itemName") or "Untradeable item"
        owned = _take_owned(pool_by_id, pool_by_name, None, name, 1) >= 1
        # No GE listing of its own -- but if this is a known charged
        # weapon variant (Scythe of Vitur, Toxic blowpipe, Trident of
        # the Seas, etc.), price it against its uncharged counterpart's
        # live price instead of leaving it at 0. See
        # CHARGED_TO_UNCHARGED_ITEM_NAME for the full list and reasoning.
        unit_price, price_source = _charged_item_price(name, prices)
        price = unit_price if unit_price is not None else 0
        return {
            "itemId": None, "itemName": name, "icon": _untradeable_item_icon(name), "tradeable": False,
            "unitPrice": unit_price, "priceSource": price_source, "fullCost": price,
            "cost": 0 if owned else price, "owned": owned, "components": None,
        }
    meta = mapping.get(str(item_id), {})
    name = raw_item.get("itemName") or meta.get("name") or f"Item #{item_id}"
    icon = item_icon_url(meta.get("icon"))
    unit_price, price_source = unit_price_for(item_id, prices)
    price = unit_price if unit_price is not None else 0
    owned = _take_owned(pool_by_id, pool_by_name, item_id, name, 1) >= 1
    return {
        "itemId": item_id, "itemName": name, "icon": icon, "tradeable": True,
        "unitPrice": unit_price, "priceSource": price_source, "fullCost": price,
        "cost": 0 if owned else price, "owned": owned, "components": None,
    }


def resolve_gear_setup_icon(raw_icon: Optional[dict], mapping: dict) -> Optional[dict]:
    """Resolve a setup's display-only icon -- just a name + icon URL, no
    price/ownership attached since it never affects cost. An untradeable
    icon pick (a pet, a quest reward, anything with no GE listing --
    "Tumeken's guardian" being the reported case) used to always come
    back with icon: None here, falling back to the frontend's plain
    text-abbreviation placeholder even when we know its real wiki icon
    perfectly well -- the same gap _untradeable_item_icon already closes
    for gear-slot items (see its docstring), just never wired up here
    too."""
    if not raw_icon:
        return None
    item_id = raw_icon.get("itemId")
    if item_id is not None:
        meta = mapping.get(str(item_id), {})
        name = raw_icon.get("itemName") or meta.get("name") or f"Item #{item_id}"
        icon = item_icon_url(meta.get("icon"))
        return {"itemId": item_id, "itemName": name, "icon": icon, "tradeable": True}
    name = raw_icon.get("itemName") or "Item"
    return {"itemId": None, "itemName": name, "icon": _untradeable_item_icon(name), "tradeable": False}


def _mark_slot_affordability(resolved: Optional[dict], coins: int) -> Optional[dict]:
    if resolved is None:
        return None
    # A plain-untradeable item can still carry a real unitPrice -- a
    # charged weapon priced off its uncharged counterpart, or crystal
    # armour priced off a Crystal armour seed (see _charged_item_price
    # and _crystal_armour_seed_price) -- and that's just as much a real,
    # actionable savings target as anything actually GE-buyable, even
    # though there's no direct "buy this exact item" GE listing behind
    # it. Without this, those slots priced fine (fullCost/cost were
    # already correct) but still showed "n/a" in the Still to Purchase
    # list and could never become the highlighted next-purchase target.
    purchasable = (
        resolved["tradeable"] or resolved.get("components") is not None or resolved.get("unitPrice") is not None
    )
    resolved["purchasable"] = purchasable
    resolved["affordable"] = (
        not resolved["owned"] and purchasable and resolved["cost"] > 0 and coins >= resolved["cost"]
    )
    return resolved


def _still_to_purchase_summary(equipment: dict, inventory: list, coins: int) -> Tuple[List[dict], Optional[dict]]:
    pending = [r for r in equipment.values() if r and not r["owned"]]
    pending += [r for r in inventory if r and not r["owned"]]
    pending.sort(key=lambda r: (0 if r["purchasable"] else 1, r["cost"]))

    still_to_purchase = [
        {
            "itemName": r["itemName"], "icon": r["icon"], "tradeable": r["tradeable"],
            "isCombo": r.get("components") is not None, "purchasable": r["purchasable"], "cost": r["cost"],
        }
        for r in pending
    ]

    next_purchase = next((item for item in still_to_purchase if item["purchasable"]), None)
    if next_purchase:
        cost = next_purchase["cost"]
        next_purchase = {
            **next_purchase,
            "progressPct": 100.0 if cost <= 0 else round(min(coins, cost) / cost * 100, 1),
            "funded": coins >= cost,
        }
    return still_to_purchase, next_purchase


def _build_owned_pools(db: Session, player: Player) -> Tuple[Dict[int, int], Dict[str, int]]:
    """Combines bank+inventory+equipment+potion storage into the same
    shape Maintrius's own load_character_snapshot() produced
    (totalsById/totalsByName) -- the "everything currently owned" pool
    every gear setup checks itself against independently (see
    build_gear_setups, which takes a fresh copy of this per setup).

    Potion storage (added alongside PotionStorageItem in app/models.py)
    slots in here with zero special-casing: the plugin already reports
    it in the exact same item-id/quantity shape as bank/inventory/
    equipment (see MyscapePlugin#readPotionStorageItems in the
    Mootrius/myscape-plugin repo), so it just needs its own query
    added, same as the other three."""
    pool_by_id: Dict[int, int] = {}
    pool_by_name: Dict[str, int] = {}

    def add(item_id: int, item_name: Optional[str], quantity: int):
        pool_by_id[item_id] = pool_by_id.get(item_id, 0) + quantity
        if item_name:
            key = _normalize_item_name(item_name)
            pool_by_name[key] = pool_by_name.get(key, 0) + quantity

    for item in db.query(BankItem).filter(BankItem.player_id == player.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(InventoryItem).filter(InventoryItem.player_id == player.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(EquipmentItem).filter(EquipmentItem.player_id == player.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(PotionStorageItem).filter(PotionStorageItem.player_id == player.id).all():
        add(item.item_id, item.item_name, item.quantity)

    return pool_by_id, pool_by_name


def _player_coins(db: Session, player: Player) -> int:
    """GP in possession, same as Maintrius: bank-only (not inventory or
    equipped), specifically so withdrawing coins to go shopping doesn't
    make the total look like it dropped -- see load_character_snapshot's
    docstring in the original osrs_tracker.py for the full reasoning,
    which applies just as much here."""
    row = (
        db.query(BankItem)
        .filter(BankItem.player_id == player.id, BankItem.item_id == COINS_ITEM_ID)
        .first()
    )
    return row.quantity if row else 0


def build_gear_setups(db: Session, player: Player, mapping: dict, prices: dict, coins: int) -> List[dict]:
    setups = db.query(GearSetup).filter(GearSetup.player_id == player.id).order_by(GearSetup.created_at).all()
    base_pool_by_id, base_pool_by_name = _build_owned_pools(db, player)

    results = []
    for s in setups:
        total_cost = 0
        total_full_cost = 0
        # Fresh copy per setup -- see the docstring on Maintrius's own
        # build_gear_setups for why (setups are alternate goals, not
        # simultaneous requirements; the same owned Basilisk jaw can
        # cover more than one setup's need for it).
        pool_by_id = dict(base_pool_by_id)
        pool_by_name = dict(base_pool_by_name)

        equipment = {}
        setup_equipment = s.equipment or {}
        for slot in EQUIPMENT_SLOTS:
            resolved = _mark_slot_affordability(
                _resolve_gear_slot_item(setup_equipment.get(slot), mapping, prices, pool_by_id, pool_by_name),
                coins,
            )
            equipment[slot] = resolved
            if resolved:
                total_cost += resolved["cost"]
                total_full_cost += resolved["fullCost"]

        inventory = []
        setup_inventory = s.inventory or [None] * INVENTORY_SIZE
        for raw_item in setup_inventory:
            resolved = _mark_slot_affordability(
                _resolve_gear_slot_item(raw_item, mapping, prices, pool_by_id, pool_by_name), coins
            )
            inventory.append(resolved)
            if resolved:
                total_cost += resolved["cost"]
                total_full_cost += resolved["fullCost"]

        progress_pct = 100.0 if total_cost <= 0 else round(min(coins, total_cost) / total_cost * 100, 1)
        still_to_purchase, next_purchase = _still_to_purchase_summary(equipment, inventory, coins)
        results.append({
            "id": str(s.id),
            "name": s.name or "Untitled Setup",
            "createdAt": s.created_at.isoformat() if s.created_at else None,
            "icon": resolve_gear_setup_icon(s.icon, mapping),
            "equipment": equipment,
            "inventory": inventory,
            "totalCost": total_cost,
            "totalFullCost": total_full_cost,
            "totalOwnedSavings": max(total_full_cost - total_cost, 0),
            "progressPct": progress_pct,
            "funded": coins >= total_cost,
            "stillToPurchase": still_to_purchase,
            "nextPurchase": next_purchase,
        })
    return results


def build_purchase_goals_state(db: Session, player: Player) -> dict:
    """The Purchase Goals page's own poll payload -- coins, every gear
    setup (fully priced/owned-checked), the owned-items pool (for any
    future UI that wants to show it), and whatever wiki fetch errors are
    currently in effect. A slimmed-down build_state(): Maintrius's own
    version also folded in Loot Tracker data, which has no equivalent
    here yet."""
    mapping, mapping_err = get_mapping()
    prices, prices_err = get_latest_prices()
    coins = _player_coins(db, player)
    _, pool_by_name = _build_owned_pools(db, player)

    return {
        "coins": coins,
        "pricesError": prices_err,
        "mappingError": mapping_err,
        # Most expensive setup (full cost, ignoring what's already owned)
        # first -- same as Maintrius's own build_state.
        "gearSetups": sorted(build_gear_setups(db, player, mapping, prices, coins), key=lambda s: -s["totalFullCost"]),
        "ownedItems": pool_by_name,
    }

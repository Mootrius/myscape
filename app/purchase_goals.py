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
import pathlib
import re
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.item_ids import find_item_by_exact_name, find_item_icon, find_item_ids, search_item_names
from app.models import (
    BankItem,
    EquipmentItem,
    ForestryKitItem,
    GearSetup,
    InventoryItem,
    MasterScrollBookItem,
    Player,
    PohItem,
    PotionStorageItem,
    RunePouchItem,
    SeedBoxItem,
    SeedVaultItem,
    TackleBoxItem,
)
from app.recipes import find_recipe, search_recipe_names
from app.schemas import GEAR_SETUP_EQUIPMENT_SLOTS, INVENTORY_SIZE

# OSRS's own item id for coins -- used to read "gp in the bank" straight
# off the synced bank_items rows, the same way the original tool's
# load_character_snapshot() read it straight off bank.json.
COINS_ITEM_ID = 995

# The OSRS Wiki Real-time Prices API requires a descriptive User-Agent
# identifying the tool and how to reach whoever runs it -- see
# https://prices.runescape.wiki/osrs/faqs
API_BASE = "https://prices.runescape.wiki/api/v2/osrs"
# Icons used to be hotlinked straight to the wiki from the browser on
# every page load, on the assumption that the wiki's image host sat
# behind a Cloudflare bot challenge a plain server-side request could
# never pass. In practice a plain server-side request goes through
# fine -- and the wiki's own Special:FilePath link is actually two
# uncacheable redirects in front of the real (long-cacheable) image, so
# hotlinking it meant re-hitting the wiki twice per icon on every single
# refresh, which is what was tripping rate limits. item_icon_url below
# (and npc_icon_url in app/loot.py) now always points at our own
# /icon-cache/<filename> route instead (see app/icon_cache.py) --
# nothing in this file talks to the wiki's image host directly any
# more, so there's no ICON_PATH_BASE constant here either; icon_cache.py
# has its own copy of the wiki's Special:FilePath base for the one
# place that still needs it.
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
        # highalch/members ride along unused by every existing caller
        # here (gear setups only ever needed name/icon), but cost
        # nothing extra to keep -- see Storages Viewer's
        # app/possessions.py, which reuses this same mapping for its
        # High Alch value / Tradeable toggles rather than re-fetching
        # the ~860KB payload a second time under a different cache.
        by_id = {
            str(entry["id"]): {
                "name": entry.get("name"),
                "icon": entry.get("icon"),
                "highalch": entry.get("highalch"),
                "members": entry.get("members"),
            }
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
    # Always our own /icon-cache/<filename> route (app/main.py) now,
    # never a direct wiki hotlink -- that route (via
    # ensure_cached_icon_path in app/icon_cache.py) is what actually
    # fetches-and-caches an icon this is the first request for. See
    # that module's own top-of-file comment for why handing the browser
    # a direct wiki fallback here, even just for a brand new icon's
    # first render, was itself enough to trip the wiki's rate limiting
    # on a page -- Storages Viewer especially -- showing enough
    # never-before-seen icons at once.
    return "/icon-cache/" + urllib.parse.quote(icon_filename)


def unit_price_for(item_id: int, prices: dict) -> Tuple[Optional[int], Optional[str]]:
    p = prices.get(str(item_id))
    if not p:
        return None, None
    if p.get("high") is not None:
        return p["high"], "high (instant-buy)"
    if p.get("low") is not None:
        return p["low"], "low (instant-sell, no recent buy trades)"
    return None, None


# Ported from RuneLite's own "Item Prices" plugin -- the table behind
# the "GE: 5.47M gp" tooltip it shows when you hover an untradeable
# item in-game (e.g. a Crystal helm, priced as 1x Crystal armour seed).
# The OSRS Wiki's price-mapping API (get_mapping()/get_latest_prices()
# above) simply doesn't carry this data at all -- an untradeable has no
# GE listing, so it isn't in that API's item table to begin with -- so
# this is a genuinely separate data source: {untradeableItemId:
# [{"itemId": tradeableItemId, "qty": int}, ...]}, built offline by
# scripts/fetch_untradeable_mapping.py from RuneLite's own
# net.runelite.client.game.ItemMapping (BSD 2-Clause licensed) and
# regenerated by hand the same rare way item_ids.json/recipes.json are
# -- see that script's own docstring for the full provenance and for
# why a couple of RuneLite's own quirks (chained/recursive mappings,
# charge-state variant grouping) are already resolved ahead of time in
# the shipped JSON rather than walked here.
UNTRADEABLE_MAPPING_PATH = pathlib.Path(__file__).resolve().parent / "data" / "untradeable_mapping.json"
_untradeable_mapping_index: Optional[Dict[str, list]] = None

# Hand-picked one-off additions on top of the RuneLite-ported table
# above, for an untradeable<->tradeable price link that table doesn't
# happen to carry but we've found and want anyway. Kept as its own
# small dict rather than edited into untradeable_mapping.json itself,
# so a future re-run of scripts/fetch_untradeable_mapping.py (which
# fully regenerates that file from RuneLite's own upstream data) can
# never silently drop one of these -- get_untradeable_mapping merges
# this in every time, after loading the file fresh. Same entry shape
# as the JSON file's own: {untradeableItemId: [{"itemId":
# tradeableItemId, "qty": int}, ...]}. Add more here as they turn up.
_MANUAL_UNTRADEABLE_PRICE_LINKS: Dict[str, list] = {
    # Chugging barrel (the assembled/charged Tempoross reward, item id
    # 30000) has no GE listing of its own -- only Chugging barrel
    # (disassembled), id 30002, is actually sold on the Grand Exchange
    # -- so it prices the same way a charged/degraded item elsewhere in
    # this table already does: 1:1 off its tradeable counterpart.
    "30000": [{"itemId": 30002, "qty": 1}],
}


def get_untradeable_mapping() -> Dict[str, list]:
    global _untradeable_mapping_index
    if _untradeable_mapping_index is None:
        try:
            with open(UNTRADEABLE_MAPPING_PATH, "r", encoding="utf-8") as f:
                base = json.load(f)
        except (OSError, json.JSONDecodeError):
            base = {}
        _untradeable_mapping_index = {**base, **_MANUAL_UNTRADEABLE_PRICE_LINKS}
    return _untradeable_mapping_index


def derived_price_for(item_id: int, prices: dict) -> Tuple[Optional[int], Optional[str]]:
    """Same shape as unit_price_for -- (unit_price, price_source), both
    None if item_id isn't a known untradeable-with-a-linked-value (most
    untradeables genuinely have no such link) or none of its linked
    component(s) currently have a live price of their own. Most entries
    link to a single component at quantity 1 (a straight substitution,
    like Black mask -> Black mask (10)); a few sum more than one
    (an "Echo" Barrows piece prices as its plain counterpart PLUS its
    ornament kit) or multiply a quantity greater than 1 (Crystal legs =
    2x Crystal armour seed). A component with no live price of its own
    right now is simply left out of the sum rather than voiding the
    whole result -- same as RuneLite's own ItemManager does -- so this
    only returns None outright when EVERY linked component is
    unpriced."""
    components = get_untradeable_mapping().get(str(item_id))
    if not components:
        return None, None
    total = 0
    priced_any = False
    for component in components:
        price, _ = unit_price_for(component["itemId"], prices)
        if price is not None:
            total += price * component["qty"]
            priced_any = True
    if not priced_any:
        return None, None
    return total, "derived (linked item)"


def search_items(query: str, limit: int = 20) -> List[dict]:
    mapping, _ = get_mapping()
    q = query.strip().lower()
    if not q:
        return []

    # A player typing a short, precise name -- like "Dom", the Doom of
    # Mokhaiotl's pet -- almost always means an EXACT match, even when
    # dozens of longer, unrelated names merely CONTAIN the same letters
    # ("Saradomin brew", "Saradomin boots", "Saradomin coif", ...).
    # Those "contains" matches can easily fill up the entire `limit` on
    # their own from the tradeable-item tier alone, before the tier
    # that actually holds "Dom" -- an untradeable pet, so only the
    # item-id snapshot fallback three tiers down even knows about it --
    # ever gets a chance to run at all. So: look for an exact
    # (case-insensitive) name match across every tier FIRST, in the
    # same priority order the three tiers already run in below
    # (tradeable mapping, then known recipes, then the general item-id
    # snapshot), and guarantee it as result #1 whenever one exists,
    # entirely independent of whatever the normal startswith/contains
    # scan below would have found on its own.
    exact = None
    for item_id, meta in mapping.items():
        name = meta.get("name") or ""
        if name.lower() == q:
            exact = {"id": int(item_id), "name": name, "icon": item_icon_url(meta.get("icon")), "tradeable": True}
            break
    if exact is None:
        recipe = find_recipe(q)
        if recipe:
            exact = {"id": None, "name": recipe["name"], "icon": item_icon_url(recipe.get("icon")), "tradeable": False}
    if exact is None:
        entry = find_item_by_exact_name(q)
        if entry and entry.get("name"):
            exact = {"id": None, "name": entry["name"], "icon": item_icon_url(entry.get("icon")), "tradeable": False}
    exact_name_lower = exact["name"].lower() if exact else None
    # One slot of `limit` is reserved for `exact` (inserted at the very
    # end below) so the normal tiers below fill at most limit-1 more --
    # otherwise a search with an exact match would return limit+1
    # results instead of just bumping something off the end.
    fill_limit = limit - 1 if exact else limit

    starts, contains = [], []
    for item_id, meta in mapping.items():
        name = meta.get("name") or ""
        low = name.lower()
        if low == exact_name_lower:
            continue  # already captured as `exact` above
        if low.startswith(q):
            starts.append((item_id, meta))
        elif q in low:
            contains.append((item_id, meta))
    starts.sort(key=lambda kv: len(kv[1].get("name") or ""))
    contains.sort(key=lambda kv: len(kv[1].get("name") or ""))
    combined = (starts + contains)[:fill_limit]
    results = [
        {"id": int(item_id), "name": meta.get("name"), "icon": item_icon_url(meta.get("icon")), "tradeable": True}
        for item_id, meta in combined
    ]

    # Fill any remaining slots with known item-combination recipes (see
    # app/recipes.py) -- e.g. "Neitiznot faceguard" has no Grand
    # Exchange listing of its own, so it would never show up above, but
    # a player should still be able to find it by name and see its icon
    # rather than being told to type it in blind as an untradeable item.
    # Names already matched as a real tradeable item above (or as the
    # exact match) are skipped so nothing appears twice.
    if len(results) < fill_limit:
        seen_names = {r["name"].lower() for r in results}
        if exact_name_lower is not None:
            seen_names.add(exact_name_lower)
        for entry in search_recipe_names(q, fill_limit - len(results), exclude=seen_names):
            results.append({"id": None, "name": entry["name"], "icon": item_icon_url(entry.get("icon")), "tradeable": False})

    # Still short? Fall back to the broader item-id snapshot (see
    # app/item_ids.py), which covers every item in the game -- tradeable
    # or not, recipe output or not (a quest reward, a minigame-only
    # item, anything else neither of the two tiers above knows about).
    # This is what lets search find literally any known OSRS item by
    # name, closing the gap the old "add as an untradeable item"
    # fallback used to paper over for exactly this case.
    if len(results) < fill_limit:
        seen_names = {r["name"].lower() for r in results}
        if exact_name_lower is not None:
            seen_names.add(exact_name_lower)
        for entry in search_item_names(q, fill_limit - len(results), exclude=seen_names):
            if entry.get("name"):
                results.append({"id": None, "name": entry["name"], "icon": item_icon_url(entry.get("icon")), "tradeable": False})

    if exact:
        results.insert(0, exact)

    return results[:limit]


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


def _noted_counterpart_id(item_id: int, mapping: dict) -> Optional[int]:
    """Given a tradeable item's own (unnoted) item id, returns its noted
    counterpart's id -- unnoted_id + 1, OSRS's own structural convention
    for linking every notable item to its note (the same convention
    _noted_id_fallback in app/loot.py relies on for pricing, confirmed
    live against the wiki API: e.g. Adamantite ore is 449 unnoted / 450
    noted). Only returns it when item_id itself is a known tradeable
    item (mapping confirms it -- true by construction here, since every
    caller's item_id already came from mapping/search_items) AND
    item_id + 1 is NOT separately listed in mapping -- a noted item's id
    is never listed there at all (same fact loot.py's fallback relies
    on in the other direction), so finding item_id + 1 present as its
    own distinct mapping entry means it's some other real item, not this
    one's note, and crediting it toward ownership would be wrong."""
    if str(item_id) not in mapping:
        return None
    candidate = item_id + 1
    if str(candidate) in mapping:
        return None
    return candidate


def _take_owned(
    pool_by_id: dict,
    pool_by_name: dict,
    item_id: Optional[int],
    item_name: Optional[str],
    qty: int,
    mapping: Optional[dict] = None,
) -> int:
    """Claim up to qty units of an item from the shared "already own"
    pool (built from bank+inventory+equipment+potion storage -- see
    build_owned_pools below), returning how many were actually
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
    items (see build_owned_pools) and mixing the two for one call
    risks claiming the same physical item twice over. An item can have
    more than one real id (a quest-reward variant, a minigame-only
    version, etc.) -- owning it under any of them counts, and this
    tries them in order until qty is satisfied or they're exhausted.

    A gear slot's required item id is always the UNNOTED canonical id
    (it's configured via search_items, which only ever returns that
    one -- see get_mapping's docstring), but a player's bank can easily
    hold the same item noted (its own, separate item id --
    unnoted_id + 1, see _noted_counterpart_id). Without this, a noted
    copy sitting right there in the bank never counted toward owning
    the unnoted slot at all -- once the exact id comes up short, and a
    `mapping` was passed in, this also checks the noted counterpart's
    id before giving up on that unit."""
    if qty <= 0:
        return 0
    if item_id is not None:
        avail = pool_by_id.get(item_id, 0)
        take = min(avail, qty)
        if take:
            pool_by_id[item_id] = avail - take
        remaining = qty - take
        if remaining > 0 and mapping is not None:
            noted_id = _noted_counterpart_id(item_id, mapping)
            if noted_id is not None:
                avail_noted = pool_by_id.get(noted_id, 0)
                take_noted = min(avail_noted, remaining)
                if take_noted:
                    pool_by_id[noted_id] = avail_noted - take_noted
                    take += take_noted
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
    owned_qty = _take_owned(pool_by_id, pool_by_name, comp_id, name, qty, mapping)
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


# Every one of the special cases that used to live here (charged
# weapons like Scythe of Vitur/Tumeken's Shadow priced off their
# uncharged counterpart, Crystal helm/body/legs priced off a Crystal
# armour seed, Bow of Faerdhinen/Blade of Saeldor, Elidinis' ward (f))
# is now just another entry in the ported RuneLite table
# (derived_price_for/get_untradeable_mapping above) -- it covers all of
# them, plus ~900 more untradeable items these hand-rolled formulas
# never reached (Barrows equipment in every degraded state, dragon
# ornament kits, god sword hilts, and so on). See that table's own
# comment for the two places this changes a previously-hand-tuned
# number: Elidinis' ward (f) no longer adds in the 10,000 Soul runes'
# cost (RuneLite's own table doesn't either), and Bow of
# Faerdhinen/Blade of Saeldor now prices off the depleted "(inactive)"
# bow's own market rate rather than raw material cost -- both a
# deliberate choice to match RuneLite's own numbers everywhere rather
# than keep two disagreeing sources of truth.
def _derived_item_ids(name: Optional[str]) -> List[int]:
    """Every real item id `name` resolves to (see find_item_ids) that
    the ported untradeable mapping actually has an entry for -- i.e.
    every real, permanent id this name could plausibly be (a name can
    resolve to more than one, e.g. a colour/charge variant), filtered
    down to the ones derived_price_for can actually price.

    Crystal helm/body/legs, Bow of Faerdhinen, and Blade of Saeldor all
    come in eight house-colour cosmetic variants (e.g. "Crystal helm
    (ithell)", "Bow of Faerdhinen (amlodd)") that item_ids.json's exact-
    name snapshot never recorded under that exact spelling -- the wiki
    only has one page per base item, not one per colour. A colour-
    suffixed name is retried here with that suffix stripped (see
    _CRYSTAL_ARMOUR_COLOR_SUFFIX_RE -- reused directly, not through
    _strip_cosmetic_item_suffix, since that helper's own "must start
    with 'crystal '" guard would wrongly block Faerdhinen/Saeldor). Any
    house colour of the same piece/weapon prices identically anyway
    (the cosmetic doesn't change the underlying seed/creation cost), so
    landing on the base item's id instead of the exact colour typed is
    harmless for pricing purposes."""
    ids = find_item_ids(name) if name else None
    if not ids and name:
        stripped = _CRYSTAL_ARMOUR_COLOR_SUFFIX_RE.sub("", name.strip()).strip()
        if stripped and stripped.lower() != name.strip().lower():
            ids = find_item_ids(stripped)
    if not ids:
        return []
    covered = get_untradeable_mapping()
    return [i for i in ids if str(i) in covered]


def has_derived_price(name: Optional[str]) -> bool:
    """True when `name` names a known untradeable item with a linked GE
    value available (see derived_price_for) -- independent of whether a
    live price is resolvable for it right now. Used to skip recipe-
    based component auto-expansion for it at write time (see
    set_gear_slot in app/main.py): _resolve_gear_slot_item below always
    prices (and displays) a covered item via this direct linked value,
    ignoring any components a setup has stored for it, so there would
    be nothing to gain from expanding it into components up front."""
    return bool(_derived_item_ids(name))


def derived_price_by_name(name: Optional[str], prices: dict) -> Tuple[Optional[int], Optional[str]]:
    """derived_price_for, but starting from an item's NAME -- for the
    many places in Purchase Goals where an untradeable slot is stored
    with only a name (no real item id was ever resolved/stored for it).
    Tries every real id `name` could be (see _derived_item_ids) in
    turn, same shape as unit_price_for, (unit_price, price_source),
    both None if none of them are covered or priced."""
    for item_id in _derived_item_ids(name):
        price, source = derived_price_for(item_id, prices)
        if price is not None:
            return price, source
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

    # Any untradeable item the ported RuneLite table has a linked value
    # for (derived_price_by_name -- Crystal helm/body/legs, charged
    # weapons, Bow of Faerdhinen/Blade of Saeldor, Elidinis' ward (f),
    # and ~900 more) -- checked first, ahead of both the combo and
    # plain-untradeable branches below, so this takes over regardless of
    # whatever (possibly stale) components a setup saved earlier may
    # already have stored for one. Falls through to the normal handling
    # below only if it isn't a covered item, or is but has no live price
    # to pin to right now.
    if item_id is None:
        name = raw_item.get("itemName") or ""
        special_price, special_price_source = derived_price_by_name(name, prices)
        if special_price is not None:
            owned = _take_owned(pool_by_id, pool_by_name, None, name, 1) >= 1
            return {
                "itemId": None, "itemName": name, "icon": _untradeable_item_icon(name), "tradeable": False,
                "unitPrice": special_price, "priceSource": special_price_source, "fullCost": special_price,
                "cost": 0 if owned else special_price, "owned": owned, "components": None,
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
        # Reaching this branch at all means the derived_price_by_name
        # check up top already came back empty for this name -- no GE
        # listing of its own, and no linked value in the ported
        # RuneLite table either -- so there's genuinely nothing left to
        # price it against.
        unit_price, price_source = None, None
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
    owned = _take_owned(pool_by_id, pool_by_name, item_id, name, 1, mapping) >= 1
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
    # A plain-untradeable item can still carry a real unitPrice -- any
    # item the ported RuneLite table has a linked value for (see
    # derived_price_by_name) -- and that's just as much a real,
    # actionable savings target as anything actually GE-buyable, even
    # though there's no direct "buy this exact item" GE listing behind
    # it. Without this, those slots priced fine (fullCost/cost were
    # already correct) but still showed "n/a" in the Still to Purchase
    # list and could never become the highlighted next-purchase target.
    #
    # A combo (components is not None) used to count as purchasable just
    # for HAVING a components list, regardless of whether any of them
    # actually had a real price -- so a combo built entirely from other
    # untradeable items with no special-case price of their own (Keris
    # partisan of the sun: itself untradeable, made from Keris partisan
    # + Jewel of the Sun, both *also* untradeable) summed to a fullCost
    # of 0 and was still marked purchasable, making it sort as the
    # cheapest possible item and win Next Purchase outright at "0 gp".
    # fullCost > 0 means at least one component actually resolved to a
    # real price, which is what "purchasable" is meant to capture here.
    purchasable = (
        resolved["tradeable"]
        or resolved.get("unitPrice") is not None
        or (resolved.get("components") is not None and resolved.get("fullCost", 0) > 0)
    )
    resolved["purchasable"] = purchasable
    resolved["affordable"] = (
        not resolved["owned"] and purchasable and resolved["cost"] > 0 and coins >= resolved["cost"]
    )
    return resolved


def _still_to_purchase_summary(
    equipment: dict,
    inventory: list,
    coins: int,
    sort_mode: str = "low_to_high",
    custom_order: Optional[list] = None,
) -> Tuple[List[dict], Optional[dict]]:
    # Every pending row also carries the exact slot it came from
    # (slotType/slot) -- a "still to purchase" row IS a specific
    # equipment/inventory slot, and that identity is what "custom" sort
    # mode's drag-and-drop reordering is keyed on (see
    # StillToPurchaseOrderEntryIn in app/schemas.py) -- the same
    # slot-identity shape move_gear_slot_item's from/to already use.
    pending = [(r, "equipment", slot) for slot, r in equipment.items() if r and not r["owned"]]
    pending += [(r, "inventory", idx) for idx, r in enumerate(inventory) if r and not r["owned"]]
    # Fully untradeable -- itself has no GE listing, and (for a combo)
    # none of its components do either, so purchasable is False and
    # there's no live price to ever pin this to (see the fullCost > 0
    # check in _mark_slot_affordability). That's not a "still need to
    # buy this for n/a" line, it's just not a real purchase target at
    # all, so it's left out of the list entirely rather than shown with
    # a "n/a" cost -- Keris partisan of the sun is the reported case.
    pending = [entry for entry in pending if entry[0]["purchasable"]]

    if sort_mode == "high_to_low":
        pending.sort(key=lambda entry: entry[0]["cost"], reverse=True)
    elif sort_mode == "alphabetical":
        pending.sort(key=lambda entry: entry[0]["itemName"].casefold())
    elif sort_mode == "reverse_alphabetical":
        pending.sort(key=lambda entry: entry[0]["itemName"].casefold(), reverse=True)
    elif sort_mode == "custom":
        # Anything not in the player's own saved order (new since they
        # last dragged something, or they've simply never reordered at
        # all yet) falls back to cost-ascending, same as
        # "low_to_high" -- both so a first-time switch to "custom"
        # starts from a sensible order rather than an arbitrary one, and
        # so a freshly-added item doesn't get silently lost at whatever
        # position Python happens to iterate equipment/inventory in.
        order_index = {
            (entry.get("slotType"), str(entry.get("slot"))): i for i, entry in enumerate(custom_order or [])
        }
        pending.sort(
            key=lambda entry: (
                order_index.get((entry[1], str(entry[2])), len(order_index)),
                entry[0]["cost"],
            )
        )
    else:
        pending.sort(key=lambda entry: entry[0]["cost"])

    still_to_purchase = [
        {
            "itemName": r["itemName"], "icon": r["icon"], "tradeable": r["tradeable"],
            "isCombo": r.get("components") is not None, "purchasable": r["purchasable"], "cost": r["cost"],
            "slotType": slot_type, "slot": slot,
        }
        for r, slot_type, slot in pending
    ]

    # Whatever sits at the top of the list above -- cheapest first in
    # "low_to_high", priciest first in "high_to_low", first alphabetically
    # in "alphabetical", last alphabetically in "reverse_alphabetical", or
    # whatever the player last dragged to the top in "custom" -- is what's
    # shown as the next thing to buy. This is
    # deliberately just still_to_purchase[0] rather than a
    # separately-computed cheapest item, so rearranging the list
    # (switching sort mode, or dragging a row to the front in custom mode)
    # always moves the highlighted next purchase along with it.
    next_purchase = still_to_purchase[0] if still_to_purchase else None
    if next_purchase:
        cost = next_purchase["cost"]
        next_purchase = {
            **next_purchase,
            "progressPct": 100.0 if cost <= 0 else round(min(coins, cost) / cost * 100, 1),
            "funded": coins >= cost,
        }
    return still_to_purchase, next_purchase


def build_owned_pools(db: Session, player: Player) -> Tuple[Dict[int, int], Dict[str, int]]:
    """Combines bank+inventory+equipment+potion storage+rune pouch+seed
    vault+tackle box+the whole PoH Costume Room+Forestry Kit+Master
    Scroll Book+Seed Box into the same shape Maintrius's own
    load_character_snapshot() produced (totalsById/totalsByName) -- the
    "everything currently owned" pool every gear setup checks itself
    against independently (see build_gear_setups, which takes a fresh
    copy of this per setup), and also what an item-goal Mindmap node
    checks its target item's count against (see evaluate_completion in
    app/mindmaps.py).

    Potion storage, the rune pouch, the seed vault, the tackle box, the
    PoH Costume Room, the Forestry Kit, the Master Scroll Book, and the
    Seed Box (added alongside PotionStorageItem/RunePouchItem/
    SeedVaultItem/TackleBoxItem/PohItem/ForestryKitItem/
    MasterScrollBookItem/SeedBoxItem in app/models.py) slot in here
    with zero special-casing: the plugin already reports each in the
    exact same item-id/quantity shape as bank/inventory/equipment (see
    MyscapePlugin#readPotionStorageItems/#readRunePouchItems/
    #readSeedVaultItems/#readTackleBoxItems/#readPohItems/
    #readForestryKitItems/#readMasterScrollBookItems/#readSeedBoxItems
    in the Mootrius/myscape-plugin repo), so each just needs its own
    query added, same as the others. Runes owned only inside a pouch
    (or seeds only inside the vault or the seed box, a costume piece
    only in the Costume Room, gear only in a tackle box, or a scroll
    only in the Master Scroll Book) would otherwise never show up here
    at all -- RuneLite's normal inventory scan reports the pouch/kit/
    book/box itself as a single item, not what's stored inside it; the
    seed vault isn't part of any ItemContainer at all; and the rest,
    though genuine ItemContainers same as the bank, are their own
    separate ones this function's usual bank/inventory/equipment sweep
    never touches -- so without this, a setup (or goal node) needing,
    say, fire runes, ranarr seeds, a stored cape, a barbed rod, an
    insect repellent, a teleport scroll, or a boxed seed would keep
    listing them as missing even while a full pouch, vault, Costume
    Room, tackle box, kit, book, or box of them sat right there."""
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
    for item in db.query(RunePouchItem).filter(RunePouchItem.player_id == player.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(SeedVaultItem).filter(SeedVaultItem.player_id == player.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(TackleBoxItem).filter(TackleBoxItem.player_id == player.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(PohItem).filter(PohItem.player_id == player.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(ForestryKitItem).filter(ForestryKitItem.player_id == player.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(MasterScrollBookItem).filter(MasterScrollBookItem.player_id == player.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(SeedBoxItem).filter(SeedBoxItem.player_id == player.id).all():
        add(item.item_id, item.item_name, item.quantity)

    return pool_by_id, pool_by_name


def _player_coins(db: Session, player: Player) -> int:
    """GP in possession, summed across every storage build_owned_pools
    sweeps (bank+inventory+equipment+potion storage+rune pouch+seed
    vault+tackle box+PoH Costume Room+Forestry Kit+Master Scroll Book+
    Seed Box) rather than bank-only, so coins carried in the inventory
    or tucked away in any of those other storages count toward the
    Purchase Goals GP total the same as coins already banked."""
    total = 0
    for model in (
        BankItem,
        InventoryItem,
        EquipmentItem,
        PotionStorageItem,
        RunePouchItem,
        SeedVaultItem,
        TackleBoxItem,
        PohItem,
        ForestryKitItem,
        MasterScrollBookItem,
        SeedBoxItem,
    ):
        row = (
            db.query(model)
            .filter(model.player_id == player.id, model.item_id == COINS_ITEM_ID)
            .first()
        )
        if row:
            total += row.quantity
    return total


def build_gear_setups(db: Session, player: Player, mapping: dict, prices: dict, coins: int) -> List[dict]:
    # sort_order first, created_at second -- see GearSetup's own
    # docstring in app/models.py. Postgres already sorts NULLs last on
    # an ascending order by default, but that's not something to lean
    # on silently -- every setup's sort_order is NULL until a player
    # actually drags one, at which point created_at (itself always
    # oldest-first) is the ENTIRE order, landing new setups at the end
    # exactly where "newest last" wants them; once any reordering has
    # happened, sort_order alone decides it (every setup gets a fresh
    # one on any reorder -- see set_gear_setup_order in app/main.py --
    # so ties needing the created_at tiebreaker again shouldn't occur).
    setups = (
        db.query(GearSetup)
        .filter(GearSetup.player_id == player.id)
        .order_by(GearSetup.sort_order.asc(), GearSetup.created_at.asc())
        .all()
    )
    base_pool_by_id, base_pool_by_name = build_owned_pools(db, player)

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
        for slot in GEAR_SETUP_EQUIPMENT_SLOTS:
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
        sort_mode = s.still_to_purchase_sort_mode or "low_to_high"
        still_to_purchase, next_purchase = _still_to_purchase_summary(
            equipment, inventory, coins, sort_mode, s.still_to_purchase_custom_order
        )
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
            "stillToPurchaseSort": sort_mode,
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
    _, pool_by_name = build_owned_pools(db, player)

    return {
        "coins": coins,
        "pricesError": prices_err,
        "mappingError": mapping_err,
        # Most expensive setup (full cost, ignoring what's already owned)
        # first -- same as Maintrius's own build_state.
        "gearSetups": sorted(build_gear_setups(db, player, mapping, prices, coins), key=lambda s: -s["totalFullCost"]),
        "ownedItems": pool_by_name,
    }

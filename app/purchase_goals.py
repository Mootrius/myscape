"""Purchase Goals: named "gear setups" a player plans and saves toward, ported
from the single-user osrs_tracker.py. The mechanic is unchanged: three
slot-item shapes (plain tradeable, plain untradeable, composed "combo"),
owned-pool bookkeeping, and the affordability / still-to-purchase /
next-purchase computation. Owned items come from the synced storage tables,
wiki data from in-memory process-level caches, and each setup is a per-player
GearSetup row (app/models.py).
"""
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
import uuid
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.item_ids import (
    canonical_master_scroll_item_id,
    find_item_by_exact_name,
    find_item_id_by_icon_filename,
    find_item_ids,
    search_item_names,
)
from app.models import (
    BankItem,
    EquipmentItem,
    ForestryKitItem,
    GameAccount,
    GearSetup,
    InventoryItem,
    MasterScrollBookItem,
    PohItem,
    PotionStorageItem,
    RunePouchItem,
    SeedBoxItem,
    SeedVaultItem,
    TackleBoxItem,
)
from app.recipes import find_recipe, search_recipe_names
from app.schemas import GEAR_SETUP_EQUIPMENT_SLOTS, INVENTORY_SIZE

# OSRS item id for coins; gp is read off the synced bank rows.
COINS_ITEM_ID = 995

# The OSRS Wiki Real-time Prices API requires a descriptive User-Agent with
# contact info; see https://prices.runescape.wiki/osrs/faqs
API_BASE = "https://prices.runescape.wiki/api/v2/osrs"
USER_AGENT = "myscape.io/1.0 (Purchase Goals; contact: chandler@myscape.io)"

# Item icons come from RuneLite's static icon export (cacheable CDN, one PNG per
# numeric item id); item_icon_url builds the URL directly. Names without a known
# id resolve via app/item_ids.py (see _untradeable_item_icon).
# app/icon_cache.py's wiki fetching remains for NPC portraits (app/loot.py) and
# as the last-resort fallback for names with no id.
ITEM_ICON_CDN_BASE = "https://static.runelite.net/cache/item/icon/"

# Cache freshness windows before refetching from the wiki API.
PRICE_TTL_SECONDS = 60
MAPPING_TTL_SECONDS = 24 * 60 * 60  # item mapping barely changes; once a day is plenty

# Process-level caches shared across players: {"fetchedAt": float, "byId":
# {...}, "error": str|None}. The ~860KB mapping changes about daily, so it is
# not refetched per request.
_mapping_cache: Optional[dict] = None
_price_cache: Optional[dict] = None


def _fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_mapping(force: bool = False) -> Tuple[Dict[str, dict], Optional[str]]:
    """Returns ({itemId: {"name":..., "icon":...}}, error|None), refreshing from
    the wiki at most once a day.
    """
    global _mapping_cache
    fresh = _mapping_cache and (time.time() - _mapping_cache["fetchedAt"]) < MAPPING_TTL_SECONDS
    if _mapping_cache and fresh and not force:
        return _mapping_cache["byId"], _mapping_cache.get("error")

    try:
        raw = _fetch_json(f"{API_BASE}/mapping")
        # highalch/members are unused here but kept: app/possessions.py reuses
        # this mapping for its High Alch / Tradeable toggles.
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


def item_icon_url(item_id: Optional[int]) -> Optional[str]:
    """Builds an item icon URL on RuneLite's CDN from a numeric item id. None in,
    None out; the frontend hides a 404 via the icon's onerror handler.
    """
    if item_id is None:
        return None
    return ITEM_ICON_CDN_BASE + str(item_id) + ".png"


def _wiki_icon_url(icon_filename: Optional[str]) -> Optional[str]:
    """Routes a wiki image FILENAME through our /icon-cache/<filename> route
    (app/main.py, app/icon_cache.py) instead of hotlinking. Only used by
    _untradeable_item_icon's last-resort fallback.
    """
    if not icon_filename:
        return None
    if not _ICON_EXT_RE.search(icon_filename):
        icon_filename = icon_filename + ".png"
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


# Ported from RuneLite's "Item Prices" plugin: the table behind the "GE: 5.47M
# gp" tooltip on untradeables (e.g. Crystal helm = 1x Crystal armour seed),
# absent from the wiki price API. Shape: {untradeableItemId: [{"itemId":
# tradeableItemId, "qty": int}, ...]}. Built offline by
# scripts/fetch_untradeable_mapping.py from RuneLite's ItemMapping (BSD
# 2-Clause); see that script for details.
UNTRADEABLE_MAPPING_PATH = pathlib.Path(__file__).resolve().parent / "data" / "untradeable_mapping.json"
_untradeable_mapping_index: Optional[Dict[str, list]] = None

# Hand-picked links missing from the RuneLite table. Kept apart from
# untradeable_mapping.json so regenerating that file cannot drop them;
# get_untradeable_mapping merges them in. Same entry shape.
_MANUAL_UNTRADEABLE_PRICE_LINKS: Dict[str, list] = {
    # The assembled Chugging barrel (id 30000) has no GE listing; only the
    # disassembled one (id 30002) does, so it prices 1:1 off that.
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
    """Same shape as unit_price_for: (unit_price, price_source), both None if
    item_id has no linked value or no component has a live price. Entries may
    sum several components (Echo Barrows piece = piece + ornament kit) or
    multiply a qty (Crystal legs = 2x seed). Unpriced components are skipped,
    as in RuneLite's ItemManager.
    """
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

    # A short name like "Dom" (the Doom of Mokhaiotl pet) usually means an exact
    # match, but longer "contains" matches can fill `limit` before the tier
    # holding an untradeable is reached. So an exact case-insensitive match
    # across all tiers is found first and guaranteed as result #1.
    exact = None
    for item_id, meta in mapping.items():
        name = meta.get("name") or ""
        if name.lower() == q:
            exact = {"id": int(item_id), "name": name, "icon": item_icon_url(int(item_id)), "tradeable": True}
            break
    if exact is None:
        recipe = find_recipe(q)
        if recipe:
            exact = {"id": None, "name": recipe["name"], "icon": _untradeable_item_icon(recipe["name"]), "tradeable": False}
    if exact is None:
        entry = find_item_by_exact_name(q)
        if entry and entry.get("name"):
            exact = {"id": None, "name": entry["name"], "icon": _untradeable_item_icon(entry["name"]), "tradeable": False}
    exact_name_lower = exact["name"].lower() if exact else None
    # One slot of `limit` is reserved for `exact`, inserted at the end.
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
        {"id": int(item_id), "name": meta.get("name"), "icon": item_icon_url(int(item_id)), "tradeable": True}
        for item_id, meta in combined
    ]

    # Fill remaining slots with combination recipes (app/recipes.py) such as
    # "Neitiznot faceguard", which has no GE listing. Names already matched are
    # skipped.
    if len(results) < fill_limit:
        seen_names = {r["name"].lower() for r in results}
        if exact_name_lower is not None:
            seen_names.add(exact_name_lower)
        for entry in search_recipe_names(q, fill_limit - len(results), exclude=seen_names):
            results.append({"id": None, "name": entry["name"], "icon": _untradeable_item_icon(entry["name"]), "tradeable": False})

    # Still short: fall back to the item-id snapshot (app/item_ids.py), which
    # covers every item in the game.
    if len(results) < fill_limit:
        seen_names = {r["name"].lower() for r in results}
        if exact_name_lower is not None:
            seen_names.add(exact_name_lower)
        for entry in search_item_names(q, fill_limit - len(results), exclude=seen_names):
            if entry.get("name"):
                results.append({"id": None, "name": entry["name"], "icon": _untradeable_item_icon(entry["name"]), "tradeable": False})

    if exact:
        results.insert(0, exact)

    return results[:limit]


# Crystal armour recolors (eight Iorwerth Clan houses, e.g. "Crystal helm
# (ithell)") are cosmetic and not reported by the plugin, so the suffix is
# stripped to name-match owned items. Ported from _strip_cosmetic_item_suffix in
# osrs_tracker.py.
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
    """Returns the noted counterpart's id: unnoted_id + 1, as in
    _noted_id_fallback (app/loot.py). Only when item_id is in mapping and
    item_id + 1 is not, since noted ids are never listed there.
    """
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
    """Claim up to qty units of an item from the shared "already own" pool (see
    build_owned_pools), returning how many were available. Pools are mutated
    in place so one physical item satisfies only one requirement.
    
    Tradeable items match by id. Untradeables match by game id when
    app/item_ids.py knows one (avoiding name near-misses; see
    _find_item_ids_with_cosmetic_fallback for colour-suffixed cosmetics), else
    by case-insensitive name. Once ids exist for a name, ids alone are used,
    since pool_by_id and pool_by_name hold the same physical items and mixing
    them could claim one twice. An item with several ids counts under any of
    them.
    
    Gear slots store the UNNOTED id, but the bank may hold the item noted (see
    _noted_counterpart_id); when the exact id falls short and `mapping` is
    passed, the noted id is checked too.
    """
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

    candidate_ids = _find_item_ids_with_cosmetic_fallback(item_name)
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
    icon = item_icon_url(comp_id)
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
    """Resolve a component for display only, when the whole combined item is
    owned and its components are never claimed.
    """
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
    icon = item_icon_url(comp_id)
    unit_price, _ = unit_price_for(comp_id, prices)
    price = unit_price if unit_price is not None else 0
    return {
        "itemId": comp_id, "itemName": name, "icon": icon, "quantity": qty,
        "unitPrice": unit_price, "fullCost": price * qty, "cost": 0,
        "ownedQty": qty, "owned": True,
    }


# Crystal armour, Bow of Faerdhinen (c) and Blade of Saeldor (c) come in eight
# house-colour variants (e.g. "Bow of Faerdhinen (c) (Amlodd)") that
# item_ids.json records only under the base name (see find_item_ids in
# app/item_ids.py). app/data/recipes.json has an entry per colour and feeds
# gear-slot search (search_recipe_names), so such names are valid saved slots.
# The suffix is stripped via _CRYSTAL_ARMOUR_COLOR_SUFFIX_RE (not
# _strip_cosmetic_item_suffix, whose "crystal " guard would block
# Faerdhinen/Saeldor) to recover the base name's ids.
def _find_item_ids_with_cosmetic_fallback(name: Optional[str]) -> Optional[List[int]]:
    """find_item_ids, retried with the house-colour suffix stripped. Used by
    _derived_item_ids (pricing) and _take_owned (ownership).
    """
    ids = find_item_ids(name) if name else None
    if ids or not name:
        return ids
    stripped = _CRYSTAL_ARMOUR_COLOR_SUFFIX_RE.sub("", name.strip()).strip()
    if stripped and stripped.lower() != name.strip().lower():
        return find_item_ids(stripped)
    return None


# Charged weapons, Crystal armour, Bow of Faerdhinen/Blade of Saeldor, Elidinis'
# ward (f) and ~900 other untradeables are priced by the ported RuneLite table
# (derived_price_for), matching RuneLite's numbers.
def _derived_item_ids(name: Optional[str]) -> List[int]:
    """Every item id `name` resolves to that the ported untradeable mapping can
    price. House colours price identically, so the base id is fine.
    """
    ids = _find_item_ids_with_cosmetic_fallback(name)
    if not ids:
        return []
    covered = get_untradeable_mapping()
    return [i for i in ids if str(i) in covered]


def has_derived_price(name: Optional[str]) -> bool:
    """True when `name` is a known untradeable with a linked GE value (live price
    or not). Used to skip recipe-component auto-expansion at write time
    (set_gear_slot in app/main.py), since _resolve_gear_slot_item prices it by
    that value and ignores stored components.
    """
    return bool(_derived_item_ids(name))


def derived_price_by_name(name: Optional[str], prices: dict) -> Tuple[Optional[int], Optional[str]]:
    """derived_price_for starting from an item NAME (untradeable slots may be
    stored without an id). Returns (unit_price, price_source), both None if
    not covered or priced.
    """
    for item_id in _derived_item_ids(name):
        price, source = derived_price_for(item_id, prices)
        if price is not None:
            return price, source
    return None, None


def _untradeable_item_id(name: str) -> Optional[int]:
    """Best item id for a name with no GE listing: the first id app/item_ids.py
    resolves (variants share one icon). None if not in the snapshot.
    """
    ids = find_item_ids(name)
    return ids[0] if ids else None


def _untradeable_item_icon(name: str) -> Optional[str]:
    """Icon URL for an untradeable item: resolves its id via app/item_ids.py and
    builds the CDN icon like a tradeable one.
    
    Names missing from the snapshot (~190 colour variants) fall back to
    find_item_id_by_icon_filename (app/item_ids.py), since recipes.json stores
    each variant's icon filename (e.g. "Crystal helm (Ithell)" -> 27717). Only
    recipes with no id at all fall through to _wiki_icon_url
    (app/icon_cache.py).
    """
    item_id = _untradeable_item_id(name)
    if item_id is not None:
        return item_icon_url(item_id)
    recipe = find_recipe(name)
    if recipe and recipe.get("icon"):
        by_filename = find_item_id_by_icon_filename(recipe["icon"])
        if by_filename is not None:
            return item_icon_url(by_filename)
        return _wiki_icon_url(recipe["icon"])
    return None


def _resolve_gear_slot_item(raw_item: Optional[dict], mapping: dict, prices: dict, pool_by_id: dict, pool_by_name: dict) -> Optional[dict]:
    """Turn a stored slot item (or None) into the priced/iconed shape the
    frontend renders (see GearSlotItemIn in app/schemas.py). Port of
    _resolve_gear_slot_item. A legacy "supplies" key is ignored.
    """
    if not raw_item:
        return None
    item_id = raw_item.get("itemId")
    components_raw = raw_item.get("components")

    # Untradeables with a linked value in the ported RuneLite table
    # (derived_price_by_name) are checked first and override any stale stored
    # components. Falls through if not covered or no live price.
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
        # derived_price_by_name found nothing: no GE listing and no linked
        # value.
        unit_price, price_source = None, None
        price = unit_price if unit_price is not None else 0
        return {
            "itemId": None, "itemName": name, "icon": _untradeable_item_icon(name), "tradeable": False,
            "unitPrice": unit_price, "priceSource": price_source, "fullCost": price,
            "cost": 0 if owned else price, "owned": owned, "components": None,
        }
    meta = mapping.get(str(item_id), {})
    name = raw_item.get("itemName") or meta.get("name") or f"Item #{item_id}"
    icon = item_icon_url(item_id)
    unit_price, price_source = unit_price_for(item_id, prices)
    price = unit_price if unit_price is not None else 0
    owned = _take_owned(pool_by_id, pool_by_name, item_id, name, 1, mapping) >= 1
    return {
        "itemId": item_id, "itemName": name, "icon": icon, "tradeable": True,
        "unitPrice": unit_price, "priceSource": price_source, "fullCost": price,
        "cost": 0 if owned else price, "owned": owned, "components": None,
    }


def resolve_gear_setup_icon(raw_icon: Optional[dict], mapping: dict) -> Optional[dict]:
    """Resolve a setup's display-only icon (name + URL, no price or ownership).
    Untradeable picks (pets, quest rewards) use _untradeable_item_icon.
    """
    if not raw_icon:
        return None
    item_id = raw_icon.get("itemId")
    if item_id is not None:
        meta = mapping.get(str(item_id), {})
        name = raw_icon.get("itemName") or meta.get("name") or f"Item #{item_id}"
        icon = item_icon_url(item_id)
        return {"itemId": item_id, "itemName": name, "icon": icon, "tradeable": True}
    name = raw_icon.get("itemName") or "Item"
    return {"itemId": None, "itemName": name, "icon": _untradeable_item_icon(name), "tradeable": False}


# Runes, food, potions and ammunition are cheap and re-buyable, so slots holding
# them are always treated as owned (never in Still to Purchase / Next Purchase),
# regardless of the real pool. Sourced from the OSRS Wiki's Runes, Food/All
# food, Potions and Ammunition pages; potions are matched by
# _is_dose_style_potion_name. Applied once in _mark_slot_affordability. Names
# match lowercased.

# All 24 current rune types (elemental, catalytic, combination, Sunfire, Wrath,
# the elemental-mix runes, and the Cabbage rune joke item); see
# https://oldschool.runescape.wiki/w/Runes. Talismans/tiaras are not runes.
_ALWAYS_ATTAINABLE_RUNE_NAMES = frozenset({
    "air rune", "mind rune", "water rune", "earth rune", "fire rune",
    "body rune", "cosmic rune", "chaos rune", "nature rune", "law rune",
    "death rune", "sunfire rune", "astral rune", "blood rune", "soul rune",
    "wrath rune", "mist rune", "dust rune", "mud rune", "smoke rune",
    "steam rune", "lava rune", "aether rune", "cabbage rune",
})

# Realistic edible food; see https://oldschool.runescape.wiki/w/Food/All_food.
# Excludes raw ingredients, half-finished pies, and novelty minigame/quest food.
_ALWAYS_ATTAINABLE_FOOD_NAMES = frozenset({
    # Fish
    "shrimps", "anchovies", "sardine", "salmon", "trout", "giant carp",
    "cod", "herring", "pike", "mackerel", "tuna", "bass", "swordfish",
    "lobster", "shark", "manta ray", "sea turtle", "monkfish", "anglerfish",
    "dark crab", "karambwan", "cooked karambwan", "blighted anglerfish",
    "blighted karambwan", "blighted manta ray", "cave eel", "lava eel",
    "bluefin", "marlin", "haddock", "halibut", "edible seaweed",
    # Meat and other mains
    "cooked chicken", "cooked meat", "cooked chompy", "cooked jubbly",
    "cooked rabbit", "cooked t-bone steak", "cooked wild kebbit",
    "cooked sweetcorn", "cooked oomlie wrap", "cooked giant crab meat",
    "giant crab meat", "giant frog legs", "roast beast meat",
    "roast bird meat", "roast rabbit", "ugthanki meat", "ugthanki kebab",
    "ugthanki kebab (bad)", "kebab", "toad's legs", "spicy toad's legs",
    # Pies and pizzas
    "admiral pie", "apple pie", "botanical pie", "fish pie", "garden pie",
    "meat pie", "mud pie", "mushroom pie", "pumpkin pie", "redberry pie",
    "dragonfruit pie", "anchovy pizza", "meat pizza", "pineapple pizza",
    "plain pizza",
    # Potatoes, cakes, and other baked goods
    "baked potato", "chilli potato", "egg potato", "mushroom potato",
    "potato with butter", "potato with cheese", "potato", "tuna potato",
    "cake", "chocolate cake", "chocolate bar", "chocolate bomb", "bread",
    "baguette", "roll", "cooking apple",
    # Fruit and vegetables
    "banana", "bruised banana", "cabbage", "lemon", "lemon chunks",
    "lemon slices", "lime", "lime chunks", "lime slices", "orange",
    "orange chunks", "orange slices", "pineapple", "pineapple chunks",
    "pineapple ring", "peach", "pumpkin", "tomato", "chopped tomato",
    "onion", "chopped onion", "onion & tomato", "dragonfruit",
    "dwellberries", "redberries", "jangerberries", "caerula berries",
    "tenti pineapple", "equa leaves", "cheese",
    # Drinks and other prepared food
    "cup of tea", "cup of tea (nettle)", "cup of tea (damiana)",
    "cup of tea (milky damiana)", "damiana tea", "damiana tea (milky)",
    "tea flask", "poison chalice", "stew", "spicy stew", "curry",
    "half full wine jug", "jug of wine", "pot of cream", "asgarnian ale",
    "greenman's ale", "dragon bitter", "dwarven stout", "grog", "beer",
    "wizard's mind bomb", "vodka", "whisky", "gin", "brandy",
    "chocolatey milk", "karamjan rum", "spinach roll", "easter egg",
    "pineapple punch", "wizard blizzard", "blurberry special",
    "choc saturday", "short green guy", "fruit blast", "drunk dragon",
})

# Ammunition for the ammo slot or inventory stacks; see
# https://oldschool.runescape.wiki/w/Ammunition. Weapons (Crystal bow,
# chinchompas, throwing knives) are excluded.
_ALWAYS_ATTAINABLE_AMMO_NAMES = frozenset({
    "bronze arrow", "iron arrow", "steel arrow", "mithril arrow",
    "adamant arrow", "rune arrow", "amethyst arrow", "dragon arrow",
    "seeking bronze arrow", "seeking iron arrow", "seeking steel arrow",
    "seeking mithril arrow", "seeking adamant arrow", "seeking rune arrow",
    "seeking amethyst arrow", "seeking dragon arrow", "training arrows",
    "ogre arrow", "ice arrows", "broad arrows", "brutal arrows",
    "fire arrows",
    "bronze bolts", "opal bolts (e)", "blurite bolts", "jade bolts (e)",
    "silver bolts", "iron bolts", "pearl bolts (e)", "steel bolts",
    "topaz bolts (e)", "mithril bolts", "sapphire bolts (e)",
    "emerald bolts (e)", "adamant bolts", "ruby bolts (e)",
    "diamond bolts (e)", "kebbit bolts", "long kebbit bolts", "broad bolts",
    "runite bolts", "dragonstone bolts (e)", "onyx bolts (e)",
    "amethyst broad bolts", "dragon bolts", "sunlight antler bolts",
    "moonlight antler bolts", "bolt rack",
    "bronze dart", "iron dart", "steel dart", "black dart", "mithril dart",
    "adamant dart", "rune dart", "amethyst dart", "dragon dart",
    "atlatl dart",
    "bronze javelin", "iron javelin", "steel javelin", "mithril javelin",
    "adamant javelin", "rune javelin", "amethyst javelin", "dragon javelin",
    "morrigan's javelin",
    "guam tar", "marrentill tar", "tarromin tar", "harralander tar",
    "irit tar",
    "steel cannonball", "granite cannonball",
})

# Potions match the "<base name>(<dose>)" pattern (dose 1-4) instead of a list
# of 210+ variants, as in app/possessions.py's _dose_family; charge-based
# accessories sharing it (Amulet of glory(1)) are excluded. Duplicated rather
# than imported because app/possessions.py already imports from this module
# (circular otherwise).
_POTION_DOSE_NAME_RE = re.compile(r"^(.*\S)\s*\((\d)\)$")
_POTION_DOSE_EXCLUDE_BASE_NAMES = frozenset({
    "amulet of glory", "amulet of chemistry", "ring of wealth",
    "ring of dueling", "ring of the elements", "combat bracelet",
    "skills necklace", "games necklace", "necklace of passage",
    "digsite pendant", "slayer ring", "burning amulet",
    "trailblazer amulet",
})


def _is_dose_style_potion_name(name: str) -> bool:
    """True for a dose-specific potion name like "Super restore(3)"; see
    _POTION_DOSE_NAME_RE and _POTION_DOSE_EXCLUDE_BASE_NAMES.
    """
    match = _POTION_DOSE_NAME_RE.match(name.strip())
    if not match:
        return False
    base, dose = match.group(1).strip(), int(match.group(2))
    if dose < 1 or dose > 4:
        return False
    return base.lower() not in _POTION_DOSE_EXCLUDE_BASE_NAMES


def _is_always_attainable_item(name: Optional[str]) -> bool:
    """True for any rune, food, potion or ammunition item (case-insensitive)."""
    if not name:
        return False
    lowered = name.strip().lower()
    return (
        lowered in _ALWAYS_ATTAINABLE_RUNE_NAMES
        or lowered in _ALWAYS_ATTAINABLE_FOOD_NAMES
        or lowered in _ALWAYS_ATTAINABLE_AMMO_NAMES
        or _is_dose_style_potion_name(name)
    )


# Ava's devices have a real, non-trivial GE price, so they are not forced owned,
# but they are unpriced and never a Still to Purchase / Next Purchase target.
# The slot is still colored by real ownership. Applied in
# _mark_slot_affordability; only tradeable/unitPrice/cost/fullCost are
# overridden, never owned.
_NO_PRICE_ITEM_NAMES = frozenset({
    "ava's attractor", "ava's accumulator", "ava's assembler",
})


def _is_no_price_item(name: Optional[str]) -> bool:
    """True for one of Ava's devices; see _NO_PRICE_ITEM_NAMES."""
    if not name:
        return False
    return name.strip().lower() in _NO_PRICE_ITEM_NAMES


def _mark_slot_affordability(resolved: Optional[dict], coins: int) -> Optional[dict]:
    if resolved is None:
        return None
    # Always-attainable items are owned with cost 0 (fullCost keeps the real
    # price). Runs before purchasable/affordable are computed.
    if _is_always_attainable_item(resolved.get("itemName")):
        resolved["owned"] = True
        resolved["cost"] = 0
    # Ava's devices (see _is_no_price_item): owned stays as resolved from the
    # real pool; only price and purchasability are zeroed.
    if _is_no_price_item(resolved.get("itemName")):
        resolved["tradeable"] = False
        resolved["unitPrice"] = None
        resolved["priceSource"] = None
        resolved["cost"] = 0
        resolved["fullCost"] = 0
    # A plain-untradeable item can carry a real unitPrice via
    # derived_price_by_name, making it a valid savings target.
    #
    # A combo is purchasable only when fullCost > 0 (some component has a real
    # price); otherwise a combo of untradeables (e.g. Keris partisan of the sun)
    # would sum to 0 gp and win Next Purchase.
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
    # Each row carries its slot identity (slotType/slot), the key for "custom"
    # sort drag-and-drop (see StillToPurchaseOrderEntryIn in app/schemas.py).
    pending = [(r, "equipment", slot) for slot, r in equipment.items() if r and not r["owned"]]
    pending += [(r, "inventory", idx) for idx, r in enumerate(inventory) if r and not r["owned"]]
    # Fully untradeable (no purchasable components): no price to pin, so it is
    # not a purchase target and is left out rather than shown as "n/a".
    pending = [entry for entry in pending if entry[0]["purchasable"]]

    if sort_mode == "high_to_low":
        pending.sort(key=lambda entry: entry[0]["cost"], reverse=True)
    elif sort_mode == "alphabetical":
        pending.sort(key=lambda entry: entry[0]["itemName"].casefold())
    elif sort_mode == "reverse_alphabetical":
        pending.sort(key=lambda entry: entry[0]["itemName"].casefold(), reverse=True)
    elif sort_mode == "custom":
        # Items missing from the saved order fall back to cost-ascending, so
        # "custom" starts sensibly and new items are not lost.
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

    # The next purchase is still_to_purchase[0] under the current sort mode, so
    # reordering the list moves the highlighted purchase with it.
    next_purchase = still_to_purchase[0] if still_to_purchase else None
    if next_purchase:
        cost = next_purchase["cost"]
        next_purchase = {
            **next_purchase,
            "progressPct": 100.0 if cost <= 0 else round(min(coins, cost) / cost * 100, 1),
            "funded": coins >= cost,
        }
    return still_to_purchase, next_purchase


def build_owned_pools(db: Session, game_account: GameAccount) -> Tuple[Dict[int, int], Dict[str, int]]:
    """Combines bank, inventory, equipment, potion storage, rune pouch, seed
    vault, tackle box, PoH Costume Room, Forestry Kit, Master Scroll Book and
    Seed Box into the "everything owned" pool (totalsById/totalsByName). Each
    gear setup checks a fresh copy (see build_gear_setups), as do item-goal
    Mindmap nodes (evaluate_completion in app/mindmaps.py).
    
    The plugin reports each extra storage in the same item-id/quantity shape
    (MyscapePlugin#read*Items in the Mootrius/myscape-plugin repo). They are
    separate containers that RuneLite's inventory scan does not see into, so
    each needs its own query or its items would read as missing.
    """
    pool_by_id: Dict[int, int] = {}
    pool_by_name: Dict[str, int] = {}

    def add(item_id: int, item_name: Optional[str], quantity: int):
        pool_by_id[item_id] = pool_by_id.get(item_id, 0) + quantity
        if item_name:
            key = _normalize_item_name(item_name)
            pool_by_name[key] = pool_by_name.get(key, 0) + quantity

    for item in db.query(BankItem).filter(BankItem.game_account_id == game_account.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(InventoryItem).filter(InventoryItem.game_account_id == game_account.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(EquipmentItem).filter(EquipmentItem.game_account_id == game_account.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(PotionStorageItem).filter(PotionStorageItem.game_account_id == game_account.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(RunePouchItem).filter(RunePouchItem.game_account_id == game_account.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(SeedVaultItem).filter(SeedVaultItem.game_account_id == game_account.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(TackleBoxItem).filter(TackleBoxItem.game_account_id == game_account.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(PohItem).filter(PohItem.game_account_id == game_account.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(ForestryKitItem).filter(ForestryKitItem.game_account_id == game_account.id).all():
        add(item.item_id, item.item_name, item.quantity)
    for item in db.query(MasterScrollBookItem).filter(MasterScrollBookItem.game_account_id == game_account.id).all():
        add(canonical_master_scroll_item_id(item.item_id, item.item_name), item.item_name, item.quantity)
    for item in db.query(SeedBoxItem).filter(SeedBoxItem.game_account_id == game_account.id).all():
        add(item.item_id, item.item_name, item.quantity)

    return pool_by_id, pool_by_name


def _player_coins(db: Session, game_account: GameAccount) -> int:
    """GP in possession, summed across every storage build_owned_pools sweeps,
    not just the bank.
    """
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
            .filter(model.game_account_id == game_account.id, model.item_id == COINS_ITEM_ID)
            .first()
        )
        if row:
            total += row.quantity
    return total


def _build_one_gear_setup(
    s: GearSetup,
    mapping: dict,
    prices: dict,
    coins: int,
    base_pool_by_id: Dict[int, int],
    base_pool_by_name: Dict[str, int],
) -> dict:
    """Resolves ONE GearSetup row into the dict shape GET /api/gear-setups
    returns; shared with build_purchase_goal_share_snapshot.
    base_pool_by_id/base_pool_by_name are copied, not mutated: setups are
    alternate goals, so each starts from the same untouched pool.
    """
    total_cost = 0
    total_full_cost = 0
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
    return {
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
    }


def build_gear_setups(db: Session, game_account: GameAccount, mapping: dict, prices: dict, coins: int) -> List[dict]:
    # Ordered by sort_order, then created_at (see GearSetup in app/models.py).
    # sort_order is NULL until a player drags a setup, so created_at alone
    # orders new setups last; NULLs are sorted last explicitly rather than
    # relying on the Postgres default.
    setups = (
        db.query(GearSetup)
        .filter(GearSetup.game_account_id == game_account.id)
        .order_by(GearSetup.sort_order.asc(), GearSetup.created_at.asc())
        .all()
    )
    base_pool_by_id, base_pool_by_name = build_owned_pools(db, game_account)
    return [_build_one_gear_setup(s, mapping, prices, coins, base_pool_by_id, base_pool_by_name) for s in setups]


def build_purchase_goals_state(db: Session, game_account: GameAccount) -> dict:
    """The Purchase Goals page's poll payload: coins, every priced/owned-checked
    gear setup, the owned pool, and current wiki fetch errors.
    """
    mapping, mapping_err = get_mapping()
    prices, prices_err = get_latest_prices()
    coins = _player_coins(db, game_account)
    _, pool_by_name = build_owned_pools(db, game_account)

    return {
        "coins": coins,
        "pricesError": prices_err,
        "mappingError": mapping_err,
        # Setups keep build_gear_setups' order (GearSetup.sort_order).
        # Re-sorting by cost here would snap a dragged setup back on every fetch
        # (set_gear_setup_order in app/main.py).
        "gearSetups": build_gear_setups(db, game_account, mapping, prices, coins),
        "ownedItems": pool_by_name,
    }


def build_purchase_goal_share_snapshot(setup: GearSetup) -> dict:
    """Freezes ONE gear setup (already resolved and ownership-checked by the
    caller, see _get_owned_gear_setup in app/main.py) into the payload POST
    /api/gear-setups/<id>/share stores in a SharedContent row for
    render_purchase_goals_share (app/pages/). Point-in-time, never live.
    
    Resolved against EMPTY owned pools so a visitor sees the setup at full
    price, not net of the sharer's bank: everything is owned: False with cost
    == fullCost, except always-attainable items
    (runes/food/potions/ammunition) force-owned by _mark_slot_affordability.
    Hence totalCost here is totalFullCost minus those items' fullCost, not its
    usual "net of owned" meaning. .purchase-goal-share (purchase-goals.css)
    greys all ownership borders so nothing about the sharer's account is
    implied.
    
    coins is frozen at 0 so the Next Purchase widget reads "0 / <cost> gp"
    without a share-specific render path.
    
    still_to_purchase/next_purchase are frozen in the setup's current sort
    mode as a starting array only. The share page opens on "low_to_high" and
    re-sorts client-side with a JS port of _still_to_purchase_summary's sort
    branches; still_to_purchase_custom_order is frozen as customOrder so
    CUSTOM shows the sharer's order.
    """
    mapping, _ = get_mapping()
    prices, _ = get_latest_prices()
    resolved = _build_one_gear_setup(setup, mapping, prices, 0, {}, {})

    return {
        "coins": 0,
        "gearSetup": resolved,
        "customOrder": setup.still_to_purchase_custom_order,
    }


def _raw_slot_item_from_resolved(resolved: Optional[dict]) -> Optional[dict]:
    """Reverses _resolve_gear_slot_item: turns a resolved slot dict (GET
    /api/gear-setups or a share payload) into the raw {"itemId", "itemName",
    "components"} shape GearSetup.equipment/inventory stores (see
    GearSlotItemIn in app/schemas.py). Used by
    import_gear_setup_from_share_payload. Icon, price and owned/cost are
    dropped since they are recomputed on read.
    """
    if resolved is None:
        return None
    components = resolved.get("components")
    if components:
        return {
            "itemId": None,
            "itemName": resolved.get("itemName"),
            "components": [
                {
                    "itemId": c.get("itemId"),
                    "itemName": c.get("itemName"),
                    "quantity": c.get("quantity") or 1,
                }
                for c in components
            ],
        }
    return {"itemId": resolved.get("itemId"), "itemName": resolved.get("itemName")}


def import_gear_setup_from_share_payload(db: Session, game_account: GameAccount, payload: dict) -> GearSetup:
    """Reverse of build_purchase_goal_share_snapshot: creates a new, editable
    GearSetup for game_account from a share's frozen payload (see POST
    /api/shares/{code}/import in app/main.py).
    
    Payload slots are resolved dicts, so each goes through
    _raw_slot_item_from_resolved. equipment is rebuilt sparse (only filled
    slots), while inventory stays a positional list of 28 filled-or-None
    entries. The name is the sharer's, verbatim. sort_order stays NULL so the
    setup lands at the end of the list. The caller commits.
    """
    gear_setup = payload["gearSetup"]

    equipment = {}
    for slot, resolved in (gear_setup.get("equipment") or {}).items():
        raw = _raw_slot_item_from_resolved(resolved)
        if raw is not None:
            equipment[slot] = raw

    inventory = [_raw_slot_item_from_resolved(entry) for entry in (gear_setup.get("inventory") or [])]

    raw_icon = None
    icon = gear_setup.get("icon")
    if icon:
        raw_icon = {"itemId": icon.get("itemId"), "itemName": icon.get("itemName")}

    setup = GearSetup(
        # Explicit id: the caller (POST /api/shares/{code}/import in
        # app/main.py) reads setup.id before commit, and the column default is
        # not applied until flush.
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        name=gear_setup.get("name") or "New Setup",
        icon=raw_icon,
        equipment=equipment,
        inventory=inventory,
    )
    db.add(setup)
    return setup

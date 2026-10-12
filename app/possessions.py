"""Backend logic for Storages Viewer: three views of the synced storage data.

1. MINIMUM trackers (PossessionTracker kind="min"): progress bar toward a
target.
2. MAXIMUM trackers (kind="max"): red/green box once the owned count exceeds
N.
3. Full raw view: every owned item with a per-location breakdown, so the
page's location toggles recompute totals client-side.

Does not reuse build_owned_pools (app/purchase_goals.py), which merges all
storages and loses the per-storage breakdown. Quantities are always read live
from the synced tables; a tracker stores only what to watch and its threshold.
"""
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.item_ids import canonical_master_scroll_item_id, find_item_by_exact_name, find_item_ids
from app.models import (
    BankItem,
    BoatCargoItem,
    EquipmentItem,
    ForestryKitItem,
    HiddenPossessionStorage,
    HuntsmansKitItem,
    InventoryItem,
    LootingBagItem,
    MasterScrollBookItem,
    PinnedPossessionItem,
    GameAccount,
    PohItem,
    PossessionTracker,
    PossessionView,
    PotionStorageItem,
    RunePouchItem,
    SeedBoxItem,
    SeedVaultItem,
    TackleBoxItem,
)
from app.purchase_goals import COINS_ITEM_ID, derived_price_for, get_latest_prices, get_mapping, item_icon_url, search_items, unit_price_for
from app.schemas import POSSESSION_STORAGE_KEYS

# Storage key (matches schemas.POSSESSION_STORAGE_KEYS and
# GameAccount.storage_synced_at) -> model table, in the fixed order used by
# location-breakdown dicts and the plugin's Status section.
STORAGE_SOURCES = [
    ("bank", BankItem),
    ("equipment", EquipmentItem),
    ("inventory", InventoryItem),
    ("potion_storage", PotionStorageItem),
    ("rune_pouch", RunePouchItem),
    ("seed_vault", SeedVaultItem),
    ("looting_bag", LootingBagItem),
    ("tackle_box", TackleBoxItem),
    ("poh", PohItem),
    ("forestry_kit", ForestryKitItem),
    ("master_scroll_book", MasterScrollBookItem),
    ("seed_box", SeedBoxItem),
    ("huntsmans_kit", HuntsmansKitItem),
    # BoatCargoItem has an extra `slot` column (app/models.py); only the shared
    # columns are read here.
    ("boat_cargo", BoatCargoItem),
]


def get_owned_breakdown(db: Session, game_account: GameAccount) -> Dict[int, dict]:
    """Returns {item_id: {"itemName": str|None, "total": int, "byLocation":
    {storage_key: int}}} across all fourteen storages. itemName is the first
    non-empty name reported (display fallback for untradeables; see BankItem
    in app/models.py).
    """
    breakdown: Dict[int, dict] = {}
    for key, model in STORAGE_SOURCES:
        rows = db.query(model).filter(model.game_account_id == game_account.id).all()
        for row in rows:
            row_item_id = row.item_id
            if key == "master_scroll_book":
                # Older rows may still hold the Book's untradeable "default
                # teleport" cosmetic id; see canonical_master_scroll_item_id.
                row_item_id = canonical_master_scroll_item_id(row_item_id, row.item_name)
            entry = breakdown.setdefault(row_item_id, {"itemName": None, "total": 0, "byLocation": {}})
            entry["total"] += row.quantity
            entry["byLocation"][key] = entry["byLocation"].get(key, 0) + row.quantity
            if row.item_name and not entry["itemName"]:
                entry["itemName"] = row.item_name
    return breakdown


# Icons come from the CDN-direct per-id export (item_icon_url in
# app/purchase_goals.py), which has the right art for every distinct id, so no
# id->icon overrides are needed.


def resolve_item_display(item_id: int, fallback_name: Optional[str], mapping: dict) -> dict:
    """Returns {"name", "icon", "tradeable", "highAlch"} for one item id: live GE
    mapping first, then the item_ids.json snapshot by name (untradeables are
    absent from the GE mapping), then the name already stored. The icon
    depends only on item_id.
    """
    meta = mapping.get(str(item_id))
    if meta:
        name = meta.get("name") or fallback_name or f"Item #{item_id}"
        tradeable = True
        high_alch = meta.get("highalch")
    else:
        name = fallback_name
        tradeable = False
        high_alch = None
        if fallback_name:
            snap = find_item_by_exact_name(fallback_name)
            if snap:
                name = snap.get("name") or fallback_name
        name = name or f"Item #{item_id}"

    return {
        "name": name,
        "icon": item_icon_url(item_id),
        "tradeable": tradeable,
        "highAlch": high_alch,
    }


# Potions are named "Base name(N)" (N = doses, 1-4), with a separate item id per
# dose count. _dose_family detects this from the name alone so
# build_possessions_summary can fold variants into one row in 1-dose units.
_DOSE_NAME_RE = re.compile(r"^(.*\S)\s*\((\d)\)$")

# Non-potion items using "Name(N)" for charges on one physical item (e.g. Amulet
# of glory), not a fungible quantity. Keyed by lowercase base name so
# _dose_family skips them.
_DOSE_MERGE_EXCLUDE_BASE_NAMES = {
    "amulet of glory",
    "amulet of chemistry",
    "ring of wealth",
    "ring of dueling",
    "ring of the elements",
    "combat bracelet",
    "skills necklace",
    "games necklace",
    "necklace of passage",
    "digsite pendant",
    "slayer ring",
    "burning amulet",
    "trailblazer amulet",
}


def _dose_family(name: str) -> Optional[Tuple[str, int]]:
    """Returns (base_name, dose_count) for a dose-specific potion name like
    "Super restore(3)", else None (no trailing "(N)", N outside 1-4, or an
    excluded charge item).
    """
    match = _DOSE_NAME_RE.match(name.strip())
    if not match:
        return None
    base = match.group(1).strip()
    dose = int(match.group(2))
    if dose < 1 or dose > 4:
        return None
    if base.lower() in _DOSE_MERGE_EXCLUDE_BASE_NAMES:
        return None
    return base, dose


def _resolve_dose1_display(base: str, mapping: dict) -> Tuple[str, Optional[str], bool, Optional[int]]:
    """Returns (name, icon, tradeable, itemId) for `base`'s 1-dose variant,
    resolved by name (find_item_ids, resolve_item_display). `name` is always
    "{base}(1)" even on a miss; icon/itemId are None on a miss and the caller
    falls back to an owned variant's.
    """
    name = f"{base}(1)"
    ids = find_item_ids(name)
    if not ids:
        return name, None, False, None
    display = resolve_item_display(ids[0], name, mapping)
    return display["name"], display["icon"], display["tradeable"], ids[0]


def _merge_dose_families(items: List[dict], mapping: dict) -> List[dict]:
    """Folds all dose variants of a potion (see _dose_family) into one row in
    1-dose units: "Prayer potion(4)" x5 and "(1)" x2 become "Prayer potion(1)"
    x22. The value per dose is the summed variant stack values over total
    doses. Name and icon come from the real 1-dose item (see
    _resolve_dose1_display) even if none is owned. Non-dose items pass
    through.
    """
    plain: List[dict] = []
    families: Dict[str, dict] = {}

    for it in items:
        fam = _dose_family(it["name"])
        if fam is None:
            plain.append(it)
            continue
        base, dose = fam
        family = families.setdefault(base, {
            "name": base,
            "icon": it["icon"],
            "tradeable": it["tradeable"],
            "itemId": it["itemId"],
            "bestDose": 0,
            "totalDoses": 0,
            "geValueTotal": 0.0,
            "geKnown": False,
            "haValueTotal": 0.0,
            "haKnown": False,
            "byLocation": {},
        })
        family["totalDoses"] += it["total"] * dose
        if it["gePrice"] is not None:
            family["geValueTotal"] += it["gePrice"] * it["total"]
            family["geKnown"] = True
        if it["highAlch"] is not None:
            family["haValueTotal"] += it["highAlch"] * it["total"]
            family["haKnown"] = True
        # Fallback when no "(1)" item id is found (rare): the owned variant with
        # the most doses.
        if dose >= family["bestDose"]:
            family["bestDose"] = dose
            family["icon"] = it["icon"]
            family["itemId"] = it["itemId"]
            family["tradeable"] = it["tradeable"]
        for loc, qty in it["byLocation"].items():
            family["byLocation"][loc] = family["byLocation"].get(loc, 0) + qty * dose

    merged = list(plain)
    for family in families.values():
        total_doses = family["totalDoses"]
        if total_doses <= 0:
            continue
        dose1_name, dose1_icon, dose1_tradeable, dose1_item_id = _resolve_dose1_display(family["name"], mapping)
        merged.append({
            "itemId": dose1_item_id if dose1_item_id is not None else family["itemId"],
            "name": dose1_name,
            "icon": dose1_icon if dose1_icon is not None else family["icon"],
            "tradeable": dose1_tradeable if dose1_item_id is not None else family["tradeable"],
            "highAlch": (family["haValueTotal"] / total_doses) if family["haKnown"] else None,
            "gePrice": (family["geValueTotal"] / total_doses) if family["geKnown"] else None,
            # Dose potions are always GE-tradeable, so the merged value is a
            # real GE price; geDerived is not carried over per variant.
            "geDerived": False,
            "total": total_doses,
            "byLocation": family["byLocation"],
        })
    return merged


def search_trackable_items(query: str, limit: int = 20) -> List[dict]:
    """Item search for setting up a tracker. Uses search_items' three-tier
    ranking (app/purchase_goals.py) but drops results with no real item id,
    which a tracker needs, including recipe results (app/recipes.py). Rarely
    trims anything.
    """
    raw = search_items(query, limit=limit * 2)  # overfetch -- some may get dropped below
    results = []
    seen_ids = set()
    for r in raw:
        item_id = r.get("id")
        if item_id is None:
            ids = find_item_ids(r["name"]) if r.get("name") else None
            item_id = ids[0] if ids else None
        if item_id is None or item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        results.append({
            "id": item_id,
            "name": r["name"],
            "icon": r.get("icon"),
            "tradeable": bool(r.get("tradeable")),
        })
        if len(results) >= limit:
            break
    return results


def _tracker_out(tracker: PossessionTracker, mapping: dict, breakdown: Dict[int, dict]) -> dict:
    display = resolve_item_display(tracker.item_id, tracker.item_name, mapping)
    owned = breakdown.get(tracker.item_id, {}).get("total", 0)
    return {
        "id": str(tracker.id),
        "kind": tracker.kind,
        "itemId": tracker.item_id,
        "itemName": display["name"],
        "icon": display["icon"],
        "tradeable": display["tradeable"],
        "targetQuantity": tracker.target_quantity,
        "ownedQuantity": owned,
    }


def build_trackers_state(db: Session, game_account: GameAccount) -> dict:
    """Combined payload polled by the min/max sections: both tracker kinds
    resolved against a live owned-quantity breakdown and GE mapping, ordered
    by sort_order (lowest first, as in Mindmaps).
    """
    mapping, mapping_error = get_mapping()
    breakdown = get_owned_breakdown(db, game_account)
    trackers = (
        db.query(PossessionTracker)
        .filter(PossessionTracker.game_account_id == game_account.id)
        .order_by(PossessionTracker.sort_order)
        .all()
    )
    min_trackers = [_tracker_out(t, mapping, breakdown) for t in trackers if t.kind == "min"]
    max_trackers = [_tracker_out(t, mapping, breakdown) for t in trackers if t.kind == "max"]
    return {"minTrackers": min_trackers, "maxTrackers": max_trackers, "mappingError": mapping_error}


def pinned_item_ids(db: Session, game_account: GameAccount) -> set:
    """Item ids this player has pinned (see PinnedPossessionItem in
    app/models.py), as a set since callers only need membership or a flat
    list.
    """
    rows = (
        db.query(PinnedPossessionItem.item_id)
        .filter(PinnedPossessionItem.game_account_id == game_account.id)
        .all()
    )
    return {row[0] for row in rows}


def hidden_storage_keys(db: Session, game_account: GameAccount) -> set:
    """Storage source keys this player has hidden in Storages Viewer's settings
    menu (see HiddenPossessionStorage in app/models.py), as a set for the same
    reason as pinned_item_ids.
    """
    rows = (
        db.query(HiddenPossessionStorage.storage_key)
        .filter(HiddenPossessionStorage.game_account_id == game_account.id)
        .all()
    )
    return {row[0] for row in rows}


def set_storage_hidden(db: Session, game_account: GameAccount, storage_key: str, hidden: bool) -> None:
    """Shows or hides one storage source for this player (gear-icon settings
    menu; see render_possessions in app/pages.py). Idempotent, like
    pin/unpin_possession_item in app/main.py, so a repeated or out-of-order
    request never raises.
    """
    existing = (
        db.query(HiddenPossessionStorage)
        .filter(HiddenPossessionStorage.game_account_id == game_account.id, HiddenPossessionStorage.storage_key == storage_key)
        .first()
    )
    if hidden and not existing:
        db.add(HiddenPossessionStorage(game_account_id=game_account.id, storage_key=storage_key))
        db.commit()
    elif not hidden and existing:
        db.delete(existing)
        db.commit()


def build_possessions_summary(db: Session, game_account: GameAccount) -> dict:
    """Section 3's payload: every owned item with its live GE/high-alch value and
    a per-location quantity breakdown, so toggles recompute client-side (see
    render_possessions in app/pages.py). Dose variants are folded into one row
    (see _merge_dose_families).
    
    Untradeables with a RuneLite-linked value (derived_price_for in
    app/purchase_goals.py) get that value with TRADEABLE still NO; geDerived
    marks it as an estimate (shown with a leading "~"). Coins and Platinum
    tokens use a fixed rate (currency_gp_rate) and are not geDerived since
    their value is exact.
    """
    mapping, mapping_error = get_mapping()
    prices, price_error = get_latest_prices()
    breakdown = get_owned_breakdown(db, game_account)

    # Coins and Platinum tokens are currency with no GE listing but an exact gp
    # value (1 coin = 1gp, 1 platinum token = 1,000gp). geDerived stays False
    # since the value is exact, not an estimate.
    currency_gp_rate = {COINS_ITEM_ID: 1}
    for platinum_id in find_item_ids("Platinum token") or []:
        currency_gp_rate[platinum_id] = 1000

    items = []
    for item_id, entry in breakdown.items():
        if entry["total"] <= 0:
            continue
        display = resolve_item_display(item_id, entry["itemName"], mapping)
        if item_id in currency_gp_rate:
            ge_price = currency_gp_rate[item_id]
            ge_derived = False
        elif display["tradeable"]:
            ge_price, _ = unit_price_for(item_id, prices)
            ge_derived = False
        else:
            # Untradeables may have a GE-derived value (derived_price_for /
            # get_untradeable_mapping in app/purchase_goals.py); geDerived lets
            # the frontend mark it as an estimate (see valueCell in
            # render_possessions).
            ge_price, _ = derived_price_for(item_id, prices)
            ge_derived = ge_price is not None
        items.append({
            "itemId": item_id,
            "name": display["name"],
            "icon": display["icon"],
            "tradeable": display["tradeable"],
            "highAlch": display["highAlch"],
            "gePrice": ge_price,
            "geDerived": ge_derived,
            "total": entry["total"],
            "byLocation": entry["byLocation"],
        })

    items = _merge_dose_families(items, mapping)

    # Marked after merging: a pin is made against the merged row's itemId (see
    # _merge_dose_families), not a pre-merge dose variant's id.
    pinned_ids = pinned_item_ids(db, game_account)
    for item in items:
        item["pinned"] = item["itemId"] in pinned_ids

    return {
        "items": items,
        "mappingError": mapping_error,
        "priceError": price_error,
        "hiddenStorageKeys": sorted(hidden_storage_keys(db, game_account)),
    }


def build_possessions_share_snapshot(db: Session, game_account: GameAccount, active_locations: List[str]) -> dict:
    """Freezes Storages Viewer's section 3 into a myscape.io/s/<code> snapshot
    (see POST /api/possessions/share in app/main.py, render_storages_share in
    app/pages.py). Most fields come verbatim from build_possessions_summary.
    activeLocations is the one transient piece (the client-side location
    filter), so it is passed through from
    PossessionShareCreateRequest.locations, filtered against
    POSSESSION_STORAGE_KEYS.
    """
    summary = build_possessions_summary(db, game_account)
    summary["activeLocations"] = [key for key in active_locations if key in POSSESSION_STORAGE_KEYS]
    return summary


def next_sort_order(db: Session, game_account: GameAccount, kind: str) -> float:
    """One past the highest sort_order among this player's trackers of this kind,
    so a new tracker lands at the end of its section (same approach as
    add_node in app/mindmaps.py).
    """
    highest = (
        db.query(PossessionTracker)
        .filter(PossessionTracker.game_account_id == game_account.id, PossessionTracker.kind == kind)
        .order_by(PossessionTracker.sort_order.desc())
        .first()
    )
    return (highest.sort_order + 1.0) if highest else 0.0


def _view_out(view: PossessionView) -> dict:
    return {"id": str(view.id), "name": view.name, "config": view.config or {}}


def build_possession_views(db: Session, game_account: GameAccount) -> List[dict]:
    """This player's saved Storages Viewer views in reorder-strip order, nulls
    last (as GearSetup.sort_order) so a view with no sort_order doesn't sort
    unpredictably under Postgres NULL ordering.
    """
    views = (
        db.query(PossessionView)
        .filter(PossessionView.game_account_id == game_account.id)
        .order_by(PossessionView.sort_order.is_(None), PossessionView.sort_order, PossessionView.created_at)
        .all()
    )
    return [_view_out(v) for v in views]


def next_possession_view_sort_order(db: Session, game_account: GameAccount) -> float:
    """Append-past-the-max sort_order, as next_sort_order, over saved views."""
    highest = (
        db.query(PossessionView)
        .filter(PossessionView.game_account_id == game_account.id)
        .order_by(PossessionView.sort_order.desc())
        .first()
    )
    if highest and highest.sort_order is not None:
        return highest.sort_order + 1.0
    return 0.0

"""Backend logic for Possessions Monitoring -- three ways of looking at
the same synced storage data Purchase Goals already reads (see
build_owned_pools in app/purchase_goals.py, which this deliberately
does NOT reuse -- that function collapses everything into one combined
pool with no memory of which storage an item came from, but section 3's
per-location toggles need exactly that memory kept around):

1. MINIMUM trackers (section 1) -- "keep at least N of this" -- a
   PossessionTracker row with kind="min", read against how many of its
   item the player currently owns (summed across every storage) and
   shown as a fill-toward-target progress bar.
2. MAXIMUM trackers (section 2) -- "flag me once I have more than N of
   this" -- same PossessionTracker shape, kind="max", shown as a
   red/green box instead of a bar.
3. The full raw view (section 3) -- every item currently owned in ANY
   storage, with a per-location quantity breakdown so the page's own
   location toggles can recompute each item's shown total client-side
   without another round trip (see build_possessions_summary below).

Every quantity here is always read live off the last-synced snapshot
tables (BankItem and friends) -- same "no cached amount to go stale"
approach as build_owned_pools -- a PossessionTracker row only ever
remembers WHAT to watch and WHAT threshold matters, never a count of
its own.
"""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.item_ids import find_item_by_exact_name, find_item_ids
from app.models import (
    BankItem,
    EquipmentItem,
    InventoryItem,
    LootingBagItem,
    Player,
    PossessionTracker,
    PotionStorageItem,
    RunePouchItem,
    SeedVaultItem,
)
from app.purchase_goals import get_latest_prices, get_mapping, item_icon_url, search_items, unit_price_for

# Storage key (matches schemas.POSSESSION_STORAGE_KEYS and
# Player.storage_synced_at's own keys) -> the model table it's read
# from, in the fixed order every location-breakdown dict and the
# plugin panel's own Status section list them in.
STORAGE_SOURCES = [
    ("bank", BankItem),
    ("equipment", EquipmentItem),
    ("inventory", InventoryItem),
    ("potion_storage", PotionStorageItem),
    ("rune_pouch", RunePouchItem),
    ("seed_vault", SeedVaultItem),
    ("looting_bag", LootingBagItem),
]


def get_owned_breakdown(db: Session, player: Player) -> Dict[int, dict]:
    """Returns {item_id: {"itemName": str|None, "total": int,
    "byLocation": {storage_key: int}}} across every one of the seven
    synced storages -- the single query this whole module (both the
    tracker sections and the full raw view) computes owned quantities
    from. itemName is whichever storage first reported a non-empty one
    for that id (see BankItem's docstring in app/models.py for why
    that field exists at all -- purely an untradeable-item display
    fallback, same role it plays here)."""
    breakdown: Dict[int, dict] = {}
    for key, model in STORAGE_SOURCES:
        rows = db.query(model).filter(model.player_id == player.id).all()
        for row in rows:
            entry = breakdown.setdefault(row.item_id, {"itemName": None, "total": 0, "byLocation": {}})
            entry["total"] += row.quantity
            entry["byLocation"][key] = entry["byLocation"].get(key, 0) + row.quantity
            if row.item_name and not entry["itemName"]:
                entry["itemName"] = row.item_name
    return breakdown


# A handful of items don't just show a bigger pile of the same picture
# as more of them are held (RuneScape's "xN" quantity overlay already
# handles that for every ordinary item) -- Coins and Abyssal Pearls are
# actual in-game currency stacks whose own artwork changes at set
# thresholds (see the OSRS Wiki's "Coins" article for the full
# 1/2/3/4/5/25/100/250/1000/10000 sequence; Abyssal Pearls tops out at
# 5). Both the live GE mapping and the item_ids.json snapshot only ever
# carry the base ("1") appearance for these -- neither holds a stack
# size to pick a bigger image from -- so this table overrides the wiki
# icon FILENAME outright to whichever file is that item's biggest
# denomination, regardless of how many the player actually owns (a
# handful of coins showing the 10,000gp pile image is a cosmetic choice
# for a nicer-looking row, not a claim about the real stack size --
# QUANTITY is what actually tells the player how many they have). Add
# another entry here if another such item turns up.
_STACK_ICON_OVERRIDES = {
    995: "Coins 10000.png",
    26792: "Abyssal pearls 5.png",
}


def resolve_item_display(item_id: int, fallback_name: Optional[str], mapping: dict) -> dict:
    """Returns {"name", "icon", "tradeable", "highAlch"} for one real
    item id -- tries the live GE mapping first (real icon, high alch,
    and the definitive tradeable=True), then falls back to the
    item_ids.json snapshot by name (for an untradeable item, whose id
    never appears in the GE mapping at all), then to the bare id/name a
    storage table itself already had on file. The icon filename is
    resolved from whichever of those tiers applies, then run through
    _STACK_ICON_OVERRIDES before being turned into a URL -- see that
    table's own comment."""
    meta = mapping.get(str(item_id))
    if meta:
        icon_filename = meta.get("icon")
        name = meta.get("name") or fallback_name or f"Item #{item_id}"
        tradeable = True
        high_alch = meta.get("highalch")
    else:
        icon_filename = None
        name = fallback_name
        tradeable = False
        high_alch = None
        if fallback_name:
            snap = find_item_by_exact_name(fallback_name)
            if snap:
                icon_filename = snap.get("icon")
                name = snap.get("name") or fallback_name
        name = name or f"Item #{item_id}"

    icon_filename = _STACK_ICON_OVERRIDES.get(item_id, icon_filename)
    return {
        "name": name,
        "icon": item_icon_url(icon_filename),
        "tradeable": tradeable,
        "highAlch": high_alch,
    }


def search_trackable_items(query: str, limit: int = 20) -> List[dict]:
    """Item search for setting up a min/max tracker (sections 1/2) --
    reuses search_items' own three-tier startswith-then-contains
    ranking (live GE mapping, then known combination recipes, then the
    item_ids.json snapshot -- see that function's own comment in
    app/purchase_goals.py for why a plain scan alone isn't enough to
    guarantee a short, precise name surfaces first) but, unlike that
    function, never returns a result with no real item id -- a
    tracker has nothing to watch without one, whereas Purchase Goals'
    own search is fine matching an untradeable item by name alone.

    A recipe result (a combined item like "Neitiznot faceguard", which
    itself has no real item id at all -- see app/recipes.py) is
    dropped rather than attached to a wrong id, same as an
    item_ids.json result whose name genuinely isn't in that snapshot
    either. In practice this rarely trims anything: almost every real,
    obtainable item -- tradeable or not -- has an entry in the
    item_ids.json snapshot with a real id attached."""
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


def build_trackers_state(db: Session, player: Player) -> dict:
    """The combined payload the page's min/max sections poll -- both
    kinds of tracker, each already resolved against a live owned-
    quantity breakdown and a live GE mapping (icon/name/tradeable),
    sorted the same way Mindmaps orders sibling nodes (sort_order,
    lowest first -- see PossessionTracker's own docstring)."""
    mapping, mapping_error = get_mapping()
    breakdown = get_owned_breakdown(db, player)
    trackers = (
        db.query(PossessionTracker)
        .filter(PossessionTracker.player_id == player.id)
        .order_by(PossessionTracker.sort_order)
        .all()
    )
    min_trackers = [_tracker_out(t, mapping, breakdown) for t in trackers if t.kind == "min"]
    max_trackers = [_tracker_out(t, mapping, breakdown) for t in trackers if t.kind == "max"]
    return {"minTrackers": min_trackers, "maxTrackers": max_trackers, "mappingError": mapping_error}


def build_possessions_summary(db: Session, player: Player) -> dict:
    """Section 3's payload -- every item currently owned in any
    storage, each with its live GE/high-alch value and a per-location
    quantity breakdown, so the page's own location toggles (and the
    high-alch/GE-value/tradeable display toggles) can recompute what
    each box shows entirely client-side rather than re-polling this
    endpoint for every toggle flip (see renderItemList's own approach
    in the Loot Tracker page, which this section's box/sort/search UI
    otherwise mirrors closely -- see render_possessions in
    app/pages.py)."""
    mapping, mapping_error = get_mapping()
    prices, price_error = get_latest_prices()
    breakdown = get_owned_breakdown(db, player)

    items = []
    for item_id, entry in breakdown.items():
        if entry["total"] <= 0:
            continue
        display = resolve_item_display(item_id, entry["itemName"], mapping)
        ge_price, _ = unit_price_for(item_id, prices) if display["tradeable"] else (None, None)
        items.append({
            "itemId": item_id,
            "name": display["name"],
            "icon": display["icon"],
            "tradeable": display["tradeable"],
            "highAlch": display["highAlch"],
            "gePrice": ge_price,
            "total": entry["total"],
            "byLocation": entry["byLocation"],
        })

    return {"items": items, "mappingError": mapping_error, "priceError": price_error}


def next_sort_order(db: Session, player: Player, kind: str) -> float:
    """One past the highest existing sort_order for this player's
    trackers of this kind -- a new tracker always lands at the end of
    its own section, same "append past the current max" approach
    Mindmaps uses for a new sibling node (see add_node in
    app/mindmaps.py)."""
    highest = (
        db.query(PossessionTracker)
        .filter(PossessionTracker.player_id == player.id, PossessionTracker.kind == kind)
        .order_by(PossessionTracker.sort_order.desc())
        .first()
    )
    return (highest.sort_order + 1.0) if highest else 0.0

"""Backend logic for Storages Viewer -- three ways of looking at
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
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.item_ids import find_item_by_exact_name, find_item_ids
from app.models import (
    BankItem,
    EquipmentItem,
    ForestryKitItem,
    HiddenPossessionStorage,
    InventoryItem,
    LootingBagItem,
    MasterScrollBookItem,
    PinnedPossessionItem,
    Player,
    PohItem,
    PossessionTracker,
    PotionStorageItem,
    RunePouchItem,
    SeedBoxItem,
    SeedVaultItem,
    TackleBoxItem,
)
from app.purchase_goals import COINS_ITEM_ID, derived_price_for, get_latest_prices, get_mapping, item_icon_url, search_items, unit_price_for

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
    ("tackle_box", TackleBoxItem),
    ("poh", PohItem),
    ("forestry_kit", ForestryKitItem),
    ("master_scroll_book", MasterScrollBookItem),
    ("seed_box", SeedBoxItem),
]


def get_owned_breakdown(db: Session, player: Player) -> Dict[int, dict]:
    """Returns {item_id: {"itemName": str|None, "total": int,
    "byLocation": {storage_key: int}}} across every one of the twelve
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


# Coins and Abyssal Pearls are actual in-game currency stacks whose own
# artwork changes at set thresholds (see the OSRS Wiki's "Coins"
# article for the full 1/2/3/4/5/25/100/250/1000/10000 sequence;
# Abyssal Pearls tops out at 5) -- but neither is a GE-tradeable item
# (no listing, so never in the live mapping), and the wiki's own
# File:Coins.png / File:Abyssal pearls.png redirects (see the general
# fallback in resolve_item_display below) don't reliably land on the
# BIGGEST denomination either -- Coins.png redirects to the 100gp pile,
# not 10,000gp. So these two stay pinned here to the exact file we
# actually want, regardless of how many the player owns (a handful of
# coins showing the 10,000gp pile image is a cosmetic choice for a
# nicer-looking row, not a claim about the real stack size -- QUANTITY
# is what actually tells the player how many they have). Add another
# entry here only if some other item's own bare-name redirect turns out
# not to land on the size we want either.
_STACK_ICON_OVERRIDES = {
    995: "Coins 10000.png",
    26792: "Abyssal pearls 5.png",
}

# Crystal helm/body/legs can be recolored to match any of seven Iorwerth
# Clan houses (Amlodd/Cadarn/Crwys/Hefin/Iorwerth/Ithell/Trahaearn --
# there's no Meilyr recolor for the armour, unlike the crystal bow/
# blade's own ornament kits, confirmed against the wiki's own Bucket
# data below turning up zero Meilyr rows for these three items), on top
# of the original un-recolored look -- eight total looks per piece, all
# purely cosmetic. The game's own client calls every single one of them
# by the exact same name ("Crystal helm", or "Crystal helm (inactive)"
# once its charges run out -- recoloring never changes the name shown
# in a tooltip), so the RuneLite plugin's own item_name for one is
# never enough to tell them apart -- only the real item id is different
# per colour. item_ids.json (built from the wiki's Bucket:Infobox_item
# table by name -- see scripts/fetch_item_ids.py) merges every colour's
# ids into that one "Crystal helm" entry for exactly that reason, and
# keeps only ONE icon for the whole group -- so resolve_item_display's
# usual name-based icon guess always lands on the same (effectively
# arbitrary) colour's picture regardless of which one a player actually
# owns.
#
# This table is what actually fixes that: every real crystal armour
# item id mapped straight to ITS OWN colour's icon filename, queried
# live off the wiki's Bucket:Infobox_item table one level below where
# fetch_item_ids.py stops (per id, not merged by name) rather than
# guessed -- so a player's own Ithell helm shows the Ithell icon, not
# whichever colour happened to be first/marked default. Doesn't cover
# the Deadman Mode/Last Man Standing-only variants (own separate ids,
# but not obtainable in a normal game and so never actually reported by
# the plugin) -- add them here too if that ever changes.
_CRYSTAL_ARMOUR_ICON_OVERRIDES = {
    # Crystal helm -- active
    23971: "Crystal helm.png",  # original, un-recolored
    27705: "Crystal helm (Hefin).png",
    27717: "Crystal helm (Ithell).png",
    27729: "Crystal helm (Iorwerth).png",
    27741: "Crystal helm (Trahaearn).png",
    27753: "Crystal helm (Cadarn).png",
    27765: "Crystal helm (Crwys).png",
    27777: "Crystal helm (Amlodd).png",
    # Crystal helm -- inactive (0 charges left)
    23973: "Crystal helm (inactive).png",
    27707: "Crystal helm (inactive) (Hefin).png",
    27719: "Crystal helm (inactive) (Ithell).png",
    27731: "Crystal helm (inactive) (Iorwerth).png",
    27743: "Crystal helm (inactive) (Trahaearn).png",
    27755: "Crystal helm (inactive) (Cadarn).png",
    27767: "Crystal helm (inactive) (Crwys).png",
    27779: "Crystal helm (inactive) (Amlodd).png",
    # Crystal body -- active
    23975: "Crystal body.png",
    27697: "Crystal body (Hefin).png",
    27709: "Crystal body (Ithell).png",
    27721: "Crystal body (Iorwerth).png",
    27733: "Crystal body (Trahaearn).png",
    27745: "Crystal body (Cadarn).png",
    27757: "Crystal body (Crwys).png",
    27769: "Crystal body (Amlodd).png",
    # Crystal body -- inactive
    23977: "Crystal body (inactive).png",
    27699: "Crystal body (inactive) (Hefin).png",
    27711: "Crystal body (inactive) (Ithell).png",
    27723: "Crystal body (inactive) (Iorwerth).png",
    27735: "Crystal body (inactive) (Trahaearn).png",
    27747: "Crystal body (inactive) (Cadarn).png",
    27759: "Crystal body (inactive) (Crwys).png",
    27771: "Crystal body (inactive) (Amlodd).png",
    # Crystal legs -- active
    23979: "Crystal legs.png",
    27701: "Crystal legs (Hefin).png",
    27713: "Crystal legs (Ithell).png",
    27725: "Crystal legs (Iorwerth).png",
    27737: "Crystal legs (Trahaearn).png",
    27749: "Crystal legs (Cadarn).png",
    27761: "Crystal legs (Crwys).png",
    27773: "Crystal legs (Amlodd).png",
    # Crystal legs -- inactive
    23981: "Crystal legs (inactive).png",
    27703: "Crystal legs (inactive) (Hefin).png",
    27715: "Crystal legs (inactive) (Ithell).png",
    27727: "Crystal legs (inactive) (Iorwerth).png",
    27739: "Crystal legs (inactive) (Trahaearn).png",
    27751: "Crystal legs (inactive) (Cadarn).png",
    27763: "Crystal legs (inactive) (Crwys).png",
    27775: "Crystal legs (inactive) (Amlodd).png",
}


def resolve_item_display(item_id: int, fallback_name: Optional[str], mapping: dict) -> dict:
    """Returns {"name", "icon", "tradeable", "highAlch"} for one real
    item id -- tries the live GE mapping first (real icon, high alch,
    and the definitive tradeable=True), then falls back to the
    item_ids.json snapshot by name (for an untradeable item, whose id
    never appears in the GE mapping at all) for a corrected/canonical
    name, then to the bare id/name a storage table itself already had
    on file.

    The ICON filename for that untradeable branch deliberately does NOT
    use item_ids.json's own stored "icon" field, even though that
    lookup is sitting right there -- that field was captured from
    whichever image the wiki's Infobox_item data marks as an item's
    "default_version", which for every stackable/denominated item (the
    exact items this bit us on -- Tokkul, Stardust, Platinum tokens,
    and friends, none of which have a GE listing) is consistently the
    SMALLEST ("1") variant, not the biggest. Same root cause the
    _STACK_ICON_OVERRIDES table above exists for on Coins/Abyssal
    Pearls, just silently wrong for every OTHER such item instead of
    loudly wrong for two well-known ones.

    Loot Tracker's own item icon resolution (see _resolve_loot_items in
    app/loot.py) sidesteps this entirely by falling back to the bare
    item NAME as the filename instead of a snapshot lookup, and that
    turns out to already do exactly the right thing here: the OSRS
    Wiki maintains File:<Name>.png (no denomination suffix) as a
    REDIRECT to whichever version IT treats as that item's default/
    biggest-looking icon -- confirmed directly against the wiki's own
    API, e.g. File:Dragonfruit tree seed.png -> File:Dragonfruit tree
    seed 5.png, File:Abyssal pearls.png -> File:Abyssal pearls 5.png
    (matching the hardcoded override above on its own). So the bare
    name is used here too, the same fallback Loot Tracker already
    relies on, rather than reproducing its own separate one -- run
    through _STACK_ICON_OVERRIDES afterward for the two items (Coins
    being the motivating case) where that redirect still doesn't land
    on the specific denomination we want -- and through
    _CRYSTAL_ARMOUR_ICON_OVERRIDES for the same reason on a completely
    different class of item: crystal helm/body/legs, where the bare
    name is shared by all eight cosmetic recolors (that table's own
    comment has the full story), so the bare-name guess this branch
    otherwise relies on can't tell them apart at all."""
    meta = mapping.get(str(item_id))
    if meta:
        icon_filename = meta.get("icon")
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
        icon_filename = name

    icon_filename = _STACK_ICON_OVERRIDES.get(item_id) or _CRYSTAL_ARMOUR_ICON_OVERRIDES.get(item_id) or icon_filename
    return {
        "name": name,
        "icon": item_icon_url(icon_filename),
        "tradeable": tradeable,
        "highAlch": high_alch,
    }


# A "dose" item's own display name is always "Base name(N)" -- N being
# how many doses/sips are left in that particular bottle (1-4 in OSRS,
# never more) -- and the SAME potion shows up as a completely separate
# item id per dose count (Prayer potion(4) and Prayer potion(1) are two
# unrelated GE listings as far as the game's item table is concerned).
# Left alone, that means the exact same potion the player is carrying
# splits into up to four rows in the table below purely because some of
# it has been sipped from. _dose_family below detects that pattern from
# the name alone (no hardcoded potion list to keep updated as Jagex adds
# new ones) so build_possessions_summary can fold every dose variant of
# one potion back into a single row, counted in 1-dose units.
_DOSE_NAME_RE = re.compile(r"^(.*\S)\s*\((\d)\)$")

# A handful of non-potion items use this exact same "Name(N)" naming
# convention for something that ISN'T a fungible quantity -- charges
# left on one specific physical piece of jewelry (an Amulet of glory
# with 1 charge left isn't "1/4 of a shared amulet supply" the way a
# Prayer potion(1) is 1/4 of a shared potion supply). Merging those the
# same way would misrepresent "one charge left on this ring, plus four
# on that other ring" as "owning 5 of the same ring". Named here by
# their base name (lowercase) so _dose_family skips them; add another
# entry if a new charge-based accessory turns up behaving the same way.
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
    """Returns (base_name, dose_count) when `name` is a dose-specific
    potion name like "Super restore(3)", or None when it isn't one at
    all (no trailing "(N)"), the parenthesized number isn't a real dose
    count (outside 1-4 -- OSRS potions never have more than 4 doses),
    or the base name is one of the non-potion charge items excluded
    above."""
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
    """Returns (name, icon, tradeable, itemId) for `base`'s own 1-dose
    variant, e.g. "Super attack" -> Super attack(1)'s own name/icon/
    tradeable/item id -- looked up by name (find_item_ids) and then
    resolved the normal way (resolve_item_display), same as every
    other row on this page, rather than assuming a linear icon-naming
    pattern. `name` is always "{base}(1)" (the in-game convention, no
    space before the parenthesis) even on the rare miss below, so the
    merged row's own QUANTITY always reads as "this many 1-dose
    bottles" regardless of whether the icon/tradeable/itemId lookup
    itself succeeded. icon/itemId come back None on a miss (no real
    "(1)" item id on file for this base name at all) -- the caller
    falls back to an owned variant's own icon/id in that case."""
    name = f"{base}(1)"
    ids = find_item_ids(name)
    if not ids:
        return name, None, False, None
    display = resolve_item_display(ids[0], name, mapping)
    return display["name"], display["icon"], display["tradeable"], ids[0]


def _merge_dose_families(items: List[dict], mapping: dict) -> List[dict]:
    """Folds every dose variant of the same potion (see _dose_family)
    into one row, counted in 1-dose units -- so "Prayer potion(4)" x5
    and "Prayer potion(1)" x2 become a single "Prayer potion(1)" row at
    quantity 22 (5*4 + 2*1), rather than two separate rows for the same
    potion. GE/high-alch "value" for the merged row is each variant's
    own stack value added together and divided back out over the total
    dose count -- a real owned-quantity-weighted average per dose,
    rather than assuming doses price perfectly linearly (they don't
    always) -- so the stack value shown (value per dose * total doses)
    still adds up to exactly what the separate variants were worth.

    The merged row's own name always ends in "(1)" -- same in-game
    naming convention as every other dose variant, no space before the
    parenthesis (e.g. "Divine super combat potion(1)") -- and its icon
    is that same 1-dose bottle's own artwork, resolved by name via
    resolve_item_display exactly like every other row (see
    _resolve_dose1_display below), so QUANTITY's x_ number always
    matches what's actually pictured: however many 1-dose bottles
    worth of this potion are owned, never a picture of some other dose
    count. This holds even when the player doesn't happen to own any
    real 1-dose bottles right now -- the 1-dose item id/icon come from
    the game's own item data, not from what's in the breakdown. Items
    that aren't a dose variant at all pass through untouched."""
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
        # Fallback only -- used when _resolve_dose1_display can't find a
        # real "(1)" item id below, which should be rare (every
        # standard potion has one): whichever owned variant has the
        # most doses, closest to how the potion normally looks "full".
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
            # Dose-variant potions are always GE-tradeable in OSRS (no
            # known untradeable one exists), so a merged row's own value
            # is always a real GE price, never a derived one -- unlike
            # every other row, geDerived isn't carried through per-
            # variant here since there's nothing real to average.
            "geDerived": False,
            "total": total_doses,
            "byLocation": family["byLocation"],
        })
    return merged


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


def pinned_item_ids(db: Session, player: Player) -> set:
    """Every item id this player currently has pinned (see
    PinnedPossessionItem's own docstring in app/models.py) -- a plain
    set, since every caller (build_possessions_summary below, and the
    pin/unpin endpoints in app/main.py, which just hand this same set
    straight back to the frontend) only ever needs membership or a
    flat list, never the rows themselves."""
    rows = (
        db.query(PinnedPossessionItem.item_id)
        .filter(PinnedPossessionItem.player_id == player.id)
        .all()
    )
    return {row[0] for row in rows}


def hidden_storage_keys(db: Session, player: Player) -> set:
    """Every storage source key this player has switched off in
    Storages Viewer's settings menu (see
    HiddenPossessionStorage's own docstring in app/models.py) -- same
    plain-set shape as pinned_item_ids above, for the same reason:
    build_possessions_summary below and the hide/unhide endpoints in
    app/main.py only ever need membership or a flat list back, never
    the rows themselves."""
    rows = (
        db.query(HiddenPossessionStorage.storage_key)
        .filter(HiddenPossessionStorage.player_id == player.id)
        .all()
    )
    return {row[0] for row in rows}


def set_storage_hidden(db: Session, player: Player, storage_key: str, hidden: bool) -> None:
    """Flips one storage source on/off for this player -- the gear-icon
    settings menu next to Storages Viewer's location filter
    buttons (see render_possessions in app/pages.py). Idempotent both
    ways, same reasoning as pin/unpin_possession_item in app/main.py:
    hiding an already-hidden storage (or showing an already-shown one)
    is a no-op rather than an error, so a checkbox flipped twice in a
    row -- e.g. a slow request landing after a faster second click --
    never surfaces an error banner over it."""
    existing = (
        db.query(HiddenPossessionStorage)
        .filter(HiddenPossessionStorage.player_id == player.id, HiddenPossessionStorage.storage_key == storage_key)
        .first()
    )
    if hidden and not existing:
        db.add(HiddenPossessionStorage(player_id=player.id, storage_key=storage_key))
        db.commit()
    elif not hidden and existing:
        db.delete(existing)
        db.commit()


def build_possessions_summary(db: Session, player: Player) -> dict:
    """Section 3's payload -- every item currently owned in any
    storage, each with its live GE/high-alch value and a per-location
    quantity breakdown, so the page's own location toggles (and the
    high-alch/GE-value/tradeable display toggles) can recompute what
    each box shows entirely client-side rather than re-polling this
    endpoint for every toggle flip (see renderItemList's own approach
    in the Loot Tracker page, which this section's box/sort/search UI
    otherwise mirrors closely -- see render_possessions in
    app/pages.py). Potion dose variants of the same potion are folded
    into one row here, counted in 1-dose units (see
    _merge_dose_families) -- everything downstream of this function
    just sees one row per potion, never per dose-specific item id.

    An untradeable item still gets a GE value here whenever RuneLite's
    own ported Item Prices data links it to one (see derived_price_for
    in app/purchase_goals.py -- the same "GE: 5.47M gp" a Crystal helm
    shows on hover in-game). TRADEABLE stays NO for these either way --
    it's a computed stand-in value, not a real GE listing -- geDerived
    on each item marks which rows that applies to, for the frontend to
    show the distinction (a leading "~", since it's an estimate rather
    than a live listing). Coins and Platinum tokens get their own fixed
    gp-conversion rate instead (see currency_gp_rate below), but NOT
    geDerived -- unlike a Crystal helm's linked-item estimate, a coin's
    gp value isn't an approximation of anything; it's exactly 1gp, by
    definition, every time."""
    mapping, mapping_error = get_mapping()
    prices, price_error = get_latest_prices()
    breakdown = get_owned_breakdown(db, player)

    # Coins and Platinum tokens are currency, not goods -- neither has a
    # real Grand Exchange listing (both already show TRADEABLE: NO), but
    # each has an unambiguous gp-equivalent "value" that's more useful
    # here than the em dash they'd otherwise get: a coin's value is
    # just its own face value (1 coin = 1gp), and a platinum token is
    # worth exactly 1,000 coins -- the fixed rate the GE currency
    # exchange counter itself converts at. geDerived is left False for
    # these (see the frontend's valueCell in render_possessions, and
    # this function's own docstring above) -- that flag exists to warn
    # the player a number is an ESTIMATE, and a coin's gp value isn't
    # one: it's exact, by definition, not "close enough" the way a
    # Crystal helm's linked-item price is.
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
            # Not Grand Exchange tradeable, but a lot of untradeables
            # still have a real GE-derived value -- the same "GE: 5.47M
            # gp" a Crystal helm shows on hover in-game, ported from
            # RuneLite's own Item Prices plugin data (see
            # derived_price_for/get_untradeable_mapping in
            # app/purchase_goals.py). TRADEABLE stays NO either way --
            # this is a computed stand-in value, not a real GE listing
            # -- geDerived just lets the frontend mark it as such
            # (see valueCell in render_possessions).
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

    # Marked after merging, not on each raw per-dose-variant item above
    # -- a merged potion row's own itemId (see _merge_dose_families) is
    # what the frontend actually has and what a pin was made against,
    # never one of the pre-merge dose variants' ids.
    pinned_ids = pinned_item_ids(db, player)
    for item in items:
        item["pinned"] = item["itemId"] in pinned_ids

    return {
        "items": items,
        "mappingError": mapping_error,
        "priceError": price_error,
        "hiddenStorageKeys": sorted(hidden_storage_keys(db, player)),
    }


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

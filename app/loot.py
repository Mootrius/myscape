"""Loot Tracker -- what a player has gotten from NPC kills, clue caskets,
raid/minigame rewards and pickpocketing. The myscape RuneLite plugin
(MyscapePlugin#onLootReceived) forwards RuneLite's LootReceived events to POST
/api/players/me/loot (append-only; see LootEvent in app/models.py).
Page data is computed fresh from LootEvent rows in the selected range (the DB
query is windowed).
Clue caskets arrive as "Clue Scroll (<Tier>)" when the plugin paired the tier,
else a bare "Casket". Tiered caskets and raid/minigame events get a "By NPC"
tile; a bare "Casket" or pickpocket only counts toward the chart and totals.
"""
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import GameAccount, HiddenLootEntry, LootEvent
from app.purchase_goals import (
    COINS_ITEM_ID,
    get_latest_prices,
    get_mapping,
    get_untradeable_mapping,
    item_icon_url,
)

# Timerange presets as fixed lookbacks from now; "24h" is the default for a
# missing/unknown ?range=.
DEFAULT_RANGE_KEY = "24h"

RANGE_PRESETS: Dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "1w": timedelta(days=7),
    "1m": timedelta(days=30),
    "3m": timedelta(days=90),
    "6m": timedelta(days=182),
    "1y": timedelta(days=365),
}

# Hard ceiling on bar count so a pathological CUSTOM range cannot produce
# hairline bars.
_MAX_BUCKETS = 400

# NPCs excluded for every player: Wilderness "Crystalline"/"Corrupted" reskins
# and Tombs of Amascut's six boss-room NPCs (duplicates of the raid's chest
# event). Unlike the per-player HiddenLootEntry, build_loot_state skips these
# before anything else, so they affect no total, tile or item breakdown. Matched
# like npc_hide_key.
_EXCLUDED_NPC_NAMES = frozenset(
    name.lower()
    for name in (
        "Crystalline Bat",
        "Crystalline Rat",
        "Crystalline Spider",
        "Crystalline Unicorn",
        "Crystalline Scorpion",
        "Crystalline Wolf",
        "Crystalline Bear",
        "Crystalline Dragon",
        "Crystalline Dark Beast",
        "Corrupted Bat",
        "Corrupted Spider",
        "Corrupted Rat",
        "Corrupted Unicorn",
        "Corrupted Scorpion",
        "Corrupted Wolf",
        "Corrupted Bear",
        "Corrupted Dragon",
        "Corrupted Dark Beast",
        "Ba-Ba",
        "Akkha",
        "Kephri",
        "Zebak",
        "Tumeken's Warden",
        "Elidinis' Warden",
    )
)


def resolve_range(range_key: Optional[str], start: Optional[datetime], end: Optional[datetime]) -> Tuple[datetime, datetime]:
    """Turns the ?range=/&start=/&end= params into a (start, end) UTC pair.
    "custom" uses the given values (swapped if reversed); anything else is a
    fixed lookback, defaulting to DEFAULT_RANGE_KEY.
    """
    if range_key == "custom" and start is not None and end is not None:
        if end < start:
            start, end = end, start
        return start, end
    delta = RANGE_PRESETS.get(range_key or DEFAULT_RANGE_KEY, RANGE_PRESETS[DEFAULT_RANGE_KEY])
    now = datetime.now(timezone.utc)
    return now - delta, now


def parse_loot_range_bound(value: str, *, is_end: bool) -> datetime:
    """Parses ?start=/&end= for range="custom": a bare "YYYY-MM-DD" widens to the
    whole day; a full ISO-8601 timestamp (from a clicked bar's bucketUrl) is
    used verbatim, assuming UTC if naive. Raises ValueError otherwise.
    """
    if "T" in value or ":" in value:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if is_end:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


def _bucket_plan(start: datetime, end: datetime) -> Tuple[int, timedelta, str]:
    """Picks bucket count and granularity (for fmtBucketLabel in
    render_loot_tracker's script) from the span: <=2 days hourly, <=45 daily,
    <=220 weekly, else monthly. Buckets are span / count wide, not
    calendar-aligned.
    """
    span = end - start
    span_days = span.total_seconds() / 86400
    if span_days <= 2:
        granularity = "hourly"
        raw = span.total_seconds() / 3600
    elif span_days <= 45:
        granularity = "daily"
        raw = span_days
    elif span_days <= 220:
        granularity = "weekly"
        raw = span_days / 7
    else:
        granularity = "monthly"
        raw = span_days / 30
    num_buckets = max(1, min(_MAX_BUCKETS, round(raw) or 1))
    bucket_width = span / num_buckets
    return num_buckets, bucket_width, granularity


def _build_name_index(mapping: dict) -> Dict[str, int]:
    """{lowercased tradeable item name: id}, built once per mapping refresh and
    passed to _noted_id_fallback.
    """
    index: Dict[str, int] = {}
    for id_str, meta in mapping.items():
        name = meta.get("name")
        if not name:
            continue
        key = name.strip().lower()
        if key not in index:
            try:
                index[key] = int(id_str)
            except (TypeError, ValueError):
                continue
    return index


def _noted_id_fallback(
    item_id: int,
    mapping: dict,
    item_name: Optional[str] = None,
    name_index: Optional[Dict[str, int]] = None,
) -> Optional[int]:
    """Resolves a noted item's unnoted id (the wiki mapping/price APIs only carry
    the unnoted one). Tries item_id - 1 first, which is not guaranteed:
    Mahogany logs' noted id - 1 is Teak logs' unnoted id. Falls back to
    item_name against name_index (noted items keep the unnoted display name).
    Only returns an id that `mapping` lists while item_id itself is unlisted,
    so untradeables never borrow a price.
    """
    if str(item_id) in mapping:
        return None
    candidate = item_id - 1
    if str(candidate) in mapping:
        return candidate
    if item_name and name_index:
        candidate = name_index.get(item_name.strip().lower())
        if candidate is not None and candidate != item_id:
            return candidate
    return None


# Untradeable drops valued like a linked tradeable (the same link
# derived_price_for uses in app/purchase_goals.py, via get_untradeable_mapping).
# Opt-in rather than every linked item, so other untradeable drops keep their
# 0 gp. Araxyte fang is untradeable but can be etched into the tradeable Etched
# araxyte fang.
_LOOT_LINKED_PRICE_ITEM_IDS = frozenset({29799})  # Araxyte fang


def _sell_price_from_listing(p: Optional[dict]) -> Tuple[Optional[int], Optional[str]]:
    if not p:
        return None, None
    if p.get("low") is not None:
        return p["low"], "low (instant-sell)"
    if p.get("high") is not None:
        return p["high"], "high (instant-buy, no recent sell trades)"
    return None, None


def sell_price_for(
    item_id: int,
    prices: dict,
    mapping: Optional[dict] = None,
    item_name: Optional[str] = None,
    name_index: Optional[Dict[str, int]] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """What a dropped item is worth if sold: the instant-sell ("low") price, the
    opposite of app/purchase_goals.py's unit_price_for. Falls back to the
    unnoted price via _noted_id_fallback, then, for the items in
    _LOOT_LINKED_PRICE_ITEM_IDS, to the linked tradeable's price.
    """
    p = prices.get(str(item_id))
    if not p and mapping is not None:
        unnoted_id = _noted_id_fallback(item_id, mapping, item_name, name_index)
        if unnoted_id is not None:
            p = prices.get(str(unnoted_id))
    price, source = _sell_price_from_listing(p)
    if price is not None or item_id not in _LOOT_LINKED_PRICE_ITEM_IDS:
        return price, source
    total = 0
    for component in get_untradeable_mapping().get(str(item_id), []):
        component_price, _ = _sell_price_from_listing(prices.get(str(component["itemId"])))
        if component_price is not None:
            total += component_price * component["qty"]
    if not total:
        return None, None
    return total, "linked item (instant-sell)"


def _item_value(
    item_id: Optional[int],
    quantity: int,
    prices: dict,
    mapping: Optional[dict] = None,
    item_name: Optional[str] = None,
    name_index: Optional[Dict[str, int]] = None,
) -> int:
    if item_id is None:
        return 0
    if item_id == COINS_ITEM_ID:
        return quantity
    unit_price, _src = sell_price_for(item_id, prices, mapping, item_name, name_index)
    return (unit_price or 0) * quantity


_ICON_EXT_RE = re.compile(r"\.(png|gif|jpg|jpeg)$", re.IGNORECASE)


def npc_icon_url(name: Optional[str]) -> Optional[str]:
    """Best-effort NPC/event portrait guessed from the wiki's "<Name>.png"
    convention. Multi-form NPCs fall back to the infobox's first image in
    app/icon_cache.py; a missing portrait 404s and the frontend hides it.
    Served via /icon-cache/ because direct wiki hotlinks trip its rate
    limiting.
    """
    if not name:
        return None
    filename = name if _ICON_EXT_RE.search(name) else name + ".png"
    return "/icon-cache/" + urllib.parse.quote(filename)


# Sources where npc_icon_url's guessed "<source_name>.png" picks the wrong
# picture or none, so a wiki filename or bundled /static/ image is hand-picked.
# Keyed by lowercased raw source_name, for both "npc" and "event" sources.
# {key: (display name override or None, portrait filename or "/static/..." URL)}
# - Tombs of Amascut, Intricate pouch, Hallowed Sepulchre Coffin, Golem
# Crafting, Barrows: events with no creature portrait of their own.
# - Guardians of the Rift: renamed to the NPC who hands out its reward.
# - Skeleton Hellhound: no single infobox portrait; the Vet'ion reskin is used.
_NPC_DISPLAY_OVERRIDES: Dict[str, Tuple[Optional[str], str]] = {
    "tombs of amascut": (None, "Tumeken's Warden (level-489).png"),
    "intricate pouch": (None, "Intricate pouch detail.png"),
    "guardians of the rift": ("Rewards Guardian", "Rewards Guardian.png"),
    "skeleton hellhound": (None, "Skeleton Hellhound (Vet'ion).png"),
    "hallowed sepulchre coffin": (None, "Coffin (Hallowed Sepulchre).png"),
    "golem crafting": (None, "Golem (sunstone).png"),
    "barrows": (None, "Chest (Barrows).png"),
    # Reward events named after an item (seed pack, bird nest, salvage, dossier,
    # unsired, forgotten lockbox) show the wiki "detail" render in the NPC/source panel; the item
    # panel uses the small CDN icon (see _resolve_loot_items).
    "seed pack": (None, "Seed pack detail.png"),
    "bird nest": (None, "Bird nest (empty) detail.png"),
    "small salvage": (None, "Small salvage detail.png"),
    "fishy salvage": (None, "Fishy salvage detail.png"),
    "barracuda salvage": (None, "Barracuda salvage detail.png"),
    "large salvage": (None, "Large salvage detail.png"),
    "plundered salvage": (None, "Plundered salvage detail.png"),
    "martial salvage": (None, "Martial salvage detail.png"),
    "fremennik salvage": (None, "Fremennik salvage detail.png"),
    "opulent salvage": (None, "Opulent salvage detail.png"),
    "dossier": (None, "Dossier detail.png"),
    "unsired": (None, "Unsired detail.png"),
    "forgotten lockbox": (None, "Forgotten lockbox detail.png"),
    # Grotesque Guardians' loot is recorded under its phase NPC "Dusk".
    "dusk": ("Grotesque Guardians", "Dusk.png"),
    "duke sucellus": (None, "/static/img/npc-duke-sucellus.png"),
    # The nine "Tarnished ..." NPCs fold into one "Tarnished items" tile
    # (grouped by display name).
    "tarnished 2h sword": ("Tarnished items", "/static/img/npc-tarnished-items.png"),
    "tarnished amulet": ("Tarnished items", "/static/img/npc-tarnished-items.png"),
    "tarnished battleaxe": ("Tarnished items", "/static/img/npc-tarnished-items.png"),
    "tarnished halberd": ("Tarnished items", "/static/img/npc-tarnished-items.png"),
    "tarnished longsword": ("Tarnished items", "/static/img/npc-tarnished-items.png"),
    "tarnished necklace": ("Tarnished items", "/static/img/npc-tarnished-items.png"),
    "tarnished bracelet": ("Tarnished items", "/static/img/npc-tarnished-items.png"),
    "tarnished ring": ("Tarnished items", "/static/img/npc-tarnished-items.png"),
    "tarnished spear": ("Tarnished items", "/static/img/npc-tarnished-items.png"),
}


def _override_icon_url(icon: str) -> Optional[str]:
    """Portrait URL for an override: "/..." values are bundled /static/ images
    used as-is, else a wiki filename routed through npc_icon_url.
    """
    return icon if icon.startswith("/") else npc_icon_url(icon)


# Clue tiers recognized, as the canonical names _clue_tier_from_source_name
# returns.
CLUE_TIERS = ["Beginner", "Easy", "Medium", "Hard", "Elite", "Master"]

# Matches the tiered clue event name "Clue Scroll (Hard)" etc., which the plugin
# sends after pairing a casket with its chat line "You have completed N <tier>
# Treasure Trails." (MyscapePlugin#onChatMessage). Case-insensitive;
# re-normalized against CLUE_TIERS.
_CLUE_TIER_RE = re.compile(r"^Clue Scroll \((Beginner|Easy|Medium|Hard|Elite|Master)\)$", re.IGNORECASE)


def _clue_tier_from_source_name(source_name: Optional[str]) -> Optional[str]:
    """The canonical tier name for a tiered clue event name, else None."""
    if not source_name:
        return None
    match = _CLUE_TIER_RE.match(source_name.strip())
    if not match:
        return None
    matched = match.group(1).lower()
    for tier in CLUE_TIERS:
        if tier.lower() == matched:
            return tier
    return None


def clue_casket_icon_url(tier: str) -> str:
    """A closed reward casket's portrait for the tier: the wiki's larger "detail"
    render ("Reward casket (hard) detail.png"), served via /icon-cache/.
    """
    filename = f"Reward casket ({tier.lower()}) detail.png"
    return "/icon-cache/" + urllib.parse.quote(filename)


# Hiding NPCs/items (see HiddenLootEntry in app/models.py)
# Both key functions are the single place hide writes (main.py) and
# build_loot_state reads derive a key, so the two cannot drift.


def npc_hide_key(name: Optional[str]) -> str:
    """An NPC's (or tiered casket's) hide key: its trimmed, lowercased name. Loot
    events carry no numeric NPC id.
    """
    return (name or "").strip().lower()


def item_hide_key(item_id: Optional[int], item_name: Optional[str]) -> str:
    """An item's hide key: itemId if resolved, else itemName (as in
    _add_item_totals), prefixed by kind so an id and a name never collide.
    """
    if item_id is not None:
        return "id:" + str(item_id)
    return "name:" + (item_name or "").strip().lower()


def hidden_npc_keys(db: Session, game_account: GameAccount) -> set:
    """Hidden NPC keys for this player, as a set."""
    rows = (
        db.query(HiddenLootEntry.key)
        .filter(HiddenLootEntry.game_account_id == game_account.id, HiddenLootEntry.kind == "npc")
        .all()
    )
    return {row[0] for row in rows}


def hidden_item_keys(db: Session, game_account: GameAccount) -> set:
    """Hidden item keys for this player, as a set."""
    rows = (
        db.query(HiddenLootEntry.key)
        .filter(HiddenLootEntry.game_account_id == game_account.id, HiddenLootEntry.kind == "item")
        .all()
    )
    return {row[0] for row in rows}


def set_npc_hidden(db: Session, game_account: GameAccount, name: str, hidden: bool) -> None:
    """Hides or unhides one NPC by name (eye button in render_loot_tracker,
    app/pages/). Idempotent.
    """
    key = npc_hide_key(name)
    existing = (
        db.query(HiddenLootEntry)
        .filter(HiddenLootEntry.game_account_id == game_account.id, HiddenLootEntry.kind == "npc", HiddenLootEntry.key == key)
        .first()
    )
    if hidden and not existing:
        db.add(HiddenLootEntry(game_account_id=game_account.id, kind="npc", key=key))
        db.commit()
    elif not hidden and existing:
        db.delete(existing)
        db.commit()


def set_item_hidden(db: Session, game_account: GameAccount, item_id: Optional[int], item_name: Optional[str], hidden: bool) -> None:
    """Hides or unhides one item via item_hide_key. Idempotent."""
    key = item_hide_key(item_id, item_name)
    existing = (
        db.query(HiddenLootEntry)
        .filter(HiddenLootEntry.game_account_id == game_account.id, HiddenLootEntry.kind == "item", HiddenLootEntry.key == key)
        .first()
    )
    if hidden and not existing:
        db.add(HiddenLootEntry(game_account_id=game_account.id, kind="item", key=key))
        db.commit()
    elif not hidden and existing:
        db.delete(existing)
        db.commit()


def _resolve_loot_items(
    raw_items: list,
    mapping: dict,
    prices: dict,
    hidden_items: set,
    name_index: Optional[Dict[str, int]] = None,
) -> Tuple[List[dict], int]:
    resolved = []
    total_value = 0
    for raw in raw_items:
        item_id = raw.get("item_id")
        quantity = raw.get("quantity", 0) or 0
        raw_item_name = raw.get("item_name")
        # Fold a noted id to its unnoted one so both variants merge in
        # _add_item_totals.
        canonical_id = item_id
        if item_id is not None:
            unnoted_id = _noted_id_fallback(item_id, mapping, raw_item_name, name_index)
            if unnoted_id is not None:
                canonical_id = unnoted_id
        meta = mapping.get(str(canonical_id), {}) if canonical_id is not None else {}
        item_name = raw_item_name or meta.get("name") or (
            f"Item #{canonical_id}" if canonical_id is not None else "Unknown item"
        )
        value = _item_value(item_id, quantity, prices, mapping, raw_item_name, name_index)
        total_value += value
        # Item tiles use the small CDN icon; NPC/source tiles use the wiki
        # detail render (_NPC_DISPLAY_OVERRIDES).
        icon = item_icon_url(canonical_id)
        resolved.append({
            "itemId": canonical_id,
            "itemName": item_name,
            "icon": icon,
            "quantity": quantity,
            "value": value,
            "hidden": item_hide_key(canonical_id, item_name) in hidden_items,
        })
    return resolved, total_value


def _add_item_totals(bucket: Dict[object, dict], items: List[dict], occurred_at: datetime) -> None:
    """Folds one event's items into a {itemKey: totals} dict (itemId, else name),
    summing quantity/value. Relies on newest-first iteration: the first
    sighting of a key is its latest drop, so lastDroppedAt is set once.
    """
    for it in items:
        key = it["itemId"] if it["itemId"] is not None else it["itemName"]
        totals = bucket.get(key)
        if totals is None:
            totals = {
                "itemId": it["itemId"],
                "itemName": it["itemName"],
                "icon": it["icon"],
                "quantity": 0,
                "value": 0,
                "lastDroppedAt": occurred_at,
                "hidden": it["hidden"],
            }
            bucket[key] = totals
        totals["quantity"] += it["quantity"]
        totals["value"] += it["value"]


def _finalize_items(bucket: Dict[object, dict]) -> List[dict]:
    """Turns an _add_item_totals dict into the frontend list, with lastDroppedAt
    as ISO string. Order is irrelevant (client sorts).
    """
    out = []
    for totals in bucket.values():
        out.append({**totals, "lastDroppedAt": totals["lastDroppedAt"].isoformat()})
    return out


def build_loot_state(db: Session, game_account: GameAccount, start: datetime, end: datetime) -> dict:
    """Everything the Loot Tracker page needs in one payload for [start, end)
    (see resolve_range): chart buckets, a per-NPC breakdown and an all-NPCs
    item breakdown. _EXCLUDED_NPC_NAMES sources are skipped first.
    A hidden NPC's kills are left out of buckets/windowValue/windowKills but
    its windowNpcs entry is still built (flagged "hidden") for the eye toggle
    and drill-down. A hidden ITEM's value is subtracted from every total
    (visible_value) and it stays in windowItems/npcItems, flagged. See
    HiddenLootEntry.
    """
    mapping, mapping_error = get_mapping()
    name_index = _build_name_index(mapping)
    prices, prices_error = get_latest_prices()
    hidden_npcs = hidden_npc_keys(db, game_account)
    hidden_items = hidden_item_keys(db, game_account)

    num_buckets, bucket_width, granularity = _bucket_plan(start, end)
    bucket_seconds = bucket_width.total_seconds()
    span_seconds = (end - start).total_seconds()

    # Windowed at the query. Ordered desc so _add_item_totals's "first seen =
    # most recent" holds.
    events = (
        db.query(LootEvent)
        .filter(LootEvent.game_account_id == game_account.id, LootEvent.occurred_at >= start, LootEvent.occurred_at <= end)
        .order_by(desc(LootEvent.occurred_at))
        .all()
    )

    buckets = []
    for i in range(num_buckets):
        buckets.append({
            "start": (start + bucket_width * i).isoformat(),
            "end": (start + bucket_width * (i + 1)).isoformat(),
            "value": 0,
            "killCount": 0,
        })

    # Per-NPC totals, per-bucket values and items for the "By NPC" row; each is
    # a subset of the matching totals. Includes tiered clue events and other
    # "event" sources, not only NPC kills (see npc_like_name). A bare "Casket"
    # or pickpocket only counts toward buckets/windowValue/windowKills.
    npc_totals: Dict[str, dict] = {}
    npc_bucket_values: Dict[str, List[int]] = {}
    npc_items: Dict[str, Dict[object, dict]] = {}
    window_item_totals: Dict[object, dict] = {}

    for event in events:
        if event.occurred_at is None:
            continue
        if (event.source_name or "").strip().lower() in _EXCLUDED_NPC_NAMES:
            continue
        offset = (event.occurred_at - start).total_seconds()
        if not (0 <= offset <= span_seconds):
            continue
        idx = int(offset // bucket_seconds) if bucket_seconds > 0 else 0
        if idx >= num_buckets:
            idx = num_buckets - 1
        if idx < 0:
            continue

        items, _raw_event_value = _resolve_loot_items(event.items or [], mapping, prices, hidden_items, name_index)
        visible_value = sum(it["value"] for it in items if not it["hidden"])

        # Resolves the "By NPC" tile identity. An NPC kill uses
        # source_name/npc_icon_url, a tiered clue event the casket's name and
        # icon, and any other named "event" (raid/minigame) its own name with a
        # guessed portrait. The untiered "Casket" has no identity and
        # pickpockets never get a tile. A _NPC_DISPLAY_OVERRIDES entry (by
        # lowercased raw source_name) replaces name/portrait.
        tier = _clue_tier_from_source_name(event.source_name)
        stripped_name = (event.source_name or "").strip()
        override = _NPC_DISPLAY_OVERRIDES.get(stripped_name.lower())
        if event.source_type == "npc":
            npc_like_name = (override[0] if override else None) or event.source_name
            npc_like_icon = _override_icon_url(override[1]) if override else npc_icon_url(npc_like_name)
        elif tier is not None:
            npc_like_name = f"Reward casket ({tier.lower()})"
            npc_like_icon = clue_casket_icon_url(tier)
        elif event.source_type == "event" and stripped_name and stripped_name.lower() != "casket":
            npc_like_name = (override[0] if override else None) or stripped_name
            npc_like_icon = _override_icon_url(override[1]) if override else npc_icon_url(npc_like_name)
        else:
            npc_like_name = None
            npc_like_icon = None
        is_npc = npc_like_name is not None
        npc_hidden = is_npc and npc_hide_key(npc_like_name) in hidden_npcs

        if not npc_hidden:
            buckets[idx]["value"] += visible_value
            buckets[idx]["killCount"] += 1

        if is_npc:
            name = npc_like_name
            totals = npc_totals.get(name)
            if totals is None:
                totals = {
                    "sourceName": name,
                    "icon": npc_like_icon,
                    "combatLevel": event.combat_level,
                    "killCount": 0,
                    "value": 0,
                    "lastKillAt": event.occurred_at,
                    "hidden": npc_hide_key(name) in hidden_npcs,
                }
                npc_totals[name] = totals
                npc_bucket_values[name] = [0] * num_buckets
                npc_items[name] = {}
            # A hidden entry's own tile still shows its real count and value;
            # only the chart/header totals skip it.
            totals["killCount"] += 1
            totals["value"] += visible_value
            npc_bucket_values[name][idx] += visible_value

            # Own item breakdown includes every item (hidden ones flagged); the
            # "ALL NPCs" view omits a hidden entry's items.
            _add_item_totals(npc_items[name], items, event.occurred_at)
            if not npc_hidden:
                _add_item_totals(window_item_totals, items, event.occurred_at)

    window_npcs = sorted(npc_totals.values(), key=lambda n: (-n["killCount"], -n["value"]))
    for n in window_npcs:
        n["lastKillAt"] = n["lastKillAt"].isoformat()

    return {
        "buckets": buckets,
        "granularity": granularity,
        "rangeStart": start.isoformat(),
        "rangeEnd": end.isoformat(),
        "windowValue": sum(b["value"] for b in buckets),
        "windowKills": sum(b["killCount"] for b in buckets),
        "windowNpcs": window_npcs,
        "npcBucketValues": npc_bucket_values,
        "windowItems": _finalize_items(window_item_totals),
        "npcItems": {name: _finalize_items(items) for name, items in npc_items.items()},
        "pricesError": prices_error,
        "mappingError": mapping_error,
    }


def sync_loot_events(db: Session, game_account: GameAccount, events: list) -> int:
    """Inserts the `events` (LootEventIn-shaped) not already on file, keyed by
    event_id (insert-if-new, see LootEvent in app/models.py). Returns the
    number added.
    """
    if not events:
        return 0

    incoming_ids = [e.event_id for e in events]
    existing_ids = {
        row[0] for row in (
            db.query(LootEvent.event_id)
            .filter(LootEvent.game_account_id == game_account.id, LootEvent.event_id.in_(incoming_ids))
            .all()
        )
    }

    added = 0
    for event in events:
        if event.event_id in existing_ids:
            continue
        existing_ids.add(event.event_id)
        db.add(LootEvent(
            game_account_id=game_account.id,
            event_id=event.event_id,
            source_name=event.source_name,
            source_type=event.source_type,
            combat_level=event.combat_level,
            items=[item.model_dump() for item in event.items],
            occurred_at=event.occurred_at,
        ))
        added += 1
    db.commit()
    return added


def kc_counts_by_player(db: Session, game_account: GameAccount) -> Dict[Tuple[str, str], List[datetime]]:
    """{(source_type, lowercased source_name): [occurred_at, ...]} over the
    player's whole LootEvent history (not range-windowed), one timestamp per
    row. A Mindmaps "kc" goal is checked against it (evaluate_completion in
    app/mindmaps.py); timestamps let a sinceDate filter them.
    Matching is on exact source_name: "Clue Scroll (Hard)" counts only hard
    caskets, and the untiered "Casket" is a separate key.
    """
    rows = (
        db.query(LootEvent.source_type, LootEvent.source_name, LootEvent.occurred_at)
        .filter(LootEvent.game_account_id == game_account.id)
        .all()
    )
    counts: Dict[Tuple[str, str], List[datetime]] = {}
    for source_type, source_name, occurred_at in rows:
        key = (source_type, (source_name or "").strip().lower())
        counts.setdefault(key, []).append(occurred_at)
    return counts


def build_loot_share_snapshot(db: Session, game_account: GameAccount, start: datetime, end: datetime) -> dict:
    """Freezes the data render_loot_tracker_share's wrapper script (app/pages/)
    needs for a read-only, drillable copy of [start, end) at
    myscape.io/s/<code>. Built when a player clicks "Share" (POST
    /api/players/me/loot/share) and stored on SharedContent.payload; never
    recomputed.
    Same {"full", "buckets", "hideBreakdown"} shape as
    app/data/landing_loot_demo.json (scripts/gen_landing_loot_demo.py).
    "full": build_loot_state for the whole range. "buckets": one
    build_loot_state per full["buckets"] entry (same -1ms end trim as
    bucketUrl), index-aligned, including empty buckets. "hideBreakdown": per
    bucket, {npcName: {killCount, items: {itemHideKey: value}}}, so a
    visitor's hide/unhide recomputes bars and totals locally (applyHiddenFlags
    in render_landing_loot_preview's script).
    """
    full_state = build_loot_state(db, game_account, start, end)

    bucket_states = []
    hide_breakdown = []
    for b in full_state["buckets"]:
        b_start = datetime.fromisoformat(b["start"])
        b_end = datetime.fromisoformat(b["end"]) - timedelta(milliseconds=1)
        bucket_state = build_loot_state(db, game_account, b_start, b_end)
        bucket_states.append(bucket_state)

        entry = {}
        for npc in bucket_state["windowNpcs"]:
            items_for_npc = {}
            for item in bucket_state["npcItems"].get(npc["sourceName"], []):
                key = item_hide_key(item["itemId"], item["itemName"])
                items_for_npc[key] = items_for_npc.get(key, 0) + item["value"]
            entry[npc["sourceName"]] = {"killCount": npc["killCount"], "items": items_for_npc}
        hide_breakdown.append(entry)

    return {"full": full_state, "buckets": bucket_states, "hideBreakdown": hide_breakdown}

"""Loot Tracker -- what a player has actually gotten from killing NPCs
(and clue scroll caskets, pickpocketing, and anything else RuneLite's
own bundled Loot Tracker plugin recognizes as loot), ported in spirit
from the original single-user Maintrius tool's Loot Tracker/Trip
Tracker features in osrs_tracker.py, but rebuilt on real-time data
instead of reading a separate "Loot Logger" plugin's log files off
disk.

The old tool depended on a third-party "Loot Logger" plugin writing
JSON-lines files to ~/.runelite/loots/<account hash>/npc/<name>.log
(and .../event/<name>.log for clue caskets), which meant loot only
ever showed up for someone who happened to already have that separate
plugin installed and left enabled. This app's own plugin now captures
the same data itself: see MyscapePlugin#onLootReceived in the
Mootrius/myscape-plugin repo, which subscribes to RuneLite's own
bundled Loot Tracker plugin's LootReceived event -- the same
integration point real third-party loot-logging plugins (including
the "Loot Logger" one the old tool depended on) actually use, rather
than reimplementing NPC-death loot detection from scratch -- and syncs
each kill/casket/pickpocket to POST /api/players/me/loot as it
happens. See LootEvent's docstring in app/models.py for the append-
only sync shape this needs, unlike every other synced source.

This is a first pass, not the full old feature set:

- A rolling last-24-hours bar chart (bucketed hourly, same shape as
  the old tool's own chart), plus a per-NPC breakdown of that same
  window -- a clickable "By NPC" row and a matching per-hour value
  array for each one, so the chart can show one NPC's slice of each
  bucket filled in while the bucket's own full height still shows as
  an outline -- are here. Everything is scoped to the last 24 hours on
  purpose for now; an all-time view (totals, a full per-source
  breakdown, a scrollable history feed) is deliberately not built yet,
  not because it's hard, just not what the page needs today.
- The old tool's per-boss drop-table checklist ("pick Vorkath from a
  dropdown, see its full wiki drop table filled in as you go, with
  hand-curated backfill for kills from before Loot Logger was
  installed") is deliberately NOT ported -- it's bespoke to specific
  bosses and specific pre-existing history that has no equivalent here
  (this app's plugin starts capturing from whenever a player links
  their account, with nothing before that to backfill). A generic
  version of that view -- built on top of the same LootEvent rows and
  a wiki-fetched drop table -- is a natural next refinement once
  there's a UI for picking which source to focus on.
- Every clue casket comes through as source_name "Casket" with no
  tier, whatever tier it actually was -- a real limitation of the
  RuneLite event this reads (see LootEvent's docstring), not something
  this module works around yet. Caskets (and anything else that isn't
  source_type "npc") still count toward the chart's own totals, just
  never toward the "By NPC" row or its per-hour breakdown -- that one's
  NPCs only, by design (see build_loot_state below).
- Computed fresh from this player's last-24-hours of LootEvent rows on
  every read (the DB query itself is windowed, not just the totals),
  same as Purchase Goals computes fresh from every bank/inventory/
  equipment row -- fine at the scale this app runs at today.
"""
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import LootEvent, Player
from app.purchase_goals import COINS_ITEM_ID, ICON_PATH_BASE, get_latest_prices, get_mapping, item_icon_url

# The rolling bar-chart window at the top of the page -- 24 hourly
# buckets, oldest on the left, ending at "now" on the right. Ported
# straight from the original single-user tool's build_npc_tracker/
# build_loot_trackers (osrs_tracker.py), which bucket every kill/casket
# the same way: not calendar-aligned hours, but 24 sliding one-hour
# windows counting back from the moment the page is built.
ROLLING_WINDOW_HOURS = 24


def sell_price_for(item_id: int, prices: dict) -> Tuple[Optional[int], Optional[str]]:
    """What a dropped item is actually worth right now if sold -- the
    mirror of app/purchase_goals.py's unit_price_for, which prefers the
    instant-BUY ("high") price since Purchase Goals is about the cost
    to acquire something. Loot value is the opposite direction: what a
    kill actually netted is what selling its drops would return, not
    what buying them back would cost -- so this prefers instant-sell
    ("low") instead, same as the original tool's own sell_price_for."""
    p = prices.get(str(item_id))
    if not p:
        return None, None
    if p.get("low") is not None:
        return p["low"], "low (instant-sell)"
    if p.get("high") is not None:
        return p["high"], "high (instant-buy, no recent sell trades)"
    return None, None


def _item_value(item_id: Optional[int], quantity: int, prices: dict) -> int:
    if item_id is None:
        return 0
    if item_id == COINS_ITEM_ID:
        return quantity
    unit_price, _src = sell_price_for(item_id, prices)
    return (unit_price or 0) * quantity


_ICON_EXT_RE = re.compile(r"\.(png|gif|jpg|jpeg)$", re.IGNORECASE)


def npc_icon_url(name: Optional[str]) -> Optional[str]:
    """Best-effort NPC/event portrait, guessed off the wiki's usual
    "<Name>.png" infobox-image convention -- the NPC-side counterpart
    to item_icon_url (imported above from app/purchase_goals.py), which
    has an id-keyed mapping API to look item icons up in; NPCs have no
    equivalent, so this is a guess. Some bosses (multiple combat forms,
    no single infobox image) will 404 -- the frontend quietly hides the
    image when that happens, same as item icons already do."""
    if not name:
        return None
    filename = name if _ICON_EXT_RE.search(name) else name + ".png"
    return ICON_PATH_BASE + "/" + urllib.parse.quote(filename)


def _resolve_loot_items(raw_items: list, mapping: dict, prices: dict) -> Tuple[List[dict], int]:
    resolved = []
    total_value = 0
    for raw in raw_items:
        item_id = raw.get("item_id")
        quantity = raw.get("quantity", 0) or 0
        meta = mapping.get(str(item_id), {}) if item_id is not None else {}
        item_name = raw.get("item_name") or meta.get("name") or (
            f"Item #{item_id}" if item_id is not None else "Unknown item"
        )
        value = _item_value(item_id, quantity, prices)
        total_value += value
        icon = item_icon_url(meta.get("icon")) if meta.get("icon") else item_icon_url(item_name)
        resolved.append({
            "itemId": item_id,
            "itemName": item_name,
            "icon": icon,
            "quantity": quantity,
            "value": value,
        })
    return resolved, total_value


def build_loot_state(db: Session, player: Player) -> dict:
    """Everything the Loot Tracker page needs in one payload, all
    windowed to the last ROLLING_WINDOW_HOURS: the rolling bar chart's
    24 hourly buckets, and a per-NPC breakdown of that same window (one
    entry per NPC actually killed in it, plus that NPC's own 24-slot
    hourly value array) -- see the module docstring for what this
    covers today and what's still to come."""
    mapping, mapping_error = get_mapping()
    prices, prices_error = get_latest_prices()

    now = datetime.now(timezone.utc)
    window = timedelta(hours=ROLLING_WINDOW_HOURS)
    window_start = now - window

    # Windowed at the query itself, not just in the totals below -- see
    # the module docstring. Still ordered desc so a tie in which bucket
    # two same-hour events land in resolves the same way it always has.
    events = (
        db.query(LootEvent)
        .filter(LootEvent.player_id == player.id, LootEvent.occurred_at >= window_start)
        .order_by(desc(LootEvent.occurred_at))
        .all()
    )

    # 24 fixed one-hour windows computed once up front (oldest first,
    # ending "now"), the same way the old tool built its own chart --
    # see ROLLING_WINDOW_HOURS above.
    hourly_buckets = []
    for hours_ago in range(ROLLING_WINDOW_HOURS - 1, -1, -1):
        bucket_end = now - timedelta(hours=hours_ago)
        hourly_buckets.append({
            "start": (bucket_end - timedelta(hours=1)).isoformat(),
            "end": bucket_end.isoformat(),
            "value": 0,
            "killCount": 0,
        })

    # Per-NPC totals/hourly breakdown for the "By NPC" row and its
    # click-to-filter overlay on the chart -- npc_hourly[name][i] is
    # always <= hourly_buckets[i]["value"], since it's that same
    # bucket's NPC-only subset. Deliberately npc-only (source_type ==
    # "npc") -- see the module docstring for why caskets/pickpockets
    # still count toward hourly_buckets but never show up here.
    npc_totals: Dict[str, dict] = {}
    npc_hourly: Dict[str, List[int]] = {}

    for event in events:
        if event.occurred_at is None:
            continue
        # The DB query above already excludes anything older than the
        # window, but not a client clock skewed into the future --
        # this still needs to guard idx below from going negative/past
        # the last bucket.
        age = now - event.occurred_at
        if not (timedelta(0) <= age < window):
            continue
        idx = (ROLLING_WINDOW_HOURS - 1) - int(age.total_seconds() // 3600)
        if not (0 <= idx < ROLLING_WINDOW_HOURS):
            continue

        _items, event_value = _resolve_loot_items(event.items or [], mapping, prices)
        hourly_buckets[idx]["value"] += event_value
        hourly_buckets[idx]["killCount"] += 1

        if event.source_type == "npc":
            name = event.source_name
            totals = npc_totals.get(name)
            if totals is None:
                totals = {
                    "sourceName": name,
                    "icon": npc_icon_url(name),
                    "combatLevel": event.combat_level,
                    "killCount": 0,
                    "value": 0,
                }
                npc_totals[name] = totals
                npc_hourly[name] = [0] * ROLLING_WINDOW_HOURS
            totals["killCount"] += 1
            totals["value"] += event_value
            npc_hourly[name][idx] += event_value

    # Same sort as the old tool's own "monsters" list: most-killed
    # first, value as the tiebreaker.
    window_npcs = sorted(npc_totals.values(), key=lambda n: (-n["killCount"], -n["value"]))

    return {
        "hourlyBuckets": hourly_buckets,
        "windowValue": sum(b["value"] for b in hourly_buckets),
        "windowKills": sum(b["killCount"] for b in hourly_buckets),
        "windowNpcs": window_npcs,
        "npcHourlyValues": npc_hourly,
        "pricesError": prices_error,
        "mappingError": mapping_error,
    }


def sync_loot_events(db: Session, player: Player, events: list) -> int:
    """Inserts whichever of `events` (LootEventIn-shaped) this player
    doesn't already have on file, keyed by event_id -- see LootEvent's
    docstring in app/models.py for why this is an insert-if-new rather
    than the delete-and-replace every other sync endpoint uses. Returns
    how many were actually new."""
    if not events:
        return 0

    incoming_ids = [e.event_id for e in events]
    existing_ids = {
        row[0] for row in (
            db.query(LootEvent.event_id)
            .filter(LootEvent.player_id == player.id, LootEvent.event_id.in_(incoming_ids))
            .all()
        )
    }

    added = 0
    for event in events:
        # Guards against both an event already on file AND a duplicate
        # within this same batch (the unique constraint would catch the
        # latter at commit time anyway, but as a 500 rather than this
        # quietly deduping the way a genuine retry is supposed to).
        if event.event_id in existing_ids:
            continue
        existing_ids.add(event.event_id)
        db.add(LootEvent(
            player_id=player.id,
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

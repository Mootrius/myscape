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

- A bar chart over a user-selected timerange (a handful of presets --
  24 hours, 1 week, 1 month, 3/6 months, 1 year -- plus a CUSTOM
  start/end pair), bucketed at a granularity that auto-scales to the
  chosen span (hourly for a short range, daily/weekly/monthly for a
  longer one -- see _bucket_plan below), a clickable "By NPC" row (one
  box per NPC killed in that range) that filters the chart down to
  that NPC's own slice of each bucket -- the rest of each bucket's
  height still shows as an outline -- and an item panel beside it
  (all-NPCs by default, just that NPC's own items once one is
  selected) are here. Every part of the page (the chart, the header's
  own kc/gp totals, the NPC panel, and the item panel) scopes together
  to whichever range is currently selected, not just the chart in
  isolation. An all-time view (a full per-source lifetime breakdown, a
  scrollable history feed) beyond what the longest preset (1 year) or
  a CUSTOM range already covers is deliberately not built yet, not
  because it's hard, just not what the page needs today.
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
- Computed fresh from this player's LootEvent rows in the selected
  range on every read (the DB query itself is windowed, not just the
  totals), same as Purchase Goals computes fresh from every bank/
  inventory/equipment row -- fine at the scale this app runs at today.
"""
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import HiddenLootEntry, LootEvent, GameAccount
from app.purchase_goals import COINS_ITEM_ID, get_latest_prices, get_mapping, item_icon_url

# The timerange presets the chart's range button offers (see
# render_loot_tracker in app/pages.py), each a fixed lookback from
# "now" -- CUSTOM isn't listed here since it carries its own explicit
# start/end instead of a lookback. "24h" is the range this page
# originally hardcoded (see this module's old ROLLING_WINDOW_HOURS),
# kept as the default so an unrecognized/missing ?range= behaves the
# same as before this feature existed.
DEFAULT_RANGE_KEY = "24h"

RANGE_PRESETS: Dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "1w": timedelta(days=7),
    "1m": timedelta(days=30),
    "3m": timedelta(days=90),
    "6m": timedelta(days=182),
    "1y": timedelta(days=365),
}

# Above this many buckets, a bar chart just becomes unreadable
# (indistinguishable hairline bars) -- a hard ceiling regardless of
# what _bucket_plan's span-based math would otherwise produce, mostly
# a guard against a pathological CUSTOM range (a multi-decade span
# would still ask for "monthly" granularity, e.g. hundreds of bars).
_MAX_BUCKETS = 400


def resolve_range(range_key: Optional[str], start: Optional[datetime], end: Optional[datetime]) -> Tuple[datetime, datetime]:
    """Turns GET /api/players/me/loot's ?range=/&start=/&end= query
    params into a concrete (start, end) UTC pair. range_key="custom"
    uses the given start/end verbatim (already parsed to tz-aware
    datetimes by the caller -- see app/main.py's read_loot), swapping
    them if end came in before start rather than erroring, since nothing
    about a picked date range needs to be told "the wrong way around" --
    it's an easy input to get backwards, not a request to reject.
    Anything else (a recognized preset, or a missing/unrecognized key,
    which falls back to DEFAULT_RANGE_KEY the same way an absent
    ?range= always has since this page only ever had one window) is a
    fixed lookback from "now"."""
    if range_key == "custom" and start is not None and end is not None:
        if end < start:
            start, end = end, start
        return start, end
    delta = RANGE_PRESETS.get(range_key or DEFAULT_RANGE_KEY, RANGE_PRESETS[DEFAULT_RANGE_KEY])
    now = datetime.now(timezone.utc)
    return now - delta, now


def _bucket_plan(start: datetime, end: datetime) -> Tuple[int, timedelta, str]:
    """Chooses how many equal-width buckets to slice [start, end] into
    for the bar chart, and what granularity label the frontend should
    use to format each bucket's x-axis tick (see fmtBucketLabel in
    render_loot_tracker's script) -- purely from the range's own span,
    so a short range (like the original hardcoded 24-hour window) gets
    hourly buckets and a long one gets coarser ones, and the chart
    never tries to cram a year's worth of hourly bars into view.
    Thresholds: <=2 days -> hourly, <=45 days -> daily, <=220 days ->
    weekly, longer -> monthly (roughly 24h/1w/1m/3m-6m/1y, this page's
    own presets, each landing solidly inside one band rather than
    right on a boundary).

    Bucket width is the span divided evenly by the bucket count -- NOT
    calendar-aligned hours/days/weeks/months -- so this holds for a
    CUSTOM range of any length, not just the presets: a 40-day custom
    range still gets ~40 sensible daily-ish buckets rather than
    snapping to calendar day boundaries."""
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


def _noted_id_fallback(item_id: int, mapping: dict) -> Optional[int]:
    """A noted item (some monster drops and clue caskets hand out ores
    and similar stackables noted, so they stack in the kill inventory
    instead of taking a slot each) has its own item id, but the wiki's
    mapping/price APIs only ever carry data under the UNNOTED id --
    notes trade at the same price as the unnoted item anyway, so there
    being no separate listing for the noted id isn't a bug on the
    wiki's end. OSRS's item definitions always place a notable item's
    noted id at exactly unnoted_id + 1 (that's how the game links every
    notable item to its own note, not a guess), so unnoted_id is
    item_id - 1. Only returns it once mapping confirms item_id - 1 is
    itself a real, known tradeable item AND item_id is NOT already one
    (both true) -- otherwise a merely-untradeable item (a quest item,
    say) would silently borrow whatever unrelated item happens to sit
    at the neighboring id."""
    if str(item_id) in mapping:
        return None
    candidate = item_id - 1
    if str(candidate) in mapping:
        return candidate
    return None


def sell_price_for(item_id: int, prices: dict, mapping: Optional[dict] = None) -> Tuple[Optional[int], Optional[str]]:
    """What a dropped item is actually worth right now if sold -- the
    mirror of app/purchase_goals.py's unit_price_for, which prefers the
    instant-BUY ("high") price since Purchase Goals is about the cost
    to acquire something. Loot value is the opposite direction: what a
    kill actually netted is what selling its drops would return, not
    what buying them back would cost -- so this prefers instant-sell
    ("low") instead, same as the original tool's own sell_price_for.
    Falls back to a noted item's unnoted counterpart's price when
    given `mapping` -- see _noted_id_fallback."""
    p = prices.get(str(item_id))
    if not p and mapping is not None:
        unnoted_id = _noted_id_fallback(item_id, mapping)
        if unnoted_id is not None:
            p = prices.get(str(unnoted_id))
    if not p:
        return None, None
    if p.get("low") is not None:
        return p["low"], "low (instant-sell)"
    if p.get("high") is not None:
        return p["high"], "high (instant-buy, no recent sell trades)"
    return None, None


def _item_value(item_id: Optional[int], quantity: int, prices: dict, mapping: Optional[dict] = None) -> int:
    if item_id is None:
        return 0
    if item_id == COINS_ITEM_ID:
        return quantity
    unit_price, _src = sell_price_for(item_id, prices, mapping)
    return (unit_price or 0) * quantity


_ICON_EXT_RE = re.compile(r"\.(png|gif|jpg|jpeg)$", re.IGNORECASE)


def npc_icon_url(name: Optional[str]) -> Optional[str]:
    """Best-effort NPC/event portrait, guessed off the wiki's usual
    "<Name>.png" infobox-image convention -- still wiki-sourced, unlike
    every item icon in this app now (see item_icon_url, imported above
    from app/purchase_goals.py, which instead hits RuneLite's own CDN
    directly by real numeric item id). There's no NPC-id equivalent of
    that CDN this app's data model could key off of at all (see
    npc_hide_key's own comment below), so a guessed wiki filename is
    still the only thing to go on here. Some bosses (multiple combat
    forms, e.g. the Alchemical Hydra's four elemental phases) have no
    single portrait under that guessed name -- app/icon_cache.py's
    fetch step falls back to whatever the wiki's own infobox lists as
    that NPC's first version rather than just 404ing outright (see
    _first_infobox_image there), so this only actually 404s, and the
    frontend quietly hides the image the same way a missing item icon
    already does, for a genuinely missing/renamed portrait.

    Routed through our own /icon-cache/<filename> route -- see
    app/icon_cache.py's own top-of-file comment for why a direct wiki
    hotlink here was itself enough to trip the wiki's rate limiting;
    this is now the module's main reason to still exist at all."""
    if not name:
        return None
    filename = name if _ICON_EXT_RE.search(name) else name + ".png"
    return "/icon-cache/" + urllib.parse.quote(filename)


# ---- Hiding NPCs/items out of the tracker (see HiddenLootEntry's own
# docstring in app/models.py) -----------------------------------------
#
# Both key functions below are the single place a hide/unhide write (in
# main.py) and build_loot_state's own reads compute a HiddenLootEntry
# key from a raw name/id, so the two can never drift apart -- storing
# ANY other derived form (the display name's original casing, say)
# would risk a hide made one way not matching a lookup made another.


def npc_hide_key(name: Optional[str]) -> str:
    """An NPC's identity for hiding purposes -- loot events carry no
    numeric NPC id to key off (see LootEvent's docstring in
    app/models.py), so this is the same sourceName build_loot_state
    already groups kills by, just trimmed/lowercased so a hide made
    against one casing still matches a kill logged with another."""
    return (name or "").strip().lower()


def item_hide_key(item_id: Optional[int], item_name: Optional[str]) -> str:
    """An item's identity for hiding purposes -- the same two-tier
    fallback _add_item_totals already keys its own per-item totals
    dicts by (itemId when the drop resolved to a real item id, else
    itemName for the rare drop that never resolved one), just
    stringified with a tier prefix so an id and a same-looking name can
    never collide in the same key space."""
    if item_id is not None:
        return "id:" + str(item_id)
    return "name:" + (item_name or "").strip().lower()


def hidden_npc_keys(db: Session, game_account: GameAccount) -> set:
    """Every NPC this player currently has hidden (see npc_hide_key),
    as a plain set -- build_loot_state's only use for this is
    membership, same as pinned_item_ids in app/possessions.py."""
    rows = (
        db.query(HiddenLootEntry.key)
        .filter(HiddenLootEntry.game_account_id == game_account.id, HiddenLootEntry.kind == "npc")
        .all()
    )
    return {row[0] for row in rows}


def hidden_item_keys(db: Session, game_account: GameAccount) -> set:
    """Every item this player currently has hidden (see item_hide_key),
    as a plain set -- same role as hidden_npc_keys above, just the
    other kind."""
    rows = (
        db.query(HiddenLootEntry.key)
        .filter(HiddenLootEntry.game_account_id == game_account.id, HiddenLootEntry.kind == "item")
        .all()
    )
    return {row[0] for row in rows}


def set_npc_hidden(db: Session, game_account: GameAccount, name: str, hidden: bool) -> None:
    """Hides or unhides one NPC by name (see the eye button on each NPC
    tile in render_loot_tracker, app/pages.py) -- idempotent either
    way, same as Storages Viewer's pin/unpin endpoints: hiding
    an already-hidden NPC, or unhiding one that isn't, is a no-op
    rather than an error."""
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
    """Hides or unhides one item by the same (itemId, itemName) ->
    item_hide_key resolution build_loot_state itself uses -- same
    idempotence as set_npc_hidden above."""
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


def _resolve_loot_items(raw_items: list, mapping: dict, prices: dict, hidden_items: set) -> Tuple[List[dict], int]:
    resolved = []
    total_value = 0
    for raw in raw_items:
        item_id = raw.get("item_id")
        quantity = raw.get("quantity", 0) or 0
        # A noted drop keeps the game's own display name (OSRS shows
        # "Blue dragonhide" whether it's noted or not) but carries a
        # DIFFERENT item id from the unnoted item -- which is exactly
        # what _add_item_totals below groups by, so left alone a noted
        # and unnoted drop of the same item would land in two separate
        # buckets with identical names. Folding the noted id down to
        # its unnoted counterpart here (same lookup _noted_id_fallback
        # already does for pricing, since the wiki's mapping/price
        # APIs never carry a separate listing for the noted id anyway)
        # means both variants resolve to the same itemId and merge into
        # one entry downstream.
        canonical_id = item_id
        if item_id is not None:
            unnoted_id = _noted_id_fallback(item_id, mapping)
            if unnoted_id is not None:
                canonical_id = unnoted_id
        meta = mapping.get(str(canonical_id), {}) if canonical_id is not None else {}
        item_name = raw.get("item_name") or meta.get("name") or (
            f"Item #{canonical_id}" if canonical_id is not None else "Unknown item"
        )
        # Value is still priced off the ORIGINAL item_id (sell_price_for
        # does its own noted-id fallback internally) -- canonical_id is
        # only for grouping/display, not a claim that the two ids are
        # interchangeable everywhere.
        value = _item_value(item_id, quantity, prices, mapping)
        total_value += value
        # A real numeric item id was already on hand for every drop
        # here (canonical_id, straight off the plugin's own sync) --
        # item_icon_url (app/purchase_goals.py) builds RuneLite's CDN
        # URL directly from it, tradeable or not, so unlike before there's
        # no need to fall back to guessing a wiki filename off the bare
        # item name for an untradeable drop any more.
        icon = item_icon_url(canonical_id)
        resolved.append({
            "itemId": canonical_id,
            "itemName": item_name,
            "icon": icon,
            "quantity": quantity,
            "value": value,
            # Same (itemId, itemName) -> key resolution as
            # item_hide_key/_add_item_totals -- see that function's own
            # comment for why this can only ever be set here, once, and
            # simply copied through by every downstream totals dict
            # rather than recomputed anywhere else.
            "hidden": item_hide_key(canonical_id, item_name) in hidden_items,
        })
    return resolved, total_value


def _add_item_totals(bucket: Dict[object, dict], items: List[dict], occurred_at: datetime) -> None:
    """Folds one event's resolved items into a {itemKey: totals} dict
    (itemId when there is one, else the item name -- the same fallback
    _resolve_loot_items itself uses to name an item), summing quantity/
    value and keeping the most recent drop time for that item. Shared
    by the global (all-NPCs) and per-NPC item aggregations in
    build_loot_state below, which differ only in which dict they fold
    into.

    Relies on the caller iterating events newest-first (see
    build_loot_state's query ordering): the *first* time an item key is
    seen is therefore already its most recent drop, so lastDroppedAt is
    only ever set once here, never updated afterward."""
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
                # Same value for every event that folds into this key
                # (a pure lookup against the player's hidden-item set,
                # see item_hide_key), so capturing it once here on
                # first sight is as good as recomputing it every fold.
                "hidden": it["hidden"],
            }
            bucket[key] = totals
        totals["quantity"] += it["quantity"]
        totals["value"] += it["value"]


def _finalize_items(bucket: Dict[object, dict]) -> List[dict]:
    """Turns one item-totals dict from _add_item_totals into the list
    shape the frontend gets, with lastDroppedAt as an ISO string --
    kept as a real datetime internally so future work could compare/
    re-sort server-side, but the page itself sorts client-side (see
    render_loot_tracker's sort tabs), so insertion order here doesn't
    matter."""
    out = []
    for totals in bucket.values():
        out.append({**totals, "lastDroppedAt": totals["lastDroppedAt"].isoformat()})
    return out


def build_loot_state(db: Session, game_account: GameAccount, start: datetime, end: datetime) -> dict:
    """Everything the Loot Tracker page needs in one payload, all
    scoped to [start, end) (see resolve_range, which turns the page's
    range button/CUSTOM picker into this pair): the bar chart's own
    buckets (count and granularity chosen by _bucket_plan from the
    range's span), a per-NPC breakdown of that same range (one entry
    per NPC actually killed in it, that NPC's own per-bucket value
    array, and that NPC's own item breakdown), and an all-NPCs item
    breakdown for when nothing is selected -- see the module docstring
    for what this covers today and what's still to come.

    A hidden NPC's kills are excluded from buckets/windowValue/
    windowKills entirely, as if they'd never happened -- but its own
    entry in windowNpcs is still built normally (just flagged
    "hidden": True) so the eye-toggle button in render_loot_tracker,
    app/pages.py can still show/dim it, and drilling into it still
    works. A hidden ITEM instead just has its own value subtracted out
    of every total it would otherwise count toward (bucket/window/NPC
    values alike -- see visible_value below), whichever NPC (or
    non-NPC source) it came from, while its own entry in windowItems/
    npcItems is likewise kept and flagged rather than dropped -- same
    eye-toggle treatment, one level down. See HiddenLootEntry's own
    docstring in app/models.py for the full hide/unhide model this
    implements."""
    mapping, mapping_error = get_mapping()
    prices, prices_error = get_latest_prices()
    hidden_npcs = hidden_npc_keys(db, game_account)
    hidden_items = hidden_item_keys(db, game_account)

    num_buckets, bucket_width, granularity = _bucket_plan(start, end)
    bucket_seconds = bucket_width.total_seconds()
    span_seconds = (end - start).total_seconds()

    # Windowed at the query itself, not just in the totals below -- see
    # the module docstring. Still ordered desc so a tie in which bucket
    # two same-instant events land in resolves the same way it always
    # has, and so _add_item_totals's "first seen this item key = most
    # recent drop" trick above holds.
    events = (
        db.query(LootEvent)
        .filter(LootEvent.game_account_id == game_account.id, LootEvent.occurred_at >= start, LootEvent.occurred_at <= end)
        .order_by(desc(LootEvent.occurred_at))
        .all()
    )

    # num_buckets equal-width slices covering [start, end) computed
    # once up front (oldest first) -- see _bucket_plan for how
    # num_buckets/bucket_width were chosen.
    buckets = []
    for i in range(num_buckets):
        buckets.append({
            "start": (start + bucket_width * i).isoformat(),
            "end": (start + bucket_width * (i + 1)).isoformat(),
            "value": 0,
            "killCount": 0,
        })

    # Per-NPC totals/per-bucket/item breakdown for the "By NPC" row, its
    # click-to-filter overlay on the chart, and the item panel beside it
    # -- npc_bucket_values[name][i] is always <= buckets[i]["value"],
    # since it's that same bucket's NPC-only subset, and the same is
    # true of each NPC's own item quantities against window_items below.
    # Deliberately npc-only (source_type == "npc") -- see the module
    # docstring for why caskets/pickpockets still count toward buckets
    # but never show up in any of this.
    npc_totals: Dict[str, dict] = {}
    npc_bucket_values: Dict[str, List[int]] = {}
    npc_items: Dict[str, Dict[object, dict]] = {}
    window_item_totals: Dict[object, dict] = {}

    for event in events:
        if event.occurred_at is None:
            continue
        # The DB query above already excludes anything outside the
        # range, but not a client clock skewed past `end` -- this still
        # needs to guard idx below from going negative/past the last
        # bucket.
        offset = (event.occurred_at - start).total_seconds()
        if not (0 <= offset <= span_seconds):
            continue
        idx = int(offset // bucket_seconds) if bucket_seconds > 0 else 0
        if idx >= num_buckets:
            idx = num_buckets - 1
        if idx < 0:
            continue

        items, _raw_event_value = _resolve_loot_items(event.items or [], mapping, prices, hidden_items)
        # What this event actually contributes to any total -- every
        # OTHER item's value, minus whichever of its items the player
        # has individually hidden (see item_hide_key/_resolve_loot_items
        # above). Used for buckets below regardless of source_type, and
        # again for this NPC's own totals further down -- the two
        # numbers are the same computation, just added to different
        # places.
        visible_value = sum(it["value"] for it in items if not it["hidden"])
        is_npc = event.source_type == "npc"
        npc_hidden = is_npc and npc_hide_key(event.source_name) in hidden_npcs

        # A hidden NPC's kill is excluded from the chart/header totals
        # entirely (see this function's own docstring) -- a non-NPC
        # event (no NPC identity to hide) always lands here instead,
        # same as before this feature existed.
        if not npc_hidden:
            buckets[idx]["value"] += visible_value
            buckets[idx]["killCount"] += 1

        if is_npc:
            name = event.source_name
            totals = npc_totals.get(name)
            if totals is None:
                totals = {
                    "sourceName": name,
                    "icon": npc_icon_url(name),
                    "combatLevel": event.combat_level,
                    "killCount": 0,
                    "value": 0,
                    "lastKillAt": event.occurred_at,
                    "hidden": npc_hide_key(name) in hidden_npcs,
                }
                npc_totals[name] = totals
                npc_bucket_values[name] = [0] * num_buckets
                npc_items[name] = {}
            # This NPC's OWN tile always reflects its real kill count
            # and (item-hidden-filtered) value, whether or not the NPC
            # itself is hidden -- so revealing it via the eye toggle
            # shows real numbers, not zeroes, to decide whether to
            # unhide it. Only the chart/header totals above skip a
            # hidden NPC's contribution.
            totals["killCount"] += 1
            totals["value"] += visible_value
            npc_bucket_values[name][idx] += visible_value

            # This NPC's own item breakdown always gets every item
            # (hidden or not -- see _add_item_totals, which now carries
            # each item's own "hidden" flag through untouched) so
            # drilling into a hidden NPC, or one with some items
            # hidden, still shows its full picture. The combined
            # "ALL NPCs" view below is different: a hidden NPC's items
            # don't fold into it at all, matching how its kills don't
            # fold into the chart/header totals above -- hiding an NPC
            # removes it from the combined picture outright, not just
            # dims it there.
            _add_item_totals(npc_items[name], items, event.occurred_at)
            if not npc_hidden:
                _add_item_totals(window_item_totals, items, event.occurred_at)

    # Same sort as the old tool's own "monsters" list: most-killed
    # first, value as the tiebreaker. The frontend re-sorts this itself
    # per its own sort tabs (high/low/alphabetical/recent) -- this
    # ordering is just the payload's own default, not load-bearing.
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
            .filter(LootEvent.game_account_id == game_account.id, LootEvent.event_id.in_(incoming_ids))
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
    """{(source_type, <lowercased source_name>): [occurred_at, ...]}
    across this player's ENTIRE LootEvent history (not windowed by a
    range, unlike build_loot_state above) -- every occurrence's own
    timestamp, per NPC killed, per NPC pickpocketed, per clue-casket-
    or-minigame-reward source. What a Mindmaps "kc" goal node's
    activityType+sourceName+targetCount (and optional sinceDate) is
    checked against (see evaluate_completion in app/mindmaps.py) --
    len(...) of a key's list is the same all-time count this used to
    return directly (as a pre-aggregated int) before a goal could ask
    "since when", and a goal with a sinceDate just counts how many of
    these timestamps fall on or after it instead, so this returns the
    raw per-occurrence timestamps rather than a SQL-side count now that
    a caller might need to filter them by date.

    One entry in a key's list is simply "one LootEvent row with this
    (source_type, source_name)", i.e. one occurrence of that event --
    an NPC kill or a pickpocket is one row per occurrence, so a key's
    list length is a real kill/pickpocket count; a clue casket or
    minigame reward is also one row per occurrence, so it's a real
    open/reward count too, just without a way to split a clue casket
    count by tier (see LootEvent's docstring in app/models.py for
    why)."""
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

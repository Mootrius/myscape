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
- A clue casket USED to always come through as the bare source_name
  "Casket" with no tier at all -- a real limitation of RuneLite's own
  LootReceived event, still true today (see LootEvent's docstring in
  app/models.py). MyscapePlugin now works around it itself, though:
  it independently detects a completed trail's own tier off the
  chatbox's "You have completed N <tier> Treasure Trails." line and
  pairs it with that casket's own LootReceived event (see
  MyscapePlugin#onChatMessage/onLootReceived in the Mootrius/
  myscape-plugin repo), relabeling it "Clue Scroll (<Tier>)" before it
  is ever synced here. build_loot_state below (see
  CLUE_TIERS/_clue_tier_from_source_name/clue_casket_icon_url) then
  treats a tiered clue event as an honorary NPC: it shows up in the
  "By NPC" row itself, under the display name "Reward casket (<tier>)"
  (the wiki/in-game item's own real name, confirmed against the wiki)
  with that tier's own casket icon -- searchable, sortable, hideable,
  and click-to-filter-the-chart, exactly like Vorkath or any other real
  NPC, and its own items fold into the combined "ALL NPCs" item panel
  the same way. Still just the bare "Casket", with no NPC-like
  identity at all, for any older event synced before that plugin
  update, or the rarer case where the chat line and the loot event
  landed too far apart to pair (see CLUE_TIER_MAX_TICK_GAP in the
  plugin) -- those still count toward the chart's own totals exactly as
  before, just can't show up as their own tile with no tier to name it
  by. A pickpocket still never shows up in the "By NPC" row either,
  same as before this feature existed.
- A raid/minigame reward (RuneLite's own LootRecordType.EVENT covers
  these too, same as a clue casket -- "Tombs of Amascut", "Chambers of
  Xeric", "Barrows", "Wintertodt", etc.) gets its own "By NPC" tile the
  same way, under that event's own real name and a guessed wiki
  portrait (see npc_icon_url) -- no chat-line pairing needed here the
  way a clue casket's tier requires, since RuneLite's own LootReceived
  event already carries the raid/minigame's real name untouched.
  Reported missing for a Tombs of Amascut raid specifically: the loot
  was already being received, synced, and folded into the chart's own
  totals all along, it just had no tile of its own the way an NPC kill
  or clue casket did -- see build_loot_state below for the fix.
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

# NPCs that never surface in the Loot Tracker at all, for any player --
# per explicit instruction. The Wilderness rework's "Crystalline" and
# "Corrupted" reskins of its own dungeon NPCs (wolf, bear, rat, dark
# beast, ...) are excluded outright here, both sides of the pair. Same
# for Tombs of Amascut's six boss-room NPCs (Ba-Ba, Akkha, Kephri,
# Zebak, and the raid's two final-boss forms Tumeken's Warden/Elidinis'
# Warden) -- each boss's own kill is a real source_type "npc" LootEvent
# in its own right alongside the raid's own combined "Tombs of Amascut"
# chest event (see build_loot_state's events loop further down), which
# would otherwise double up on every reward the chest already covers
# with six more (mostly-empty) per-boss tiles of their own -- excluded
# per explicit instruction rather than left as noise for every ToA
# raider to individually hide. Deliberately NOT the same mechanism as
# HiddenLootEntry/npc_hide_key
# below -- that's a per-player, reversible choice made from the eye-
# toggle on an NPC's own tile in the UI, and a hidden NPC still gets a
# tile (just dimmed, still countable by unhiding it -- see
# build_loot_state's own docstring). An excluded NPC gets none of
# that: build_loot_state's events loop skips a match here before doing
# anything else with it, so it never touches buckets/windowValue/
# windowKills, never gets its own windowNpcs tile, and its items never
# fold into windowItems -- the same "as if it never happened" treatment
# a hidden NPC only gets for the chart/header totals, extended to cover
# its own tile and item breakdown too, and with no per-player toggle to
# turn it back on. Matched the same case-insensitive, trimmed way
# npc_hide_key normalizes a real hide (see that function's own
# comment), so a casing difference in how the plugin reports a name
# can't slip one through.
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


def parse_loot_range_bound(value: str, *, is_end: bool) -> datetime:
    """Parses one of GET /api/players/me/loot's ?start=/&end= query
    params for range="custom" -- either a bare "YYYY-MM-DD" date (what
    the range menu's own two text inputs in render_loot_tracker,
    app/pages.py, always send) or a full ISO-8601 timestamp with an
    explicit time component (what a clicked bar sends instead -- see
    bucketUrl in that same script, which already knows its own
    bucket's precise start/end down to the millisecond and would lose
    that precision if forced through the date-only path below).
    A bare date is widened to that whole calendar day (00:00:00 for
    the start bound, 23:59:59.999999 for the end bound -- a single day
    on its own names a span, not an instant) the same way this
    function's predecessor always did; a full timestamp is trusted
    verbatim (already tz-aware, or assumed UTC if not) since the
    caller already means something more precise than "that whole
    day". Raises ValueError for anything that's neither -- same as a
    bare strptime call would have, so read_loot's own try/except in
    app/main.py doesn't need to change."""
    if "T" in value or ":" in value:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if is_end:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


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


# A handful of loot sources where npc_icon_url's usual guessed-filename
# default ("<source_name>.png") lands on the wrong picture (or no
# picture at all), so a specific wiki filename is hand-picked here
# instead -- confirmed directly against the wiki, the same way
# clue_casket_icon_url's own filenames are, rather than guessed. Keyed
# by the RAW source_name RuneLite/the plugin actually sends (trimmed,
# lowercased -- matched the same case-insensitive way npc_hide_key
# normalizes a real hide), so it applies whether that source turns out
# to be a real NPC kill (source_type "npc") or a raid/minigame reward
# (source_type "event") once build_loot_state's events loop resolves
# npc_like_name/npc_like_icon for it -- per explicit instruction:
#
# - "Tombs of Amascut": the raid's own combined chest event has no
#   portrait of its own to guess a filename from at all (it's not a
#   creature) -- shown under the final boss's own portrait instead.
# - "Intricate pouch": Guardians of the Rift's own per-round reward
#   event, named after the pouch item it hands out rather than any
#   creature -- same reasoning as Tombs of Amascut above.
# - "Guardians of the Rift": the minigame's own completion event,
#   renamed to "Rewards Guardian" (the NPC who actually hands out its
#   reward) for a clearer display name, not just a different portrait.
# - "Skeleton Hellhound": a real NPC kill, but a bare wiki guess for
#   this exact name has no single infobox portrait of its own to fall
#   back on either (see npc_icon_url's and app/icon_cache.py's own
#   comments on _first_infobox_image) -- Vet'ion's own reskin picked
#   here rather than leaving it to whichever variant that fallback
#   happens to land on.
# - "Hallowed Sepulchre Coffin": Hallowed Sepulchre's own end-of-run
#   reward event -- confirmed against a live tile in-app rather than
#   guessed (RuneLite's Loot Tracker plugin source has historically
#   used a different internal name for this event, "Hallowed Sack", but
#   the live tile is what actually matters here). Shown under the
#   reward coffin's own wiki portrait instead of a bare guess off this
#   name, which has no infobox picture of its own.
# - "Golem Crafting": Wyrmscraig's golem-crafting reward event -- a bare
#   wiki guess off this exact name has no infobox picture of its own
#   ("Golem Crafting" isn't itself an in-game creature/item), so the
#   sunstone golem's own portrait is used instead.
#
# {lowercased raw source_name: (display name override or None to keep
# the raw name as-is, wiki filename to use for its portrait)}.
_NPC_DISPLAY_OVERRIDES: Dict[str, Tuple[Optional[str], str]] = {
    "tombs of amascut": (None, "Tumeken's Warden (level-489).png"),
    "intricate pouch": (None, "Intricate pouch detail.png"),
    "guardians of the rift": ("Rewards Guardian", "Rewards Guardian.png"),
    "skeleton hellhound": (None, "Skeleton Hellhound (Vet'ion).png"),
    "hallowed sepulchre coffin": (None, "Coffin (Hallowed Sepulchre).png"),
    "golem crafting": (None, "Golem (sunstone).png"),
}


# The six clue tiers this app knows how to recognize a casket by -- the
# canonical display name _CLUE_TIER_RE's captured word gets normalized
# to (see _clue_tier_from_source_name below, which is case-insensitive
# on the way in specifically so it isn't at the mercy of whatever exact
# casing the plugin/chat line used).
CLUE_TIERS = ["Beginner", "Easy", "Medium", "Hard", "Elite", "Master"]

# Matches this app's own tiered clue-reward event name -- "Clue Scroll
# (Hard)", etc. -- as MyscapePlugin#onLootReceived now sends it once it
# manages to pair a casket's LootReceived event with the chatbox's own
# "You have completed N <tier> Treasure Trails." line that fires
# alongside it (see that plugin's onChatMessage/onLootReceived for the
# full pairing logic, and this module's own docstring for why RuneLite's
# LootReceived event can't be trusted to carry a tier on its own).
# Case-insensitive since nothing server-side forces the plugin's own
# capitalization choice to stay byte-for-byte in sync with this regex
# forever -- _clue_tier_from_source_name below re-normalizes whatever
# case actually matched against CLUE_TIERS.
_CLUE_TIER_RE = re.compile(r"^Clue Scroll \((Beginner|Easy|Medium|Hard|Elite|Master)\)$", re.IGNORECASE)


def _clue_tier_from_source_name(source_name: Optional[str]) -> Optional[str]:
    """None for anything that isn't one of this app's own tiered clue-
    reward event names (an NPC kill, a pickpocket, a plain untiered
    "Casket" -- still the source_name for a clue casket the plugin
    couldn't pair with a tier in time, e.g. the chatbox line and the
    loot event landing too far apart -- or any other non-clue event),
    else that tier's own canonical, properly-cased name off CLUE_TIERS
    (never whatever raw case _CLUE_TIER_RE happened to match)."""
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
    """A closed reward casket's own portrait for the given tier ("Hard"
    -> "Reward casket (hard) detail.png", the wiki's own real filename
    for the "detail" render of that tier's casket item -- the larger,
    smoothly-shaded image the wiki's own item infobox uses (~27KB),
    rather than the small flat inventory icon this used to point at
    (the plain "Reward casket (hard).png", ~600 bytes -- still a real
    file on the wiki, just not what this picks any more since the
    detail version reads far better at the size loot-tracker.css
    actually renders these tiles). Confirmed directly against the
    wiki like the plain version before it -- unlike npc_icon_url above
    this never needs app/icon_cache.py's redirect/disambiguation
    fallback since all six tiers' detail images resolve on the first
    guess too. Routed through the same /icon-cache/<filename> route as
    npc_icon_url, for the same rate-limiting reason."""
    filename = f"Reward casket ({tier.lower()}) detail.png"
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
    """An NPC's identity for hiding purposes -- or a tiered clue
    casket's, now that build_loot_state treats "Reward casket (<tier>)"
    as an honorary NPC too (see that function's own comment on
    npc_totals). Loot events carry no numeric NPC id to key off (see
    LootEvent's docstring in app/models.py), so this is the same
    sourceName-or-casket-display-name build_loot_state already groups
    kills/opens by, just trimmed/lowercased so a hide made against one
    casing still matches an entry logged with another."""
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

    An NPC in _EXCLUDED_NPC_NAMES above is skipped before any of the
    below even sees it -- no bucket/window contribution, no windowNpcs
    tile, no item breakdown, for any player, with no way to turn it
    back on. That's a stronger, permanent version of the per-player
    hidden-NPC treatment described next.

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
    # since it's that same bucket's own subset, and the same is true of
    # each entry's own item quantities against window_items below. Not
    # npc_totals's real source_type "npc" alone any more, though: a
    # tiered clue-reward event (see _clue_tier_from_source_name) folds
    # in here too, under the display name "Reward casket (<tier>)" --
    # the OSRS wiki/in-game item's own real name (confirmed against the
    # wiki), lowercase tier and all -- and so does any other
    # source_type "event" with a real name of its own (a raid/minigame
    # reward -- "Tombs of Amascut", "Chambers of Xeric", "Barrows", ...
    # -- under that event's own name/guessed portrait), so it shows up,
    # is searched, sorted, hidden, and clicked exactly like any other
    # NPC tile; see npc_like_name/npc_like_icon just below the events
    # loop starts. Still never anything for an UNTIERED "Casket" (the
    # plugin couldn't pair it with a tier in time -- see this module's
    # own docstring) or a pickpocket -- those still just count toward
    # buckets/windowValue/windowKills below and nothing else, same as
    # before this feature existed.
    npc_totals: Dict[str, dict] = {}
    npc_bucket_values: Dict[str, List[int]] = {}
    npc_items: Dict[str, Dict[object, dict]] = {}
    window_item_totals: Dict[object, dict] = {}

    for event in events:
        if event.occurred_at is None:
            continue
        # A permanently-excluded NPC (see _EXCLUDED_NPC_NAMES above)
        # is skipped before anything else below even looks at it --
        # unlike a per-player hidden NPC (npc_hidden further down),
        # which still gets its own windowNpcs tile and still counts
        # toward its OWN totals, just not the chart/header ones, an
        # excluded NPC gets none of that: no tile, no item breakdown,
        # no contribution to any total at all, for any player.
        if (event.source_name or "").strip().lower() in _EXCLUDED_NPC_NAMES:
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

        # A real NPC kill uses its own source_name/portrait as always;
        # a tiered clue-reward event (see _clue_tier_from_source_name)
        # gets treated exactly the same way, just under the casket's own
        # display name/icon instead of an NPC's -- see npc_totals's own
        # comment above for why. A raid/minigame reward (RuneLite's own
        # LootRecordType.EVENT covers both these and clue caskets --
        # "Tombs of Amascut", "Chambers of Xeric", "Barrows", "Wintertodt",
        # etc. -- see MyscapePlugin#onLootReceived in the Mootrius/
        # myscape-plugin repo, which just passes RuneLite's own event
        # name through untouched for these, no chat-line pairing needed
        # the way a clue casket's tier does) is now an honorary NPC too,
        # under its own real event name and a guessed wiki portrait --
        # npc_icon_url's own docstring already calls its guess an
        # "NPC/event portrait" for exactly this reason. Reported missing
        # for a Tombs of Amascut raid specifically (RuneLite's own Loot
        # Tracker panel already shows these; ours didn't), even though
        # the raw LootEvent was already being received/stored/charted
        # into the buckets/window totals below all along -- it just never
        # got its own "By NPC" tile the way an NPC kill or clue casket
        # did, which is the actual bug this branch fixes.
        # The bare, untiered "Casket" placeholder name (the plugin
        # couldn't pair it with a tier in time -- see this module's own
        # docstring) is deliberately excluded here even though it's also
        # source_type "event": it has no meaningful identity of its own
        # to show a tile under, unlike a real raid/minigame name. A
        # pickpocket (source_type "pickpocket") still never gets a tile
        # either, same as before this feature existed.
        #
        # A source in _NPC_DISPLAY_OVERRIDES above (Tombs of Amascut,
        # Intricate pouch, Guardians of the Rift, Skeleton Hellhound)
        # swaps in its own hand-picked display name/portrait right here,
        # in place of the source_name/npc_icon_url guess an NPC or event
        # branch would otherwise use -- see that table's own comment for
        # why each one needed it. Looked up once, by the same raw,
        # trimmed, lowercased source_name every other branch below
        # already keys off of, so it applies identically whichever
        # branch (real NPC or named event) actually matches.
        tier = _clue_tier_from_source_name(event.source_name)
        stripped_name = (event.source_name or "").strip()
        override = _NPC_DISPLAY_OVERRIDES.get(stripped_name.lower())
        if event.source_type == "npc":
            npc_like_name = (override[0] if override else None) or event.source_name
            npc_like_icon = npc_icon_url(override[1]) if override else npc_icon_url(npc_like_name)
        elif tier is not None:
            npc_like_name = f"Reward casket ({tier.lower()})"
            npc_like_icon = clue_casket_icon_url(tier)
        elif event.source_type == "event" and stripped_name and stripped_name.lower() != "casket":
            npc_like_name = (override[0] if override else None) or stripped_name
            npc_like_icon = npc_icon_url(override[1]) if override else npc_icon_url(npc_like_name)
        else:
            npc_like_name = None
            npc_like_icon = None
        is_npc = npc_like_name is not None
        npc_hidden = is_npc and npc_hide_key(npc_like_name) in hidden_npcs

        # A hidden NPC's (or hidden clue tier's) kill/open is excluded
        # from the chart/header totals entirely (see this function's
        # own docstring) -- anything with no NPC-like identity at all
        # (no way to hide it specifically) always lands here instead,
        # same as before this feature existed.
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
            # This NPC's (or casket tier's) OWN tile always reflects its
            # real kill/open count and (item-hidden-filtered) value,
            # whether or not it's itself hidden -- so revealing it via
            # the eye toggle shows real numbers, not zeroes, to decide
            # whether to unhide it. Only the chart/header totals above
            # skip a hidden entry's contribution.
            totals["killCount"] += 1
            totals["value"] += visible_value
            npc_bucket_values[name][idx] += visible_value

            # This entry's own item breakdown always gets every item
            # (hidden or not -- see _add_item_totals, which now carries
            # each item's own "hidden" flag through untouched) so
            # drilling into a hidden NPC/tier, or one with some items
            # hidden, still shows its full picture. The combined
            # "ALL NPCs" view below is different: a hidden entry's
            # items don't fold into it at all, matching how its kills/
            # opens don't fold into the chart/header totals above --
            # hiding it removes it from the combined picture outright,
            # not just dims it there.
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
    open/reward count too. A clue casket's own source_name is now
    "Clue Scroll (<Tier>)" whenever the plugin managed to pair its
    tier (see this module's own docstring and CLUE_TIERS/
    _clue_tier_from_source_name above), so a Mindmaps "kc" goal CAN be
    scoped to one specific tier now, just by naming that exact
    sourceName -- "Clue Scroll (Hard)" only counts hard caskets, same
    as this always worked for any other source_name. A goal that still
    wants every tier lumped together has no single key to ask for
    that under any more (source_name is the whole key here, not a
    prefix match), and the older bare "Casket" source_name (still what
    a casket the plugin couldn't tier gets sent as -- see this
    module's own docstring) is its own separate key too, uncounted by
    any tier-specific goal."""
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

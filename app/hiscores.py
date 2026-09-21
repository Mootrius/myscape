"""Boss kill counts, sourced two ways -- see app/routers/linking.py and
MyscapePlugin#onChatMessage in the Mootrius/myscape-plugin repo for the
other halves of this design:

1. sync_hiscores below: a one-time pull from the official OSRS Hiscores,
   fired the moment a character links OR re-links (see
   exchange_link_code in app/routers/linking.py) -- never on an
   interval. This seeds boss_kill_counts with the account's real
   lifetime totals so Goal Tracking has real numbers from the first
   page load, rather than starting every boss at zero.
2. apply_kill_count_updates below: applied every time RuneLite's own
   chatbox announces a fresh kill count ("Your Zulrah kill count is:
   1,234.", etc. -- see KILLCOUNT_PATTERN's own comment in
   MyscapePlugin.java), via POST /api/players/me/kill-counts. This is
   the live source of truth from then on -- the instant the game itself
   reports a number, it's synced, no polling delay of any kind.

Why not just keep pulling the hiscores on an interval (this module's own
earlier design)? Because the official hiscores only get recomputed when
the character logs out -- not continuously while playing -- so an
interval poll made mid-session just echoes back a stale number, and
naively trusting it would make the KC column visibly regress. A chatbox
message has no such problem: it's the exact number the game server just
computed, the moment the kill happened, whether or not the character
ever logs out. That eliminates the whole staleness/logout-gating problem
class an interval-based design has to work around, at the cost of one
real tradeoff worth being explicit about: unlike a hiscores pull (which
re-anchors to ground truth on every success), a missed or dropped chat
message has no self-correction -- see apply_kill_count_updates's own
docstring. POST /api/players/me/hiscores/sync (still here, still
callable directly) exists specifically as a manual escape hatch for
that: relinking, or hitting that endpoint, re-pulls the real hiscores
number and overwrites whatever drift accumulated.

Should a player unlink, tracking is paused for free: revoke_link (see
app/routers/linking.py) revokes the plugin's API key without touching
boss_kill_counts, so POST /api/players/me/kill-counts simply has nothing
valid to authenticate with until the player re-links -- at which point
exchange_link_code re-pulls the hiscores baseline and chat updates
resume from there.

Deliberately the *official* Jagex endpoint, not Wise Old Man or any
other third party, for the one-time baseline pull: it's the same primary
source WOM itself mirrors, so going direct costs nothing accuracy-wise
and drops the extra dependency.

Endpoint shape (confirmed directly against a live response, not just
docs): `GET https://secure.runescape.com/m=hiscore_oldschool{suffix}/
index_lite.json?player=<name>`, one URL per account type (see GAMEMODES
below), JSON body with a `skills` list (unused here) and an
`activities` list -- boss kill counts live there, as
`{"name": "Zulrah", "rank": -1, "score": -1}` when unranked (never
killed it, or too few kills to rank) and real ints otherwise. Querying
the wrong game-mode endpoint for a real account just 404s, same as a
nonexistent name or a player who's opted out of hiscores entirely --
those three cases are indistinguishable from the HTTP response alone.

Rate-limit posture for the hiscores pull (Jagex publishes no formal
quota for this endpoint, but it's the same one WOM, RuneLite's own
hiscores panel, and every third-party OSRS site all hit, and hammering
it is a good way to get an IP soft-throttled). This matters less now
that a pull only ever fires on link/relink rather than every N minutes
for every active account, but the same guards stay in place since
nothing stops a player from rapidly unlinking/relinking, or hitting the
manual resync endpoint repeatedly:

1. Per-account cooldown (_MIN_ACCOUNT_REFRESH_SECONDS, checked against
   the game_account's own hiscores_synced_at column -- persists across
   requests/restarts/deploys, unlike anything in-memory below). A sync
   requested again before this window elapses costs zero network calls
   -- it just hands back what's already stored. Short (see the constant
   below), purely to absorb an accidental rapid-fire relink or double
   click, not a freshness window the way it was back when this module
   polled on an interval.
2. A hard global minimum spacing between ANY two outbound requests to
   Jagex (_throttle below) -- not just per account, across every
   account this whole process ever syncs, including the extra probe
   requests a first-ever sync can cost (see _resolve_gamemode). One
   in-process lock is enough here the same way it's enough for
   app/limiter.py's slowapi Limiter elsewhere in this app: this is a
   single Render web service, not a fleet of workers that would need a
   shared store to coordinate.
3. A short in-memory failure backoff per account (_recent_failures),
   same shape as app/icon_cache.py's own -- a genuinely down or slow
   upstream doesn't get hit again on every subsequent attempt within
   the backoff window.
4. The account's resolved game mode (main/ironman/hardcore/ultimate) is
   cached on the GameAccount row after the first successful sync (see
   _resolve_gamemode), so every sync after the first is exactly one
   request, never a multi-endpoint probe.

A failed fetch never wipes out what's already stored -- sync_hiscores
only ever overwrites hiscores_synced_at (and boss_kill_counts/
boss_kill_counts_updated_at) on a genuine success, so a transient Jagex
hiccup on link/relink just leaves the account without a fresh baseline
yet rather than blanking out or regressing anything.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional
from uuid import UUID

from app.bosses import CHAT_NAME_TO_DISPLAY_NAME, HISCORES_NAME_TO_DISPLAY_NAME

USER_AGENT = "myscape.io/1.0 (Goal Tracking; contact: chandler@myscape.io)"
BASE_URL = "https://secure.runescape.com/m=hiscore_oldschool{suffix}/index_lite.json"

# Probed in this order on an account's first-ever sync (or if its
# previously-cached mode stops resolving -- see _resolve_gamemode) and
# stopped at the first one that returns real data. Deliberately just
# the four persistent, common account types -- deadman/seasonal/
# tournament/skiller/fresh_start are event-scoped or niche enough not
# to be worth the extra probe requests by default.
GAMEMODES = [
    ("main", ""),
    ("ironman", "_ironman"),
    ("hardcore", "_hardcore_ironman"),
    ("ultimate", "_ultimate"),
]
_SUFFIX_BY_MODE = dict(GAMEMODES)

_FETCH_TIMEOUT_SECONDS = 10

# Purely an accidental-rapid-fire guard now (see this module's own
# top-of-file comment) -- a real link/relink cycle, or a deliberate
# manual resync, is never this frequent in practice.
_MIN_ACCOUNT_REFRESH_SECONDS = 60

_MIN_GLOBAL_INTERVAL_SECONDS = 2.0
_FAILURE_BACKOFF_SECONDS = 5 * 60

_rate_lock = threading.Lock()
_last_request_at = 0.0

_failures_lock = threading.Lock()
_recent_failures: Dict[UUID, float] = {}

# app.bosses.CHAT_NAME_TO_DISPLAY_NAME, keyed lower-case -- see
# apply_kill_count_updates for why chat-parsed names are matched
# case-insensitively (unlike HISCORES_NAME_TO_DISPLAY_NAME's exact-match
# use in _parse_boss_kill_counts, where the source is a JSON API whose
# capitalization is always the same).
_CHAT_NAME_TO_DISPLAY_NAME_LOWER = {
    chat_name.lower(): display_name for chat_name, display_name in CHAT_NAME_TO_DISPLAY_NAME.items()
}


class HiscoresSyncError(Exception):
    """Raised only when there's nothing usable to fall back on -- see
    this module's own top-of-file comment on why a fetch failure with
    existing cached data doesn't raise at all."""


class NotLinkedError(HiscoresSyncError):
    """The game account has no runescape_name yet (plugin never linked,
    or linked but hasn't reported a name) -- there's no one to look up."""


class RecentlyFailedError(HiscoresSyncError):
    """This account's hiscores lookup failed recently enough that
    _FAILURE_BACKOFF_SECONDS hasn't elapsed -- see sync_hiscores."""


@dataclass
class HiscoresSyncResult:
    boss_kill_counts: Dict[str, int]
    synced_at: Optional[datetime]
    from_cache: bool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _throttle() -> None:
    """Blocks, if needed, so this call starts no sooner than
    _MIN_GLOBAL_INTERVAL_SECONDS after the last one this process made --
    to ANY gamemode endpoint, not just this account's. Held for the
    whole wait (not released-then-slept) so two threads throttling at
    once can't both wake up at the same moment and race past the
    interval together."""
    global _last_request_at
    with _rate_lock:
        now = time.monotonic()
        wait = _last_request_at + _MIN_GLOBAL_INTERVAL_SECONDS - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _last_request_at = now


def _fetch_gamemode(mode: str, rsn: str) -> Optional[dict]:
    """One throttled GET for this game mode. Returns the parsed JSON on
    200, or None on a 404 (nonexistent name, wrong game mode for this
    account, or hiscores hidden -- see this module's own comment on why
    those three can't be told apart). Anything else (timeout, non-404
    HTTP error, malformed body) raises."""
    suffix = _SUFFIX_BY_MODE[mode]
    url = BASE_URL.format(suffix=suffix) + "?player=" + urllib.parse.quote(rsn)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    _throttle()
    try:
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return json.loads(data)


def _resolve_gamemode(rsn: str, known_mode: Optional[str]):
    """Tries known_mode first if this account already has one cached,
    then falls back through the rest of GAMEMODES (so an account whose
    type changed -- deironed, or a rare mode swap -- self-heals instead
    of getting stuck 404ing forever). Returns (mode, payload) from
    whichever gamemode actually answered, or (None, None) if every one
    of them 404d."""
    tried = set()
    if known_mode and known_mode in _SUFFIX_BY_MODE:
        payload = _fetch_gamemode(known_mode, rsn)
        if payload is not None:
            return known_mode, payload
        tried.add(known_mode)
    for mode, _suffix in GAMEMODES:
        if mode in tried:
            continue
        payload = _fetch_gamemode(mode, rsn)
        if payload is not None:
            return mode, payload
    return None, None


def _parse_boss_kill_counts(payload: dict) -> Dict[str, int]:
    """activities[].name -> kill count, keyed by OUR display_name (see
    app.bosses.HISCORES_NAME_TO_DISPLAY_NAME -- the hiscores' own name
    string differs from ours for a small handful of bosses, e.g. its
    bare "Mimic"/"Nightmare" for our "The Mimic"/"The Nightmare"),
    for every activity this payload reports that matches a boss in
    app.bosses.HISCORE_BOSSES (anything else -- clue scrolls, LMS rank,
    Collections Logged, ... -- isn't a boss and is ignored here). -1
    (Jagex's "not ranked" sentinel) is normalized to 0 rather than kept
    literal, so a boss the player has simply never killed reads as a
    real zero, not a display bug."""
    result: Dict[str, int] = {}
    for activity in payload.get("activities", []):
        display_name = HISCORES_NAME_TO_DISPLAY_NAME.get(activity.get("name"))
        if display_name is None:
            continue
        score = activity.get("score")
        result[display_name] = score if isinstance(score, int) and score > 0 else 0
    return result


def _is_fresh(synced_at: Optional[datetime]) -> bool:
    if synced_at is None:
        return False
    age = (_utcnow() - synced_at).total_seconds()
    return age < _MIN_ACCOUNT_REFRESH_SECONDS


def sync_hiscores(db, game_account) -> HiscoresSyncResult:
    """Pulls this account's real lifetime kill counts from the official
    OSRS hiscores and unconditionally overwrites boss_kill_counts with
    them -- called by exchange_link_code (app/routers/linking.py) the
    moment a character links or re-links, and by POST
    /api/players/me/hiscores/sync for a manual drift-correction resync
    (see this module's own top-of-file comment for why that manual path
    still matters even though nothing polls on an interval anymore).
    Unlike this module's earlier interval-polling design, there's no
    per-boss diffing here any more: a hiscores pull now only ever fires
    at a moment (link/relink/manual resync) where trusting it outright
    is exactly right, not a moment where the character might still be
    logged in accumulating kills this pull would otherwise stomp on.

    Returns cached data (from_cache=True, no network call at all) when
    game_account.hiscores_synced_at is still within
    _MIN_ACCOUNT_REFRESH_SECONDS -- purely an accidental-rapid-fire
    guard now, see that constant's own comment. Otherwise fetches fresh
    data, overwrites boss_kill_counts[name]/
    boss_kill_counts_updated_at[name] together for every boss this pull
    reported (existing entries for any boss NOT in this pull -- there
    shouldn't be any, since every current hiscores boss is always
    reported, ranked or not -- are left as-is rather than dropped),
    always advances hiscores_account_type/hiscores_synced_at, commits,
    and returns the result (from_cache=False).

    Raises NotLinkedError if this game account has no runescape_name
    yet, RecentlyFailedError if it failed within the last
    _FAILURE_BACKOFF_SECONDS, or HiscoresSyncError for a genuine fetch
    failure -- but ONLY when there's no previously-synced data to fall
    back on; if boss_kill_counts already has something in it, a failed
    refresh attempt is swallowed and that existing data is returned
    instead (from_cache=True), so a transient Jagex hiccup never wipes
    out an existing baseline. See this module's own top-of-file
    comment."""
    if not game_account.runescape_name:
        raise NotLinkedError("Link your RuneLite account before syncing hiscores.")

    if _is_fresh(game_account.hiscores_synced_at):
        return HiscoresSyncResult(
            boss_kill_counts=dict(game_account.boss_kill_counts or {}),
            synced_at=game_account.hiscores_synced_at,
            from_cache=True,
        )

    has_prior_data = bool(game_account.boss_kill_counts)

    with _failures_lock:
        failed_at = _recent_failures.get(game_account.id)
    if failed_at is not None and (time.monotonic() - failed_at) < _FAILURE_BACKOFF_SECONDS:
        if has_prior_data:
            return HiscoresSyncResult(
                boss_kill_counts=dict(game_account.boss_kill_counts or {}),
                synced_at=game_account.hiscores_synced_at,
                from_cache=True,
            )
        raise RecentlyFailedError(
            "The last hiscores lookup for this account failed -- try again in a few minutes."
        )

    try:
        mode, payload = _resolve_gamemode(
            game_account.runescape_name, game_account.hiscores_account_type
        )
    except Exception as exc:  # noqa: BLE001 -- network/parse failure, handled below either way
        with _failures_lock:
            _recent_failures[game_account.id] = time.monotonic()
        if has_prior_data:
            return HiscoresSyncResult(
                boss_kill_counts=dict(game_account.boss_kill_counts or {}),
                synced_at=game_account.hiscores_synced_at,
                from_cache=True,
            )
        raise HiscoresSyncError("Couldn't reach the OSRS hiscores. Please try again shortly.") from exc

    if mode is None:
        with _failures_lock:
            _recent_failures[game_account.id] = time.monotonic()
        if has_prior_data:
            return HiscoresSyncResult(
                boss_kill_counts=dict(game_account.boss_kill_counts or {}),
                synced_at=game_account.hiscores_synced_at,
                from_cache=True,
            )
        raise HiscoresSyncError(
            f"'{game_account.runescape_name}' isn't showing up on the OSRS hiscores -- "
            "too new, too low level, or hiscores visibility turned off in-game."
        )

    with _failures_lock:
        _recent_failures.pop(game_account.id, None)

    pulled = _parse_boss_kill_counts(payload)
    synced_at = _utcnow()
    synced_at_iso = synced_at.isoformat()

    # Unconditional overwrite -- see this function's own docstring and
    # this module's top-of-file comment for why that's correct here
    # (unlike the interval-polling design this replaced): every boss
    # this pull reports gets both its stored value and its anchor moved
    # forward together, full stop.
    baseline = dict(game_account.boss_kill_counts or {})
    anchors = dict(game_account.boss_kill_counts_updated_at or {})
    baseline.update(pulled)
    for name in pulled:
        anchors[name] = synced_at_iso

    game_account.boss_kill_counts = baseline
    game_account.boss_kill_counts_updated_at = anchors
    game_account.hiscores_account_type = mode
    game_account.hiscores_synced_at = synced_at
    db.add(game_account)
    db.commit()

    return HiscoresSyncResult(boss_kill_counts=baseline, synced_at=synced_at, from_cache=False)


def apply_kill_count_updates(db, game_account, updates: Iterable) -> int:
    """Applies one or more live, chat-parsed kill-count readings (POST
    /api/players/me/kill-counts -- see app/main.py and
    MyscapePlugin#onChatMessage in the Mootrius/myscape-plugin repo)
    straight to boss_kill_counts, with no diffing against what's
    already stored: unlike a hiscores pull (see sync_hiscores and this
    module's own top-of-file comment on why THAT needs care about
    when it's trusted), a chatbox kill-count line IS the ground truth
    the instant the game announces it -- there's nothing to
    second-guess it against.

    updates is an iterable of objects with .boss_name and .kill_count
    (see KillCountUpdateIn in app/schemas.py). boss_name is matched
    against app.bosses.CHAT_NAME_TO_DISPLAY_NAME case-insensitively --
    chat capitalization isn't as reliably consistent as the hiscores
    API's own JSON. An update whose boss_name doesn't match anything in
    that table is silently skipped rather than treated as an error --
    RuneLite's KILLCOUNT_PATTERN matches some wording this account's
    boss list doesn't cover (a minigame score, a clue tier, some future
    boss not yet added to app.bosses), same tolerance
    _parse_boss_kill_counts already gives an unrecognized hiscores
    activity name.

    Both boss_kill_counts[display_name] and
    boss_kill_counts_updated_at[display_name] are written together for
    every matched update -- see GameAccount's own docstring in
    app/models.py for why these two always move in lockstep. Commits
    once regardless of how many updates matched (no commit at all, and
    no write to game_account, if nothing matched). Returns the number
    actually applied -- fewer than the number of updates submitted is
    normal, not an error, same "partial success reported as a count"
    contract LootSyncResponse.added_count already uses for loot
    events."""
    baseline = dict(game_account.boss_kill_counts or {})
    anchors = dict(game_account.boss_kill_counts_updated_at or {})
    now_iso = _utcnow().isoformat()

    applied = 0
    for update in updates:
        display_name = _CHAT_NAME_TO_DISPLAY_NAME_LOWER.get(update.boss_name.strip().lower())
        if display_name is None:
            continue
        baseline[display_name] = update.kill_count
        anchors[display_name] = now_iso
        applied += 1

    if applied:
        game_account.boss_kill_counts = baseline
        game_account.boss_kill_counts_updated_at = anchors
        db.add(game_account)
        db.commit()

    return applied

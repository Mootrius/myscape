"""Boss kill counts from the official OSRS Hiscores -- the plumbing
behind Goal Tracking's "Sync from Hiscores" button (POST
/api/players/me/hiscores/sync in app/main.py, render_goal_tracking in
app/pages.py).

Deliberately the *official* Jagex endpoint, not Wise Old Man or any
other third party: it's the same primary source WOM itself mirrors, so
going direct costs nothing accuracy-wise and drops the extra
dependency. See the session that built this for the fuller tradeoff
discussion (loot_events already gives near-real-time "kills since
tracking started" for free; this exists for the one thing that can't --
a player's real lifetime total, to seed a goal against).

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

Rate-limit posture (the actual point of this module -- Jagex publishes
no formal quota for this endpoint, but it's the same one WOM, RuneLite's
own hiscores panel, and every third-party OSRS site all hit, and
hammering it is a good way to get an IP soft-throttled):

1. Per-account cache (_MIN_ACCOUNT_REFRESH_SECONDS, checked against the
   game_account's own hiscores_synced_at column -- persists across
   requests/restarts/deploys, unlike anything in-memory below). A sync
   requested again before this window elapses costs zero network calls
   -- it just hands back what's already stored. Generous enough that
   double-clicking the button, or two tabs syncing at once, can't cause
   a request burst, and roughly matched to how often the hiscores
   themselves actually update anyway (see the module docstring above),
   so a shorter window wouldn't even show fresher numbers most of the
   time.
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
   upstream doesn't get hit again on every subsequent click within the
   backoff window.
4. The account's resolved game mode (main/ironman/hardcore/ultimate) is
   cached on the GameAccount row after the first successful sync (see
   _resolve_gamemode), so every sync after the first is exactly one
   request, never a multi-endpoint probe.

A failed fetch never wipes out what's already stored -- sync_hiscores
only overwrites boss_kill_counts/hiscores_synced_at on a genuine
success, so a transient Jagex hiccup leaves Goal Tracking showing
yesterday's numbers rather than blanking out.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import UUID

from app.bosses import HISCORES_NAME_TO_DISPLAY_NAME

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
_MIN_ACCOUNT_REFRESH_SECONDS = 15 * 60
_MIN_GLOBAL_INTERVAL_SECONDS = 2.0
_FAILURE_BACKOFF_SECONDS = 5 * 60

_rate_lock = threading.Lock()
_last_request_at = 0.0

_failures_lock = threading.Lock()
_recent_failures: Dict[UUID, float] = {}


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
    """The one entry point POST /api/players/me/hiscores/sync (app/
    main.py) calls. Returns cached data (from_cache=True, no network
    call at all) when game_account.hiscores_synced_at is still within
    _MIN_ACCOUNT_REFRESH_SECONDS; otherwise fetches fresh data and
    updates+commits game_account's boss_kill_counts/
    hiscores_account_type/hiscores_synced_at before returning it
    (from_cache=False).

    Raises NotLinkedError if this game account has no runescape_name
    yet, RecentlyFailedError if it failed within the last
    _FAILURE_BACKOFF_SECONDS, or HiscoresSyncError for a genuine fetch
    failure -- but ONLY when there's no previously-synced data to fall
    back on; if boss_kill_counts already has something in it, a failed
    refresh attempt is swallowed and that existing data is returned
    instead (from_cache=True), so a transient Jagex hiccup never turns
    an already-working page into an error page. See this module's own
    top-of-file comment."""
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

    boss_kill_counts = _parse_boss_kill_counts(payload)
    synced_at = _utcnow()

    game_account.boss_kill_counts = boss_kill_counts
    game_account.hiscores_account_type = mode
    game_account.hiscores_synced_at = synced_at
    db.add(game_account)
    db.commit()

    return HiscoresSyncResult(boss_kill_counts=boss_kill_counts, synced_at=synced_at, from_cache=False)

"""Boss kill counts, sourced two ways (see app/routers/linking.py and
MyscapePlugin#onChatMessage in the Mootrius/myscape-plugin repo):

1. sync_hiscores: a one-time pull from the official OSRS Hiscores when a
character links or re-links (exchange_link_code), or via POST
/api/players/me/hiscores/sync as a manual drift-correction. Seeds
boss_kill_counts with lifetime totals.
2. apply_kill_count_updates: applied for each RuneLite chatbox kill-count
message (POST /api/players/me/kill-counts). The live source of truth
afterwards. A missed chat message has no self-correction; relinking or the
manual sync re-anchors.

No interval polling: the official hiscores only update on logout, so a
mid-session poll would return a stale number and make the KC regress.
Unlinking pauses tracking, since revoke_link revokes the plugin API key
without touching boss_kill_counts.

The official Jagex endpoint is used rather than a third party: `GET
https://secure.runescape.com/m=hiscore_oldschool{suffix}/index_lite.json?player=<name>`,
one URL per account type (see GAMEMODES). The JSON `activities` list holds
boss counts as `{"name": "Zulrah", "rank": -1, "score": -1}` when unranked. A
wrong game-mode endpoint, a nonexistent name and a hiscores opt-out all 404
and cannot be told apart.

Rate-limit guards (Jagex publishes no quota):
1. Per-account cooldown (_MIN_ACCOUNT_REFRESH_SECONDS) against
game_account.hiscores_synced_at, persisted across restarts; within it, the
stored data is returned with no network call.
2. Global minimum spacing between any two outbound requests (_throttle); one
in-process lock suffices on a single Render service.
3. Short in-memory per-account failure backoff (_recent_failures), as in
app/icon_cache.py.
4. The resolved game mode is cached on the GameAccount row so later syncs are
a single request.

A failed fetch never overwrites stored data.
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

from app.bosses import (
    CHAT_NAME_TO_DISPLAY_NAME,
    CLUE_SCROLL_HISCORE_NAMES,
    HISCORES_NAME_TO_DISPLAY_NAME,
)

USER_AGENT = "myscape.io/1.0 (Goal Tracking; contact: chandler@myscape.io)"
BASE_URL = "https://secure.runescape.com/m=hiscore_oldschool{suffix}/index_lite.json"

# Probed in order on an account's first sync (or when its cached mode stops
# resolving), stopping at the first with data. Only the four persistent account
# types; event-scoped and niche modes are skipped.
GAMEMODES = [
    ("main", ""),
    ("ironman", "_ironman"),
    ("hardcore", "_hardcore_ironman"),
    ("ultimate", "_ultimate"),
]
_SUFFIX_BY_MODE = dict(GAMEMODES)

_FETCH_TIMEOUT_SECONDS = 10

# Only absorbs accidental rapid-fire relinks or double clicks.
_MIN_ACCOUNT_REFRESH_SECONDS = 60

_MIN_GLOBAL_INTERVAL_SECONDS = 2.0
_FAILURE_BACKOFF_SECONDS = 5 * 60

_rate_lock = threading.Lock()
_last_request_at = 0.0

_failures_lock = threading.Lock()
_recent_failures: Dict[UUID, float] = {}

# app.bosses.CHAT_NAME_TO_DISPLAY_NAME keyed lower-case; chat names are matched
# case-insensitively (see apply_kill_count_updates), unlike the exact-match
# hiscores JSON.
_CHAT_NAME_TO_DISPLAY_NAME_LOWER = {
    chat_name.lower(): display_name for chat_name, display_name in CHAT_NAME_TO_DISPLAY_NAME.items()
}

# app/bosses.CLUE_SCROLL_HISCORE_NAMES as a set for O(1) membership checks in
# _parse_clue_scroll_counts.
_CLUE_SCROLL_NAME_SET = set(CLUE_SCROLL_HISCORE_NAMES)


class HiscoresSyncError(Exception):
    """Raised only when there is nothing cached to fall back on (see module
    docstring).
    """


class NotLinkedError(HiscoresSyncError):
    """The game account has no runescape_name yet, so there is no one to look up."""


class RecentlyFailedError(HiscoresSyncError):
    """This account's lookup failed within _FAILURE_BACKOFF_SECONDS (see
    sync_hiscores).
    """


@dataclass
class HiscoresSyncResult:
    boss_kill_counts: Dict[str, int]
    synced_at: Optional[datetime]
    from_cache: bool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _throttle() -> None:
    """Blocks so this call starts at least _MIN_GLOBAL_INTERVAL_SECONDS after the
    last one this process made, to any gamemode endpoint. The lock is held for
    the whole wait so concurrent threads cannot wake together and race past
    the interval.
    """
    global _last_request_at
    with _rate_lock:
        now = time.monotonic()
        wait = _last_request_at + _MIN_GLOBAL_INTERVAL_SECONDS - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _last_request_at = now


def _fetch_gamemode(mode: str, rsn: str) -> Optional[dict]:
    """One throttled GET for this game mode. Returns parsed JSON on 200 or None
    on 404; anything else (timeout, other HTTP error, malformed body) raises.
    """
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
    """Tries known_mode first, then the rest of GAMEMODES, so an account whose
    type changed (e.g. deironed) self-heals. Returns (mode, payload) from the
    first mode that answered, or (None, None) if all 404d.
    """
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
    """activities[].name -> kill count, keyed by our display_name (the hiscores
    name differs for a few bosses, e.g. "Mimic" vs "The Mimic"; see
    app.bosses.HISCORES_NAME_TO_DISPLAY_NAME). Only activities in
    app.bosses.HISCORE_BOSSES are kept. -1 ("not ranked") is normalized to 0.
    """
    result: Dict[str, int] = {}
    for activity in payload.get("activities", []):
        display_name = HISCORES_NAME_TO_DISPLAY_NAME.get(activity.get("name"))
        if display_name is None:
            continue
        score = activity.get("score")
        result[display_name] = score if isinstance(score, int) and score > 0 else 0
    return result


def _parse_clue_scroll_counts(payload: dict) -> Dict[str, int]:
    """activities[].name -> completion count, keyed by the hiscores clue-tier
    name (app.bosses.CLUE_SCROLL_HISCORE_NAMES). -1 normalizes to 0; "Clue
    Scrolls (all)" and non-tier activities are ignored.
    """
    result: Dict[str, int] = {}
    for activity in payload.get("activities", []):
        name = activity.get("name")
        if name not in _CLUE_SCROLL_NAME_SET:
            continue
        score = activity.get("score")
        result[name] = score if isinstance(score, int) and score > 0 else 0
    return result


def _is_fresh(synced_at: Optional[datetime]) -> bool:
    if synced_at is None:
        return False
    age = (_utcnow() - synced_at).total_seconds()
    return age < _MIN_ACCOUNT_REFRESH_SECONDS


def sync_hiscores(db, game_account) -> HiscoresSyncResult:
    """Pulls the account's lifetime kill counts from the official hiscores and
    overwrites boss_kill_counts. Called by exchange_link_code
    (app/routers/linking.py) on link/relink and by POST
    /api/players/me/hiscores/sync.
    
    Returns stored data (from_cache=True, no network) when hiscores_synced_at
    is within _MIN_ACCOUNT_REFRESH_SECONDS. Otherwise fetches, writes
    boss_kill_counts[name] and boss_kill_counts_updated_at[name] together for
    every reported boss (bosses absent from the pull are left as-is), advances
    hiscores_account_type/hiscores_synced_at, commits, and returns
    from_cache=False.
    
    Raises NotLinkedError (no runescape_name), RecentlyFailedError (failed
    within _FAILURE_BACKOFF_SECONDS), or HiscoresSyncError on a fetch failure,
    but only when nothing was previously synced; if boss_kill_counts is
    non-empty the failure is swallowed and the existing data returned
    (from_cache=True).
    """
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
    pulled_clues = _parse_clue_scroll_counts(payload)
    synced_at = _utcnow()
    synced_at_iso = synced_at.isoformat()

    # Unconditional overwrite: a link/relink/manual pull is the right moment to
    # trust the hiscores outright. clue_scroll_counts has no per-tier anchor;
    # nothing else writes it, so hiscores_synced_at says how fresh every tier
    # is.
    baseline = dict(game_account.boss_kill_counts or {})
    anchors = dict(game_account.boss_kill_counts_updated_at or {})
    baseline.update(pulled)
    for name in pulled:
        anchors[name] = synced_at_iso

    clue_baseline = dict(game_account.clue_scroll_counts or {})
    clue_baseline.update(pulled_clues)

    game_account.boss_kill_counts = baseline
    game_account.boss_kill_counts_updated_at = anchors
    game_account.clue_scroll_counts = clue_baseline
    game_account.hiscores_account_type = mode
    game_account.hiscores_synced_at = synced_at
    db.add(game_account)
    db.commit()

    return HiscoresSyncResult(boss_kill_counts=baseline, synced_at=synced_at, from_cache=False)


def apply_kill_count_updates(db, game_account, updates: Iterable) -> int:
    """Applies live, chat-parsed kill-count readings (POST
    /api/players/me/kill-counts, see app/main.py) straight to boss_kill_counts
    with no diffing: the chat line is ground truth.
    
    updates is an iterable of objects with .boss_name and .kill_count
    (KillCountUpdateIn in app/schemas.py). boss_name is matched
    case-insensitively against app.bosses.CHAT_NAME_TO_DISPLAY_NAME; unmatched
    names (minigame scores, clue tiers, new bosses) are skipped silently.
    
    boss_kill_counts[name] and boss_kill_counts_updated_at[name] are written
    together (see GameAccount in app/models.py). Commits once, and not at all
    if nothing matched. Returns the number applied; fewer than submitted is
    normal.
    """
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

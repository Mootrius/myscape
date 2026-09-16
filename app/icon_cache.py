"""Local, weekly-refreshed disk cache for item icon images.

item_icon_url (app/purchase_goals.py) used to hand the browser a direct
hotlink straight to the wiki's Special:FilePath/<name>.png for every
single icon on every single page load. That URL isn't the image itself
-- it's the first of two redirects (FilePath -> Special:Redirect/file/...
-> the actual /images/....png?<hash>), and the wiki marks BOTH of those
redirect hops `cache-control: private, must-revalidate, max-age=0` --
never cacheable, always re-fetched -- even though the final image is
itself served with `cache-control: public, max-age=31536000, immutable`
once you reach it. With dozens of icons on a single Possessions
Monitoring or Loot Tracker page, every refresh was re-hitting the wiki
TWICE per icon just to get redirected to the exact same place as last
time -- almost certainly what was tripping Cloudflare's rate limiting
and showing up as icons that stop loading.

This module fetches the image bytes ourselves, server-side, following
that same redirect chain once, and saves them under app/static/item-
icons/ so the browser can be handed a same-origin URL instead -- one
request to our own server (which itself either already has the file or
fetches it once), never the wiki's redirect chain, on every page load
from then on.

Refreshed weekly rather than on a fixed TTL: OSRS updates every
Wednesday at ~6am EST, so a cached icon counts as stale once the most
recent Thursday 6am America/New_York has passed since it was last
fetched -- one clean weekly refresh window timed to pick up whatever
changed in that update, rather than an arbitrary "7 days since last
fetched" that could just as easily land mid-week.

Lazy and request-driven, not cron-driven, on purpose: this is a single
free Render web service with no separate worker/cron process and an
ephemeral disk (wiped on every redeploy, same as purchase_goals.py's
own in-memory get_mapping/get_latest_prices caches) -- a scheduled job
could simply never fire if nothing hits the site around the moment it's
due, and Render's free tier spins the service down after inactivity
anyway. So instead, every call to cached_icon_url() does a cheap local
freshness check (a stat(), no network) and, if the file is missing or
past this week's Thursday cutoff, hands the work to a small background
thread pool to populate/refresh it -- self-healing on whatever the next
real request happens to be, and never blocking the request that
triggered it (that request gets the direct wiki hotlink for just this
one load, same as it always has, while the cache catches up for next
time).
"""
import os
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, Optional, Set
from zoneinfo import ZoneInfo

# Duplicated from purchase_goals.py's own USER_AGENT/ICON_PATH_BASE
# rather than imported -- purchase_goals.py imports cached_icon_url FROM
# this module, so importing back from it here would be circular. Keep
# these two in sync with purchase_goals.py if they ever change.
USER_AGENT = "myscape.io/1.0 (Purchase Goals; contact: chandler@myscape.io)"
ICON_PATH_BASE = "https://oldschool.runescape.wiki/w/Special:FilePath"

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "item-icons")
os.makedirs(CACHE_DIR, exist_ok=True)

_EASTERN = ZoneInfo("America/New_York")
_FETCH_TIMEOUT_SECONDS = 15
# How long to hold off retrying an icon that just failed to fetch, so a
# renamed/missing file (or a wiki hiccup) doesn't get hammered again on
# every single request that renders it in the meantime -- generous
# enough to avoid a retry storm, short enough that a transient failure
# recovers the same day.
_FAILURE_BACKOFF_SECONDS = 10 * 60
# Bounded rather than one raw thread per miss -- a cold cache (e.g.
# right after a Render redeploy wipes the disk) can have dozens of
# icons go stale/missing at once, and firing them all at the wiki
# simultaneously would recreate exactly the request-burst problem this
# cache exists to avoid. Four at a time is plenty for how few icons any
# one page actually needs refreshed.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="icon-fetch")

_lock = Lock()
_in_flight: Set[str] = set()
_recent_failures: Dict[str, float] = {}


def _safe_filename(icon_filename: Optional[str]) -> Optional[str]:
    """Rejects anything that isn't a plain file name. These come from
    the wiki's own item mapping data, not directly from user input, but
    there's no reason to ever let a "/" or ".." in one turn into a path
    escape out of CACHE_DIR."""
    if not icon_filename:
        return None
    if "/" in icon_filename or "\\" in icon_filename or icon_filename in (".", ".."):
        return None
    return icon_filename


def _thursday_cutoff(now: Optional[datetime] = None) -> datetime:
    """The most recent Thursday 06:00 America/New_York at or before
    `now` -- a cached icon older than this is due for a refresh. Anchoring
    to a fixed weekday (rather than "7 days since last fetched") means
    every icon gets refreshed within a day of Wednesday's game update
    regardless of which day of the previous week it happened to be
    cached on."""
    now = now or datetime.now(_EASTERN)
    days_since_thursday = (now.weekday() - 3) % 7  # Mon=0 ... Thu=3 ... Sun=6
    cutoff = (now - timedelta(days=days_since_thursday)).replace(hour=6, minute=0, second=0, microsecond=0)
    if cutoff > now:
        cutoff -= timedelta(days=7)
    return cutoff


def _cached_path(filename: str) -> str:
    return os.path.join(CACHE_DIR, filename)


def _is_fresh(filename: str) -> bool:
    try:
        mtime = os.path.getmtime(_cached_path(filename))
    except OSError:
        return False
    return datetime.fromtimestamp(mtime, tz=_EASTERN) >= _thursday_cutoff()


def _fetch_and_save(filename: str) -> None:
    url = ICON_PATH_BASE + "/" + urllib.parse.quote(filename)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
        if not content_type.startswith("image/") or not data:
            raise ValueError(f"unexpected icon response ({content_type!r}, {len(data)} bytes)")
        # Write-then-rename rather than writing straight to the real
        # path -- os.replace is atomic on POSIX, so a request racing this
        # fetch always sees either the complete old file or the complete
        # new one, never a half-written one.
        tmp_path = _cached_path(filename) + f".tmp{os.getpid()}-{threading.get_ident()}"
        with open(tmp_path, "wb") as f:
            f.write(data)
        os.replace(tmp_path, _cached_path(filename))
        with _lock:
            _recent_failures.pop(filename, None)
    except Exception:  # noqa: BLE001 -- best-effort cache; a failed fetch just leaves the wiki hotlink in place for this icon
        with _lock:
            _recent_failures[filename] = time.time()
    finally:
        with _lock:
            _in_flight.discard(filename)


def _maybe_refresh_async(filename: str) -> None:
    with _lock:
        if filename in _in_flight:
            return
        failed_at = _recent_failures.get(filename)
        if failed_at is not None and (time.time() - failed_at) < _FAILURE_BACKOFF_SECONDS:
            return
        _in_flight.add(filename)
    _executor.submit(_fetch_and_save, filename)


def cached_icon_url(icon_filename: Optional[str]) -> Optional[str]:
    """Returns our own /icon-cache/<name> URL for an icon that's already
    cached and still fresh this week. Otherwise kicks off a background
    fetch to populate/refresh it for next time and returns None so the
    caller falls back to hotlinking the wiki directly for THIS one
    request (see item_icon_url in app/purchase_goals.py) -- request
    handling never blocks on a network fetch."""
    filename = _safe_filename(icon_filename)
    if not filename:
        return None
    if _is_fresh(filename):
        return "/icon-cache/" + urllib.parse.quote(filename)
    _maybe_refresh_async(filename)
    return None


def resolve_cached_path(icon_filename: Optional[str]) -> Optional[str]:
    """Used by the /icon-cache/{filename} route (app/main.py) to turn a
    requested filename into a real path on disk, or None if it's
    missing/invalid -- freshness doesn't matter here (only whether
    cached_icon_url() offers a URL up in the first place); os.replace's
    atomicity means it's always safe to read whatever's currently
    there, even mid-refresh."""
    filename = _safe_filename(icon_filename)
    if not filename:
        return None
    path = _cached_path(filename)
    return path if os.path.isfile(path) else None

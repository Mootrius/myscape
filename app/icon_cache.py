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
Render web service with no separate worker/cron process, so a scheduled
job could simply never fire if nothing hits the site around the moment
it's due (and on the free tier specifically, the service also spins
down after inactivity, making that worse). So instead, the
/icon-cache/{filename} route (app/main.py) does a cheap local freshness
check (a stat(), no network) on every request and, if the file is
missing or past this week's Thursday cutoff, hands the work to a small
bounded background thread pool to populate/refresh it -- self-healing
on whatever the next real request happens to be, regardless of whether
that file was ever cached before or just went stale.

CACHE_DIR defaults to a folder next to this file (app/static/item-
icons/), which is fine for local dev but ephemeral on Render -- wiped
on every redeploy, same as purchase_goals.py's own in-memory
get_mapping/get_latest_prices caches. In production, ICON_CACHE_DIR
(set in render.yaml) instead points this at a mounted persistent disk,
so the whole point of this module -- not re-fetching an icon we
already have -- actually holds across deploys too, not just within one
running instance's lifetime. Either way, a first-ever view of some
never-before-cached icon (or, without the disk, the first view of
*anything* after a redeploy) still has to actually fetch it once --
this module's job is making sure that only ever happens once per icon,
throttled, rather than every page load.

THIS is also the piece that used to fall back to a direct wiki hotlink
for that one request rather than wait on the fetch -- item_icon_url
handed the browser the raw wiki URL for anything not already cached and
fresh, on the theory that a request should never block on a network
fetch. That's true for the *page* request, but every one of these is
its own separate, already-async, already-lazy-loaded <img> request --
blocking one of THOSE for a few seconds costs nothing a page visitor
would notice, and not blocking it meant every icon miss became a
direct, un-throttled browser-to-wiki request instead. On Possessions
Monitoring especially -- by far the widest, most varied set of icons
any page here shows, since it's a player's whole bank/inventory rather
than a short, repeat-heavy list like Loot Tracker's recent drops or one
gear setup's own slots -- a first view (or, without ICON_CACHE_DIR
pointed at a persistent disk, the first view after any redeploy) could
easily have dozens of icons never fetched before, all at once, all
completely bypassing this module's own
4-at-a-time throttling and racing the browser straight at the wiki in
parallel: exactly the rate-limit-tripping request burst this cache
exists to prevent, just moved from "us re-fetching" to "the browser
fetching directly" instead.

So now: item_icon_url always hands out our own /icon-cache/<filename>
URL, never the wiki's, and ensure_cached_icon_path (called from that
route) is the one place responsible for deciding whether to serve what
we already have, wait briefly for an in-flight fetch, or 404 -- but
ONLY waits when there's truly nothing on disk yet for that icon (a
first-ever view, or -- lacking a persistent ICON_CACHE_DIR -- a cold
cache post-redeploy). Once a file exists,
a stale-past-Thursday icon is still served immediately, with its
refresh happening in the background exactly as before -- there's no
reason to make a request wait on a brand new fetch just because the
cutoff passed, when what's on disk is still a perfectly good icon.
"""
import os
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, Optional
from zoneinfo import ZoneInfo

# Duplicated from purchase_goals.py's own USER_AGENT/ICON_PATH_BASE
# rather than imported -- purchase_goals.py has no reason to import
# anything back from this module any more (see item_icon_url's own
# comment). Keep these two in sync with purchase_goals.py if they ever
# change.
USER_AGENT = "myscape.io/1.0 (Purchase Goals; contact: chandler@myscape.io)"
ICON_PATH_BASE = "https://oldschool.runescape.wiki/w/Special:FilePath"

# ICON_CACHE_DIR overrides where this lives -- set in render.yaml to a
# mounted persistent disk's path in production; unset (the normal case
# for local dev) falls back to a folder next to this file, same as
# before. See this module's own top-of-file comment for why the
# override matters.
CACHE_DIR = os.environ.get("ICON_CACHE_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "item-icons"
)
os.makedirs(CACHE_DIR, exist_ok=True)

_EASTERN = ZoneInfo("America/New_York")
_FETCH_TIMEOUT_SECONDS = 15
# How long a request for a brand new (never-yet-cached) icon will wait
# on that fetch before giving up and 404ing for just this one load --
# generous enough to cover a fetch that's queued behind a few others in
# the burst (see _executor below) plus its own _FETCH_TIMEOUT_SECONDS,
# short enough a genuinely wedged wiki request doesn't hang the <img>
# tag that triggered it. The fetch itself keeps running in the
# background past this timeout either way, so a slow first load still
# leaves the icon cached for next time.
_WAIT_FOR_FRESH_SECONDS = 20
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
# one page actually needs refreshed, and -- now that a genuine cache
# miss waits on this same pool instead of the browser going around it
# -- is also what keeps a burst of brand new icons throttled instead of
# hitting the wiki all at once.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="icon-fetch")

_lock = Lock()
_in_flight: Dict[str, Future] = {}
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
    except Exception:  # noqa: BLE001 -- best-effort cache; a failed fetch just leaves nothing cached for this icon
        with _lock:
            _recent_failures[filename] = time.time()
        raise
    finally:
        with _lock:
            _in_flight.pop(filename, None)


def _get_or_start_fetch(filename: str) -> Optional[Future]:
    """Returns the in-flight Future for this icon -- joining an
    already-running fetch if one exists rather than starting a
    redundant second one for the same filename -- or starts a new one,
    unless it failed too recently (see _FAILURE_BACKOFF_SECONDS), in
    which case this returns None without touching the executor at
    all."""
    with _lock:
        existing = _in_flight.get(filename)
        if existing is not None:
            return existing
        failed_at = _recent_failures.get(filename)
        if failed_at is not None and (time.time() - failed_at) < _FAILURE_BACKOFF_SECONDS:
            return None
        future = _executor.submit(_fetch_and_save, filename)
        _in_flight[filename] = future
        return future


def ensure_cached_icon_path(icon_filename: Optional[str]) -> Optional[str]:
    """Used by the /icon-cache/{filename} route (app/main.py) to turn a
    requested filename into a real path on disk, fetching it first if
    needed -- the one place responsible for deciding whether to serve
    what's already cached, wait briefly on a fetch, or give up (see this
    module's own top-of-file comment for why waiting is limited to just
    the "nothing cached yet" case).

    Returns None if the icon can't be served at all (invalid filename,
    or a fetch that failed/timed out with nothing already on disk) --
    the route turns that into a 404, and the frontend's own onerror
    handler on every icon <img> tag just hides it rather than showing a
    broken image."""
    filename = _safe_filename(icon_filename)
    if not filename:
        return None
    path = _cached_path(filename)
    have_file = os.path.isfile(path)
    if _is_fresh(filename):
        return path
    future = _get_or_start_fetch(filename)
    if have_file:
        # Already have *something* to serve -- no reason to hold this
        # request up over a routine weekly refresh, which keeps running
        # in the background (or already is, via the Future above)
        # regardless of what this particular request does next.
        return path
    if future is None:
        # Nothing on disk, and this exact icon failed recently enough
        # that _get_or_start_fetch declined to retry it yet -- 404 for
        # now, self-healing once the backoff window passes.
        return None
    try:
        future.result(timeout=_WAIT_FOR_FRESH_SECONDS)
    except Exception:  # noqa: BLE001 -- includes the fetch's own failure and a timed-out wait alike
        pass
    return path if os.path.isfile(path) else None

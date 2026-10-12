"""Local, weekly-refreshed disk cache for wiki-sourced icon images.

Used for NPC/event portraits (npc_icon_url in app/loot.py; there is no numeric
NPC id to use an id-keyed CDN) and as the last-resort fallback for rare recipe
items with no known id (_wiki_icon_url in app/purchase_goals.py). Item icons
otherwise come from RuneLite's CDN.

Why cache: the wiki's Special:FilePath URL is the first of two redirects, and
both hops are `cache-control: private, must-revalidate, max-age=0`, so
hotlinking re-hits the wiki twice per icon per page load and trips Cloudflare
rate limiting. This module fetches the image once server-side and serves it
from app/static/item-icons/ under a same-origin /icon-cache/<filename> URL.

Freshness: an icon is stale once the most recent Thursday 06:00
America/New_York (after the Wednesday game update) has passed since it was
fetched.

Lazy, not cron-driven: the service is a single Render web process with no
worker, so the /icon-cache/{filename} route (app/main.py) does a cheap stat()
check and hands missing/stale files to a bounded background thread pool.

CACHE_DIR defaults to a folder next to this file (ephemeral on Render);
ICON_CACHE_DIR (render.yaml) points it at a persistent disk.

Only a request with nothing on disk waits (briefly) on a fetch; stale files
are served immediately while refreshing in the background. Letting the browser
hotlink the wiki on a miss would bypass the pool's throttling and cause
request bursts.

Guessed "<Name>.png" files can 404 permanently (multi-form bosses, names that
are redirects/disambiguation pages); _first_infobox_image falls back to the
page's infobox image and caches it under the originally guessed filename.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, Optional
from zoneinfo import ZoneInfo

# Duplicated from purchase_goals.py (USER_AGENT / ICON_PATH_BASE); keep in sync.
USER_AGENT = "myscape.io/1.0 (Purchase Goals; contact: chandler@myscape.io)"
ICON_PATH_BASE = "https://oldschool.runescape.wiki/w/Special:FilePath"
WIKI_API_BASE = "https://oldschool.runescape.wiki/api.php"

# ICON_CACHE_DIR overrides the location (a persistent disk in production).
CACHE_DIR = os.environ.get("ICON_CACHE_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "item-icons"
)
os.makedirs(CACHE_DIR, exist_ok=True)

_EASTERN = ZoneInfo("America/New_York")
_FETCH_TIMEOUT_SECONDS = 15
# How long a request for a never-cached icon waits on its fetch before 404ing.
# The fetch keeps running in the background, so the icon is still cached for
# next time.
_WAIT_FOR_FRESH_SECONDS = 20
# Back-off after a failed fetch, so a renamed/missing file or wiki hiccup is not
# retried on every request.
_FAILURE_BACKOFF_SECONDS = 10 * 60
# Bounded pool rather than a thread per miss: a cold cache can have dozens of
# icons missing at once, and firing them all at the wiki would recreate the
# request burst this cache avoids.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="icon-fetch")

_lock = Lock()
_in_flight: Dict[str, Future] = {}
_recent_failures: Dict[str, float] = {}


def _safe_filename(icon_filename: Optional[str]) -> Optional[str]:
    """Rejects anything that is not a plain file name (no "/" or ".."), so a name
    can never escape CACHE_DIR.
    """
    if not icon_filename:
        return None
    if "/" in icon_filename or "\\" in icon_filename or icon_filename in (".", ".."):
        return None
    return icon_filename


def _thursday_cutoff(now: Optional[datetime] = None) -> datetime:
    """The most recent Thursday 06:00 America/New_York at or before `now`; a
    cached icon older than this is due for refresh.
    """
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


def _fetch_wiki_bytes(url: str) -> bytes:
    """The GET shared by the direct guess and the infobox fallback. Checks
    content-type, since a dead-end redirect chain can return 200 with an HTML
    error page.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
        content_type = resp.headers.get("Content-Type", "")
        data = resp.read()
    if not content_type.startswith("image/") or not data:
        raise ValueError(f"unexpected icon response ({content_type!r}, {len(data)} bytes)")
    return data


# Matches an infobox `image`/`imageN` parameter and captures the filename in its
# [[File:...]] link. `search` stops at the first match, which is image1 for
# multi-version infoboxes.
_INFOBOX_IMAGE_RE = re.compile(
    r"\|\s*image\d*\s*=\s*\[\[\s*File\s*:\s*([^|\]]+?)\s*(?:\|[^\]]*)?\]\]",
    re.IGNORECASE,
)

# Matches a page that is only a redirect ("#REDIRECT [[Target]]") and captures
# Target. Anchored with `match` so it fires only on pages that are redirects.
_REDIRECT_RE = re.compile(r"^\s*#REDIRECT\s*:?\s*\[\[\s*([^|\]#]+)", re.IGNORECASE)


def _fetch_wikitext(page_title: str) -> Optional[str]:
    """Raw wikitext of one page, or None if it does not exist or has none."""
    url = (
        WIKI_API_BASE
        + "?action=parse&prop=wikitext&format=json&page="
        + urllib.parse.quote(page_title)
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
        payload = json.loads(resp.read())
    return (payload.get("parse") or {}).get("wikitext", {}).get("*")


def _first_wikilink_starting_with(wikitext: str, prefix: str) -> Optional[str]:
    """First `[[Target]]`/`[[Target|Display]]` link in `wikitext` whose Target
    starts with `prefix` (case-insensitive). Deliberately narrower than "first
    link": disambiguation pages mix in same-topic but wrong entries.
    """
    for match in re.finditer(r"\[\[\s*([^|\]#]+?)\s*(?:\|[^\]]*)?\]\]", wikitext):
        target = match.group(1).strip()
        if target.lower().startswith(prefix.lower()):
            return target
    return None


def _first_infobox_image(page_title: str) -> Optional[str]:
    """Called once a guessed "<page_title>.png" has 404d. Returns the first image
    listed in the page's infobox, or None if nothing usable turns up or the
    wiki is unreachable.
    
    Handles two cases, in order: (1) several image1/image2/... parameters on
    one page (e.g. Alchemical Hydra phases), where the first is taken; (2) the
    name is a #REDIRECT (e.g. "Greater Skeleton Hellhound"), followed one hop,
    and for a disambiguation page the first link starting with page_title is
    tried, one hop further and no more.
    """
    wikitext = _fetch_wikitext(page_title)
    if not wikitext:
        return None

    redirect_match = _REDIRECT_RE.match(wikitext)
    if redirect_match:
        wikitext = _fetch_wikitext(redirect_match.group(1).strip()) or wikitext

    match = _INFOBOX_IMAGE_RE.search(wikitext)
    if match:
        return match.group(1).strip()

    disambig_target = _first_wikilink_starting_with(wikitext, page_title)
    if not disambig_target or disambig_target.lower() == page_title.lower():
        return None
    disambig_wikitext = _fetch_wikitext(disambig_target)
    if not disambig_wikitext:
        return None
    match = _INFOBOX_IMAGE_RE.search(disambig_wikitext)
    return match.group(1).strip() if match else None


def _fetch_and_save(filename: str) -> None:
    url = ICON_PATH_BASE + "/" + urllib.parse.quote(filename)
    try:
        try:
            data = _fetch_wiki_bytes(url)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            # Cache the resolved image under the ORIGINALLY requested filename,
            # since callers only know the guessed name; later requests then
            # resolve from disk without repeating the lookup.
            base_title = re.sub(r"\.(png|gif|jpe?g)$", "", filename, flags=re.IGNORECASE)
            fallback_name = _first_infobox_image(base_title)
            if not fallback_name:
                raise
            fallback_url = ICON_PATH_BASE + "/" + urllib.parse.quote(fallback_name)
            data = _fetch_wiki_bytes(fallback_url)
        # Write-then-rename: os.replace is atomic on POSIX, so readers never see
        # a half-written file.
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
    """Returns the in-flight Future for this icon (joining an existing fetch), or
    starts a new one. Returns None, without touching the executor, if it
    failed within _FAILURE_BACKOFF_SECONDS.
    """
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
    """Used by the /icon-cache/{filename} route (app/main.py): returns a path to
    serve, fetching first if needed, or None if the icon cannot be served
    (invalid name, or a failed/timed-out fetch with nothing on disk). The
    route turns None into a 404 and the frontend hides the broken <img>.
    """
    filename = _safe_filename(icon_filename)
    if not filename:
        return None
    path = _cached_path(filename)
    have_file = os.path.isfile(path)
    if _is_fresh(filename):
        return path
    future = _get_or_start_fetch(filename)
    if have_file:
        # Serve what is on disk; a weekly refresh continues in the background.
        return path
    if future is None:
        # Nothing on disk and a recent failure suppressed a retry: 404 until the
        # back-off passes.
        return None
    try:
        future.result(timeout=_WAIT_FOR_FRESH_SECONDS)
    except Exception:  # noqa: BLE001 -- includes the fetch's own failure and a timed-out wait alike
        pass
    return path if os.path.isfile(path) else None

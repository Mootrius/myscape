"""Postgres-backed cache for wiki-sourced icon images.

Used for NPC/event portraits (npc_icon_url in app/loot.py; there is no numeric
NPC id to use an id-keyed CDN) and as the last-resort fallback for rare recipe
items with no known id (_wiki_icon_url in app/purchase_goals.py). Item icons
otherwise come from RuneLite's CDN.

Why cache: the wiki's Special:FilePath URL is the first of two redirects, and
both hops are `cache-control: private, must-revalidate, max-age=0`, so
hotlinking re-hits the wiki twice per icon per page load and trips Cloudflare
rate limiting. This module fetches the image once server-side and serves it
under a same-origin /icon-cache/<filename> URL.

Storage: the icon_cache_entries table (IconCacheEntry, app/models.py), with a
small in-process LRU in front of it. It lives in Postgres rather than on a
Render persistent disk because a disk turns off zero-downtime deploys (the old
instance has to stop before the new one starts, which is what showed visitors
Render's 502 page on every push); see render.yaml.

Freshness: a cached icon is kept indefinitely. It is only re-fetched when
REFRESH_ICONS_FETCHED_BEFORE (below) is moved past the time it was fetched, so
refreshing the art means bumping that date and deploying.

Lazy, not cron-driven: the service is a single Render web process with no
worker, so the /icon-cache/{filename} route (app/routers/site.py) does a cheap
lookup and hands missing (or, after a bump of that date, outdated) icons to a
bounded background thread pool. The
pool's threads open their own DB sessions.

Only a request with nothing cached waits (briefly) on a fetch; outdated icons
are served immediately while refreshing in the background. Letting the browser
hotlink the wiki on a miss would bypass the pool's throttling and cause
request bursts.

Guessed "<Name>.png" files can 404 permanently (multi-form bosses, names that
are redirects/disambiguation pages); _first_infobox_image falls back to the
page's infobox image and caches it under the originally guessed filename.
"""
import hashlib
import json
import logging
import mimetypes
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Optional

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import IconCacheEntry

logger = logging.getLogger(__name__)

# Duplicated from purchase_goals.py (USER_AGENT / ICON_PATH_BASE); keep in sync.
USER_AGENT = "myscape.io/1.0 (Purchase Goals; contact: chandler@myscape.io)"
ICON_PATH_BASE = "https://oldschool.runescape.wiki/w/Special:FilePath"
WIKI_API_BASE = "https://oldschool.runescape.wiki/api.php"

# Every icon fetched before this moment is re-fetched (lazily, on its next
# view, serving the old picture meanwhile); anything fetched after it is kept
# forever. Move it to "now" and deploy to refresh all NPC/event and diary icons
# from the wiki, e.g. after a game update changes their art.
REFRESH_ICONS_FETCHED_BEFORE = datetime(2026, 10, 1, tzinfo=timezone.utc)

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

# Icons kept in process memory (a few KB each), so a page of tiles does not
# make one DB round trip per tile. Least recently used goes first.
_MEMORY_MAX_ENTRIES = 256

_lock = Lock()
_in_flight: Dict[str, Future] = {}
_recent_failures: Dict[str, float] = {}
_memory: "OrderedDict[str, CachedIcon]" = OrderedDict()


@dataclass(frozen=True)
class CachedIcon:
    """One cached image, as the route serves it."""

    data: bytes
    content_type: str
    fetched_at: datetime  # timezone-aware

    @property
    def etag(self) -> str:
        return '"' + hashlib.sha1(self.data).hexdigest()[:20] + '"'


def _safe_filename(icon_filename: Optional[str]) -> Optional[str]:
    """Rejects anything that is not a plain file name (no "/" or ".."). Names
    are only ever table keys now, but this keeps the URL space tidy and the
    old traversal guarantee.
    """
    if not icon_filename:
        return None
    if "/" in icon_filename or "\\" in icon_filename or icon_filename in (".", ".."):
        return None
    return icon_filename


def _is_fresh(icon: CachedIcon) -> bool:
    return icon.fetched_at >= REFRESH_ICONS_FETCHED_BEFORE


def _sniff_content_type(data: bytes, filename: str) -> str:
    """The wiki's image type from its magic bytes (the infobox fallback can be
    a different format than the guessed filename), else from the filename.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _aware_utc(value: datetime) -> datetime:
    # SQLite (local/dev) drops tzinfo on DateTime(timezone=True) columns.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _memory_get(filename: str) -> Optional[CachedIcon]:
    with _lock:
        icon = _memory.get(filename)
        if icon is not None:
            _memory.move_to_end(filename)
        return icon


def _memory_put(filename: str, icon: CachedIcon) -> None:
    with _lock:
        _memory[filename] = icon
        _memory.move_to_end(filename)
        while len(_memory) > _MEMORY_MAX_ENTRIES:
            _memory.popitem(last=False)


def _db_get(filename: str) -> Optional[CachedIcon]:
    db = SessionLocal()
    try:
        row = db.get(IconCacheEntry, filename)
        if row is None:
            return None
        return CachedIcon(bytes(row.data), row.content_type, _aware_utc(row.fetched_at))
    finally:
        db.close()


def _db_save(filename: str, icon: CachedIcon) -> None:
    """Insert or replace the row. A concurrent insert of the same key (two
    workers, or a retry) loses the race at commit; the second attempt then
    finds the row and updates it.
    """
    for attempt in range(2):
        db = SessionLocal()
        try:
            row = db.get(IconCacheEntry, filename)
            if row is None:
                row = IconCacheEntry(filename=filename)
                db.add(row)
            row.content_type = icon.content_type
            row.data = icon.data
            row.fetched_at = icon.fetched_at
            db.commit()
            return
        except IntegrityError:
            db.rollback()
            if attempt:
                raise
        finally:
            db.close()


def _lookup(filename: str) -> Optional[CachedIcon]:
    """Memory first, then Postgres. A database error counts as a miss, so a
    DB hiccup cannot turn into a broken page (the frontend hides a 404 <img>).
    """
    icon = _memory_get(filename)
    if icon is not None:
        return icon
    try:
        icon = _db_get(filename)
    except Exception:  # noqa: BLE001 -- best-effort cache
        logger.warning("icon cache read failed for %s", filename, exc_info=True)
        return None
    if icon is not None:
        _memory_put(filename, icon)
    return icon


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
            # resolve from the cache without repeating the lookup.
            base_title = re.sub(r"\.(png|gif|jpe?g)$", "", filename, flags=re.IGNORECASE)
            fallback_name = _first_infobox_image(base_title)
            if not fallback_name:
                raise
            fallback_url = ICON_PATH_BASE + "/" + urllib.parse.quote(fallback_name)
            data = _fetch_wiki_bytes(fallback_url)
        icon = CachedIcon(data, _sniff_content_type(data, filename), datetime.now(timezone.utc))
        _db_save(filename, icon)
        _memory_put(filename, icon)
        with _lock:
            _recent_failures.pop(filename, None)
    except Exception:  # noqa: BLE001 -- best-effort cache; a failed fetch (or save) just leaves nothing new cached for this icon
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


def ensure_cached_icon(icon_filename: Optional[str]) -> Optional[CachedIcon]:
    """Used by the /icon-cache/{filename} route (app/routers/site.py): returns
    the icon to serve, fetching first if needed, or None if it cannot be
    served (invalid name, or a failed/timed-out fetch with nothing cached).
    The route turns None into a 404 and the frontend hides the broken <img>.
    """
    filename = _safe_filename(icon_filename)
    if not filename:
        return None
    icon = _lookup(filename)
    if icon is not None and _is_fresh(icon):
        return icon
    future = _get_or_start_fetch(filename)
    if icon is not None:
        # Serve what is cached; a refresh continues in the background.
        return icon
    if future is None:
        # Nothing cached and a recent failure suppressed a retry: 404 until
        # the back-off passes.
        return None
    try:
        future.result(timeout=_WAIT_FOR_FRESH_SECONDS)
    except Exception:  # noqa: BLE001 -- includes the fetch's own failure and a timed-out wait alike
        pass
    return _lookup(filename)

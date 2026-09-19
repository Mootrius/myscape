"""Local, weekly-refreshed disk cache for wiki-sourced icon images.

Every ITEM icon in this app moved off this module -- item_icon_url
(app/purchase_goals.py) now hits RuneLite's own static icon CDN
directly by real numeric item id, a real CDN with none of the problems
described below, so there's nothing left for this module to
fetch-and-cache for items any more (see that function's own comment
for the switch and why). What's left, and the reason this module still
exists at all:

1. NPC/event portraits for Loot Tracker (npc_icon_url in app/loot.py)
   -- there's no numeric NPC id anywhere in this app's data model (see
   npc_hide_key's own comment there) for an id-keyed CDN to serve those
   from at all, so a guessed wiki filename is still the only option.
2. The genuinely rare combination-item name that resolves to a real id
   neither by name nor by icon filename in app/item_ids.py's two
   snapshots (_untradeable_item_icon's own last-resort fallback in
   app/purchase_goals.py, via _wiki_icon_url) -- a small handful of
   app/recipes.py's ~1200 known recipes at last count (event
   cosmetics, furniture, and the like with no real infobox id on file
   at all), now that the icon-filename snapshot resolves the ~190
   cosmetic colour variants (Crystal armour, Bow of Faerdhinen,
   Graceful, and friends) that used to fall all the way through to
   here.

Both still need exactly the machinery this module was built for in the
first place: item_icon_url (app/purchase_goals.py) used to hand the
browser a direct hotlink straight to the wiki's
Special:FilePath/<name>.png for every single icon on every single page
load. That URL isn't the image itself -- it's the first of two
redirects (FilePath -> Special:Redirect/file/... -> the actual
/images/....png?<hash>), and the wiki marks BOTH of those redirect hops
`cache-control: private, must-revalidate, max-age=0` -- never
cacheable, always re-fetched -- even though the final image is itself
served with `cache-control: public, max-age=31536000, immutable` once
you reach it. With dozens of icons on a single Possessions Monitoring
or Loot Tracker page, every refresh was re-hitting the wiki TWICE per
icon just to get redirected to the exact same place as last time --
almost certainly what was tripping Cloudflare's rate limiting and
showing up as icons that stop loading. NPC portraits (and that rare
recipe fallback) still hit exactly that same redirect chain, so this
module's whole reason to exist is just as real for them as it used to
be for every item icon too.

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
for that one request rather than wait on the fetch -- item_icon_url (as
it worked back when everything, not just NPC portraits and the rare
recipe fallback, went through this module) handed the browser the raw
wiki URL for anything not already cached and fresh, on the theory that
a request should never block on a network fetch. That's true for the
*page* request, but every one of these is its own separate, already-
async, already-lazy-loaded <img> request -- blocking one of THOSE for a
few seconds costs nothing a page visitor would notice, and not blocking
it meant every icon miss became a direct, un-throttled browser-to-wiki
request instead. Possessions Monitoring used to be the extreme case
here -- by far the widest, most varied set of icons any page ever
showed, since it's a player's whole bank/inventory rather than a short,
repeat-heavy list -- where a first view (or, without ICON_CACHE_DIR
pointed at a persistent disk, the first view after any redeploy) could
easily have had dozens of icons never fetched before, all at once, all
completely bypassing this module's own 4-at-a-time throttling and
racing the browser straight at the wiki in parallel: exactly the
rate-limit-tripping request burst this cache exists to prevent, just
moved from "us re-fetching" to "the browser fetching directly" instead.
That's exactly the failure mode Possessions Monitoring's own icons no
longer have any exposure to at all now that they're CDN-direct, but the
same reasoning is still live for a Loot Tracker page spanning a long
time range with dozens of distinct NPCs never portrayed before.

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

A guessed "<Name>.png" can also 404 for a reason no amount of
retrying/backoff fixes: some NPCs -- bosses with multiple combat forms
especially, like the Alchemical Hydra's four elemental phases -- have
no single canonical portrait under that name at all, only per-version
ones the wiki's own infobox lists as image1/image2/etc. See
_first_infobox_image below: rather than 404ing outright on one of
these, _fetch_and_save now falls back to asking the wiki's own
infobox wikitext which image it lists first, and caches THAT under
the originally-guessed filename -- so this lookup only ever happens
once per NPC (whatever fetch actually succeeds gets written to the
same cache path future requests already check first), and it's a
general fallback rather than a hydra-specific patch, so any other NPC
hitting the same multi-version-portrait issue self-heals the same way
without needing its own fix.
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

# Duplicated from purchase_goals.py's own USER_AGENT/ICON_PATH_BASE
# rather than imported -- purchase_goals.py has no reason to import
# anything back from this module any more (see item_icon_url's own
# comment). Keep these two in sync with purchase_goals.py if they ever
# change.
USER_AGENT = "myscape.io/1.0 (Purchase Goals; contact: chandler@myscape.io)"
ICON_PATH_BASE = "https://oldschool.runescape.wiki/w/Special:FilePath"
# Only reached when a guessed filename 404s -- see _first_infobox_image.
WIKI_API_BASE = "https://oldschool.runescape.wiki/api.php"

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


def _fetch_wiki_bytes(url: str) -> bytes:
    """The actual GET, shared by the direct guess and the infobox
    fallback below -- same content-type check either way, since a
    dead-end redirect chain can still come back 200 with an HTML error
    page rather than a real 404."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
        content_type = resp.headers.get("Content-Type", "")
        data = resp.read()
    if not content_type.startswith("image/") or not data:
        raise ValueError(f"unexpected icon response ({content_type!r}, {len(data)} bytes)")
    return data


# Matches an infobox's `image`/`image1`/`image2`/... parameter line and
# captures the filename inside its [[File:...]] link -- e.g.
# "|image1 = [[File:Alchemical Hydra (serpentine).png|x300px]]" captures
# "Alchemical Hydra (serpentine).png". `search` (not `findall`) so this
# naturally stops at the first one it finds, which for a multi-version
# infobox is always image1 -- these templates list their versions in
# order, image1 first -- and for a single-version one is just `image`.
_INFOBOX_IMAGE_RE = re.compile(
    r"\|\s*image\d*\s*=\s*\[\[\s*File\s*:\s*([^|\]]+?)\s*(?:\|[^\]]*)?\]\]",
    re.IGNORECASE,
)


def _first_infobox_image(page_title: str) -> Optional[str]:
    """Only called once a guessed "<page_title>.png" has already 404d.
    Looks up that wiki page's own infobox wikitext and returns
    whichever image it lists first -- i.e. whatever the wiki itself
    treats as that NPC's primary/first version, the same one a visitor
    landing on the page would see first. None if the page has no
    infobox image at all (a genuinely missing/renamed icon, not the
    multiple-combat-forms case this exists for) or can't be reached."""
    url = (
        WIKI_API_BASE
        + "?action=parse&prop=wikitext&format=json&page="
        + urllib.parse.quote(page_title)
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
        payload = json.loads(resp.read())
    wikitext = (payload.get("parse") or {}).get("wikitext", {}).get("*")
    if not wikitext:
        return None
    match = _INFOBOX_IMAGE_RE.search(wikitext)
    return match.group(1).strip() if match else None


def _fetch_and_save(filename: str) -> None:
    url = ICON_PATH_BASE + "/" + urllib.parse.quote(filename)
    try:
        try:
            data = _fetch_wiki_bytes(url)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            # See _first_infobox_image's own docstring. Cache whatever
            # this resolves to under the ORIGINALLY-requested filename
            # (not the resolved one) -- every other piece of this
            # module, and the /icon-cache/<filename> route calling it,
            # only ever knows the guessed name, so this is what makes
            # future requests for this same NPC keep resolving straight
            # from disk without ever repeating this lookup.
            base_title = re.sub(r"\.(png|gif|jpe?g)$", "", filename, flags=re.IGNORECASE)
            fallback_name = _first_infobox_image(base_title)
            if not fallback_name:
                raise
            fallback_url = ICON_PATH_BASE + "/" + urllib.parse.quote(fallback_name)
            data = _fetch_wiki_bytes(fallback_url)
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

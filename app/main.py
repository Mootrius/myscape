"""myscape's web app: a placeholder landing page, health checks, and the
early account system (website signup/login, RuneLite plugin account
linking) -- see README.md for how the pieces fit together.
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# Without this, the root logger defaults to WARNING-and-up with no
# handler attached, which silently drops every log.info() call in the
# app (e.g. app/email_client.py's "RESEND_API_KEY not set -- would have
# emailed ..." line) -- they'd never reach Render's log viewer at all,
# regardless of whether that's actually what happened, which makes
# exactly the kind of "why didn't this email send" question this app
# needs to answer unanswerable from the logs alone. INFO is still well
# below DEBUG, so this doesn't turn on noisy per-request debug output.
logging.basicConfig(level=logging.INFO)

from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exception_handlers import http_exception_handler as _default_http_exception_handler
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import (
    get_current_game_account_from_api_key,
    get_current_verified_game_account_from_session,
    get_optional_current_account_from_session,
    get_optional_current_player_view_from_session,
)
from app.database import SessionLocal, get_db
from app.icon_cache import ensure_cached_icon_path
from app.limiter import limiter
from app.loot import build_loot_state, kc_counts_by_player, parse_loot_range_bound, resolve_range, set_item_hidden, set_npc_hidden, sync_loot_events
from app.item_ids import find_item_ids
from app.npc_names import search_npc_names
from app.quest_names import search_quest_names
from app.mindmaps import (
    add_node,
    add_shared_child,
    build_mindmaps_state,
    delete_node,
    new_root_node,
    replace_nodes,
    set_node_goal,
    update_node,
)
from app.models import (
    BankItem,
    BoatCargoItem,
    EquipmentItem,
    ForestryKitItem,
    GameAccount,
    GearSetup,
    HuntsmansKitItem,
    InventoryItem,
    LootingBagItem,
    MasterScrollBookItem,
    MindMap,
    PinnedPossessionItem,
    PohItem,
    PossessionTracker,
    PossessionView,
    PotionStorageItem,
    RunePouchItem,
    SeedBoxItem,
    SeedVaultItem,
    TackleBoxItem,
)
from app.pages import (
    _SITE_URL,
    PlayerView,
    render_account,
    render_dashboard,
    render_forgot_password,
    render_goal_tracking,
    render_landing,
    render_login,
    render_loot_tracker,
    render_mindmaps,
    render_not_found,
    render_possessions,
    render_purchase_goals,
    render_reset_password,
    render_signup,
    render_verify_email,
    render_verify_email_required,
)
from app.possessions import (
    build_possession_views,
    build_possessions_summary,
    build_trackers_state,
    hidden_storage_keys,
    next_possession_view_sort_order,
    next_sort_order,
    pinned_item_ids,
    resolve_item_display,
    search_trackable_items,
    set_storage_hidden,
)
from app.purchase_goals import (
    COINS_ITEM_ID,
    build_owned_pools,
    build_purchase_goals_state,
    get_mapping,
    has_derived_price,
    search_items,
)
from app.recipes import expand_recipe_components
from app.routers import auth, linking
from app.schemas import (
    AddMindMapNodeRequest,
    AddMindMapSharedChildRequest,
    BankOut,
    BankItemOut,
    BankSyncRequest,
    BankSyncResponse,
    BoatCargoOut,
    BoatCargoItemOut,
    BoatCargoSyncRequest,
    BoatCargoSyncResponse,
    CreateGearSetupRequest,
    CreateMindMapRequest,
    DiariesSyncRequest,
    DiariesSyncResponse,
    EquipmentOut,
    EquipmentItemOut,
    EquipmentSyncRequest,
    EquipmentSyncResponse,
    EQUIPMENT_SLOTS,
    ForestryKitOut,
    ForestryKitItemOut,
    ForestryKitSyncRequest,
    ForestryKitSyncResponse,
    GEAR_SETUP_EQUIPMENT_SLOTS,
    HideLootItemRequest,
    HideLootNpcRequest,
    HuntsmansKitOut,
    HuntsmansKitItemOut,
    HuntsmansKitSyncRequest,
    HuntsmansKitSyncResponse,
    INVENTORY_SIZE,
    InventoryOut,
    InventoryItemOut,
    InventorySyncRequest,
    InventorySyncResponse,
    ItemSearchResponse,
    LootingBagOut,
    LootingBagItemOut,
    LootingBagSyncRequest,
    LootingBagSyncResponse,
    LootSyncRequest,
    LootSyncResponse,
    MasterScrollBookOut,
    MasterScrollBookItemOut,
    MasterScrollBookSyncRequest,
    MasterScrollBookSyncResponse,
    MoveGearSlotItemRequest,
    NpcSearchResponse,
    PlayerOut,
    PohOut,
    PohItemOut,
    PohSyncRequest,
    PohSyncResponse,
    POSSESSION_STORAGE_KEYS,
    PossessionTrackerIn,
    PossessionTrackerUpdate,
    PossessionViewSaveRequest,
    PossessionViewUpdateRequest,
    PotionStorageOut,
    PotionStorageItemOut,
    PotionStorageSyncRequest,
    PotionStorageSyncResponse,
    QuestSearchResponse,
    QuestsSyncRequest,
    QuestsSyncResponse,
    RenameGearSetupRequest,
    RenameMindMapRequest,
    ReplaceMindMapNodesRequest,
    RunePouchOut,
    RunePouchItemOut,
    RunePouchSyncRequest,
    RunePouchSyncResponse,
    SeedBoxOut,
    SeedBoxItemOut,
    SeedBoxSyncRequest,
    SeedBoxSyncResponse,
    SeedVaultOut,
    SeedVaultItemOut,
    SeedVaultSyncRequest,
    SeedVaultSyncResponse,
    SetGearSetupIconRequest,
    SetGearSetupOrderRequest,
    SetGearSlotRequest,
    SetPossessionViewOrderRequest,
    SetStillToPurchaseOrderRequest,
    SetStillToPurchaseSortRequest,
    SetMindMapNodeGoalRequest,
    SkillsSyncRequest,
    SkillsSyncResponse,
    SyncStatusOut,
    TackleBoxOut,
    TackleBoxItemOut,
    TackleBoxSyncRequest,
    TackleBoxSyncResponse,
    UpdateMindMapNodeRequest,
)

# A defensive upper bound, not a real OSRS limit -- the largest bank
# ever seen is nowhere near this, so the only way a sync would hit it is
# a malformed or buggy client, and rejecting that outright beats quietly
# accepting and storing whatever it sent.
MAX_BANK_ITEMS = 2000
# The inventory and equipment containers are fixed-size (28 slots, 11
# slots), so unlike the bank there's a real upper bound on distinct
# items in one sync -- these are that exact size, not a round-number
# guess, so anything over is definitely malformed.
MAX_INVENTORY_ITEMS = INVENTORY_SIZE
MAX_EQUIPMENT_ITEMS = len(EQUIPMENT_SLOTS)
# Potion Storage supports a few dozen distinct potion types, and the
# plugin reports at most two rows per type (a full-dose count plus one
# leftover partial-dose item -- see MyscapePlugin#readPotionStorageItems
# in the Mootrius/myscape-plugin repo), so this is a generous multiple
# of the real ceiling, not a round-number guess either.
MAX_POTION_STORAGE_ITEMS = 200
# A Rune Pouch (regular or Divine) has at most 6 slots (see
# MyscapePlugin's RUNE_POUCH_TYPE_VARBITS in the Mootrius/myscape-plugin
# repo, read defensively at 6 even though only 3-4 are used in-game
# today), each holding a single rune type -- so 6 is the real ceiling,
# not a round-number guess. Left with a little headroom in case Jagex
# ever ships a bigger pouch before this constant is revisited.
MAX_RUNE_POUCH_ITEMS = 10
# The Seed Vault holds every tradeable seed in the game (a few dozen
# distinct types), a generous multiple of the real ceiling, not a
# round-number guess, same spirit as MAX_POTION_STORAGE_ITEMS.
MAX_SEED_VAULT_ITEMS = 200
# The Looting Bag holds up to 28 distinct item stacks (the same size as
# the main inventory, since it's filled the same way), so this mirrors
# MAX_INVENTORY_ITEMS's own reasoning rather than being a fresh guess.
MAX_LOOTING_BAG_ITEMS = INVENTORY_SIZE
# A Tackle Box only ever stores 35 distinct kinds of item (a fixed,
# documented ceiling, not a guess) -- a little headroom past that in
# case a future update raises it, same spirit as MAX_RUNE_POUCH_ITEMS.
MAX_TACKLE_BOX_ITEMS = 50
# The whole PoH Costume Room -- every piece of furniture combined into
# one sync (see PohItem's docstring in app/models.py for why it's one
# unified sync rather than six). Sized generously for the sum of what
# those six used to allow separately: a few dozen set pieces each for
# Magic Wardrobe/Armour Case/Fancy Dress Box, every non-tradeable
# holiday reward for the Toy Box (more accumulate every year), the
# hundreds of distinct clue rewards across all six Treasure Trail tiers
# for the Treasure Chest, and every cape the game has for the Cape
# Rack -- generous headroom past that combined real total, not a
# round-number guess.
MAX_POH_ITEMS = 1500
# The Forestry Kit holds a handful of Forestry event consumables at
# most -- generous headroom past that, same spirit as
# MAX_RUNE_POUCH_ITEMS, not a tight fit.
MAX_FORESTRY_KIT_ITEMS = 50
# The Master Scroll Book holds "every type of teleport scroll" (OSRS
# Wiki) -- dozens of distinct scroll types across every minigame and
# Treasure Trail reward, not hundreds -- generous headroom past that,
# same spirit as MAX_SEED_VAULT_ITEMS.
MAX_MASTER_SCROLL_BOOK_ITEMS = 150
# The Seed Box holds seeds of six different types (OSRS Wiki) --
# generous headroom past that fixed ceiling, same spirit as
# MAX_RUNE_POUCH_ITEMS, in case a future update raises it.
MAX_SEED_BOX_ITEMS = 20
# The Huntsman's Kit holds a handful of creature-specific Hunter
# equipment sets -- generous headroom past that, same spirit as
# MAX_FORESTRY_KIT_ITEMS, not a tight fit.
MAX_HUNTSMANS_KIT_ITEMS = 50
# One boat's cargo hold capacity scales with its wood tier (Basic
# through Ironwood -- see the OSRS Wiki's "Cargo hold" article), but
# even the biggest tier is nowhere near this -- generous headroom past
# the real ceiling, same spirit as MAX_SEED_VAULT_ITEMS, per sync (this
# bounds ONE boat slot's own request -- see sync_boat_cargo below,
# and BoatCargoItem's docstring in app/models.py -- not a combined
# total across all five of a player's boats).
MAX_BOAT_CARGO_ITEMS = 100
# There are exactly 24 real OSRS skills (see SKILL_NAMES in
# app/mindmaps.py) -- a real ceiling, not a guess.
MAX_SKILLS_PER_SYNC = 24
# A defensive upper bound on completed quests/miniquests -- OSRS has
# nowhere near this many, so the only way a sync would hit it is a
# malformed/buggy client.
MAX_QUESTS_PER_SYNC = 1000
# There are exactly 12 real OSRS achievement diary areas (see
# DIARY_AREAS in app/mindmaps.py) -- a real ceiling, not a guess.
MAX_DIARY_AREAS_PER_SYNC = 12
# The plugin syncs one loot event immediately as it happens (see
# MyscapePlugin#onLootReceived), so a real sync is always exactly 1 --
# this is a defensive upper bound against a malformed/buggy client
# trying to batch an unreasonable number into one request, not a real
# expected size.
MAX_LOOT_EVENTS_PER_SYNC = 50

SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY")
if not SESSION_SECRET_KEY:
    raise RuntimeError(
        "SESSION_SECRET_KEY is not set. Generate one (e.g. `python -c "
        "'import secrets; print(secrets.token_hex(32))'`) and set it as an "
        "environment variable -- see .env.example. On Render, render.yaml "
        "already has it set to auto-generate and persist a value."
    )

app = FastAPI(title="myscape")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(StarletteHTTPException)
async def _styled_not_found_handler(request: Request, exc: StarletteHTTPException):
    """Swaps in render_not_found's styled page for a 404 hit while
    browsing the site itself -- everywhere else (every /api/* and
    /static/* response, and every non-404 status anywhere) keeps
    FastAPI's normal {"detail": ...} JSON body untouched, since the
    site's own JS (describeError() in app/pages.py) parses that JSON
    for every form's error message and would break if it got HTML
    back instead.

    Registered on Starlette's own HTTPException, not FastAPI's --
    fastapi.HTTPException is a *subclass* of it, and a genuinely
    unmatched route (someone hitting a URL that doesn't exist at all)
    is raised internally by Starlette's router as the base class, not
    the subclass. A handler registered on the subclass alone silently
    never catches that case -- it only ever saw the fastapi.HTTPException
    instances explicitly `raise`d elsewhere in this file. Registering on
    the base class here still catches both: Starlette looks up handlers
    by walking the raised exception's MRO, and every fastapi.HTTPException
    instance's MRO includes this base class too."""
    if exc.status_code == status.HTTP_404_NOT_FOUND and not request.url.path.startswith(("/api/", "/static/")):
        # Exception handlers aren't routed through FastAPI's dependency
        # injection, so this can't just take a
        # player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)
        # parameter the way every other page route in this file does --
        # open and close a DB session by hand instead, purely to get the
        # header nav's Dashboard/Log out state right for a signed-in
        # visitor who hits a broken link. Calling both dependency
        # functions directly like this means their own `account`/`db`
        # *Depends(...)* defaults never fire -- every argument has to be
        # passed explicitly, account included, or it comes through as
        # the literal Depends(...) marker object instead of an Account
        # (or None), and the get_optional_current_player_view_from_session
        # call below blows up trying to use it (was exactly this bug,
        # every 404 on the live site 500ing instead, before this got
        # fixed -- see the multi-account docs for how it was caught).
        db = SessionLocal()
        try:
            account = get_optional_current_account_from_session(request, db)
            player = get_optional_current_player_view_from_session(request, db, account)
        finally:
            db.close()
        return HTMLResponse(render_not_found(player), status_code=status.HTTP_404_NOT_FOUND)
    return await _default_http_exception_handler(request, exc)
# Session cookies back website login (see app/auth.py). `https_only` is on
# because myscape.io is HTTPS-only in production; if that ever gets in the
# way of local http://localhost testing, override it with an env var --
# don't just delete it.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    same_site="lax",
    https_only=os.environ.get("SESSION_COOKIE_HTTPS_ONLY", "true").lower() != "false",
    max_age=60 * 60 * 24 * 30,  # 30 days
)
app.include_router(auth.router)
app.include_router(linking.router)

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/icon-cache/{filename}")
def get_cached_icon(filename: str):
    """Serves a (possibly not-yet-fetched) wiki-sourced icon -- a
    dedicated route rather than folding this into the /static mount
    above so it can set its own long-lived Cache-Control, and so it can
    do more than a plain static-file lookup: ensure_cached_icon_path
    (app/icon_cache.py) is what actually fetches-and-caches an icon
    this is the first request for -- see that module's own top-of-file
    comment for why that fetch happens here, briefly blocking this one
    request, rather than falling back to letting the browser hit the
    wiki directly.

    Every ITEM icon in this app now bypasses this route entirely --
    item_icon_url (app/purchase_goals.py) hands those out as a direct
    RuneLite CDN URL instead (see that function's own comment). What's
    left hitting this route: NPC/event portraits for Loot Tracker
    (npc_icon_url in app/loot.py, no numeric NPC id for that CDN to
    serve those from at all) and the rare combination-item name
    app/item_ids.py's snapshot doesn't cover under its exact stored
    spelling (_untradeable_item_icon's own last-resort fallback in
    app/purchase_goals.py).

    Re-validates the filename itself (no path traversal out of the
    cache directory) rather than trusting the URL alone."""
    path = ensure_cached_icon_path(filename)
    if not path:
        raise HTTPException(status_code=404)
    return FileResponse(path, headers={"Cache-Control": "public, max-age=604800, immutable"})


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@app.on_event("startup")
def on_startup():
    # Brings the database up to the latest schema by applying whichever
    # of migrations/versions/*.py it hasn't seen yet (see README.md's
    # "Database schema changes") -- the Alembic equivalent of the old
    # Base.metadata.create_all() + sync_missing_columns() pair this
    # replaced, which is also why this still runs unconditionally on
    # every startup rather than as a separate deploy step: it's the
    # smallest change from the previous behavior, and safe here since
    # this service only ever runs as a single instance. The very first
    # migration is written defensively (skips any table that already
    # exists) specifically so this needs no one-time manual step to
    # tell Alembic that production's existing tables are already
    # "migrated" -- see migrations/versions/5cf359e6d5b1_initial_schema.py.
    alembic_cfg = Config(os.path.join(_REPO_ROOT, "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


@app.get("/", response_class=HTMLResponse)
def root(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    # Used to redirect a logged-in player straight to /dashboard, on the
    # theory that they'd have no reason to want the landing page once
    # they're already a user -- but that also meant the header's own
    # "myscape" logo link (plain href="/", same as it's always been)
    # could never actually take a logged-in player back to the landing
    # page itself, only bounce them right back to whatever dashboard
    # page they were already on. render_landing is player-aware (see
    # its own docstring) specifically so it can render properly either
    # way now.
    return render_landing(player)


# The disallowed paths here are every page _shell() itself renders
# noindex by default (see that function's own comment in app/pages.py)
# -- kept as an explicit list rather than trying to derive one from the
# route table at import time, since a robots.txt a crawler can't parse
# is worse than one that's occasionally one route behind if a new page
# is ever added without updating both places. /dashboard alone covers
# every /dashboard/* tool page (Purchase Goals, Loot Tracker, Mindmaps,
# Storages Viewer) as a prefix match, same as the other entries here
# cover their own sub-paths. /api/ is blocked outright -- none of it is
# a page a crawler could render anyway, and there's no reason to spend
# a crawl budget probing it.
_ROBOTS_TXT = """User-agent: *
Allow: /
Disallow: /dashboard
Disallow: /account
Disallow: /login
Disallow: /signup
Disallow: /forgot-password
Disallow: /reset-password
Disallow: /verify-email
Disallow: /verify-email-required
Disallow: /api/

Sitemap: """ + _SITE_URL + """/sitemap.xml
"""


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt():
    return _ROBOTS_TXT


# One entry -- the landing page is the only URL on the whole site
# _shell() ever renders indexable (see its own noindex/canonical_path
# comment), so it's also the only one worth listing here. A sitemap
# full of noindexed pages wouldn't help those pages get indexed (the
# noindex tag itself always wins) and would just be one more thing to
# keep in sync with the route table for no benefit.
_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>""" + _SITE_URL + """/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
"""


@app.get("/sitemap.xml")
def sitemap_xml():
    return Response(content=_SITEMAP_XML, media_type="application/xml")


@app.get("/signup", response_class=HTMLResponse)
def signup_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if player:
        return RedirectResponse("/dashboard", status_code=302)
    return render_signup()


@app.get("/login", response_class=HTMLResponse)
def login_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if player:
        return RedirectResponse("/dashboard", status_code=302)
    return render_login()


@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if player:
        return RedirectResponse("/dashboard", status_code=302)
    return render_forgot_password()


@app.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    # No redirect-if-logged-in here, unlike the other auth pages -- the
    # token itself is read client-side from the URL's query string (see
    # render_reset_password's own script), so there's no server-side
    # reason to gate this on session state, and someone already logged
    # in in one tab may still be legitimately using a reset link they
    # requested (or were sent) in another.
    return render_reset_password()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_dashboard(player)


@app.get("/account", response_class=HTMLResponse)
def account_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    # No email_verified_at gate here, unlike dashboard_page above --
    # render_account's own docstring covers why (log out, and fixing a
    # mistyped signup email in particular, both need to stay reachable
    # before verification).
    if not player:
        return RedirectResponse("/login", status_code=302)
    return render_account(player)


@app.get("/verify-email-required", response_class=HTMLResponse)
def verify_email_required_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if player.email_verified_at:
        # Nothing left to do here -- most likely they already verified
        # in another tab, or followed a bookmarked/stale link.
        return RedirectResponse("/dashboard", status_code=302)
    return render_verify_email_required(player)


@app.get("/verify-email", response_class=HTMLResponse)
def verify_email_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if player and player.email_verified_at:
        # Already verified in this session -- most likely they followed
        # a bookmarked/stale link, or already verified in another tab.
        # Nothing left for this page to do.
        return RedirectResponse("/dashboard", status_code=302)
    # No redirect-if-logged-out here, same reasoning as reset_password_page's
    # own comment -- the token itself is read client-side from the URL's
    # query string (see render_verify_email's own script), and someone
    # clicking a confirmation link from their email isn't necessarily still
    # in the same browser session (or any session at all) that signed up.
    # `player` is still passed through though (logged-in-but-unverified is
    # exactly the state this page is usually reached in), so the header nav
    # shows Dashboard/Log out rather than Log in/Sign up when applicable.
    return render_verify_email(player)


@app.get("/api/health")
def health():
    """Proves the app itself is up. Doesn't touch the database -- see
    /api/health/db for that -- so this stays fast and always answers even
    if the database is briefly unreachable."""
    return {"status": "ok"}


@app.get("/api/health/db")
def health_db(db: Session = Depends(get_db)):
    """Proves the app can actually reach and query the database -- the
    real end-to-end check for a first deploy."""
    player_count = db.execute(text("SELECT COUNT(*) FROM players")).scalar()
    return {"status": "ok", "playerCount": player_count}


@app.get("/api/players/me", response_model=PlayerOut)
def read_current_player(game_account: GameAccount = Depends(get_current_game_account_from_api_key)):
    """First real use of the API key auth: the plugin calls this (with
    its `Authorization: Bearer <key>` header) to confirm it's linked and
    see which player it's linked to.

    PlayerOut mixes identity (email) and game-data (runescape_name,
    account_hash) fields -- same conflation as app/routers/auth.py's own
    _player_out_for, which has the fuller explanation. Built by hand
    here (rather than just returning game_account) since email now
    lives on the separate Account row this GameAccount belongs to, not
    on GameAccount itself."""
    return PlayerOut(
        id=game_account.id,
        email=game_account.account.email,
        runescape_name=game_account.runescape_name,
        account_hash=game_account.account_hash,
    )


@app.post("/api/players/me/unlink", status_code=status.HTTP_204_NO_CONTENT)
def unlink_player(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_game_account_from_api_key)):
    """Called by the RuneLite plugin's "Unlink" button (API-key
    authenticated). See linking.revoke_link() for what this actually
    does and why POST /api/link/unlink there is this endpoint's
    session-authenticated counterpart, not a duplicate."""
    linking.revoke_link(db, game_account)


def _stamp_storage_synced(game_account: GameAccount, storage_key: str, now: datetime) -> None:
    """Records that `storage_key` (one of POSSESSION_STORAGE_KEYS) was
    just synced -- called from the bottom of every one of the twelve
    per-storage POST handlers below, right before their own db.commit()
    (storage_synced_at is a plain column on the same GameAccount row already
    being flushed, so this never needs a commit of its own). See
    GameAccount.storage_synced_at's own docstring in app/models.py for why
    this exists at all rather than just reading the item tables' own
    updated_at back.

    Reassigns the whole dict rather than mutating the existing one in
    place -- a JSONB column's SQLAlchemy tracking only notices a
    brand-new object assigned to it, not an in-place `dict[key] = ...`
    on the same object, so mutating in place would silently fail to
    persist."""
    game_account.storage_synced_at = {**(game_account.storage_synced_at or {}), storage_key: now.isoformat()}


@app.post("/api/players/me/bank", response_model=BankSyncResponse)
def sync_bank(
    payload: BankSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Called by the RuneLite plugin (API-key authenticated) whenever
    the bank interface is open and its contents settle after a change
    -- see MyscapeClient#syncBank in the Mootrius/myscape-plugin repo.
    Always a full replace, never a merge: every one of the player's
    existing bank_items rows is deleted and replaced with exactly what
    this request says, so an item that's been sold or withdrawn since
    the last sync disappears here too, the same way it disappeared from
    the actual bank (see BankItem's docstring in app/models.py for why
    that's the right model for this)."""
    if len(payload.items) > MAX_BANK_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_BANK_ITEMS}).",
        )

    db.query(BankItem).filter(BankItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(BankItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "bank", now)
    db.commit()

    return BankSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/bank", response_model=BankOut)
def read_bank(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The website's own read of the last-synced bank snapshot --
    session-authenticated (unlike the POST above), since it's the
    website reading this back, not the plugin writing it. Nothing in
    the UI surfaces this yet (Purchase Goals is still a placeholder
    card on /dashboard), but this is what that card will eventually
    read from."""
    items = db.query(BankItem).filter(BankItem.game_account_id == game_account.id).order_by(BankItem.item_id).all()
    updated_at = items[0].updated_at if items else None
    return BankOut(items=[BankItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/inventory", response_model=InventorySyncResponse)
def sync_inventory(
    payload: InventorySyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for the main
    28-slot inventory instead -- see MyscapeClient#syncInventory in the
    Mootrius/myscape-plugin repo. Full replace, never a merge."""
    if len(payload.items) > MAX_INVENTORY_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_INVENTORY_ITEMS}).",
        )

    db.query(InventoryItem).filter(InventoryItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(InventoryItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "inventory", now)
    db.commit()

    return InventorySyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/inventory", response_model=InventoryOut)
def read_inventory(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank above, for the
    inventory instead."""
    items = db.query(InventoryItem).filter(InventoryItem.game_account_id == game_account.id).order_by(InventoryItem.item_id).all()
    updated_at = items[0].updated_at if items else None
    return InventoryOut(items=[InventoryItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/equipment", response_model=EquipmentSyncResponse)
def sync_equipment(
    payload: EquipmentSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for worn
    equipment instead -- see MyscapeClient#syncEquipment in the
    Mootrius/myscape-plugin repo. Full replace, never a merge, keyed by
    slot rather than item id (EquipmentSyncRequest's own validator
    already rejects a duplicate slot within one sync -- see
    app/schemas.py)."""
    if len(payload.items) > MAX_EQUIPMENT_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_EQUIPMENT_ITEMS}).",
        )

    db.query(EquipmentItem).filter(EquipmentItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(EquipmentItem(
            game_account_id=game_account.id, slot=item.slot, item_id=item.item_id,
            item_name=item.item_name, quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "equipment", now)
    db.commit()

    return EquipmentSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/equipment", response_model=EquipmentOut)
def read_equipment(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank above, for worn
    equipment instead."""
    items = db.query(EquipmentItem).filter(EquipmentItem.game_account_id == game_account.id).order_by(EquipmentItem.slot).all()
    updated_at = items[0].updated_at if items else None
    return EquipmentOut(items=[EquipmentItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/potion-storage", response_model=PotionStorageSyncResponse)
def sync_potion_storage(
    payload: PotionStorageSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for the
    Player-Owned-House Potion Storage instead -- see
    MyscapeClient#syncPotionStorage in the Mootrius/myscape-plugin repo.
    Full replace, never a merge. Unlike bank/inventory/equipment,
    Potion Storage isn't an ItemContainer the plugin can just read
    directly -- see MyscapePlugin#readPotionStorageItems there for how
    it actually reads this -- but the resulting shape and this
    endpoint's contract are identical, so nothing here needs to know
    the difference. This is also what replaced the old "supplies"
    gear-slot flag: see PotionStorageItem's docstring in app/models.py
    for why that flag existed and why it's gone now."""
    if len(payload.items) > MAX_POTION_STORAGE_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_POTION_STORAGE_ITEMS}).",
        )

    db.query(PotionStorageItem).filter(PotionStorageItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(PotionStorageItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "potion_storage", now)
    db.commit()

    return PotionStorageSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/potion-storage", response_model=PotionStorageOut)
def read_potion_storage(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank above, for potion
    storage instead."""
    items = (
        db.query(PotionStorageItem)
        .filter(PotionStorageItem.game_account_id == game_account.id)
        .order_by(PotionStorageItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return PotionStorageOut(items=[PotionStorageItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/rune-pouch", response_model=RunePouchSyncResponse)
def sync_rune_pouch(
    payload: RunePouchSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for a Rune
    Pouch's contents instead -- see MyscapeClient#syncRunePouch in the
    Mootrius/myscape-plugin repo. Full replace, never a merge. Unlike
    bank/inventory/equipment, a Rune Pouch's contents aren't part of any
    ItemContainer the plugin can just read directly -- see
    MyscapePlugin#readRunePouchItems there for how it actually reads
    this (the pouch itself is one inventory item; what's stored inside
    it comes from a separate set of varbits) -- but the resulting shape
    and this endpoint's contract are identical, so nothing here needs to
    know the difference. Deliberately its own endpoint rather than
    folded into /inventory's payload: see RunePouchItem's docstring in
    app/models.py for why."""
    if len(payload.items) > MAX_RUNE_POUCH_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_RUNE_POUCH_ITEMS}).",
        )

    db.query(RunePouchItem).filter(RunePouchItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(RunePouchItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "rune_pouch", now)
    db.commit()

    return RunePouchSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/rune-pouch", response_model=RunePouchOut)
def read_rune_pouch(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank above, for the rune
    pouch instead."""
    items = (
        db.query(RunePouchItem)
        .filter(RunePouchItem.game_account_id == game_account.id)
        .order_by(RunePouchItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return RunePouchOut(items=[RunePouchItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/seed-vault", response_model=SeedVaultSyncResponse)
def sync_seed_vault(
    payload: SeedVaultSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for a
    Player-Owned-House Seed Vault's contents instead -- see
    MyscapeClient#syncSeedVault in the Mootrius/myscape-plugin repo and
    SeedVaultItem's docstring in app/models.py. Full replace, never a
    merge."""
    if len(payload.items) > MAX_SEED_VAULT_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_SEED_VAULT_ITEMS}).",
        )

    db.query(SeedVaultItem).filter(SeedVaultItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(SeedVaultItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "seed_vault", now)
    db.commit()

    return SeedVaultSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/seed-vault", response_model=SeedVaultOut)
def read_seed_vault(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank above, for the seed
    vault instead."""
    items = (
        db.query(SeedVaultItem)
        .filter(SeedVaultItem.game_account_id == game_account.id)
        .order_by(SeedVaultItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return SeedVaultOut(items=[SeedVaultItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/looting-bag", response_model=LootingBagSyncResponse)
def sync_looting_bag(
    payload: LootingBagSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for a Looting
    Bag's contents instead -- see MyscapeClient#syncLootingBag in the
    Mootrius/myscape-plugin repo and LootingBagItem's docstring in
    app/models.py. Full replace, never a merge."""
    if len(payload.items) > MAX_LOOTING_BAG_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_LOOTING_BAG_ITEMS}).",
        )

    db.query(LootingBagItem).filter(LootingBagItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(LootingBagItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "looting_bag", now)
    db.commit()

    return LootingBagSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/looting-bag", response_model=LootingBagOut)
def read_looting_bag(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank above, for the looting
    bag instead."""
    items = (
        db.query(LootingBagItem)
        .filter(LootingBagItem.game_account_id == game_account.id)
        .order_by(LootingBagItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return LootingBagOut(items=[LootingBagItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/tackle-box", response_model=TackleBoxSyncResponse)
def sync_tackle_box(
    payload: TackleBoxSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for a Tackle
    Box's contents instead -- see MyscapeClient#syncTackleBox in the
    Mootrius/myscape-plugin repo and TackleBoxItem's docstring in
    app/models.py. Full replace, never a merge."""
    if len(payload.items) > MAX_TACKLE_BOX_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_TACKLE_BOX_ITEMS}).",
        )

    db.query(TackleBoxItem).filter(TackleBoxItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(TackleBoxItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "tackle_box", now)
    db.commit()

    return TackleBoxSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/tackle-box", response_model=TackleBoxOut)
def read_tackle_box(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank above, for the Tackle
    Box instead."""
    items = (
        db.query(TackleBoxItem)
        .filter(TackleBoxItem.game_account_id == game_account.id)
        .order_by(TackleBoxItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return TackleBoxOut(items=[TackleBoxItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/poh", response_model=PohSyncResponse)
def sync_poh(
    payload: PohSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for the whole
    Player-Owned-House Costume Room instead -- see MyscapeClient#syncPoh
    in the Mootrius/myscape-plugin repo and PohItem's docstring in
    app/models.py for why this is one endpoint covering all six pieces
    of furniture rather than six separate ones, and why it's named
    "poh" rather than "costume-room". Full replace, never a merge."""
    if len(payload.items) > MAX_POH_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_POH_ITEMS}).",
        )

    db.query(PohItem).filter(PohItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(PohItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "poh", now)
    db.commit()

    return PohSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/poh", response_model=PohOut)
def read_poh(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank above, for the whole
    PoH Costume Room instead."""
    items = (
        db.query(PohItem)
        .filter(PohItem.game_account_id == game_account.id)
        .order_by(PohItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return PohOut(items=[PohItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/forestry-kit", response_model=ForestryKitSyncResponse)
def sync_forestry_kit(
    payload: ForestryKitSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for the
    Forestry Kit's contents instead -- see
    MyscapeClient#syncForestryKit in the Mootrius/myscape-plugin repo
    and ForestryKitItem's docstring in app/models.py. Full replace,
    never a merge."""
    if len(payload.items) > MAX_FORESTRY_KIT_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_FORESTRY_KIT_ITEMS}).",
        )

    db.query(ForestryKitItem).filter(ForestryKitItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(ForestryKitItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "forestry_kit", now)
    db.commit()

    return ForestryKitSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/forestry-kit", response_model=ForestryKitOut)
def read_forestry_kit(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank above, for the
    Forestry Kit instead."""
    items = (
        db.query(ForestryKitItem)
        .filter(ForestryKitItem.game_account_id == game_account.id)
        .order_by(ForestryKitItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return ForestryKitOut(items=[ForestryKitItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/master-scroll-book", response_model=MasterScrollBookSyncResponse)
def sync_master_scroll_book(
    payload: MasterScrollBookSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for the
    Master Scroll Book's stored teleport scrolls instead -- see
    MyscapeClient#syncMasterScrollBook in the Mootrius/myscape-plugin
    repo and MasterScrollBookItem's docstring in app/models.py (no
    confirmed container id yet, so this may not receive real syncs
    until the plugin's own temporary diagnostic finds one). Full
    replace, never a merge."""
    if len(payload.items) > MAX_MASTER_SCROLL_BOOK_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_MASTER_SCROLL_BOOK_ITEMS}).",
        )

    db.query(MasterScrollBookItem).filter(MasterScrollBookItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(MasterScrollBookItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "master_scroll_book", now)
    db.commit()

    return MasterScrollBookSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/master-scroll-book", response_model=MasterScrollBookOut)
def read_master_scroll_book(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank above, for the
    Master Scroll Book instead."""
    items = (
        db.query(MasterScrollBookItem)
        .filter(MasterScrollBookItem.game_account_id == game_account.id)
        .order_by(MasterScrollBookItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return MasterScrollBookOut(items=[MasterScrollBookItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/seed-box", response_model=SeedBoxSyncResponse)
def sync_seed_box(
    payload: SeedBoxSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for the Seed
    Box's contents instead -- see MyscapeClient#syncSeedBox in the
    Mootrius/myscape-plugin repo and SeedBoxItem's docstring in
    app/models.py. Full replace, never a merge."""
    if len(payload.items) > MAX_SEED_BOX_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_SEED_BOX_ITEMS}).",
        )

    db.query(SeedBoxItem).filter(SeedBoxItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(SeedBoxItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "seed_box", now)
    db.commit()

    return SeedBoxSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/seed-box", response_model=SeedBoxOut)
def read_seed_box(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank above, for the Seed
    Box instead."""
    items = (
        db.query(SeedBoxItem)
        .filter(SeedBoxItem.game_account_id == game_account.id)
        .order_by(SeedBoxItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return SeedBoxOut(items=[SeedBoxItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/huntsmans-kit", response_model=HuntsmansKitSyncResponse)
def sync_huntsmans_kit(
    payload: HuntsmansKitSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for a
    Huntsman's Kit's contents instead -- see
    MyscapeClient#syncHuntsmansKit in the Mootrius/myscape-plugin repo
    and HuntsmansKitItem's docstring in app/models.py. Full replace,
    never a merge."""
    if len(payload.items) > MAX_HUNTSMANS_KIT_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_HUNTSMANS_KIT_ITEMS}).",
        )

    db.query(HuntsmansKitItem).filter(HuntsmansKitItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(HuntsmansKitItem(
            game_account_id=game_account.id, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    _stamp_storage_synced(game_account, "huntsmans_kit", now)
    db.commit()

    return HuntsmansKitSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/huntsmans-kit", response_model=HuntsmansKitOut)
def read_huntsmans_kit(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank above, for the
    Huntsman's Kit instead."""
    items = (
        db.query(HuntsmansKitItem)
        .filter(HuntsmansKitItem.game_account_id == game_account.id)
        .order_by(HuntsmansKitItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return HuntsmansKitOut(items=[HuntsmansKitItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/boat-cargo/{slot}", response_model=BoatCargoSyncResponse)
def sync_boat_cargo(
    slot: int,
    payload: BoatCargoSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank above, for ONE of the
    player's (up to five) boats' cargo hold contents instead -- `slot`
    (1-5) picks which one. Deletes and replaces only THAT slot's own
    rows (BoatCargoItem.game_account_id AND .slot both filtered on below,
    unlike every other per-storage sync here which only ever needs
    game_account_id) -- see BoatCargoItem's docstring in app/models.py for
    why a sync of one boat must never touch what's already known about
    the other four."""
    if slot < 1 or slot > 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slot must be between 1 and 5.")
    if len(payload.items) > MAX_BOAT_CARGO_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_BOAT_CARGO_ITEMS}).",
        )

    db.query(BoatCargoItem).filter(BoatCargoItem.game_account_id == game_account.id, BoatCargoItem.slot == slot).delete()
    now = datetime.now(timezone.utc)
    for item in payload.items:
        db.add(BoatCargoItem(
            game_account_id=game_account.id, slot=slot, item_id=item.item_id, item_name=item.item_name,
            quantity=item.quantity, updated_at=now,
        ))
    # One shared "boat_cargo" timestamp across all five slots (see
    # BoatCargoItem's own docstring for why) -- bumped by whichever
    # slot happens to sync most recently, same simplification PoH's
    # single "poh" key already makes for its six furniture pieces.
    _stamp_storage_synced(game_account, "boat_cargo", now)
    db.commit()

    return BoatCargoSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/boat-cargo", response_model=BoatCargoOut)
def read_boat_cargo(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank above, for every one of
    the player's boats' cargo combined -- unlike every other single-
    container GET here, this one has no per-slot equivalent of its own
    (nothing on the website currently needs just one boat's contents on
    their own), so it always returns every slot's rows together,
    ordered by slot then item id, each row's own `slot` still attached
    (see BoatCargoItemOut's own docstring in app/schemas.py)."""
    items = (
        db.query(BoatCargoItem)
        .filter(BoatCargoItem.game_account_id == game_account.id)
        .order_by(BoatCargoItem.slot, BoatCargoItem.item_id)
        .all()
    )
    updated_at = items[0].updated_at if items else None
    return BoatCargoOut(items=[BoatCargoItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.get("/api/players/me/sync-status", response_model=SyncStatusOut)
def read_sync_status(game_account: GameAccount = Depends(get_current_game_account_from_api_key)):
    """API-key authenticated (unlike the website's own session-
    authenticated GETs above) -- this is what the RuneLite plugin's
    side panel Status section actually polls (see MyscapePanel's
    Status section in the Mootrius/myscape-plugin repo), since the
    plugin has no browser session to authenticate with, the same
    reason every other plugin-facing endpoint here is API-key
    authenticated too. Returns every one of POSSESSION_STORAGE_KEYS,
    `None` for anything never synced (see GameAccount.storage_synced_at's
    own docstring in app/models.py for why that's not the same thing
    as "synced empty")."""
    stamped = game_account.storage_synced_at or {}
    return SyncStatusOut(storages={key: stamped.get(key) for key in POSSESSION_STORAGE_KEYS})


@app.post("/api/players/me/skills", response_model=SkillsSyncResponse)
def sync_skills(
    payload: SkillsSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Full replace of the player's current level+xp in every skill --
    see GameAccount.skills' own comment in app/models.py and
    MyscapeClient#syncSkills in the Mootrius/myscape-plugin repo. Unlike
    bank/inventory/etc., this isn't many independent rows to delete-and-
    replace, just one JSONB column to overwrite outright, since a
    player has exactly one current level+xp per skill."""
    if len(payload.skills) > MAX_SKILLS_PER_SYNC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many skills in one sync (max {MAX_SKILLS_PER_SYNC}).",
        )
    game_account.skills = {s.skill: {"level": s.level, "xp": s.xp} for s in payload.skills}
    db.commit()
    return SkillsSyncResponse(skill_count=len(payload.skills))


@app.get("/api/players/me/skills")
def read_skills(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The website's own read of the last-synced skills snapshot --
    session-authenticated like every other GET here."""
    return {"skills": game_account.skills or {}}


@app.post("/api/players/me/quests", response_model=QuestsSyncResponse)
def sync_quests(
    payload: QuestsSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Full replace of the player's completed quest/miniquest list --
    see GameAccount.completed_quests' own comment in app/models.py and
    MyscapeClient#syncQuests in the Mootrius/myscape-plugin repo."""
    if len(payload.completed_quests) > MAX_QUESTS_PER_SYNC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many quests in one sync (max {MAX_QUESTS_PER_SYNC}).",
        )
    game_account.completed_quests = [q.strip() for q in payload.completed_quests if q and q.strip()]
    db.commit()
    return QuestsSyncResponse(quest_count=len(game_account.completed_quests))


@app.get("/api/players/me/quests")
def read_quests(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The website's own read of the last-synced completed-quests
    snapshot -- session-authenticated like every other GET here."""
    return {"completedQuests": game_account.completed_quests or []}


@app.post("/api/players/me/diaries", response_model=DiariesSyncResponse)
def sync_diaries(
    payload: DiariesSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Full replace of the player's highest completed tier per
    achievement diary area -- see GameAccount.diary_tiers' own comment in
    app/models.py and MyscapeClient#syncDiaries in the
    Mootrius/myscape-plugin repo. The plugin sends only each area's
    HIGHEST completed tier (matching how the in-game diary journal
    itself only ever shows one), not one row per tier."""
    if len(payload.diary_tiers) > MAX_DIARY_AREAS_PER_SYNC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many diary areas in one sync (max {MAX_DIARY_AREAS_PER_SYNC}).",
        )
    game_account.diary_tiers = {d.area: d.tier for d in payload.diary_tiers}
    db.commit()
    return DiariesSyncResponse(area_count=len(payload.diary_tiers))


@app.get("/api/players/me/diaries")
def read_diaries(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The website's own read of the last-synced diary-tiers snapshot
    -- session-authenticated like every other GET here."""
    return {"diaryTiers": game_account.diary_tiers or {}}


@app.post("/api/players/me/loot", response_model=LootSyncResponse)
def sync_loot(
    payload: LootSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Records one or more loot events (a kill, a clue casket, a
    pickpocket -- see MyscapePlugin#onLootReceived in the
    Mootrius/myscape-plugin repo) as they happen. Unlike every sync
    endpoint above, this is an insert-if-new, not a delete-and-replace
    -- see LootEvent's docstring in app/models.py for why a historical
    log needs a different sync shape than a current-state snapshot, and
    sync_loot_events in app/loot.py for the actual dedup logic (keyed
    on each event's client-generated event_id)."""
    if len(payload.events) > MAX_LOOT_EVENTS_PER_SYNC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many events in one sync (max {MAX_LOOT_EVENTS_PER_SYNC}).",
        )
    added_count = sync_loot_events(db, game_account, payload.events)
    return LootSyncResponse(added_count=added_count)


@app.get("/api/players/me/loot")
def read_loot(
    range: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """The combined state the Loot Tracker page polls -- the bar
    chart's buckets and a per-NPC breakdown of the same range,
    computed fresh from this player's synced LootEvent rows. `range`
    is one of app/loot.py's RANGE_PRESETS keys ("24h", "1w", "1m",
    "3m", "6m", "1y") or "custom", in which case `start`/`end` are
    either plain "YYYY-MM-DD" dates (as the range menu's own date
    inputs send them, naming the first and last calendar day to
    include, both inclusive) or full ISO-8601 timestamps (as a
    clicked bar sends instead, naming its own bucket's exact
    start/end -- see bucketUrl in render_loot_tracker's script) --
    see parse_loot_range_bound in app/loot.py for how each is told
    apart and turned into a concrete instant. An unrecognized/missing
    `range`, or a `custom` missing either date, falls back to
    resolve_range's own default (the page's original 24-hour window).
    Not pinned to a Pydantic response_model for the same reason GET
    /api/gear-setups above isn't -- see LootState's docstring in
    app/schemas.py. See build_loot_state in app/loot.py."""
    start_dt = None
    end_dt = None
    if range == "custom":
        try:
            if start:
                start_dt = parse_loot_range_bound(start, is_end=False)
            if end:
                end_dt = parse_loot_range_bound(end, is_end=True)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start/end must be YYYY-MM-DD dates or ISO-8601 timestamps.",
            )
    range_start, range_end = resolve_range(range, start_dt, end_dt)
    return build_loot_state(db, game_account, range_start, range_end)


@app.post("/api/players/me/loot/hidden-npcs")
def hide_loot_npc(payload: HideLootNpcRequest, db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Hides one NPC from Loot Tracker -- the eye button on an NPC
    tile's hover corner in render_loot_tracker, app/pages.py. See
    set_npc_hidden in app/loot.py for what this actually removes from
    the tracker's own totals."""
    set_npc_hidden(db, game_account, payload.name, True)
    return {"ok": True}


@app.delete("/api/players/me/loot/hidden-npcs")
def unhide_loot_npc(payload: HideLootNpcRequest, db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Reverses hide_loot_npc above -- the same eye button, now shown on
    a dimmed (already-hidden) tile once the panel's own "show hidden"
    toggle has revealed it."""
    set_npc_hidden(db, game_account, payload.name, False)
    return {"ok": True}


@app.post("/api/players/me/loot/hidden-items")
def hide_loot_item(payload: HideLootItemRequest, db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Hides one item from Loot Tracker -- same eye-button affordance as
    hide_loot_npc above, one level down (see set_item_hidden in
    app/loot.py)."""
    set_item_hidden(db, game_account, payload.item_id, payload.item_name, True)
    return {"ok": True}


@app.delete("/api/players/me/loot/hidden-items")
def unhide_loot_item(payload: HideLootItemRequest, db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Reverses hide_loot_item above -- same relationship as
    unhide_loot_npc has to hide_loot_npc."""
    set_item_hidden(db, game_account, payload.item_id, payload.item_name, False)
    return {"ok": True}


@app.get("/api/items/search", response_model=ItemSearchResponse)
def item_search(q: str = "", game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Backs the gear-setup slot picker's search box (see
    app/purchase_goals.py's search_items -- ported from Maintrius's own
    search_items in osrs_tracker.py) -- session-authenticated like every
    other Purchase Goals endpoint below, since only the website UI calls
    this, never the plugin."""
    return ItemSearchResponse(results=search_items(q))


@app.get("/api/npcs/search", response_model=NpcSearchResponse)
def npc_search(q: str = "", game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Backs the Mindmaps KC goal's NPC search field (see
    app/npc_names.py) -- session-authenticated like item_search above,
    since only the website UI calls this."""
    return NpcSearchResponse(results=search_npc_names(q))


@app.get("/api/quests/search", response_model=QuestSearchResponse)
def quest_search(q: str = "", game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Backs the Mindmaps QUEST goal's quest/miniquest search field
    (see app/quest_names.py) -- session-authenticated like
    item_search above, since only the website UI calls this."""
    return QuestSearchResponse(results=search_quest_names(q))


@app.get("/dashboard/purchase-goals", response_class=HTMLResponse)
def purchase_goals_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_purchase_goals(player)


@app.get("/dashboard/loot", response_class=HTMLResponse)
def loot_tracker_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_loot_tracker(player)


@app.get("/dashboard/mindmaps", response_class=HTMLResponse)
def mindmaps_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_mindmaps(player)


@app.get("/dashboard/possessions", response_class=HTMLResponse)
def possessions_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_possessions(player)


@app.get("/dashboard/goal-tracking", response_class=HTMLResponse)
def goal_tracking_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_goal_tracking(player)


@app.get("/api/possessions/search-items", response_model=ItemSearchResponse)
def possessions_item_search(q: str = "", game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Backs the min/max tracker "add an item" search field on the
    Storages Viewer page -- session-authenticated like
    item_search above, since only the website UI calls this. Unlike
    that endpoint, every result here always carries a real item id
    (see search_trackable_items in app/possessions.py for why -- a
    tracker has nothing to watch without one)."""
    return ItemSearchResponse(results=search_trackable_items(q))


@app.get("/api/possessions/summary")
def possessions_summary(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Section 3's payload -- every item currently owned in any synced
    storage, priced and broken down by location (see
    build_possessions_summary in app/possessions.py). Not pinned to a
    response_model, same reasoning as /api/gear-setups below: a plain
    list of dicts is simpler than fixing a schema for data this shape-
    stable in practice but not worth formally modeling."""
    return build_possessions_summary(db, game_account)


@app.get("/api/possessions/trackers")
def possessions_trackers(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Sections 1/2's combined payload -- both the minimum and maximum
    trackers the player has set up, each already resolved against a
    live owned-quantity count (see build_trackers_state in
    app/possessions.py)."""
    return build_trackers_state(db, game_account)


@app.post("/api/possessions/trackers", status_code=status.HTTP_201_CREATED)
def create_possession_tracker(
    payload: PossessionTrackerIn,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Adds one new min or max tracker. item_name is whatever the
    search result the player picked carried (see
    possessions_item_search above) -- purely the same untradeable-
    item-display fallback role documented on BankItem in
    app/models.py, never consulted for a tradeable item. Re-adding the
    same (kind, item_id) pair a player already has a tracker for
    updates its target instead of erroring or duplicating -- the
    natural behavior when they're just changing their mind about the
    number, not a state they need to explicitly delete-then-recreate
    to reach."""
    existing = (
        db.query(PossessionTracker)
        .filter(
            PossessionTracker.game_account_id == game_account.id,
            PossessionTracker.kind == payload.kind,
            PossessionTracker.item_id == payload.item_id,
        )
        .first()
    )
    if existing:
        existing.target_quantity = payload.target_quantity
        if payload.item_name:
            existing.item_name = payload.item_name
        db.commit()
    else:
        db.add(PossessionTracker(
            game_account_id=game_account.id,
            kind=payload.kind,
            item_id=payload.item_id,
            item_name=payload.item_name,
            target_quantity=payload.target_quantity,
            sort_order=next_sort_order(db, game_account, payload.kind),
        ))
        db.commit()
    return build_trackers_state(db, game_account)


@app.patch("/api/possessions/trackers/{tracker_id}")
def update_possession_tracker(
    tracker_id: uuid.UUID,
    payload: PossessionTrackerUpdate,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Edits an existing tracker's target quantity in place -- the only
    thing the page's own UI ever lets a player change about one after
    creation (swapping the item itself is delete-and-recreate instead,
    see PossessionTrackerUpdate's own docstring in app/schemas.py)."""
    tracker = (
        db.query(PossessionTracker)
        .filter(PossessionTracker.id == tracker_id, PossessionTracker.game_account_id == game_account.id)
        .first()
    )
    if not tracker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker not found.")
    tracker.target_quantity = payload.target_quantity
    db.commit()
    return build_trackers_state(db, game_account)


@app.delete("/api/possessions/trackers/{tracker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_possession_tracker(
    tracker_id: uuid.UUID,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    tracker = (
        db.query(PossessionTracker)
        .filter(PossessionTracker.id == tracker_id, PossessionTracker.game_account_id == game_account.id)
        .first()
    )
    if not tracker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker not found.")
    db.delete(tracker)
    db.commit()


@app.post("/api/possessions/pins/{item_id}")
def pin_possession_item(
    item_id: int,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Pins one item to the top of section 3's list (see
    PinnedPossessionItem's own docstring in app/models.py, and the pin
    button on each row in render_possessions). item_id always comes
    from a row already on screen -- the client only ever calls this
    with an id lifted straight off /api/possessions/summary's own
    payload -- so, unlike a tracker, there's no item_name to carry and
    nothing to validate against a search. Idempotent: pinning an
    already-pinned item is a no-op rather than an error, the same
    reasoning as re-adding an existing tracker just updating it instead
    of failing -- a player clicking an already-filled pin button
    should never see an error banner over it."""
    existing = (
        db.query(PinnedPossessionItem)
        .filter(PinnedPossessionItem.game_account_id == game_account.id, PinnedPossessionItem.item_id == item_id)
        .first()
    )
    if not existing:
        db.add(PinnedPossessionItem(game_account_id=game_account.id, item_id=item_id))
        db.commit()
    return {"pinnedItemIds": sorted(pinned_item_ids(db, game_account))}


@app.delete("/api/possessions/pins/{item_id}")
def unpin_possession_item(
    item_id: int,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Unpins one item -- same idempotent shape as pin_possession_item
    above, a no-op rather than a 404 if it wasn't pinned to begin with."""
    db.query(PinnedPossessionItem).filter(
        PinnedPossessionItem.game_account_id == game_account.id, PinnedPossessionItem.item_id == item_id
    ).delete()
    db.commit()
    return {"pinnedItemIds": sorted(pinned_item_ids(db, game_account))}


@app.post("/api/possessions/hidden-storages/{storage_key}")
def hide_possession_storage(
    storage_key: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Switches one storage source off in Storages Viewer's
    settings menu (see HiddenPossessionStorage's own docstring in
    app/models.py, and the gear-icon menu next to the location filter
    buttons in render_possessions) -- its items stop counting toward
    section 3's list and every tracker's owned quantity until it's
    switched back on."""
    if storage_key not in POSSESSION_STORAGE_KEYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown storage.")
    set_storage_hidden(db, game_account, storage_key, True)
    return {"hiddenStorageKeys": sorted(hidden_storage_keys(db, game_account))}


@app.delete("/api/possessions/hidden-storages/{storage_key}")
def unhide_possession_storage(
    storage_key: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Reverses hide_possession_storage above -- same idempotent shape
    as unpin_possession_item."""
    if storage_key not in POSSESSION_STORAGE_KEYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown storage.")
    set_storage_hidden(db, game_account, storage_key, False)
    return {"hiddenStorageKeys": sorted(hidden_storage_keys(db, game_account))}


@app.get("/api/possessions/views")
def list_possession_views(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Every saved Storages Viewer view this player has (see
    build_possession_views in app/possessions.py), in their own
    reorder-strip order."""
    return {"views": build_possession_views(db, game_account)}


@app.post("/api/possessions/views", status_code=status.HTTP_201_CREATED)
def create_possession_view(
    payload: PossessionViewSaveRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Saves the page's current filter/sort setup as a new named view
    -- always appended past the end of the player's existing views
    (see next_possession_view_sort_order), never merged into an
    existing one even if the name matches -- renaming/overwriting an
    existing view is what PATCH .../{view_id} is for."""
    db.add(PossessionView(
        game_account_id=game_account.id,
        name=payload.name,
        config=payload.config,
        sort_order=next_possession_view_sort_order(db, game_account),
    ))
    db.commit()
    return {"views": build_possession_views(db, game_account)}


@app.put("/api/possessions/views/order")
def set_possession_view_order(
    payload: SetPossessionViewOrderRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Saves a drag-and-drop reorder of the saved-views strip -- same
    full-replacement convention as set_gear_setup_order above:
    payload.order is the complete list of view ids in their new order,
    not a delta. Every view this player owns gets a fresh sort_order
    (its plain 0-based position in payload.order) in one pass; a
    stale/omitted id keeps its existing sort_order rather than
    erroring the whole request out, and an id in payload.order that
    isn't one of the player's own views is silently ignored -- same
    defensive stance as set_gear_setup_order."""
    owned_views = {
        str(v.id): v
        for v in db.query(PossessionView).filter(PossessionView.game_account_id == game_account.id).all()
    }
    for index, view_id in enumerate(payload.order):
        view = owned_views.get(view_id)
        if view is not None:
            view.sort_order = float(index)
    db.commit()
    return {"views": build_possession_views(db, game_account)}


def _get_owned_possession_view(db: Session, game_account: GameAccount, view_id: str) -> PossessionView:
    try:
        view_uuid = uuid.UUID(view_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found.")
    view = (
        db.query(PossessionView)
        .filter(PossessionView.id == view_uuid, PossessionView.game_account_id == game_account.id)
        .first()
    )
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found.")
    return view


@app.patch("/api/possessions/views/{view_id}")
def update_possession_view(
    view_id: str,
    payload: PossessionViewUpdateRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Renames an existing saved view, replaces its stored config with
    the page's current filter/sort setup, or both at once -- see
    PossessionViewUpdateRequest's own docstring in app/schemas.py."""
    view = _get_owned_possession_view(db, game_account, view_id)
    if payload.name is not None:
        view.name = payload.name
    if payload.config is not None:
        view.config = payload.config
    db.commit()
    return {"views": build_possession_views(db, game_account)}


@app.delete("/api/possessions/views/{view_id}")
def delete_possession_view(
    view_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    view = _get_owned_possession_view(db, game_account, view_id)
    db.delete(view)
    db.commit()
    return {"views": build_possession_views(db, game_account)}


@app.get("/api/gear-setups")
def list_gear_setups(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The combined state the Purchase Goals page polls (see
    app/purchase_goals.py's build_purchase_goals_state, ported from
    Maintrius's own build_state in osrs_tracker.py) -- every one of the
    player's gear setups, fully priced/owned-checked against their
    synced bank+inventory+equipment+potion storage, plus their current coins and
    whatever wiki price/mapping errors are in effect. Not pinned to a
    Pydantic response_model (see GearSetupsState's docstring in
    app/schemas.py) since the shape is too dynamic/nested to usefully
    fix -- FastAPI serializes the plain dict build_purchase_goals_state
    returns as-is."""
    return build_purchase_goals_state(db, game_account)


@app.post("/api/gear-setups", status_code=status.HTTP_201_CREATED)
def create_gear_setup(
    payload: CreateGearSetupRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    name = (payload.name or "").strip() or "New Setup"
    setup = GearSetup(game_account_id=game_account.id, name=name, equipment={}, inventory=[None] * INVENTORY_SIZE)
    db.add(setup)
    db.commit()
    return build_purchase_goals_state(db, game_account)


@app.put("/api/gear-setups/order")
def set_gear_setup_order(
    payload: SetGearSetupOrderRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Saves a drag-and-drop reorder of the player's gear setup LIST
    itself (the icon row above the gear frame -- contrast
    set_still_to_purchase_order below, which reorders rows INSIDE one
    setup) -- payload.order is the complete list of setup ids in their
    new order, not a delta, same convention as every other reorder
    endpoint here. Every setup this player owns gets a fresh sort_order
    (its plain 0-based position in payload.order) in one pass; any of
    the player's setup ids payload.order left out (a stale client, or a
    setup deleted mid-drag) keeps whatever sort_order it already had
    rather than erroring the whole request out, and any id in
    payload.order that ISN'T one of the player's own setups is silently
    ignored -- the same defensive stance _get_owned_gear_setup takes
    everywhere else, just applied per-id instead of failing the batch."""
    owned_setups = {
        str(s.id): s
        for s in db.query(GearSetup).filter(GearSetup.game_account_id == game_account.id).all()
    }
    for index, setup_id in enumerate(payload.order):
        setup = owned_setups.get(setup_id)
        if setup is not None:
            setup.sort_order = float(index)
    db.commit()
    return build_purchase_goals_state(db, game_account)


def _get_owned_gear_setup(db: Session, game_account: GameAccount, setup_id: str) -> GearSetup:
    try:
        setup_uuid = uuid.UUID(setup_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gear setup not found")
    setup = (
        db.query(GearSetup)
        .filter(GearSetup.id == setup_uuid, GearSetup.game_account_id == game_account.id)
        .first()
    )
    if setup is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gear setup not found")
    return setup


@app.patch("/api/gear-setups/{setup_id}")
def rename_gear_setup(
    setup_id: str,
    payload: RenameGearSetupRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    setup = _get_owned_gear_setup(db, game_account, setup_id)
    setup.name = payload.name
    db.commit()
    return build_purchase_goals_state(db, game_account)


@app.delete("/api/gear-setups/{setup_id}")
def delete_gear_setup(
    setup_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    setup = _get_owned_gear_setup(db, game_account, setup_id)
    db.delete(setup)
    db.commit()
    return build_purchase_goals_state(db, game_account)


@app.put("/api/gear-setups/{setup_id}/icon")
def set_gear_setup_icon(
    setup_id: str,
    payload: SetGearSetupIconRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Sets (or, with icon omitted/null, clears) the display-only icon
    shown next to a setup's total cost -- purely cosmetic, never affects
    cost/ownership (see GearSetup's docstring in app/models.py and
    _handle_set_gear_setup_icon in Maintrius's own osrs_tracker.py)."""
    setup = _get_owned_gear_setup(db, game_account, setup_id)
    if payload.icon is None:
        setup.icon = None
    else:
        setup.icon = {"itemId": payload.icon.item_id, "itemName": payload.icon.item_name or None}
    db.commit()
    return build_purchase_goals_state(db, game_account)


@app.put("/api/gear-setups/{setup_id}/slot")
def set_gear_slot(
    setup_id: str,
    payload: SetGearSlotRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Fills (or, with item omitted/null, clears) one equipment or
    inventory slot of a gear setup -- see SetGearSlotRequest/
    GearSlotItemIn in app/schemas.py for the validated shape (plain
    tradeable, plain untradeable, or composed "combo") and
    _handle_set_gear_slot in Maintrius's own osrs_tracker.py for the
    original this ports. Stores exactly what was sent, unresolved --
    pricing/ownership is computed fresh on every read, not here (see
    app/purchase_goals.py) -- with one addition: a plain untradeable
    item (no item_id, no components) is checked against the known
    item-combination recipes (app/recipes.py) and, on a match, is
    auto-expanded into a "combo" here before it's ever persisted. This
    is what lets someone search for and select e.g. "Neitiznot
    faceguard" directly instead of having to know it's built from a
    Helm of Neitiznot + a Basilisk jaw and build it from parts
    themselves -- the frontend never has to know the difference."""
    setup = _get_owned_gear_setup(db, game_account, setup_id)

    if payload.item is None:
        stored_item = None
    else:
        stored_item = {"itemId": payload.item.item_id, "itemName": payload.item.item_name or None}
        if payload.item.components:
            stored_item["components"] = [
                {"itemId": c.item_id, "itemName": c.item_name or None, "quantity": c.quantity}
                for c in payload.item.components
            ]
        if (
            payload.item.item_id is None
            and not payload.item.components
            and payload.item.item_name
            and not has_derived_price(payload.item.item_name)
        ):
            # Anything the ported RuneLite table already has a linked GE
            # value for (has_derived_price/derived_price_by_name in
            # app/purchase_goals.py -- Crystal helm/body/legs, charged
            # weapons, Bow of Faerdhinen/Blade of Saeldor, Elidinis'
            # ward (f), and ~900 more) is skipped here: it's priced
            # directly off that linked value at read time regardless of
            # whatever components this would expand into (some of which,
            # for a few of these specific items, the wiki's own recipe
            # data gets outright wrong or simply doesn't have at all),
            # so there's nothing useful to auto-expand into up front.
            mapping, _ = get_mapping()
            auto_components = expand_recipe_components(payload.item.item_name, mapping)
            if auto_components:
                stored_item["components"] = auto_components

    if payload.slot_type == "equipment":
        if payload.slot not in GEAR_SETUP_EQUIPMENT_SLOTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"slot must be one of {GEAR_SETUP_EQUIPMENT_SLOTS}"
            )
        # New dict, not an in-place mutation of the loaded one -- see the
        # IMPORTANT note on GearSetup in app/models.py for why that
        # distinction matters for a JSONB column.
        equipment = dict(setup.equipment or {})
        if stored_item is None:
            equipment.pop(payload.slot, None)
        else:
            equipment[payload.slot] = stored_item
        setup.equipment = equipment
    elif payload.slot_type == "inventory":
        if not isinstance(payload.slot, int) or not (0 <= payload.slot < INVENTORY_SIZE):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"slot must be an integer 0-{INVENTORY_SIZE - 1}",
            )
        inventory = list(setup.inventory or [None] * INVENTORY_SIZE)
        if len(inventory) != INVENTORY_SIZE:
            inventory = (inventory + [None] * INVENTORY_SIZE)[:INVENTORY_SIZE]
        inventory[payload.slot] = stored_item
        setup.inventory = inventory
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slot_type must be 'equipment' or 'inventory'")

    db.commit()
    return build_purchase_goals_state(db, game_account)


def _check_gear_slot(slot_type: str, slot: Any) -> None:
    """Same slot-shape validation set_gear_slot applies to the one slot
    it's writing, factored out so move_gear_slot_item below can apply it
    to both the source and destination slot of a drag-and-drop."""
    if slot_type == "equipment":
        if slot not in GEAR_SETUP_EQUIPMENT_SLOTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"slot must be one of {GEAR_SETUP_EQUIPMENT_SLOTS}"
            )
    elif slot_type == "inventory":
        if not isinstance(slot, int) or not (0 <= slot < INVENTORY_SIZE):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"slot must be an integer 0-{INVENTORY_SIZE - 1}",
            )
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slot_type must be 'equipment' or 'inventory'")


def _read_gear_slot(equipment: dict, inventory: list, slot_type: str, slot: Any) -> Optional[dict]:
    return equipment.get(slot) if slot_type == "equipment" else inventory[slot]


def _write_gear_slot(equipment: dict, inventory: list, slot_type: str, slot: Any, item: Optional[dict]) -> None:
    if slot_type == "equipment":
        if item is None:
            equipment.pop(slot, None)
        else:
            equipment[slot] = item
    else:
        inventory[slot] = item


@app.put("/api/gear-setups/{setup_id}/slot/move")
def move_gear_slot_item(
    setup_id: str,
    payload: MoveGearSlotItemRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Drag-and-drop: moves whatever's stored in (from_slot_type,
    from_slot) into (to_slot_type, to_slot), across equipment and
    inventory alike. If the destination already holds an item, the two
    simply swap rather than the destination's original item being lost.

    Operates purely on the raw stored shape (exactly what set_gear_slot
    itself would have stored -- item id/name, or a combo's already-
    expanded components list), never on the resolved/priced shape the
    frontend renders -- so a combo's exact stored components move
    across untouched rather than being reconstructed from (and
    potentially drifting from) their priced/resolved form."""
    setup = _get_owned_gear_setup(db, game_account, setup_id)

    _check_gear_slot(payload.from_slot_type, payload.from_slot)
    _check_gear_slot(payload.to_slot_type, payload.to_slot)

    if payload.from_slot_type == payload.to_slot_type and payload.from_slot == payload.to_slot:
        # Dropped a slot onto itself -- nothing to do.
        return build_purchase_goals_state(db, game_account)

    # Fresh dict/list, not an in-place mutation of the loaded ones -- see
    # the IMPORTANT note on GearSetup in app/models.py for why that
    # distinction matters for a JSONB column.
    equipment = dict(setup.equipment or {})
    inventory = list(setup.inventory or [None] * INVENTORY_SIZE)
    if len(inventory) != INVENTORY_SIZE:
        inventory = (inventory + [None] * INVENTORY_SIZE)[:INVENTORY_SIZE]

    from_item = _read_gear_slot(equipment, inventory, payload.from_slot_type, payload.from_slot)
    to_item = _read_gear_slot(equipment, inventory, payload.to_slot_type, payload.to_slot)

    _write_gear_slot(equipment, inventory, payload.to_slot_type, payload.to_slot, from_item)
    _write_gear_slot(equipment, inventory, payload.from_slot_type, payload.from_slot, to_item)

    setup.equipment = equipment
    setup.inventory = inventory
    db.commit()
    return build_purchase_goals_state(db, game_account)


@app.put("/api/gear-setups/{setup_id}/still-to-purchase-sort")
def set_still_to_purchase_sort(
    setup_id: str,
    payload: SetStillToPurchaseSortRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Switches which of the buttons above a setup's "Still to
    Purchase" list is active -- see STILL_TO_PURCHASE_SORT_MODES in
    app/schemas.py and _still_to_purchase_summary in
    app/purchase_goals.py for what each one actually does. Doesn't
    touch still_to_purchase_custom_order -- switching to "custom" and
    back doesn't lose a previously-dragged order, and switching away
    from "custom" doesn't erase it either, it's just not applied while
    a different mode is active."""
    setup = _get_owned_gear_setup(db, game_account, setup_id)
    setup.still_to_purchase_sort_mode = payload.sort_mode
    db.commit()
    return build_purchase_goals_state(db, game_account)


@app.put("/api/gear-setups/{setup_id}/still-to-purchase-order")
def set_still_to_purchase_order(
    setup_id: str,
    payload: SetStillToPurchaseOrderRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Saves a drag-and-drop reorder of a setup's "Still to Purchase"
    list -- payload.order is the complete list as currently displayed
    (not a delta), one {slot_type, slot} entry per row, exactly mirroring
    how set_gear_slot/move_gear_slot_item always store a full
    replacement rather than a patch. Also switches the setup into
    "custom" sort mode if it wasn't already there -- dragging a row is
    only ever possible in "custom" mode client-side (see
    renderSummaryList in app/pages.py), so this is a defensive
    backstop, not something a well-behaved client should ever rely on."""
    setup = _get_owned_gear_setup(db, game_account, setup_id)
    setup.still_to_purchase_sort_mode = "custom"
    setup.still_to_purchase_custom_order = [
        {"slotType": entry.slot_type, "slot": entry.slot} for entry in payload.order
    ]
    db.commit()
    return build_purchase_goals_state(db, game_account)


def _build_goal_context(db: Session, game_account: GameAccount) -> dict:
    """Everything Mindmaps' goal-node auto-completion (see
    evaluate_completion in app/mindmaps.py) needs to check every node
    in every one of this player's mindmaps against, gathered once per
    request rather than once per node. Lives here rather than in
    app/mindmaps.py because building it means reaching into
    app/purchase_goals.py (for the same owned-item pool a gear setup
    already checks itself against) and app/loot.py (for kill counts) --
    app/mindmaps.py deliberately doesn't import either, to avoid a
    circular import (app/purchase_goals.py itself imports from
    app/schemas.py, which imports SKILL_NAMES/DIARY_AREAS/DIARY_TIERS
    back out of app/mindmaps.py for its own sync-payload validation) --
    main.py is the one place already importing all three, so it's the
    natural place to wire them together.

    An item-goal node and a gear-setup slot are checking the literal
    same "what does this player currently have" question, so this
    reuses build_owned_pools outright rather than re-deriving it."""
    owned_pool_by_id, owned_pool_by_name = build_owned_pools(db, game_account)
    platinum_qty = sum(owned_pool_by_id.get(i, 0) for i in (find_item_ids("Platinum token") or []))
    gp_total = owned_pool_by_id.get(COINS_ITEM_ID, 0) + platinum_qty * 1000

    return {
        "owned_pool_by_id": owned_pool_by_id,
        "owned_pool_by_name": owned_pool_by_name,
        "gp_total": gp_total,
        "skills": game_account.skills or {},
        "completed_quests": {(q or "").strip().lower() for q in (game_account.completed_quests or [])},
        "diary_tiers": game_account.diary_tiers or {},
        "kc_counts": kc_counts_by_player(db, game_account),
    }


@app.get("/api/mindmaps")
def list_mindmaps(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Every one of the player's mindmaps, each with its full node list
    -- see build_mindmaps_state in app/mindmaps.py. Not pinned to a
    Pydantic response_model, same reasoning as GET /api/gear-setups
    above (see MindMapsState's docstring in app/schemas.py)."""
    return build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))


@app.post("/api/mindmaps", status_code=status.HTTP_201_CREATED)
def create_mindmap(
    payload: CreateMindMapRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    name = (payload.name or "").strip() or "New Mindmap"
    mindmap = MindMap(game_account_id=game_account.id, name=name, nodes=[new_root_node(name)])
    db.add(mindmap)
    db.commit()
    return build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))


def _get_owned_mindmap(db: Session, game_account: GameAccount, mindmap_id: str) -> MindMap:
    try:
        mindmap_uuid = uuid.UUID(mindmap_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mindmap not found")
    mindmap = (
        db.query(MindMap)
        .filter(MindMap.id == mindmap_uuid, MindMap.game_account_id == game_account.id)
        .first()
    )
    if mindmap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mindmap not found")
    return mindmap


@app.patch("/api/mindmaps/{mindmap_id}")
def rename_mindmap(
    mindmap_id: str,
    payload: RenameMindMapRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    mindmap = _get_owned_mindmap(db, game_account, mindmap_id)
    mindmap.name = payload.name
    db.commit()
    return build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))


@app.delete("/api/mindmaps/{mindmap_id}")
def delete_mindmap(
    mindmap_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    mindmap = _get_owned_mindmap(db, game_account, mindmap_id)
    db.delete(mindmap)
    db.commit()
    return build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))


@app.post("/api/mindmaps/{mindmap_id}/nodes", status_code=status.HTTP_201_CREATED)
def add_mindmap_node(
    mindmap_id: str,
    payload: AddMindMapNodeRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    mindmap = _get_owned_mindmap(db, game_account, mindmap_id)
    try:
        new_nodes, new_node_id = add_node(
            mindmap.nodes, payload.relative_to, payload.relation, payload.text, payload.color, payload.before
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    mindmap.nodes = new_nodes
    db.commit()
    state = build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))
    # See add_node's docstring in app/mindmaps.py -- handed back
    # alongside the full state so the client can select the new node
    # without diffing old vs. new node lists itself.
    state["newNodeId"] = new_node_id
    return state


@app.post("/api/mindmaps/{mindmap_id}/nodes/shared-child", status_code=status.HTTP_201_CREATED)
def add_mindmap_shared_child(
    mindmap_id: str,
    payload: AddMindMapSharedChildRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """The node canvas's shift-click multi-select: adds one new node as
    a shared child connected below two or more existing ones -- see
    add_shared_child in app/mindmaps.py."""
    mindmap = _get_owned_mindmap(db, game_account, mindmap_id)
    try:
        new_nodes, new_node_id = add_shared_child(mindmap.nodes, payload.parent_ids, payload.text, payload.color)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    mindmap.nodes = new_nodes
    db.commit()
    state = build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))
    state["newNodeId"] = new_node_id
    return state


@app.put("/api/mindmaps/{mindmap_id}/nodes")
def replace_mindmap_nodes(
    mindmap_id: str,
    payload: ReplaceMindMapNodesRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Restores a mindmap's whole node tree to a previously-seen
    snapshot -- what the node canvas's undo/redo buttons use (see
    replace_nodes in app/mindmaps.py) in place of a confirm-before-
    delete dialog on individual node deletes."""
    mindmap = _get_owned_mindmap(db, game_account, mindmap_id)
    try:
        mindmap.nodes = replace_nodes([n.model_dump(exclude_none=True) for n in payload.nodes])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    db.commit()
    return build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))


@app.patch("/api/mindmaps/{mindmap_id}/nodes/{node_id}")
def update_mindmap_node(
    mindmap_id: str,
    node_id: str,
    payload: UpdateMindMapNodeRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    mindmap = _get_owned_mindmap(db, game_account, mindmap_id)
    try:
        mindmap.nodes = update_node(mindmap.nodes, node_id, payload.text, payload.color, payload.note)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    db.commit()
    return build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))


@app.patch("/api/mindmaps/{mindmap_id}/nodes/{node_id}/goal")
def set_mindmap_node_goal(
    mindmap_id: str,
    node_id: str,
    payload: SetMindMapNodeGoalRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Saves a node's goal fields -- the per-color forms described in
    app/mindmaps.py's clean_goal docstring (kc target + activity for
    red, item + quantity for orange, and so on) -- and is also what
    the gray-node "Complete" button calls (gray's only field beyond
    its text is the manual completed flag clean_goal validates).
    require_complete defaults to True inside set_node_goal itself, so
    an incomplete submission (a red node with no activity chosen, say)
    is rejected here with a 400 naming what's missing, rather than
    silently saved half-filled-in.

    payload.note (see SetMindMapNodeGoalRequest's own docstring) rides
    along on the same request when given -- applied via the same
    update_node a plain node-PATCH uses, against the already-updated
    node list, so a trackable node's popover Save button persists its
    goal AND its note in one request/one undo step instead of two."""
    mindmap = _get_owned_mindmap(db, game_account, mindmap_id)
    try:
        nodes = set_node_goal(mindmap.nodes, node_id, payload.goal)
        if payload.note is not None:
            nodes = update_node(nodes, node_id, note=payload.note)
        mindmap.nodes = nodes
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    db.commit()
    return build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))


@app.delete("/api/mindmaps/{mindmap_id}/nodes/{node_id}")
def delete_mindmap_node(
    mindmap_id: str,
    node_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    mindmap = _get_owned_mindmap(db, game_account, mindmap_id)
    try:
        mindmap.nodes = delete_node(mindmap.nodes, node_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    db.commit()
    return build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))

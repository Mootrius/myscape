"""myscape's web app: landing page, health checks, and the account system
(website signup/login, RuneLite plugin account linking). See README.md for how
the pieces fit together.
"""
import base64
import logging
import os
import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# Without this the root logger drops every log.info() call (e.g. email_client's
# "RESEND_API_KEY not set" line) before it reaches Render's logs.
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
    get_current_verified_account_from_session,
    get_current_verified_game_account_from_session,
    get_optional_current_account_from_session,
    get_optional_current_game_account_from_session,
    get_optional_current_player_view_from_session,
)
from app import goals as goals_module
from app import site_flags
from app import hiscores as sync_hiscores_module
from app.database import SessionLocal, get_db
from app.icon_cache import ensure_cached_icon_path
from app.limiter import limiter
from app.loot import build_loot_share_snapshot, build_loot_state, kc_counts_by_player, parse_loot_range_bound, resolve_range, set_item_hidden, set_npc_hidden, sync_loot_events
from app.bosses import collection_log_page_kill_counts
from app.collectionlog import find_unique_item_id_by_name, get_collection_log_tabs, get_valid_item_ids
from app.item_ids import canonical_master_scroll_item_id, find_item_ids
from app.npc_names import search_npc_names
from app.quest_names import search_quest_names
from app.character_progress_data import (
    get_ca_tier_totals,
    get_diary_tier_totals,
    get_quest_list,
)
from app.mindmaps import (
    DIARY_TIERS,
    _normalize_lookup_name,
    add_node,
    add_shared_child,
    build_mindmap_share_snapshot,
    build_mindmaps_state,
    delete_node,
    import_mindmap_from_share_payload,
    new_root_node,
    replace_nodes,
    set_node_goal,
    update_node,
)
from app.models import (
    Account,
    BankItem,
    BoatCargoItem,
    EquipmentItem,
    ForestryKitItem,
    GameAccount,
    GearSetup,
    Goal,
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
    PermanentExample,
    SharedContent,
    TackleBoxItem,
    _utcnow,
)
from app.pages import (
    _MODEL_VIEWER_BACKGROUNDS,
    _SITE_URL,
    PlayerView,
    build_player_view,
    render_account,
    render_character_overview,
    render_dashboard,
    render_forgot_password,
    render_goal_tracking,
    render_help_support,
    render_goal_tracking_share,
    render_landing,
    render_login,
    render_loot_tracker,
    render_loot_tracker_share,
    render_mindmaps,
    render_mindmap_share,
    render_not_found,
    render_possessions,
    render_public_character_overview,
    render_purchase_goals,
    render_purchase_goals_share,
    render_reset_password,
    render_signup,
    render_signup_coming_soon,
    render_storages_share,
    render_verify_email,
    render_verify_email_required,
)
from app.public_profile import find_public_game_account, find_viewable_game_account, format_cooldown_remaining, generate_public_code, regenerate_cooldown_remaining
from app.possessions import (
    build_possession_views,
    build_possessions_share_snapshot,
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
    build_purchase_goal_share_snapshot,
    build_purchase_goals_state,
    get_mapping,
    has_derived_price,
    import_gear_setup_from_share_payload,
    item_icon_url,
    search_items,
)
from app.recipes import expand_recipe_components
from app.permanent_examples import (
    capture_permanent_examples,
    find_permanent_profile,
    frozen_owner,
)
from app.sharing import SHARE_DEFAULT_LIFETIME, find_valid_share, generate_share_code
from app.routers import account, auth, friends, linking
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
    CharacterModelSyncRequest,
    CharacterModelSyncResponse,
    CharacterSummarySyncRequest,
    CharacterSummarySyncResponse,
    CollectionLogSyncRequest,
    CollectionLogItemAddRequest,
    CollectionLogItemAddResponse,
    CollectionLogSyncResponse,
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
    GoalCreateRequest,
    GoalOut,
    GoalReorderRequest,
    GoalsResponse,
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
    KillCountSyncRequest,
    KillCountSyncResponse,
    RunescapeNameSyncRequest,
    RunescapeNameSyncResponse,
    LootingBagOut,
    LootingBagItemOut,
    LootingBagSyncRequest,
    LootingBagSyncResponse,
    LootShareCreateRequest,
    LootSyncRequest,
    LootSyncResponse,
    MasterScrollBookOut,
    MasterScrollBookItemOut,
    MasterScrollBookSyncRequest,
    MasterScrollBookSyncResponse,
    ModelViewerBackgroundUpdateRequest,
    MoveGearSlotItemRequest,
    NpcSearchResponse,
    PlayerOut,
    PohOut,
    PohItemOut,
    PohSyncRequest,
    PohSyncResponse,
    POSSESSION_STORAGE_KEYS,
    PossessionShareCreateRequest,
    PossessionTrackerIn,
    PossessionTrackerUpdate,
    PossessionViewSaveRequest,
    PossessionViewUpdateRequest,
    PotionStorageOut,
    PotionStorageItemOut,
    PotionStorageSyncRequest,
    PotionStorageSyncResponse,
    PublicProfileUpdateRequest,
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
    SetGoalSortModeRequest,
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

# Defensive upper bound, not a real OSRS limit: only a malformed or buggy client
# would hit it, and rejecting beats storing it.
MAX_BANK_ITEMS = 2000
# Inventory and equipment are fixed-size containers (28 and 11 slots), so these
# are exact ceilings.
MAX_INVENTORY_ITEMS = INVENTORY_SIZE
MAX_EQUIPMENT_ITEMS = len(EQUIPMENT_SLOTS)
# At most two rows per potion type (full-dose count plus one partial-dose item);
# generous multiple of a few dozen types.
MAX_POTION_STORAGE_ITEMS = 200
# A Rune Pouch has at most 6 slots (one rune type each), with a little headroom
# in case Jagex ships a bigger one.
MAX_RUNE_POUCH_ITEMS = 10
# Every tradeable seed (a few dozen types); generous multiple of the real
# ceiling.
MAX_SEED_VAULT_ITEMS = 200
# The Looting Bag holds up to 28 stacks, same as the inventory.
MAX_LOOTING_BAG_ITEMS = INVENTORY_SIZE
# A Tackle Box stores 35 distinct kinds of item; small headroom past that.
MAX_TACKLE_BOX_ITEMS = 50
# The whole PoH Costume Room as one sync (see PohItem in app/models.py), sized
# generously for all six furniture pieces combined.
MAX_POH_ITEMS = 1500
# A handful of Forestry event consumables at most; generous headroom.
MAX_FORESTRY_KIT_ITEMS = 50
# Dozens of distinct teleport scroll types; generous headroom.
MAX_MASTER_SCROLL_BOOK_ITEMS = 150
# The Seed Box holds six seed types; headroom in case that is raised.
MAX_SEED_BOX_ITEMS = 20
# A handful of creature-specific Hunter equipment sets; generous headroom.
MAX_HUNTSMANS_KIT_ITEMS = 50
# Bounds ONE boat slot's request, not all five boats (see sync_boat_cargo).
MAX_BOAT_CARGO_ITEMS = 100
# Exactly 24 OSRS skills (SKILL_NAMES in app/mindmaps.py).
MAX_SKILLS_PER_SYNC = 24
# Defensive upper bound on completed quests/miniquests; OSRS has far fewer.
MAX_QUESTS_PER_SYNC = 1000
# Exactly 12 achievement diary areas (DIARY_AREAS in app/mindmaps.py).
MAX_DIARY_AREAS_PER_SYNC = 12
# Number of collection log item ids in app.collectionlog.get_valid_item_ids()
# (1721 at time of writing); a sync is a full replace, so this is the true
# maximum.
MAX_COLLECTION_LOG_ITEMS_PER_SYNC = len(get_valid_item_ids())
# The plugin syncs one loot event as it happens, so a real sync is exactly 1;
# this is a defensive bound against batching abuse.
MAX_LOOT_EVENTS_PER_SYNC = 50
# Same as MAX_LOOT_EVENTS_PER_SYNC: the plugin syncs one kill count at a time.
MAX_KILL_COUNT_UPDATES_PER_SYNC = 20
# One composited player model is well under 1 MB as GLB; 8 MB raw (~10.7 MB
# base64) rejects malformed or hostile requests.
MAX_CHARACTER_MODEL_BYTES = 8 * 1024 * 1024

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
    """Swaps in render_not_found's styled page for 404s on site pages. /api/*,
    /static/* and non-404 statuses keep FastAPI's JSON {"detail": ...} body,
    which the site's JS (describeError() in app/pages.py) parses.
    
    Registered on Starlette's HTTPException because unmatched routes raise the
    base class, which a handler on the fastapi subclass never sees.
    """
    if exc.status_code == status.HTTP_404_NOT_FOUND and not request.url.path.startswith(("/api/", "/static/")):
        # Exception handlers bypass dependency injection, so the DB session is
        # opened by hand (for the signed-in nav). Dependencies are called
        # directly, so every argument must be passed explicitly or the literal
        # Depends(...) marker leaks through.
        db = SessionLocal()
        try:
            account = get_optional_current_account_from_session(request, db)
            player = get_optional_current_player_view_from_session(request, db, account)
        finally:
            db.close()
        return HTMLResponse(render_not_found(player), status_code=status.HTTP_404_NOT_FOUND)
    return await _default_http_exception_handler(request, exc)
# Session cookies back website login (see app/auth.py). `https_only` is on
# because myscape.io is HTTPS-only in production; for local http://localhost
# testing override it with an env var rather than deleting it.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    same_site="lax",
    https_only=os.environ.get("SESSION_COOKIE_HTTPS_ONLY", "true").lower() != "false",
    max_age=60 * 60 * 24 * 30,  # 30 days
)
app.include_router(account.router)
app.include_router(auth.router)
app.include_router(friends.router)
app.include_router(linking.router)

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/icon-cache/{filename}")
def get_cached_icon(filename: str):
    """Serves a wiki-sourced icon via ensure_cached_icon_path (app/icon_cache.py)
    with a long-lived Cache-Control. Item icons use the RuneLite CDN directly;
    this serves NPC/event portraits and rare combination items missing from
    app/item_ids.py. The filename is re-validated against path traversal.
    """
    path = ensure_cached_icon_path(filename)
    if not path:
        raise HTTPException(status_code=404)
    return FileResponse(path, headers={"Cache-Control": "public, max-age=604800, immutable"})


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@app.on_event("startup")
def on_startup():
    # Applies pending migrations/versions/*.py (see README.md "Database schema
    # changes"). Runs on every startup, safe because the service is a single
    # instance; the initial migration skips existing tables, so production needs
    # no manual stamping.
    alembic_cfg = Config(os.path.join(_REPO_ROOT, "alembic.ini"))
    command.upgrade(alembic_cfg, "head")

    # Copies the README's permanent example links into their own table on first
    # sight (app/permanent_examples.py). Must never stop the app from booting.
    db = SessionLocal()
    try:
        capture_permanent_examples(
            db,
            {
                "summary": _character_overview_summary_payload,
                "progress": _character_overview_progress_payload,
                "skills": _skills_payload,
                "collection-log": _collection_log_payload,
            },
        )
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception("Could not capture permanent examples.")
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
def root(
    home: Optional[str] = None,
    player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session),
):
    # A logged-in player goes straight to /dashboard, except via the header logo
    # (_shell() in pages.py), which adds ?home=1 while signed in.
    if player and not home:
        return RedirectResponse("/dashboard", status_code=302)
    return render_landing(player)


# Every page _shell() renders noindex (app/pages.py); keep in sync when adding a
# page. /dashboard covers all /dashboard/* by prefix.
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


# The landing page is the only indexable URL _shell() renders.
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
    if not site_flags.SIGNUPS_ENABLED:
        # Sign-ups are off for now; see app/site_flags.py.
        return render_signup_coming_soon()
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
    # No redirect-if-logged-in: the token is read client-side from the query
    # string, and a reset link may be used in another tab.
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
    # No email_verified_at gate, unlike dashboard_page: log out and fixing a
    # mistyped signup email must stay reachable before verification (see
    # render_account's docstring).
    if not player:
        return RedirectResponse("/login", status_code=302)
    return render_account(player)


@app.get("/verify-email-required", response_class=HTMLResponse)
def verify_email_required_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if player.email_verified_at:
        # Nothing to do here; most likely already verified in another tab or a
        # stale link.
        return RedirectResponse("/dashboard", status_code=302)
    return render_verify_email_required(player)


@app.get("/verify-email", response_class=HTMLResponse)
def verify_email_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if player and player.email_verified_at:
        # Already verified; nothing left for this page to do.
        return RedirectResponse("/dashboard", status_code=302)
    # No redirect-if-logged-out: the email link may open in a different browser
    # session. `player` is still passed so the header nav is correct.
    return render_verify_email(player)


@app.get("/api/health")
def health():
    """Proves the app is up. Doesn't touch the database (see /api/health/db), so
    it answers even if the database is briefly unreachable.
    """
    return {"status": "ok"}


@app.get("/api/health/db")
def health_db(db: Session = Depends(get_db)):
    """Proves the app can reach and query the database."""
    player_count = db.execute(text("SELECT COUNT(*) FROM players")).scalar()
    return {"status": "ok", "playerCount": player_count}


@app.get("/api/players/me", response_model=PlayerOut)
def read_current_player(game_account: GameAccount = Depends(get_current_game_account_from_api_key)):
    """The plugin calls this (`Authorization: Bearer <key>`) to confirm it is
    linked and to whom. Built by hand because email lives on the Account row
    (see app/routers/auth.py's _player_out_for).
    """
    return PlayerOut(
        id=game_account.id,
        email=game_account.account.email,
        runescape_name=game_account.runescape_name,
        account_hash=game_account.account_hash,
    )


@app.post("/api/players/me/unlink", status_code=status.HTTP_204_NO_CONTENT)
def unlink_player(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_game_account_from_api_key)):
    """Called by the plugin's "Unlink" button (API-key authenticated); see
    linking.revoke_link() for the session-authenticated counterpart.
    """
    linking.revoke_link(db, game_account)


def _stamp_storage_synced(game_account: GameAccount, storage_key: str, now: datetime) -> None:
    """Records that `storage_key` (a POSSESSION_STORAGE_KEYS entry) was just
    synced; called before each handler's db.commit() (see
    GameAccount.storage_synced_at). Reassigns the dict because SQLAlchemy
    doesn't track in-place mutation of a JSONB column.
    """
    game_account.storage_synced_at = {**(game_account.storage_synced_at or {}), storage_key: now.isoformat()}


@app.post("/api/players/me/bank", response_model=BankSyncResponse)
def sync_bank(
    payload: BankSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Called by the plugin (API-key authenticated) when the bank contents
    settle. A full replace, never a merge, so sold or withdrawn items
    disappear (see BankItem in app/models.py).
    """
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
    """The website's read of the last-synced bank snapshot
    (session-authenticated, unlike the POST above).
    """
    items = db.query(BankItem).filter(BankItem.game_account_id == game_account.id).order_by(BankItem.item_id).all()
    updated_at = items[0].updated_at if items else None
    return BankOut(items=[BankItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/inventory", response_model=InventorySyncResponse)
def sync_inventory(
    payload: InventorySyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for the 28-slot inventory."""
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
    """Same contract as GET /api/players/me/bank, for the inventory."""
    items = db.query(InventoryItem).filter(InventoryItem.game_account_id == game_account.id).order_by(InventoryItem.item_id).all()
    updated_at = items[0].updated_at if items else None
    return InventoryOut(items=[InventoryItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/equipment", response_model=EquipmentSyncResponse)
def sync_equipment(
    payload: EquipmentSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for worn equipment, keyed by
    slot.
    """
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
    """Same contract as GET /api/players/me/bank, for worn equipment."""
    items = db.query(EquipmentItem).filter(EquipmentItem.game_account_id == game_account.id).order_by(EquipmentItem.slot).all()
    updated_at = items[0].updated_at if items else None
    return EquipmentOut(items=[EquipmentItemOut.model_validate(item) for item in items], updated_at=updated_at)


@app.post("/api/players/me/potion-storage", response_model=PotionStorageSyncResponse)
def sync_potion_storage(
    payload: PotionStorageSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Same contract as POST /api/players/me/bank, for Potion Storage."""
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
    """Same contract as GET /api/players/me/bank, for potion storage."""
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
    """Same contract as POST /api/players/me/bank, for a Rune Pouch. Its own
    endpoint rather than part of /inventory's payload (see RunePouchItem in
    app/models.py).
    """
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
    """Same contract as GET /api/players/me/bank, for the rune pouch."""
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
    """Same contract as POST /api/players/me/bank, for a Seed Vault (see
    SeedVaultItem in app/models.py).
    """
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
    """Same contract as GET /api/players/me/bank, for the seed vault."""
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
    """Same contract as POST /api/players/me/bank, for a Looting Bag (see
    LootingBagItem in app/models.py).
    """
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
    """Same contract as GET /api/players/me/bank, for the looting bag."""
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
    """Same contract as POST /api/players/me/bank, for a Tackle Box (see
    TackleBoxItem in app/models.py).
    """
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
    """Same contract as GET /api/players/me/bank, for the Tackle Box."""
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
    """Same contract as POST /api/players/me/bank, for the whole PoH Costume
    Room: one endpoint for all six furniture pieces, named "poh" (see PohItem
    in app/models.py).
    """
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
    """Same contract as GET /api/players/me/bank, for the PoH Costume Room."""
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
    """Same contract as POST /api/players/me/bank, for the Forestry Kit (see
    ForestryKitItem in app/models.py).
    """
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
    """Same contract as GET /api/players/me/bank, for the Forestry Kit."""
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
    """Same contract as POST /api/players/me/bank, for the Master Scroll Book
    (see MasterScrollBookItem). The container id is unconfirmed, so real syncs
    may not arrive yet.
    """
    if len(payload.items) > MAX_MASTER_SCROLL_BOOK_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many items in one sync (max {MAX_MASTER_SCROLL_BOOK_ITEMS}).",
        )

    db.query(MasterScrollBookItem).filter(MasterScrollBookItem.game_account_id == game_account.id).delete()
    now = datetime.now(timezone.utc)
    # The Book shows its default teleport under an untradeable cosmetic id;
    # store the real scroll id (canonical_master_scroll_item_id), merging rows
    # that collapse together so the unique constraint holds.
    merged_scrolls = {}
    for item in payload.items:
        real_id = canonical_master_scroll_item_id(item.item_id, item.item_name)
        if real_id in merged_scrolls:
            merged_scrolls[real_id]["quantity"] += item.quantity
        else:
            merged_scrolls[real_id] = {"item_name": item.item_name, "quantity": item.quantity}
    for real_id, scroll in merged_scrolls.items():
        db.add(MasterScrollBookItem(
            game_account_id=game_account.id, item_id=real_id, item_name=scroll["item_name"],
            quantity=scroll["quantity"], updated_at=now,
        ))
    _stamp_storage_synced(game_account, "master_scroll_book", now)
    db.commit()

    return MasterScrollBookSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/master-scroll-book", response_model=MasterScrollBookOut)
def read_master_scroll_book(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for the Master Scroll Book."""
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
    """Same contract as POST /api/players/me/bank, for the Seed Box (see
    SeedBoxItem in app/models.py).
    """
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
    """Same contract as GET /api/players/me/bank, for the Seed Box."""
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
    """Same contract as POST /api/players/me/bank, for a Huntsman's Kit (see
    HuntsmansKitItem in app/models.py).
    """
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
    """Same contract as GET /api/players/me/bank, for the Huntsman's Kit."""
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
    """Same contract as POST /api/players/me/bank, for ONE boat's cargo; `slot`
    (1-5) picks the boat and only that slot's rows are replaced (see
    BoatCargoItem).
    """
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
    # One shared "boat_cargo" timestamp for all five slots, bumped by the latest
    # sync.
    _stamp_storage_synced(game_account, "boat_cargo", now)
    db.commit()

    return BoatCargoSyncResponse(item_count=len(payload.items))


@app.get("/api/players/me/boat-cargo", response_model=BoatCargoOut)
def read_boat_cargo(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Same contract as GET /api/players/me/bank, for all boats combined, ordered
    by slot then item id (see BoatCargoItemOut).
    """
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
    """API-key authenticated because the plugin's side panel polls it. Returns
    every POSSESSION_STORAGE_KEYS entry, `None` if never synced (distinct from
    "synced empty").
    """
    stamped = game_account.storage_synced_at or {}
    return SyncStatusOut(storages={key: stamped.get(key) for key in POSSESSION_STORAGE_KEYS})


@app.post("/api/players/me/skills", response_model=SkillsSyncResponse)
def sync_skills(
    payload: SkillsSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Full replace of the player's level+xp per skill (one JSONB column; see
    GameAccount.skills).
    """
    if len(payload.skills) > MAX_SKILLS_PER_SYNC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many skills in one sync (max {MAX_SKILLS_PER_SYNC}).",
        )
    game_account.skills = {s.skill: {"level": s.level, "xp": s.xp} for s in payload.skills}
    db.commit()
    return SkillsSyncResponse(skill_count=len(payload.skills))


def _skills_payload(game_account: GameAccount) -> dict:
    """Factored out of read_skills so both share one payload builder (like
    _character_overview_summary_payload).
    """
    return {"skills": game_account.skills or {}}


@app.get("/api/players/me/skills")
def read_skills(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The website's read of the last-synced skills snapshot."""
    return _skills_payload(game_account)


@app.post("/api/players/me/quests", response_model=QuestsSyncResponse)
def sync_quests(
    payload: QuestsSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Full replace of the player's completed quest/miniquest list (see
    GameAccount.completed_quests in app/models.py).
    """
    if len(payload.completed_quests) > MAX_QUESTS_PER_SYNC or len(payload.in_progress_quests) > MAX_QUESTS_PER_SYNC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many quests in one sync (max {MAX_QUESTS_PER_SYNC}).",
        )
    game_account.completed_quests = [q.strip() for q in payload.completed_quests if q and q.strip()]
    game_account.in_progress_quests = [q.strip() for q in payload.in_progress_quests if q and q.strip()]
    db.commit()
    return QuestsSyncResponse(quest_count=len(game_account.completed_quests))


@app.get("/api/players/me/quests")
def read_quests(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The website's read of the last-synced quests snapshot."""
    return {
        "completedQuests": game_account.completed_quests or [],
        "inProgressQuests": game_account.in_progress_quests or [],
    }


@app.post("/api/players/me/diaries", response_model=DiariesSyncResponse)
def sync_diaries(
    payload: DiariesSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Full replace of the highest completed tier per diary area (see
    GameAccount.diary_tiers).
    """
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
    """The website's read of the last-synced diary-tiers snapshot."""
    return {"diaryTiers": game_account.diary_tiers or {}}


@app.post("/api/players/me/collection-log", response_model=CollectionLogSyncResponse)
def sync_collection_log(
    payload: CollectionLogSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Full replace of every collection log item ever obtained, with quantity
    (see GameAccount.collection_log_items). Entries with an unknown item_id or
    quantity < 1 are dropped individually rather than failing the sync, so one
    stale id from an old plugin build can't zero out every sync.
    """
    if len(payload.items) > MAX_COLLECTION_LOG_ITEMS_PER_SYNC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many collection log items in one sync (max {MAX_COLLECTION_LOG_ITEMS_PER_SYNC}).",
        )
    valid_item_ids = get_valid_item_ids()
    collection_log_items = {}
    for item in payload.items:
        item_id = item.item_id
        # Some slots are announced under their placeholder variant (id + 2),
        # e.g. Yama Dossier 30805 vs structure id 30803; an unknown id whose
        # placeholder base is a log id is that slot.
        if item_id not in valid_item_ids and (item_id - 2) in valid_item_ids:
            item_id -= 2
        if item_id in valid_item_ids and item.quantity >= 1:
            collection_log_items[str(item_id)] = max(item.quantity, collection_log_items.get(str(item_id), 0))
    game_account.collection_log_items = collection_log_items
    game_account.collection_log_synced_at = datetime.now(timezone.utc)
    db.commit()
    return CollectionLogSyncResponse(item_count=len(game_account.collection_log_items))


@app.post("/api/players/me/collection-log/item", response_model=CollectionLogItemAddResponse)
def add_collection_log_item(
    payload: CollectionLogItemAddRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Marks ONE collection log item obtained when the game announces it
    (MyscapePlugin#onChatMessage), without reopening the in-game log. An add,
    never a replace: other items are untouched and a new item starts at
    quantity 1. A name that isn't exactly one log slot changes nothing and
    returns item_id null.
    """
    item_id = find_unique_item_id_by_name(payload.item_name)
    if item_id is None:
        return CollectionLogItemAddResponse(item_id=None, applied_count=0)
    items = dict(game_account.collection_log_items or {})
    if str(item_id) not in items:
        items[str(item_id)] = 1
        # Reassigned (not mutated in place) so SQLAlchemy sees the JSON column
        # change.
        game_account.collection_log_items = items
    game_account.collection_log_synced_at = datetime.now(timezone.utc)
    db.commit()
    return CollectionLogItemAddResponse(item_id=item_id, applied_count=1)


def _collection_log_payload(game_account: GameAccount) -> dict:
    """Factored out of read_collection_log so both share one payload builder."""
    return {
        "tabs": get_collection_log_tabs(),
        "obtainedItems": game_account.collection_log_items or {},
        "syncedAt": game_account.collection_log_synced_at.isoformat() if game_account.collection_log_synced_at else None,
        # Page name -> kill/completion counts (several for combo pages or raid
        # modes). {} if hiscores were never synced.
        "killCounts": collection_log_page_kill_counts(
            game_account.boss_kill_counts or {},
            game_account.clue_scroll_counts or {},
        ),
    }


@app.get("/api/players/me/collection-log")
def read_collection_log(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The website's read of the collection log: the player's state plus the
    static tab/page/item structure, in one response.
    """
    return _collection_log_payload(game_account)


@app.post("/api/players/me/character-summary", response_model=CharacterSummarySyncResponse)
def sync_character_summary(
    payload: CharacterSummarySyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Full replace of Character Overview's summary row (see
    GameAccount.character_summary_*). stat_count is always 11; it only
    satisfies MyscapeClient#syncPayload's countField contract.
    """
    game_account.character_summary_combat_level = payload.combat_level
    game_account.character_summary_total_level = payload.total_level
    game_account.character_summary_total_xp = payload.total_xp
    game_account.character_summary_quests_completed = payload.quests_completed
    game_account.character_summary_quests_total = payload.quests_total
    game_account.character_summary_achievements_completed = payload.achievements_completed
    game_account.character_summary_achievements_total = payload.achievements_total
    game_account.character_summary_combat_tasks_completed = payload.combat_tasks_completed
    game_account.character_summary_combat_tasks_total = payload.combat_tasks_total
    game_account.character_summary_collections_completed = payload.collections_completed
    game_account.character_summary_collections_total = payload.collections_total
    game_account.character_summary_combat_task_tier_completed = payload.combat_task_tier_completed
    # Optional: only overwritten when this sync sent one, so an older plugin
    # build doesn't wipe a value a newer build already synced.
    if payload.account_type is not None:
        game_account.account_type = payload.account_type
    game_account.character_summary_synced_at = datetime.now(timezone.utc)
    db.commit()
    return CharacterSummarySyncResponse(stat_count=11)


def _diary_progress_rows(game_account: GameAccount) -> list[dict]:
    """One entry per diary area with completed/total TASK counts and per-tier
    state; shared by the progress payload and the summary tile so they agree.
    """
    diary_totals = get_diary_tier_totals()
    account_diary_tiers = game_account.diary_tiers or {}
    diaries = []
    for area, tier_totals in diary_totals.items():
        highest = account_diary_tiers.get(area)
        highest_index = DIARY_TIERS.index(highest) if highest in DIARY_TIERS else -1
        completed = sum(tier_totals[t] for i, t in enumerate(DIARY_TIERS) if i <= highest_index and t in tier_totals)
        total = sum(tier_totals.values())
        tiers = {
            t: ("completed" if i <= highest_index else "not_completed")
            for i, t in enumerate(DIARY_TIERS)
        }
        diaries.append({"area": area, "completed": completed, "total": total, "tiers": tiers})
    return diaries


def _achievement_diary_tile_counts(game_account: GameAccount) -> tuple:
    """(completed, total) in TASKS for the Achievement Diaries tile. The in-game
    figure can be a tier count (e.g. 36/48), so it is computed from
    diary_tiers once synced.
    """
    if game_account.diary_tiers:
        rows = _diary_progress_rows(game_account)
        return sum(r["completed"] for r in rows), sum(r["total"] for r in rows)
    return (
        game_account.character_summary_achievements_completed,
        game_account.character_summary_achievements_total,
    )


def _combat_tasks_tile_total(game_account: GameAccount):
    """Total for the Combat Achievements tile. The in-game total varies between
    accounts (632 vs 655), so fixed per-tier totals are used once a completed
    count has synced.
    """
    if game_account.character_summary_combat_tasks_completed is None:
        return game_account.character_summary_combat_tasks_total
    return sum(get_ca_tier_totals().values())


def _character_overview_summary_payload(game_account: GameAccount) -> dict:
    """The summary-row payload, shared with the public counterpart.
    modelViewerBackgroundIndex rides along so public viewers and other devices
    pick up the background.
    """
    achievements_completed, achievements_total = _achievement_diary_tile_counts(game_account)
    return {
        "combatLevel": game_account.character_summary_combat_level,
        "totalLevel": game_account.character_summary_total_level,
        "totalXp": game_account.character_summary_total_xp,
        "questsCompleted": game_account.character_summary_quests_completed,
        "questsTotal": game_account.character_summary_quests_total,
        "achievementsCompleted": achievements_completed,
        "achievementsTotal": achievements_total,
        "combatTasksCompleted": game_account.character_summary_combat_tasks_completed,
        "combatTasksTotal": _combat_tasks_tile_total(game_account),
        "collectionsCompleted": game_account.character_summary_collections_completed,
        "collectionsTotal": game_account.character_summary_collections_total,
        "accountType": game_account.account_type,
        "modelViewerBackgroundIndex": game_account.model_viewer_background_index,
        "syncedAt": game_account.character_summary_synced_at.isoformat() if game_account.character_summary_synced_at else None,
    }


@app.get("/api/character-overview/summary")
def character_overview_summary(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Character Overview's summary row (session-authenticated). Null stats
    render as an em dash (render_character_overview in app/pages.py).
    """
    return _character_overview_summary_payload(game_account)


def _character_overview_progress_payload(game_account: GameAccount) -> dict:
    """The quests/diaries/combat-achievements payload, shared by the session and
    public endpoints. Quest names are matched case-insensitively (RuneLite and
    wiki names differ in case). diary_tiers stores only the highest completed
    tier, so lower tiers count as completed and there is no partial progress.
    Combat achievements give a completed count per tier (null if never synced)
    and the fixed total.
    """
    quest_list = get_quest_list()
    completed_lookup = {_normalize_lookup_name(n) for n in (game_account.completed_quests or [])}
    in_progress_lookup = {_normalize_lookup_name(n) for n in (game_account.in_progress_quests or [])}

    def quest_state(name: str) -> str:
        normalized = _normalize_lookup_name(name)
        if normalized in completed_lookup:
            return "completed"
        if normalized in in_progress_lookup:
            return "in_progress"
        return "not_started"

    quests = {
        group: [{"name": name, "state": quest_state(name)} for name in names]
        for group, names in quest_list.items()
    }

    diaries = _diary_progress_rows(game_account)

    ca_totals = get_ca_tier_totals()
    ca_completed = game_account.character_summary_combat_task_tier_completed
    combat_achievements = [
        {
            "tier": tier,
            "completed": (ca_completed or {}).get(tier) if ca_completed is not None else None,
            "total": total,
        }
        for tier, total in ca_totals.items()
    ]

    return {"quests": quests, "diaries": diaries, "combatAchievements": combat_achievements}


@app.get("/api/character-overview/progress")
def character_overview_progress(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Session-authenticated wrapper around _character_overview_progress_payload."""
    return _character_overview_progress_payload(game_account)


@app.post("/api/players/me/character-model", response_model=CharacterModelSyncResponse)
def sync_character_model(
    payload: CharacterModelSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Full replace of the player's 3D model export (see
    GameAccount.character_model_glb). byte_count is len(decoded file), a
    transit-integrity check.
    """
    try:
        glb_bytes = base64.b64decode(payload.glb_base64, validate=True)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="glb_base64 is not valid base64.",
        )
    if len(glb_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty model upload.",
        )
    if len(glb_bytes) > MAX_CHARACTER_MODEL_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model upload too large (max {MAX_CHARACTER_MODEL_BYTES} bytes).",
        )

    game_account.character_model_glb = glb_bytes
    game_account.character_model_synced_at = datetime.now(timezone.utc)
    db.commit()
    return CharacterModelSyncResponse(byte_count=len(glb_bytes))


def _character_overview_model_response(game_account: GameAccount) -> Response:
    """The .glb response, shared by the session-scoped and public endpoints."""
    if not game_account.character_model_glb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No character model captured yet.")
    return Response(
        content=game_account.character_model_glb,
        media_type="model/gltf-binary",
        headers={"Cache-Control": "private, max-age=0, must-revalidate"},
    )


@app.get("/api/character-overview/model")
def character_overview_model(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Character Overview's 3D-viewer payload (session-authenticated): raw .glb
    bytes (model/gltf-binary) for three.js GLTFLoader#parse. 404, not an empty
    200, when nothing is captured.
    """
    return _character_overview_model_response(game_account)


def _public_profile_payload(game_account: GameAccount) -> dict:
    """The is_public/code/url trio returned by read/update_public_profile and
    regenerate_public_profile_code.
    """
    return {
        "isPublic": game_account.is_public_profile,
        "code": game_account.public_code,
        "url": f"{_SITE_URL}/c/{game_account.public_code}" if game_account.public_code else None,
    }


@app.get("/api/players/me/public-profile")
def read_public_profile(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The settings card's initial-state read (session-authenticated)."""
    return _public_profile_payload(game_account)


@app.post("/api/players/me/public-profile")
def update_public_profile(
    payload: PublicProfileUpdateRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Flips GameAccount.is_public_profile. A code is generated the first time a
    character goes public and kept afterwards, so re-publishing reuses the
    link.
    """
    game_account.is_public_profile = payload.is_public
    if payload.is_public and not game_account.public_code:
        game_account.public_code = generate_public_code(db)
        game_account.public_code_regenerated_at = _utcnow()
    db.commit()
    return _public_profile_payload(game_account)


@app.post("/api/players/me/public-profile/regenerate-code")
def regenerate_public_profile_code(
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Issues a fresh code, abandoning the old one. Throttled to once per day
    (PUBLIC_CODE_REGENERATE_COOLDOWN in app/public_profile.py) with a 429.
    """
    remaining = regenerate_cooldown_remaining(game_account)
    if remaining is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You can generate a new link again in about {format_cooldown_remaining(remaining)}.",
        )
    game_account.public_code = generate_public_code(db)
    game_account.public_code_regenerated_at = _utcnow()
    db.commit()
    return _public_profile_payload(game_account)


@app.post("/api/players/me/model-viewer-background")
def update_model_viewer_background(
    payload: ModelViewerBackgroundUpdateRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Called by the shuffle button (shuffleBackground in app/pages.py),
    fire-and-forget. The schema checks index >= 0; the upper bound is
    _MODEL_VIEWER_BACKGROUNDS' length in app/pages.py.
    """
    if payload.index >= len(_MODEL_VIEWER_BACKGROUNDS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"index must be less than {len(_MODEL_VIEWER_BACKGROUNDS)}.",
        )
    game_account.model_viewer_background_index = payload.index
    db.commit()
    return {"index": game_account.model_viewer_background_index}


# Public, unauthenticated reads for myscape.io/c/<code>
#
# Each mirrors a session-authenticated endpoint with the same payload builder,
# resolving by public_code. A missing code and a private profile 404 identically
# (see find_public_game_account). Rate-limited per IP to bound enumeration of
# the ~28.6 million possible codes.
def _get_public_game_account_or_404(
    db: Session, code: str, viewer: Optional[GameAccount] = None
) -> GameAccount:
    """404s unless the profile is public OR the signed-in session's active
    character (`viewer`) is its owner or an accepted friend
    (find_viewable_game_account).
    """
    game_account = find_viewable_game_account(db, code, viewer)
    if game_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    return game_account


def _find_viewable_or_frozen(db: Session, code: str, viewer: Optional[GameAccount] = None):
    """Like _get_public_game_account_or_404, but a non-viewable code that is a
    permanent example (app/permanent_examples.py) returns its frozen
    PermanentExample.
    """
    game_account = find_viewable_game_account(db, code, viewer)
    if game_account is not None:
        return game_account
    frozen = find_permanent_profile(db, code)
    if frozen is not None:
        return frozen
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")


@app.get("/api/public/{code}/summary")
@limiter.limit("30/minute")
def public_character_overview_summary(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    game_account = _find_viewable_or_frozen(db, code, viewer)
    if isinstance(game_account, PermanentExample):
        return game_account.payload["summary"]
    return _character_overview_summary_payload(game_account)


@app.get("/api/public/{code}/progress")
@limiter.limit("30/minute")
def public_character_overview_progress(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    game_account = _find_viewable_or_frozen(db, code, viewer)
    if isinstance(game_account, PermanentExample):
        return game_account.payload["progress"]
    return _character_overview_progress_payload(game_account)


@app.get("/api/public/{code}/skills")
@limiter.limit("30/minute")
def public_skills(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    game_account = _find_viewable_or_frozen(db, code, viewer)
    if isinstance(game_account, PermanentExample):
        return game_account.payload["skills"]
    return _skills_payload(game_account)


@app.get("/api/public/{code}/collection-log")
@limiter.limit("30/minute")
def public_collection_log(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    game_account = _find_viewable_or_frozen(db, code, viewer)
    if isinstance(game_account, PermanentExample):
        return game_account.payload["collection-log"]
    return _collection_log_payload(game_account)


@app.get("/api/public/{code}/model")
@limiter.limit("30/minute")
def public_character_overview_model(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    game_account = _find_viewable_or_frozen(db, code, viewer)
    if isinstance(game_account, PermanentExample):
        if not game_account.model_glb:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No character model captured yet.")
        return Response(
            content=game_account.model_glb,
            media_type="model/gltf-binary",
            headers={"Cache-Control": "private, max-age=0, must-revalidate"},
        )
    return _character_overview_model_response(game_account)


@app.get("/c/{code}", response_class=HTMLResponse)
@limiter.limit("30/minute")
def public_character_overview_page(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session),
    viewer_game_account: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    """The shared-link page: render_public_character_overview (app/pages.py)
    wired to the public endpoints above. Missing and private codes 404 into
    the styled not-found page.
    """
    # Friends and the owner can open a private profile too
    # (find_viewable_game_account).
    game_account = find_viewable_game_account(db, code, viewer_game_account)
    if game_account is None:
        # A README permanent example renders from its frozen copy; the page's
        # fetches are answered the same way by /api/public/<code>/*.
        frozen = find_permanent_profile(db, code)
        if frozen is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
        return render_public_character_overview(frozen_owner(frozen.owner_name, frozen.code), viewer)
    return render_public_character_overview(game_account, viewer)


@app.get("/s/{code}", response_class=HTMLResponse)
@limiter.limit("30/minute")
def shared_content_page(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session),
):
    """Landing spot for every myscape.io/s/<code>: looks the code up once and
    dispatches on content_type to a render_*_share function. Missing and
    expired codes 404 identically (see find_valid_share in app/sharing.py).
    """
    share = find_valid_share(db, code)
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found.")
    # The share's owner, queried by FK (pages.py stays DB-free). May be None if
    # the account was deleted (no cascade on this FK); render_loot_tracker_share
    # handles that.
    if share.game_account_id is None:
        # A permanent example's frozen copy carries its owner's name alongside
        # the payload.
        owner = frozen_owner(getattr(share, "frozen_owner_name", None))
    else:
        owner = db.query(GameAccount).filter(GameAccount.id == share.game_account_id).first()
    if share.content_type == "loot_tracker":
        return render_loot_tracker_share(share, owner, viewer)
    if share.content_type == "purchase_goal":
        return render_purchase_goals_share(share, owner, viewer)
    if share.content_type == "possessions":
        return render_storages_share(share, owner, viewer)
    if share.content_type == "mindmap":
        return render_mindmap_share(share, owner, viewer)
    if share.content_type == "goal_tracking":
        return render_goal_tracking_share(share, owner, viewer)
    # Unreachable: content_type is only set by this file's create-share
    # endpoints. Fail loudly rather than guess.
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found.")


@app.post("/api/shares/{code}/import")
def import_shared_purchase_goal(
    code: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Imports someone else's shared setup as a new GearSetup of the signed-in
    player (render_purchase_goals_share in app/pages.py); the reverse of POST
    /api/gear-setups/{setup_id}/share. A signed-out visitor is sent to /signup
    by the page script.
    
    content_type="purchase_goal" makes invalid, expired and other-type codes
    404 alike. The response adds importedSetupId, which the share page stores
    under the myscape:purchaseGoals:activeSetupId localStorage key (preferred
    by Purchase Goals' loadState on boot).
    """
    share = find_valid_share(db, code, content_type="purchase_goal")
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found.")
    new_setup = import_gear_setup_from_share_payload(db, game_account, share.payload)
    db.commit()
    state = build_purchase_goals_state(db, game_account)
    state["importedSetupId"] = str(new_setup.id)
    return state


@app.post("/api/players/me/hiscores/sync")
def sync_hiscores(
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """A manual resync, the one drift-correction hatch (see app/hiscores.py).
    Other pulls only happen at link/relink; live counts come from POST
    /api/players/me/kill-counts. Session-authenticated since the data comes
    from the official Hiscores.
    """
    try:
        result = sync_hiscores_module.sync_hiscores(db, game_account)
    except sync_hiscores_module.NotLinkedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except sync_hiscores_module.HiscoresSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return {
        "boss_kill_counts": result.boss_kill_counts,
        "synced_at": result.synced_at.isoformat() if result.synced_at else None,
        "from_cache": result.from_cache,
    }


@app.post("/api/players/me/kill-counts", response_model=KillCountSyncResponse)
def sync_kill_counts(
    payload: KillCountSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Goal Tracking's live kill-count feed: one chatbox-parsed reading at a
    time, API-key-authenticated. Delegates to apply_kill_count_updates in
    app/hiscores.py, which skips unrecognized bosses.
    """
    if len(payload.updates) > MAX_KILL_COUNT_UPDATES_PER_SYNC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many updates in one sync (max {MAX_KILL_COUNT_UPDATES_PER_SYNC}).",
        )
    applied_count = sync_hiscores_module.apply_kill_count_updates(db, game_account, payload.updates)
    return KillCountSyncResponse(applied_count=applied_count)


@app.post("/api/players/me/runescape-name", response_model=RunescapeNameSyncResponse)
def sync_runescape_name(
    payload: RunescapeNameSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Keeps GameAccount.runescape_name current after an in-game name change.
    Written only when account_hash matches this key's linked account: the id,
    not the name, is the identity.
    """
    if game_account.account_hash != payload.account_hash:
        return RunescapeNameSyncResponse(updated=0)
    if game_account.runescape_name == payload.runescape_name:
        return RunescapeNameSyncResponse(updated=0)
    game_account.runescape_name = payload.runescape_name
    db.commit()
    return RunescapeNameSyncResponse(updated=1)


@app.post("/api/players/me/loot", response_model=LootSyncResponse)
def sync_loot(
    payload: LootSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Records loot events as they happen. Insert-if-new, not delete-and-replace;
    dedup keys on the client-generated event_id (sync_loot_events in
    app/loot.py).
    """
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
    """The Loot Tracker's polled state (build_loot_state in app/loot.py). `range`
    is a RANGE_PRESETS key or "custom"; custom `start`/`end` are "YYYY-MM-DD"
    dates (both inclusive) or ISO-8601 timestamps (a clicked bar's bucket; see
    parse_loot_range_bound). Unrecognized or incomplete ranges fall back to
    resolve_range's 24-hour default. No response_model (see LootState).
    """
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


@app.post("/api/players/me/loot/share")
def create_loot_share(
    payload: LootShareCreateRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Freezes the selected range into a SharedContent row
    (build_loot_share_snapshot in app/loot.py) and returns a
    myscape.io/s/<code> link. Unthrottled: GET /s/{code} is the rate-limited
    surface.
    """
    start_dt = None
    end_dt = None
    if payload.range == "custom":
        try:
            if payload.start:
                start_dt = parse_loot_range_bound(payload.start, is_end=False)
            if payload.end:
                end_dt = parse_loot_range_bound(payload.end, is_end=True)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start/end must be YYYY-MM-DD dates or ISO-8601 timestamps.",
            )
    range_start, range_end = resolve_range(payload.range, start_dt, end_dt)
    snapshot = build_loot_share_snapshot(db, game_account, range_start, range_end)
    code = generate_share_code(db)
    share = SharedContent(
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        code=code,
        content_type="loot_tracker",
        payload=snapshot,
        expires_at=_utcnow() + SHARE_DEFAULT_LIFETIME,
    )
    db.add(share)
    db.commit()
    return {"code": code, "url": f"{_SITE_URL}/s/{code}"}


@app.post("/api/players/me/loot/hidden-npcs")
def hide_loot_npc(payload: HideLootNpcRequest, db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Hides one NPC from Loot Tracker (the eye button on an NPC tile); see
    set_npc_hidden in app/loot.py.
    """
    set_npc_hidden(db, game_account, payload.name, True)
    return {"ok": True}


@app.delete("/api/players/me/loot/hidden-npcs")
def unhide_loot_npc(payload: HideLootNpcRequest, db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Reverses hide_loot_npc."""
    set_npc_hidden(db, game_account, payload.name, False)
    return {"ok": True}


@app.post("/api/players/me/loot/hidden-items")
def hide_loot_item(payload: HideLootItemRequest, db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Hides one item from Loot Tracker (see set_item_hidden in app/loot.py)."""
    set_item_hidden(db, game_account, payload.item_id, payload.item_name, True)
    return {"ok": True}


@app.delete("/api/players/me/loot/hidden-items")
def unhide_loot_item(payload: HideLootItemRequest, db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Reverses hide_loot_item."""
    set_item_hidden(db, game_account, payload.item_id, payload.item_name, False)
    return {"ok": True}


@app.get("/api/items/search", response_model=ItemSearchResponse)
def item_search(q: str = "", game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Backs the gear-setup slot picker's search (search_items in
    app/purchase_goals.py); session-authenticated.
    """
    return ItemSearchResponse(results=search_items(q))


@app.get("/api/npcs/search", response_model=NpcSearchResponse)
def npc_search(q: str = "", game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Backs the Mindmaps KC goal's NPC search field (app/npc_names.py);
    session-authenticated.
    """
    return NpcSearchResponse(results=search_npc_names(q))


@app.get("/api/quests/search", response_model=QuestSearchResponse)
def quest_search(q: str = "", game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Backs the Mindmaps QUEST goal's search field (app/quest_names.py);
    session-authenticated.
    """
    return QuestSearchResponse(results=search_quest_names(q))


@app.get("/dashboard/purchase-goals", response_class=HTMLResponse)
def purchase_goals_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_purchase_goals(player)


@app.get("/dashboard/loot-tracker", response_class=HTMLResponse)
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


@app.get("/dashboard/storages-viewer", response_class=HTMLResponse)
def possessions_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_possessions(player)


@app.get("/dashboard/goal-tracking", response_class=HTMLResponse)
def goal_tracking_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    """No sync on page load: KC data is seeded at link time and kept current by
    chatbox updates, so boss_kill_counts is read as-is.
    """
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_goal_tracking(player)


@app.get("/dashboard/help-and-support", response_class=HTMLResponse)
def help_support_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    """Same login/verified gate as every other /dashboard/* page (see
    render_help_support in app/pages.py).
    """
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_help_support(player)


@app.get("/dashboard/character-overview", response_class=HTMLResponse)
def character_overview_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    """Same login/verified gate as every other /dashboard/* page (see
    render_character_overview in app/pages.py).
    """
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_character_overview(player)


@app.get("/api/possessions/search-items", response_model=ItemSearchResponse)
def possessions_item_search(q: str = "", game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Backs the tracker "add an item" search; every result has a real item id
    (search_trackable_items), which a tracker needs.
    """
    return ItemSearchResponse(results=search_trackable_items(q))


@app.get("/api/possessions/summary")
def possessions_summary(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Section 3's payload: every owned item, priced and broken down by location
    (build_possessions_summary). No response_model.
    """
    return build_possessions_summary(db, game_account)


@app.get("/api/possessions/trackers")
def possessions_trackers(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Sections 1/2's payload: the minimum and maximum trackers, each resolved
    against a live owned quantity (build_trackers_state in
    app/possessions.py).
    """
    return build_trackers_state(db, game_account)


@app.post("/api/possessions/trackers", status_code=status.HTTP_201_CREATED)
def create_possession_tracker(
    payload: PossessionTrackerIn,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Adds one min or max tracker. item_name is the untradeable-item display
    fallback (see BankItem). Re-adding an existing (kind, item_id) updates its
    target.
    """
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
    """Edits a tracker's target quantity in place; swapping the item is
    delete-and-recreate (see PossessionTrackerUpdate in app/schemas.py).
    """
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
    """Pins one item to the top of section 3 (see PinnedPossessionItem).
    Idempotent.
    """
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
    """Unpins one item; idempotent like pin_possession_item."""
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
    """Switches one storage source off (see HiddenPossessionStorage); its items
    stop counting toward section 3 and tracker quantities.
    """
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
    """Reverses hide_possession_storage; idempotent like unpin_possession_item."""
    if storage_key not in POSSESSION_STORAGE_KEYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown storage.")
    set_storage_hidden(db, game_account, storage_key, False)
    return {"hiddenStorageKeys": sorted(hidden_storage_keys(db, game_account))}


@app.post("/api/possessions/share")
def create_possessions_share(
    payload: PossessionShareCreateRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Freezes section 3 into a SharedContent row
    (build_possessions_share_snapshot) and returns a myscape.io/s/<code> link.
    """
    snapshot = build_possessions_share_snapshot(db, game_account, payload.locations)
    code = generate_share_code(db)
    share = SharedContent(
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        code=code,
        content_type="possessions",
        payload=snapshot,
        expires_at=_utcnow() + SHARE_DEFAULT_LIFETIME,
    )
    db.add(share)
    db.commit()
    return {"code": code, "url": f"{_SITE_URL}/s/{code}"}


@app.get("/api/possessions/views")
def list_possession_views(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Every saved Storages Viewer view (build_possession_views in
    app/possessions.py), in reorder-strip order.
    """
    return {"views": build_possession_views(db, game_account)}


@app.post("/api/possessions/views", status_code=status.HTTP_201_CREATED)
def create_possession_view(
    payload: PossessionViewSaveRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Saves the current filter/sort setup as a new named view, always appended;
    renaming/overwriting is PATCH .../{view_id}.
    """
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
    """Saves a reorder of the saved-views strip (payload.order is the complete id
    list; omitted ids keep their sort_order, unowned ids are ignored).
    """
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
    """Renames a saved view, replaces its stored config, or both (see
    PossessionViewUpdateRequest in app/schemas.py).
    """
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
    """The Purchase Goals page's polled state (build_purchase_goals_state in
    app/purchase_goals.py): every setup priced against synced storage, plus
    coins and wiki errors. No response_model (see GearSetupsState).
    """
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


def _duplicate_name(name: str) -> str:
    """"<name> (copy)", with the base trimmed to fit the 60-character name limit
    so the "(copy)" marker always survives.
    """
    suffix = " (copy)"
    base = (name or "").strip()
    if len(base) + len(suffix) > 60:
        base = base[: 60 - len(suffix)].rstrip()
    return base + suffix


@app.post("/api/gear-setups/{setup_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_gear_setup(
    setup_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """A full copy of one of the player's setups, landing at the END of the list
    (sort_order NULL). The response is the GET /api/gear-setups shape plus
    newSetupId.
    """
    source = _get_owned_gear_setup(db, game_account, setup_id)
    new_setup = GearSetup(
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        name=_duplicate_name(source.name),
        icon=copy.deepcopy(source.icon),
        equipment=copy.deepcopy(source.equipment or {}),
        inventory=copy.deepcopy(source.inventory or [None] * INVENTORY_SIZE),
        still_to_purchase_sort_mode=source.still_to_purchase_sort_mode or "low_to_high",
        still_to_purchase_custom_order=copy.deepcopy(source.still_to_purchase_custom_order),
    )
    db.add(new_setup)
    db.commit()
    state = build_purchase_goals_state(db, game_account)
    state["newSetupId"] = str(new_setup.id)
    return state


@app.put("/api/gear-setups/order")
def set_gear_setup_order(
    payload: SetGearSetupOrderRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Saves a reorder of the gear setup LIST. payload.order is the complete id
    list; omitted ids keep their sort_order and unowned ids are ignored.
    """
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
    """Sets (or, with icon omitted/null, clears) the cosmetic icon next to a
    setup's total cost; never affects cost or ownership (see GearSetup in
    app/models.py).
    """
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
    """Fills (or clears) one equipment or inventory slot. Stores what was sent,
    since pricing and ownership are computed on read, except that a plain
    untradeable item matching a recipe (app/recipes.py) is auto-expanded into
    a "combo" so e.g. "Neitiznot faceguard" can be selected directly.
    """
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
            # Skipped for anything with a linked GE value in the ported RuneLite
            # table (has_derived_price in app/purchase_goals.py): it is priced
            # from that at read time, and wiki recipe data for some is wrong or
            # missing.
            mapping, _ = get_mapping()
            auto_components = expand_recipe_components(payload.item.item_name, mapping)
            if auto_components:
                stored_item["components"] = auto_components

    if payload.slot_type == "equipment":
        if payload.slot not in GEAR_SETUP_EQUIPMENT_SLOTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"slot must be one of {GEAR_SETUP_EQUIPMENT_SLOTS}"
            )
        # New dict, not an in-place mutation; see the IMPORTANT note on
        # GearSetup in app/models.py (JSONB tracking).
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
    """Slot-shape validation shared with set_gear_slot, applied by
    move_gear_slot_item to both source and destination slots.
    """
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
    """Drag-and-drop: moves the item between slots (equipment or inventory),
    swapping with an occupied destination. Works on the raw stored shape so a
    combo's components move unchanged.
    """
    setup = _get_owned_gear_setup(db, game_account, setup_id)

    _check_gear_slot(payload.from_slot_type, payload.from_slot)
    _check_gear_slot(payload.to_slot_type, payload.to_slot)

    if payload.from_slot_type == payload.to_slot_type and payload.from_slot == payload.to_slot:
        # Dropped a slot onto itself; nothing to do.
        return build_purchase_goals_state(db, game_account)

    # Fresh dict/list, not in-place mutation; see the IMPORTANT note on
    # GearSetup in app/models.py.
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
    """Switches the active "Still to Purchase" sort. Leaves
    still_to_purchase_custom_order untouched so a dragged order survives mode
    switches.
    """
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
    """Saves a reorder of a setup's "Still to Purchase" list (payload.order is
    the full displayed list). Also switches to "custom" mode as a backstop.
    """
    setup = _get_owned_gear_setup(db, game_account, setup_id)
    setup.still_to_purchase_sort_mode = "custom"
    setup.still_to_purchase_custom_order = [
        {"slotType": entry.slot_type, "slot": entry.slot} for entry in payload.order
    ]
    db.commit()
    return build_purchase_goals_state(db, game_account)


@app.post("/api/gear-setups/{setup_id}/share")
def create_purchase_goal_share(
    setup_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Freezes one gear setup into a SharedContent row
    (build_purchase_goal_share_snapshot in app/purchase_goals.py) and returns
    a myscape.io/s/<code> link; same posture as POST
    /api/players/me/loot/share.
    """
    setup = _get_owned_gear_setup(db, game_account, setup_id)
    snapshot = build_purchase_goal_share_snapshot(setup)
    code = generate_share_code(db)
    share = SharedContent(
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        code=code,
        content_type="purchase_goal",
        payload=snapshot,
        expires_at=_utcnow() + SHARE_DEFAULT_LIFETIME,
    )
    db.add(share)
    db.commit()
    return {"code": code, "url": f"{_SITE_URL}/s/{code}"}


def _build_goal_context(db: Session, game_account: GameAccount) -> dict:
    """Everything goal-node auto-completion (evaluate_completion in
    app/mindmaps.py) checks nodes against, gathered once per request. Lives
    here because it needs app/purchase_goals.py and app/loot.py, which
    app/mindmaps.py avoids importing to prevent a circular import.
    """
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
    """Every mindmap with its full node list (build_mindmaps_state in
    app/mindmaps.py). No response_model, like GET /api/gear-setups (see
    MindMapsState in app/schemas.py).
    """
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


@app.post("/api/mindmaps/{mindmap_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_mindmap(
    mindmap_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """A full copy of one of the player's mindmaps. Node ids are reused since
    they're only referenced within their own mindmap. The response adds
    newMindmapId.
    """
    source = _get_owned_mindmap(db, game_account, mindmap_id)
    new_mindmap = MindMap(
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        name=_duplicate_name(source.name),
        nodes=copy.deepcopy(source.nodes or []),
    )
    db.add(new_mindmap)
    db.commit()
    state = build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))
    state["newMindmapId"] = str(new_mindmap.id)
    return state


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
    # See add_node in app/mindmaps.py; returned with the full state so the
    # client can select the new node without diffing.
    state["newNodeId"] = new_node_id
    return state


@app.post("/api/mindmaps/{mindmap_id}/nodes/shared-child", status_code=status.HTTP_201_CREATED)
def add_mindmap_shared_child(
    mindmap_id: str,
    payload: AddMindMapSharedChildRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """The node canvas's shift-click multi-select: adds one shared child below
    two or more existing nodes (add_shared_child in app/mindmaps.py).
    """
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
    """Restores a mindmap's whole node tree to a prior snapshot, for the canvas's
    undo/redo buttons (replace_nodes in app/mindmaps.py).
    """
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
    """Saves a node's goal fields (see clean_goal in app/mindmaps.py); also used
    by the gray node's "Complete" button. Incomplete submissions get a 400.
    payload.note is applied via update_node, so goal and note persist as one
    undo step.
    """
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


@app.post("/api/mindmaps/{mindmap_id}/share")
def create_mindmap_share(
    mindmap_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Freezes one mindmap into a new SharedContent row
    (build_mindmap_share_snapshot in app/mindmaps.py) and returns a
    myscape.io/s/<code> link. Same posture as POST /api/players/me/loot/share.
    """
    mindmap = _get_owned_mindmap(db, game_account, mindmap_id)
    snapshot = build_mindmap_share_snapshot(mindmap, _build_goal_context(db, game_account))
    code = generate_share_code(db)
    share = SharedContent(
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        code=code,
        content_type="mindmap",
        payload=snapshot,
        expires_at=_utcnow() + SHARE_DEFAULT_LIFETIME,
    )
    db.add(share)
    db.commit()
    return {"code": code, "url": f"{_SITE_URL}/s/{code}"}


@app.post("/api/mindmaps/shares/{code}/import")
def import_shared_mindmap(
    code: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Imports someone else's shared mindmap as a new MindMap of the signed-in
    player (render_mindmap_share in app/pages.py); the reverse of POST
    /api/mindmaps/{mindmap_id}/share. A signed-out visitor is sent to /signup
    by the page script.
    
    content_type="mindmap" makes invalid, expired and other-type codes 404
    alike. The response adds importedMindmapId, which the share page stores
    under the myscape:mindmaps:activeMindmapId localStorage key (preferred by
    loadState on boot).
    """
    share = find_valid_share(db, code, content_type="mindmap")
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found.")
    new_mindmap = import_mindmap_from_share_payload(db, game_account, share.payload)
    db.commit()
    state = build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))
    state["importedMindmapId"] = str(new_mindmap.id)
    return state


def _goal_out(goal: Goal, context: dict) -> GoalOut:
    return GoalOut(
        id=goal.id,
        goal_type=goal.goal_type,
        target_name=goal.target_name,
        metric=goal.metric,
        target_value=goal.target_value,
        current_value=goals_module.current_value(goal, context),
        progress_pct=goals_module.progress_pct(goal, context),
        target_display=goals_module.target_display(goal),
        item_icon=item_icon_url(goal.item_id),
        is_recurring=goal.is_recurring,
        recur_interval=goal.recur_interval,
        recur_unit=goal.recur_unit,
        recur_period_start=goal.recur_period_start,
        baseline_value=goal.baseline_value,
        sort_order=goal.sort_order,
        created_at=goal.created_at,
    )


@app.get("/api/goals", response_model=GoalsResponse)
def list_goals(
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Every goal, oldest first, with progress computed live (app/goals.py); Goal
    Tracking's page polls this. Always in created_at order; the client
    re-sorts per sort tab, and sort_mode rides along for the first paint. Also
    where recurring goals roll their period forward
    (maybe_roll_recurring_period); committed once, only if a goal rolled.
    """
    goals = db.query(Goal).filter(Goal.game_account_id == game_account.id).order_by(Goal.created_at).all()
    context = goals_module.build_progress_context(db, game_account)
    rolled = False
    for goal in goals:
        if goals_module.maybe_roll_recurring_period(goal, context):
            rolled = True
    if rolled:
        db.commit()
    return GoalsResponse(
        goals=[_goal_out(goal, context) for goal in goals],
        sort_mode=game_account.goal_sort_mode,
    )


@app.put("/api/goals/sort-mode", response_model=GoalsResponse)
def set_goal_sort_mode(
    payload: SetGoalSortModeRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Switches the active #gtSortTabs button, persisted in
    GameAccount.goal_sort_mode. Leaves Goal.sort_order alone, so "custom"
    replays the last dragged order (see set_goal_order).
    """
    game_account.goal_sort_mode = payload.sort_mode
    db.commit()
    goals = db.query(Goal).filter(Goal.game_account_id == game_account.id).order_by(Goal.created_at).all()
    context = goals_module.build_progress_context(db, game_account)
    return GoalsResponse(
        goals=[_goal_out(goal, context) for goal in goals],
        sort_mode=game_account.goal_sort_mode,
    )


@app.put("/api/goals/reorder", response_model=GoalsResponse)
def set_goal_order(
    payload: GoalReorderRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Saves a reorder of the goal list in "custom" mode (same rules as
    set_gear_setup_order); also switches to "custom" as a backstop.
    """
    owned_goals = {
        str(g.id): g
        for g in db.query(Goal).filter(Goal.game_account_id == game_account.id).all()
    }
    for index, goal_id in enumerate(payload.order):
        goal = owned_goals.get(goal_id)
        if goal is not None:
            goal.sort_order = float(index)
    game_account.goal_sort_mode = "custom"
    db.commit()
    goals = sorted(owned_goals.values(), key=lambda g: g.created_at)
    context = goals_module.build_progress_context(db, game_account)
    return GoalsResponse(
        goals=[_goal_out(goal, context) for goal in goals],
        sort_mode=game_account.goal_sort_mode,
    )


@app.post("/api/goals", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
def create_goal(
    payload: GoalCreateRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Adds one goal. Validation is in app.goals.clean_new_goal and
    clean_target_mode; a GoalValidationError becomes a 400.
    
    A recurring goal's first period starts now, baselined against its current
    absolute_value() so it opens at 0/target_value. payload.recur_start_at
    replaces "now" but is still baselined against the live value (no history
    exists for a past start), so it only phase-locks the period boundaries. A
    one-time GAIN-mode goal gets the same baseline (see Goal.baseline_value).
    """
    try:
        cleaned = goals_module.clean_new_goal(
            payload.goal_type,
            payload.target_name,
            payload.metric,
            payload.target_value,
            payload.item_id,
            payload.is_recurring,
            payload.recur_interval,
            payload.recur_unit,
        )
        target_mode = goals_module.clean_target_mode(
            cleaned["goal_type"], cleaned["metric"], cleaned["is_recurring"], payload.target_mode
        )
    except goals_module.GoalValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    context = goals_module.build_progress_context(db, game_account)
    goal = Goal(game_account_id=game_account.id, **cleaned)
    if goal.is_recurring:
        recur_start_at = payload.recur_start_at
        # Assumed UTC if tz-naive: mixing naive and aware datetimes in
        # maybe_roll_recurring_period (app/goals.py) raises TypeError. The
        # wizard always sends ISO-8601 UTC, so only raw API calls hit this.
        if recur_start_at is not None and recur_start_at.tzinfo is None:
            recur_start_at = recur_start_at.replace(tzinfo=timezone.utc)
        goal.recur_period_start = recur_start_at or _utcnow()
        goal.baseline_value = goals_module.absolute_value(goal, context)
    elif target_mode == "gain":
        goal.baseline_value = goals_module.absolute_value(goal, context)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _goal_out(goal, context)


@app.delete("/api/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    try:
        goal_uuid = uuid.UUID(goal_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")
    goal = (
        db.query(Goal)
        .filter(Goal.id == goal_uuid, Goal.game_account_id == game_account.id)
        .first()
    )
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")
    db.delete(goal)
    db.commit()



def build_goal_tracking_share_snapshot(db: Session, game_account: GameAccount) -> dict:
    """Freezes EVERY goal of game_account into the payload POST /api/goals/share
    stores. Frozen as-is, without rolling recurring periods forward as
    list_goals does. model_dump(mode="json") makes uuid/datetime fields plain
    strings so the JSONB payload and its re-import
    (goals_module.import_goals_from_share_payload) round-trip. sortMode rides
    along for the share page.
    """
    goals = db.query(Goal).filter(Goal.game_account_id == game_account.id).order_by(Goal.created_at).all()
    context = goals_module.build_progress_context(db, game_account)
    return {
        "goals": [_goal_out(goal, context).model_dump(mode="json") for goal in goals],
        "sortMode": game_account.goal_sort_mode,
    }


@app.post("/api/goals/share")
def create_goal_tracking_share(
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Freezes this account's ENTIRE goal list into a SharedContent row and
    returns a myscape.io/s/<code> link; same posture as POST
    /api/mindmaps/{mindmap_id}/share.
    """
    snapshot = build_goal_tracking_share_snapshot(db, game_account)
    code = generate_share_code(db)
    share = SharedContent(
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        code=code,
        content_type="goal_tracking",
        payload=snapshot,
        expires_at=_utcnow() + SHARE_DEFAULT_LIFETIME,
    )
    db.add(share)
    db.commit()
    return {"code": code, "url": f"{_SITE_URL}/s/{code}"}


@app.post("/api/goals/shares/{code}/import")
def import_shared_goals(
    code: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Appends someone else's shared goal list to this player's goals
    (render_goal_tracking_share in app/pages.py); the reverse of POST
    /api/goals/share. GAIN-mode and recurring goals get a fresh baseline
    against THIS account (see goals_module.import_goals_from_share_payload). A
    signed-out visitor is sent to /signup by the page script.
    
    content_type="goal_tracking" makes invalid, expired and other-type codes
    404 alike.
    """
    share = find_valid_share(db, code, content_type="goal_tracking")
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found.")
    goals_module.import_goals_from_share_payload(db, game_account, share.payload)
    db.commit()
    goals = db.query(Goal).filter(Goal.game_account_id == game_account.id).order_by(Goal.created_at).all()
    context = goals_module.build_progress_context(db, game_account)
    return GoalsResponse(
        goals=[_goal_out(goal, context) for goal in goals],
        sort_mode=game_account.goal_sort_mode,
    )

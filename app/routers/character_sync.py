"""Plugin sync endpoints for skills, quests, diaries, collection log, character summary/model, hiscores, kill counts and name."""
import base64
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import hiscores as sync_hiscores_module
from app.auth import (
    get_current_game_account_from_api_key,
    get_current_verified_game_account_from_session,
)
from app.collectionlog import find_unique_item_id_by_name, get_valid_item_ids
from app.database import get_db
from app.models import GameAccount
from app.routers.shared import _collection_log_payload, _skills_payload
from app.schemas import (
    CharacterModelSyncRequest,
    CharacterModelSyncResponse,
    CharacterSummarySyncRequest,
    CharacterSummarySyncResponse,
    CollectionLogItemAddRequest,
    CollectionLogItemAddResponse,
    CollectionLogSyncRequest,
    CollectionLogSyncResponse,
    DiariesSyncRequest,
    DiariesSyncResponse,
    KillCountSyncRequest,
    KillCountSyncResponse,
    QuestsSyncRequest,
    QuestsSyncResponse,
    RunescapeNameSyncRequest,
    RunescapeNameSyncResponse,
    SkillsSyncRequest,
    SkillsSyncResponse,
)

router = APIRouter()


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
# Same as MAX_LOOT_EVENTS_PER_SYNC: the plugin syncs one kill count at a time.
MAX_KILL_COUNT_UPDATES_PER_SYNC = 20
# One composited player model is well under 1 MB as GLB; 8 MB raw (~10.7 MB
# base64) rejects malformed or hostile requests.
MAX_CHARACTER_MODEL_BYTES = 8 * 1024 * 1024


@router.post("/api/players/me/skills", response_model=SkillsSyncResponse)
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


@router.get("/api/players/me/skills")
def read_skills(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The website's read of the last-synced skills snapshot."""
    return _skills_payload(game_account)


@router.post("/api/players/me/quests", response_model=QuestsSyncResponse)
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


@router.get("/api/players/me/quests")
def read_quests(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The website's read of the last-synced quests snapshot."""
    return {
        "completedQuests": game_account.completed_quests or [],
        "inProgressQuests": game_account.in_progress_quests or [],
    }


@router.post("/api/players/me/diaries", response_model=DiariesSyncResponse)
def sync_diaries(
    payload: DiariesSyncRequest,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_game_account_from_api_key),
):
    """Full replace of the highest completed tier per diary area (see
    GameAccount.diary_tiers) and, when sent, of the per-tier task counts (see
    GameAccount.diary_task_counts).
    """
    if len(payload.diary_tiers) > MAX_DIARY_AREAS_PER_SYNC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many diary areas in one sync (max {MAX_DIARY_AREAS_PER_SYNC}).",
        )
    game_account.diary_tiers = {d.area: d.tier for d in payload.diary_tiers}
    if payload.task_counts is not None:
        if len(payload.task_counts) > MAX_DIARY_AREAS_PER_SYNC:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Too many diary areas in one sync (max {MAX_DIARY_AREAS_PER_SYNC}).",
            )
        game_account.diary_task_counts = {
            c.area: {"easy": c.easy, "medium": c.medium, "hard": c.hard, "elite": c.elite}
            for c in payload.task_counts
        }
    db.commit()
    return DiariesSyncResponse(area_count=len(payload.diary_tiers))


@router.get("/api/players/me/diaries")
def read_diaries(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The website's read of the last-synced diary-tiers snapshot."""
    return {"diaryTiers": game_account.diary_tiers or {}}


@router.post("/api/players/me/collection-log", response_model=CollectionLogSyncResponse)
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


@router.post("/api/players/me/collection-log/item", response_model=CollectionLogItemAddResponse)
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


@router.get("/api/players/me/collection-log")
def read_collection_log(game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """The website's read of the collection log: the player's state plus the
    static tab/page/item structure, in one response.
    """
    return _collection_log_payload(game_account)


@router.post("/api/players/me/character-summary", response_model=CharacterSummarySyncResponse)
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


@router.post("/api/players/me/character-model", response_model=CharacterModelSyncResponse)
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


@router.post("/api/players/me/hiscores/sync")
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


@router.post("/api/players/me/kill-counts", response_model=KillCountSyncResponse)
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


@router.post("/api/players/me/runescape-name", response_model=RunescapeNameSyncResponse)
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

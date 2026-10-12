"""Mindmaps endpoints."""
import copy
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_verified_game_account_from_session
from app.database import get_db
from app.item_ids import find_item_ids
from app.loot import kc_counts_by_player
from app.mindmaps import (
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
    GameAccount,
    MindMap,
    SharedContent,
    _utcnow,
)
from app.pages import _SITE_URL
from app.purchase_goals import (
    COINS_ITEM_ID,
    build_owned_pools,
)
from app.routers.shared import _duplicate_name
from app.schemas import (
    AddMindMapNodeRequest,
    AddMindMapSharedChildRequest,
    CreateMindMapRequest,
    RenameMindMapRequest,
    ReplaceMindMapNodesRequest,
    SetMindMapNodeGoalRequest,
    UpdateMindMapNodeRequest,
)
from app.sharing import SHARE_DEFAULT_LIFETIME, find_valid_share, generate_share_code

router = APIRouter()


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


@router.get("/api/mindmaps")
def list_mindmaps(db: Session = Depends(get_db), game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Every mindmap with its full node list (build_mindmaps_state in
    app/mindmaps.py). No response_model, like GET /api/gear-setups (see
    MindMapsState in app/schemas.py).
    """
    return build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))


@router.post("/api/mindmaps", status_code=status.HTTP_201_CREATED)
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


@router.patch("/api/mindmaps/{mindmap_id}")
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


@router.post("/api/mindmaps/{mindmap_id}/duplicate", status_code=status.HTTP_201_CREATED)
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


@router.delete("/api/mindmaps/{mindmap_id}")
def delete_mindmap(
    mindmap_id: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    mindmap = _get_owned_mindmap(db, game_account, mindmap_id)
    db.delete(mindmap)
    db.commit()
    return build_mindmaps_state(db, game_account, _build_goal_context(db, game_account))


@router.post("/api/mindmaps/{mindmap_id}/nodes", status_code=status.HTTP_201_CREATED)
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


@router.post("/api/mindmaps/{mindmap_id}/nodes/shared-child", status_code=status.HTTP_201_CREATED)
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


@router.put("/api/mindmaps/{mindmap_id}/nodes")
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


@router.patch("/api/mindmaps/{mindmap_id}/nodes/{node_id}")
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


@router.patch("/api/mindmaps/{mindmap_id}/nodes/{node_id}/goal")
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


@router.delete("/api/mindmaps/{mindmap_id}/nodes/{node_id}")
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


@router.post("/api/mindmaps/{mindmap_id}/share")
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


@router.post("/api/mindmaps/shares/{code}/import")
def import_shared_mindmap(
    code: str,
    db: Session = Depends(get_db),
    game_account: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Imports someone else's shared mindmap as a new MindMap of the signed-in
    player (render_mindmap_share in app/pages/); the reverse of POST
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

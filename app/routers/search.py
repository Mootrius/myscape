"""Item, NPC and quest search endpoints."""
from fastapi import APIRouter, Depends

from app.auth import get_current_verified_game_account_from_session
from app.models import GameAccount
from app.npc_names import search_npc_names
from app.purchase_goals import search_items
from app.quest_names import search_quest_names
from app.schemas import (
    ItemSearchResponse,
    NpcSearchResponse,
    QuestSearchResponse,
)

router = APIRouter()


@router.get("/api/items/search", response_model=ItemSearchResponse)
def item_search(q: str = "", game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Backs the gear-setup slot picker's search (search_items in
    app/purchase_goals.py); session-authenticated.
    """
    return ItemSearchResponse(results=search_items(q))


@router.get("/api/npcs/search", response_model=NpcSearchResponse)
def npc_search(q: str = "", game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Backs the Mindmaps KC goal's NPC search field (app/npc_names.py);
    session-authenticated.
    """
    return NpcSearchResponse(results=search_npc_names(q))


@router.get("/api/quests/search", response_model=QuestSearchResponse)
def quest_search(q: str = "", game_account: GameAccount = Depends(get_current_verified_game_account_from_session)):
    """Backs the Mindmaps QUEST goal's search field (app/quest_names.py);
    session-authenticated.
    """
    return QuestSearchResponse(results=search_quest_names(q))

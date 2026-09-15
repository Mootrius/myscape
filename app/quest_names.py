"""Quest/miniquest name lookup for the Mindmaps QUEST goal's search
field.

Backed by a static JSON snapshot (app/data/quest_names.json) built
from the OSRS Wiki's Category:Quests and Category:Miniquests
membership lists -- see scripts/fetch_quest_names.py for how it's
generated/regenerated. Like item_ids.py's item snapshot, this only
changes when Jagex releases new quests/miniquests, so a bundled
snapshot refreshed by manually re-running that script is plenty.

This is purely a name list for the search field to offer -- see
app/mindmaps.py's evaluate_completion for how a quest goal is actually
scored (a case-insensitive match against the player's own synced
completed-quests list, not against this snapshot).
"""
import json
import pathlib
from typing import List, Optional

QUEST_NAMES_PATH = pathlib.Path(__file__).resolve().parent / "data" / "quest_names.json"

_quest_names: Optional[List[str]] = None


def get_quest_names() -> List[str]:
    global _quest_names
    if _quest_names is None:
        try:
            with open(QUEST_NAMES_PATH, "r", encoding="utf-8") as f:
                _quest_names = json.load(f)
        except (OSError, json.JSONDecodeError):
            _quest_names = []
    return _quest_names


def search_quest_names(query: str, limit: int = 20) -> List[str]:
    """Fuzzy-searches the quest/miniquest name snapshot, using the same
    startswith-then-contains scheme as search_item_names in
    app/item_ids.py."""
    q = (query or "").strip().lower()
    if not q:
        return []
    starts, contains = [], []
    for name in get_quest_names():
        lname = name.lower()
        if lname.startswith(q):
            starts.append(name)
        elif q in lname:
            contains.append(name)
    starts.sort(key=len)
    contains.sort(key=len)
    return (starts + contains)[:limit]

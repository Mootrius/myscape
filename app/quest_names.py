"""Quest/miniquest name lookup for the Mindmaps QUEST goal's search field.

Backed by a static snapshot (app/data/quest_names.json) from the OSRS Wiki's
Category:Quests and Category:Miniquests; see scripts/fetch_quest_names.py to
regenerate. Like item_ids.py, it changes only when quests are released.

Purely a name list. A quest goal is scored by a case-insensitive match against
the player's synced completed-quests list (evaluate_completion in
app/mindmaps.py).
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
    """Fuzzy name search as in search_item_names (app/item_ids.py): startswith,
    then contains.
    """
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

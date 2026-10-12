"""Killable-NPC name lookup for the Mindmaps KC goal's search field.

Backed by a static snapshot (app/data/npc_names.json) from the OSRS Wiki's
"Bucket" monster infobox table, filtered to NPCs with a positive combat level;
see scripts/fetch_npc_names.py to regenerate. Like item_ids.py, it changes
only when NPCs are added.

Purely a name list. A kc goal is scored against synced LootEvent rows
(evaluate_completion in app/mindmaps.py).
"""
import json
import pathlib
from typing import List, Optional

NPC_NAMES_PATH = pathlib.Path(__file__).resolve().parent / "data" / "npc_names.json"

_npc_names: Optional[List[str]] = None


def get_npc_names() -> List[str]:
    global _npc_names
    if _npc_names is None:
        try:
            with open(NPC_NAMES_PATH, "r", encoding="utf-8") as f:
                _npc_names = json.load(f)
        except (OSError, json.JSONDecodeError):
            _npc_names = []
    return _npc_names


def search_npc_names(query: str, limit: int = 20) -> List[str]:
    """Fuzzy name search as in search_item_names (app/item_ids.py): prefix
    matches first (shortest first, so "Goblin" outranks "Goblin
    (Dorgesh-Kaan)"), then substring matches.
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    starts, contains = [], []
    for name in get_npc_names():
        lname = name.lower()
        if lname.startswith(q):
            starts.append(name)
        elif q in lname:
            contains.append(name)
    starts.sort(key=len)
    contains.sort(key=len)
    return (starts + contains)[:limit]

"""Killable-NPC name lookup for the Mindmaps KC goal's search field.

Backed by a static JSON snapshot (app/data/npc_names.json) built from
the OSRS Wiki's "Bucket" data extension's monster infobox table,
filtered down to NPCs with a positive combat level (i.e. ones a player
can actually fight) -- see scripts/fetch_npc_names.py for how it's
generated/regenerated. Like item_ids.py's item snapshot, this only
changes when Jagex adds new NPCs, so a bundled snapshot refreshed by
manually re-running that script is plenty.

This is purely a name list, not a live "have you killed this NPC yet"
check -- see app/mindmaps.py's evaluate_completion for how a kc goal
is actually scored (against synced LootEvent rows). The search field
this backs just needs to offer real NPC names to pick from; the
docstrings on the KC goal's fields describe the eventual plan to also
use this snapshot for the loot tracker matching itself.
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
    """Fuzzy-searches the NPC name snapshot, using the same
    startswith-then-contains scheme as search_item_names in
    app/item_ids.py -- exact-prefix matches first (shortest names
    first, so "Goblin" outranks "Goblin (Dorgesh-Kaan)"), then
    substring matches, same ordering rationale."""
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

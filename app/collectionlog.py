"""The collection log's static structure (tabs -> pages -> items), item-name
lookup, and validation of synced item ids.

Backed by two snapshots in app/data/:
- collection_log_schema.json: {<item id>: tab/page structure}, read from the
RuneLite client's cache data (see CollectionLogSchemaExporter in the
Mootrius/myscape-plugin repo for the method and the evansloan/collection-log
credit). It is identical for every player, so it is bundled.
- collection_log_item_names.json: {<item id>: <item name>} for the schema's
ids; see scripts/build_collection_log_item_names.py.

A leaf module (no app imports, like app/item_ids.py, app/quest_names.py,
app/npc_names.py). Icons are left to the caller via item_icon_url(item["id"])
in app/purchase_goals.py: importing it here would risk a cycle, since
purchase_goals imports app.schemas, which imports get_valid_item_ids from here
(CollectionLogItemIn).

Per-player obtained items are not here; they live in
GameAccount.collection_log_items (app/models.py), synced by POST
/api/players/me/collection-log (app/main.py).
"""
import json
import pathlib
from typing import Dict, FrozenSet, List, Optional

DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
SCHEMA_PATH = DATA_DIR / "collection_log_schema.json"
ITEM_NAMES_PATH = DATA_DIR / "collection_log_item_names.json"

_schema: Optional[dict] = None
_item_names: Optional[Dict[int, str]] = None
_valid_item_ids: Optional[FrozenSet[int]] = None


def _load_schema() -> dict:
    global _schema
    if _schema is None:
        try:
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                _schema = json.load(f)
        except (OSError, json.JSONDecodeError):
            _schema = {"tabs": []}
    return _schema


def _load_item_names() -> Dict[int, str]:
    global _item_names
    if _item_names is None:
        try:
            with open(ITEM_NAMES_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # JSON keys are strings; converted to ints once so the rest of the
            # module uses real item ids.
            _item_names = {int(k): v for k, v in raw.items()}
        except (OSError, json.JSONDecodeError, ValueError):
            _item_names = {}
    return _item_names


def get_item_name(item_id: int) -> Optional[str]:
    return _load_item_names().get(item_id)


_item_ids_by_name: Optional[Dict[str, List[int]]] = None


def _normalize_item_name(name: str) -> str:
    return " ".join(name.replace("\u2019", "'").split()).lower()


def find_unique_item_id_by_name(name: Optional[str]) -> Optional[int]:
    """The collection log item id for a name printed by the game ("New item added
    to your collection log: <name>"; POST
    /api/players/me/collection-log/item), or None if the name is not in the
    log or is ambiguous. Names shared by several slots (Ancient pages,
    Graceful recolors, Decorative armour) are not guessed, since the chat line
    does not say which unlocked; they appear on the next full sync.
    """
    global _item_ids_by_name
    if not name:
        return None
    if _item_ids_by_name is None:
        index: Dict[str, List[int]] = {}
        for item_id, item_name in _load_item_names().items():
            index.setdefault(_normalize_item_name(item_name), []).append(item_id)
        _item_ids_by_name = index
    ids = _item_ids_by_name.get(_normalize_item_name(name))
    return ids[0] if ids and len(ids) == 1 else None


def get_valid_item_ids() -> FrozenSet[int]:
    """Every item id the schema uses; the ceiling synced ids are validated
    against (CollectionLogItemIn in app/schemas.py), like
    DIARY_AREAS/DIARY_TIERS in app/mindmaps.py.
    """
    global _valid_item_ids
    if _valid_item_ids is None:
        ids = set()
        for tab in _load_schema().get("tabs", []):
            for page in tab.get("pages", []):
                ids.update(page.get("itemIds", []))
        _valid_item_ids = frozenset(ids)
    return _valid_item_ids


def get_collection_log_tabs() -> List[dict]:
    """The full tab -> page -> item structure, each item with its name
    (get_item_name) for render_character_overview in app/pages.py:
    [{"name": <tab>, "pages": [{"name": <page>, "items": [{"id": <id>, "name":
    <name>}, ...]}, ...]}, ...]
    
    No icon URL (see module docstring). An id with no resolvable name falls
    back to the id as a string; the build script asserts every schema id
    resolves, but the two files are edited independently.
    """
    tabs = []
    for tab in _load_schema().get("tabs", []):
        pages = []
        for page in tab.get("pages", []):
            items = [
                {"id": item_id, "name": get_item_name(item_id) or str(item_id)}
                for item_id in page.get("itemIds", [])
            ]
            pages.append({"name": page.get("name", ""), "items": items})
        tabs.append({"name": tab.get("name", ""), "pages": pages})
    return tabs

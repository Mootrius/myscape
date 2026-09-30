"""The collection log's own static structure (tabs -> pages -> items)
and item-name lookup, plus validation of a synced item id against it.

Backed by two static JSON snapshots in app/data/:

- collection_log_schema.json: {<item id>: nothing but the tab/page
  structure itself} -- read straight out of the RuneLite client's own
  cache data (struct/enum compositions), not hand-compiled; see
  CollectionLogSchemaExporter in the Mootrius/myscape-plugin repo for
  exactly how, and its own doc comment for the evansloan/collection-log
  credit. Every real OSRS game build has exactly one such structure --
  it's identical for every player -- so, like item_ids.json/
  quest_names.json/npc_names.json elsewhere in this app, it only needs
  exporting once and is bundled here rather than re-derived per sync.
- collection_log_item_names.json: {<item id>: <item name>} for exactly
  the item ids the schema above uses -- see
  scripts/build_collection_log_item_names.py for how it's built.

Deliberately a leaf module (no imports from elsewhere in this app,
matching app/item_ids.py/app/quest_names.py/app/npc_names.py), so it
never has to answer for an icon URL: item_icon_url in
app/purchase_goals.py is already "the one place every item icon in
this app is built from now" (see that function's own comment) --
get_collection_log_tabs below leaves icons to its caller (an item's
`id` is everything item_icon_url needs) rather than importing that
function in here and risking a real import cycle for it (purchase_
goals.py itself imports from app.schemas, which is exactly where this
module's own get_valid_item_ids gets imported FROM, for the synced-
item-id validator -- see CollectionLogItemIn there).

What this module is deliberately NOT the source of: which of these
items a given player has actually obtained, and in what quantity.
That's per-player state (GameAccount.collection_log_items in
app/models.py, synced by POST /api/players/me/collection-log in
app/main.py) -- this module only ever answers "what's the shape of the
whole collection log" and "what's item <id> called", the same
structure for every player.
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
            # Keys are strings in the JSON file itself (see that
            # script's own comment on why) -- converted to real ints
            # once here so every other function in this module can
            # just use real item ids throughout, matching every other
            # id-keyed structure in this app.
            _item_names = {int(k): v for k, v in raw.items()}
        except (OSError, json.JSONDecodeError, ValueError):
            _item_names = {}
    return _item_names


def get_item_name(item_id: int) -> Optional[str]:
    return _load_item_names().get(item_id)


def get_valid_item_ids() -> FrozenSet[int]:
    """Every item id the collection log schema actually uses -- the
    real ceiling a synced item id is validated against (see
    CollectionLogItemIn in app/schemas.py), the same way DIARY_AREAS/
    DIARY_TIERS in app/mindmaps.py validate a synced diary sync."""
    global _valid_item_ids
    if _valid_item_ids is None:
        ids = set()
        for tab in _load_schema().get("tabs", []):
            for page in tab.get("pages", []):
                ids.update(page.get("itemIds", []))
        _valid_item_ids = frozenset(ids)
    return _valid_item_ids


def get_collection_log_tabs() -> List[dict]:
    """The full tab -> page -> item structure, each item enriched with
    its name (get_item_name above) so the Character Overview page's
    collection log renderer (render_character_overview in
    app/pages.py) doesn't need a second lookup for that:

    [{"name": <tab name>, "pages": [{"name": <page name>,
       "items": [{"id": <item id>, "name": <item name>}, ...]},
      ...]}, ...]

    No icon URL here -- see this module's own top-of-file comment for
    why that's left to the caller (item_icon_url(item["id"]) in
    app/purchase_goals.py).

    An item id with no resolvable name (shouldn't happen --
    scripts/build_collection_log_item_names.py asserts every schema id
    resolves before it ever writes that snapshot -- but the schema and
    the name snapshot are two independently-edited files, so this
    doesn't assume they can never drift apart) falls back to the id
    itself as a string, the same "show something rather than nothing"
    fallback every other never-resolved id in this app gets."""
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

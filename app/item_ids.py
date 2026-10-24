"""Real OSRS item id/icon lookup for items that are NOT Grand Exchange tradeable
(tradeable items already carry an id from the price-mapping API in
app/purchase_goals.py).

Matching untradeable items a player owns by NAME TEXT (see _take_owned in
app/purchase_goals.py) is fragile: apostrophe encoding, whitespace or
capitalization differences make the match fail silently. Item ids are
permanent and globally unique, the same ones RuneLite reports.

Backed by a static snapshot (app/data/item_ids.json) built from the OSRS
Wiki's "Bucket" item infobox table; see scripts/fetch_item_ids.py to
regenerate. The data changes only when items are added to the game.
"""
import json
import pathlib
from typing import Dict, List, Optional

ITEM_IDS_PATH = pathlib.Path(__file__).resolve().parent / "data" / "item_ids.json"
# {wiki image filename (lowercase, no "File:" prefix): [item_id, ...]}. A
# separate snapshot because item_ids.json merges every cosmetic recolor under
# one shared name (e.g. all Crystal helm colours under "crystal helm"), but each
# recolor has its own image filename, which is what app/data/recipes.json stores
# per variant. Lets _untradeable_item_icon (app/purchase_goals.py) reach the
# RuneLite CDN for those names. See scripts/fetch_icon_ids_by_filename.py.
ICON_IDS_BY_FILENAME_PATH = pathlib.Path(__file__).resolve().parent / "data" / "icon_ids_by_filename.json"

_item_index: Optional[Dict[str, dict]] = None
_icon_filename_index: Optional[Dict[str, List[int]]] = None

# item_ids.json entries whose "name" is a scrape artifact (raw infobox markup
# instead of plain text). Excluded by exact lowercased key (as keyed in
# get_item_index) so they never reach find_item_ids, find_item_by_exact_name or
# search_item_names, or any search dropdown built on them (Purchase Goals'
# search_items, search_trackable_items in app/possessions.py). Applied at load
# time so it survives regeneration; recheck the list after running
# scripts/fetch_item_ids.py.
_BAD_ITEM_INDEX_KEYS = {
    # "Lovley[sic] jubbly bib": the wiki's "[sic]" template rendered as literal
    # HTML.
    'lovley<sup class="noprint">&#91;<span class="fact-text" '
    'title="the preceding quoted material has been reproduced '
    'verbatim from the quoted original and is not a transcription '
    'error.">sic</span>&#93;</sup> jubbly bib',
    # The wiki's "null name" placeholder template scraped as a name. It shares
    # icon and ids with a real item, so hiding it loses nothing.
    'null <sup><span style="cursor:help; border-bottom:1px dotted" '
    'title="the name of this entity is not defined in the game.">'
    '[?]</span></sup>[[category:pages with null name]]',
}


def get_item_index() -> Dict[str, dict]:
    global _item_index
    if _item_index is None:
        try:
            with open(ITEM_IDS_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            raw = {}
        _item_index = {
            key: entry for key, entry in raw.items()
            if key not in _BAD_ITEM_INDEX_KEYS
        }
    return _item_index


# Master Scroll Book interface text -> real teleport item name, for scrolls
# whose label is not simply "<label> teleport".
_MASTER_SCROLL_BOOK_ALIASES = {
    "chasm of fire": "chasm teleport scroll",
    "chasm": "chasm teleport scroll",
    "elf camp": "iorwerth camp teleport",
    "cerberus": "key master teleport",
    "revenants": "revenant cave teleport",
    "revenant": "revenant cave teleport",
}

_teleport_item_ids: Optional[set] = None


def _get_teleport_item_ids() -> set:
    global _teleport_item_ids
    if _teleport_item_ids is None:
        _teleport_item_ids = {
            item_id
            for key, entry in get_item_index().items()
            if "teleport" in key
            for item_id in entry.get("ids", [])
        }
    return _teleport_item_ids


def canonical_master_scroll_item_id(item_id: int, item_name: Optional[str]) -> int:
    """The Master Scroll Book shows the default-set scroll with an untradeable
    cosmetic item id and short interface text (e.g. "Nardah"), which loses its
    normal icon, name and Grand Exchange value. Resolves that text back to the
    real teleport scroll's id. An id that already belongs to a real teleport
    item, or text that cannot be resolved, is returned unchanged.
    """
    if item_id in _get_teleport_item_ids() or not item_name:
        return item_id
    label = " ".join(item_name.replace("\u2019", "'").replace("<br>", "").split()).lower()
    if not label:
        return item_id
    # The interface wraps long labels with a hyphen ("Arde-" / "aglais"), which
    # survives line-break stripping, so also try the label without hyphens.
    labels = [label]
    if "-" in label:
        labels.append(label.replace("-", ""))
    for text in labels:
        candidates = []
        alias = _MASTER_SCROLL_BOOK_ALIASES.get(text)
        if alias:
            candidates.append(alias)
        candidates += [text + " teleport", text + " teleport scroll"]
        if "teleport" in text:
            candidates.append(text)
        for name in candidates:
            ids = find_item_ids(name)
            if ids:
                return ids[0]
    return item_id


def get_icon_filename_index() -> Dict[str, List[int]]:
    global _icon_filename_index
    if _icon_filename_index is None:
        try:
            with open(ICON_IDS_BY_FILENAME_PATH, "r", encoding="utf-8") as f:
                _icon_filename_index = json.load(f)
        except (OSError, json.JSONDecodeError):
            _icon_filename_index = {}
    return _icon_filename_index


def find_item_ids(item_name: str) -> Optional[List[int]]:
    """Every game item id documented for item_name (case-insensitive exact
    match), or None. A name can have several ids (e.g. quest-reward variants);
    owning any counts as owning the item.
    """
    if not item_name:
        return None
    entry = get_item_index().get(item_name.strip().lower())
    return entry["ids"] if entry else None


def resolve_item_ids(item_name: str) -> Optional[List[int]]:
    """find_item_ids, with a fallback for cosmetic recolors the snapshot only
    records under their base name (e.g. "Graceful boots (Hallowed)", whose ids
    sit under "Graceful boots" with every other recolor). The recipe entry for
    the name stores the variant's wiki icon filename, which
    ICON_IDS_BY_FILENAME_PATH maps to just that variant's ids, so owning a
    different recolor does not satisfy it. Returns None if neither resolves.
    """
    ids = find_item_ids(item_name)
    if ids:
        return ids
    if not item_name:
        return None
    from app.recipes import find_recipe  # lazy: keeps this module import-light
    recipe = find_recipe(item_name)
    icon = (recipe or {}).get("icon")
    if not icon:
        return None
    name = icon.strip()
    if name.lower().startswith("file:"):
        name = name[len("file:"):]
    return get_icon_filename_index().get(name.lower()) or None


def find_item_by_exact_name(item_name: str) -> Optional[dict]:
    """The raw {"name": str, "icon": str|None, "ids": [int, ...]} entry for
    item_name (case-insensitive exact match), or None. Used by search_items in
    app/purchase_goals.py as the last exact-match tier, so short precise names
    (e.g. "Dom") surface in search.
    """
    if not item_name:
        return None
    return get_item_index().get(item_name.strip().lower())


def find_item_id_by_icon_filename(icon_filename: str) -> Optional[int]:
    """A real item id for a wiki image filename (case-insensitive, "File:"
    optional) from ICON_IDS_BY_FILENAME_PATH's snapshot, or None. Used by
    _untradeable_item_icon in app/purchase_goals.py for cosmetic variants that
    find_item_ids cannot place. If a filename lists several ids the first is
    used, since ids sharing a filename share an icon.
    """
    if not icon_filename:
        return None
    name = icon_filename.strip()
    if name.lower().startswith("file:"):
        name = name[len("file:"):]
    ids = get_icon_filename_index().get(name.lower())
    return ids[0] if ids else None


def search_item_names(query: str, limit: int, exclude: Optional[set] = None) -> List[dict]:
    """Fuzzy name search over this snapshot (startswith, then contains, as in
    search_items in app/purchase_goals.py and search_recipe_names in
    app/recipes.py). The final tier of search_items, so untradeable non-recipe
    items (quest rewards, minigame items) are findable with a real icon.
    `exclude` is a set of lowercased names already matched by earlier tiers.
    Returns raw entries {"name": str, "icon": str|None (a wiki filename, not a
    URL)}.
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    exclude = exclude or set()
    starts, contains = [], []
    for key, entry in get_item_index().items():
        if key in exclude:
            continue
        if key.startswith(q):
            starts.append(entry)
        elif q in key:
            contains.append(entry)
    starts.sort(key=lambda e: len(e.get("name") or ""))
    contains.sort(key=lambda e: len(e.get("name") or ""))
    combined = (starts + contains)[:limit]
    return [{"name": e.get("name"), "icon": e.get("icon")} for e in combined]

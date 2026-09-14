"""Item-combination recipe lookup -- lets a player search for a
non-tradeable combination item (e.g. "Neitiznot faceguard") the same
way they'd search for any other item, and have the app automatically
know it's made of a Helm of Neitiznot + a Basilisk jaw, without them
having to say so or already know its exact spelling.

Backed by a static JSON snapshot (app/data/recipes.json) built from the
OSRS Wiki's "Bucket" data extension -- see scripts/fetch_recipes.py for
how it's generated/regenerated. The wiki stores this in the same
`Recipe` bucket table as ordinary skilling recipes (fletching a bow,
cooking a meal, etc); what distinguishes a pure item-combination like
this one is that it names no `uses_skill` at all and produces exactly
1 of its output per recipe (excluding batch-crafted things like
arrows), so that's exactly what scripts/fetch_recipes.py filters on
when building the snapshot. Recipes essentially never change once a
game update ships them, so a bundled snapshot (refreshed by manually
re-running that script) is plenty -- there's no need for a live fetch
or a background refresh job.

Each entry in the index is keyed by the *output* item's name
(lowercased) -- {"name": str, "icon": str|None, "materials": [{"name":
str, "quantity": int}, ...]} -- since that's what a player would
actually search for, not the wiki's own page title (which can cover
several output variants at once, e.g. "Adamant arrow" documenting both
plain and poisoned arrows).
"""
import json
import pathlib
from typing import Dict, List, Optional

RECIPES_PATH = pathlib.Path(__file__).resolve().parent / "data" / "recipes.json"

_recipe_index: Optional[Dict[str, dict]] = None


def get_recipe_index() -> Dict[str, dict]:
    global _recipe_index
    if _recipe_index is None:
        try:
            with open(RECIPES_PATH, "r", encoding="utf-8") as f:
                _recipe_index = json.load(f)
        except (OSError, json.JSONDecodeError):
            _recipe_index = {}
    return _recipe_index


def find_recipe(item_name: str) -> Optional[dict]:
    """Returns the full recipe entry for item_name (case-insensitive
    exact match against the recipe's own output name), or None if it
    isn't a known combination item."""
    if not item_name:
        return None
    return get_recipe_index().get(item_name.strip().lower())


def search_recipe_names(query: str, limit: int, exclude: Optional[set] = None) -> List[dict]:
    """Fuzzy-searches known combination-item recipes by name, using the
    same startswith-then-contains scheme as search_items in
    app/purchase_goals.py -- lets combination gear like "Neitiznot
    faceguard" show up as a normal, icon-bearing search suggestion even
    though it has no Grand Exchange listing of its own to search
    against. `exclude` is a set of already-used lowercased names (e.g.
    ones already matched as a real tradeable item) to skip, so nothing
    is suggested twice. Returns raw entries -- {"name": str, "icon":
    str|None (a wiki image filename, not yet a full URL)} -- since
    turning that filename into a URL is the caller's job (see
    item_icon_url in app/purchase_goals.py); this module has no reason
    to know about the wiki's icon-hosting convention itself."""
    q = (query or "").strip().lower()
    if not q:
        return []
    exclude = exclude or set()
    starts, contains = [], []
    for key, entry in get_recipe_index().items():
        if key in exclude:
            continue
        if key.startswith(q):
            starts.append(entry)
        elif q in key:
            contains.append(entry)
    starts.sort(key=lambda e: len(e["name"]))
    contains.sort(key=lambda e: len(e["name"]))
    combined = (starts + contains)[:limit]
    return [{"name": e["name"], "icon": e.get("icon")} for e in combined]


def _build_name_to_id(mapping: dict) -> Dict[str, int]:
    """Exact-match index of every GE-tradeable item's lowercased name to
    its item id -- built fresh from the already-cached wiki mapping
    (see get_mapping() in app/purchase_goals.py) each time it's needed,
    since the mapping itself only refreshes at most once a day and this
    is a cheap pass over it either way."""
    by_name: Dict[str, int] = {}
    for item_id, meta in mapping.items():
        name = meta.get("name")
        if name:
            by_name[name.strip().lower()] = int(item_id)
    return by_name


def expand_recipe_components(item_name: str, mapping: dict) -> Optional[List[dict]]:
    """If item_name matches a known combination recipe, returns the
    components list in the raw storage shape a gear slot expects (see
    GearComponentIn in app/schemas.py) -- {"itemId": int|None,
    "itemName": str, "quantity": int} per material, with each material
    resolved to a real item id when it's itself GE-tradeable and left
    as a name-only (untradeable) reference otherwise, exactly like a
    manually-built combo already supports. Returns None when item_name
    isn't a recognized recipe, so the caller can fall back to storing it
    as a plain untradeable item."""
    recipe = find_recipe(item_name)
    if not recipe:
        return None
    name_to_id = _build_name_to_id(mapping)
    components = []
    for m in recipe["materials"]:
        mat_name = m.get("name") or ""
        item_id = name_to_id.get(mat_name.strip().lower())
        components.append({"itemId": item_id, "itemName": mat_name, "quantity": m.get("quantity") or 1})
    return components

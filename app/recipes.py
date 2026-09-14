"""Item-combination recipe lookup -- lets a player type/search a
non-tradeable combination item (e.g. "Neitiznot faceguard") into a gear
setup slot and have the app automatically know it's made of a Helm of
Neitiznot + a Basilisk jaw, without them having to say so.

Backed by a static JSON snapshot (app/data/recipes.json) built from the
OSRS Wiki's "Bucket" data extension -- see scripts/fetch_recipes.py for
how it's generated/regenerated. The wiki stores this in the same
`Recipe` bucket table as ordinary skilling recipes (fletching a bow,
cooking a meal, etc); what distinguishes a pure item-combination like
this one is that it names no `uses_skill` at all, so that's exactly
what scripts/fetch_recipes.py filters on when building the snapshot.
Recipes essentially never change once a game update ships them, so a
bundled snapshot (refreshed by manually re-running that script) is
plenty -- there's no need for a live fetch or a background refresh job.
"""
import json
import pathlib
from typing import Dict, List, Optional

RECIPES_PATH = pathlib.Path(__file__).resolve().parent / "data" / "recipes.json"

# {itemNameLower: [{"name": str, "quantity": int}, ...]}
_recipe_index: Optional[Dict[str, List[dict]]] = None


def get_recipe_index() -> Dict[str, List[dict]]:
    global _recipe_index
    if _recipe_index is None:
        try:
            with open(RECIPES_PATH, "r", encoding="utf-8") as f:
                _recipe_index = json.load(f)
        except (OSError, json.JSONDecodeError):
            _recipe_index = {}
    return _recipe_index


def find_recipe(item_name: str) -> Optional[List[dict]]:
    """Returns the material list for item_name (case-insensitive exact
    match against the recipe's own page name), or None if it isn't a
    known combination item."""
    if not item_name:
        return None
    return get_recipe_index().get(item_name.strip().lower())


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
    materials = find_recipe(item_name)
    if not materials:
        return None
    name_to_id = _build_name_to_id(mapping)
    components = []
    for m in materials:
        mat_name = m.get("name") or ""
        item_id = name_to_id.get(mat_name.strip().lower())
        components.append({"itemId": item_id, "itemName": mat_name, "quantity": m.get("quantity") or 1})
    return components

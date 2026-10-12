"""Item-combination recipe lookup: lets a player search for a non-tradeable
combination item (e.g. "Neitiznot faceguard") like any other item and have the
app know its components (Helm of Neitiznot + Basilisk jaw).

Backed by a static snapshot (app/data/recipes.json) from the OSRS Wiki's
"Bucket" `Recipe` table; see scripts/fetch_recipes.py to regenerate. Pure item
combinations are the recipes that name no `uses_skill` and produce exactly 1
of their output (excluding batch-crafted items like arrows), which is what
that script filters on. Recipes rarely change, so no live fetch is needed.

The index is keyed by the lowercased *output* item name: {"name": str, "icon":
str|None, "materials": [{"name": str, "quantity": int}, ...]}, not the wiki
page title (which can cover several outputs).
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
    """The full recipe entry for item_name (case-insensitive match on output
    name), or None if it is not a known combination item.
    """
    if not item_name:
        return None
    return get_recipe_index().get(item_name.strip().lower())


def search_recipe_names(query: str, limit: int, exclude: Optional[set] = None) -> List[dict]:
    """Fuzzy name search over combination recipes (startswith, then contains, as
    in search_items in app/purchase_goals.py), so items with no Grand Exchange
    listing appear as normal suggestions. `exclude` is a set of lowercased
    names already matched. Returns raw entries {"name": str, "icon": str|None
    (a wiki filename, not a URL)}; building the URL is the caller's job
    (item_icon_url in app/purchase_goals.py).
    """
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
    """Exact-match index of every GE-tradeable item's lowercased name -> item id,
    built from the cached wiki mapping (get_mapping() in
    app/purchase_goals.py), which refreshes at most daily.
    """
    by_name: Dict[str, int] = {}
    for item_id, meta in mapping.items():
        name = meta.get("name")
        if name:
            by_name[name.strip().lower()] = int(item_id)
    return by_name


# Some combination items are built from other combination items (e.g. Avernic
# treads (max) from Primordial, Pegasian and Eternal boots one at a time), and
# the intermediate items have no GE listing, so pricing means walking down to
# purchasable materials. Caps how many such hops _expand_materials follows. Real
# chains are 2-3 deep, so this guards against data glitches or cycles.
MAX_RECIPE_DEPTH = 8


def _expand_materials(materials: List[dict], name_to_id: Dict[str, int], depth: int, seen: set) -> List[dict]:
    """Recursively resolves a materials list into flat components in the gear
    slot shape {"itemId": int|None, "itemName": str, "quantity": int}. A
    GE-tradeable material resolves to its id and stops, even if it has its own
    recipe. An untradeable material with a recipe is expanded one level
    deeper, with quantities scaled. Anything else stays a bare named
    component. Same-name results are summed (e.g. Demon tear across the
    Avernic treads chain).
    """
    merged: Dict[str, dict] = {}

    def add(item_id: Optional[int], item_name: str, quantity: int):
        key = item_name.lower()
        if key in merged:
            merged[key]["quantity"] += quantity
        else:
            merged[key] = {"itemId": item_id, "itemName": item_name, "quantity": quantity}

    for m in materials:
        mat_name = (m.get("name") or "").strip()
        if not mat_name:
            continue
        qty = m.get("quantity") or 1
        key = mat_name.lower()
        item_id = name_to_id.get(key)

        if item_id is None and depth < MAX_RECIPE_DEPTH and key not in seen:
            sub_recipe = get_recipe_index().get(key)
            if sub_recipe:
                sub_components = _expand_materials(sub_recipe["materials"], name_to_id, depth + 1, seen | {key})
                for comp in sub_components:
                    add(comp["itemId"], comp["itemName"], comp["quantity"] * qty)
                continue

        add(item_id, mat_name, qty)

    return list(merged.values())


def expand_recipe_components(item_name: str, mapping: dict) -> Optional[List[dict]]:
    """If item_name is a known combination recipe, returns its fully resolved
    components in the gear slot storage shape (GearComponentIn in
    app/schemas.py), expanding untradeable intermediates via
    _expand_materials. Returns None for an unknown recipe, so the caller can
    store a plain untradeable item.
    """
    recipe = find_recipe(item_name)
    if not recipe:
        return None
    name_to_id = _build_name_to_id(mapping)
    return _expand_materials(recipe["materials"], name_to_id, depth=0, seen={item_name.strip().lower()})

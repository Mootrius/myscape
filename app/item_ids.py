"""Real OSRS item id/icon lookup for items that AREN'T Grand Exchange
tradeable (see app/purchase_goals.py's `mapping` for tradeable items,
which already carry a real id from the wiki's price-mapping API).

This exists to fix a specific, longstanding gap: an untradeable item
in a gear setup -- a plain one, a recipe material, or the combined item
itself -- could previously only be matched against what a player
already owns by comparing item NAME TEXT (see _take_owned in
app/purchase_goals.py). That's fragile -- the RuneLite plugin reports
whatever the game client itself calls the item, and if that text
differs from what a gear slot or recipe names it in ANY way (an
apostrophe encoded differently, incidental whitespace, a stray
capitalization difference) the match silently fails and the item looks
unowned even when it isn't.

Every item in the game -- tradeable or not -- has a small number of
real, permanent, globally-unique numeric ids, the SAME ones RuneLite
itself reports. Backed by a static JSON snapshot (app/data/item_ids.json)
built from the OSRS Wiki's "Bucket" data extension's item infobox table
-- see scripts/fetch_item_ids.py for how it's generated/regenerated.
Like recipes, this data only changes when new items are added to the
game, so a bundled snapshot (refreshed by manually re-running that
script) is plenty.
"""
import json
import pathlib
from typing import Dict, List, Optional

ITEM_IDS_PATH = pathlib.Path(__file__).resolve().parent / "data" / "item_ids.json"
# {wiki image filename (lowercase, no "File:" prefix): [item_id, ...]}
# -- a DIFFERENT snapshot from item_ids.json above, and the reason it
# exists rather than just reusing that one: item_ids.json merges every
# cosmetic recolor of one item page under a single shared NAME (e.g.
# every Crystal helm colour is stored under the one key "crystal
# helm"), because that's what the wiki's own infobox_item rows share
# too -- so it has no way to tell "Crystal helm (Ithell)" apart from
# any other colour by name alone. Those same rows each carry their OWN
# distinct 'image' field, though (e.g. "File:Crystal helm
# (Ithell).png") -- exactly the filename app/data/recipes.json already
# stores per colour variant -- so keying by THAT instead resolves an
# exact recipe icon filename straight to its real id, letting
# _untradeable_item_icon (app/purchase_goals.py) reach the RuneLite CDN
# for a cosmetic-variant name even though item_ids.json's name-merged
# snapshot can't place it. See scripts/fetch_icon_ids_by_filename.py.
ICON_IDS_BY_FILENAME_PATH = pathlib.Path(__file__).resolve().parent / "data" / "icon_ids_by_filename.json"

_item_index: Optional[Dict[str, dict]] = None
_icon_filename_index: Optional[Dict[str, List[int]]] = None


def get_item_index() -> Dict[str, dict]:
    global _item_index
    if _item_index is None:
        try:
            with open(ITEM_IDS_PATH, "r", encoding="utf-8") as f:
                _item_index = json.load(f)
        except (OSError, json.JSONDecodeError):
            _item_index = {}
    return _item_index


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
    """Returns every real game item id documented for item_name
    (case-insensitive exact match), or None if it isn't in the
    snapshot. A name can resolve to more than one id -- a quest-reward
    or minigame-only variant alongside the standard item, for instance
    -- and owning any one of them counts as owning the item."""
    if not item_name:
        return None
    entry = get_item_index().get(item_name.strip().lower())
    return entry["ids"] if entry else None


def find_item_by_exact_name(item_name: str) -> Optional[dict]:
    """Returns the raw {"name": str, "icon": str|None, "ids": [int, ...]}
    entry for item_name (case-insensitive exact match), or None. Used by
    search_items in app/purchase_goals.py as the last of three tiers it
    checks for an EXACT match (after the live tradeable mapping and
    known recipes) -- see that function's own comment for why a plain
    startswith/contains scan alone isn't enough to guarantee a short,
    precise name (e.g. "Dom", the Doom of Mokhaiotl's pet) actually
    surfaces as a search result at all, let alone first."""
    if not item_name:
        return None
    return get_item_index().get(item_name.strip().lower())


def find_item_id_by_icon_filename(icon_filename: str) -> Optional[int]:
    """Returns a real item id for a wiki image filename (case-
    insensitive, "File:" prefix optional) documented in
    ICON_IDS_BY_FILENAME_PATH's snapshot, or None if it isn't there.
    Used by _untradeable_item_icon in app/purchase_goals.py to resolve
    an exact cosmetic-variant name (e.g. "Crystal helm (Ithell)") that
    find_item_ids above can't place -- item_ids.json merges every
    recolor of one item page under a single shared name, but each
    recolor's own icon filename is still distinct, and that's exactly
    what app/data/recipes.json stores per variant. A filename can list
    more than one real id (an inventory/worn pair sharing one look,
    same as find_item_ids' own multi-id case) -- the first is used,
    since by construction every id sharing a filename shares its icon
    too, so which one is "as good as any" here."""
    if not icon_filename:
        return None
    name = icon_filename.strip()
    if name.lower().startswith("file:"):
        name = name[len("file:"):]
    ids = get_icon_filename_index().get(name.lower())
    return ids[0] if ids else None


def search_item_names(query: str, limit: int, exclude: Optional[set] = None) -> List[dict]:
    """Fuzzy-searches this snapshot by name, using the same
    startswith-then-contains scheme as search_items in
    app/purchase_goals.py and search_recipe_names in app/recipes.py --
    the final fallback tier in search_items, once neither a live
    Grand Exchange match nor a known combination recipe covers the
    query, so that a genuinely untradeable, non-combined item (a quest
    reward, a minigame-only item, anything else this snapshot covers
    but the other two don't) can still be found by name and shown with
    its real icon rather than being unfindable. `exclude` is a set of
    already-used lowercased names to skip, so nothing already matched
    by an earlier tier is suggested twice. Returns raw entries --
    {"name": str, "icon": str|None (a wiki image filename, not yet a
    full URL)}."""
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

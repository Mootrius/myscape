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

_item_index: Optional[Dict[str, dict]] = None


def get_item_index() -> Dict[str, dict]:
    global _item_index
    if _item_index is None:
        try:
            with open(ITEM_IDS_PATH, "r", encoding="utf-8") as f:
                _item_index = json.load(f)
        except (OSError, json.JSONDecodeError):
            _item_index = {}
    return _item_index


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


def find_item_icon(item_name: str) -> Optional[str]:
    """Returns the wiki image filename (not yet a full URL -- see
    item_icon_url in app/purchase_goals.py) documented for item_name
    (case-insensitive exact match), or None if it isn't in the
    snapshot or has no image on file."""
    if not item_name:
        return None
    entry = get_item_index().get(item_name.strip().lower())
    return entry.get("icon") if entry else None

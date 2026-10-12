"""Static reference data for Character Overview's quests, achievement diaries and
combat achievements sections (render_character_overview in app/pages.py, via
/api/character-overview/progress in app/main.py). Like app/quest_names.py and
app/item_ids.py, it loads fixed snapshots from app/data/*.json:

* quest_list.json: {"free": [...], "members": [...], "miniquests": [...]},
grouped and ordered like the in-game Quest List (see
scripts/fetch_quest_list.py).
* diary_area_tier_totals.json: {<area>: {<tier>: <task count>}}.
* combat_achievement_tier_totals.json: {<tier>: <task count>}.

These change only when Jagex adds content (see each fetch script). The
player's own progress against these totals is live-synced in
GameAccount.completed_quests/diary_tiers/character_summary_combat_task_tier_completed
(app/models.py).
"""
import json
import pathlib
from typing import Dict, List, Optional

_DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
_QUEST_LIST_PATH = _DATA_DIR / "quest_list.json"
_DIARY_TOTALS_PATH = _DATA_DIR / "diary_area_tier_totals.json"
_CA_TOTALS_PATH = _DATA_DIR / "combat_achievement_tier_totals.json"

_quest_list: Optional[Dict[str, List[str]]] = None
_diary_totals: Optional[Dict[str, Dict[str, int]]] = None
_ca_totals: Optional[Dict[str, int]] = None


def _load_json(path: pathlib.Path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def get_quest_list() -> Dict[str, List[str]]:
    """{"free": [...], "members": [...], "miniquests": [...]}, each alphabetized
    ignoring a leading "The", in the in-game Free/Members/Miniquests order
    (see the quest section in app/pages.py).
    
    "members" excludes the "Recipe for Disaster/<subquest>" entries:
    RuneLite's Quest enum has no per-subquest entries, so they would always
    show as not started. "miniquests" is the wiki's Category:Miniquests
    limited to those with a RuneLite Quest enum entry; the others (Tutorial
    Island, Rogue Trader, Lost Lover, ...) are untrackable.
    """
    global _quest_list
    if _quest_list is None:
        _quest_list = _load_json(_QUEST_LIST_PATH, {"free": [], "members": [], "miniquests": []})
    return _quest_list


def get_diary_tier_totals() -> Dict[str, Dict[str, int]]:
    """{<area slug, as in DIARY_AREAS in app/mindmaps.py>: {<tier, as in
    DIARY_TIERS>: <task count>}}.
    """
    global _diary_totals
    if _diary_totals is None:
        _diary_totals = _load_json(_DIARY_TOTALS_PATH, {})
    return _diary_totals


def get_ca_tier_totals() -> Dict[str, int]:
    """{<tier: "easy"/"medium"/"hard"/"elite"/"master"/"grandmaster">: <task
    count>}.
    """
    global _ca_totals
    if _ca_totals is None:
        _ca_totals = _load_json(_CA_TOTALS_PATH, {})
    return _ca_totals

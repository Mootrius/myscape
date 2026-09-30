"""Static reference data for Character Overview's quests/achievement-
diaries/combat-achievements sections (render_character_overview in
app/pages.py, via /api/character-overview/progress in app/main.py) --
the same "small, fixed, every-player-identical" category of snapshot
app/quest_names.py/app/item_ids.py already load from app/data/*.json,
here covering three more of the same shape:

* quest_list.json: {"free": [...], "members": [...]} -- every current
  quest's name, split and ordered exactly like the real in-game Quest
  List interface's own two groups (see scripts/fetch_quest_list.py).
* diary_area_tier_totals.json: {<area>: {<tier>: <task count>}} -- how
  many tasks each achievement diary area's each tier actually has.
* combat_achievement_tier_totals.json: {<tier>: <task count>} -- how
  many combat achievement tasks each tier actually has.

None of these three ever change from player to player, only when
Jagex adds content (see each fetch script's own docstring for how to
regenerate) -- unlike GameAccount.completed_quests/diary_tiers/
character_summary_combat_task_tier_completed (app/models.py), which
are that same player's own live-synced progress against these fixed
totals.
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
    """{"free": [...24 quest names...], "members": [...161...],
    "miniquests": [...19...]}, each already alphabetized (ignoring a
    leading "The") -- matches the real in-game Quest List interface's
    own three-group default order (Free/Members/Miniquests), see
    Character Overview's quest section in app/pages.py. "members"
    excludes every "Recipe for Disaster/<subquest>" entry (the
    standalone "Recipe for Disaster" quest itself is still listed) --
    those subquests aren't separately trackable via RuneLite's own
    Quest enum (net.runelite.api.Quest has no per-subquest entries for
    it, only QuestState for the parent quest as a whole), so listing
    them individually would only ever show as permanently not-started.
    "miniquests" is exactly the set of OSRS Wiki Category:Miniquests
    members that RuneLite's Quest enum actually has an entry for --
    a handful of wiki-categorized miniquests (Tutorial Island, Knight
    Waves Training Ground, Rogue Trader, Lost Lover, Spirit of
    Adventure, Architectural Alliance, Natural history quiz, Sacred
    Bone Burner) have no RuneLite Quest enum entry at all and so
    aren't trackable here either."""
    global _quest_list
    if _quest_list is None:
        _quest_list = _load_json(_QUEST_LIST_PATH, {"free": [], "members": [], "miniquests": []})
    return _quest_list


def get_diary_tier_totals() -> Dict[str, Dict[str, int]]:
    """{<area slug, matching DIARY_AREAS in app/mindmaps.py>: {<tier,
    matching DIARY_TIERS>: <task count>}}."""
    global _diary_totals
    if _diary_totals is None:
        _diary_totals = _load_json(_DIARY_TOTALS_PATH, {})
    return _diary_totals


def get_ca_tier_totals() -> Dict[str, int]:
    """{<tier, one of "easy"/"medium"/"hard"/"elite"/"master"/
    "grandmaster">: <task count>}."""
    global _ca_totals
    if _ca_totals is None:
        _ca_totals = _load_json(_CA_TOTALS_PATH, {})
    return _ca_totals

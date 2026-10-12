"""The canonical OSRS hiscores boss list: every boss-like activity in the
official hiscores "Bosses" category (an NPC/activity killcount, not a skill or
minigame score).

Used for the Goal Tracking reference table (render_goal_tracking in
app/pages/) and matched by exact name against the hiscores JSON
"activities[].name" in app/hiscores.py. A Jagex rename or addition needs
updating here, so both stay in sync.

Each entry is (slug, display_name, has_icon):
- slug: file name in app/static/boss-icons/<slug>.png when has_icon is True.
- display_name: how the hiscores name the boss.
- has_icon: whether a matching RuneLite sprite exists. Artio/Callisto,
Calvar'ion/Vet'ion and Spindel/Venenatis are twin pairs sharing one icon.
"""
from typing import Dict, List, Optional, Tuple

HISCORE_BOSSES: List[Tuple[str, str, bool]] = [
    ("abyssal-sire", "Abyssal Sire", True),
    ("alchemical-hydra", "Alchemical Hydra", True),
    ("amoxliatl", "Amoxliatl", True),
    ("araxxor", "Araxxor", True),
    ("artio", "Artio", True),
    ("barrows-chests", "Barrows Chests", True),
    ("brutus", "Brutus", True),
    ("bryophyta", "Bryophyta", True),
    ("callisto", "Callisto", True),
    ("calvarion", "Calvar'ion", True),
    ("cerberus", "Cerberus", True),
    ("chambers-of-xeric", "Chambers of Xeric", True),
    ("chambers-of-xeric-challenge-mode", "Chambers of Xeric: Challenge Mode", True),
    ("chaos-elemental", "Chaos Elemental", True),
    ("chaos-fanatic", "Chaos Fanatic", True),
    ("commander-zilyana", "Commander Zilyana", True),
    ("corporeal-beast", "Corporeal Beast", True),
    ("crazy-archaeologist", "Crazy Archaeologist", True),
    ("dagannoth-prime", "Dagannoth Prime", True),
    ("dagannoth-rex", "Dagannoth Rex", True),
    ("dagannoth-supreme", "Dagannoth Supreme", True),
    ("deranged-archaeologist", "Deranged Archaeologist", True),
    ("doom-of-mokhaiotl", "Doom of Mokhaiotl", True),
    ("duke-sucellus", "Duke Sucellus", True),
    ("general-graardor", "General Graardor", True),
    ("giant-mole", "Giant Mole", True),
    ("grotesque-guardians", "Grotesque Guardians", True),
    ("hespori", "Hespori", True),
    ("kalphite-queen", "Kalphite Queen", True),
    ("king-black-dragon", "King Black Dragon", True),
    ("kraken", "Kraken", True),
    ("kreearra", "Kree'arra", True),
    ("kril-tsutsaroth", "K'ril Tsutsaroth", True),
    ("lunar-chests", "Lunar Chests", True),
    ("mad-angel", "Mad Angel", True),
    ("maggot-king", "Maggot King", True),
    ("the-mimic", "The Mimic", True),
    ("nex", "Nex", True),
    ("the-nightmare", "The Nightmare", True),
    ("phosanis-nightmare", "Phosani's Nightmare", True),
    ("obor", "Obor", True),
    ("phantom-muspah", "Phantom Muspah", True),
    ("sarachnis", "Sarachnis", True),
    ("scorpia", "Scorpia", True),
    ("scurrius", "Scurrius", True),
    ("shellbane-gryphon", "Shellbane Gryphon", True),
    ("skotizo", "Skotizo", True),
    ("sol-heredit", "Sol Heredit", True),
    ("spindel", "Spindel", True),
    ("tempoross", "Tempoross", True),
    ("the-gauntlet", "The Gauntlet", True),
    ("the-corrupted-gauntlet", "The Corrupted Gauntlet", True),
    ("the-hueycoatl", "The Hueycoatl", True),
    ("the-leviathan", "The Leviathan", True),
    ("the-royal-titans", "The Royal Titans", True),
    ("the-whisperer", "The Whisperer", True),
    ("theatre-of-blood", "Theatre of Blood", True),
    ("theatre-of-blood-hard-mode", "Theatre of Blood: Hard Mode", True),
    ("thermonuclear-smoke-devil", "Thermonuclear Smoke Devil", True),
    ("tombs-of-amascut", "Tombs of Amascut", True),
    ("tombs-of-amascut-expert", "Tombs of Amascut: Expert Mode", True),
    ("tzkal-zuk", "TzKal-Zuk", True),
    ("tztok-jad", "TzTok-Jad", True),
    ("vardorvis", "Vardorvis", True),
    ("venenatis", "Venenatis", True),
    ("vetion", "Vet'ion", True),
    ("vorkath", "Vorkath", True),
    ("wintertodt", "Wintertodt", True),
    ("yama", "Yama", True),
    ("zalcano", "Zalcano", True),
    ("zulrah", "Zulrah", True),
]

# The hiscores' activities[].name wherever it differs from display_name. Kept as
# an override so the table can show "The Mimic"/"The Nightmare"/"Kree'arra"
# (matching wiki titles) rather than the hiscores'
# "Mimic"/"Nightmare"/"Kree'Arra". Used by app/hiscores.py.
HISCORES_NAME_OVERRIDES = {
    "The Mimic": "Mimic",
    "The Nightmare": "Nightmare",
    "Kree'arra": "Kree'Arra",
}

# Reverse lookup for app/hiscores.py: exact hiscores activity name -> slug,
# built once at import.
NAME_TO_SLUG = {
    HISCORES_NAME_OVERRIDES.get(name, name): slug for slug, name, _has_icon in HISCORE_BOSSES
}

# Reverse of the same override: hiscores activity name -> display_name.
HISCORES_NAME_TO_DISPLAY_NAME = {
    HISCORES_NAME_OVERRIDES.get(name, name): name for slug, name, _has_icon in HISCORE_BOSSES
}

# Like HISCORES_NAME_OVERRIDES, for the wording of RuneLite's "Your <boss> kill
# count is: <n>." chat message (see apply_kill_count_updates in
# app/hiscores.py). Mirrors RuneLite's KILLCOUNT_RENAMES
# (ChatCommandsPlugin.java); e.g. the chatbox says "Barrows chest", not "Barrows
# Chests".
CHAT_NAME_OVERRIDES = {
    "Barrows Chests": "Barrows chest",
}

# The chat message drops the "The " from every "The <Name>" display_name (e.g.
# "Royal Titans", "Corrupted Gauntlet"). Computed from HISCORE_BOSSES for any
# such name without its own entry above, so new bosses following the convention
# need no extra line.
for _slug, _name, _has_icon in HISCORE_BOSSES:
    if _name.startswith("The ") and _name not in CHAT_NAME_OVERRIDES:
        CHAT_NAME_OVERRIDES[_name] = _name[len("The "):]
del _slug, _name, _has_icon

# Reverse lookup for chat-parsed updates: chat wording -> display_name, built
# once at import. app/hiscores.py matches it case-insensitively.
CHAT_NAME_TO_DISPLAY_NAME = {
    CHAT_NAME_OVERRIDES.get(name, name): name for slug, name, _has_icon in HISCORE_BOSSES
}

# Collection log PAGE names (see app.collectionlog.get_collection_log_tabs)
# whose count is not a single HISCORE_BOSSES display_name. Either the page
# groups several activities (twin/trio bosses, a raid's normal and hard modes,
# Nightmare/Phosani's Nightmare), or its name differs from the hiscores name by
# more than the "The " prefix (Royal Titans and The Mad Angel go opposite ways).
#
# Each value is a LIST in display order (base mode first);
# collection_log_page_kill_counts shows entries individually ("1,234 · 56")
# rather than summed. "The Gauntlet" has one page in
# app/data/collection_log_schema.json, so its normal and corrupted counts both
# belong there. Pages without a verified hiscores mapping (e.g. Moons of Peril)
# are left out rather than risk a wrong number.
COLLECTION_LOG_PAGE_NAME_OVERRIDES: Dict[str, List[str]] = {
    "Callisto and Artio": ["Callisto", "Artio"],
    "The Gauntlet": ["The Gauntlet", "The Corrupted Gauntlet"],
    "Dagannoth Kings": ["Dagannoth Prime", "Dagannoth Rex", "Dagannoth Supreme"],
    "Venenatis and Spindel": ["Venenatis", "Spindel"],
    "Vet'ion and Calvar'ion": ["Vet'ion", "Calvar'ion"],
    "Royal Titans": ["The Royal Titans"],
    "The Mad Angel": ["Mad Angel"],
    "The Fight Caves": ["TzTok-Jad"],
    "The Inferno": ["TzKal-Zuk"],
    "Fortis Colosseum": ["Sol Heredit"],
    "The Nightmare": ["The Nightmare", "Phosani's Nightmare"],
    "Chambers of Xeric": ["Chambers of Xeric", "Chambers of Xeric: Challenge Mode"],
    "Theatre of Blood": ["Theatre of Blood", "Theatre of Blood: Hard Mode"],
    "Tombs of Amascut": ["Tombs of Amascut", "Tombs of Amascut: Expert Mode"],
}

# The hiscores' clue-tier activity names, read by _parse_clue_scroll_counts in
# app/hiscores.py. "Clue Scrolls (all)" is excluded because no collection log
# page corresponds to the combined total.
CLUE_SCROLL_HISCORE_NAMES: List[str] = [
    "Clue Scrolls (beginner)",
    "Clue Scrolls (easy)",
    "Clue Scrolls (medium)",
    "Clue Scrolls (hard)",
    "Clue Scrolls (elite)",
    "Clue Scrolls (master)",
]

# Collection log PAGE name -> the hiscores clue tier its count comes from. A
# tier's separate "(Rare)" page (Hard/Elite/Master) maps to the same tier.
# "Shared Treasure Trail Rewards" and "Scroll Cases" span tiers and are left
# unmapped.
COLLECTION_LOG_CLUE_PAGE_TIERS: Dict[str, str] = {
    "Beginner Treasure Trails": "Clue Scrolls (beginner)",
    "Easy Treasure Trails": "Clue Scrolls (easy)",
    "Medium Treasure Trails": "Clue Scrolls (medium)",
    "Hard Treasure Trails": "Clue Scrolls (hard)",
    "Elite Treasure Trails": "Clue Scrolls (elite)",
    "Master Treasure Trails": "Clue Scrolls (master)",
    "Hard Treasure Trails (Rare)": "Clue Scrolls (hard)",
    "Elite Treasure Trails (Rare)": "Clue Scrolls (elite)",
    "Master Treasure Trails (Rare)": "Clue Scrolls (master)",
}

# Unlike the pages in COLLECTION_LOG_CLUE_PAGE_TIERS, this page is the pool
# shared by every tier, so its count is the TOTAL of clues completed across all
# six tiers (see collection_log_page_kill_counts). "Scroll Cases" stays
# unmapped: it is reward slots, not a count.
COLLECTION_LOG_CLUE_TOTAL_PAGE = "Shared Treasure Trail Rewards"


def collection_log_page_kill_counts(
    boss_kill_counts: Dict[str, int],
    clue_scroll_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, List[int]]:
    """Maps GameAccount.boss_kill_counts and clue_scroll_counts (see
    app/models.py) onto collection log PAGE names. Read by read_collection_log
    in app/main.py so the collection log card can show a count next to pages
    that have one.
    
    Each value is a LIST of counts in display order: a page matching a
    HISCORE_BOSSES display_name gets one element; a
    COLLECTION_LOG_PAGE_NAME_OVERRIDES page gets one per constituent activity,
    all or nothing (a partial list would misrepresent the page); a
    COLLECTION_LOG_CLUE_PAGE_TIERS page gets its tier's count. The frontend
    joins multiple elements with a middot rather than summing.
    
    COLLECTION_LOG_CLUE_TOTAL_PAGE gets a single element: the sum across all
    six tiers (all-or-nothing).
    
    Pages without a mapping are absent from the result, which the frontend
    treats as "no count", not zero. Once an account has synced, every
    boss/tier is a key (0 for never killed), so only never-synced accounts get
    an empty result.
    """
    clue_scroll_counts = clue_scroll_counts or {}
    result: Dict[str, List[int]] = {}

    for _slug, boss_name, _has_icon in HISCORE_BOSSES:
        if boss_name in boss_kill_counts:
            result[boss_name] = [boss_kill_counts[boss_name]]

    for page_name, constituent_names in COLLECTION_LOG_PAGE_NAME_OVERRIDES.items():
        counts = [boss_kill_counts[name] for name in constituent_names if name in boss_kill_counts]
        if len(counts) == len(constituent_names):
            result[page_name] = counts

    for page_name, tier_name in COLLECTION_LOG_CLUE_PAGE_TIERS.items():
        if tier_name in clue_scroll_counts:
            result[page_name] = [clue_scroll_counts[tier_name]]

    if all(name in clue_scroll_counts for name in CLUE_SCROLL_HISCORE_NAMES):
        result[COLLECTION_LOG_CLUE_TOTAL_PAGE] = [
            sum(clue_scroll_counts[name] for name in CLUE_SCROLL_HISCORE_NAMES)
        ]

    return result

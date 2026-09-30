"""The canonical OSRS hiscores boss list -- single source of truth for
every boss/boss-like activity the official OSRS hiscores tracks (a
"Bosses" category entry: an NPC/activity killcount, not a skill,
minigame score, or other non-boss activity).

Originally built for the Goal Tracking reference table (see
render_goal_tracking in app/pages.py) by cross-referencing Wise Old
Man's own live player data (api.wiseoldman.net, which mirrors the
hiscores 1:1) and the OSRS Wiki's Module:Hiscores. Now load-bearing for
more than display, too: app/hiscores.py matches a fetched hiscores
activity back to a row here by exact name string, since the official
hiscores JSON endpoint's own "activities[].name" values are exactly
these -- confirmed directly against a real response, not assumed. If
Jagex ever renames or adds one, both the reference table and hiscores
syncing need this list updated together, which is why it lives in its
own module rather than staying private to pages.py.

Each entry is (slug, display_name, has_icon):
- slug: matches a file in app/static/boss-icons/<slug>.png when
  has_icon is True.
- display_name: exactly how the OSRS hiscores name this boss.
- has_icon: whether app/static/boss-icons/ has a matching RuneLite
  sprite. Artio/Callisto, Calvar'ion/Vet'ion, and Spindel/Venenatis are
  each a pair of twin bosses sharing one RuneLite icon (their easier
  singleplayer and harder multiplayer versions look the same, just
  reskinned) -- everything else has its own distinct icon.
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

# The official hiscores' own activities[].name string, wherever it
# differs from the display_name above -- confirmed directly against a
# live hiscores response, not assumed. Kept as a small override rather
# than changing display_name itself, since "The Mimic"/"The Nightmare"/
# "Kree'arra" read better on the Goal Tracking table (and match the
# OSRS Wiki's own article titles) than the hiscores' own bare "Mimic"/
# "Nightmare"/"Kree'Arra" would. app/hiscores.py uses this to match a
# fetched activity back to our display_name; nothing else needs it.
HISCORES_NAME_OVERRIDES = {
    "The Mimic": "Mimic",
    "The Nightmare": "Nightmare",
    "Kree'arra": "Kree'Arra",
}

# app/hiscores.py's own reverse lookup: the official hiscores' exact
# activity name string -> our slug, built once at import time rather
# than scanning HISCORE_BOSSES on every boss of every sync.
NAME_TO_SLUG = {
    HISCORES_NAME_OVERRIDES.get(name, name): slug for slug, name, _has_icon in HISCORE_BOSSES
}

# The reverse direction of the same override -- the official hiscores'
# activity name -> our display_name -- so a fetched boss can be stored
# under the name Goal Tracking's table actually looks up by.
HISCORES_NAME_TO_DISPLAY_NAME = {
    HISCORES_NAME_OVERRIDES.get(name, name): name for slug, name, _has_icon in HISCORE_BOSSES
}

# Same idea as HISCORES_NAME_OVERRIDES above, but for the raw text
# RuneLite's own chatbox uses in a "Your <boss> kill count is: <n>."
# style message (see app/hiscores.py::apply_kill_count_updates), which
# doesn't always match the hiscores' own activities[].name string
# either. Confirmed against RuneLite's own KILLCOUNT_RENAMES table
# (runelite-client's chatcommands/ChatCommandsPlugin.java, which reuses
# this same regex for its own !kc command) -- Barrows is the one
# concrete case that table records: the chatbox reports the plain,
# singular "Barrows chest", not our "Barrows Chests". Expected to grow
# as real players hit more mismatches RuneLite's own table already
# knows about but this one hasn't been seeded with yet.
CHAT_NAME_OVERRIDES = {
    "Barrows Chests": "Barrows chest",
}

# The chatbox's own "Your <boss> kill count is: <n>." message drops
# the stylistic "The " every "The <Name>" hiscores boss's display_name
# carries (The Gauntlet, The Nightmare, The Royal Titans, ...) --
# confirmed directly in-game for "Royal Titans" and "Corrupted
# Gauntlet" specifically (reported after a real kill of each didn't
# bump the Character Overview page's totals: apply_kill_count_updates
# never recognized "Royal Titans"/"Corrupted Gauntlet" as a display
# name it knew, since CHAT_NAME_TO_DISPLAY_NAME below only had the
# full "The Royal Titans"/"The Corrupted Gauntlet" to match against),
# and applied here to every other "The "-prefixed boss on the list too
# rather than left as a one-off -- it's the same stylistic-article-
# only-in-hiscores/wiki-display pattern in every case, not something
# specific to those two. Computed from HISCORE_BOSSES itself (any
# "The "-prefixed display_name not already given its own entry above)
# rather than spelled out one boss at a time, so a future Jagex boss
# following the same "The <Name>" convention self-heals the same way
# without needing its own line added here.
for _slug, _name, _has_icon in HISCORE_BOSSES:
    if _name.startswith("The ") and _name not in CHAT_NAME_OVERRIDES:
        CHAT_NAME_OVERRIDES[_name] = _name[len("The "):]
del _slug, _name, _has_icon

# app/hiscores.py's own reverse lookup for chat-parsed updates: the
# chatbox's exact wording -> our display_name, matched
# case-insensitively there (chat capitalization isn't as reliably
# consistent as the hiscores API's own JSON), built once at import time
# the same way HISCORES_NAME_TO_DISPLAY_NAME is.
CHAT_NAME_TO_DISPLAY_NAME = {
    CHAT_NAME_OVERRIDES.get(name, name): name for slug, name, _has_icon in HISCORE_BOSSES
}

# Collection log PAGE names (see app.collectionlog.get_collection_log_tabs)
# whose kill/completion count isn't a single HISCORE_BOSSES display_name
# read directly -- either because the page groups more than one
# hiscores-tracked activity (the twin/trio-boss pairs, a raid's normal
# and harder mode, or The Nightmare/Phosani's Nightmare sharing one
# page), or the page's own name differs from its hiscores boss by more
# than the "The " prefix every other "The <Name>" boss already matches
# directly (Royal Titans/The Mad Angel go opposite directions from
# their hiscores name, so neither is a plain strip/add-"The " rule --
# see each one's own hiscores display_name in HISCORE_BOSSES above).
# Every value here is a LIST, in display order (easier/base mode first,
# harder mode second -- e.g. Tombs of Amascut before its Expert Mode) --
# collection_log_page_kill_counts shows each entry individually
# ("1,234 · 56"), not summed, so a page like "Callisto and Artio"
# reads as two real numbers rather than one combined total that hides
# which twin the player has actually killed more of. Confirmed against
# a real collection log page list, not guessed -- content this app
# hasn't verified a hiscores mapping for yet (Moons of Peril, at time
# of writing) is deliberately left out of both this table and
# collection_log_page_kill_counts's own result, rather than risk
# showing a wrong number next to it.
COLLECTION_LOG_PAGE_NAME_OVERRIDES: Dict[str, List[str]] = {
    "Callisto and Artio": ["Callisto", "Artio"],
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

# The official hiscores' own clue-tier activity names (app/hiscores.py's
# own _parse_clue_scroll_counts reads these off the same activities[]
# list HISCORE_BOSSES' names come from) -- confirmed directly against a
# live hiscores response, not guessed. "Clue Scrolls (all)" is
# deliberately excluded: no single collection log page corresponds to
# the all-tiers combined total, only the six individual tiers below do.
CLUE_SCROLL_HISCORE_NAMES: List[str] = [
    "Clue Scrolls (beginner)",
    "Clue Scrolls (easy)",
    "Clue Scrolls (medium)",
    "Clue Scrolls (hard)",
    "Clue Scrolls (elite)",
    "Clue Scrolls (master)",
]

# Collection log PAGE name -> the one hiscores clue tier that page's
# completion count comes from. A tier with its own separate "(Rare)"
# unique-drop page (Hard/Elite/Master) maps both pages to the same tier
# name, since both draw from the same underlying completion count --
# confirmed against a real collection log page list. "Shared Treasure
# Trail Rewards" and "Scroll Cases" aren't tier-specific (obtainable
# from more than one tier) and are deliberately left unmapped, same
# "don't guess" reasoning as COLLECTION_LOG_PAGE_NAME_OVERRIDES above.
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


def collection_log_page_kill_counts(
    boss_kill_counts: Dict[str, int],
    clue_scroll_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, List[int]]:
    """Maps GameAccount.boss_kill_counts and GameAccount.clue_scroll_counts
    (see both columns' own docstrings in app/models.py) onto collection log
    PAGE names, for every page this module can confidently match to one or
    more hiscores-tracked counts. Read by read_collection_log in app/main.py
    so the Character Overview page's collection log card can show a kill/
    completion count next to the pages that have one, the same way the real
    in-game collection log does, without the frontend needing its own copy
    of this mapping.

    Every result value is a LIST of one or more counts, in display order --
    a page whose name exactly matches a HISCORE_BOSSES display_name (the
    large majority of boss/raid pages) gets a single-element list; a page in
    COLLECTION_LOG_PAGE_NAME_OVERRIDES gets one element per constituent
    activity, ALL of them, not just however many happen to be present (a
    partial list -- e.g. only Callisto's count, Artio's missing -- would
    silently misrepresent the page rather than honestly show nothing); a
    page in COLLECTION_LOG_CLUE_PAGE_TIERS gets its one clue-tier count.
    The frontend joins a multi-element list with a middot
    ("1,234 · 56") rather than summing it, so e.g. Callisto and
    Artio's page shows each twin's own count instead of one combined total
    that hides which twin the player has actually killed more of.

    Every other collection log page (minigames/activities the hiscores
    "Bosses" category doesn't track, Shared Treasure Trail Rewards/Scroll
    Cases, and any boss this app hasn't verified a mapping for yet) is
    simply absent from the result -- the frontend treats a missing entry
    as "no count for this page" rather than zero.

    Every hiscores boss/clue tier is a key in boss_kill_counts/
    clue_scroll_counts once an account has synced at least once (0 for
    "never killed it"/"never completed one", see _parse_boss_kill_counts
    and _parse_clue_scroll_counts in app/hiscores.py), so a mapped page
    reads as a real number either way and only an account that's never
    linked/synced gets an empty result here."""
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

    return result

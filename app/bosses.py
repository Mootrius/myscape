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
from typing import List, Tuple

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

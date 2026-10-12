"""Icon URLs shared by the dashboard and the feature pages."""
import urllib.parse

from app.purchase_goals import item_icon_url

# Dashboard card icons: real OSRS items via item_icon_url
# (app/purchase_goals.py), which resolves to RuneLite's icon CDN by item id, so
# no icons are hosted here. Coins (995) resolves to the "biggest pile" art.
# Clueless scroll (20249) is a real novelty item, not a clue scroll.
_ICON_COINS = item_icon_url(995)

_ICON_BONES = item_icon_url(536)

_ICON_CLUELESS_SCROLL = item_icon_url(20249)

_ICON_HEAVY_CASKET = item_icon_url(19941)

_ICON_MAX_CAPE = item_icon_url(13280)

_ICON_CAKE_OF_GUIDANCE = item_icon_url(7542)

# Bundled PNG: no OSRS item reads as "your character".
_ICON_CHARACTER_OVERVIEW = "/static/img/icon-character-overview.png"


def _wiki_icon_url(filename: str) -> str:
    """Routed through /icon-cache/<filename> (app/icon_cache.py), like
    npc_icon_url in app/loot.py, because direct wiki hotlinks trip the wiki's
    rate limiting. Used by the Character Overview summary icons (wiki UI
    chrome, not items).
    """
    return "/icon-cache/" + urllib.parse.quote(filename)

"""The dashboard: one card per feature."""
from html import escape

from app.pages.icons import (
    _ICON_BONES,
    _ICON_CAKE_OF_GUIDANCE,
    _ICON_CHARACTER_OVERVIEW,
    _ICON_CLUELESS_SCROLL,
    _ICON_COINS,
    _ICON_HEAVY_CASKET,
    _ICON_MAX_CAPE,
)
from app.pages.player import PlayerView
from app.pages.shell import _shell


def _dash_card(icon_src: str, icon_alt: str, title: str, description: str, extra_class: str = "") -> str:
    card_class = f"dash-card {extra_class}".strip()
    return f"""
    <div class="{card_class}">
      <div class="dash-card-icon"><img src="{escape(icon_src)}" alt="{escape(icon_alt)}" /></div>
      <div class="dash-card-body">
        <h3>{escape(title)}</h3>
        <p class="subtitle">{escape(description)}</p>
      </div>
    </div>
    """


def _dash_card_wrap(href: str, icon_src: str, icon_alt: str, title: str, description: str, extra_class: str = "") -> str:
    return f"""
    <div class="dash-card-wrap">
      <a href="{escape(href)}" class="dash-card-link">
        {_dash_card(icon_src, icon_alt, title, description, extra_class)}
      </a>
    </div>
    """


# Every dashboard card, keyed by a stable id independent of title/route/copy.
# The tuple order is the one fixed dashboard order.
DASHBOARD_CARD_KEYS = (
    "character_overview",
    "loot_tracker",
    "purchase_goals",
    "possessions",
    "mindmaps",
    "goal_tracking",
)


def render_dashboard(player: PlayerView) -> str:
    cards = {
        "loot_tracker": _dash_card_wrap(
            "/dashboard/loot-tracker",
            _ICON_BONES,
            "Dragon bones",
            "Loot Tracker",
            "Track the loot from any NPC you kill, with useful graphs and other "
            "statistics available for your tracking pleasure. Customize which "
            "NPCs are tracked and what data is shown.",
        ),
        "purchase_goals": _dash_card_wrap(
            "/dashboard/purchase-goals",
            _ICON_COINS,
            "Coins",
            "Purchase Goals",
            "Track your owned GP against the purchases you'd like to make on the "
            "Grand Exchange, all with live pricing updates for each item. "
            "Organize multiple setups to keep track of at once.",
        ),
        "mindmaps": _dash_card_wrap(
            "/dashboard/mindmaps",
            _ICON_CLUELESS_SCROLL,
            "Clueless scroll",
            "Mindmaps",
            "Organize your goals into a mindmap! Start from one goal and branch "
            "out with parent, child, and sibling nodes — all with "
            "auto-detecting completion functionality.",
        ),
        "possessions": _dash_card_wrap(
            "/dashboard/storages-viewer",
            _ICON_HEAVY_CASKET,
            "Heavy casket",
            "Storages Viewer",
            "Keep an eye on what you own across every storage in the game. "
            "Search it all, sort by anything, and filter to your heart's "
            "content — all in one place!",
        ),
        "goal_tracking": _dash_card_wrap(
            "/dashboard/goal-tracking",
            _ICON_MAX_CAPE,
            "Max cape",
            "Goal Tracking",
            "Visualize your goals by setting time-based or one-off quotas "
            "for yourself to meet, complete with auto-detecting and "
            "updating progress bars.",
        ),
        "character_overview": _dash_card_wrap(
            "/dashboard/character-overview",
            _ICON_CHARACTER_OVERVIEW,
            "Character overview icon",
            "Character Overview",
            "See your account's most relevant details all at a glance "
            "\u2014 including collection logs, skill levels, quest "
            "completions, achievement diaries, combat achievements, "
            "and more!",
        ),
    }

    cards_html = "\n      ".join(cards[key] for key in DASHBOARD_CARD_KEYS)

    # Help & Support sits outside DASHBOARD_CARD_KEYS: a smaller card on its own
    # row below the app cards.
    support_card_html = _dash_card_wrap(
        "/dashboard/help-and-support",
        _ICON_CAKE_OF_GUIDANCE,
        "Cake of guidance",
        "Help & Support",
        "See the FAQ, report bugs, and request features.",
        "dash-card--compact",
    )

    body = f"""
    <div class="dash-grid" id="dashGrid">
      {cards_html}
    </div>
    <div class="dash-support-row">
      {support_card_html}
    </div>
    """

    return _shell(title="Dashboard — myscape", player=player, body=body)

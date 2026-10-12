"""Server-rendered HTML pages (landing, signup, login, dashboard). Plain
f-strings, no template engine.
"""
from app.pages.account import render_account
from app.pages.auth_pages import (
    render_forgot_password,
    render_login,
    render_not_found,
    render_reset_password,
    render_signup,
    render_signup_coming_soon,
    render_verify_email,
    render_verify_email_required,
)
from app.pages.character_overview import (
    _MODEL_VIEWER_BACKGROUNDS,
    render_character_overview,
    render_landing_character_overview_preview,
    render_public_character_overview,
)
from app.pages.dashboard import DASHBOARD_CARD_KEYS, render_dashboard
from app.pages.goal_tracking import (
    render_goal_tracking,
    render_goal_tracking_share,
    render_landing_goal_tracking_preview,
)
from app.pages.help_support import render_help_support
from app.pages.landing import render_landing
from app.pages.loot_tracker import (
    render_landing_loot_preview,
    render_loot_tracker,
    render_loot_tracker_share,
)
from app.pages.mindmaps import render_landing_mindmap_preview, render_mindmap_share, render_mindmaps
from app.pages.player import PlayerView, build_player_view
from app.pages.possessions import (
    render_landing_storages_preview,
    render_possessions,
    render_storages_share,
)
from app.pages.purchase_goals import (
    render_landing_purchase_preview,
    render_purchase_goals,
    render_purchase_goals_share,
)
from app.pages.shell import _SITE_URL

__all__ = [
    "PlayerView",
    "build_player_view",
    "_SITE_URL",
    "render_landing",
    "DASHBOARD_CARD_KEYS",
    "render_dashboard",
    "render_help_support",
    "_MODEL_VIEWER_BACKGROUNDS",
    "render_character_overview",
    "render_public_character_overview",
    "render_landing_character_overview_preview",
    "render_account",
    "render_signup",
    "render_signup_coming_soon",
    "render_login",
    "render_forgot_password",
    "render_reset_password",
    "render_verify_email_required",
    "render_verify_email",
    "render_not_found",
    "render_purchase_goals",
    "render_landing_purchase_preview",
    "render_purchase_goals_share",
    "render_loot_tracker",
    "render_landing_loot_preview",
    "render_loot_tracker_share",
    "render_landing_mindmap_preview",
    "render_mindmaps",
    "render_mindmap_share",
    "render_landing_storages_preview",
    "render_possessions",
    "render_storages_share",
    "render_landing_goal_tracking_preview",
    "render_goal_tracking",
    "render_goal_tracking_share",
]

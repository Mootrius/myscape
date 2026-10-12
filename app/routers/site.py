"""Site pages (landing, auth pages, dashboard pages), icon cache, robots/sitemap and health checks."""
from email.utils import format_datetime, parsedate_to_datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import site_flags
from app.auth import get_optional_current_player_view_from_session
from app.database import get_db
from app.icon_cache import ensure_cached_icon
from app.pages import (
    _SITE_URL,
    PlayerView,
    render_account,
    render_character_overview,
    render_dashboard,
    render_forgot_password,
    render_goal_tracking,
    render_help_support,
    render_landing,
    render_login,
    render_loot_tracker,
    render_mindmaps,
    render_possessions,
    render_purchase_goals,
    render_reset_password,
    render_signup,
    render_signup_coming_soon,
    render_verify_email,
    render_verify_email_required,
)

router = APIRouter()


def _icon_not_modified(request: Request, etag: str, last_modified) -> bool:
    """Whether the browser's conditional headers say its copy is current.
    If-None-Match wins over If-Modified-Since, as in RFC 9110.
    """
    if_none_match = request.headers.get("if-none-match")
    if if_none_match:
        candidates = {tag.strip().removeprefix("W/") for tag in if_none_match.split(",")}
        return "*" in candidates or etag in candidates
    since = request.headers.get("if-modified-since")
    if since:
        try:
            return last_modified.replace(microsecond=0) <= parsedate_to_datetime(since)
        except (TypeError, ValueError):
            return False
    return False


@router.get("/icon-cache/{filename}")
def get_cached_icon(filename: str, request: Request):
    """Serves a wiki-sourced icon via ensure_cached_icon (app/icon_cache.py)
    with a long-lived Cache-Control, plus ETag/Last-Modified so a revalidating
    browser gets a 304. Item icons use the RuneLite CDN directly; this serves
    NPC/event portraits and rare combination items missing from
    app/item_ids.py. The filename is re-validated there.
    """
    icon = ensure_cached_icon(filename)
    if not icon:
        raise HTTPException(status_code=404)
    headers = {
        "Cache-Control": "public, max-age=604800, immutable",
        "ETag": icon.etag,
        "Last-Modified": format_datetime(icon.fetched_at, usegmt=True),
    }
    if _icon_not_modified(request, icon.etag, icon.fetched_at):
        return Response(status_code=304, headers=headers)
    return Response(content=icon.data, media_type=icon.content_type, headers=headers)


@router.get("/", response_class=HTMLResponse)
def root(
    home: Optional[str] = None,
    player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session),
):
    # A logged-in player goes straight to /dashboard, except via the header logo
    # (_shell() in app/pages/shell.py), which adds ?home=1 while signed in.
    if player and not home:
        return RedirectResponse("/dashboard", status_code=302)
    return render_landing(player)


# Every page _shell() renders noindex (app/pages/); keep in sync when adding a
# page. /dashboard covers all /dashboard/* by prefix.
_ROBOTS_TXT = """User-agent: *
Allow: /
Disallow: /dashboard
Disallow: /account
Disallow: /login
Disallow: /signup
Disallow: /forgot-password
Disallow: /reset-password
Disallow: /verify-email
Disallow: /verify-email-required
Disallow: /api/

Sitemap: """ + _SITE_URL + """/sitemap.xml
"""


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt():
    return _ROBOTS_TXT


# The landing page is the only indexable URL _shell() renders.
_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>""" + _SITE_URL + """/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
"""


@router.get("/sitemap.xml")
def sitemap_xml():
    return Response(content=_SITEMAP_XML, media_type="application/xml")


@router.get("/signup", response_class=HTMLResponse)
def signup_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if player:
        return RedirectResponse("/dashboard", status_code=302)
    if not site_flags.SIGNUPS_ENABLED:
        # Sign-ups are off for now; see app/site_flags.py.
        return render_signup_coming_soon()
    return render_signup()


@router.get("/login", response_class=HTMLResponse)
def login_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if player:
        return RedirectResponse("/dashboard", status_code=302)
    return render_login()


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if player:
        return RedirectResponse("/dashboard", status_code=302)
    return render_forgot_password()


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    # No redirect-if-logged-in: the token is read client-side from the query
    # string, and a reset link may be used in another tab.
    return render_reset_password()


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_dashboard(player)


@router.get("/account", response_class=HTMLResponse)
def account_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    # No email_verified_at gate, unlike dashboard_page: log out and fixing a
    # mistyped signup email must stay reachable before verification (see
    # render_account's docstring).
    if not player:
        return RedirectResponse("/login", status_code=302)
    return render_account(player)


@router.get("/verify-email-required", response_class=HTMLResponse)
def verify_email_required_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if player.email_verified_at:
        # Nothing to do here; most likely already verified in another tab or a
        # stale link.
        return RedirectResponse("/dashboard", status_code=302)
    return render_verify_email_required(player)


@router.get("/verify-email", response_class=HTMLResponse)
def verify_email_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if player and player.email_verified_at:
        # Already verified; nothing left for this page to do.
        return RedirectResponse("/dashboard", status_code=302)
    # No redirect-if-logged-out: the email link may open in a different browser
    # session. `player` is still passed so the header nav is correct.
    return render_verify_email(player)


@router.get("/api/health")
def health():
    """Proves the app is up. Doesn't touch the database (see /api/health/db), so
    it answers even if the database is briefly unreachable.
    """
    return {"status": "ok"}


@router.get("/api/health/db")
def health_db(db: Session = Depends(get_db)):
    """Proves the app can reach and query the database."""
    player_count = db.execute(text("SELECT COUNT(*) FROM game_accounts")).scalar()
    return {"status": "ok", "playerCount": player_count}


@router.get("/dashboard/purchase-goals", response_class=HTMLResponse)
def purchase_goals_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_purchase_goals(player)


@router.get("/dashboard/loot-tracker", response_class=HTMLResponse)
def loot_tracker_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_loot_tracker(player)


@router.get("/dashboard/mindmaps", response_class=HTMLResponse)
def mindmaps_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_mindmaps(player)


@router.get("/dashboard/storages-viewer", response_class=HTMLResponse)
def possessions_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_possessions(player)


@router.get("/dashboard/goal-tracking", response_class=HTMLResponse)
def goal_tracking_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    """No sync on page load: KC data is seeded at link time and kept current by
    chatbox updates, so boss_kill_counts is read as-is.
    """
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_goal_tracking(player)


@router.get("/dashboard/help-and-support", response_class=HTMLResponse)
def help_support_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    """Same login/verified gate as every other /dashboard/* page (see
    render_help_support in app/pages/).
    """
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_help_support(player)


@router.get("/dashboard/character-overview", response_class=HTMLResponse)
def character_overview_page(player: Optional[PlayerView] = Depends(get_optional_current_player_view_from_session)):
    """Same login/verified gate as every other /dashboard/* page (see
    render_character_overview in app/pages/).
    """
    if not player:
        return RedirectResponse("/login", status_code=302)
    if not player.email_verified_at:
        return RedirectResponse("/verify-email-required", status_code=302)
    return render_character_overview(player)

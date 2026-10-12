"""myscape's web app: landing page, health checks, and the account system
(website signup/login, RuneLite plugin account linking). See README.md for how
the pieces fit together.
"""
import logging
import os

# Without this the root logger drops every log.info() call (e.g. email_client's
# "RESEND_API_KEY not set" line) before it reaches Render's logs.
logging.basicConfig(level=logging.INFO)

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import http_exception_handler as _default_http_exception_handler
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.auth import (
    get_optional_current_account_from_session,
    get_optional_current_player_view_from_session,
)
from app.database import SessionLocal
from app.limiter import limiter
from app.pages import render_not_found
from app.permanent_examples import capture_permanent_examples
from app.routers import (
    account,
    auth,
    character_overview,
    character_sync,
    friends,
    goals,
    linking,
    loot,
    mindmaps,
    possessions,
    purchase_goals,
    search,
    shares,
    site,
    storage_sync,
)
from app.routers.shared import (
    _character_overview_progress_payload,
    _character_overview_summary_payload,
    _collection_log_payload,
    _skills_payload,
)

SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY")
if not SESSION_SECRET_KEY:
    raise RuntimeError(
        "SESSION_SECRET_KEY is not set. Generate one (e.g. `python -c "
        "'import secrets; print(secrets.token_hex(32))'`) and set it as an "
        "environment variable -- see .env.example. On Render, render.yaml "
        "already has it set to auto-generate and persist a value."
    )

app = FastAPI(title="myscape")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(StarletteHTTPException)
async def _styled_not_found_handler(request: Request, exc: StarletteHTTPException):
    """Swaps in render_not_found's styled page for 404s on site pages. /api/*,
    /static/* and non-404 statuses keep FastAPI's JSON {"detail": ...} body,
    which the site's JS (describeError() in app/pages.py) parses.
    
    Registered on Starlette's HTTPException because unmatched routes raise the
    base class, which a handler on the fastapi subclass never sees.
    """
    if exc.status_code == status.HTTP_404_NOT_FOUND and not request.url.path.startswith(("/api/", "/static/")):
        # Exception handlers bypass dependency injection, so the DB session is
        # opened by hand (for the signed-in nav). Dependencies are called
        # directly, so every argument must be passed explicitly or the literal
        # Depends(...) marker leaks through.
        db = SessionLocal()
        try:
            account = get_optional_current_account_from_session(request, db)
            player = get_optional_current_player_view_from_session(request, db, account)
        finally:
            db.close()
        return HTMLResponse(render_not_found(player), status_code=status.HTTP_404_NOT_FOUND)
    return await _default_http_exception_handler(request, exc)
# Session cookies back website login (see app/auth.py). `https_only` is on
# because myscape.io is HTTPS-only in production; for local http://localhost
# testing override it with an env var rather than deleting it.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    same_site="lax",
    https_only=os.environ.get("SESSION_COOKIE_HTTPS_ONLY", "true").lower() != "false",
    max_age=60 * 60 * 24 * 30,  # 30 days
)
app.include_router(account.router)
app.include_router(auth.router)
app.include_router(friends.router)
app.include_router(linking.router)

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
app.include_router(site.router)
app.include_router(storage_sync.router)
app.include_router(character_sync.router)
app.include_router(character_overview.router)
app.include_router(shares.router)
app.include_router(loot.router)
app.include_router(search.router)
app.include_router(possessions.router)
app.include_router(purchase_goals.router)
app.include_router(mindmaps.router)
app.include_router(goals.router)


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@app.on_event("startup")
def on_startup():
    # Applies pending migrations/versions/*.py (see README.md "Database schema
    # changes"). Runs on every startup, safe because the service is a single
    # instance; the initial migration skips existing tables, so production needs
    # no manual stamping.
    alembic_cfg = Config(os.path.join(_REPO_ROOT, "alembic.ini"))
    command.upgrade(alembic_cfg, "head")

    # Copies the README's permanent example links into their own table on first
    # sight (app/permanent_examples.py). Must never stop the app from booting.
    db = SessionLocal()
    try:
        capture_permanent_examples(
            db,
            {
                "summary": _character_overview_summary_payload,
                "progress": _character_overview_progress_payload,
                "skills": _skills_payload,
                "collection-log": _collection_log_payload,
            },
        )
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception("Could not capture permanent examples.")
    finally:
        db.close()

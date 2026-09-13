"""myscape's web app: a placeholder landing page, health checks, and the
early account system (website signup/login, RuneLite plugin account
linking) -- see README.md for how the pieces fit together.
"""
import os
from typing import Optional

from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_player_from_api_key, get_optional_current_player_from_session
from app.database import get_db
from app.limiter import limiter
from app.models import Player
from app.pages import render_dashboard, render_landing, render_login, render_signup
from app.routers import auth, linking
from app.schemas import PlayerOut

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
# Session cookies back website login (see app/auth.py). `https_only` is on
# because myscape.io is HTTPS-only in production; if that ever gets in the
# way of local http://localhost testing, override it with an env var --
# don't just delete it.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    same_site="lax",
    https_only=os.environ.get("SESSION_COOKIE_HTTPS_ONLY", "true").lower() != "false",
    max_age=60 * 60 * 24 * 30,  # 30 days
)
app.include_router(auth.router)
app.include_router(linking.router)

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@app.on_event("startup")
def on_startup():
    # Brings the database up to the latest schema by applying whichever
    # of migrations/versions/*.py it hasn't seen yet (see README.md's
    # "Database schema changes") -- the Alembic equivalent of the old
    # Base.metadata.create_all() + sync_missing_columns() pair this
    # replaced, which is also why this still runs unconditionally on
    # every startup rather than as a separate deploy step: it's the
    # smallest change from the previous behavior, and safe here since
    # this service only ever runs as a single instance. The very first
    # migration is written defensively (skips any table that already
    # exists) specifically so this needs no one-time manual step to
    # tell Alembic that production's existing tables are already
    # "migrated" -- see migrations/versions/5cf359e6d5b1_initial_schema.py.
    alembic_cfg = Config(os.path.join(_REPO_ROOT, "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


@app.get("/", response_class=HTMLResponse)
def root(player: Optional[Player] = Depends(get_optional_current_player_from_session)):
    if player:
        return RedirectResponse("/dashboard", status_code=302)
    return render_landing(None)


@app.get("/signup", response_class=HTMLResponse)
def signup_page(player: Optional[Player] = Depends(get_optional_current_player_from_session)):
    if player:
        return RedirectResponse("/dashboard", status_code=302)
    return render_signup()


@app.get("/login", response_class=HTMLResponse)
def login_page(player: Optional[Player] = Depends(get_optional_current_player_from_session)):
    if player:
        return RedirectResponse("/dashboard", status_code=302)
    return render_login()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(player: Optional[Player] = Depends(get_optional_current_player_from_session)):
    if not player:
        return RedirectResponse("/login", status_code=302)
    return render_dashboard(player)


@app.get("/api/health")
def health():
    """Proves the app itself is up. Doesn't touch the database -- see
    /api/health/db for that -- so this stays fast and always answers even
    if the database is briefly unreachable."""
    return {"status": "ok"}


@app.get("/api/health/db")
def health_db(db: Session = Depends(get_db)):
    """Proves the app can actually reach and query the database -- the
    real end-to-end check for a first deploy."""
    player_count = db.execute(text("SELECT COUNT(*) FROM players")).scalar()
    return {"status": "ok", "playerCount": player_count}


@app.get("/api/players/me", response_model=PlayerOut)
def read_current_player(player: Player = Depends(get_current_player_from_api_key)):
    """First real use of the API key auth: the plugin calls this (with
    its `Authorization: Bearer <key>` header) to confirm it's linked and
    see which player it's linked to."""
    return player


@app.post("/api/players/me/unlink", status_code=status.HTTP_204_NO_CONTENT)
def unlink_player(db: Session = Depends(get_db), player: Player = Depends(get_current_player_from_api_key)):
    """Called by the RuneLite plugin's "Unlink" button (API-key
    authenticated). See linking.revoke_link() for what this actually
    does and why POST /api/link/unlink there is this endpoint's
    session-authenticated counterpart, not a duplicate."""
    linking.revoke_link(db, player)

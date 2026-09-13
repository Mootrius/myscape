"""myscape's web app: a placeholder landing page, health checks, and the
early account system (website signup/login, RuneLite plugin account
linking) -- see README.md for how the pieces fit together.
"""
import os

from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_player_from_api_key
from app.database import Base, engine, get_db
from app.limiter import limiter
from app.models import LinkCode, Player, PlayerApiKey  # noqa: F401 -- imported so create_all sees them
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


@app.on_event("startup")
def on_startup():
    # Fine for this early stage. Once the schema needs to change without
    # wiping data, switch to real Alembic migrations instead of
    # create_all -- see README.md's "Next steps" section.
    Base.metadata.create_all(bind=engine)


@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <title>myscape</title>
        <style>
          body { background: #0f0f10; color: #ece6d8; font-family: system-ui, sans-serif;
                 display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
          h1 { font-weight: normal; letter-spacing: 0.04em; }
        </style>
      </head>
      <body>
        <h1>myscape &mdash; coming soon</h1>
      </body>
    </html>
    """


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

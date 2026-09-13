"""myscape's web app: for now, just a placeholder landing page plus two
health-check endpoints, so the very first deploy proves the whole chain
works end to end (Render -> this app -> the Postgres database) before any
real feature gets built on top of it.
"""
from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Player  # noqa: F401 -- imported so create_all sees it

app = FastAPI(title="myscape")


@app.on_event("startup")
def on_startup():
    # Fine for this early, single-table stage. Once the schema needs to
    # change without wiping data, switch to real Alembic migrations
    # instead of create_all -- see README.md's "Next steps" section.
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

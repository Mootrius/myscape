"""Database engine/session setup.

Reads DATABASE_URL from the environment. Render sets this automatically
for a web service that's wired to a database via render.yaml's
`fromDatabase` (see render.yaml at the repo root). For local development,
copy .env.example to .env and point it at a local Postgres instance (or
any Postgres you have handy) -- see README.md.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env and fill in a "
        "Postgres connection string, or (in production) attach a database "
        "to this service in render.yaml."
    )

# Render (like most managed Postgres providers) hands out URLs starting
# with "postgres://", but SQLAlchemy's psycopg driver wants "postgresql://"
# -- this keeps both spellings working without anyone having to remember
# the difference.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session, always closed after the
    request -- see its usage with Depends(get_db) in main.py."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

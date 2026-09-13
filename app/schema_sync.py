"""A stopgap for the biggest limitation of `Base.metadata.create_all()`:
it creates tables that don't exist yet, but it never alters a table that
already exists -- so a column added to a model after its table has
already been deployed once (like `Player.account_hash` and
`Player.password_hash`, both added after the `players` table already
existed in production) silently never reaches the live database. The
app keeps running -- it just fails at the exact moment something tries
to write that missing column, which is what happened here: signup broke
because `players.password_hash` didn't exist yet on Render's database.

This function closes that specific gap: for every table `create_all`
already knows about, it adds any column present on the SQLAlchemy model
but missing from the live table. It is intentionally narrow --
additive only, and only safe because every column ever added this way
has been nullable, so existing rows just get NULL and keep working. It
does not rename, retype, or add constraints/indexes. The moment a
change needs any of that, it's time to bring in real Alembic migrations
(see README.md's "Next steps") instead of extending this.

Dropping a column is a different kind of risk than adding one -- doing
it generically (drop anything on the live table that the current model
doesn't mention) would silently destroy data the moment a column is
just temporarily missing mid-refactor. So that's not automated here.
`_OBSOLETE_COLUMNS` below is a short, explicit, hand-maintained list of
columns known to be genuinely dead (not just "not in the model right
now") -- so far, just `players.verification_code`, a NOT NULL leftover
from the very first Player model, fully replaced by the LinkCode/
PlayerApiKey system and unreferenced anywhere in the current code. Left
in place, it blocks every INSERT into players (NOT NULL, no default,
and the current ORM model never sets it) -- which is exactly what broke
signup in production. Add to this list by hand, deliberately, when a
column is confirmed dead -- never generate it from a schema diff.
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeMeta

_OBSOLETE_COLUMNS = {
    "players": ["verification_code"],
}


def sync_missing_columns(engine: Engine, base: DeclarativeMeta) -> None:
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue  # brand new table -- create_all already made it in full
            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                col_type = column.type.compile(dialect=conn.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))

            for obsolete_name in _OBSOLETE_COLUMNS.get(table.name, []):
                if obsolete_name in existing_columns:
                    conn.execute(text(f'ALTER TABLE "{table.name}" DROP COLUMN "{obsolete_name}"'))

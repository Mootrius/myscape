# myscape

The backend + website for myscape: an Old School RuneScape companion app
(a website plus a RuneLite plugin) for tracking purchase goals, loot, and
more. This repo is the FastAPI + PostgreSQL backend that both the website
pages and the RuneLite plugin talk to.

## What's here right now

This is deliberately minimal -- just enough to prove the whole chain
(Render -> this app -> its database) works end to end before any real
feature gets built on top of it:

- `app/main.py` -- the FastAPI app. A placeholder landing page at `/`,
  plus `/api/health` (is the app up) and `/api/health/db` (can it reach
  the database).
- `app/database.py` -- SQLAlchemy engine/session setup, reading the
  database connection string from the `DATABASE_URL` environment
  variable.
- `app/models.py` -- one `Player` table, the seed of the account-linking
  system: each player gets a `verification_code` that will eventually get
  pasted into the RuneLite plugin's settings, so the plugin can prove
  which website account it belongs to without the server ever having to
  trust a client-asserted username.
- `render.yaml` -- tells Render how to deploy this: one web service, one
  Postgres database, wired together automatically.

## Local development

1. Install Python 3.11+, then: `pip install -r requirements.txt`
2. Get a Postgres database to point at (a local install, or a free
   throwaway one from Render/another provider).
3. `cp .env.example .env` and fill in `DATABASE_URL` with that database's
   connection string.
4. `uvicorn app.main:app --reload` and open http://localhost:8000

## Deploying

Push to GitHub, then in the Render dashboard choose "New +" -> "Blueprint"
and point it at this repo -- `render.yaml` tells it to create both the web
service and the database and wire them together. First deploy takes a few
minutes. Once it's up, `/api/health/db` should return
`{"status": "ok", "playerCount": 0}`.

## Next steps (not built yet)

- Purchase Goals / Loot Tracker data model and API endpoints (porting the
  logic from the original single-user Maintrius tool)
- The actual RuneLite plugin (separate repo) that reads bank/inventory/
  equipment/loot data and POSTs it here
- A real signup/login flow tying a website account to a `Player` row
- Switch from `Base.metadata.create_all` to real Alembic migrations once
  the schema needs to change without wiping data
- Point myscape.io's DNS at Render once the first deploy is verified

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
  `/api/health` (is the app up), `/api/health/db` (can it reach the
  database), `/api/players/me` (first real use of API-key auth -- the
  plugin calls this to confirm it's linked), and the session-cookie
  middleware backing website login.
- `app/database.py` -- SQLAlchemy engine/session setup, reading the
  database connection string from the `DATABASE_URL` environment
  variable.
- `app/models.py` -- `Player` (now with a `password_hash`), `LinkCode`,
  and `PlayerApiKey`. See "Account linking" below for how the latter two
  fit together.
- `app/security.py` -- random token generation + SHA-256 hashing for the
  link code and API key, plus scrypt password hashing for website
  accounts.
- `app/auth.py` -- two auth dependencies: `get_current_player_from_session`
  (website, via the signed session cookie) and
  `get_current_player_from_api_key` (RuneLite plugin, via `Authorization:
  Bearer <key>`).
- `app/routers/auth.py` -- website signup/login/logout
  (`/api/auth/signup`, `/api/auth/login`, `/api/auth/logout`,
  `/api/auth/me`).
- `app/limiter.py` / `app/routers/linking.py` -- the account-linking
  endpoints (`POST /api/link/start`, `POST /api/link/exchange`), the
  latter rate-limited per-IP.
- `render.yaml` -- tells Render how to deploy this: one web service, one
  Postgres database, and a generated session-signing secret, all wired
  together automatically.
- `app/pages.py` -- the server-rendered signup/login/landing pages (no
  template engine -- plain f-strings, since there are only three pages).
- `app/static/` -- the shared stylesheet and the two custom fonts, in
  the same dark/gold palette as Maintrius (the original desktop tool).
  Served as real static files (not inlined as base64 like Maintrius's
  local HTML) so browsers cache them across page loads.

## Website accounts

`POST /api/auth/signup` (email + password, min 8 characters) creates a
`Player` row with a scrypt-hashed password and immediately logs the
browser in via a signed session cookie. `POST /api/auth/login` and
`POST /api/auth/logout` do what they say; `GET /api/auth/me` returns the
signed-in player, or 401 if there isn't one. Passwords are hashed with
scrypt (Python's stdlib `hashlib.scrypt`, deliberately not the same
SHA-256 used for the link code/API key below -- a human-chosen password
needs a slow, memory-hard hash, a high-entropy random token doesn't).
Login is rate-limited per-IP, and a failed login always takes about the
same time whether or not the email exists, so timing can't be used to
enumerate registered accounts.

There's no email verification or password-reset flow yet -- see "Next
steps."

## Account linking

The RuneLite plugin authenticates with a long-lived API key rather than
a username/password, but getting that key onto the plugin is a two-step
handoff so the code a player copy-pastes is never itself the long-term
credential:

1. **`POST /api/link/start`** -- called by the website for the
   signed-in player (identified by their session cookie -- see "Website
   accounts" above). Generates a random link code, shown to the player
   exactly once, valid for 10 minutes, usable exactly once. Only its
   SHA-256 hash is stored.
2. The player pastes that code into the RuneLite plugin's settings.
3. **`POST /api/link/exchange`** -- called by the plugin with the code
   plus RuneLite's stable `account_hash` (not the display name, which
   can change). Verifies the code, marks it used, binds the game account
   to the player, and returns a separate, long-lived API key. Only its
   hash is stored too. This endpoint is rate-limited (10 requests/minute
   per IP) since it's the one place a caller benefits from guessing.
4. Every future request from the plugin sends that API key as
   `Authorization: Bearer <key>`; `app/auth.py` looks it up by hash.

This is deliberately a bit stronger than the common pattern (see Wise
Old Man's verification codes) of one long-lived, low-entropy code doing
both jobs: the thing a player pastes is short-lived and single-use, and
the thing that authenticates every future request is separately
revocable without forcing a fresh player-facing code.

## Local development

1. Install Python 3.11+, then: `pip install -r requirements.txt`
2. Get a Postgres database to point at (a local install, or a free
   throwaway one from Render/another provider).
3. `cp .env.example .env` and fill in `DATABASE_URL` with that database's
   connection string, and `SESSION_SECRET_KEY` with a random value (the
   file explains how to generate one).
4. `uvicorn app.main:app --reload` and open http://localhost:8000

## Deploying

Push to GitHub, then in the Render dashboard choose "New +" -> "Blueprint"
and point it at this repo -- `render.yaml` tells it to create both the web
service and the database and wire them together. First deploy takes a few
minutes. Once it's up, `/api/health/db` should return
`{"status": "ok", "playerCount": 0}`.

## Next steps (not built yet)

- A real dashboard for a logged-in player -- `/` currently just says
  "you're signed in" once you are
- Purchase Goals / Loot Tracker data model and API endpoints (porting the
  logic from the original single-user Maintrius tool)
- The actual RuneLite plugin (separate repo) that reads bank/inventory/
  equipment/loot data and POSTs it here, using the account-linking flow
  above to get and store its API key
- Email verification and a password-reset flow
- Switch from `Base.metadata.create_all` to real Alembic migrations once
  the schema needs to change without wiping data
- ~~Point myscape.io's DNS at Render once the first deploy is verified~~ done -- live at myscape.io
- ~~A real signup/login flow tying a website account to a `Player` row~~ done
- ~~Actual HTML signup/login pages~~ done -- `/signup` and `/login`

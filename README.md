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
- `migrations/` -- Alembic migrations (see "Database schema changes"
  below for the full workflow).
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
- `app/static/` -- the shared stylesheet, the pixel body font, and the
  logo, in the same dark/gold palette as Maintrius (the original desktop
  tool). The font is served as a real static file (not inlined as
  base64 like Maintrius's local HTML) so browsers cache it across page
  loads. The wordmark lives in the logo image, not text -- there's no
  heading/display font on the site. `app/static/favicon.ico` and
  `app/static/icons/` are the browser-tab icon, linked from every page
  in `app/pages.py`'s shared page shell -- a favicon is just a file the
  app serves and a `<link rel="icon">` tag pointing at it, so it lives
  entirely in this repo and needs nothing set on Render.

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
5. **`POST /api/players/me/unlink`** -- called by the plugin's own
   "Unlink" button (also API-key authenticated). Clears the player's
   `account_hash`/`runescape_name` and revokes every currently-active
   API key on the account, not just the one presenting the request.
   Takes effect immediately in the database. The site-wide footer has
   its own poller for this direction too (see the `footerLinkedNote`
   check in `_shell()`'s shared script, app/pages.py) -- a player
   looking at "Linked to `<name>`" in the footer will see it clear
   within a few seconds of unlinking from the plugin, the mirror image
   of the link banner's own poller for *acquiring* a link
   (`_link_banner()`, same file). Both directions exist because neither
   the website nor the plugin has any way to tell an already-open
   instance of the other about a link change directly -- polling is
   what closes that gap on both sides.

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
4. `uvicorn app.main:app --reload` and open http://localhost:8000 -- the
   app brings a brand-new database up to the latest schema itself on
   startup (see "Database schema changes" below), no separate migration
   command needed.

## Deploying

Push to GitHub, then in the Render dashboard choose "New +" -> "Blueprint"
and point it at this repo -- `render.yaml` tells it to create both the web
service and the database and wire them together. First deploy takes a few
minutes. Once it's up, `/api/health/db` should return
`{"status": "ok", "playerCount": 0}`.

## Dashboard

`GET /dashboard` (session-authenticated, redirects to `/login` if you're
not) is the logged-in home page. It currently shows two "coming soon"
cards (Purchase Goals, Loot Tracker) that are just placeholders until
those data models exist. Signing in, `/`, `/login`, and `/signup` all
redirect here now instead of showing an inline "you're signed in"
message.

Linking itself isn't a dashboard card -- it's a site-wide banner
(`_link_banner()` in `app/pages.py`, rendered by the shared `_shell()`
above every page's content) that shows for any logged-in player who
hasn't linked yet, wherever they are on the site, not just the
dashboard. It reads "You must link your RuneLite plugin settings to
myscape before it can be used." with a "Generate code" button that
calls the same `/api/link/start` endpoint and reveals the code inline;
the banner disappears entirely once `player.account_hash` is set.

Once linked, the "Linked to `<name>`" note (with its own "Unlink"
button) lives in the site-wide footer instead (`_footer()` in
`app/pages.py`, rendered by `_shell()` below every page's content) --
it's chrome about the player's account, not something specific to the
dashboard, so it shows wherever they are on the site. The footer also
always carries the required OSRS trademark attribution, regardless of
login state.

## Next steps (not built yet)

- Purchase Goals / Loot Tracker data model and API endpoints (porting the
  logic from the original single-user Maintrius tool)
- The actual RuneLite plugin (separate repo) that reads bank/inventory/
  equipment/loot data and POSTs it here, using the account-linking flow
  above to get and store its API key
- Email verification and a password-reset flow
- ~~Point myscape.io's DNS at Render once the first deploy is verified~~ done -- live at myscape.io
- ~~A real signup/login flow tying a website account to a `Player` row~~ done
- ~~Actual HTML signup/login pages~~ done -- `/signup` and `/login`
- ~~A real dashboard for a logged-in player~~ done, in its early form -- `/dashboard`
- ~~Switch from `Base.metadata.create_all` + `sync_missing_columns` to
  real Alembic migrations~~ done -- see "Database schema changes" below

## Database schema changes

Schema changes go through [Alembic](https://alembic.sqlalchemy.org/)
migrations now, in `migrations/versions/`. The app runs `alembic upgrade
head` itself at startup (see `on_startup()` in `app/main.py`) -- the same
moment `Base.metadata.create_all()` plus a hand-written
`sync_missing_columns()` used to run, which is what this replaced. That
older approach only ever added new tables and (via a short,
hand-maintained list) patched missing columns onto existing ones; it
couldn't rename or retype a column or change a constraint, and there
was no record anywhere of what had changed or when. That gap is exactly
what broke signup in production once: `players` was created by the very
first deploy, and neither `account_hash` nor `password_hash` (added in
later updates) ever actually reached the live database, since
`create_all()` silently does nothing for a table it considers
already-created.

The workflow for a schema change now: edit the model in `app/models.py`,
then run `alembic revision --autogenerate -m "add whatever"` (with
`DATABASE_URL` pointed at a database that's already up to date) to draft
a migration file from the diff, review what it generated, and commit it
alongside the model change. It takes effect the next time the app starts
-- no separate manual step.

The very first migration
(`migrations/versions/5cf359e6d5b1_initial_schema.py`) is a special
case: production's tables already existed (built up over time by
`create_all`/`sync_missing_columns`, never by Alembic), so that
migration checks whether each table is already there and only creates
the ones that aren't, rather than assuming a blank database like every
migration after it can. That's what let it ship without any one-time
"tell Alembic production is already migrated" step -- it figured that
out on its own, the first time it ran there.

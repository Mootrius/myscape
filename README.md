# myscape

**An Old School RuneScape companion: a RuneLite plugin plus a website that turns your in-game data into trackers, planners, and shareable pages.**

myscape is free and always will be. This repository is the website and backend (FastAPI + PostgreSQL). The RuneLite plugin lives in its own repository: [Mootrius/myscape-plugin](https://github.com/Mootrius/myscape-plugin).

> **Status:** new-account sign-ups are closed until the RuneLite plugin is released. Existing accounts work normally, and shared links (`myscape.io/s/<code>` and `myscape.io/c/<code>`) are viewable by anyone. See [Configuration](#configuration) for how sign-ups are switched on and off.

Live at **[myscape.io](https://myscape.io)**.

## What is myscape?

The RuneLite plugin reads your character's data from the game client (bank, inventory, equipment, skills, quests, achievement diaries, collection log, loot, and more) and sends it to your myscape account. The website then uses that data to power a set of small apps: a loot tracker, a purchase planner, mind maps for your goals, a viewer for everything you own across every storage, goal tracking, and a character overview.

The plugin never plays the game for you. It only reads data and syncs it, with no inputs sent on your behalf. The website needs the plugin to have anything to show, and the plugin needs a website account to send data to.

## Features

Everything below lives under `/dashboard` once you're signed in and linked.

### Character Overview
A one-page summary of your account: combat level, total level, total XP, quest and diary progress, and more, alongside a 3D model of your character, your collection log (browsable by tab and page, with obtained counts), and cards for skills, quests, achievement diaries, and combat achievements. Each linked character can optionally be made public at a short link (`/c/<code>`) so anyone can view it.

### Loot Tracker
Everything you've gotten from kills, clue caskets, pickpocketing, and anything else RuneLite's own Loot Tracker recognizes, with a graph over time and a per-NPC and per-item breakdown (kill counts, GP values, quantities). Sort and search, and hide NPCs or items you don't want to see.

### Purchase Goals
Plan equipment and inventory setups you're saving toward. Each slot is priced live against the OSRS Wiki's real-time prices and checked against what you already own, so you can see what's still left to buy, what the next purchase is, and how close you are, across as many setups as you like.

### Mindmaps
Organize your goals into a mind map: start from one goal and branch out with parent, child, and sibling nodes. Goal nodes (kill counts, items, GP, skills, quests, diaries, or manual) detect their own completion from your synced data.

### Storages Viewer
Everything you own across every storage in the game (bank, inventory, equipment, potion storage, rune pouch, seed vault, looting bag, tackle box, player-owned house storage, and more) in one searchable, sortable, filterable table. Pin items, hide storages, save views, and set minimum or maximum trackers ("keep at least N of this", "flag me once I have more than N").

### Goal Tracking
A list of time-based or one-off targets (boss kill counts, skill levels or XP, item quantities) with progress bars that update on their own from your synced data.

### Sharing and friends
Most apps can share a frozen snapshot of what you're looking at as a read-only link (`/s/<code>`), and a viewer can import a shared mind map, goal, or setup into their own account. Shared links are listed on your Account page, where you can revoke any of them early. Characters can also be friended by their short code, which lets friends view each other's private Character Overview.

### Accounts and characters
One website login can link several OSRS characters and switch between them from the Account page. Email verification, password reset, and changing your email or password are built in, and so is deleting a character or your whole account.

### Help & Support
An FAQ plus links to report bugs and request features.

## Getting started

For players:

1. **Create a website account** at [myscape.io](https://myscape.io) and verify your email. *(Sign-ups are currently closed.)*
2. **Install the plugin.** In RuneLite, open the Plugin Hub, search for "myscape", and install it. Don't download it from anywhere else.
3. **Link your character.** The site shows a "Generate code" button. Click it, paste the code into the plugin's sidebar panel in RuneLite, and the plugin and your account are linked. Codes last 10 minutes and work once.
4. **Play.** Data syncs as you play. Some data (bank, collection log) is read when you open that interface in-game.

## How it works

```
RuneLite plugin ──(API key)──▶  FastAPI app  ◀──(session cookie)── your browser
                                    │
                                    ▼
                               PostgreSQL
```

- **The plugin → the API.** The plugin authenticates with a long-lived, revocable API key and pushes data to `/api/players/me/*` endpoints. Container syncs (bank, inventory, equipment, and so on) are full replaces, not merges, so something you've sold or withdrawn disappears on the next sync.
- **Linking.** The plugin never sees your password. Instead, the website generates a single-use, 10-minute link code; the plugin exchanges it (along with RuneLite's stable account hash) for the API key. Only hashes of the code and the key are stored. Unlinking from either side revokes the keys immediately.
- **The browser → the API.** The website uses a signed session cookie. Pages are server-rendered Python (no template engine, no JS framework), and each app's page then draws itself client-side from JSON it polls from the API.
- **Accounts vs. characters.** A website login (`Account`) owns one or more linked OSRS characters (`GameAccount`). Almost everything (loot, setups, mind maps, storages, goals) belongs to a character.
- **Data sources outside the plugin.** Live item prices come from the [OSRS Wiki real-time prices API](https://prices.runescape.wiki/osrs/faqs). Item icons come from RuneLite's static icon CDN, and NPC portraits from the OSRS Wiki (cached on disk). A character's lifetime boss kill counts are seeded once from the official hiscores when it links, then kept current from in-game chat messages.

## Tech stack

- **Backend:** Python 3.12, [FastAPI](https://fastapi.tiangolo.com/), SQLAlchemy 2, [Alembic](https://alembic.sqlalchemy.org/), [slowapi](https://github.com/laurentS/slowapi) for rate limiting
- **Database:** PostgreSQL 16 (JSONB columns are used, so SQLite won't work)
- **Frontend:** server-rendered HTML from plain Python f-strings in `app/pages.py`, hand-written CSS per app in `app/static/css/`, vanilla JavaScript, and a pixel font served as a static file
- **Email:** [Resend](https://resend.com) for password-reset and verification emails
- **Hosting:** [Render](https://render.com) (one web service, one Postgres database, one persistent disk), configured by `render.yaml`

## Project structure

```
app/
  main.py              FastAPI app: page routes, plugin sync endpoints, per-app APIs, sitemap/robots
  pages.py             Every server-rendered page (markup, inline scripts)
  models.py            SQLAlchemy models
  schemas.py           Request/response models
  auth.py, security.py Auth dependencies (session cookie and plugin API key), hashing, tokens
  routers/             auth (login/signup/reset), linking (link codes, characters), account, friends
  purchase_goals.py    Pricing and ownership logic for Purchase Goals
  loot.py              Loot Tracker state, NPC/event naming and icons
  mindmaps.py          Mind map tree operations and goal progress
  goals.py             Goal Tracking
  possessions.py       Storages Viewer
  sharing.py, public_profile.py   Short-code generation for /s/<code> and /c/<code>
  hiscores.py          One-time kill-count seed from the official hiscores
  icon_cache.py        Disk cache for wiki-sourced icons
  email_client.py      Resend client
  site_flags.py        Feature flags (currently: sign-ups on/off)
  data/                Bundled snapshots (item IDs, quest list, collection log schema, FAQ, landing demos)
  static/              CSS, fonts, images, icons, models, video
migrations/            Alembic migrations
scripts/               One-off scripts that rebuild the bundled data snapshots
docs/                  Design notes
render.yaml            Render deployment blueprint
```

## Local development

### Prerequisites

- Python 3.12
- PostgreSQL (a local install, or a free throwaway database from any provider)

### Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`: set `DATABASE_URL` to your Postgres connection string and `SESSION_SECRET_KEY` to a random value:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

For `http://localhost` testing, you may also want `SESSION_COOKIE_HTTPS_ONLY=false` (never in production). To try the signup flow locally, set `SIGNUPS_ENABLED=true`.

### Run

```bash
uvicorn app.main:app --reload
```

Open <http://localhost:8000>. On startup the app brings the database up to the latest schema by itself (see [Database and migrations](#database-and-migrations)), so there's no separate migration step.

Without `RESEND_API_KEY`, outgoing emails (verification, password reset) are logged to the server console instead of sent, so you can follow the links straight from the logs.

### Tests

There's no automated test suite yet.

## Configuration

Environment variables (see `.env.example`):

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `DATABASE_URL` | yes | | Postgres connection string. |
| `SESSION_SECRET_KEY` | yes | | Signs website session cookies. The app refuses to start without it. On Render it's generated once and kept stable. |
| `SESSION_COOKIE_HTTPS_ONLY` | no | `true` | Marks the session cookie `Secure`. Set to `false` only for local `http://` testing. |
| `SIGNUPS_ENABLED` | no | `false` | When `false`, `/signup` shows a "coming soon" page and `POST /api/auth/signup` returns 403. Set to `true` to open sign-ups. |
| `ICON_CACHE_DIR` | no | a folder next to `app/icon_cache.py` | Where wiki-sourced icons are cached. In production it points at the persistent disk so the cache survives redeploys. |
| `RESEND_API_KEY` | no | | Enables real email delivery. Unset, emails are logged instead of sent. |
| `EMAIL_FROM_ADDRESS` | no | `myscape <noreply@myscape.io>` | The "from" address on outgoing email. Needs a domain verified with Resend. |
| `PYTHON_VERSION` | Render only | `3.12.7` | Pinned in `render.yaml` so Render doesn't pick a Python newer than the dependencies support. |

## Database and migrations

Schema changes go through Alembic migrations in `migrations/versions/`, and the app runs `alembic upgrade head` itself on every startup.

To change the schema:

1. Edit the model in `app/models.py`.
2. With `DATABASE_URL` pointing at a database that's already up to date, run `alembic revision --autogenerate -m "describe the change"`.
3. Review the generated migration, then commit it alongside the model change.

It takes effect the next time the app starts. The first migration checks whether each table already exists before creating it, because production's tables predate Alembic.

## API overview

The endpoints, grouped by purpose (the code has the full details):

- **Health:** `GET /api/health`, `GET /api/health/db`
- **Website auth** (`/api/auth/*`): signup, login, logout, current user, email verification, password reset. Login and linking are rate-limited per IP.
- **Account and characters:** link code generation and exchange, list/activate/remove characters, unlink, change email or password, delete account, shared links, friends and friend requests, and notifications.
- **Plugin sync** (`/api/players/me/*`, API-key authenticated): bank, inventory, equipment, skills, quests, diaries, collection log, loot, kill counts, the character model and summary, and each storage (potion storage, rune pouch, seed vault, looting bag, tackle box, POH, forestry kit, master scroll book, seed box, huntsman's kit, boat cargo).
- **The apps** (session authenticated): `/api/gear-setups`, `/api/mindmaps`, `/api/goals`, `/api/possessions/*`, `/api/players/me/loot`, `/api/character-overview/*`, plus item/NPC/quest search endpoints.
- **Sharing:** creating a share for each app, importing a share into your own account, and the public read-only endpoints behind `/c/<code>`.

## Deployment

The site runs on Render, defined by `render.yaml`: a web service (`uvicorn app.main:app`), a Postgres database, a persistent disk for the icon cache, and a generated session secret. To deploy your own copy, push the repo to GitHub, choose **New +** → **Blueprint** in the Render dashboard, and point it at the repo. Then set the variables marked "sync: false" in `render.yaml` (`RESEND_API_KEY`, optionally `EMAIL_FROM_ADDRESS`), and set `SIGNUPS_ENABLED=true` if you want sign-ups open. Once it's up, `/api/health/db` should return `{"status": "ok", ...}`.

The service is designed to run as a single instance: migrations run at startup, and a few caches (item prices, mappings) live in process memory.

## Security and privacy

- Website passwords are hashed with scrypt. Link codes and plugin API keys are random, high-entropy tokens stored only as SHA-256 hashes. A failed login takes about the same time whether or not the email exists.
- Session cookies are signed, `SameSite=Lax`, and `Secure` by default.
- Link-code exchange, login, and other sensitive endpoints are rate-limited per IP.
- Link codes are single-use and expire after 10 minutes. Unlinking from the plugin or the site revokes every active API key for the character.
- **What's public:** nothing, unless you make it so. A character's Character Overview is private by default and only viewable at `/c/<code>` if you turn it on (and by friends you've accepted). Shared snapshots exist only at the `/s/<code>` links you create, and you can revoke each one from your Account page. Short codes avoid easily confused characters, and codes that don't exist or are private look identical to a visitor.
- **What's stored:** your email, a password hash, and the game data the plugin syncs for each linked character. Deleting a character, or your whole account, from the Account page removes it.

## Roadmap

- Release the RuneLite plugin, then open sign-ups.
- *Add what's next here.*

## Feedback and support

Questions, bug reports, and feature requests are welcome on the [Discord server](https://discord.gg/myscape), on the Help & Support page of the site, or as [GitHub issues](https://github.com/Mootrius/myscape/issues).

## Credits and disclaimers

- Item prices, NPC portraits, and a lot of reference data come from the [Old School RuneScape Wiki](https://oldschool.runescape.wiki). Item icons come from RuneLite's icon cache.
- Built to work with [RuneLite](https://runelite.net).
- myscape is a fan project. It is not affiliated with or endorsed by Jagex. Old School RuneScape is a trademark of Jagex Ltd.

## License

No license has been chosen yet; until one is added, all rights are reserved.

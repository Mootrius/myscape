# myscape

An Old School RuneScape companion: a [RuneLite plugin](https://github.com/Mootrius/myscape-plugin) that syncs your in-game data, and a website ([myscape.io](https://myscape.io)) that turns it into trackers, planners, and shareable pages. Free, always. This repo is the website and backend.

> **Status:** new sign-ups are closed until the plugin is released (see `SIGNUPS_ENABLED` below). Shared links (`/s/<code>`, `/c/<code>`) are viewable by anyone.

## Apps

- **Character Overview:** combat/total level, quests, diaries, combat achievements, collection log, skills, and a 3D model of your character. Optionally public at a short link.
- **Loot Tracker:** drops from kills, caskets, and more, with graphs and per-NPC and per-item breakdowns.
- **Purchase Goals:** equipment and inventory setups priced live against the OSRS Wiki and checked against what you own.
- **Mindmaps:** goal trees whose nodes detect their own completion.
- **Storages Viewer:** everything you own across every storage, searchable, with min/max trackers and saved views.
- **Goal Tracking:** kill count, skill, and item targets with live progress.

Most apps can share a read-only snapshot link, and one login can link several characters.

## Getting started

1. Create an account and verify your email.
2. Install **myscape** from the RuneLite Plugin Hub.
3. Click "Generate code" on the site and paste it into the plugin's sidebar panel.

## Development

Requires Python 3.12 and PostgreSQL.

```bash
pip install -r requirements.txt
cp .env.example .env   # set DATABASE_URL and SESSION_SECRET_KEY
uvicorn app.main:app --reload
```

The schema is migrated automatically on startup. To change it, edit `app/models.py`, run `alembic revision --autogenerate -m "..."`, review the migration, and commit it with the change. Without `RESEND_API_KEY`, emails are logged to the console instead of sent.

### Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | required | Postgres connection string. |
| `SESSION_SECRET_KEY` | required | Signs session cookies. |
| `SIGNUPS_ENABLED` | `false` | `true` opens sign-ups; otherwise `/signup` shows "coming soon". |
| `SESSION_COOKIE_HTTPS_ONLY` | `true` | Set `false` only for local `http://` testing. |
| `ICON_CACHE_DIR` | next to `app/icon_cache.py` | Icon cache location (a persistent disk in production). |
| `RESEND_API_KEY` | unset | Enables sending email. |
| `EMAIL_FROM_ADDRESS` | `myscape <noreply@myscape.io>` | Sender address. |

## Deployment

Deployed on Render via `render.yaml` (web service, Postgres, persistent disk). Create it with **New +** → **Blueprint**, then set `RESEND_API_KEY`. Runs as a single instance.

## Links

[Discord](https://discord.gg/myscape) · [Plugin](https://github.com/Mootrius/myscape-plugin)

myscape is a fan project, not affiliated with or endorsed by Jagex. Old School RuneScape is a trademark of Jagex Ltd.

"""Sends transactional email (right now: just password-reset links) via
Resend's HTTP API (https://resend.com) -- a single POST per email, no
SDK, matching the plain urllib.request style already used elsewhere in
this app (scripts/fetch_item_ids.py, app/icon_cache.py) rather than
adding a new dependency for what's a two-field JSON request.

RESEND_API_KEY isn't set in local dev (see render.yaml, where it's
deliberately `sync: false` -- Render prompts for it at deploy time
rather than ever committing a real key to this repo). Rather than
failing every password-reset request in that environment, send_email
logs the message it would have sent instead -- good enough to test the
reset flow end to end locally (the reset link shows up right in the
server's own console/log output) without needing a real Resend account
just to run this app at all.

EMAIL_FROM_ADDRESS defaults to a myscape.io address -- Resend requires
verifying whichever sending domain is actually used (its dashboard
walks through adding the DNS records), so this only works in
production once that's done; until then (or in local dev), every send
just logs instead, same as the no-API-key case.
"""
import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
EMAIL_FROM_ADDRESS = os.environ.get("EMAIL_FROM_ADDRESS", "myscape <noreply@myscape.io>")
_FETCH_TIMEOUT_SECONDS = 15


def send_email(to: str, subject: str, html: str, text: str) -> None:
    """Best-effort -- a failed send (missing/invalid API key, Resend
    being down, an unverified sending domain) is logged and swallowed
    rather than raised, the same "never let a side-effect send break
    the actual request" reasoning app/icon_cache.py's own fetches
    follow. Concretely for forgot-password (this function's only
    caller right now): the response is always the same generic "if
    that email exists, check your inbox" message regardless of whether
    the send actually worked (see POST /api/auth/forgot-password in
    app/routers/auth.py) -- there's nothing a raised exception here
    could usefully change about that response anyway, and the request
    itself did everything it could (a token really was generated and
    stored)."""
    # TEMPORARY: print(), not log.*, to rule out a Render log-viewer
    # filter hiding our normal logging -- remove once root-caused.
    print(f"[DEBUG email_client] send_email called, to={to!r}, "
          f"RESEND_API_KEY set={bool(RESEND_API_KEY)}, from={EMAIL_FROM_ADDRESS!r}", flush=True)
    if not RESEND_API_KEY:
        log.info("RESEND_API_KEY not set -- would have emailed %s (%r):\n%s", to, subject, text)
        return

    body = json.dumps({
        "from": EMAIL_FROM_ADDRESS,
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
    }).encode("utf-8")
    req = urllib.request.Request(
        RESEND_API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
            print(f"[DEBUG email_client] Resend accepted, HTTP {resp.status}", flush=True)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"[DEBUG email_client] Resend rejected HTTP {exc.code}: {detail}", flush=True)
        log.warning("Resend rejected an email to %s (HTTP %s): %s", to, exc.code, detail)
    except Exception as exc:  # noqa: BLE001 -- best-effort send, see docstring
        print(f"[DEBUG email_client] send failed: {exc!r}", flush=True)
        log.warning("Failed to send email to %s", to, exc_info=True)

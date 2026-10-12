"""Sends transactional email (currently password-reset and verification links)
via Resend's HTTP API (https://resend.com): one POST per email using
urllib.request, no SDK.

RESEND_API_KEY is unset in local dev (render.yaml sets it `sync: false` so no
key is committed). send_email then logs the message instead of sending, so the
reset flow can be tested locally from the log output.

EMAIL_FROM_ADDRESS defaults to a myscape.io address. Resend requires the
sending domain to be verified; until then, sends are logged as in the no-key
case.
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
    """Best-effort: a failed send (bad key, Resend down, unverified domain) is
    logged and swallowed so a side effect never breaks the request. The
    forgot-password response is the same generic message regardless (POST
    /api/auth/forgot-password in app/routers/auth.py).
    """
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
            # An explicit User-Agent is required: urllib's default
            # ("Python-urllib/3.x") is flagged by Cloudflare in front of Resend,
            # which rejects it with a 403 "error code: 1010".
            "User-Agent": "myscape-web/1.0 (+https://myscape.io)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS):
            pass
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        log.warning("Resend rejected an email to %s (HTTP %s): %s", to, exc.code, detail)
    except Exception:  # noqa: BLE001 -- best-effort send, see docstring
        log.warning("Failed to send email to %s", to, exc_info=True)

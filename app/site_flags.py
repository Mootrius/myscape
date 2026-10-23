"""Site-wide on/off switches flipped by hand.

SIGNUPS_ENABLED: whether new accounts can be created. On by default; set the
environment variable to "false" to switch sign-ups off. While off:
- GET /signup shows a "coming soon" page (render_signup_coming_soon in
app/pages/; render_signup is untouched), and
- POST /api/auth/signup returns 403 (hiding the form is not enough; anyone can
POST directly).
Login, password resets and everything else for existing accounts are
unaffected.

To switch off: set the SIGNUPS_ENABLED environment variable to "false" (on
Render: Environment tab, then redeploy) or change the default below.
"""
import os

SIGNUPS_ENABLED = os.environ.get("SIGNUPS_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")

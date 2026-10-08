"""Site-wide on/off switches that are meant to be flipped by hand.

SIGNUPS_ENABLED
    Whether new accounts can be created. Off for now: myscape.io is
    being shared (shareable links and so on) ahead of the RuneLite
    plugin's release, and nobody should be able to register until then.
    While it is off:

    - GET /signup shows a "myscape is coming soon" page instead of the
      sign-up form (render_signup_coming_soon in app/pages.py; the real
      form, render_signup, is untouched and still there), and
    - POST /api/auth/signup refuses with a 403 (the form being hidden
      isn't enough on its own -- anyone can post to the endpoint
      directly).

    Logging in, password resets and everything else for EXISTING
    accounts is unaffected.

    To bring sign-ups back: set the SIGNUPS_ENABLED environment
    variable to "true" (on Render: the service's Environment tab,
    then redeploy/restart), or change the default below to "true".
"""
import os

SIGNUPS_ENABLED = os.environ.get("SIGNUPS_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")

"""Server-rendered HTML pages (landing, signup, login, dashboard).

No template engine -- these are simple enough that plain f-strings beat
adding a Jinja2 dependency for a handful of pages. If the page count
grows past "a handful," that tradeoff is worth revisiting.
"""
from html import escape
from typing import Optional

from app.models import Player


def _nav_sides(player: Optional[Player]) -> tuple[str, str]:
    """The single link/button that goes on each side of the centered
    logo in the header (see _shell). Logged out: Log in on the left,
    Sign up on the right. Logged in: Dashboard on the left,
    Log out on the right -- the email address used to show here too,
    but there's no room for it next to a centered logo without
    crowding the nav, so it's dropped (still shown on the dashboard
    itself)."""
    if player:
        return (
            '<a href="/dashboard">Dashboard</a>',
            '<button class="link" id="logoutBtn" type="button">Log out</button>',
        )
    return (
        '<a href="/login">Log in</a>',
        '<a href="/signup">Sign up</a>',
    )


def _link_banner(player: Optional[Player]) -> str:
    """A site-wide banner telling a logged-in, not-yet-linked player to
    link their RuneLite plugin -- shown above the header on every page
    (see _shell), not just the dashboard, since linking is a
    prerequisite for using myscape at all. Renders to nothing once
    `player.account_hash` is set, or if nobody's logged in.

    It's a normal-flow block ahead of `.page` (not fixed/absolute), so it
    pushes the rest of the page down rather than overlapping it -- see
    the body/.page split in _shell(). The "Generate code" button doubles
    as the code display: clicking it swaps its own label to the code
    instead of opening a separate reveal area. A second click copies
    that code to the clipboard, relabels the button "Copied to
    clipboard", and disables it for good -- see the click handler in
    _shell().

    The banner's `id="linkBanner"` isn't just styling -- _shell()'s
    shared script uses its presence to decide whether to poll for the
    link completing (see that function) and reload once it has, since
    the actual linking click happens over in the RuneLite plugin, which
    has no way to tell this browser tab about it directly."""
    if not player or player.account_hash:
        return ""
    return """
    <div class="link-banner" id="linkBanner">
      <div class="link-banner-inner">
        <span class="link-banner-message">Click to generate a code to enter into your RuneLite settings for the plugin to begin.</span>
        <button class="link-banner-btn" id="generateLinkBtn" type="button">Generate code</button>
      </div>
      <div class="auth-error link-banner-error" id="linkError"></div>
    </div>
    """


def _shell(*, title: str, player: Optional[Player], body: str, extra_script: str = "") -> str:
    nav_left, nav_right = _nav_sides(player)
    shared_script = """
    document.getElementById('logoutBtn')?.addEventListener('click', async () => {
      await fetch('/api/auth/logout', { method: 'POST' });
      window.location.href = '/';
    });

    document.getElementById('generateLinkBtn')?.addEventListener('click', async (e) => {
      const btn = e.target;
      const errorEl = document.getElementById('linkError');
      errorEl.classList.remove('show');

      // Second click: the code is already showing (its value is stashed
      // in the button's own dataset) -- copy it to the clipboard and lock
      // the button rather than generating another one.
      if (btn.dataset.code) {
        try {
          await navigator.clipboard.writeText(btn.dataset.code);
          btn.textContent = 'Copied to clipboard';
          btn.removeAttribute('title');
          btn.disabled = true;
        } catch (err) {
          errorEl.textContent = 'Could not copy the code -- please copy it manually.';
          errorEl.classList.add('show');
        }
        return;
      }

      // First click: generate the code and show it in the button's own label.
      btn.disabled = true;
      try {
        const res = await fetch('/api/link/start', { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          errorEl.textContent = describeError(data, 'Could not generate a code. Please try again.');
          errorEl.classList.add('show');
          return;
        }
        btn.textContent = data.code;
        btn.dataset.code = data.code;
        btn.classList.add('link-banner-btn--code');
        btn.title = 'Click to copy this code to your clipboard.';
      } catch (err) {
        errorEl.textContent = 'Something went wrong. Please try again.';
        errorEl.classList.add('show');
      } finally {
        btn.disabled = false;
      }
    });

    function describeError(data, fallback) {
      if (!data || !data.detail) return fallback;
      if (typeof data.detail === 'string') return data.detail;
      if (Array.isArray(data.detail) && data.detail[0]?.msg) return data.detail[0].msg;
      return fallback;
    }

    // Linking itself happens over on the RuneLite side (the player pastes
    // the code shown by the button above into the plugin's own "Link
    // account" button) -- this open tab has no way to hear about that
    // directly, so while the banner is up it polls the session-authenticated
    // "who am I" endpoint every few seconds and reloads once account_hash
    // comes back set, the same way it would if the player refreshed by
    // hand. Stops polling the moment it succeeds (or the tab is closed).
    const linkBanner = document.getElementById('linkBanner');
    if (linkBanner) {
      const linkPollInterval = setInterval(async () => {
        try {
          const res = await fetch('/api/auth/me');
          if (!res.ok) return; // e.g. session expired -- a normal reload will sort that out
          const data = await res.json();
          if (data.account_hash) {
            clearInterval(linkPollInterval);
            window.location.reload();
          }
        } catch (err) {
          // Transient network hiccup -- just try again next tick.
        }
      }, 3000);
    }
    """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <link rel="icon" href="/static/favicon.ico" sizes="any" />
  <link rel="icon" type="image/png" sizes="32x32" href="/static/icons/favicon-32x32.png" />
  <link rel="icon" type="image/png" sizes="16x16" href="/static/icons/favicon-16x16.png" />
  <link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png" />
  <link rel="stylesheet" href="/static/css/myscape.css" />
</head>
<body>
  <video class="bg-video" autoplay muted loop playsinline preload="auto">
    <source src="/static/video/background.webm" type="video/webm" />
    <source src="/static/video/background.mp4" type="video/mp4" />
  </video>
  <div class="bg-overlay"></div>
  {_link_banner(player)}
  <header>
    <nav class="wrap header-inner">
      <div class="nav-side nav-left">{nav_left}</div>
      <p class="logo"><a href="/">myscape</a></p>
      <div class="nav-side nav-right">{nav_right}</div>
    </nav>
  </header>
  <div class="page">
    <div class="wrap">
      {body}
    </div>
  </div>
  <script>
    {shared_script}
    {extra_script}
  </script>
</body>
</html>"""


def render_landing(player: Optional[Player]) -> str:
    # Logged-in visitors get redirected to /dashboard before this ever
    # renders (see main.py) -- this stays player-aware only so the nav
    # (and link banner) don't look broken if that ever changes.
    # No body copy for now -- just the header/nav over the background
    # video, until there's a real landing pitch to put here.
    body = ""
    return _shell(title="myscape", player=player, body=body)


# Small inline SVGs for the dashboard cards below -- drawn from scratch in
# the game's own item icons (from the OSRS Wiki), not drawings of our own --
# so a returning player recognizes them at a glance.
_ICON_COINS = "/static/img/icon-coins.png"
_ICON_BONES = "/static/img/icon-dragon-bones.png"


def _dash_card(icon_src: str, icon_alt: str, title: str, description: str) -> str:
    """One dashboard feature card -- an icon chip on the left, heading and
    description stacked on the right. Both current cards describe features
    that aren't live yet, but their copy explains what's coming rather than
    just saying "coming soon" now that there's something to say about them."""
    return f"""
    <div class="dash-card">
      <div class="dash-card-icon"><img src="{escape(icon_src)}" alt="{escape(icon_alt)}" /></div>
      <div class="dash-card-body">
        <h3>{escape(title)}</h3>
        <p class="subtitle">{escape(description)}</p>
      </div>
    </div>
    """


def render_dashboard(player: Player) -> str:
    linked_note = ""
    if player.account_hash:
        # A website-side way to unlink, independent of the plugin's own
        # "Unlink" button -- the plugin authenticates that endpoint with
        # its stored API key, so if that key is ever lost or forgotten
        # locally without the server hearing about it, the plugin has
        # no way left to call it. This one only needs the browser
        # session that's already showing this page, so it's always a
        # way out (see linking.revoke_link() in app/routers/linking.py).
        linked_note = f"""
        <p class="dash-linked-note" id="dashLinkedNote">Linked to <strong>{escape(player.runescape_name or "your game account")}</strong>.
          <button class="link" id="dashUnlinkBtn" type="button">Unlink</button>
        </p>
        <div class="auth-error" id="dashUnlinkError"></div>
        """

    purchase_goals_card = _dash_card(
        _ICON_COINS,
        "Coins",
        "Purchase Goals",
        "Track your owned GP against the purchases you'd like to make on the "
        "Grand Exchange, all with live pricing updates for each item. "
        "One-off purchases and entire setups are both supported.",
    )
    loot_tracker_card = _dash_card(
        _ICON_BONES,
        "Dragon bones",
        "Loot Tracker",
        "Track the loot from any NPC you kill, with useful graphs and other "
        "statistics available for your tracking pleasure. Customize which "
        "NPCs are tracked and what data is shown.",
    )

    body = f"""
    {linked_note}
    <div class="dash-grid">
      {purchase_goals_card}
      {loot_tracker_card}
    </div>
    """
    script = """
    document.getElementById('dashUnlinkBtn')?.addEventListener('click', async (e) => {
      const btn = e.target;
      const errorEl = document.getElementById('dashUnlinkError');
      errorEl.classList.remove('show');
      btn.disabled = true;
      try {
        const res = await fetch('/api/link/unlink', { method: 'POST' });
        if (res.ok) {
          window.location.reload();
          return;
        }
        const data = await res.json().catch(() => ({}));
        errorEl.textContent = describeError(data, 'Could not unlink. Please try again.');
        errorEl.classList.add('show');
      } catch (err) {
        errorEl.textContent = 'Something went wrong. Please try again.';
        errorEl.classList.add('show');
      } finally {
        btn.disabled = false;
      }
    });

    // The mirror image of the link banner's own poller (see _shell()):
    // while this page shows "Linked to <name>", nothing here would
    // otherwise notice becoming unlinked elsewhere -- the plugin's own
    // Unlink button chief among them, since (like linking itself) it
    // has no way to tell an already-open browser tab about it directly.
    // The click handler above already reloads immediately on success,
    // so this only ever ends up doing the work for the *other* trigger.
    const dashLinkedNote = document.getElementById('dashLinkedNote');
    if (dashLinkedNote) {
      const unlinkPollInterval = setInterval(async () => {
        try {
          const res = await fetch('/api/auth/me');
          if (!res.ok) return; // e.g. session expired -- a normal reload will sort that out
          const data = await res.json();
          if (!data.account_hash) {
            clearInterval(unlinkPollInterval);
            window.location.reload();
          }
        } catch (err) {
          // Transient network hiccup -- just try again next tick.
        }
      }, 3000);
    }
    """
    return _shell(title="Dashboard — myscape", player=player, body=body, extra_script=script)


def render_signup() -> str:
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>Sign up</h2>
        <div class="auth-error" id="formError"></div>
        <form id="signupForm">
          <div class="field">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" placeholder="you@example.com" required />
          </div>
          <div class="field">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" placeholder="At least 8 characters" required minlength="8" />
          </div>
          <button class="primary" type="submit">Sign up</button>
        </form>
        <div class="auth-switch">Already have an account? <a href="/login">Log in</a></div>
      </div>
    </div>
    """
    script = """
    document.getElementById('signupForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const errorEl = document.getElementById('formError');
      errorEl.classList.remove('show');
      const submitBtn = e.target.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      try {
        const res = await fetch('/api/auth/signup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: document.getElementById('email').value,
            password: document.getElementById('password').value,
          }),
        });
        if (res.ok) {
          window.location.href = '/';
          return;
        }
        const data = await res.json().catch(() => ({}));
        errorEl.textContent = describeError(data, 'Could not create your account.');
        errorEl.classList.add('show');
      } catch (err) {
        errorEl.textContent = 'Something went wrong. Please try again.';
        errorEl.classList.add('show');
      } finally {
        submitBtn.disabled = false;
      }
    });
    """
    return _shell(title="Sign up — myscape", player=None, body=body, extra_script=script)


def render_login() -> str:
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>Log in</h2>
        <div class="auth-error" id="formError"></div>
        <form id="loginForm">
          <div class="field">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" placeholder="you@example.com" required />
          </div>
          <div class="field">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" placeholder="Your password" required />
          </div>
          <button class="primary" type="submit">Log in</button>
        </form>
        <div class="auth-switch">Don't have an account? <a href="/signup">Sign up</a></div>
      </div>
    </div>
    """
    script = """
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const errorEl = document.getElementById('formError');
      errorEl.classList.remove('show');
      const submitBtn = e.target.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: document.getElementById('email').value,
            password: document.getElementById('password').value,
          }),
        });
        if (res.ok) {
          window.location.href = '/';
          return;
        }
        const data = await res.json().catch(() => ({}));
        errorEl.textContent = describeError(data, 'Incorrect email or password.');
        errorEl.classList.add('show');
      } catch (err) {
        errorEl.textContent = 'Something went wrong. Please try again.';
        errorEl.classList.add('show');
      } finally {
        submitBtn.disabled = false;
      }
    });
    """
    return _shell(title="Log in — myscape", player=None, body=body, extra_script=script)

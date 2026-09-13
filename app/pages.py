"""Server-rendered HTML pages (landing, signup, login).

No template engine -- these are simple enough that plain f-strings beat
adding a Jinja2 dependency for three pages. If the page count grows past
"a handful," that tradeoff is worth revisiting.
"""
from html import escape
from typing import Optional

from app.models import Player


def _nav(player: Optional[Player]) -> str:
    if player:
        return f"""
        <nav>
          <a href="/dashboard">Dashboard</a>
          <span>{escape(player.email or "")}</span>
          <button class="link" id="logoutBtn" type="button">Log out</button>
        </nav>
        """
    return """
    <nav>
      <a href="/login">Log in</a>
      <a href="/signup">Sign up</a>
    </nav>
    """


def _shell(*, title: str, player: Optional[Player], body: str, extra_script: str = "") -> str:
    logout_script = """
    document.getElementById('logoutBtn')?.addEventListener('click', async () => {
      await fetch('/api/auth/logout', { method: 'POST' });
      window.location.href = '/';
    });
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
  <div class="wrap">
    <header>
      <p class="logo"><a href="/"><img src="/static/img/logo.png" alt="myscape" /></a></p>
      {_nav(player)}
    </header>
    {body}
  </div>
  <script>
    {logout_script}
    {extra_script}
  </script>
</body>
</html>"""


def render_landing(player: Optional[Player]) -> str:
    # Logged-in visitors get redirected to /dashboard before this ever
    # renders (see main.py) -- this stays player-aware only so the nav
    # doesn't look broken if that ever changes.
    body = """
    <p class="subtitle">An Old School RuneScape companion &mdash; purchase goals, loot tracking, and more.
    <a href="/signup">Sign up</a> to get started.</p>
    """
    return _shell(title="myscape", player=player, body=body)


def render_dashboard(player: Player) -> str:
    if player.account_hash:
        link_card = f"""
        <h3>RuneLite account</h3>
        <p class="subtitle">Linked to <strong>{escape(player.runescape_name or "your game account")}</strong>.</p>
        <p class="hint">Game account ID: {escape(player.account_hash[:16])}&hellip;</p>
        """
    else:
        link_card = """
        <h3>Link your RuneLite account</h3>
        <p class="subtitle">Generate a one-time code to paste into the myscape section of the
        RuneLite plugin's settings. (The plugin itself is still being built -- this gets your
        website account ready for when it lands.)</p>
        <button class="primary" id="generateLinkBtn" type="button">Generate linking code</button>
        <div id="linkCodeResult" style="display:none;">
          <div class="link-code" id="linkCodeValue"></div>
          <p class="hint">Paste this into the plugin's settings. It expires in 10 minutes and
          only works once -- generate a new one if it expires.</p>
        </div>
        <div class="auth-error" id="linkError"></div>
        """

    body = f"""
    <p class="dash-welcome">Welcome back, {escape(player.email or "")}.</p>
    <div class="dash-grid">
      <div class="dash-card" id="linkCard">
        {link_card}
      </div>
      <div class="dash-card dash-card-soon">
        <h3>Purchase Goals</h3>
        <p class="subtitle">Coming soon.</p>
      </div>
      <div class="dash-card dash-card-soon">
        <h3>Loot Tracker</h3>
        <p class="subtitle">Coming soon.</p>
      </div>
    </div>
    """
    script = """
    document.getElementById('generateLinkBtn')?.addEventListener('click', async (e) => {
      const btn = e.target;
      const errorEl = document.getElementById('linkError');
      errorEl.classList.remove('show');
      btn.disabled = true;
      try {
        const res = await fetch('/api/link/start', { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          errorEl.textContent = describeError(data, 'Could not generate a code. Please try again.');
          errorEl.classList.add('show');
          return;
        }
        document.getElementById('linkCodeValue').textContent = data.code;
        document.getElementById('linkCodeResult').style.display = 'block';
        btn.textContent = 'Generate a new code';
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
    """
    return _shell(title="Dashboard — myscape", player=player, body=body, extra_script=script)


def render_signup() -> str:
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>Create your account</h2>
        <p class="auth-subtitle">Free to join &mdash; link a RuneLite plugin once you're in.</p>
        <div class="auth-error" id="formError"></div>
        <form id="signupForm">
          <div class="field">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" placeholder="you@example.com" required />
          </div>
          <div class="field">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" placeholder="At least 8 characters" required minlength="8" />
            <div class="hint">Minimum 8 characters.</div>
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

    function describeError(data, fallback) {
      if (!data || !data.detail) return fallback;
      if (typeof data.detail === 'string') return data.detail;
      if (Array.isArray(data.detail) && data.detail[0]?.msg) return data.detail[0].msg;
      return fallback;
    }
    """
    return _shell(title="Sign up — myscape", player=None, body=body, extra_script=script)


def render_login() -> str:
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>Log in</h2>
        <p class="auth-subtitle">Welcome back.</p>
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

    function describeError(data, fallback) {
      if (!data || !data.detail) return fallback;
      if (typeof data.detail === 'string') return data.detail;
      if (Array.isArray(data.detail) && data.detail[0]?.msg) return data.detail[0].msg;
      return fallback;
    }
    """
    return _shell(title="Log in — myscape", player=None, body=body, extra_script=script)

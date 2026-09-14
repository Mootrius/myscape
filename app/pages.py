"""Server-rendered HTML pages (landing, signup, login, dashboard).

No template engine -- these are simple enough that plain f-strings beat
adding a Jinja2 dependency for a handful of pages. If the page count
grows past "a handful," that tradeoff is worth revisiting.
"""
import os
from html import escape
from typing import Optional

from app.models import Player

# Cache-busting query string for the stylesheet link in _shell() below.
# Without this, a browser that already has myscape.css cached (Starlette's
# StaticFiles doesn't send a Cache-Control header, so browsers are free to
# treat it as fresh for a while on their own heuristics) can keep serving
# a stale copy after a CSS-only deploy, with no visible sign anything is
# wrong -- the page's HTML is never cached, so it looks like the deploy
# "didn't work" when it's really just an old stylesheet. Appending the
# file's own mtime as `?v=` gives every deploy (which always re-checks
# out the repo, refreshing this) a new URL, so there's nothing stale to
# fall back to.
_STATIC_CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "css", "myscape.css")
try:
    _CSS_VERSION = int(os.path.getmtime(_STATIC_CSS_PATH))
except OSError:
    _CSS_VERSION = 0

# Same cache-busting trick as _CSS_VERSION above, for the Purchase Goals
# page's own stylesheet -- kept as a separate file (rather than folded
# into myscape.css) since none of it applies anywhere else on the site.
_PURCHASE_GOALS_CSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "css", "purchase-goals.css"
)
try:
    _PURCHASE_GOALS_CSS_VERSION = int(os.path.getmtime(_PURCHASE_GOALS_CSS_PATH))
except OSError:
    _PURCHASE_GOALS_CSS_VERSION = 0


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


def _footer(player: Optional[Player]) -> str:
    """A site-wide footer, the visual mirror of the header (see the
    `header` rule in myscape.css and its comment) -- same full-width
    darkening gradient technique, but stronger and fading upward
    instead of down, so it unmistakably reads as a floor under the
    page rather than a second, weaker header.

    Holds two things, neither of which is really page content: the
    "Linked to <name>" status (moved down here from the dashboard body
    -- it's chrome about the player's account, not something specific
    to that one page, so every page showing it is more consistent than
    just the one) with its "Unlink" button, and the OSRS trademark
    attribution, which belongs on every page regardless of login
    state. See _shell()'s shared_script for the Unlink button's click
    handler and its own unlink-poller (the mirror of _link_banner()'s
    poller below, for the opposite direction)."""
    linked_line = ""
    if player and player.account_hash:
        linked_line = f"""
        <p class="footer-linked-note" id="footerLinkedNote">Linked to <strong>{escape(player.runescape_name or "your game account")}</strong>.
          <button class="link" id="footerUnlinkBtn" type="button">Unlink</button>
        </p>
        <div class="auth-error footer-unlink-error" id="footerUnlinkError"></div>
        """
    return f"""
    <footer>
      <div class="footer-inner wrap">
        {linked_line}
        <p class="footer-trademark">
          <a href="https://oldschool.runescape.com/" target="_blank" rel="noopener">Old School RuneScape</a>
          is a trademark of
          <a href="https://www.jagex.com/" target="_blank" rel="noopener">Jagex Ltd.</a>
        </p>
      </div>
    </footer>
    """


def _shell(*, title: str, player: Optional[Player], body: str, extra_script: str = "", extra_head: str = "") -> str:
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

    document.getElementById('footerUnlinkBtn')?.addEventListener('click', async (e) => {
      const btn = e.target;
      const errorEl = document.getElementById('footerUnlinkError');
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

    // The mirror image of the link banner's own poller just below: while
    // the footer shows "Linked to <name>", nothing here would otherwise
    // notice becoming unlinked elsewhere -- the plugin's own Unlink
    // button chief among them, since (like linking itself) it has no way
    // to tell an already-open browser tab about it directly. The click
    // handler above already reloads immediately on success, so this only
    // ever ends up doing the work when the *other* side triggered it.
    const footerLinkedNote = document.getElementById('footerLinkedNote');
    if (footerLinkedNote) {
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
  <link rel="stylesheet" href="/static/css/myscape.css?v={_CSS_VERSION}" />
  {extra_head}
</head>
<body>
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
  {_footer(player)}
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
    # Wrapped in a plain link rather than restyling _dash_card for a
    # click handler -- the inline style just strips the anchor's default
    # underline/color so it reads as the same card, not a text link.
    purchase_goals_card = (
        '<a href="/dashboard/purchase-goals" style="display:block;color:inherit;text-decoration:none;">'
        + _dash_card(
            _ICON_COINS,
            "Coins",
            "Purchase Goals",
            "Track your owned GP against the purchases you'd like to make on the "
            "Grand Exchange, all with live pricing updates for each item. "
            "One-off purchases and entire setups are both supported.",
        )
        + "</a>"
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
    <div class="dash-grid">
      {purchase_goals_card}
      {loot_tracker_card}
    </div>
    """
    return _shell(title="Dashboard — myscape", player=player, body=body)


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


def render_purchase_goals(player: Player) -> str:
    """The Purchase Goals page -- named "gear setups" a player plans and
    tracks GP toward, ported feature-for-feature from the original
    single-user Maintrius tool's own Purchase Goals UI (see
    app/purchase_goals.py's module docstring for what changed and what
    didn't on the way over).

    Unlike the other pages here, everything below the header shell is
    rendered client-side from a single polled JSON payload (GET
    /api/gear-setups, see that endpoint in app/main.py) rather than
    server-rendered -- the original tool worked the same way (a local
    HTML file polling its own local server), and keeping that shape
    means every mutation endpoint can just hand back the freshly
    recomputed state and let the same render() function redraw
    everything, rather than juggling two different rendering paths."""
    extra_head = (
        f'<link rel="stylesheet" href="/static/css/purchase-goals.css?v={_PURCHASE_GOALS_CSS_VERSION}" />'
    )
    body = """
    <div class="pg-header">
      <div class="tracker-icon-row" id="setupIconRow"></div>
      <div class="tracker-menu-wrap">
        <button class="icon-menu-btn" id="setupMenuBtn" type="button" title="Setup options">
          <span class="hamburger-icon"><span></span><span></span><span></span></span>
        </button>
        <div class="tracker-menu" id="setupMenu" style="display:none;">
          <button class="tracker-menu-item" id="menuNewSetup" type="button">New setup</button>
          <button class="tracker-menu-item" id="menuRenameSetup" type="button">Rename</button>
          <button class="tracker-menu-item danger" id="menuDeleteSetup" type="button">Delete</button>
        </div>
      </div>
    </div>
    <div class="auth-error" id="pgError"></div>
    <div class="pg-setup-form" id="pgNameForm" style="display:none;">
      <input type="text" id="pgNameInput" placeholder="Setup name" maxlength="60" />
      <button class="primary" id="pgNameSave" type="button">Save</button>
      <button class="link" id="pgNameCancel" type="button">Cancel</button>
    </div>
    <div class="overlay-card" id="pgOverlay" style="display:none;">
      <div class="overlay-side overlay-source">
        <img class="overlay-icon" src="/static/img/icon-coins.png" alt="Coins" />
        <span class="overlay-amount" id="pgCoinsAmount">0</span>
      </div>
      <div class="overlay-progress">
        <div class="progress-track overlay-track"><div class="progress-fill" id="pgOverlayFill" style="width:0%;"></div></div>
      </div>
      <div class="overlay-side overlay-target">
        <div class="overlay-icon-wrap" id="pgIconTrigger" title="Set a display icon for this setup">
          <img class="overlay-icon" id="pgOverlayIconImg" alt="" style="display:none;" />
          <span class="overlay-icon-placeholder" id="pgOverlayIconPlaceholder">+</span>
        </div>
        <span class="overlay-amount" id="pgCostAmount">0</span>
      </div>
    </div>
    <div id="pgIconPicker"></div>
    <div class="pg-body" id="pgBody" style="display:none;">
      <div class="pg-doll-wrap">
        <div class="pg-gear-frame" id="pgGearFrame"></div>
        <div id="pgSlotPicker"></div>
      </div>
      <div class="pg-summary-col">
        <div class="gear-summary">
          <div class="gear-summary-heading">Still to purchase</div>
          <div class="gear-next-purchase" id="pgNextPurchase" style="display:none;">
            <div class="gear-next-purchase-icon-wrap">
              <img class="gear-next-purchase-icon" id="pgNpIcon" src="" alt="" />
            </div>
            <div class="gear-next-purchase-body">
              <div class="gear-next-purchase-label">Next purchase</div>
              <div class="gear-next-purchase-name" id="pgNpName"></div>
              <div class="progress-track"><div class="progress-fill" id="pgNpFill" style="width:0%;"></div></div>
              <div class="gear-next-purchase-amount" id="pgNpAmount"></div>
            </div>
          </div>
          <p class="gear-summary-empty" id="pgSummaryEmpty" style="display:none;">Everything in this setup is already owned.</p>
          <div class="gear-summary-list" id="pgSummaryList"></div>
        </div>
      </div>
    </div>
    <p class="pg-empty" id="pgEmptyMsg">Loading&hellip;</p>
    """
    script = """
    (function () {
      var COINS_ICON = '/static/img/icon-coins.png';

      var PG = {
        data: null,
        activeSetupId: null,
        picker: null,       // { slotType, slot } while a gear/inventory slot is open for editing
        iconPicker: false,  // true while the setup-icon picker is open
        nameFormMode: null, // 'new' | 'rename' | null
        pollTimer: null,
      };

      function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
          return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
      }

      function formatGp(n) {
        n = Math.round(n || 0);
        return n.toLocaleString('en-US');
      }

      // Ticks an element's text from whatever it currently shows to a new
      // target over half a second, instead of popping straight to the new
      // number -- same idea as the original desktop app's tween helper.
      // This only works because pgCoinsAmount/pgCostAmount are now fixed,
      // persistent elements (see the static markup above) that live for
      // the whole page instead of being torn down and rebuilt on every
      // poll -- an element that gets replaced every few seconds has no
      // "currently shows" to tween from, and re-tweening from a stale
      // snapshot on a brand-new node each time is exactly what was
      // causing the coins readout to visibly flicker. Keyed per-element
      // (WeakMap) so a still-running tween is cancelled rather than left
      // to fight a new one for the same node -- two rAF loops racing to
      // write the same textContent every frame is its own flicker bug.
      var numberTweens = new WeakMap();
      function tickNumberText(el, targetValue, format) {
        if (!el) return;
        if (typeof targetValue !== 'number' || !isFinite(targetValue)) {
          var prevBad = numberTweens.get(el);
          if (prevBad && prevBad.raf) cancelAnimationFrame(prevBad.raf);
          el.textContent = format(targetValue);
          numberTweens.delete(el);
          return;
        }

        var prev = numberTweens.get(el);
        var startValue = prev ? prev.currentValue : targetValue;
        if (prev && prev.raf) cancelAnimationFrame(prev.raf);

        // First time this element has ever been set, or already showing
        // the target -- nothing to animate, just show it outright.
        if (!prev || startValue === targetValue) {
          el.textContent = format(targetValue);
          numberTweens.set(el, { raf: null, currentValue: targetValue });
          return;
        }

        var duration = 500;
        var startTime = null;
        function step(ts) {
          if (startTime === null) startTime = ts;
          var t = Math.min(1, (ts - startTime) / duration);
          var eased = 1 - Math.pow(1 - t, 3); // ease-out, matches the bars' feel
          var current = startValue + (targetValue - startValue) * eased;
          el.textContent = format(current);
          if (t < 1) {
            var state = numberTweens.get(el);
            state.currentValue = current;
            state.raf = requestAnimationFrame(step);
          } else {
            el.textContent = format(targetValue);
            numberTweens.set(el, { raf: null, currentValue: targetValue });
          }
        }
        numberTweens.set(el, { raf: requestAnimationFrame(step), currentValue: startValue });
      }

      function showError(msg) {
        var el = document.getElementById('pgError');
        if (!msg) { el.classList.remove('show'); el.textContent = ''; return; }
        el.textContent = msg;
        el.classList.add('show');
      }

      async function apiCall(url, options) {
        try {
          const res = await fetch(url, options);
          const data = await res.json().catch(() => ({}));
          if (!res.ok) {
            showError(describeError(data, 'Something went wrong. Please try again.'));
            return null;
          }
          showError(null);
          return data;
        } catch (err) {
          showError('Something went wrong. Please try again.');
          return null;
        }
      }

      async function loadState(showLoadingState) {
        const data = await apiCall('/api/gear-setups');
        if (!data) return;
        PG.data = data;
        if (!PG.activeSetupId || !data.gearSetups.some(function (s) { return s.id === PG.activeSetupId; })) {
          PG.activeSetupId = data.gearSetups.length ? data.gearSetups[0].id : null;
        }
        render();
      }

      function activeSetup() {
        if (!PG.data || !PG.activeSetupId) return null;
        return PG.data.gearSetups.find(function (s) { return s.id === PG.activeSetupId; }) || null;
      }

      // ---- Top-level render ---------------------------------------------

      function render() {
        renderIconRow();
        renderContent();
      }

      function renderIconRow() {
        var row = document.getElementById('setupIconRow');
        if (!PG.data) { row.innerHTML = ''; return; }
        row.innerHTML = PG.data.gearSetups.map(function (s) {
          var active = s.id === PG.activeSetupId ? ' active' : '';
          if (s.icon && s.icon.icon) {
            return '<button class="tracker-icon-btn' + active + '" data-setup-id="' + esc(s.id) + '" type="button" title="' + esc(s.name) + '">' +
              '<img src="' + esc(s.icon.icon) + '" alt="" /></button>';
          }
          var label = esc((s.icon && s.icon.itemName) || s.name || '?').slice(0, 3);
          return '<button class="tracker-icon-btn' + active + '" data-setup-id="' + esc(s.id) + '" type="button" title="' + esc(s.name) + '">' +
            '<span class="tracker-icon-fallback">' + label + '</span></button>';
        }).join('');
        row.querySelectorAll('[data-setup-id]').forEach(function (btn) {
          btn.addEventListener('click', function () {
            PG.activeSetupId = btn.getAttribute('data-setup-id');
            PG.picker = null;
            PG.iconPicker = false;
            render();
          });
        });
      }

      function renderContent() {
        var overlayEl = document.getElementById('pgOverlay');
        var bodyEl = document.getElementById('pgBody');
        var emptyEl = document.getElementById('pgEmptyMsg');

        if (!PG.data) {
          overlayEl.style.display = 'none';
          bodyEl.style.display = 'none';
          emptyEl.style.display = '';
          emptyEl.textContent = 'Loading…';
          return;
        }
        var setup = activeSetup();
        if (!setup) {
          overlayEl.style.display = 'none';
          bodyEl.style.display = 'none';
          emptyEl.style.display = '';
          emptyEl.textContent = 'No gear setups yet -- use the menu above to create your first one.';
          return;
        }

        overlayEl.style.display = '';
        bodyEl.style.display = '';
        emptyEl.style.display = 'none';

        updateOverlay(setup);

        var doll = '<div class="gear-doll">' + EQUIPMENT_SLOTS.map(function (slotName) {
          return slotHtml(setup.equipment[slotName], 'equipment', slotName, 'slot-' + slotName);
        }).join('') + '</div>';

        var grid = '<div class="inventory-grid">' + setup.inventory.map(function (item, idx) {
          return slotHtml(item, 'inventory', idx, '');
        }).join('') + '</div>';

        document.getElementById('pgGearFrame').innerHTML = doll + grid;
        renderSummaryList(setup);

        // Pin the column's width to the gear-frame's own rendered width
        // (see the comment on .pg-doll-wrap in purchase-goals.css) --
        // without this, the slot picker rendered into it below would
        // stretch the column (and the whole row) wider than the frame,
        // shoving the summary column out of place instead of just
        // wrapping its own contents inside the frame's width.
        var dollWrapEl = document.querySelector('.pg-doll-wrap');
        var gearFrameEl = document.getElementById('pgGearFrame');
        if (dollWrapEl && gearFrameEl) {
          dollWrapEl.style.width = gearFrameEl.offsetWidth + 'px';
        }

        wireSlotClicks();
        renderIconPicker();
        renderSlotPicker();
      }

      // Updates the overlay's GP numbers/bar and the next-purchase mini
      // bar in place, on the same fixed elements every time (see the
      // static markup in render_purchase_goals), instead of rebuilding
      // them -- that's what lets tickNumberText tween the numbers and the
      // bars' own CSS transition (see .progress-fill) animate their width
      // smoothly rather than popping or flickering on every poll.
      function updateOverlay(setup) {
        var pct = Math.max(0, Math.min(100, setup.progressPct));
        tickNumberText(document.getElementById('pgCoinsAmount'), PG.data.coins, formatGp);
        tickNumberText(document.getElementById('pgCostAmount'), setup.totalCost, formatGp);

        var fillEl = document.getElementById('pgOverlayFill');
        fillEl.style.width = pct + '%';
        fillEl.classList.toggle('funded-fill', !!setup.funded);

        var iconImgEl = document.getElementById('pgOverlayIconImg');
        var iconPlaceholderEl = document.getElementById('pgOverlayIconPlaceholder');
        if (setup.icon && setup.icon.icon) {
          iconImgEl.src = setup.icon.icon;
          iconImgEl.style.display = '';
          iconPlaceholderEl.style.display = 'none';
        } else {
          iconImgEl.style.display = 'none';
          iconPlaceholderEl.style.display = '';
        }

        var npEl = document.getElementById('pgNextPurchase');
        if (setup.nextPurchase) {
          var np = setup.nextPurchase;
          var npPct = Math.max(0, Math.min(100, np.progressPct));
          npEl.style.display = '';
          var npIconEl = document.getElementById('pgNpIcon');
          npIconEl.src = np.icon || '';
          npIconEl.style.visibility = np.icon ? '' : 'hidden';
          document.getElementById('pgNpName').textContent = np.itemName;
          var npFillEl = document.getElementById('pgNpFill');
          npFillEl.style.width = npPct + '%';
          npFillEl.classList.toggle('funded-fill', !!np.funded);
          document.getElementById('pgNpAmount').textContent = formatGp(PG.data.coins) + ' / ' + formatGp(np.cost) + ' gp';
        } else {
          npEl.style.display = 'none';
        }
      }

      var EQUIPMENT_SLOTS = ['head', 'cape', 'neck', 'ammo', 'weapon', 'body', 'shield', 'legs', 'hands', 'boots', 'ring'];

      function slotClasses(resolved) {
        var cls = 'gear-slot';
        if (!resolved) return cls;
        cls += ' filled';
        if (resolved.owned) cls += ' owned';
        else if (resolved.affordable) cls += ' affordable';
        else cls += ' not-owned';
        return cls;
      }

      function slotBadge(resolved) {
        if (!resolved) return '';
        if (resolved.supplies) return '<span class="gear-slot-supplies-badge" title="Supplies -- always counted as owned">S</span>';
        if (resolved.components) return '<span class="gear-slot-combo-badge" title="Combined item">C</span>';
        if (!resolved.tradeable) return '<span class="gear-slot-untradeable-badge" title="Untradeable -- matched by name">?</span>';
        return '';
      }

      function itemWikiUrl(itemName) {
        return 'https://oldschool.runescape.wiki/w/' + encodeURIComponent(String(itemName).replace(/ /g, '_'));
      }

      function slotHtml(resolved, slotType, slot, extraClass) {
        var picking = PG.picker && PG.picker.slotType === slotType && String(PG.picker.slot) === String(slot);
        var cls = slotClasses(resolved) + (extraClass ? ' ' + extraClass : '') + (picking ? ' picking' : '');
        var inner = resolved && resolved.icon
          ? '<img class="gear-slot-icon" src="' + esc(resolved.icon) + '" alt="" />'
          : (resolved ? '<span class="tracker-icon-fallback">' + esc(resolved.itemName || '?').slice(0, 6) + '</span>' : '');
        var title = resolved
          ? esc(resolved.itemName) + (resolved.cost ? ' -- ' + formatGp(resolved.cost) + ' gp' : '') + ' -- click to view on the wiki'
          : 'Empty slot';
        var itemNameAttr = resolved ? ' data-item-name="' + esc(resolved.itemName) + '"' : '';
        // The remove ("x") button only ever shows up on hover (see
        // .gear-slot-remove in purchase-goals.css) and only exists at all
        // when the slot is filled -- an empty slot has nothing to remove.
        var removeBtn = resolved ? '<button class="gear-slot-remove" type="button" title="Remove item">&times;</button>' : '';
        return '<div class="' + cls + '" data-slot-type="' + slotType + '" data-slot="' + esc(slot) + '"' + itemNameAttr + ' title="' + title + '">' +
          inner + slotBadge(resolved) + removeBtn + '</div>';
      }

      function wireSlotClicks() {
        document.querySelectorAll('.gear-slot').forEach(function (el) {
          var removeBtn = el.querySelector('.gear-slot-remove');
          if (removeBtn) {
            removeBtn.addEventListener('click', function (e) {
              // Don't let this bubble up to the slot's own click handler
              // below (which would otherwise also open the item's wiki
              // page at the same time as removing it).
              e.stopPropagation();
              var slotType = el.getAttribute('data-slot-type');
              var slot = slotType === 'inventory' ? parseInt(el.getAttribute('data-slot'), 10) : el.getAttribute('data-slot');
              removeSlotItem(slotType, slot);
            });
          }
          el.addEventListener('click', function () {
            var slotType = el.getAttribute('data-slot-type');
            var slot = slotType === 'inventory' ? parseInt(el.getAttribute('data-slot'), 10) : el.getAttribute('data-slot');
            var itemName = el.getAttribute('data-item-name');
            // A filled slot's item is now a link out to the wiki instead
            // of an editor -- removing is handled by the hover "x"
            // (above) and adding only ever happens on an empty slot, so
            // there's nothing left for a filled slot's own click to open.
            if (itemName) {
              window.open(itemWikiUrl(itemName), '_blank', 'noopener');
              return;
            }
            if (PG.picker && PG.picker.slotType === slotType && String(PG.picker.slot) === String(slot)) {
              PG.picker = null;
            } else {
              openSlotPicker(slotType, slot);
            }
            PG.iconPicker = false;
            renderContent();
          });
        });
      }

      // Only the "still to purchase" list + empty message -- the
      // next-purchase mini bar/amount above it is a fixed element updated
      // in place by updateOverlay() instead, so it isn't rebuilt (and
      // therefore doesn't need to animate) every time this list changes.
      function renderSummaryList(setup) {
        var emptyEl = document.getElementById('pgSummaryEmpty');
        var listEl = document.getElementById('pgSummaryList');
        if (!setup.stillToPurchase.length) {
          emptyEl.style.display = '';
          listEl.style.display = 'none';
          listEl.innerHTML = '';
          return;
        }
        emptyEl.style.display = 'none';
        listEl.style.display = '';
        listEl.innerHTML = setup.stillToPurchase.map(function (item) {
          var rowCls = 'gear-summary-row' + (item.purchasable ? '' : ' unpurchasable');
          var costHtml = item.purchasable
            ? '<span class="gear-summary-row-cost">' + formatGp(item.cost) + '</span>'
            : '<span class="gear-summary-row-cost na">n/a</span>';
          return '<div class="' + rowCls + '">' +
            (item.icon ? '<img class="gear-summary-row-icon" src="' + esc(item.icon) + '" alt="" />' : '<span class="gear-summary-row-icon"></span>') +
            '<span class="gear-summary-row-name">' + esc(item.itemName) + (item.isCombo ? ' (combo)' : '') + '</span>' +
            costHtml +
            '</div>';
        }).join('');
      }

      // ---- Setup icon picker ----------------------------------------------

      function renderIconPicker() {
        var el = document.getElementById('pgIconPicker');
        if (!el) return;
        if (!PG.iconPicker) { el.innerHTML = ''; return; }
        el.innerHTML = '' +
          '<div class="gear-icon-picker">' +
          '  <div class="search-box">' +
          '    <input type="text" id="iconSearchInput" placeholder="Search for an item to use as this setup\\'s icon" autocomplete="off" />' +
          '    <div class="suggestions" id="iconSuggestions"></div>' +
          '  </div>' +
          '  <button class="link" id="iconClearBtn" type="button">Clear icon</button>' +
          '  <button class="link" id="iconCancelBtn" type="button">Cancel</button>' +
          '</div>';
        var input = document.getElementById('iconSearchInput');
        input.addEventListener('input', debounce(function () { runSearch(input.value, renderIconSuggestions); }, 200));
        document.getElementById('iconClearBtn').addEventListener('click', async function () {
          const data = await apiCall('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/icon', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ icon: null }),
          });
          if (data) { PG.data = data; PG.iconPicker = false; render(); }
        });
        document.getElementById('iconCancelBtn').addEventListener('click', function () { PG.iconPicker = false; renderIconPicker(); });
      }

      function renderIconSuggestions(results) {
        var box = document.getElementById('iconSuggestions');
        if (!box) return;
        if (!results.length) { box.classList.remove('show'); box.innerHTML = ''; return; }
        box.innerHTML = results.map(function (r) {
          return '<div class="suggestion" data-item-id="' + r.id + '" data-item-name="' + esc(r.name) + '">' +
            (r.icon ? '<img src="' + esc(r.icon) + '" alt="" />' : '') + '<span>' + esc(r.name) + '</span></div>';
        }).join('');
        box.classList.add('show');
        box.querySelectorAll('.suggestion').forEach(function (row) {
          row.addEventListener('click', async function () {
            const icon = { item_id: parseInt(row.getAttribute('data-item-id'), 10), item_name: row.getAttribute('data-item-name') };
            const data = await apiCall('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/icon', {
              method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ icon: icon }),
            });
            if (data) { PG.data = data; PG.iconPicker = false; render(); }
          });
        });
      }

      // ---- Gear/inventory slot picker --------------------------------------

      function openSlotPicker(slotType, slot) {
        PG.picker = { slotType: slotType, slot: slot, query: '', selected: null };
      }

      function renderSlotPicker() {
        var el = document.getElementById('pgSlotPicker');
        if (!el) return;
        var p = PG.picker;
        if (!p) { el.innerHTML = ''; return; }

        // No "build from parts" option any more -- if what's searched
        // isn't a live GE-tradeable match, picking the "add as
        // untradeable" fallback below still works exactly the same, and
        // the server checks the name against known item-combination
        // recipes (e.g. "Neitiznot faceguard" -> Helm of Neitiznot +
        // Basilisk jaw) and auto-expands it there -- see
        // expand_recipe_components in app/recipes.py -- so nobody has
        // to know or type out what an item is made of.
        var body = '' +
          '<div class="search-box search-box-full">' +
          '  <input type="text" id="slotSearchInput" placeholder="Search for an item" autocomplete="off" value="' + esc(p.query) + '" />' +
          '  <div class="suggestions" id="slotSuggestions"></div>' +
          '</div>' +
          '<div class="gear-slot-picker-actions">' +
          '  <button class="gspa-secondary" id="slotAddSuppliesBtn" type="button">Add as supplies</button>' +
          '  <button class="gspa-primary" id="slotAddBtn" type="button">Add</button>' +
          '</div>';

        el.innerHTML = '<div class="gear-slot-picker">' + body + '</div>';

        wireSlotPickerEvents();
      }

      function wireSlotPickerEvents() {
        var p = PG.picker;
        var input = document.getElementById('slotSearchInput');
        input.addEventListener('input', debounce(function () {
          p.query = input.value;
          // Whatever was selected before no longer matches what's
          // typed now -- Add/Add as supplies need a fresh pick.
          p.selected = null;
          runSearch(input.value, function (results) { renderSlotSuggestions(input.value, results); });
        }, 200));
        document.getElementById('slotAddBtn').addEventListener('click', function () {
          if (!p.selected) { showError('Pick an item from the list first.'); return; }
          saveSlot({ item_id: p.selected.itemId, item_name: p.selected.itemName });
        });
        document.getElementById('slotAddSuppliesBtn').addEventListener('click', function () {
          if (!p.selected) { showError('Pick an item from the list first.'); return; }
          saveSlot({ item_id: p.selected.itemId, item_name: p.selected.itemName, supplies: true });
        });
      }

      function renderSlotSuggestions(query, results) {
        var box = document.getElementById('slotSuggestions');
        if (!box) return;
        var trimmed = (query || '').trim();
        if (!trimmed) { box.classList.remove('show'); box.innerHTML = ''; return; }

        var rowsHtml = results.map(function (r) {
          // Combination items (e.g. "Neitiznot faceguard") have no
          // Grand Exchange listing of their own -- no data-item-id, and
          // a small "combo" tag so it's clear this isn't a live-priced
          // match, but it's still a normal, icon-bearing, click-to-
          // select suggestion. The server auto-detects and prices these
          // from their real components once selected -- see
          // app/recipes.py -- so nobody has to already know or type out
          // what an item is made of just to find it.
          var idAttr = r.id != null ? ' data-item-id="' + r.id + '"' : '';
          var comboTag = r.id == null ? '<span class="suggestion-combo-tag">combo</span>' : '';
          return '<div class="suggestion" data-item-name="' + esc(r.name) + '"' + idAttr + '>' +
            (r.icon ? '<img src="' + esc(r.icon) + '" alt="" />' : '') + '<span>' + esc(r.name) + '</span>' + comboTag + '</div>';
        }).join('');

        // No match at all, tradeable or otherwise -- offer to add
        // exactly what was typed as an untradeable item instead,
        // matched by name rather than id (see _take_owned in
        // app/purchase_goals.py). This is now the rare fallback rather
        // than the main path for combination gear, since those show up
        // as normal suggestions above.
        if (!results.length) {
          rowsHtml = '<div class="suggestion suggestion-add-untradeable" data-untradeable-name="' + esc(trimmed) + '">' +
            '<span class="suggestion-add-icon">+</span><span>Add &ldquo;' + esc(trimmed) + '&rdquo; as an untradeable item</span></div>';
        }

        box.innerHTML = rowsHtml;
        box.classList.add('show');

        var input = document.getElementById('slotSearchInput');
        box.querySelectorAll('.suggestion[data-item-name]').forEach(function (row) {
          row.addEventListener('click', function () {
            var idAttr = row.getAttribute('data-item-id');
            PG.picker.selected = {
              itemId: idAttr !== null ? parseInt(idAttr, 10) : null,
              itemName: row.getAttribute('data-item-name'),
            };
            PG.picker.query = PG.picker.selected.itemName;
            if (input) input.value = PG.picker.selected.itemName;
            box.classList.remove('show');
            box.innerHTML = '';
          });
        });
        box.querySelectorAll('.suggestion-add-untradeable').forEach(function (row) {
          row.addEventListener('click', function () {
            var name = row.getAttribute('data-untradeable-name');
            PG.picker.selected = { itemId: null, itemName: name };
            PG.picker.query = name;
            if (input) input.value = name;
            box.classList.remove('show');
            box.innerHTML = '';
          });
        });
      }

      async function saveSlot(item) {
        var p = PG.picker;
        const data = await apiCall('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/slot', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ slot_type: p.slotType, slot: p.slot, item: item }),
        });
        if (data) { PG.data = data; PG.picker = null; render(); }
      }

      // Removes whatever's in a slot directly from its hover "x" -- unlike
      // saveSlot above, this doesn't go through PG.picker (a filled slot
      // no longer opens one at all; see wireSlotClicks), so the slot to
      // clear is passed in explicitly instead.
      async function removeSlotItem(slotType, slot) {
        const data = await apiCall('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/slot', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ slot_type: slotType, slot: slot, item: null }),
        });
        if (data) { PG.data = data; render(); }
      }

      async function runSearch(query, callback) {
        query = (query || '').trim();
        if (!query) { callback([]); return; }
        const data = await apiCall('/api/items/search?q=' + encodeURIComponent(query));
        callback(data ? data.results : []);
      }

      function debounce(fn, wait) {
        var t = null;
        return function () {
          var args = arguments;
          clearTimeout(t);
          t = setTimeout(function () { fn.apply(null, args); }, wait);
        };
      }

      // pgIconTrigger is now a fixed element (see the static overlay
      // markup in render_purchase_goals) instead of being rebuilt on
      // every render, so it only needs wiring up once here rather than
      // on every renderContent() call.
      document.getElementById('pgIconTrigger').addEventListener('click', function () {
        PG.iconPicker = !PG.iconPicker;
        PG.picker = null;
        renderIconPicker();
        document.getElementById('pgSlotPicker').innerHTML = '';
      });

      // ---- Setup CRUD (menu + name form) -----------------------------------

      document.getElementById('setupMenuBtn').addEventListener('click', function () {
        var menu = document.getElementById('setupMenu');
        menu.style.display = menu.style.display === 'none' ? 'flex' : 'none';
      });
      document.addEventListener('click', function (e) {
        var wrap = document.querySelector('.tracker-menu-wrap');
        if (wrap && !wrap.contains(e.target)) document.getElementById('setupMenu').style.display = 'none';
      });

      document.getElementById('menuNewSetup').addEventListener('click', function () {
        document.getElementById('setupMenu').style.display = 'none';
        openNameForm('new', '');
      });
      document.getElementById('menuRenameSetup').addEventListener('click', function () {
        document.getElementById('setupMenu').style.display = 'none';
        var setup = activeSetup();
        if (!setup) { showError('Create a setup first.'); return; }
        openNameForm('rename', setup.name);
      });
      document.getElementById('menuDeleteSetup').addEventListener('click', async function () {
        document.getElementById('setupMenu').style.display = 'none';
        var setup = activeSetup();
        if (!setup) return;
        if (!window.confirm('Delete "' + setup.name + '"? This cannot be undone.')) return;
        const data = await apiCall('/api/gear-setups/' + encodeURIComponent(setup.id), { method: 'DELETE' });
        if (data) { PG.data = data; PG.activeSetupId = data.gearSetups.length ? data.gearSetups[0].id : null; render(); }
      });

      function openNameForm(mode, initialValue) {
        PG.nameFormMode = mode;
        var form = document.getElementById('pgNameForm');
        var input = document.getElementById('pgNameInput');
        form.style.display = 'flex';
        input.value = initialValue || '';
        input.focus();
      }

      document.getElementById('pgNameCancel').addEventListener('click', function () {
        document.getElementById('pgNameForm').style.display = 'none';
        PG.nameFormMode = null;
      });
      document.getElementById('pgNameSave').addEventListener('click', async function () {
        var name = (document.getElementById('pgNameInput').value || '').trim();
        if (!name) { showError('A setup name is required.'); return; }
        var mode = PG.nameFormMode;
        document.getElementById('pgNameForm').style.display = 'none';
        PG.nameFormMode = null;
        var data;
        if (mode === 'new') {
          data = await apiCall('/api/gear-setups', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name }),
          });
          if (data) {
            PG.data = data;
            var created = data.gearSetups.find(function (s) { return s.name === name; }) || data.gearSetups[data.gearSetups.length - 1];
            PG.activeSetupId = created ? created.id : PG.activeSetupId;
            render();
          }
        } else if (mode === 'rename') {
          var setup = activeSetup();
          if (!setup) return;
          data = await apiCall('/api/gear-setups/' + encodeURIComponent(setup.id), {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name }),
          });
          if (data) { PG.data = data; render(); }
        }
      });

      // ---- Boot + poll ------------------------------------------------------

      loadState();
      PG.pollTimer = setInterval(function () {
        // Skip a background refresh while the player has an editor open --
        // an in-flight rename/slot-pick shouldn't get yanked out from
        // under them by a poll landing mid-edit.
        if (PG.picker || PG.iconPicker || PG.nameFormMode) return;
        loadState();
      }, 5000);
    })();
    """
    return _shell(
        title="Purchase Goals — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )

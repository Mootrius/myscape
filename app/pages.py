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

# Same cache-busting trick again, for the Loot Tracker page's own
# stylesheet.
_LOOT_TRACKER_CSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "css", "loot-tracker.css"
)
try:
    _LOOT_TRACKER_CSS_VERSION = int(os.path.getmtime(_LOOT_TRACKER_CSS_PATH))
except OSError:
    _LOOT_TRACKER_CSS_VERSION = 0


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
    // See myscape.css's own `user-select: none` for the text-selection
    // half of "nothing on the page is grabbable" -- this is the other
    // half, for images specifically: -webkit-user-drag there stops
    // WebKit's native image-drag ghost, but Firefox has no CSS knob for
    // it at all, only preventDefault() on the drag's own dragstart
    // event. Delegated on document (rather than one listener per <img>)
    // so it also covers every icon injected later by a page's own
    // script (gear-slot icons, NPC/item boxes, search results, etc.),
    // not just whatever <img> tags happened to be in the initial HTML.
    document.addEventListener('dragstart', (e) => {
      if (e.target.tagName === 'IMG') e.preventDefault();
    });

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
    loot_tracker_card = (
        '<a href="/dashboard/loot" style="display:block;color:inherit;text-decoration:none;">'
        + _dash_card(
            _ICON_BONES,
            "Dragon bones",
            "Loot Tracker",
            "Track the loot from any NPC you kill, with useful graphs and other "
            "statistics available for your tracking pleasure. Customize which "
            "NPCs are tracked and what data is shown.",
        )
        + "</a>"
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
    <h2 class="page-title">Purchase Goals</h2>
    <div class="pg-header">
      <div class="tracker-icon-row" id="setupIconRow"></div>
      <div class="tracker-menu-wrap">
        <button class="icon-menu-btn" id="setupMenuBtn" type="button" title="Setup options">
          <span class="hamburger-icon"><span></span><span></span><span></span></span>
        </button>
        <div class="tracker-menu" id="setupMenu" style="display:none;">
          <button class="tracker-menu-item" id="menuNewSetup" type="button">New setup</button>
          <button class="tracker-menu-item" id="menuRenameSetup" type="button">Rename setup</button>
          <button class="tracker-menu-item danger" id="menuDeleteSetup" type="button">Delete setup</button>
        </div>
      </div>
    </div>
    <div class="auth-error" id="pgError"></div>
    <div class="pg-setup-form" id="pgNameForm" style="display:none;">
      <input type="text" id="pgNameInput" placeholder="Setup name" maxlength="60" />
      <button class="primary pg-setup-form-save" id="pgNameSave" type="button">Save</button>
      <button class="btn-secondary" id="pgNameCancel" type="button">Cancel</button>
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
          <div class="gear-summary-sort" id="pgSortButtons"></div>
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
          <p class="gear-summary-empty" id="pgSummaryEmpty" style="display:none;"></p>
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
        dragSuppressClick: false, // true for one click right after a completed drag-and-drop (see wireSlotClicks)
        // Bumped every time a direct, explicit action (a click, a drag-drop,
        // a form submit -- anything that isn't the background poll) applies
        // a fresh server response to PG.data. loadState() -- the poll's
        // only entry point -- snapshots this before its own fetch and
        // compares after: if it changed while the fetch was in flight, a
        // newer, more authoritative response already landed and the poll's
        // now-stale one is dropped instead of clobbering it. See loadState
        // below and the "Boot + poll" section at the end of this script.
        stateVersion: 0,
      };

      // Remembers which gear setup was last active across a page refresh
      // -- without this, every reload silently fell back to whichever
      // setup happens to be first, discarding whatever the player was
      // actually looking at. Plain localStorage rather than anything
      // server-side since this is purely which setup a given browser
      // last had open, not data that needs to sync across devices or
      // follow the player's account -- and it's deliberately NOT scoped
      // per player: if a different player ever logs in on the same
      // browser, the stored id simply won't match any of their setups
      // and loadState's own fallback below lands on their first setup
      // instead, exactly as it always did. Wrapped in try/catch since
      // localStorage can throw (private browsing in some browsers,
      // storage disabled/full) -- losing this one convenience is fine,
      // it should never break the page.
      var ACTIVE_SETUP_STORAGE_KEY = 'myscape:purchaseGoals:activeSetupId';
      function loadStoredActiveSetupId() {
        try { return localStorage.getItem(ACTIVE_SETUP_STORAGE_KEY); } catch (e) { return null; }
      }
      function setActiveSetupId(id) {
        PG.activeSetupId = id;
        try {
          if (id) localStorage.setItem(ACTIVE_SETUP_STORAGE_KEY, id);
          else localStorage.removeItem(ACTIVE_SETUP_STORAGE_KEY);
        } catch (e) { /* ignore -- see comment above */ }
      }

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
        // Snapshot the version before the request goes out. This is the
        // background poll's only entry point (plus the one-time boot
        // call) -- if some other, more direct action (a sort-button
        // click, a drag-drop, a rename...) applies its own fresher
        // response while this fetch is still in flight, PG.stateVersion
        // will have moved on by the time we get here, and this now-stale
        // response is dropped rather than overwriting the newer state.
        var versionAtStart = PG.stateVersion;
        const data = await apiCall('/api/gear-setups');
        if (!data) return;
        if (PG.stateVersion !== versionAtStart) return;
        PG.stateVersion++;
        PG.data = data;
        if (!PG.activeSetupId || !data.gearSetups.some(function (s) { return s.id === PG.activeSetupId; })) {
          // On first load (or if whatever was active just vanished --
          // deleted from another tab, say), prefer the last setup this
          // browser had open (see setActiveSetupId above) over just
          // defaulting to the first one, falling back to the first only
          // when there's no usable stored id (never set, or it no
          // longer matches any of this player's setups).
          var stored = loadStoredActiveSetupId();
          var resolved = (stored && data.gearSetups.some(function (s) { return s.id === stored; }))
            ? stored
            : (data.gearSetups.length ? data.gearSetups[0].id : null);
          setActiveSetupId(resolved);
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
            setActiveSetupId(btn.getAttribute('data-setup-id'));
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

        // The 11 real paperdoll slots and the 8 misc slots (runes,
        // teleports, whatever else a setup needs beyond its actual gear
        // -- see MISC_EQUIPMENT_SLOTS in app/schemas.py), the latter
        // rendered two rows of 4, render as two separate grids stacked
        // in one flex column (see .gear-doll in purchase-goals.css)
        // rather than one combined grid, so the misc block can be
        // sized/positioned independently of the paperdoll shape above
        // it.
        var doll = '<div class="gear-doll">' +
          '<div class="gear-doll-slots">' + MAIN_EQUIPMENT_SLOTS.map(function (slotName) {
            return slotHtml(setup.equipment[slotName], 'equipment', slotName, 'slot-' + slotName);
          }).join('') + '</div>' +
          '<div class="gear-doll-misc">' + MISC_EQUIPMENT_SLOTS.map(function (slotName) {
            return slotHtml(setup.equipment[slotName], 'equipment', slotName, 'gear-slot-sm');
          }).join('') + '</div>' +
        '</div>';

        var grid = '<div class="inventory-grid">' + setup.inventory.map(function (item, idx) {
          return slotHtml(item, 'inventory', idx, '');
        }).join('') + '</div>';

        document.getElementById('pgGearFrame').innerHTML = doll + grid;
        renderSortButtons(setup);
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

      var MAIN_EQUIPMENT_SLOTS = ['head', 'cape', 'neck', 'ammo', 'weapon', 'body', 'shield', 'legs', 'hands', 'boots', 'ring'];
      // Eight extra planning-only slots (runes for a rune pouch,
      // teleports, whatever else a setup needs beyond its actual gear),
      // rendered as two rows of 4 below the paperdoll (see
      // .gear-doll-misc in purchase-goals.css) -- see
      // MISC_EQUIPMENT_SLOTS in app/schemas.py, which this mirrors
      // client-side same as MAIN_EQUIPMENT_SLOTS above mirrors that
      // file's EQUIPMENT_SLOTS.
      var MISC_EQUIPMENT_SLOTS = ['misc1', 'misc2', 'misc3', 'misc4', 'misc5', 'misc6', 'misc7', 'misc8'];

      function slotClasses(resolved) {
        var cls = 'gear-slot';
        if (!resolved) return cls;
        cls += ' filled';
        if (resolved.owned) cls += ' owned';
        else if (resolved.affordable) cls += ' affordable';
        else cls += ' not-owned';
        return cls;
      }

      function itemWikiUrl(itemName) {
        return 'https://oldschool.runescape.wiki/w/' + encodeURIComponent(String(itemName).replace(/ /g, '_'));
      }

      function slotHtml(resolved, slotType, slot, extraClass) {
        var picking = PG.picker && PG.picker.slotType === slotType && String(PG.picker.slot) === String(slot);
        var cls = slotClasses(resolved) + (extraClass ? ' ' + extraClass : '') + (picking ? ' picking' : '');
        // draggable="false" here -- browsers make <img> draggable by
        // default, which competes with the .gear-slot div's own
        // draggable="true" (see below): starting a drag with the
        // pointer right over the icon picked up the browser's native
        // image-drag instead of bubbling up to the slot's own
        // dragstart, so only the icon moved (as an image, not a slot
        // move) while the rest of the box didn't drag at all. This (plus
        // the matching -webkit-user-drag: none in purchase-goals.css for
        // Safari, which doesn't always respect the attribute alone)
        // makes the whole box the only thing that's ever draggable,
        // everywhere the pointer starts within it.
        var inner = resolved && resolved.icon
          ? '<img class="gear-slot-icon" src="' + esc(resolved.icon) + '" alt="" draggable="false" />'
          : (resolved ? '<span class="tracker-icon-fallback">' + esc(resolved.itemName || '?').slice(0, 6) + '</span>' : '');
        var title = resolved ? esc(resolved.itemName) : 'Empty slot';
        var itemNameAttr = resolved ? ' data-item-name="' + esc(resolved.itemName) + '"' : '';
        // The remove ("x") button only ever shows up on hover (see
        // .gear-slot-remove in purchase-goals.css) and only exists at all
        // when the slot is filled -- an empty slot has nothing to remove.
        var removeBtn = resolved ? '<button class="gear-slot-remove" type="button" title="Remove item">&times;</button>' : '';
        // Only a filled slot can be dragged FROM (nothing to move out of
        // an empty one) -- but every slot, filled or empty, is a valid
        // drop target either way (see wireSlotClicks), so this only ever
        // gates the `draggable` attribute, never drop handling.
        var draggableAttr = resolved ? ' draggable="true"' : '';
        return '<div class="' + cls + '" data-slot-type="' + slotType + '" data-slot="' + esc(slot) + '"' + itemNameAttr + draggableAttr + ' title="' + title + '">' +
          inner + removeBtn + '</div>';
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
          // ---- Drag-and-drop: drag a filled slot onto another slot to
          // move it there, or swap the two if the destination is also
          // filled. Works between equipment and inventory in either
          // direction, since every slot shares this same .gear-slot
          // wiring regardless of slotType. Only a filled slot is
          // `draggable` (see slotHtml), but EVERY slot -- filled or
          // empty -- needs the dragover/drop listeners below, since any
          // of them can be a drop target.
          if (el.getAttribute('draggable') === 'true') {
            el.addEventListener('dragstart', function (e) {
              var slotType = el.getAttribute('data-slot-type');
              var slot = el.getAttribute('data-slot');
              e.dataTransfer.effectAllowed = 'move';
              // text/plain (rather than a custom MIME type) so this also
              // degrades harmlessly if dropped outside the app instead of
              // silently failing to initiate the drag in some browsers.
              e.dataTransfer.setData('text/plain', JSON.stringify({ slotType: slotType, slot: slot }));
              el.classList.add('dragging');
            });
            el.addEventListener('dragend', function () {
              el.classList.remove('dragging');
              document.querySelectorAll('.gear-slot.drag-over').forEach(function (t) {
                t.classList.remove('drag-over');
              });
              // A completed drag shouldn't ALSO register as a click on
              // the slot it started from (which would open the item's
              // wiki page right after moving it) -- suppressed once,
              // below, then cleared.
              PG.dragSuppressClick = true;
            });
          }
          el.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            el.classList.add('drag-over');
          });
          el.addEventListener('dragleave', function () {
            el.classList.remove('drag-over');
          });
          el.addEventListener('drop', function (e) {
            e.preventDefault();
            el.classList.remove('drag-over');
            var raw = e.dataTransfer.getData('text/plain');
            if (!raw) return;
            var source;
            try { source = JSON.parse(raw); } catch (err) { return; }
            var toSlotType = el.getAttribute('data-slot-type');
            var toSlot = toSlotType === 'inventory' ? parseInt(el.getAttribute('data-slot'), 10) : el.getAttribute('data-slot');
            var fromSlotType = source.slotType;
            var fromSlot = fromSlotType === 'inventory' ? parseInt(source.slot, 10) : source.slot;
            // Dropped back onto its own slot -- nothing to do (also
            // covered server-side, but no reason to round-trip for it).
            if (fromSlotType === toSlotType && String(fromSlot) === String(toSlot)) return;
            moveSlotItem(fromSlotType, fromSlot, toSlotType, toSlot);
          });

          el.addEventListener('click', function () {
            if (PG.dragSuppressClick) {
              PG.dragSuppressClick = false;
              return;
            }
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
            var opening = !(PG.picker && PG.picker.slotType === slotType && String(PG.picker.slot) === String(slot));
            if (opening) {
              openSlotPicker(slotType, slot);
            } else {
              PG.picker = null;
            }
            PG.iconPicker = false;
            renderContent();
            if (opening) {
              var input = document.getElementById('slotSearchInput');
              if (input) {
                // preventScroll so the browser's own native "scroll
                // focused element into view" doesn't fire a second,
                // competing (and non-smooth) scroll right before ours
                // below -- scrollPickerIntoView is the only thing that
                // should move the page here. select() is a no-op on an
                // empty input but puts any leftover text in a re-opened
                // picker's box in a ready-to-replace state.
                input.focus({ preventScroll: true });
                input.select();
              }
              scrollPickerIntoView();
            }
          });
        });
      }

      // Smoothly scrolls the just-opened slot picker's search box into
      // view, with some breathing room below it -- the picker renders
      // directly below the gear/inventory grid, which can easily sit
      // below the fold (a shorter viewport, or the page having been
      // scrolled down to reach the slot that was clicked), so without
      // this a player could click an empty slot and not notice anything
      // happened. Deliberately scrolls a bit past the search box itself
      // (MARGIN_BELOW), not just up to its bottom edge -- landing it
      // right at the very edge of the viewport looks cramped, and
      // leaves no room for the suggestions dropdown that appears the
      // moment the player starts typing. A no-op when the box (plus
      // that margin) is already visible, rather than jumping the page
      // around on every click. Called right after renderContent()
      // rebuilds #pgSlotPicker, so the search input already exists in
      // the DOM by the time this runs.
      function scrollPickerIntoView() {
        var target = document.getElementById('slotSearchInput') || document.getElementById('pgSlotPicker');
        if (!target) return;
        var MARGIN_BELOW = 160;
        var rect = target.getBoundingClientRect();
        var overflowBelow = rect.bottom + MARGIN_BELOW - window.innerHeight;
        if (overflowBelow > 0) {
          window.scrollBy({ top: overflowBelow, left: 0, behavior: 'smooth' });
        } else if (rect.top < 0) {
          // Rare: the picker sits above the current scroll position
          // (e.g. the page was scrolled further since it opened) --
          // bring it back into view from the top instead.
          window.scrollBy({ top: rect.top - 24, left: 0, behavior: 'smooth' });
        }
      }

      // ---- Still to Purchase: sort mode buttons + drag-to-reorder ----------

      // 'Low to High'/'High to Low' read as a plain "GP" label plus an
      // arrow showing which direction that sorts -- up for ascending
      // (cheapest first), down for descending (priciest first) -- same
      // shorthand the Loot Tracker's own sort tabs use now (see
      // _sort_tabs in app/pages.py).
      var STILL_TO_PURCHASE_SORT_MODES = [
        { key: 'low_to_high', label: 'GP \\u2191', title: 'GP, low to high' },
        { key: 'high_to_low', label: 'GP \\u2193', title: 'GP, high to low' },
        { key: 'alphabetical', label: 'Alphabetical' },
        { key: 'custom', label: 'Custom' },
      ];

      // The buttons that replaced the old static "Still to purchase"
      // label -- rebuilt every render (like the rest of this page) so
      // the active one can track setup.stillToPurchaseSort, which
      // changes server-side, not just on the client.
      function renderSortButtons(setup) {
        var el = document.getElementById('pgSortButtons');
        if (!el) return;
        var mode = setup.stillToPurchaseSort || 'low_to_high';
        el.innerHTML = STILL_TO_PURCHASE_SORT_MODES.map(function (m) {
          var cls = 'sort-btn' + (m.key === mode ? ' active' : '');
          var titleAttr = m.title ? ' title="' + m.title + '"' : '';
          return '<button type="button" class="' + cls + '" data-sort-mode="' + m.key + '"' + titleAttr + '>' + m.label + '</button>';
        }).join('');
        el.querySelectorAll('.sort-btn').forEach(function (btn) {
          btn.addEventListener('click', function () {
            var newMode = btn.getAttribute('data-sort-mode');
            if (newMode === mode) return;
            setStillToPurchaseSort(newMode);
          });
        });
      }

      async function setStillToPurchaseSort(mode) {
        const data = await apiCall('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/still-to-purchase-sort', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sort_mode: mode }),
        });
        if (data) { PG.stateVersion++; PG.data = data; render(); }
      }

      // True if any gear (equipment, including the misc slots) or
      // inventory slot on this setup actually holds an item -- used
      // purely to pick the right empty-state message in
      // renderSummaryList below, since an empty "still to purchase"
      // list alone doesn't say whether that's because nothing's been
      // added yet or because everything added is already owned.
      function setupHasAnyItems(setup) {
        var equipment = setup.equipment || {};
        for (var slot in equipment) {
          if (Object.prototype.hasOwnProperty.call(equipment, slot) && equipment[slot]) return true;
        }
        var inventory = setup.inventory || [];
        for (var i = 0; i < inventory.length; i++) {
          if (inventory[i]) return true;
        }
        return false;
      }

      // Only the "still to purchase" list + empty message -- the
      // next-purchase mini bar/amount above it is a fixed element updated
      // in place by updateOverlay() instead, so it isn't rebuilt (and
      // therefore doesn't need to animate) every time this list changes.
      function renderSummaryList(setup) {
        var emptyEl = document.getElementById('pgSummaryEmpty');
        var listEl = document.getElementById('pgSummaryList');
        if (!setup.stillToPurchase.length) {
          // An empty "still to purchase" list means one of two very
          // different things -- a brand new (or emptied-out) setup with
          // nothing in any slot yet, versus a setup that's fully filled
          // in and every one of those items is already owned -- so the
          // message has to say which. setupHasAnyItems checks the
          // setup's actual gear/inventory slots directly rather than
          // inferring from stillToPurchase being empty, since that's
          // exactly the one signal that's identical in both cases.
          emptyEl.textContent = setupHasAnyItems(setup)
            ? 'Everything in this setup is already owned.'
            : 'Add items to the left to get started.';
          emptyEl.style.display = '';
          listEl.style.display = 'none';
          listEl.innerHTML = '';
          return;
        }
        emptyEl.style.display = 'none';
        listEl.style.display = '';
        // Rows are only draggable in "custom" sort mode -- dragging one
        // in "high to low"/"low to high" would just get computed right
        // back out from under you on the next render, since those two
        // are always re-sorted by live cost rather than remembered.
        var customMode = (setup.stillToPurchaseSort || 'low_to_high') === 'custom';
        listEl.innerHTML = setup.stillToPurchase.map(function (item) {
          var rowCls = 'gear-summary-row' + (item.purchasable ? '' : ' unpurchasable') + (customMode ? ' draggable' : '');
          var costHtml = item.purchasable
            ? '<span class="gear-summary-row-cost">' + formatGp(item.cost) + '</span>'
            : '<span class="gear-summary-row-cost na">n/a</span>';
          var draggableAttr = customMode ? ' draggable="true"' : '';
          var slotAttrs = ' data-slot-type="' + esc(item.slotType) + '" data-slot="' + esc(item.slot) + '"';
          // draggable="false" on the icon for the same reason as
          // .gear-slot-icon (see slotHtml) -- otherwise starting a drag
          // with the pointer over the icon grabs the browser's own
          // native image drag instead of the row underneath it.
          return '<div class="' + rowCls + '"' + slotAttrs + draggableAttr + '>' +
            (item.icon ? '<img class="gear-summary-row-icon" src="' + esc(item.icon) + '" alt="" draggable="false" />' : '<span class="gear-summary-row-icon"></span>') +
            '<span class="gear-summary-row-name">' + esc(item.itemName) + '</span>' +
            costHtml +
            '</div>';
        }).join('');
        wireSummaryDrag(customMode);
      }

      // Drag-and-drop reordering for the "custom" sort mode -- same
      // dragstart/dragover/drop shape as wireSlotClicks' gear-slot
      // dragging, just vertical-list reordering instead of move-or-swap
      // between two fixed slots. A drop always lands the dragged row
      // immediately before whichever row it was dropped on.
      function wireSummaryDrag(customMode) {
        if (!customMode) return;
        document.querySelectorAll('#pgSummaryList .gear-summary-row').forEach(function (el) {
          el.addEventListener('dragstart', function (e) {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', JSON.stringify({
              slotType: el.getAttribute('data-slot-type'),
              slot: el.getAttribute('data-slot'),
            }));
            el.classList.add('dragging');
          });
          el.addEventListener('dragend', function () {
            el.classList.remove('dragging');
            document.querySelectorAll('#pgSummaryList .gear-summary-row.drag-over').forEach(function (t) {
              t.classList.remove('drag-over');
            });
          });
          el.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            el.classList.add('drag-over');
          });
          el.addEventListener('dragleave', function () {
            el.classList.remove('drag-over');
          });
          el.addEventListener('drop', function (e) {
            e.preventDefault();
            el.classList.remove('drag-over');
            var raw = e.dataTransfer.getData('text/plain');
            if (!raw) return;
            var source;
            try { source = JSON.parse(raw); } catch (err) { return; }
            var target = { slotType: el.getAttribute('data-slot-type'), slot: el.getAttribute('data-slot') };
            if (source.slotType === target.slotType && String(source.slot) === String(target.slot)) return;
            reorderStillToPurchase(source, target);
          });
        });
      }

      async function reorderStillToPurchase(source, target) {
        var setup = activeSetup();
        if (!setup) return;
        function sameSlot(a, b) { return a.slotType === b.slotType && String(a.slot) === String(b.slot); }
        var order = setup.stillToPurchase.map(function (item) { return { slotType: item.slotType, slot: item.slot }; });
        var fromIdx = order.findIndex(function (entry) { return sameSlot(entry, source); });
        if (fromIdx === -1) return;
        var moved = order.splice(fromIdx, 1)[0];
        // Removing the dragged row can shift the target's own index down
        // by one, so its position is looked up again fresh rather than
        // reusing an index captured before the splice above.
        var toIdx = order.findIndex(function (entry) { return sameSlot(entry, target); });
        if (toIdx === -1) { order.splice(fromIdx, 0, moved); } else { order.splice(toIdx, 0, moved); }

        const data = await apiCall('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/still-to-purchase-order', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            order: order.map(function (entry) {
              return { slot_type: entry.slotType, slot: entry.slotType === 'inventory' ? parseInt(entry.slot, 10) : entry.slot };
            }),
          }),
        });
        if (data) { PG.stateVersion++; PG.data = data; render(); }
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
          '  <div class="gear-icon-picker-actions">' +
          '    <button class="btn-secondary" id="iconClearBtn" type="button">Clear</button>' +
          '    <button class="btn-secondary" id="iconCancelBtn" type="button">Cancel</button>' +
          '  </div>' +
          '</div>';
        var input = document.getElementById('iconSearchInput');
        input.addEventListener('input', debounce(function () { runSearch(input.value, renderIconSuggestions); }, 200));
        document.getElementById('iconClearBtn').addEventListener('click', async function () {
          const data = await apiCall('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/icon', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ icon: null }),
          });
          if (data) { PG.stateVersion++; PG.data = data; PG.iconPicker = false; render(); }
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
            if (data) { PG.stateVersion++; PG.data = data; PG.iconPicker = false; render(); }
          });
        });
      }

      // ---- Gear/inventory slot picker --------------------------------------

      function openSlotPicker(slotType, slot) {
        PG.picker = { slotType: slotType, slot: slot, query: '' };
      }

      function renderSlotPicker() {
        var el = document.getElementById('pgSlotPicker');
        if (!el) return;
        var p = PG.picker;
        if (!p) { el.innerHTML = ''; return; }

        // No "build from parts" option any more, and no separate "Add"
        // step either -- clicking a suggestion saves it immediately
        // (see renderSlotSuggestions), so this is just the search box.
        // Search itself covers every known OSRS item (live Grand
        // Exchange matches, known item-combination recipes, and every
        // other named item from app/item_ids.py's snapshot, in that
        // order -- see search_items in app/purchase_goals.py), and a
        // combination item like "Neitiznot faceguard" is auto-expanded
        // into its real parts server-side the moment it's picked (see
        // expand_recipe_components in app/recipes.py), so nobody has to
        // know or type out what an item is made of, or fall back to
        // typing in an untradeable item blind.
        var body = '' +
          '<div class="search-box search-box-full">' +
          '  <input type="text" id="slotSearchInput" placeholder="Search for an item" autocomplete="off" value="' + esc(p.query) + '" />' +
          '  <div class="suggestions" id="slotSuggestions"></div>' +
          '</div>';

        el.innerHTML = '<div class="gear-slot-picker">' + body + '</div>';

        wireSlotPickerEvents();
      }

      function wireSlotPickerEvents() {
        var p = PG.picker;
        var input = document.getElementById('slotSearchInput');
        input.addEventListener('input', debounce(function () {
          p.query = input.value;
          runSearch(input.value, function (results) { renderSlotSuggestions(input.value, results); });
        }, 200));
      }

      function renderSlotSuggestions(query, results) {
        var box = document.getElementById('slotSuggestions');
        if (!box) return;
        var trimmed = (query || '').trim();
        if (!trimmed) { box.classList.remove('show'); box.innerHTML = ''; return; }

        var rowsHtml = results.map(function (r) {
          // Combination items (e.g. "Neitiznot faceguard") have no
          // Grand Exchange listing of their own -- no data-item-id --
          // but are still a normal, icon-bearing, click-to-select
          // suggestion like any other. The server auto-detects and
          // prices these from their real components once selected --
          // see app/recipes.py -- so nobody has to already know or type
          // out what an item is made of just to find it.
          var idAttr = r.id != null ? ' data-item-id="' + r.id + '"' : '';
          return '<div class="suggestion" data-item-name="' + esc(r.name) + '"' + idAttr + '>' +
            (r.icon ? '<img src="' + esc(r.icon) + '" alt="" />' : '') + '<span>' + esc(r.name) + '</span></div>';
        }).join('');

        // No match at all -- search now spans live Grand Exchange
        // items, known item-combination recipes, and every other named
        // item in the game (see search_items in
        // app/purchase_goals.py), so this should be rare -- a typo, or
        // something genuinely not in the game. Nothing left to fall
        // back to, so this is just a plain, non-interactive message
        // rather than an "add it blind" escape hatch.
        if (!results.length) {
          rowsHtml = '<div class="suggestion-empty">No items found</div>';
        }

        box.innerHTML = rowsHtml;
        box.classList.add('show');

        box.querySelectorAll('.suggestion[data-item-name]').forEach(function (row) {
          row.addEventListener('click', function () {
            var idAttr = row.getAttribute('data-item-id');
            box.classList.remove('show');
            box.innerHTML = '';
            saveSlot({
              item_id: idAttr !== null ? parseInt(idAttr, 10) : null,
              item_name: row.getAttribute('data-item-name'),
            });
          });
        });
      }

      async function saveSlot(item) {
        var p = PG.picker;
        const data = await apiCall('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/slot', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ slot_type: p.slotType, slot: p.slot, item: item }),
        });
        if (data) { PG.stateVersion++; PG.data = data; PG.picker = null; render(); }
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
        if (data) { PG.stateVersion++; PG.data = data; render(); }
      }

      // Drag-and-drop: moves whatever's in (fromSlotType, fromSlot) into
      // (toSlotType, toSlot), across equipment and inventory alike --
      // see move_gear_slot_item in app/main.py, which does the actual
      // move-or-swap server-side against the raw stored item (not this
      // resolved/priced shape), so a combo's exact stored components
      // travel with it untouched. Closes any open slot picker afterward
      // -- if one happened to be open on the slot just dropped into, its
      // stale target no longer matches what's there.
      async function moveSlotItem(fromSlotType, fromSlot, toSlotType, toSlot) {
        const data = await apiCall('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/slot/move', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            from_slot_type: fromSlotType, from_slot: fromSlot,
            to_slot_type: toSlotType, to_slot: toSlot,
          }),
        });
        if (data) { PG.stateVersion++; PG.data = data; PG.picker = null; render(); }
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
        var opening = !PG.iconPicker;
        PG.iconPicker = opening;
        PG.picker = null;
        renderIconPicker();
        document.getElementById('pgSlotPicker').innerHTML = '';
        if (opening) {
          // Same "land the cursor in the search box, ready to type"
          // treatment as opening a gear/inventory slot's own picker --
          // see the slot-click handler above. select() is a no-op on an
          // empty input but puts any leftover text in a re-opened
          // picker's box in a ready-to-replace state.
          var input = document.getElementById('iconSearchInput');
          if (input) {
            input.focus({ preventScroll: true });
            input.select();
          }
        }
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
        if (data) { PG.stateVersion++; PG.data = data; setActiveSetupId(data.gearSetups.length ? data.gearSetups[0].id : null); render(); }
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
            PG.stateVersion++;
            PG.data = data;
            var created = data.gearSetups.find(function (s) { return s.name === name; }) || data.gearSetups[data.gearSetups.length - 1];
            if (created) setActiveSetupId(created.id);
            render();
          }
        } else if (mode === 'rename') {
          var setup = activeSetup();
          if (!setup) return;
          data = await apiCall('/api/gear-setups/' + encodeURIComponent(setup.id), {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name }),
          });
          if (data) { PG.stateVersion++; PG.data = data; render(); }
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


def render_loot_tracker(player: Player) -> str:
    """The Loot Tracker page -- a first pass at porting the original
    single-user Maintrius tool's Loot Tracker/Trip Tracker features
    (see app/loot.py's module docstring for what's here today and
    what's deliberately not yet). Same shape as render_purchase_goals
    above: a thin server-rendered shell, everything below it drawn
    client-side from one polled JSON payload (GET /api/players/me/loot,
    see app/loot.py's build_loot_state).

    Everything on this page is scoped to the rolling last-24-hours
    window: the bar chart; the NPC panel below-left that lets a player
    click one NPC to see just that NPC's share of each hour's loot
    filled in at the bottom of its bar (the bar's own full all-sources
    height still shows as an outline above it), searchable/sortable via
    its own search box and sort tabs; and the item panel below-right,
    which mirrors that same search/sort UI over either every item
    dropped by every NPC in the window (nothing selected) or just the
    selected NPC's own items -- see renderBarChart/renderNpcRow/
    renderItemList below, and build_loot_state in app/loot.py for the
    matching hourlyBuckets/npcHourlyValues/windowItems/npcItems shape."""
    extra_head = f'<link rel="stylesheet" href="/static/css/loot-tracker.css?v={_LOOT_TRACKER_CSS_VERSION}" />'

    def _sort_tabs(tabs_id: str, count_label: str) -> str:
        # count_label names whichever secondary number that panel's own
        # boxes show beside gp -- "KC" for the NPC panel, "Qty" for the
        # item panel -- so its two new count-based tabs read naturally on
        # each side (data-sort stays the same generic "count-high"/
        # "count-low" either way; see sortEntries in the script below for
        # which field that actually sorts by per panel). Labeled as the
        # metric name plus an arrow (down for descending/high-to-low, up
        # for ascending/low-to-high -- same shorthand Purchase Goals'
        # own sort buttons use now, see STILL_TO_PURCHASE_SORT_MODES)
        # rather than spelling out "High to Low"/"Low to High" -- with
        # six tabs sharing one row, the full text wrapped each button
        # onto two lines, which was both harder to scan and taller than
        # intended.
        return f"""
          <div class="loot-sort-tabs" id="{tabs_id}">
            <button type="button" class="loot-sort-tab" data-sort="high" title="GP, high to low">GP &darr;</button>
            <button type="button" class="loot-sort-tab" data-sort="low" title="GP, low to high">GP &uarr;</button>
            <button type="button" class="loot-sort-tab" data-sort="count-high" title="{count_label}, high to low">{count_label} &darr;</button>
            <button type="button" class="loot-sort-tab" data-sort="count-low" title="{count_label}, low to high">{count_label} &uarr;</button>
            <button type="button" class="loot-sort-tab" data-sort="alpha">Alphabetical</button>
            <button type="button" class="loot-sort-tab" data-sort="recent">Recent</button>
          </div>
        """

    body = f"""
    <h2 class="page-title">Loot Tracker</h2>
    <div class="auth-error" id="lootError"></div>
    <p class="pg-empty" id="lootEmptyMsg">Loading&hellip;</p>
    <div id="lootBody" style="display:none;">
      <div class="loot-chart-card">
        <div class="loot-chart-header">
          <div class="loot-chart-kills" id="lootChartKills">LAST 24H &middot; 0 KILLS</div>
          <div class="loot-chart-title" id="lootChartTitle">ALL NPCs</div>
          <div class="loot-chart-total" id="lootChartTotal">0 gp</div>
        </div>
        <div class="loot-bar-plot">
          <div class="loot-bar-gridlines" id="lootBarGridlines"></div>
          <div class="loot-bar-bars" id="lootBarBars"></div>
        </div>
        <div class="loot-bar-x-labels" id="lootBarXLabels"></div>
      </div>
      <div class="loot-panels">
        <div class="loot-panel">
          <div class="loot-panel-controls">
            <input type="text" class="loot-search" id="lootNpcSearch" placeholder="Search for an NPC" autocomplete="off" />
            {_sort_tabs("lootNpcSortTabs", "KC")}
          </div>
          <p class="loot-column-empty" id="lootNpcEmpty" style="display:none;">
            No NPC kills in the last 24 hours yet.
          </p>
          <div class="loot-npc-row" id="lootNpcRow"></div>
        </div>
        <div class="loot-panel">
          <div class="loot-panel-controls">
            <input type="text" class="loot-search" id="lootItemSearch" placeholder="Search for an item" autocomplete="off" />
            {_sort_tabs("lootItemSortTabs", "Qty")}
          </div>
          <p class="loot-column-empty" id="lootItemEmpty" style="display:none;">
            No items dropped in the last 24 hours yet.
          </p>
          <div class="loot-item-list" id="lootItemList"></div>
        </div>
      </div>
    </div>
    """
    script = """
    (function () {
      var state = { selectedNpc: null, npcSort: 'high', npcSearch: '', itemSort: 'high', itemSearch: '' };
      var lastData = null;

      // Shared by both panels' search boxes -- a plain case-insensitive
      // substring match against whichever name field the caller points
      // it at (sourceName for NPCs, itemName for items).
      function filterByName(list, query, nameKey) {
        if (!query) return list;
        var q = query.toLowerCase();
        return list.filter(function (entry) {
          return (entry[nameKey] || '').toLowerCase().indexOf(q) !== -1;
        });
      }

      // Shared by both panels' sort tabs. 'high'/'low' sort by valueKey
      // (gp), 'count-high'/'count-low' sort by countKey (killCount for
      // NPCs, quantity for items -- each panel's own secondary number,
      // see _sort_tabs' count_label in app/pages.py for the matching tab
      // labels), 'alpha' by nameKey, 'recent' by recentKey (an ISO
      // timestamp -- lastKillAt for NPCs, lastDroppedAt for items)
      // newest first. Never mutates the list it's given -- callers still
      // hold the original (unsorted, unfiltered) array from lastData.
      function sortEntries(list, sortMode, nameKey, valueKey, recentKey, countKey) {
        var out = list.slice();
        if (sortMode === 'low') {
          out.sort(function (a, b) { return (a[valueKey] || 0) - (b[valueKey] || 0); });
        } else if (sortMode === 'count-high') {
          out.sort(function (a, b) { return (b[countKey] || 0) - (a[countKey] || 0); });
        } else if (sortMode === 'count-low') {
          out.sort(function (a, b) { return (a[countKey] || 0) - (b[countKey] || 0); });
        } else if (sortMode === 'alpha') {
          out.sort(function (a, b) { return (a[nameKey] || '').localeCompare(b[nameKey] || ''); });
        } else if (sortMode === 'recent') {
          out.sort(function (a, b) { return new Date(b[recentKey] || 0) - new Date(a[recentKey] || 0); });
        } else {
          out.sort(function (a, b) { return (b[valueKey] || 0) - (a[valueKey] || 0); });
        }
        return out;
      }

      // Toggles which sort-tab button looks active within one of the
      // two .loot-sort-tabs containers -- shared by both panels since
      // they're identical markup (see _sort_tabs in render_loot_tracker).
      function updateSortTabs(containerId, activeSort) {
        var container = document.getElementById(containerId);
        var btns = container.querySelectorAll('.loot-sort-tab');
        for (var i = 0; i < btns.length; i++) {
          btns[i].classList.toggle('active', btns[i].getAttribute('data-sort') === activeSort);
        }
      }

      // The item panel shows every NPC's items combined when nothing's
      // selected, or just the selected NPC's own items once one is
      // clicked in the NPC panel -- see build_loot_state's windowItems/
      // npcItems in app/loot.py for how those two lists are computed.
      function currentItems() {
        if (!lastData) return [];
        if (state.selectedNpc && lastData.npcItems && lastData.npcItems[state.selectedNpc]) {
          return lastData.npcItems[state.selectedNpc];
        }
        return lastData.windowItems || [];
      }

      function fmtGp(n) {
        n = n || 0;
        return n.toLocaleString('en-US');
      }

      // Compact axis-label form of a gp amount -- "12.4k" / "3.1M" -- so
      // the bar chart's gridline labels stay readable in a narrow gutter.
      // Ported from the original tool's fmtGpCompact.
      function fmtGpCompact(n) {
        var sign = n < 0 ? '-' : '';
        var abs = Math.abs(n || 0);
        if (abs >= 1e6) return sign + (abs / 1e6).toFixed(abs >= 1e7 ? 0 : 1).replace(/\\.0$/, '') + 'M';
        if (abs >= 1e3) return sign + (abs / 1e3).toFixed(abs >= 1e4 ? 0 : 1).replace(/\\.0$/, '') + 'k';
        return sign + Math.round(abs).toLocaleString('en-US');
      }

      // Rounds a chart's max value up to a "nice" number (1/2/5 x a power
      // of ten) so the gridlines land on clean values. Same as the
      // original tool's niceMax.
      function niceMax(value) {
        if (!value || value <= 0) return 100;
        var magnitude = Math.pow(10, Math.floor(Math.log10(value)));
        var normalized = value / magnitude;
        var niceNormalized;
        if (normalized <= 1) niceNormalized = 1;
        else if (normalized <= 2) niceNormalized = 2;
        else if (normalized <= 5) niceNormalized = 5;
        else niceNormalized = 10;
        return niceNormalized * magnitude;
      }

      function fmtClock(isoString) {
        if (!isoString) return '';
        return new Date(isoString).toLocaleTimeString('en-US', { hour: 'numeric' });
      }

      function iconImg(src, alt, cls) {
        if (!src) return '';
        // Quietly hidden on a 404 (a guessed NPC/item wiki filename that
        // doesn't exist) rather than showing a broken-image icon -- same
        // treatment item icons already get elsewhere on the site.
        return '<img class="' + cls + '" src="' + src + '" alt="" loading="lazy" ' +
          'onerror="this.style.display=\\'none\\'" />';
      }

      function escapeHtml(s) {
        var div = document.createElement('div');
        div.textContent = s == null ? '' : String(s);
        return div.innerHTML;
      }

      // Rolling last-24-hours bar chart, bucketed hourly (oldest on the
      // left, ending at "now" on the right) -- ported from the original
      // single-user tool's Loot Tracker chart (renderVorkathBarChart),
      // summed across every source by default. When an NPC is selected
      // (state.selectedNpc, set by renderNpcRow's click handler below)
      // each bar instead shows two layers: a full-height outline at the
      // bucket's own total value (so the scale/shape of the whole chart
      // never changes), with a solid fill at the bottom sized to just
      // that NPC's share of the same bucket. maxValue is always derived
      // from the total buckets, never the selected NPC's own values, so
      // the axis stays put when switching NPCs. Reuses the existing
      // bar-col elements when the bucket count hasn't changed (it's
      // always the same 24 hourly slots on every 10s poll) so the CSS
      // height transition actually animates between polls instead of
      // snapping.
      function renderBarChart(buckets, windowValue, windowKills, npcHourlyValues, selectedNpc, windowNpcs) {
        buckets = buckets || [];
        npcHourlyValues = npcHourlyValues || {};
        // With an NPC selected, the header's gp/kill numbers switch to
        // just that NPC's own totals (already sitting right on its
        // windowNpcs entry -- value/killCount, the same numbers its own
        // NPC box shows) instead of the whole window's -- otherwise
        // selecting Guard would still show every other NPC's loot
        // summed in up top while the chart itself only fills in Guard's
        // share, which reads as a mismatch.
        var selectedEntry = selectedNpc && windowNpcs
          ? windowNpcs.filter(function (n) { return n.sourceName === selectedNpc; })[0]
          : null;
        var headerValue = selectedEntry ? selectedEntry.value : windowValue;
        var headerKills = selectedEntry ? selectedEntry.killCount : windowKills;
        document.getElementById('lootChartTotal').textContent = fmtGp(headerValue) + ' gp';
        document.getElementById('lootChartKills').textContent =
          'last 24h \\u00b7 ' + (headerKills || 0).toLocaleString('en-US') + ' kill' + (headerKills === 1 ? '' : 's');
        document.getElementById('lootChartTitle').textContent = selectedNpc || 'ALL NPCs';

        var maxValue = niceMax(Math.max.apply(null, [0].concat(buckets.map(function (b) { return b.value; }))));
        var gridlineSteps = 4;
        var gridlinesEl = document.getElementById('lootBarGridlines');
        var stepsHtml = '';
        for (var i = 0; i <= gridlineSteps; i++) {
          var frac = i / gridlineSteps;
          stepsHtml += '<div class="loot-bar-gridline" style="bottom:' + (frac * 100).toFixed(2) + '%;">' +
            '<div class="loot-bar-gridline-label">' + fmtGpCompact(maxValue * frac) + '</div>' +
          '</div>';
        }
        gridlinesEl.innerHTML = stepsHtml;

        var selectedValues = selectedNpc ? (npcHourlyValues[selectedNpc] || buckets.map(function () { return 0; })) : null;

        // The outline always sits at the bucket's *total* height and
        // never itself animates or changes with selection -- only the
        // solid fill below (see fillPct) grows/shrinks against it. With
        // nothing selected, the fill's height equals the outline's (both
        // are the bucket total), so the fill simply covers the outline
        // completely and it's invisible -- nothing to distinguish from a
        // plain solid bar. Selecting an NPC only changes the FILL's
        // height (down to that NPC's share), which is what exposes the
        // outline sitting above it -- so it reads as the bar shrinking
        // down to reveal an outline that was quietly there the whole
        // time, and deselecting reads as the bar growing back up to meet
        // it again, rather than the outline itself doing any growing,
        // shrinking, or fading of its own.
        function outlinePct(b) {
          return maxValue > 0 ? Math.max(0, Math.min(100, (b.value / maxValue) * 100)) : 0;
        }
        // A bordered box still paints its border even at height:0 (the
        // same reason a 0x0 div with colored borders makes a CSS
        // triangle) -- so an hour with zero total loot would render a
        // visible sliver of the outline's border color despite its
        // height correctly staying at 0%. Only turning the border on for
        // an hour that actually has something to outline avoids that.
        // Deliberately NOT tied to whether an NPC is selected (unlike
        // before) -- the whole point now is that the outline's own
        // visibility never changes on selection, only the fill's height
        // does.
        function outlineActive(b) {
          return b.value > 0;
        }
        function fillValue(b, i) {
          return selectedNpc ? (selectedValues[i] || 0) : b.value;
        }
        function fillPct(b, i) {
          var v = fillValue(b, i);
          return maxValue > 0 ? Math.max(0, Math.min(100, (v / maxValue) * 100)) : 0;
        }
        function titleFor(b, i) {
          if (selectedNpc) {
            return selectedNpc + ': ' + fmtGp(fillValue(b, i)) + ' gp \\u00b7 hour total ' + fmtGp(b.value) + ' gp';
          }
          return fmtGp(b.value) + ' gp' + (b.killCount ? ' \\u00b7 ' + b.killCount + ' kill' + (b.killCount === 1 ? '' : 's') : '');
        }

        var barsEl = document.getElementById('lootBarBars');
        var existingCols = barsEl.children;
        if (existingCols.length !== buckets.length) {
          barsEl.innerHTML = buckets.map(function (b, i) {
            return '<div class="loot-bar-col" title="' + titleFor(b, i) + '">' +
              '<div class="loot-bar-outline' + (outlineActive(b) ? ' active' : '') + '" style="height:' + outlinePct(b) + '%;"></div>' +
              '<div class="loot-bar-fill' + (fillPct(b, i) > 0 ? ' has-value' : '') + '" style="height:' + fillPct(b, i) + '%;"></div>' +
            '</div>';
          }).join('');
        } else {
          buckets.forEach(function (b, i) {
            var col = existingCols[i];
            col.title = titleFor(b, i);
            var outline = col.querySelector('.loot-bar-outline');
            outline.style.height = outlinePct(b) + '%';
            outline.classList.toggle('active', outlineActive(b));
            var fill = col.querySelector('.loot-bar-fill');
            var fp = fillPct(b, i);
            fill.style.height = fp + '%';
            fill.classList.toggle('has-value', fp > 0);
          });
        }

        // Labeling every hour would be unreadable at 24 bars -- every
        // 4th hour, plus the chart always ends at "now".
        document.getElementById('lootBarXLabels').innerHTML = buckets.map(function (b, i) {
          if (i === buckets.length - 1) return '<div class="loot-bar-x-label now">NOW</div>';
          var label = (i % 4 === 0) ? fmtClock(b.start) : '';
          return '<div class="loot-bar-x-label">' + label + '</div>';
        }).join('');
      }

      // The clickable "By NPC" row -- one box per NPC killed in the
      // last 24 hours, each toggling state.selectedNpc (clicking the
      // already-active one clears it back to "all sources") and
      // re-rendering the chart/row from the last-polled data, with no
      // extra fetch needed.
      //
      // Only rebuilds the row's HTML (and so its <img> icons) when the
      // actual set/order of NPCs has changed -- otherwise just toggles
      // each existing box's active/title state in place. Rebuilding on
      // every single 10s poll (even though the same NPCs were still
      // showing) was what made an icon "flicker": a fresh <img src=...>
      // every poll re-fetches/redraws it from scratch, which shows up
      // as a flash for any icon that isn't instant to (re)load -- not a
      // problem with that icon's own URL.
      // The full NPC list from lastData is filtered by state.npcSearch
      // and sorted by state.npcSort before every render -- so the
      // dedup key below has to reflect the search/sort state too, not
      // just which NPCs came back from the poll, or an in-place search
      // keystroke would find an unchanged-looking key (same NPCs, same
      // order coincidentally) and skip rebuilding.
      var lastNpcKey = null;
      function renderNpcRow(npcs) {
        var emptyEl = document.getElementById('lootNpcEmpty');
        var rowEl = document.getElementById('lootNpcRow');
        if (!npcs.length) {
          emptyEl.textContent = 'No NPC kills in the last 24 hours yet.';
          emptyEl.style.display = '';
          rowEl.innerHTML = '';
          lastNpcKey = null;
          return;
        }

        var sorted = sortEntries(filterByName(npcs, state.npcSearch, 'sourceName'), state.npcSort, 'sourceName', 'value', 'lastKillAt', 'killCount');
        if (!sorted.length) {
          emptyEl.textContent = 'No NPCs match your search.';
          emptyEl.style.display = '';
          rowEl.innerHTML = '';
          lastNpcKey = null;
          return;
        }
        emptyEl.style.display = 'none';

        function npcTitle(n) {
          return n.sourceName + ' \\u2014 ' + fmtGp(n.value) + ' gp \\u00b7 ' + n.killCount + ' kill' + (n.killCount === 1 ? '' : 's');
        }

        var key = state.npcSearch + '\\u0001' + state.npcSort + '\\u0001' + sorted.map(function (n) { return n.sourceName; }).join('|');
        if (key !== lastNpcKey) {
          lastNpcKey = key;
          rowEl.innerHTML = sorted.map(function (n) {
            var active = state.selectedNpc === n.sourceName;
            return '<button type="button" class="loot-npc-box' + (active ? ' active' : '') + '" data-npc="' +
              escapeHtml(n.sourceName) + '" title="' + escapeHtml(npcTitle(n)) + '">' +
              iconImg(n.icon, n.sourceName, 'loot-npc-box-icon') +
              '<div class="loot-npc-box-kc">' + n.killCount + ' kc</div>' +
              '<div class="loot-npc-box-value">' + fmtGpCompact(n.value) + ' gp</div>' +
            '</button>';
          }).join('');
          return;
        }

        // Same NPC set/order as last render (key unchanged) -- reuse
        // the existing boxes (and their <img> icons, avoiding the
        // flicker) but still refresh the kc/value text and title in
        // place, since a later poll can bump those numbers for an NPC
        // that's still sorted into the same slot.
        var boxes = rowEl.children;
        sorted.forEach(function (n, i) {
          var box = boxes[i];
          if (!box) return;
          box.classList.toggle('active', state.selectedNpc === n.sourceName);
          box.title = npcTitle(n);
          var kcEl = box.querySelector('.loot-npc-box-kc');
          if (kcEl) kcEl.textContent = n.killCount + ' kc';
          var valEl = box.querySelector('.loot-npc-box-value');
          if (valEl) valEl.textContent = fmtGpCompact(n.value) + ' gp';
        });
      }

      // The item panel below-right -- either every item dropped by
      // every NPC in the window (nothing selected) or just the
      // selected NPC's own items (see currentItems above), filtered by
      // state.itemSearch and sorted by state.itemSort the same way the
      // NPC row is. Keyed on itemId (falling back to itemName for
      // stackables/untradeables that share a name but no id, matching
      // _add_item_totals's own key choice server-side) rather than
      // array index, plus the selected NPC and search/sort state, so
      // switching NPCs or search/sort always rebuilds (new icons) while
      // an unchanged poll reuses the existing DOM (no icon flicker).
      var lastItemKey = null;
      function renderItemList(items) {
        var emptyEl = document.getElementById('lootItemEmpty');
        var listEl = document.getElementById('lootItemList');
        if (!items.length) {
          emptyEl.textContent = 'No items dropped in the last 24 hours yet.';
          emptyEl.style.display = '';
          listEl.innerHTML = '';
          lastItemKey = null;
          return;
        }

        var sorted = sortEntries(filterByName(items, state.itemSearch, 'itemName'), state.itemSort, 'itemName', 'value', 'lastDroppedAt', 'quantity');
        if (!sorted.length) {
          emptyEl.textContent = 'No items match your search.';
          emptyEl.style.display = '';
          listEl.innerHTML = '';
          lastItemKey = null;
          return;
        }
        emptyEl.style.display = 'none';

        function itemTitle(it) {
          return it.itemName + ' \\u00d7 ' + fmtGp(it.quantity) + ' \\u2014 ' + fmtGp(it.value) + ' gp';
        }

        var key = (state.selectedNpc || '') + '\\u0001' + state.itemSearch + '\\u0001' + state.itemSort + '\\u0001' +
          sorted.map(function (it) { return it.itemId != null ? it.itemId : it.itemName; }).join('|');
        if (key !== lastItemKey) {
          lastItemKey = key;
          listEl.innerHTML = sorted.map(function (it) {
            return '<div class="loot-item-box" title="' + escapeHtml(itemTitle(it)) + '">' +
              iconImg(it.icon, it.itemName, 'loot-item-box-icon') +
              '<div class="loot-item-box-qty">' + '\\u00d7' + fmtGpCompact(it.quantity) + '</div>' +
              '<div class="loot-item-box-value">' + fmtGpCompact(it.value) + ' gp</div>' +
            '</div>';
          }).join('');
          return;
        }

        // Same reasoning as renderNpcRow's reuse branch above: the item
        // set/order didn't change, so keep the existing icons, but
        // still refresh the qty/value text and title in case a later
        // poll bumped either for an item still sorted into this slot.
        var boxes = listEl.children;
        sorted.forEach(function (it, i) {
          var box = boxes[i];
          if (!box) return;
          box.title = itemTitle(it);
          var qtyEl = box.querySelector('.loot-item-box-qty');
          if (qtyEl) qtyEl.textContent = '\\u00d7' + fmtGpCompact(it.quantity);
          var valEl = box.querySelector('.loot-item-box-value');
          if (valEl) valEl.textContent = fmtGpCompact(it.value) + ' gp';
        });
      }

      document.getElementById('lootNpcRow').addEventListener('click', function (e) {
        var btn = e.target.closest('.loot-npc-box');
        if (!btn || !lastData) return;
        var name = btn.getAttribute('data-npc');
        state.selectedNpc = (state.selectedNpc === name) ? null : name;
        renderBarChart(lastData.hourlyBuckets || [], lastData.windowValue || 0, lastData.windowKills || 0, lastData.npcHourlyValues || {}, state.selectedNpc, lastData.windowNpcs || []);
        renderNpcRow(lastData.windowNpcs || []);
        renderItemList(currentItems());
      });

      document.getElementById('lootNpcSearch').addEventListener('input', function (e) {
        state.npcSearch = e.target.value;
        if (lastData) renderNpcRow(lastData.windowNpcs || []);
      });
      document.getElementById('lootNpcSortTabs').addEventListener('click', function (e) {
        var btn = e.target.closest('.loot-sort-tab');
        if (!btn || !lastData) return;
        state.npcSort = btn.getAttribute('data-sort');
        updateSortTabs('lootNpcSortTabs', state.npcSort);
        renderNpcRow(lastData.windowNpcs || []);
      });
      document.getElementById('lootItemSearch').addEventListener('input', function (e) {
        state.itemSearch = e.target.value;
        renderItemList(currentItems());
      });
      document.getElementById('lootItemSortTabs').addEventListener('click', function (e) {
        var btn = e.target.closest('.loot-sort-tab');
        if (!btn) return;
        state.itemSort = btn.getAttribute('data-sort');
        updateSortTabs('lootItemSortTabs', state.itemSort);
        renderItemList(currentItems());
      });
      updateSortTabs('lootNpcSortTabs', state.npcSort);
      updateSortTabs('lootItemSortTabs', state.itemSort);

      async function loadState() {
        var errorEl = document.getElementById('lootError');
        try {
          var res = await fetch('/api/players/me/loot');
          if (!res.ok) {
            errorEl.textContent = 'Could not load your loot. Please refresh.';
            errorEl.classList.add('show');
            return;
          }
          errorEl.classList.remove('show');
          var data = await res.json();
          lastData = data;

          // The selected NPC may have aged out of the window on a later
          // poll (its last kill in the last 24h just fell off the back
          // of the rolling window) -- fall back to "all sources" rather
          // than silently showing a flat/empty fill for it forever.
          var npcs = data.windowNpcs || [];
          if (state.selectedNpc && !npcs.some(function (n) { return n.sourceName === state.selectedNpc; })) {
            state.selectedNpc = null;
          }

          document.getElementById('lootEmptyMsg').style.display = 'none';
          document.getElementById('lootBody').style.display = '';
          renderBarChart(data.hourlyBuckets || [], data.windowValue || 0, data.windowKills || 0, data.npcHourlyValues || {}, state.selectedNpc, data.windowNpcs || []);
          renderNpcRow(npcs);
          renderItemList(currentItems());
        } catch (err) {
          errorEl.textContent = 'Something went wrong loading your loot.';
          errorEl.classList.add('show');
        }
      }

      loadState();
      setInterval(loadState, 10000);
    })();
    """
    return _shell(
        title="Loot Tracker — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )

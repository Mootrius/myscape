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

# Same cache-busting trick again, for the Mindmaps page's own stylesheet.
_MINDMAPS_CSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "css", "mindmaps.css"
)
try:
    _MINDMAPS_CSS_VERSION = int(os.path.getmtime(_MINDMAPS_CSS_PATH))
except OSError:
    _MINDMAPS_CSS_VERSION = 0


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
  <!-- Preloaded as early as possible in <head>, ahead of the
       stylesheet that actually declares @font-face for it (see
       myscape.css) -- the site's whole look rides on this one pixel
       font, set as the body's font-family there, and
       without a preload hint the browser doesn't discover it needs
       this file until it's parsed the CSS AND gone to paint text,
       by which point it's already painted once with a fallback
       system font and has to re-paint everything once the real font
       arrives -- that's the flash of the wrong font swapping to the
       right one on navigation. crossorigin is required here even
       though this is same-origin -- fonts are always fetched in
       anonymous CORS mode, and a preload missing it is treated as a
       different request from the @font-face one, so the browser
       fetches the file twice instead of reusing this one. -->
  <link rel="preload" href="/static/fonts/RuneScapePlain11.otf" as="font" type="font/otf" crossorigin />
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
_ICON_CLUE_SCROLL = "/static/img/icon-clue-scroll.png"


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
    mindmaps_card = (
        '<a href="/dashboard/mindmaps" style="display:block;color:inherit;text-decoration:none;">'
        + _dash_card(
            _ICON_CLUE_SCROLL,
            "Clue scroll",
            "Mindmaps",
            "Organize your goals into a mindmap -- start from one idea and branch "
            "out with parent, child, and sibling nodes, each recolorable to "
            "however you like to group things.",
        )
        + "</a>"
    )

    body = f"""
    <div class="dash-grid">
      {purchase_goals_card}
      {loot_tracker_card}
      {mindmaps_card}
    </div>
    """
    return _shell(title="Dashboard — myscape", player=player, body=body)


def render_signup() -> str:
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>SIGN UP</h2>
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
          <button class="primary" type="submit">SIGN UP</button>
        </form>
        <div class="auth-switch">Already have an account? <a href="/login">LOG IN</a></div>
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
        <h2>LOG IN</h2>
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
          <button class="primary" type="submit">LOG IN</button>
        </form>
        <div class="auth-switch">Don't have an account? <a href="/signup">SIGN UP</a></div>
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
        <span class="overlay-amount" id="pgCoinsAmount">0 gp</span>
      </div>
      <div class="overlay-progress">
        <div class="progress-track overlay-track"><div class="progress-fill" id="pgOverlayFill" style="width:0%;"></div></div>
      </div>
      <div class="overlay-side overlay-target">
        <div class="overlay-icon-wrap" id="pgIconTrigger" title="Set a display icon for this setup">
          <img class="overlay-icon" id="pgOverlayIconImg" alt="" style="display:none;" />
          <span class="overlay-icon-placeholder" id="pgOverlayIconPlaceholder">+</span>
        </div>
        <span class="overlay-amount" id="pgCostAmount">0 gp</span>
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

      // formatGp on its own, plus the ' gp' unit -- kept as its own
      // wrapper rather than baking the suffix into formatGp itself,
      // since formatGp is also used where a caller builds its own
      // surrounding text that already ends in " gp" on its own (see
      // pgNpAmount below, "1,234 / 5,678 gp") and would otherwise
      // double up ("5,678 gp gp"). Used for the coins counter and the
      // setup's total-cost/goal amount on the overlay bar (the two
      // tickNumberText calls below), and each still-to-purchase item's
      // own cost in the list.
      function formatGpLabel(n) {
        return formatGp(n) + ' gp';
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
        tickNumberText(document.getElementById('pgCoinsAmount'), PG.data.coins, formatGpLabel);
        tickNumberText(document.getElementById('pgCostAmount'), setup.totalCost, formatGpLabel);

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
            ? '<span class="gear-summary-row-cost">' + formatGpLabel(item.cost) + '</span>'
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
    see app/loot.py's build_loot_state), re-polled from scratch
    whenever the range button picks a new range.

    Everything on this page scopes together to whichever range is
    currently selected (see the range button up top -- presets plus a
    CUSTOM start/end date pair): the bar chart; the NPC panel
    below-left that lets a player click one NPC to see just that NPC's
    share of each bucket's loot filled in at the bottom of its bar (the
    bar's own full all-sources height still shows as an outline above
    it), searchable/sortable via its own search box and sort tabs; and
    the item panel below-right, which mirrors that same search/sort UI
    over either every item dropped by every NPC in the range (nothing
    selected) or just the selected NPC's own items -- see
    renderBarChart/renderNpcRow/renderItemList below, and
    build_loot_state in app/loot.py for the matching buckets/
    npcBucketValues/windowItems/npcItems shape."""
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
          <div class="loot-chart-range" id="lootChartRange">
            <button type="button" class="loot-range-btn" id="lootRangeBtn">
              <span id="lootRangeBtnLabel">24 HOURS</span> <span class="loot-range-caret">&darr;</span>
            </button>
            <div class="loot-range-menu" id="lootRangeMenu" style="display:none;">
              <button type="button" class="loot-range-option" data-range="1y">1 YEAR</button>
              <button type="button" class="loot-range-option" data-range="6m">6 MONTHS</button>
              <button type="button" class="loot-range-option" data-range="3m">3 MONTHS</button>
              <button type="button" class="loot-range-option" data-range="1m">1 MONTH</button>
              <button type="button" class="loot-range-option" data-range="1w">1 WEEK</button>
              <button type="button" class="loot-range-option active" data-range="24h">24 HOURS</button>
              <button type="button" class="loot-range-option" data-range="custom">CUSTOM</button>
              <div class="loot-range-custom" id="lootRangeCustom" style="display:none;">
                <label class="loot-range-custom-field">Start
                  <input type="date" id="lootRangeStart" />
                </label>
                <label class="loot-range-custom-field">End
                  <input type="date" id="lootRangeEnd" />
                </label>
                <button type="button" class="loot-range-apply" id="lootRangeApply">Apply</button>
              </div>
            </div>
          </div>
          <div class="loot-chart-title" id="lootChartTitle">ALL NPCs</div>
          <div class="loot-chart-stats">
            <div class="loot-chart-kills" id="lootChartKills">0 kc</div>
            <div class="loot-chart-total" id="lootChartTotal">0 gp</div>
          </div>
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
            No NPC kills in this range yet.
          </p>
          <div class="loot-npc-row" id="lootNpcRow"></div>
        </div>
        <div class="loot-panel">
          <div class="loot-panel-controls">
            <input type="text" class="loot-search" id="lootItemSearch" placeholder="Search for an item" autocomplete="off" />
            {_sort_tabs("lootItemSortTabs", "Qty")}
          </div>
          <p class="loot-column-empty" id="lootItemEmpty" style="display:none;">
            No items dropped in this range yet.
          </p>
          <div class="loot-item-list" id="lootItemList"></div>
        </div>
      </div>
    </div>
    """
    script = """
    (function () {
      var state = {
        selectedNpc: null, npcSort: 'high', npcSearch: '', itemSort: 'high', itemSearch: '',
        rangeKey: '24h', customStart: null, customEnd: null,
      };
      var lastData = null;

      var RANGE_LABELS = {
        '24h': '24 HOURS', '1w': '1 WEEK', '1m': '1 MONTH',
        '3m': '3 MONTHS', '6m': '6 MONTHS', '1y': '1 YEAR', 'custom': 'CUSTOM',
      };

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

      // A bucket's x-axis tick, formatted per the range's own
      // granularity (see _bucket_plan in app/loot.py, which picks
      // granularity from the selected range's span) -- hourly still
      // shows a clock time (unchanged from the original 24-hour-only
      // chart), daily/weekly a short date, monthly just the month.
      function fmtBucketLabel(granularity, isoString) {
        if (!isoString) return '';
        var d = new Date(isoString);
        if (granularity === 'hourly') return d.toLocaleTimeString('en-US', { hour: 'numeric' });
        if (granularity === 'monthly') return d.toLocaleDateString('en-US', { month: 'short' });
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      }

      // Whether an ISO timestamp is close enough to this moment to
      // treat as "now" -- used to decide whether the chart's last bar
      // gets labeled "NOW" (true for every preset, which always end at
      // the moment the page asked for them) or its own real date/time
      // (a CUSTOM range whose end isn't today would otherwise
      // mislabel its last bucket as happening right now).
      function isNowish(isoString) {
        if (!isoString) return false;
        return Math.abs(new Date(isoString).getTime() - Date.now()) < 5 * 60 * 1000;
      }

      // 'YYYY-MM-DD' (a <input type="date"> value) -> a short display
      // date, for the range button's own label once a CUSTOM range is
      // applied.
      function fmtDateShort(isoDate) {
        if (!isoDate) return '';
        var d = new Date(isoDate + 'T00:00:00');
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      }

      function rangeButtonLabel() {
        if (state.rangeKey === 'custom' && state.customStart && state.customEnd) {
          return fmtDateShort(state.customStart) + ' \\u2013 ' + fmtDateShort(state.customEnd);
        }
        return RANGE_LABELS[state.rangeKey] || RANGE_LABELS['24h'];
      }

      // The OSRS Wiki's article title for an item is (almost always)
      // just its in-game name -- the same name this page already gets
      // back as itemName -- with spaces URL-encoded, same as this
      // file's own icon URLs already do server-side (see
      // item_icon_url/ICON_PATH_BASE in app/purchase_goals.py, which
      // percent-encodes the icon filename the same way); MediaWiki
      // normalizes a %20 the same as an underscore, so this needs no
      // separate space-to-underscore step. A name that isn't actually
      // an article title (a rare mismatch) lands on the wiki's own
      // search results for it rather than a dead link, since
      // Special:Search redirects straight to an exact-title match same
      // as visiting the article directly would.
      function wikiItemUrl(name) {
        return 'https://oldschool.runescape.wiki/w/Special:Search?search=' + encodeURIComponent(name || '') + '&go=Go';
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

      // Bar chart over the currently-selected range, bucketed at
      // whatever granularity that range's span calls for (see
      // _bucket_plan in app/loot.py -- hourly for a short range like
      // the original 24-hour-only chart, coarser for a longer one),
      // oldest on the left -- ported from the original single-user
      // tool's Loot Tracker chart (renderVorkathBarChart), summed
      // across every source by default. When an NPC is selected
      // (state.selectedNpc, set by renderNpcRow's click handler below)
      // each bar instead shows two layers: a full-height outline at the
      // bucket's own total value (so the scale/shape of the whole chart
      // never changes), with a solid fill at the bottom sized to just
      // that NPC's share of the same bucket. maxValue is always derived
      // from the total buckets, never the selected NPC's own values, so
      // the axis stays put when switching NPCs. Reuses the existing
      // bar-col elements when the bucket count hasn't changed (the same
      // range keeps the same bucket count on every 10s poll) so the CSS
      // height transition actually animates between polls instead of
      // snapping -- a range change does change the bucket count, which
      // is exactly when a full rebuild (and a fresh grow-in) is right.
      function renderBarChart(buckets, windowValue, windowKills, npcBucketValues, selectedNpc, windowNpcs, granularity, rangeEnd) {
        buckets = buckets || [];
        npcBucketValues = npcBucketValues || {};
        granularity = granularity || 'hourly';
        // With an NPC selected, the header's gp/kc numbers switch to
        // just that NPC's own totals (already sitting right on its
        // windowNpcs entry -- value/killCount, the same numbers its own
        // NPC box shows) instead of the whole range's -- otherwise
        // selecting Guard would still show every other NPC's loot
        // summed in up top while the chart itself only fills in Guard's
        // share, which reads as a mismatch.
        var selectedEntry = selectedNpc && windowNpcs
          ? windowNpcs.filter(function (n) { return n.sourceName === selectedNpc; })[0]
          : null;
        var headerValue = selectedEntry ? selectedEntry.value : windowValue;
        var headerKills = selectedEntry ? selectedEntry.killCount : windowKills;
        document.getElementById('lootChartTotal').textContent = fmtGp(headerValue) + ' gp';
        document.getElementById('lootChartKills').textContent = (headerKills || 0).toLocaleString('en-US') + ' kc';
        // A selected NPC's own name is shown in ALL CAPS (e.g.
        // "ZULRAH") -- uppercased here in JS rather than via a CSS
        // text-transform on .loot-chart-title, since that would also
        // force the "ALL NPCs" fallback into "ALL NPCS", capitalizing
        // the "s" it's deliberately meant to keep lowercase.
        document.getElementById('lootChartTitle').textContent = selectedNpc ? selectedNpc.toUpperCase() : 'ALL NPCs';

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

        var selectedValues = selectedNpc ? (npcBucketValues[selectedNpc] || buckets.map(function () { return 0; })) : null;

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

        // Labeling every single bucket would be unreadable once there
        // are more than a handful -- aim for roughly one label every
        // ~1/7th of the chart's width (24 hourly buckets: every 4th,
        // same spacing the original 24-hour-only chart always used;
        // scales the same way for whatever bucket count the selected
        // range's granularity produced). The last bucket gets "NOW"
        // only when the range's own end is actually close to now (see
        // isNowish) -- true for every preset, but not necessarily for
        // a CUSTOM range picked in the past.
        var labelStep = Math.max(1, Math.ceil(buckets.length / 7));
        var endIsNow = isNowish(rangeEnd);
        document.getElementById('lootBarXLabels').innerHTML = buckets.map(function (b, i) {
          if (i === buckets.length - 1 && endIsNow) return '<div class="loot-bar-x-label now">NOW</div>';
          var label = (i % labelStep === 0) ? fmtBucketLabel(granularity, b.start) : '';
          return '<div class="loot-bar-x-label">' + label + '</div>';
        }).join('');
      }

      // The clickable "By NPC" row -- one box per NPC killed in the
      // selected range, each toggling state.selectedNpc (clicking the
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
          emptyEl.textContent = 'No NPC kills in this range yet.';
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
          emptyEl.textContent = 'No items dropped in this range yet.';
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
            return '<a class="loot-item-box" href="' + wikiItemUrl(it.itemName) + '" target="_blank" rel="noopener" title="' + escapeHtml(itemTitle(it)) + '">' +
              iconImg(it.icon, it.itemName, 'loot-item-box-icon') +
              '<div class="loot-item-box-qty">' + '\\u00d7' + fmtGpCompact(it.quantity) + '</div>' +
              '<div class="loot-item-box-value">' + fmtGpCompact(it.value) + ' gp</div>' +
            '</a>';
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

      function rerenderChart(data) {
        renderBarChart(
          data.buckets || [], data.windowValue || 0, data.windowKills || 0,
          data.npcBucketValues || {}, state.selectedNpc, data.windowNpcs || [],
          data.granularity, data.rangeEnd
        );
      }

      document.getElementById('lootNpcRow').addEventListener('click', function (e) {
        var btn = e.target.closest('.loot-npc-box');
        if (!btn || !lastData) return;
        var name = btn.getAttribute('data-npc');
        state.selectedNpc = (state.selectedNpc === name) ? null : name;
        rerenderChart(lastData);
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

      // ---- Range button (presets + CUSTOM date pair) -----------------------
      //
      // Picking a preset applies (and reloads) immediately; picking
      // CUSTOM instead just reveals the two date inputs + Apply button
      // inline in the same menu -- nothing changes until Apply is
      // clicked with both dates filled in, same as how a browser's own
      // date pickers don't commit until you're done with them.

      function updateRangeMenuActive() {
        var opts = document.querySelectorAll('#lootRangeMenu .loot-range-option');
        for (var i = 0; i < opts.length; i++) {
          opts[i].classList.toggle('active', opts[i].getAttribute('data-range') === state.rangeKey);
        }
        document.getElementById('lootRangeBtnLabel').textContent = rangeButtonLabel();
      }

      function closeRangeMenu() {
        document.getElementById('lootRangeMenu').style.display = 'none';
        document.getElementById('lootRangeCustom').style.display = 'none';
      }

      document.getElementById('lootRangeBtn').addEventListener('click', function () {
        var menu = document.getElementById('lootRangeMenu');
        var opening = menu.style.display === 'none';
        menu.style.display = opening ? 'flex' : 'none';
        if (!opening) document.getElementById('lootRangeCustom').style.display = 'none';
      });
      document.addEventListener('click', function (e) {
        var wrap = document.getElementById('lootChartRange');
        if (wrap && !wrap.contains(e.target)) closeRangeMenu();
      });
      document.getElementById('lootRangeMenu').addEventListener('click', function (e) {
        var opt = e.target.closest('.loot-range-option');
        if (!opt) return;
        var key = opt.getAttribute('data-range');
        if (key === 'custom') {
          var startInput = document.getElementById('lootRangeStart');
          var endInput = document.getElementById('lootRangeEnd');
          if (!startInput.value || !endInput.value) {
            var today = new Date();
            var weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
            var toIsoDate = function (d) { return d.toISOString().slice(0, 10); };
            if (!startInput.value) startInput.value = state.customStart || toIsoDate(weekAgo);
            if (!endInput.value) endInput.value = state.customEnd || toIsoDate(today);
          }
          document.getElementById('lootRangeCustom').style.display = 'flex';
          return;
        }
        state.rangeKey = key;
        state.selectedNpc = null;
        closeRangeMenu();
        updateRangeMenuActive();
        loadState();
      });
      document.getElementById('lootRangeApply').addEventListener('click', function () {
        var startVal = document.getElementById('lootRangeStart').value;
        var endVal = document.getElementById('lootRangeEnd').value;
        if (!startVal || !endVal) return;
        state.rangeKey = 'custom';
        state.customStart = startVal;
        state.customEnd = endVal;
        state.selectedNpc = null;
        closeRangeMenu();
        updateRangeMenuActive();
        loadState();
      });
      updateRangeMenuActive();

      function lootUrl() {
        var params = new URLSearchParams();
        params.set('range', state.rangeKey);
        if (state.rangeKey === 'custom' && state.customStart && state.customEnd) {
          params.set('start', state.customStart);
          params.set('end', state.customEnd);
        }
        return '/api/players/me/loot?' + params.toString();
      }

      async function loadState() {
        var errorEl = document.getElementById('lootError');
        try {
          var res = await fetch(lootUrl());
          if (!res.ok) {
            errorEl.textContent = 'Could not load your loot. Please refresh.';
            errorEl.classList.add('show');
            return;
          }
          errorEl.classList.remove('show');
          var data = await res.json();
          lastData = data;

          // The selected NPC may have aged out of the range on a later
          // poll (its last kill in range just fell off the back of a
          // rolling preset like 24 HOURS) -- fall back to "all sources"
          // rather than silently showing a flat/empty fill for it
          // forever.
          var npcs = data.windowNpcs || [];
          if (state.selectedNpc && !npcs.some(function (n) { return n.sourceName === state.selectedNpc; })) {
            state.selectedNpc = null;
          }

          document.getElementById('lootEmptyMsg').style.display = 'none';
          document.getElementById('lootBody').style.display = '';
          rerenderChart(data);
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


def render_mindmaps(player: Player) -> str:
    """The Mindmaps page -- brand new feature, no Maintrius equivalent to
    port. Same overall shape as Purchase Goals/Loot Tracker: a static
    HTML skeleton, everything below it rendered client-side from one
    polled-once JSON payload (GET /api/mindmaps, see app/mindmaps.py's
    build_mindmaps_state), so every mutation endpoint can just hand back
    the freshly recomputed state and let the same render() redraw
    everything. Unlike those two pages, there's no background poll --
    nothing external (no RuneLite plugin, no wiki prices) ever changes a
    mindmap out from under the player, so there's nothing to poll for
    that their own last action here hasn't already applied.

    The canvas (pan/zoom, node layout, the elbow connector lines) is
    plain positioned <div>s plus one <svg> overlay, laid out by a small
    from-scratch tree-layout algorithm in the script below -- see
    computeLayout there for the how and why (fixed node width/height,
    matching mindmaps.css exactly, so the whole layout is arithmetic
    with no DOM-measurement pass needed)."""
    extra_head = f'<link rel="stylesheet" href="/static/css/mindmaps.css?v={_MINDMAPS_CSS_VERSION}" />'
    body = """
    <h2 class="page-title">Mindmaps</h2>
    <div class="auth-error" id="mmError"></div>
    <div class="mm-name-form" id="mmNameForm" style="display:none;">
      <input type="text" id="mmNameInput" placeholder="Mindmap name" maxlength="60" />
      <button class="primary mm-name-form-save" id="mmNameSave" type="button">Save</button>
      <button class="btn-secondary" id="mmNameCancel" type="button">Cancel</button>
    </div>
    <div class="mm-empty-wrap" id="mmEmptyWrap">
      <p class="mm-empty" id="mmEmptyMsg">Loading&hellip;</p>
      <button class="primary" id="mmCreateFirstBtn" type="button" style="display:none;">Create your first mindmap</button>
    </div>
    <div id="mmBody" style="display:none;">
      <div class="mm-header">
        <div class="mm-menu-wrap">
          <button class="mm-switch-btn" id="mmSwitchBtn" type="button" title="Switch or manage mindmaps">
            <span class="mm-switch-name" id="mmSwitchName"></span>
            <span class="mm-switch-caret">&#9662;</span>
          </button>
          <div class="mm-menu" id="mmMenu" style="display:none;"></div>
        </div>
      </div>
      <div class="mm-canvas" id="mmCanvas">
        <div class="mm-zoom-controls">
          <button type="button" id="mmZoomIn" title="Zoom in">+</button>
          <button type="button" id="mmZoomOut" title="Zoom out">&minus;</button>
          <button type="button" id="mmZoomFit" title="Zoom to fit">Fit</button>
          <button type="button" id="mmZoomReset" title="Reset view">&#8635;</button>
        </div>
        <div class="mm-world" id="mmWorld">
          <svg class="mm-lines" id="mmLines"></svg>
          <div id="mmNodesLayer"></div>
        </div>
      </div>
    </div>
    """
    script = """
    (function () {
      // Matches mindmaps.css's .mm-node width/height exactly -- the
      // whole layout below is pure arithmetic on these constants (no
      // DOM measurement pass), so a mismatch here would show up as
      // connector lines not quite meeting a node's actual edges.
      var NODE_WIDTH = 160;
      var NODE_HEIGHT = 46;
      var COL_WIDTH = 190;   // horizontal spacing between sibling leaf columns
      var ROW_HEIGHT = 110;  // vertical spacing between depth levels
      var MARGIN = 60;       // breathing room around the whole tree inside the world

      // Mirrors NODE_COLORS in app/mindmaps.py -- the fixed palette a
      // node's color can be, in the order the per-node color popover
      // shows them.
      var NODE_COLORS = ['gray', 'red', 'orange', 'yellow', 'green', 'blue', 'purple', 'white'];

      var MM = {
        data: null,
        activeMindmapId: null,
        // The "anchor" node -- the last one clicked (plain or shift) --
        // used to place the popover/button below and, when it's the
        // only node selected, as the contenteditable target. Always
        // one of the ids currently in multiSelectIds (see selectNode/
        // extendMultiSelect/pruneMultiSelect, which all keep the two in
        // sync).
        selectedNodeId: null,
        focusNodeId: null, // one-shot: focus + select this node's text on the next render
        // Every currently-selected node -- a plain click replaces this
        // whole set with just the clicked node; shift-click adds to (or
        // removes from) whatever's already selected instead of starting
        // over, so selecting more than one always starts with a normal
        // click on the first node, then shift-clicks for the rest. All
        // of them get the same gold "selected" ring (see renderCanvas)
        // -- there's no visually separate "multi-select mode" anymore.
        multiSelectIds: new Set(),
        nameFormMode: null, // 'new' | 'rename' | null
        pan: { x: 0, y: 0 },
        zoom: 1,
        lastLayout: null, // set by renderCanvas, read by recenterOnNode/zoomToFit
      };

      // Same "remember what was open across a reload" convenience as
      // Purchase Goals' own ACTIVE_SETUP_STORAGE_KEY (see
      // render_purchase_goals in app/pages.py) -- per-browser, not
      // per-player, for the same reasons documented there.
      var ACTIVE_MINDMAP_STORAGE_KEY = 'myscape:mindmaps:activeMindmapId';
      function loadStoredActiveMindmapId() {
        try { return localStorage.getItem(ACTIVE_MINDMAP_STORAGE_KEY); } catch (e) { return null; }
      }
      function setActiveMindmapId(id) {
        MM.activeMindmapId = id;
        try {
          if (id) localStorage.setItem(ACTIVE_MINDMAP_STORAGE_KEY, id);
          else localStorage.removeItem(ACTIVE_MINDMAP_STORAGE_KEY);
        } catch (e) { /* ignore -- see comment above */ }
      }

      function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
          return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
      }

      function showError(msg) {
        var el = document.getElementById('mmError');
        if (!msg) { el.classList.remove('show'); el.textContent = ''; return; }
        el.textContent = msg;
        el.classList.add('show');
      }

      async function apiCall(url, options) {
        try {
          const res = await fetch(url, options);
          const data = await res.json().catch(function () { return {}; });
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

      function activeMindmap() {
        if (!MM.data || !MM.activeMindmapId) return null;
        return MM.data.mindmaps.find(function (m) { return m.id === MM.activeMindmapId; }) || null;
      }

      function selectedNode() {
        var mm = activeMindmap();
        if (!mm || !MM.selectedNodeId) return null;
        return mm.nodes.find(function (n) { return n.id === MM.selectedNodeId; }) || null;
      }

      // ---- Tree layout ----------------------------------------------------
      // A from-scratch top-down tree layout (no library) -- deliberately
      // simple over a "correct" Reingold-Tilford implementation: every
      // leaf gets its own column (so subtrees can never overlap), and
      // each parent centers over the span of its own immediate children
      // (the midpoint between the first and last, not an average across
      // all of them, which is what keeps a parent visually centered over
      // an asymmetric set of children the same way a family tree diagram
      // usually reads). Good enough for how these trees actually grow;
      // worth revisiting if a very lopsided tree ever looks obviously off.
      function computeLayout(nodes) {
        var childrenMap = new Map();
        nodes.forEach(function (n) {
          if (!childrenMap.has(n.parentId)) childrenMap.set(n.parentId, []);
          childrenMap.get(n.parentId).push(n);
        });
        childrenMap.forEach(function (list) { list.sort(function (a, b) { return a.order - b.order; }); });

        var root = nodes.find(function (n) { return n.parentId === null; });
        var positions = {};
        var leafCounter = { value: 0 };
        var maxDepth = 0;

        function walk(node, depth) {
          maxDepth = Math.max(maxDepth, depth);
          var kids = childrenMap.get(node.id) || [];
          var unitX;
          if (kids.length === 0) {
            unitX = leafCounter.value;
            leafCounter.value += 1;
          } else {
            var childXs = kids.map(function (c) { return walk(c, depth + 1); });
            unitX = (childXs[0] + childXs[childXs.length - 1]) / 2;
          }
          positions[node.id] = { x: unitX * COL_WIDTH + MARGIN, y: depth * ROW_HEIGHT + MARGIN, depth: depth };
          return unitX;
        }
        if (root) walk(root, 0);

        // A shared-child node (see extraParentIds -- the shift-click
        // multi-select's "add a shared child below several nodes")
        // structurally hangs off just ONE of its parents (its own
        // parentId, used above like any other child for column
        // assignment), but it should visually read as sitting centered
        // under the WHOLE group of nodes it's linked to. Nudge its x to
        // the average center of every linked parent (parentId plus
        // extraParentIds) that's still actually in the tree -- this only
        // moves that one node's own rendered position; it can't disturb
        // any other node's column/slot, since leafCounter bookkeeping
        // above is already done by the time this runs.
        //
        // That average-of-parents target has no idea what else already
        // occupies that row, though -- if the shared child's primary
        // parent has OTHER (ordinary) children too, or any other node
        // just happens to land nearby, the naive nudge above can walk
        // the shared child right on top of it (e.g. add a shared child
        // below A+B, then add a second, ordinary child under A -- the
        // shared child's "centered between A and B" target can collide
        // with that new sibling's own column). So the nudge is clamped
        // against every other same-row (same depth) node's CURRENT
        // position, keeping at least one full column's width between
        // centers -- same minimum spacing the grid already guarantees
        // between any two ordinary leaf columns -- and only walks as
        // far toward the average as that leaves room for. If two
        // neighbors box it in on both sides too tightly to fit at all
        // (packed row), it falls back to its own pre-nudge column
        // rather than force an overlap.
        nodes.forEach(function (n) {
          if (!n.extraParentIds || !n.extraParentIds.length) return;
          var linkedIds = [n.parentId].concat(n.extraParentIds);
          var centers = [];
          linkedIds.forEach(function (pid) {
            var p = positions[pid];
            if (p) centers.push(p.x + NODE_WIDTH / 2);
          });
          if (!centers.length) return;
          var avgCenter = centers.reduce(function (a, b) { return a + b; }, 0) / centers.length;

          var ownDepth = positions[n.id].depth;
          var minAllowed = -Infinity, maxAllowed = Infinity;
          Object.keys(positions).forEach(function (otherId) {
            if (otherId === n.id) return;
            var otherPos = positions[otherId];
            if (otherPos.depth !== ownDepth) return;
            var otherCenter = otherPos.x + NODE_WIDTH / 2;
            if (otherCenter <= avgCenter) {
              minAllowed = Math.max(minAllowed, otherCenter + COL_WIDTH);
            } else {
              maxAllowed = Math.min(maxAllowed, otherCenter - COL_WIDTH);
            }
          });

          var clampedCenter = avgCenter;
          if (minAllowed > maxAllowed) {
            // No room to fit anywhere near the average without
            // overlapping a neighbor on both sides -- stay put at the
            // node's own (collision-free, by construction) column
            // instead of forcing an overlap.
            clampedCenter = positions[n.id].x + NODE_WIDTH / 2;
          } else {
            if (clampedCenter < minAllowed) clampedCenter = minAllowed;
            if (clampedCenter > maxAllowed) clampedCenter = maxAllowed;
          }
          positions[n.id].x = clampedCenter - NODE_WIDTH / 2;
        });

        return {
          positions: positions,
          childrenMap: childrenMap,
          root: root,
          worldWidth: Math.max(1, leafCounter.value) * COL_WIDTH + MARGIN * 2,
          worldHeight: (maxDepth + 1) * ROW_HEIGHT + MARGIN * 2,
        };
      }

      // ---- Pan/zoom ---------------------------------------------------

      // .mm-world carries a CSS transition on `transform` (see
      // mindmaps.css) so every zoom change -- the +/-/fit/reset
      // buttons, the wheel, all of which end up calling applyTransform
      // through setZoom/zoomToFit/recenterOnNode -- animates smoothly
      // instead of snapping. Pan-dragging below calls applyTransform
      // too (every pointermove while dragging), and MUST stay instant
      // -- a smoothed drag would visibly lag behind the cursor -- so
      // the pan handlers toggle transitionDuration to '0s' for the
      // duration of a drag and clear it again afterward, leaving the
      // CSS transition's own duration in charge the rest of the time.
      var mmWorldEl = document.getElementById('mmWorld');
      function applyTransform() {
        mmWorldEl.style.transform =
          'translate(' + MM.pan.x + 'px, ' + MM.pan.y + 'px) scale(' + MM.zoom + ')';
      }

      // Zooms toward/away from a fixed screen point -- (originX, originY)
      // in canvas-viewport pixels, defaulting to the viewport's own
      // center when omitted (both the +/-/reset buttons and the wheel
      // listener below call it with no origin, so every zoom trigger
      // zooms around the center of the current view, not a fixed
      // top-left-anchored scale). Standard "zoom around a point" math:
      // find the world-space point currently sitting under (originX,
      // originY), change the zoom, then re-solve pan so that same
      // world point still lands under (originX, originY) afterward --
      // that's what makes the zoom feel anchored there instead of
      // drifting the view.
      function setZoom(z, originX, originY) {
        var canvas = document.getElementById('mmCanvas');
        if (originX == null) originX = canvas.clientWidth / 2;
        if (originY == null) originY = canvas.clientHeight / 2;
        var newZoom = Math.max(0.4, Math.min(2, z));
        if (newZoom === MM.zoom) return;
        var worldX = (originX - MM.pan.x) / MM.zoom;
        var worldY = (originY - MM.pan.y) / MM.zoom;
        MM.zoom = newZoom;
        MM.pan.x = originX - worldX * MM.zoom;
        MM.pan.y = originY - worldY * MM.zoom;
        applyTransform();
      }

      // Pans the canvas so the given node sits centered in the current
      // viewport, at the current zoom -- uses MM.lastLayout (set by the
      // most recent renderCanvas), so this only makes sense to call
      // right after a render.
      function recenterOnNode(nodeId) {
        var layout = MM.lastLayout;
        var pos = layout && layout.positions[nodeId];
        if (!pos) return;
        var canvas = document.getElementById('mmCanvas');
        var viewW = canvas.clientWidth, viewH = canvas.clientHeight;
        var centerX = pos.x + NODE_WIDTH / 2, centerY = pos.y + NODE_HEIGHT / 2;
        MM.pan.x = viewW / 2 - centerX * MM.zoom;
        MM.pan.y = viewH / 2 - centerY * MM.zoom;
        applyTransform();
      }

      function resetView() {
        var mm = activeMindmap();
        MM.zoom = 1;
        if (mm && mm.nodes.length) recenterOnNode(mm.nodes.find(function (n) { return n.parentId === null; }).id);
        else applyTransform();
      }

      // Fits the WHOLE tree's bounding box inside the current viewport
      // (as opposed to resetView, which always centers on just the
      // root at a fixed zoom of 1) -- picks whichever of width/height
      // is the tighter constraint, clamped to the same 0.4-2 zoom
      // range as everything else, then centers the fitted box in the
      // viewport. Uses the actual tight bounding box of the node
      // positions themselves (not layout.worldWidth/worldHeight) --
      // those two are sized for computeLayout's own arithmetic
      // convenience and end up with more empty margin past the last
      // column/row than before the first one, so centering THAT box
      // visibly drags the real content off-center (left/up) instead
      // of centering what's actually on screen.
      function zoomToFit() {
        var layout = MM.lastLayout;
        if (!layout) return;
        var ids = Object.keys(layout.positions);
        if (!ids.length) return;
        var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        ids.forEach(function (id) {
          var pos = layout.positions[id];
          minX = Math.min(minX, pos.x);
          minY = Math.min(minY, pos.y);
          maxX = Math.max(maxX, pos.x + NODE_WIDTH);
          maxY = Math.max(maxY, pos.y + NODE_HEIGHT);
        });
        var boxW = maxX - minX, boxH = maxY - minY;
        var canvas = document.getElementById('mmCanvas');
        var viewW = canvas.clientWidth, viewH = canvas.clientHeight;
        var pad = 40; // breathing room inside the viewport edges
        var availW = Math.max(1, viewW - pad * 2), availH = Math.max(1, viewH - pad * 2);
        var z = Math.max(0.4, Math.min(2, Math.min(availW / boxW, availH / boxH)));
        MM.zoom = z;
        var boxCenterX = minX + boxW / 2, boxCenterY = minY + boxH / 2;
        MM.pan.x = viewW / 2 - boxCenterX * z;
        MM.pan.y = viewH / 2 - boxCenterY * z;
        applyTransform();
      }

      // If a node's text is mid-edit (its label is focused and
      // contenteditable), blur it so the pending edit commits before
      // whatever's about to happen -- deselecting by clicking the
      // canvas, switching mindmaps, etc. -- rebuilds or hides it.
      // Without this, a click that both ends an edit AND changes
      // selection/mindmap in the same gesture could silently drop the
      // unsaved text.
      function commitActiveLabelIfEditing() {
        var el = document.activeElement;
        if (el && el.isContentEditable && el.getAttribute && el.getAttribute('data-role') === 'label') el.blur();
      }

      var canvasEl = document.getElementById('mmCanvas');
      var panState = { active: false, startX: 0, startY: 0, startPanX: 0, startPanY: 0, moved: false };
      canvasEl.addEventListener('pointerdown', function (e) {
        commitActiveLabelIfEditing();
        // A node's own handler owns clicks on it (selection), and the
        // zoom control buttons need their native click to fire
        // normally -- setPointerCapture below would otherwise redirect
        // that click's events to the canvas instead, since they're
        // also DOM descendants of it, silently swallowing the button
        // press.
        if (e.target.closest('.mm-node') || e.target.closest('.mm-zoom-controls')) return;
        panState.active = true;
        panState.moved = false;
        panState.startX = e.clientX;
        panState.startY = e.clientY;
        panState.startPanX = MM.pan.x;
        panState.startPanY = MM.pan.y;
        canvasEl.setPointerCapture(e.pointerId);
        canvasEl.classList.add('panning');
        mmWorldEl.style.transitionDuration = '0s'; // dragging must track the cursor 1:1, never smoothed
      });
      canvasEl.addEventListener('pointermove', function (e) {
        if (!panState.active) return;
        var dx = e.clientX - panState.startX, dy = e.clientY - panState.startY;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) panState.moved = true;
        MM.pan.x = panState.startPanX + dx;
        MM.pan.y = panState.startPanY + dy;
        applyTransform();
      });
      function endPan() {
        if (!panState.active) return;
        panState.active = false;
        canvasEl.classList.remove('panning');
        mmWorldEl.style.transitionDuration = ''; // hand back to .mm-world's own smooth-zoom transition
        if (!panState.moved) selectNode(null); // a plain click on empty canvas deselects
      }
      canvasEl.addEventListener('pointerup', endPan);
      canvasEl.addEventListener('pointercancel', endPan);
      canvasEl.addEventListener('wheel', function (e) {
        e.preventDefault();
        setZoom(MM.zoom + (e.deltaY < 0 ? 0.12 : -0.12));
      }, { passive: false });

      document.getElementById('mmZoomIn').addEventListener('click', function () { setZoom(MM.zoom + 0.15); });
      document.getElementById('mmZoomOut').addEventListener('click', function () { setZoom(MM.zoom - 0.15); });
      document.getElementById('mmZoomFit').addEventListener('click', zoomToFit);
      document.getElementById('mmZoomReset').addEventListener('click', resetView);

      // ---- Node selection + click delegation ---------------------------

      // A plain (non-shift) click/select REPLACES the whole selection
      // with just this one node (or clears everything if id is null --
      // the canvas's own click-to-deselect) -- this is also how a
      // multi-selection collapses back down to a single node. Selecting
      // exactly what's already selected is a deliberate no-op (no
      // re-render) -- otherwise a click meant to place the text cursor
      // somewhere inside an already-editable node's label would blow
      // away and rebuild that very DOM node out from under the
      // browser's own click-to-focus handling, losing the caret
      // position it was just about to set.
      function selectNode(id) {
        var alreadyJustThis = id === MM.selectedNodeId && (
          (id === null && MM.multiSelectIds.size === 0) ||
          (id !== null && MM.multiSelectIds.size === 1 && MM.multiSelectIds.has(id))
        );
        if (alreadyJustThis) return;
        MM.selectedNodeId = id;
        MM.multiSelectIds = new Set(id ? [id] : []);
        MM.focusNodeId = id; // focus + select this node's text on the next render, if any
        render();
      }

      // Shift-clicking a node ADDS it to (or, if it's already in there,
      // removes it from) whatever's currently selected -- selectNode
      // above is what starts a selection (even a shift-click on an
      // otherwise-empty selection just becomes the same as a plain
      // click), this only ever extends or trims one already in
      // progress. The most recently touched node becomes the new
      // anchor (see MM.selectedNodeId's own comment) so the popover/
      // button always tracks wherever the player's attention last was;
      // removing the current anchor falls back to whatever's left.
      // Never auto-focuses text editing -- typing while several nodes
      // are marked would be ambiguous about which one it's for.
      //
      // A shared child can only connect nodes at the same vertical
      // level (see _depth/add_shared_child in app/mindmaps.py, which
      // enforces this same rule server-side) -- adding a node at a
      // different depth than what's already selected is refused here
      // rather than only failing later when "Add shared child" is
      // clicked, using MM.lastLayout's own per-node depth (set by the
      // most recent renderCanvas) rather than re-walking the tree.
      // This is a silent no-op (no error message) -- the mismatched
      // node just doesn't get added to the selection.
      function extendMultiSelect(id) {
        if (MM.multiSelectIds.has(id)) {
          MM.multiSelectIds.delete(id);
          if (MM.selectedNodeId === id) {
            var remaining = Array.from(MM.multiSelectIds);
            MM.selectedNodeId = remaining.length ? remaining[remaining.length - 1] : null;
          }
          MM.focusNodeId = null;
          render();
          return;
        }
        var layout = MM.lastLayout;
        if (layout && MM.selectedNodeId) {
          var anchorPos = layout.positions[MM.selectedNodeId];
          var newPos = layout.positions[id];
          if (anchorPos && newPos && anchorPos.depth !== newPos.depth) {
            return;
          }
        }
        MM.multiSelectIds.add(id);
        MM.selectedNodeId = id;
        MM.focusNodeId = null;
        render();
      }

      document.getElementById('mmNodesLayer').addEventListener('pointerdown', function (e) {
        var el = e.target.closest('.mm-node');
        if (!el) return;
        commitActiveLabelIfEditing();
        e.stopPropagation();
        // Edge buttons and the node popover (color swatches, or the
        // "add shared child" button) handle themselves (via the click
        // delegation below) -- only a plain click on the node itself
        // (its body/label) selects it.
        if (e.target.closest('.mm-edge-btn') || e.target.closest('[data-role="popover"]')) return;
        if (e.shiftKey) { extendMultiSelect(el.getAttribute('data-node-id')); return; }
        selectNode(el.getAttribute('data-node-id'));
      });

      // A second delegation, on 'click' rather than 'pointerdown' --
      // stopPropagation() above only stops the pointerdown from
      // reaching the canvas's own pan-start handler, it doesn't
      // suppress the click event the browser fires afterward, so a
      // button's own click still arrives here normally.
      document.getElementById('mmNodesLayer').addEventListener('click', function (e) {
        var edgeBtn = e.target.closest('.mm-edge-btn');
        if (edgeBtn) {
          var nodeEl = edgeBtn.closest('.mm-node');
          addNodeRelativeTo(
            nodeEl.getAttribute('data-node-id'),
            edgeBtn.getAttribute('data-relation'),
            edgeBtn.getAttribute('data-before') === '1'
          );
          return;
        }
        var swatch = e.target.closest('.mm-swatch');
        if (swatch) { updateSelectedNode({ color: swatch.getAttribute('data-color') }); return; }
        if (e.target.closest('[data-role="delete"]')) { deleteSelectedNode(); return; }
        if (e.target.closest('[data-role="add-shared-child"]')) addSharedChildSelected();
      });

      // Committing an in-node text edit fires on focusout (bubbles,
      // unlike blur) rather than the pointerdown/click delegation
      // above, since it needs to run whenever the label loses focus
      // for ANY reason (Enter/Escape below, clicking elsewhere,
      // Tab...), not just on a click.
      document.getElementById('mmNodesLayer').addEventListener('focusout', function (e) {
        var label = e.target.closest('[data-role="label"]');
        if (label) commitNodeTextFromLabel(label);
      });
      document.getElementById('mmNodesLayer').addEventListener('keydown', function (e) {
        var label = e.target.closest('[data-role="label"]');
        if (!label) return;
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); label.blur(); }
        else if (e.key === 'Escape') { e.preventDefault(); label.blur(); }
      });
      // Pasting into a node's label should paste plain text, not
      // whatever rich markup the clipboard also carries -- a
      // contenteditable div otherwise happily inherits the source's
      // own formatting.
      document.getElementById('mmNodesLayer').addEventListener('paste', function (e) {
        var label = e.target.closest('[data-role="label"]');
        if (!label) return;
        e.preventDefault();
        var text = (e.clipboardData || window.clipboardData).getData('text/plain');
        document.execCommand('insertText', false, text);
      });

      // ---- Rendering ----------------------------------------------------

      function renderCanvas(mm) {
        var layout = computeLayout(mm.nodes);
        MM.lastLayout = layout;

        var world = document.getElementById('mmWorld');
        world.style.width = layout.worldWidth + 'px';
        world.style.height = layout.worldHeight + 'px';

        document.getElementById('mmNodesLayer').innerHTML = mm.nodes.map(function (n) {
          var pos = layout.positions[n.id];
          // Every selected node (whether it's the only one, or one of
          // several shift-added to it) gets the exact same gold ring --
          // there's no separate "multi-select" visual mode anymore.
          var isSelected = MM.multiSelectIds.has(n.id);
          var isAnchor = n.id === MM.selectedNodeId;
          var isRoot = n.parentId === null;
          var selectedCls = isSelected ? ' selected' : '';
          // Only the sole selected node is ever contenteditable --
          // typing directly into a node is how its text changes now
          // (see the focusout/keydown delegation above), and that's
          // ambiguous the moment more than one node is selected, so
          // editing is off for all of them until the selection is back
          // down to just one.
          var editableAttr = (isSelected && MM.multiSelectIds.size === 1) ? ' contenteditable="true" spellcheck="false"' : '';
          // The root is the one node every mindmap always keeps, so it
          // can't get a parent (which would just bury it under a new,
          // equally permanent root) or a sibling (it has no parent to
          // share one under) -- only its "add child" edge button shows.
          // The backend enforces the same rule; this just keeps the
          // dead-end options from ever being offered in the first place.
          // The popover below the anchor node is the color swatches +
          // delete when it's the only thing selected, or the "add
          // shared child" button once a second node's been shift-added
          // -- see MM.selectedNodeId's own comment for why it's always
          // the anchor's popover, never every selected node's own.
          var popoverHtml = '';
          if (isAnchor && MM.multiSelectIds.size === 1) popoverHtml = renderColorPopoverHtml(n);
          else if (isAnchor && MM.multiSelectIds.size >= 2) popoverHtml = renderSharedChildPopoverHtml();
          return '<div class="mm-node mm-node-' + esc(n.color) + selectedCls + '" data-node-id="' + esc(n.id) + '" ' +
            'style="left:' + pos.x + 'px; top:' + pos.y + 'px;">' +
            '<div class="mm-node-label" data-role="label"' + editableAttr + '>' + esc(n.text) + '</div>' +
            (isRoot ? '' : '<button type="button" class="mm-edge-btn mm-edge-top" data-relation="parent" title="Add parent">+</button>') +
            '<button type="button" class="mm-edge-btn mm-edge-bottom" data-relation="child" title="Add child">+</button>' +
            (isRoot ? '' : '<button type="button" class="mm-edge-btn mm-edge-left" data-relation="sibling" data-before="1" title="Add sibling">+</button>') +
            (isRoot ? '' : '<button type="button" class="mm-edge-btn mm-edge-right" data-relation="sibling" data-before="0" title="Add sibling">+</button>') +
            popoverHtml +
            '</div>';
        }).join('');

        // A newly-selected node (see selectNode) asks to be focused,
        // with its text pre-selected, right after the DOM above lands
        // -- lets the player start typing immediately to rename it,
        // the same way selecting text in any other field works.
        // Deferred with setTimeout(..., 0) rather than called inline:
        // this render() runs synchronously inside the very pointerdown
        // handler that's selecting the node, and a browser's own
        // default action for that same mousedown/pointerdown (run
        // right after all its event listeners finish) resolves focus
        // on its own -- since the node wasn't editable/focusable yet
        // at mousedown time, that default resolution finds nothing
        // focusable and blurs to <body>, silently undoing a focus()
        // called inline here. Pushing this to the next task runs it
        // after that default focus resolution has already happened,
        // so it's the one that sticks.
        if (MM.focusNodeId) {
          var focusId = MM.focusNodeId;
          MM.focusNodeId = null;
          setTimeout(function () {
            var label = document.querySelector('.mm-node[data-node-id="' + focusId + '"] [data-role="label"]');
            if (!label) return;
            label.focus();
            var range = document.createRange();
            range.selectNodeContents(label);
            var sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
          }, 0);
        }

        var svg = document.getElementById('mmLines');
        svg.setAttribute('width', layout.worldWidth);
        svg.setAttribute('height', layout.worldHeight);
        var pathsHtml = '';
        layout.childrenMap.forEach(function (kids, parentId) {
          if (parentId === null || !kids.length) return; // the null bucket just holds the root itself, not a real edge
          // Shared-child nodes (extraParentIds) get their own dedicated
          // fan-in connector below, which already draws the line up to
          // THIS parent too -- drawing it again here would just be a
          // redundant, perfectly-overlapping duplicate segment.
          var fanOutKids = kids.filter(function (k) { return !k.extraParentIds || !k.extraParentIds.length; });
          if (!fanOutKids.length) return;
          var parentPos = layout.positions[parentId];
          if (!parentPos) return;
          var parentCenterX = parentPos.x + NODE_WIDTH / 2;
          var parentBottomY = parentPos.y + NODE_HEIGHT;
          var childTopY = parentPos.y + ROW_HEIGHT;
          var busY = parentBottomY + (childTopY - parentBottomY) / 2;
          var childXs = fanOutKids.map(function (k) { return layout.positions[k.id].x + NODE_WIDTH / 2; });
          var minX = Math.min.apply(null, childXs), maxX = Math.max.apply(null, childXs);
          var d = 'M ' + parentCenterX + ' ' + parentBottomY + ' L ' + parentCenterX + ' ' + busY + ' ';
          if (fanOutKids.length > 1) d += 'M ' + minX + ' ' + busY + ' L ' + maxX + ' ' + busY + ' ';
          childXs.forEach(function (cx) { d += 'M ' + cx + ' ' + busY + ' L ' + cx + ' ' + childTopY + ' '; });
          pathsHtml += '<path d="' + d + '"></path>';
        });

        // Fan-in connectors for shared-child nodes -- the mirror image
        // of the fan-out bus above: instead of one parent branching
        // down into several children, several parents converge down
        // into one shared child (e.g. four "blocklist" nodes all
        // feeding into one "setup" node below them). Drawn as its own
        // pass since these nodes aren't grouped by a single parentId
        // the way layout.childrenMap is keyed.
        mm.nodes.forEach(function (n) {
          if (!n.extraParentIds || !n.extraParentIds.length) return;
          var childPos = layout.positions[n.id];
          if (!childPos) return;
          var linkedIds = [n.parentId].concat(n.extraParentIds).filter(function (pid) {
            return !!layout.positions[pid];
          });
          if (linkedIds.length < 2) return; // a linked parent got deleted and pruned down to <2 -- nothing shared to draw
          var childTopY = childPos.y;
          var childCenterX = childPos.x + NODE_WIDTH / 2;
          var parentBottomYs = linkedIds.map(function (pid) { return layout.positions[pid].y + NODE_HEIGHT; });
          var parentCenterXs = linkedIds.map(function (pid) { return layout.positions[pid].x + NODE_WIDTH / 2; });
          // Bus sits below the LOWEST linked parent (not just the
          // primary one) so it never runs through a parent that's
          // deeper than the others in the rare case they're not all on
          // the same row.
          var maxParentBottomY = Math.max.apply(null, parentBottomYs);
          var busY = maxParentBottomY + (childTopY - maxParentBottomY) / 2;
          var minX = Math.min.apply(null, parentCenterXs), maxX = Math.max.apply(null, parentCenterXs);
          var d = '';
          parentCenterXs.forEach(function (px, i) { d += 'M ' + px + ' ' + parentBottomYs[i] + ' L ' + px + ' ' + busY + ' '; });
          d += 'M ' + minX + ' ' + busY + ' L ' + maxX + ' ' + busY + ' ';
          d += 'M ' + childCenterX + ' ' + busY + ' L ' + childCenterX + ' ' + childTopY + ' ';
          pathsHtml += '<path d="' + d + '"></path>';
        });

        svg.innerHTML = pathsHtml;
      }

      function renderMenu() {
        var rows = MM.data.mindmaps.map(function (m) {
          var activeCls = (m.id === MM.activeMindmapId) ? ' active' : '';
          return '<button type="button" class="mm-menu-item mm-menu-switch' + activeCls + '" data-mindmap-id="' +
            esc(m.id) + '">' + esc(m.name) + '</button>';
        }).join('');
        document.getElementById('mmMenu').innerHTML = rows +
          '<div class="mm-menu-divider"></div>' +
          '<button type="button" class="mm-menu-item" id="mmMenuNew">New mindmap</button>' +
          '<button type="button" class="mm-menu-item" id="mmMenuRename">Rename mindmap</button>' +
          '<button type="button" class="mm-menu-item danger" id="mmMenuDelete">Delete mindmap</button>';
      }

      // The selected node's color swatches + delete action, shown as a
      // popover anchored right below the node itself -- replaces the
      // old toolbar's swatch row and +Parent/+Child/+Sibling/Delete
      // buttons (the add-relative ones are now the edge buttons above;
      // delete didn't have anywhere else to go once the toolbar was
      // removed, so it lives here too). The root node has no delete
      // action, same rule the backend already enforces. Shares its
      // outer .mm-node-popover shell/position with
      // renderSharedChildPopoverHtml below -- only one of the two is
      // ever shown for a given node (see renderCanvas), depending on
      // whether it's the sole selected node or the anchor of several.
      function renderColorPopoverHtml(node) {
        var swatches = NODE_COLORS.map(function (c) {
          var activeCls = (c === node.color) ? ' active' : '';
          return '<button type="button" class="mm-swatch mm-swatch-' + c + activeCls + '" data-color="' + c + '" title="' + c + '"></button>';
        }).join('');
        var isRoot = node.parentId === null;
        return '<div class="mm-node-popover" data-role="popover">' +
          '<div class="mm-color-popover-swatches">' + swatches + '</div>' +
          (isRoot ? '' : '<button type="button" class="btn-secondary mm-delete-btn mm-color-popover-delete" data-role="delete">Delete</button>') +
          '</div>';
      }

      // Shown instead of the color popover above once a SECOND node's
      // been shift-added to the selection (see extendMultiSelect) --
      // anchored the same way, below the anchor node (MM.selectedNodeId),
      // but with a single action: create the shared child connecting
      // every currently-selected node (see addSharedChildSelected).
      function renderSharedChildPopoverHtml() {
        return '<div class="mm-node-popover" data-role="popover">' +
          '<button type="button" class="btn-secondary mm-add-shared-child-btn" data-role="add-shared-child">Add shared child</button>' +
          '</div>';
      }

      function render() {
        var wrapEl = document.getElementById('mmEmptyWrap');
        var msgEl = document.getElementById('mmEmptyMsg');
        var createBtn = document.getElementById('mmCreateFirstBtn');
        var bodyEl = document.getElementById('mmBody');

        if (!MM.data) {
          wrapEl.style.display = '';
          msgEl.textContent = 'Loading…';
          createBtn.style.display = 'none';
          bodyEl.style.display = 'none';
          return;
        }
        if (!MM.data.mindmaps.length) {
          wrapEl.style.display = '';
          msgEl.textContent = '';
          createBtn.style.display = '';
          bodyEl.style.display = 'none';
          return;
        }
        wrapEl.style.display = 'none';
        bodyEl.style.display = '';

        var mm = activeMindmap();
        document.getElementById('mmSwitchName').textContent = mm ? mm.name : '';
        renderMenu();
        pruneMultiSelect(mm);
        if (mm) renderCanvas(mm);
      }

      // Drops any selected id that no longer exists in the active
      // mindmap -- a node could vanish out from under the selection
      // (deleted directly, or via switching to a different mindmap
      // entirely) without ever going through selectNode/
      // extendMultiSelect. Also re-syncs the anchor (MM.selectedNodeId)
      // if IT was the one pruned, falling back to whatever's left --
      // same "most recently added" fallback extendMultiSelect uses when
      // the anchor is removed by hand.
      function pruneMultiSelect(mm) {
        if (!mm) { MM.multiSelectIds.clear(); MM.selectedNodeId = null; return; }
        var validIds = new Set(mm.nodes.map(function (n) { return n.id; }));
        MM.multiSelectIds.forEach(function (id) {
          if (!validIds.has(id)) MM.multiSelectIds.delete(id);
        });
        if (MM.selectedNodeId && !MM.multiSelectIds.has(MM.selectedNodeId)) {
          var remaining = Array.from(MM.multiSelectIds);
          MM.selectedNodeId = remaining.length ? remaining[remaining.length - 1] : null;
        }
      }

      // ---- Mindmap switcher menu -----------------------------------------

      function closeMenu() { document.getElementById('mmMenu').style.display = 'none'; }
      document.getElementById('mmSwitchBtn').addEventListener('click', function () {
        commitActiveLabelIfEditing();
        var menu = document.getElementById('mmMenu');
        menu.style.display = menu.style.display === 'none' ? 'flex' : 'none';
      });
      document.addEventListener('click', function (e) {
        var wrap = document.querySelector('.mm-menu-wrap');
        if (wrap && !wrap.contains(e.target)) closeMenu();
      });

      document.getElementById('mmMenu').addEventListener('click', function (e) {
        commitActiveLabelIfEditing();
        var switchBtn = e.target.closest('.mm-menu-switch');
        if (switchBtn) {
          closeMenu();
          var id = switchBtn.getAttribute('data-mindmap-id');
          if (id !== MM.activeMindmapId) {
            setActiveMindmapId(id);
            MM.selectedNodeId = null;
            render();
            resetView();
          }
          return;
        }
        if (e.target.id === 'mmMenuNew') { closeMenu(); openNameForm('new', ''); return; }
        if (e.target.id === 'mmMenuRename') {
          closeMenu();
          var mm = activeMindmap();
          if (mm) openNameForm('rename', mm.name);
          return;
        }
        if (e.target.id === 'mmMenuDelete') { closeMenu(); deleteActiveMindmap(); return; }
      });

      async function deleteActiveMindmap() {
        var mm = activeMindmap();
        if (!mm) return;
        if (!window.confirm('Delete "' + mm.name + '"? This cannot be undone.')) return;
        const data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id), { method: 'DELETE' });
        if (data) {
          MM.data = data;
          MM.selectedNodeId = null;
          setActiveMindmapId(data.mindmaps.length ? data.mindmaps[0].id : null);
          render();
          resetView();
        }
      }

      // ---- New/rename mindmap form ---------------------------------------

      function openNameForm(mode, initialValue) {
        MM.nameFormMode = mode;
        var form = document.getElementById('mmNameForm');
        var input = document.getElementById('mmNameInput');
        form.style.display = 'flex';
        input.value = initialValue || '';
        input.focus();
      }
      document.getElementById('mmCreateFirstBtn').addEventListener('click', function () { openNameForm('new', ''); });
      document.getElementById('mmNameCancel').addEventListener('click', function () {
        document.getElementById('mmNameForm').style.display = 'none';
        MM.nameFormMode = null;
      });
      document.getElementById('mmNameSave').addEventListener('click', async function () {
        var name = (document.getElementById('mmNameInput').value || '').trim();
        if (!name) { showError('A mindmap name is required.'); return; }
        var mode = MM.nameFormMode;
        document.getElementById('mmNameForm').style.display = 'none';
        MM.nameFormMode = null;
        var data;
        if (mode === 'new') {
          data = await apiCall('/api/mindmaps', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name }),
          });
          if (data) {
            MM.data = data;
            var created = data.mindmaps.find(function (m) { return m.name === name; }) || data.mindmaps[data.mindmaps.length - 1];
            if (created) {
              setActiveMindmapId(created.id);
              MM.selectedNodeId = null;
              render();
              resetView();
            }
          }
        } else if (mode === 'rename') {
          var mm = activeMindmap();
          if (!mm) return;
          data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id), {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name }),
          });
          if (data) { MM.data = data; render(); }
        }
      });

      // ---- Selected-node actions ------------------------------------------

      async function updateSelectedNode(patch) {
        var mm = activeMindmap();
        var node = selectedNode();
        if (!mm || !node) return;
        const data = await apiCall(
          '/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/' + encodeURIComponent(node.id),
          { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) }
        );
        if (data) { MM.data = data; render(); }
      }

      // Only the selected node is ever contenteditable, so the label
      // losing focus always means the CURRENTLY selected node's text
      // is what changed -- no need to look up which node the label
      // belonged to.
      function commitNodeTextFromLabel(label) {
        var node = selectedNode();
        if (!node) return;
        var val = (label.textContent || '').trim();
        if (!val || val === node.text) { label.textContent = node.text; return; }
        updateSelectedNode({ text: val });
      }

      // Adds a node relative to `nodeId` -- NOT necessarily the
      // currently selected node, since the edge-hover "+" buttons work
      // on whichever node they're hovering, selected or not. `before`
      // only matters for relation "sibling" (the left- vs. right-edge
      // button): placed immediately before or after `nodeId` among its
      // own siblings, see _order_before/_order_after in
      // app/mindmaps.py.
      async function addNodeRelativeTo(nodeId, relation, before) {
        var mm = activeMindmap();
        if (!mm) return;
        var body = { relative_to: nodeId, relation: relation, text: 'New', color: 'gray' };
        if (relation === 'sibling') body.before = !!before;
        const data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        });
        if (data) {
          MM.data = data;
          // selectNode both selects and (since it's a different id
          // than whatever was selected before) queues the new node's
          // label to be focused + text-selected on the next render, so
          // the player can start typing its name immediately.
          selectNode(data.newNodeId || null);
        }
      }

      async function deleteSelectedNode() {
        var mm = activeMindmap();
        var node = selectedNode();
        if (!mm || !node || node.parentId === null) return;
        if (!window.confirm('Delete "' + node.text + '" and everything below it? This cannot be undone.')) return;
        const data = await apiCall(
          '/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/' + encodeURIComponent(node.id),
          { method: 'DELETE' }
        );
        if (data) { MM.data = data; MM.selectedNodeId = null; render(); }
      }

      // ---- Multi-select: add a shared child below several nodes ------

      // Adds one new node as a shared CHILD of every node currently in
      // MM.multiSelectIds (shift-click, see extendMultiSelect) -- e.g.
      // several "blocklist" nodes all feeding into one shared "setup"
      // node below them. Wired to the "add shared child" button inside
      // renderSharedChildPopoverHtml's popover (see the click
      // delegation above), which only ever shows once 2+ nodes are
      // selected, so the size check here is just a defensive floor,
      // not something a player can normally trigger under. Unlike a
      // normal single add, the selected nodes don't need to share a
      // parent or sit at the same depth -- see add_shared_child in
      // app/mindmaps.py for why that's fine structurally;
      // computeLayout/renderCanvas draw the extra connector lines and
      // nudge the new node's position to sit centered under the whole
      // selected group (see their own extraParentIds handling).
      async function addSharedChildSelected() {
        var mm = activeMindmap();
        if (!mm || MM.multiSelectIds.size < 2) return;
        const data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/shared-child', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ parent_ids: Array.from(MM.multiSelectIds), text: 'New', color: 'gray' }),
        });
        // selectNode below replaces MM.multiSelectIds with just the new
        // node on its own -- no separate .clear() needed first.
        if (data) { MM.data = data; selectNode(data.newNodeId || null); }
      }

      // ---- Boot -----------------------------------------------------------

      async function loadState() {
        const data = await apiCall('/api/mindmaps');
        if (!data) return;
        MM.data = data;
        if (!MM.activeMindmapId || !data.mindmaps.some(function (m) { return m.id === MM.activeMindmapId; })) {
          var stored = loadStoredActiveMindmapId();
          var resolved = (stored && data.mindmaps.some(function (m) { return m.id === stored; }))
            ? stored
            : (data.mindmaps.length ? data.mindmaps[0].id : null);
          setActiveMindmapId(resolved);
        }
        render();
        resetView();
      }

      loadState();
    })();
    """
    return _shell(
        title="Mindmaps — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )

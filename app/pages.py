"""Server-rendered HTML pages (landing, signup, login, dashboard). Plain
f-strings, no template engine.
"""
import json
import os
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import TYPE_CHECKING, Optional, Tuple

from app.bosses import HISCORE_BOSSES
from app.faq import get_faq_items
from app.mindmaps import SKILL_NAMES
from app.purchase_goals import item_icon_url

if TYPE_CHECKING:
    from app.models import Account, GameAccount, SharedContent


@dataclass
class PlayerView:
    """The combined identity + game-data view every render_* function takes,
    built per request by build_player_view from an Account and its active
    GameAccount (docs/multi-account-scoping.md). Pages never query models.
    """

    id: uuid.UUID
    email: Optional[str]
    email_verified_at: Optional[datetime]
    runescape_name: Optional[str]
    account_hash: Optional[str]
    # Hiscores snapshot (see app/hiscores.py). An empty dict means "never
    # synced"; every boss synced at least once is a key, 0 or otherwise.
    boss_kill_counts: dict
    hiscores_synced_at: Optional[datetime]


def build_player_view(account: "Account", game_account: Optional["GameAccount"]) -> PlayerView:
    """Combine an Account with its (possibly absent) active GameAccount: identity
    fields from the Account, game-data fields from the GameAccount.
    """
    return PlayerView(
        id=account.id,
        email=account.email,
        email_verified_at=account.email_verified_at,
        runescape_name=game_account.runescape_name if game_account else None,
        account_hash=game_account.account_hash if game_account else None,
        boss_kill_counts=dict(game_account.boss_kill_counts or {}) if game_account else {},
        hiscores_synced_at=game_account.hiscores_synced_at if game_account else None,
    )

# Cache-busting `?v=` (file mtime) for the stylesheet link in _shell():
# StaticFiles sends no Cache-Control, so browsers can keep a stale CSS after a
# CSS-only deploy.
_STATIC_CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "css", "myscape.css")
try:
    _CSS_VERSION = int(os.path.getmtime(_STATIC_CSS_PATH))
except OSError:
    _CSS_VERSION = 0

# Same cache-busting for the Purchase Goals stylesheet (separate from
# myscape.css since none of it applies elsewhere).
_PURCHASE_GOALS_CSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "css", "purchase-goals.css"
)
try:
    _PURCHASE_GOALS_CSS_VERSION = int(os.path.getmtime(_PURCHASE_GOALS_CSS_PATH))
except OSError:
    _PURCHASE_GOALS_CSS_VERSION = 0

_LOOT_TRACKER_CSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "css", "loot-tracker.css"
)
try:
    _LOOT_TRACKER_CSS_VERSION = int(os.path.getmtime(_LOOT_TRACKER_CSS_PATH))
except OSError:
    _LOOT_TRACKER_CSS_VERSION = 0

_HELP_SUPPORT_CSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "css", "help-support.css"
)
try:
    _HELP_SUPPORT_CSS_VERSION = int(os.path.getmtime(_HELP_SUPPORT_CSS_PATH))
except OSError:
    _HELP_SUPPORT_CSS_VERSION = 0

_CHARACTER_OVERVIEW_CSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "css", "character-overview.css"
)
try:
    _CHARACTER_OVERVIEW_CSS_VERSION = int(os.path.getmtime(_CHARACTER_OVERVIEW_CSS_PATH))
except OSError:
    _CHARACTER_OVERVIEW_CSS_VERSION = 0

# Curated snapshot behind the landing Loot Tracker preview (regenerate with
# scripts/gen_landing_loot_demo.py). Read lazily and memoized so a bad file
# fails only that page, not app startup.
_LANDING_LOOT_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "landing_loot_demo.json"
)
_landing_loot_demo_data = None


def _get_landing_loot_demo_data() -> Optional[dict]:
    global _landing_loot_demo_data
    if _landing_loot_demo_data is None:
        try:
            with open(_LANDING_LOOT_DEMO_PATH, "r") as f:
                _landing_loot_demo_data = json.load(f)
        except (OSError, ValueError):
            return None
    return _landing_loot_demo_data

# Snapshot for the landing Purchase Goals preview: a real "Tombs of Amascut"
# setup pulled once from GET /api/gear-setups.
_LANDING_PURCHASE_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "landing_purchase_demo.json"
)
_landing_purchase_demo_data = None


def _get_landing_purchase_demo_data() -> Optional[dict]:
    global _landing_purchase_demo_data
    if _landing_purchase_demo_data is None:
        try:
            with open(_LANDING_PURCHASE_DEMO_PATH, "r") as f:
                _landing_purchase_demo_data = json.load(f)
        except (OSError, ValueError):
            return None
    return _landing_purchase_demo_data

# Snapshot for the landing Mindmaps preview: one real mindmap pulled once from
# GET /api/mindmaps. Visitors edit it in memory only.
_LANDING_MINDMAP_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "landing_mindmap_demo.json"
)
_landing_mindmap_demo_data = None


def _get_landing_mindmap_demo_data() -> Optional[dict]:
    global _landing_mindmap_demo_data
    if _landing_mindmap_demo_data is None:
        try:
            with open(_LANDING_MINDMAP_DEMO_PATH, "r") as f:
                _landing_mindmap_demo_data = json.load(f)
        except (OSError, ValueError):
            return None
    return _landing_mindmap_demo_data

# Local snapshot for the Mindmaps preview's goal-criteria search
# (KC/item/quest), run client-side so visitors' cookies never reach the real
# endpoints. Full NPC and quest lists (app/npc_names.py, app/quest_names.py) but
# only a ~175-item subset of items (the full snapshot is ~1MB).
_LANDING_MINDMAP_SEARCH_POOLS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "landing_mindmap_search_pools.json"
)
_landing_mindmap_search_pools_data = None


def _get_landing_mindmap_search_pools_data() -> Optional[dict]:
    global _landing_mindmap_search_pools_data
    if _landing_mindmap_search_pools_data is None:
        try:
            with open(_LANDING_MINDMAP_SEARCH_POOLS_PATH, "r") as f:
                _landing_mindmap_search_pools_data = json.load(f)
        except (OSError, ValueError):
            return None
    return _landing_mindmap_search_pools_data

# Snapshot for the landing Storages Viewer preview: real possessions from GET
# /api/possessions/summary with PoH (Costume Room) items stripped.
_LANDING_STORAGES_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "landing_storages_demo.json"
)
_landing_storages_demo_data = None


def _get_landing_storages_demo_data() -> Optional[dict]:
    global _landing_storages_demo_data
    if _landing_storages_demo_data is None:
        try:
            with open(_LANDING_STORAGES_DEMO_PATH, "r") as f:
                _landing_storages_demo_data = json.load(f)
        except (OSError, ValueError):
            return None
    return _landing_storages_demo_data

# Snapshot for the landing Goal Tracking preview: real goals from GET
# /api/goals, with two current_value numbers adjusted by hand so the demo has an
# in-progress goal.
_LANDING_GOAL_TRACKING_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "landing_goal_tracking_demo.json"
)
_landing_goal_tracking_demo_data = None


def _get_landing_goal_tracking_demo_data() -> Optional[dict]:
    global _landing_goal_tracking_demo_data
    if _landing_goal_tracking_demo_data is None:
        try:
            with open(_LANDING_GOAL_TRACKING_DEMO_PATH, "r") as f:
                _landing_goal_tracking_demo_data = json.load(f)
        except (OSError, ValueError):
            return None
    return _landing_goal_tracking_demo_data

# Snapshot for the landing Character Overview preview: real summary, progress,
# skills and collection-log pulls in one JSON file. The 3D model is a separate
# binary asset (app/static/img/landing-character-overview-demo-model.glb) the
# preview's extra_head points the viewer at directly.
_LANDING_CHARACTER_OVERVIEW_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "landing_character_overview_demo.json"
)
_landing_character_overview_demo_data = None


def _get_landing_character_overview_demo_data() -> Optional[dict]:
    global _landing_character_overview_demo_data
    if _landing_character_overview_demo_data is None:
        try:
            with open(_LANDING_CHARACTER_OVERVIEW_DEMO_PATH, "r") as f:
                _landing_character_overview_demo_data = json.load(f)
        except (OSError, ValueError):
            return None
    return _landing_character_overview_demo_data

_MINDMAPS_CSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "css", "mindmaps.css"
)
try:
    _MINDMAPS_CSS_VERSION = int(os.path.getmtime(_MINDMAPS_CSS_PATH))
except OSError:
    _MINDMAPS_CSS_VERSION = 0

_POSSESSIONS_CSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "css", "possessions.css"
)
try:
    _POSSESSIONS_CSS_VERSION = int(os.path.getmtime(_POSSESSIONS_CSS_PATH))
except OSError:
    _POSSESSIONS_CSS_VERSION = 0

_GOAL_TRACKING_CSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "css", "goal-tracking.css"
)
try:
    _GOAL_TRACKING_CSS_VERSION = int(os.path.getmtime(_GOAL_TRACKING_CSS_PATH))
except OSError:
    _GOAL_TRACKING_CSS_VERSION = 0


def _nav_sides(player: Optional[PlayerView]) -> tuple[str, str]:
    """The link/button on each side of the centered logo: Log in / Sign up when
    logged out, Dashboard / Account when logged in.
    """
    if player:
        return (
            '<a href="/dashboard">Dashboard</a>',
            '<a href="/account">Account<span class="friend-badge" id="navAccountBadge" data-tooltip="Pending friend requests" hidden></span></a>',
        )
    return (
        '<a href="/login">Log in</a>',
        '<a href="/signup">Sign up</a>',
    )


def _link_banner(player: Optional[PlayerView]) -> str:
    """Site-wide banner prompting a logged-in, unlinked player to link their
    RuneLite plugin; renders nothing once `player.account_hash` is set. The
    "Generate code" button doubles as the code display; a second click copies
    it.
    
    `id="linkBanner"` is load-bearing: _shell()'s script polls for link
    completion only when it exists. Hidden for unverified players because POST
    /api/link/start requires a confirmed email.
    """
    if not player or not player.email_verified_at or player.account_hash:
        return ""
    return """
    <div class="link-banner" id="linkBanner">
      <div class="link-banner-inner">
        <span class="link-banner-message">Click to generate a code to enter into your RuneLite client.</span>
        <button class="link-banner-btn" id="generateLinkBtn" type="button">GENERATE CODE</button>
      </div>
      <div class="auth-error link-banner-error" id="linkError"></div>
    </div>
    """


def _footer(player: Optional[PlayerView], extra: str = "") -> str:
    """Site-wide footer, the mirror of the header (see the `header` rule in
    myscape.css): social icon row and OSRS trademark attribution. `extra` is
    page-specific content rendered first inside .footer-inner (currently the
    landing page's call-to-action, via _shell()'s footer_extra).
    """
    return f"""
    <footer>
      <div class="footer-inner wrap">
        {extra}
        <div class="footer-social">
          <a class="footer-social-link footer-social-github" href="https://github.com/Mootrius" target="_blank" rel="noopener" title="GitHub" aria-label="GitHub"></a>
          <a class="footer-social-link footer-social-discord" href="https://discord.gg/myscape" target="_blank" rel="noopener" title="Discord" aria-label="Discord"></a>
          <a class="footer-social-link footer-social-patreon" href="https://patreon.com/myscape" target="_blank" rel="noopener" title="Patreon" aria-label="Patreon"></a>
        </div>
        <p class="footer-trademark">
          <a href="https://oldschool.runescape.com/" target="_blank" rel="noopener">Old School RuneScape</a>
          is a trademark of
          <a href="https://www.jagex.com/" target="_blank" rel="noopener">Jagex Ltd.</a>
        </p>
      </div>
    </footer>
    """


# Canonical production domain for absolute og:url/og:image/twitter:image URLs
# and the landing <link rel="canonical">, whichever environment renders the page
# (these tags are for crawlers).
_SITE_URL = "https://myscape.io"

# Site-wide fallback for <meta name="description">/og:description/
# twitter:description; pages can pass meta_description to override
# (render_public_character_overview does, to name the player).
_DEFAULT_META_DESCRIPTION = (
    "myscape is a free RuneLite plugin and companion site for Old School "
    "RuneScape. Share your accolades with friends, track loot from every NPC "
    "you kill, plan Grand Exchange purchases with real-time prices, make "
    "mindmaps to plan your grinds, and set goals with auto-detecting "
    "completion functionality."
)


def _shell(
    *,
    title: str,
    player: Optional[PlayerView],
    body: str,
    extra_script: str = "",
    extra_head: str = "",
    body_class: str = "",
    footer_extra: str = "",
    meta_description: str = _DEFAULT_META_DESCRIPTION,
    canonical_path: Optional[str] = None,
    noindex: bool = True,
) -> str:
    nav_left, nav_right = _nav_sides(player)
    shared_script = """
    // Pairs with myscape.css's `user-select: none`: Firefox has no CSS
    // equivalent of -webkit-user-drag, so preventDefault() on dragstart,
    // delegated on document to cover icons injected later.
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

      if (btn.dataset.code) {
        try {
          await navigator.clipboard.writeText(btn.dataset.code);
          btn.textContent = 'COPIED TO CLIPBOARD';
          btn.removeAttribute('title');
          btn.disabled = true;
        } catch (err) {
          errorEl.textContent = 'Could not copy the code -- please copy it manually.';
          errorEl.classList.add('show');
        }
        return;
      }

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

    // Linking happens in the RuneLite plugin, so poll the session "who am I"
    // endpoint every few seconds and reload once account_hash is set.
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
        }
      }, 3000);
    }

    // Friend-request count next to ACCOUNT (see _nav_sides): polls every 10s,
    // pausing while the tab is hidden, and broadcasts a window event for the
    // account page.
    (function () {
      const badge = document.getElementById('navAccountBadge');
      if (!badge) return;
      function apply(data) {
        const total = (data && data.total) || 0;
        badge.textContent = total > 99 ? '99+' : String(total);
        badge.hidden = total <= 0;
        window.dispatchEvent(new CustomEvent('myscape:friend-notifications', { detail: data }));
      }
      async function poll() {
        if (document.hidden) return;
        try {
          const res = await fetch('/api/friends/notifications');
          if (!res.ok) return;
          apply(await res.json());
        } catch (err) {
        }
      }
      window.myscapePollFriendNotifications = poll;
      poll();
      setInterval(poll, 10000);
      document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
    })();

    // Site-wide hover tooltip for elements with data-tooltip (see
    // .myscape-tooltip in myscape.css). SHOW_DELAY is short but avoids flashing
    // tooltips while sweeping across dense grids (e.g. Collection Log). Hiding
    // is immediate.
    (function () {
      const SHOW_DELAY = 150;
      let tooltipEl = null;
      let showTimer = null;
      let currentTarget = null;

      function ensureTooltipEl() {
        if (!tooltipEl) {
          tooltipEl = document.createElement('div');
          tooltipEl.className = 'myscape-tooltip';
          document.body.appendChild(tooltipEl);
        }
        return tooltipEl;
      }

      // Centered above the target; flips below if no room and clamps to the
      // viewport. Measured after the text is set (opacity: 0 still lays out,
      // unlike display: none, hence the CSS fades via opacity/transform).
      function positionTooltip(target, el) {
        const rect = target.getBoundingClientRect();
        const tipRect = el.getBoundingClientRect();
        const gap = 8;
        let left = rect.left + rect.width / 2 - tipRect.width / 2;
        let top = rect.top - tipRect.height - gap;
        if (top < 4) top = rect.bottom + gap;
        const maxLeft = window.innerWidth - tipRect.width - 4;
        if (left < 4) left = 4;
        else if (left > maxLeft) left = Math.max(4, maxLeft);
        el.style.left = left + 'px';
        el.style.top = top + 'px';
      }

      // Touch screens: window.myscapeTouchTooltipFilter(el) returning false
      // suppresses a tooltip.
      function tooltipAllowed(target) {
        if (!window.matchMedia('(hover: none)').matches) return true;
        var filter = window.myscapeTouchTooltipFilter;
        return typeof filter !== 'function' || filter(target) !== false;
      }

      function showTooltip(target) {
        if (currentTarget !== target) return;
        // A re-rendered-away target has an all-zero rect (tooltip would land
        // top-left).
        if (!target.isConnected) return;
        if (!tooltipAllowed(target)) return;
        const text = target.getAttribute('data-tooltip');
        if (!text) return;
        const el = ensureTooltipEl();
        el.classList.remove('show');
        el.textContent = text;
        // data-tooltip-wide: wider box for a long first line.
        el.classList.toggle('myscape-tooltip--wide', target.hasAttribute('data-tooltip-wide'));
        positionTooltip(target, el);
        // Commit the hidden state to a frame before adding 'show', or the
        // fade-in can collapse into an instant appearance.
        void el.offsetWidth;
        el.classList.add('show');
      }

      function hideTooltip() {
        clearTimeout(showTimer);
        currentTarget = null;
        if (tooltipEl) tooltipEl.classList.remove('show');
      }

      document.addEventListener('mouseover', (e) => {
        const target = e.target.closest ? e.target.closest('[data-tooltip]') : null;
        if (!target || target === currentTarget) return;
        currentTarget = target;
        clearTimeout(showTimer);
        showTimer = setTimeout(() => showTooltip(target), SHOW_DELAY);
      });

      document.addEventListener('mouseout', (e) => {
        const target = e.target.closest ? e.target.closest('[data-tooltip]') : null;
        if (!target || target !== currentTarget) return;
        if (e.relatedTarget && target.contains(e.relatedTarget)) return;
        hideTooltip();
      });

      window.addEventListener('scroll', hideTooltip, true);
      window.addEventListener('resize', hideTooltip);

      // Touch has no hover, so a tooltip-carrying link (Skills cells, Collection
      // Log tiles) takes two taps: first shows the tooltip, second navigates.
      // Buttons act on tap. (hover: none) keeps this off desktop.
      (function () {
        const noHover = window.matchMedia('(hover: none)');
        let armedLink = null;
        let armTimer = null;
        document.addEventListener('touchstart', (e) => {
          if (!currentTarget) return;
          if (e.target.closest && e.target.closest('[data-tooltip]') === currentTarget) return;
          armedLink = null;
          hideTooltip();
        }, { passive: true });
        function toggleDismisses(el) {
          var fn = window.myscapeTouchTooltipToggle;
          return typeof fn === 'function' && fn(el) === true;
        }
        document.addEventListener('click', (e) => {
          if (!noHover.matches) return;
          const tipTarget = e.target.closest ? e.target.closest('[data-tooltip]') : null;
          if (tipTarget && toggleDismisses(tipTarget)) {
            if (tipTarget === currentTarget && tooltipEl && tooltipEl.classList.contains('show')) {
              hideTooltip();
            } else {
              // Shown directly from the tap: the emulated mouseover doesn't
              // refire for an element the pointer is already on.
              clearTimeout(showTimer);
              currentTarget = tipTarget;
              showTooltip(tipTarget);
            }
            return;
          }
          const link = e.target.closest ? e.target.closest('a[data-tooltip]') : null;
          if (!link) { armedLink = null; return; }
          if (!tooltipAllowed(link)) return;
          if (armedLink === link) { armedLink = null; clearTimeout(armTimer); return; }
          e.preventDefault();
          armedLink = link;
          currentTarget = link;
          showTooltip(link);
          clearTimeout(armTimer);
          armTimer = setTimeout(() => { armedLink = null; hideTooltip(); }, 3000);
        }, true);
      })();
    })();
    """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(meta_description)}" />
  <!-- Every page except the landing page is behind a login or is an auth utility
       page, so it defaults to noindex (see _shell's signature); render_landing
       opts back in. nofollow too, since crawlers needn't follow links on noindexed
       pages. -->
  {'<meta name="robots" content="noindex, nofollow" />' if noindex else ""}
  {f'<link rel="canonical" href="{escape(_SITE_URL + canonical_path)}" />' if canonical_path else ""}
  <!-- Open Graph + Twitter Card link previews (Discord/Slack/etc.), on every page
       so a pasted dashboard link still previews with the branded fallback.
       og-image-v2.jpg is 1200x630 on the opaque site background (myscape.css
       --bg), since transparent images preview against unpredictable backgrounds;
       "-v2" busts Discord/Twitter's cache keyed by image URL. -->
  <meta property="og:site_name" content="myscape" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="{escape(title)}" />
  <meta property="og:description" content="{escape(meta_description)}" />
  <meta property="og:image" content="{escape(_SITE_URL + '/static/img/og-image-v2.jpg')}" />
  <meta property="og:image:width" content="1200" />
  <meta property="og:image:height" content="630" />
  {f'<meta property="og:url" content="{escape(_SITE_URL + canonical_path)}" />' if canonical_path else ""}
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{escape(title)}" />
  <meta name="twitter:description" content="{escape(meta_description)}" />
  <meta name="twitter:image" content="{escape(_SITE_URL + '/static/img/og-image-v2.jpg')}" />
  <!-- Preload the pixel font ahead of the stylesheet that declares @font-face
       (myscape.css); otherwise the browser finds it only after parsing the CSS and
       painting, causing a flash of fallback font. crossorigin is required even
       same-origin: fonts load in anonymous CORS mode, and a preload without it is
       a separate request, so the file is fetched twice. -->
  <link rel="preload" href="/static/fonts/RuneScapePlain11.otf" as="font" type="font/otf" crossorigin />
  <!-- Tints the browser chrome (Android toolbar, iOS Safari bars) to myscape.css's
       --bg (#0f0f10). Desktop browsers ignore theme-color for non-installed pages
       on purpose. A single value, since the site has no light theme. -->
  <meta name="theme-color" content="#0f0f10" />
  <link rel="icon" href="/static/favicon.ico" sizes="any" />
  <link rel="icon" type="image/png" sizes="32x32" href="/static/icons/favicon-32x32.png" />
  <link rel="icon" type="image/png" sizes="16x16" href="/static/icons/favicon-16x16.png" />
  <link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png" />
  <link rel="stylesheet" href="/static/css/myscape.css?v={_CSS_VERSION}" />
  {extra_head}
</head>
<body{f' class="{body_class}"' if body_class else ""}>
  {_link_banner(player)}
  <header>
    <nav class="wrap header-inner">
      <div class="nav-side nav-left">{nav_left}</div>
      <!-- ?home=1 only while logged in: root() (main.py) otherwise redirects
           logged-in players to /dashboard. Not needed when logged out. -->
      <p class="logo"><a href="{'/?home=1' if player else '/'}">myscape</a></p>
      <div class="nav-side nav-right">{nav_right}</div>
    </nav>
  </header>
  <div class="page">
    <div class="wrap">
      {body}
    </div>
  </div>
  {_footer(player, extra=footer_extra)}
  <script>
    {shared_script}
    {extra_script}
  </script>
</body>
</html>"""


def render_landing(player: Optional[PlayerView]) -> str:
    # root() (main.py) redirects logged-in players to /dashboard unless ?home=1,
    # which the header logo adds while logged in. The footer's "ARE YOU READY?"
    # CTA (_footer's extra, _shell's footer_extra) sits inside <footer> so it
    # shares the footer's scroll-snap stop (see body.landing footer's min-height
    # in myscape.css). One button logged in, Log in/Sign up logged out.
    if player:
        cta_actions = '<a class="landing-cta-btn landing-cta-btn--primary" href="/dashboard">DASHBOARD</a>'
    else:
        cta_actions = (
            '<a class="landing-cta-btn landing-cta-btn--secondary" href="/login">LOG IN</a>'
            '<a class="landing-cta-btn landing-cta-btn--primary" href="/signup">SIGN UP</a>'
        )
    landing_cta = f"""
        <div class="landing-cta">
          <p class="landing-cta-heading">ARE YOU READY?</p>
          <div class="landing-cta-actions">
            {cta_actions}
          </div>
        </div>
    """
    # Interactive Character Overview preview
    # (render_landing_character_overview_preview), first on the page. Falls back
    # to the preview's own character crop if the snapshot is missing (no anchor
    # image exists for it).
    character_overview_preview = render_landing_character_overview_preview()
    if character_overview_preview:
        character_overview_preview_head, character_overview_preview_body, character_overview_preview_script = character_overview_preview
        character_overview_anchor_section = f"""
      <section class="landing-anchor landing-anchor--character-overview-preview">
        <div class="landing-character-overview-preview">
          {character_overview_preview_body}
        </div>
      </section>"""
    else:
        character_overview_preview_head, character_overview_preview_script = "", ""
        character_overview_anchor_section = """
      <section class="landing-anchor">
        <picture>
          <source srcset="/static/img/landing-character-overview-preview-char.webp" type="image/webp">
          <img src="/static/img/landing-character-overview-preview-char.png" alt="Character overviews that you can share with your friends.">
        </picture>
      </section>"""
    # Interactive Loot Tracker preview (render_landing_loot_preview) replacing
    # the marketing image; falls back to the image if the snapshot is missing.
    loot_preview = render_landing_loot_preview()
    if loot_preview:
        loot_preview_head, loot_preview_body, loot_preview_script = loot_preview
        loot_anchor_section = f"""
      <section class="landing-anchor landing-anchor--loot-preview">
        <div class="landing-loot-preview">
          {loot_preview_body}
        </div>
      </section>"""
    else:
        loot_preview_head, loot_preview_script = "", ""
        loot_anchor_section = """
      <section class="landing-anchor">
        <picture>
          <source srcset="/static/img/anchor-loot-tracking.webp" type="image/webp">
          <img src="/static/img/anchor-loot-tracking.png" alt="Loot tracking like you've never seen it before.">
        </picture>
      </section>"""
    # Purchase Goals preview (render_landing_purchase_preview): read-only,
    # placed next to Loot Tracker so the interactive previews are adjacent.
    # Falls back to the image if the snapshot is missing.
    purchase_preview = render_landing_purchase_preview()
    if purchase_preview:
        purchase_preview_head, purchase_preview_body, purchase_preview_script = purchase_preview
        purchase_anchor_section = f"""
      <section class="landing-anchor landing-anchor--purchase-preview">
        <div class="landing-purchase-preview">
          {purchase_preview_body}
        </div>
      </section>"""
    else:
        purchase_preview_head, purchase_preview_script = "", ""
        purchase_anchor_section = """
      <section class="landing-anchor">
        <picture>
          <source srcset="/static/img/anchor-purchase-planner.webp" type="image/webp">
          <img src="/static/img/anchor-purchase-planner.png" alt="Purchase planner -- plan and track your next big buys.">
        </picture>
      </section>"""
    # Mindmaps preview (render_landing_mindmap_preview): editable in memory
    # only. Falls back to the image if the snapshot or search-pools sidecar is
    # missing.
    mindmap_preview = render_landing_mindmap_preview()
    if mindmap_preview:
        mindmap_preview_head, mindmap_preview_body, mindmap_preview_script = mindmap_preview
        mindmap_anchor_section = f"""
      <section class="landing-anchor landing-anchor--mindmap-preview">
        <div class="landing-mindmap-preview">
          {mindmap_preview_body}
        </div>
      </section>"""
    else:
        mindmap_preview_head, mindmap_preview_script = "", ""
        mindmap_anchor_section = """
      <section class="landing-anchor">
        <picture>
          <source srcset="/static/img/anchor-mindmaps.webp" type="image/webp">
          <img src="/static/img/anchor-mindmaps.png" alt="Mindmaps -- to plan every step of your grind.">
        </picture>
      </section>"""
    # Storages Viewer preview (render_landing_storages_preview), PoH items
    # excluded. Falls back to the image if the snapshot is missing.
    storages_preview = render_landing_storages_preview()
    if storages_preview:
        storages_preview_head, storages_preview_body, storages_preview_script = storages_preview
        storages_anchor_section = f"""
      <section class="landing-anchor landing-anchor--storages-preview">
        <div class="landing-storages-preview">
          {storages_preview_body}
        </div>
      </section>"""
    else:
        storages_preview_head, storages_preview_script = "", ""
        storages_anchor_section = """
      <section class="landing-anchor">
        <picture>
          <source srcset="/static/img/anchor-storages.webp" type="image/webp">
          <img src="/static/img/anchor-storages.png" alt="Storage viewing -- see everything you own, in one place.">
        </picture>
      </section>"""
    # Goal Tracking preview (render_landing_goal_tracking_preview); only the
    # wizard's final Save is out of scope. Falls back to the preview's character
    # crop (no anchor image exists) if the snapshot is missing.
    goal_tracking_preview = render_landing_goal_tracking_preview()
    if goal_tracking_preview:
        goal_tracking_preview_head, goal_tracking_preview_body, goal_tracking_preview_script = goal_tracking_preview
        goal_tracking_anchor_section = f"""
      <section class="landing-anchor landing-anchor--goal-tracking-preview">
        <div class="landing-goal-tracking-preview">
          {goal_tracking_preview_body}
        </div>
      </section>"""
    else:
        goal_tracking_preview_head, goal_tracking_preview_script = "", ""
        goal_tracking_anchor_section = """
      <section class="landing-anchor">
        <picture>
          <source srcset="/static/img/landing-goal-tracking-preview-char.webp" type="image/webp">
          <img src="/static/img/landing-goal-tracking-preview-char.png" alt="Goal tracking -- for those days when you need some dopamine.">
        </picture>
      </section>"""
    # Remaining anchor panels: pre-composited marketing art, not live markup.
    # landing-anchor--intro shares a stop with the header and is pinned to one
    # screen via CSS plus the script below, which measures the header height.
    body = f"""
    <div class="landing-anchors">
      <section class="landing-anchor landing-anchor--intro">
        <div class="landing-anchor-intro-media">
          <picture>
            <source srcset="/static/img/anchor-myscape-v2.webp" type="image/webp">
            <img src="/static/img/anchor-myscape-v2.png" alt="myscape -- a place for gains.">
          </picture>
        </div>
        <p class="landing-scroll-cue">
          <span class="landing-scroll-cue-arrow"></span>
          EXPLORE FEATURES
          <span class="landing-scroll-cue-arrow"></span>
        </p>
      </section>
      {character_overview_anchor_section}
      {loot_anchor_section}
      {purchase_anchor_section}
      {storages_anchor_section}
      {mindmap_anchor_section}
      {goal_tracking_anchor_section}
      <section class="landing-anchor landing-anchor--faq">
        <div class="landing-faq">
          <h2 class="landing-faq-title">GOT QUESTIONS?</h2>
          {_HELP_SUPPORT_SEARCH_MARKUP}
        </div>
      </section>
    </div>
    """
    # CSS scroll-snap (myscape.css) covers touch and keyboard. This script adds
    # wheel/trackpad handling: one stop per gesture, locked until 'scrollend',
    # so a fast flick can't skip panels.
    script = """
    (function () {
      // The first child is normally <header>, but the link-account banner
      // renders ahead of it (body.landing > *:first-child in myscape.css).
      var firstStop = document.body.firstElementChild;
      var anchors = Array.prototype.slice.call(
        document.querySelectorAll('.landing-anchor:not(.landing-anchor--intro)')
      );
      var footer = document.querySelector('footer');
      var stops = [firstStop].concat(anchors, [footer]).filter(Boolean);
      if (stops.length < 2) return;

      var current = 0;
      var locked = false;
      var lockGen = 0;

      // One persistent listener: scrollend can fire more than once per scroll,
      // and per-goTo add/remove pairs could leave stale listeners behind.
      window.addEventListener('scrollend', function () {
        locked = false;
      });

      // Scroll clamps to the max position, so the footer can't reach its raw
      // offsetTop; clamp each stop's expected position the same way so the
      // footer isn't mistaken for the mindmaps panel.
      function stopY(el) {
        var maxScroll = document.documentElement.scrollHeight - window.innerHeight;
        return Math.min(el.offsetTop, Math.max(0, maxScroll));
      }

      function nearestStop() {
        var y = window.scrollY;
        var idx = 0;
        for (var i = 0; i < stops.length; i++) {
          if (stopY(stops[i]) <= y + 2) idx = i;
        }
        return idx;
      }

      function goTo(index) {
        index = Math.max(0, Math.min(stops.length - 1, index));
        current = index;
        locked = true;
        var myGen = ++lockGen;
        // scrollend doesn't fire for a no-op scrollIntoView (e.g. down on the
        // last panel); this backstop clears the lock, and lockGen stops it
        // clearing a later goTo()'s lock.
        window.setTimeout(function () {
          if (lockGen === myGen) locked = false;
        }, 900);
        stops[current].scrollIntoView({ behavior: 'smooth', block: 'start' });
      }

      window.addEventListener('wheel', function (e) {
        if (e.ctrlKey || Math.abs(e.deltaY) < 4) return;
        // The FAQ panel can exceed the screen height; scroll it normally until
        // its edge is in view.
        var faq = e.target.closest ? e.target.closest('.landing-anchor--faq') : null;
        if (faq) {
          var r = faq.getBoundingClientRect();
          if ((e.deltaY > 0 && r.bottom > window.innerHeight + 2) || (e.deltaY < 0 && r.top < -2)) return;
        }
        e.preventDefault();
        if (locked) return;
        goTo(nearestStop() + (e.deltaY > 0 ? 1 : -1));
      }, { passive: false });
    })();

    // Phone width: the gold app name stays 30px and only shrinks (never grows)
    // when it wouldn't fit beside the character, so it never ellipsizes.
    (function () {
      var mq = window.matchMedia('(max-width: 700px)');
      function fit() {
        var golds = document.querySelectorAll('[class$="-preview-tagline-gold"]');
        for (var i = 0; i < golds.length; i++) {
          var g = golds[i];
          g.style.fontSize = '';
          if (!mq.matches) continue;
          var wrap = g.closest('[class$="-preview-tagline-wrap"]');
          if (!wrap) continue;
          var wcs = window.getComputedStyle(wrap);
          var avail = wrap.clientWidth - (parseFloat(wcs.paddingLeft) || 0) - (parseFloat(wcs.paddingRight) || 0);
          if (avail <= 0) continue;
          var size = 30;
          if (g.scrollWidth > avail) {
            size = Math.floor(30 * avail / g.scrollWidth);
            g.style.fontSize = size + 'px';
            while (size > 14 && g.scrollWidth > avail) {
              size -= 1;
              g.style.fontSize = size + 'px';
            }
          }
        }
      }
      fit();
      window.addEventListener('resize', fit);
      window.addEventListener('load', fit);
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
    })();

    // The intro panel plus header must be exactly one screen. Header height
    // varies (link banner, wrapping), so feed the measured gap into a custom
    // property used by myscape.css's height calc.
    (function () {
      var intro = document.querySelector('.landing-anchor--intro');
      if (!intro) return;

      function sync() {
        var above = intro.getBoundingClientRect().top + window.scrollY;
        document.documentElement.style.setProperty('--landing-intro-above', above + 'px');
      }

      sync();
      window.addEventListener('resize', sync);
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(sync);
      }
    })();
    """
    # Wrapper scripts for the loot/purchase previews append here (empty for the
    # static-image fallback).
    script += (
        character_overview_preview_script
        + loot_preview_script
        + purchase_preview_script
        + storages_preview_script
        + mindmap_preview_script
        + goal_tracking_preview_script
        + _help_support_script()
    )
    # body_class="landing" scopes the scroll-snap CSS (`html:has(body.landing)`
    # in myscape.css) to this page.
    return _shell(
        title="myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=(
            character_overview_preview_head
            + loot_preview_head
            + purchase_preview_head
            + storages_preview_head
            + mindmap_preview_head
            + goal_tracking_preview_head
            + _HELP_SUPPORT_HEAD
        ),
        body_class="landing",
        footer_extra=landing_cta,
        # The only indexable page; see _shell()'s noindex/canonical_path
        # comment.
        canonical_path="/",
        noindex=False,
    )


# Dashboard card icons: real OSRS items via item_icon_url
# (app/purchase_goals.py), which resolves to RuneLite's icon CDN by item id, so
# no icons are hosted here. Coins (995) resolves to the "biggest pile" art.
# Clueless scroll (20249) is a real novelty item, not a clue scroll.
_ICON_COINS = item_icon_url(995)
_ICON_BONES = item_icon_url(536)
_ICON_CLUELESS_SCROLL = item_icon_url(20249)
_ICON_HEAVY_CASKET = item_icon_url(19941)
_ICON_MAX_CAPE = item_icon_url(13280)
_ICON_CAKE_OF_GUIDANCE = item_icon_url(7542)
# Bundled PNG: no OSRS item reads as "your character".
_ICON_CHARACTER_OVERVIEW = "/static/img/icon-character-overview.png"


def _wiki_icon_url(filename: str) -> str:
    """Routed through /icon-cache/<filename> (app/icon_cache.py), like
    npc_icon_url in app/loot.py, because direct wiki hotlinks trip the wiki's
    rate limiting. Used by the Character Overview summary icons (wiki UI
    chrome, not items).
    """
    return "/icon-cache/" + urllib.parse.quote(filename)


_ICON_SUMMARY_COMBAT_LEVEL = _wiki_icon_url("Character_Summary_-_Combat_Level_icon.png")
_ICON_SUMMARY_TOTAL_LEVEL = _wiki_icon_url("Character_Summary_-_Total_Level.png")
_ICON_SUMMARY_TOTAL_XP = _wiki_icon_url("Character_Summary_-_Total_XP_icon.png")
_ICON_SUMMARY_QUESTS = _wiki_icon_url("Quest_List_tab_icon.png")
_ICON_SUMMARY_ACHIEVEMENTS = _wiki_icon_url("Achievement_Diaries_tab_icon.png")
_ICON_SUMMARY_COMBAT_TASKS = _wiki_icon_url("Character_Summary_-_Combat_Tasks_Completed_icon.png")
_ICON_SUMMARY_COLLECTIONS = _wiki_icon_url("Character_Summary_-_Collections_Logged_icon.png")

# Account-type tile: one icon per GameAccount.account_type code (app/models.py)
# plus the all-caps value label (e.g. "UGIM"). The icon is part of the value, so
# the script (ACCOUNT_TYPE_INFO, baked from this dict) swaps the <img>
# src/alt/title once account_type is fetched. MAIN's coin is the pre-fetch
# default.
_ACCOUNT_TYPE_INFO = {
    "MAIN": (_wiki_icon_url("Coins_10000.png"), "MAIN"),
    "IRONMAN": (_wiki_icon_url("Ironman_helm.png"), "IRONMAN"),
    "UIM": (_wiki_icon_url("Ultimate_ironman_helm.png"), "UIM"),
    "HCIM": (_wiki_icon_url("Hardcore_ironman_helm.png"), "HCIM"),
    "GIM": (_wiki_icon_url("Group_ironman_helm.png"), "GIM"),
    "HCGIM": (_wiki_icon_url("Hardcore_group_ironman_helm.png"), "HCGIM"),
    "UGIM": (_wiki_icon_url("Group_ironman_helm_(unranked).png"), "UGIM"),
}


def _dash_card(icon_src: str, icon_alt: str, title: str, description: str, extra_class: str = "") -> str:
    card_class = f"dash-card {extra_class}".strip()
    return f"""
    <div class="{card_class}">
      <div class="dash-card-icon"><img src="{escape(icon_src)}" alt="{escape(icon_alt)}" /></div>
      <div class="dash-card-body">
        <h3>{escape(title)}</h3>
        <p class="subtitle">{escape(description)}</p>
      </div>
    </div>
    """


def _dash_card_wrap(href: str, icon_src: str, icon_alt: str, title: str, description: str, extra_class: str = "") -> str:
    return f"""
    <div class="dash-card-wrap">
      <a href="{escape(href)}" class="dash-card-link">
        {_dash_card(icon_src, icon_alt, title, description, extra_class)}
      </a>
    </div>
    """


# Every dashboard card, keyed by a stable id independent of title/route/copy.
# The tuple order is the one fixed dashboard order.
DASHBOARD_CARD_KEYS = (
    "character_overview",
    "loot_tracker",
    "purchase_goals",
    "possessions",
    "mindmaps",
    "goal_tracking",
)


def render_dashboard(player: PlayerView) -> str:
    cards = {
        "loot_tracker": _dash_card_wrap(
            "/dashboard/loot-tracker",
            _ICON_BONES,
            "Dragon bones",
            "Loot Tracker",
            "Track the loot from any NPC you kill, with useful graphs and other "
            "statistics available for your tracking pleasure. Customize which "
            "NPCs are tracked and what data is shown.",
        ),
        "purchase_goals": _dash_card_wrap(
            "/dashboard/purchase-goals",
            _ICON_COINS,
            "Coins",
            "Purchase Goals",
            "Track your owned GP against the purchases you'd like to make on the "
            "Grand Exchange, all with live pricing updates for each item. "
            "Organize multiple setups to keep track of at once.",
        ),
        "mindmaps": _dash_card_wrap(
            "/dashboard/mindmaps",
            _ICON_CLUELESS_SCROLL,
            "Clueless scroll",
            "Mindmaps",
            "Organize your goals into a mindmap! Start from one goal and branch "
            "out with parent, child, and sibling nodes — all with "
            "auto-detecting completion functionality.",
        ),
        "possessions": _dash_card_wrap(
            "/dashboard/storages-viewer",
            _ICON_HEAVY_CASKET,
            "Heavy casket",
            "Storages Viewer",
            "Keep an eye on what you own across every storage in the game. "
            "Search it all, sort by anything, and filter to your heart's "
            "content — all in one place!",
        ),
        "goal_tracking": _dash_card_wrap(
            "/dashboard/goal-tracking",
            _ICON_MAX_CAPE,
            "Max cape",
            "Goal Tracking",
            "Visualize your goals by setting time-based or one-off quotas "
            "for yourself to meet, complete with auto-detecting and "
            "updating progress bars.",
        ),
        "character_overview": _dash_card_wrap(
            "/dashboard/character-overview",
            _ICON_CHARACTER_OVERVIEW,
            "Character overview icon",
            "Character Overview",
            "See your account's most relevant details all at a glance "
            "\u2014 including collection logs, skill levels, quest "
            "completions, achievement diaries, combat achievements, "
            "and more!",
        ),
    }

    cards_html = "\n      ".join(cards[key] for key in DASHBOARD_CARD_KEYS)

    # Help & Support sits outside DASHBOARD_CARD_KEYS: a smaller card on its own
    # row below the app cards.
    support_card_html = _dash_card_wrap(
        "/dashboard/help-and-support",
        _ICON_CAKE_OF_GUIDANCE,
        "Cake of guidance",
        "Help & Support",
        "See the FAQ, report bugs, and request features.",
        "dash-card--compact",
    )

    body = f"""
    <div class="dash-grid" id="dashGrid">
      {cards_html}
    </div>
    <div class="dash-support-row">
      {support_card_html}
    </div>
    """

    return _shell(title="Dashboard — myscape", player=player, body=body)


# Help & Support's FAQ search. Plain (non-f-string) script so braces and regexes
# need no escaping; __FAQ_JSON__ is swapped for the entries (app/faq.py) in
# render_help_support.
#
# Ranking: typed words (minus filler) match each FAQ's question, tags and
# answer, question/tag hits counting double; a word matches on a shared stem or
# prefix, or (longer words) a one-letter typo. An FAQ must match every word,
# else the closest partial matches show, flagged as such.
_HELP_SUPPORT_SCRIPT = r"""
    (function () {
      var FAQ = __FAQ_JSON__;
      var input = document.getElementById('hsSearch');
      var clearBtn = document.getElementById('hsSearchClear');
      var statusEl = document.getElementById('hsStatus');
      var noteEl = document.getElementById('hsNote');
      var DISCORD = '<a href="https://discord.gg/myscape" target="_blank" rel="noopener noreferrer">Discord server</a>';
      var resultsEl = document.getElementById('hsResults');

      var STOP = {};
      ('a an and are as at be but by can could do does for from get got ' +
       'have how i if in into is it its me my of on or our so than that ' +
       'the their then there these they this to up us was we what when ' +
       'where which who why will with would you your ' +
       'here too also just really please very anymore into about').split(' ').forEach(function (w) { STOP[w] = true; });

      function words(s) {
        return String(s).toLowerCase().replace(/['\u2019]/g, '').match(/[a-z0-9~]+/g) || [];
      }
      function stem(w) {
        var n = w.length;
        if (n > 4 && w.slice(-3) === 'ies') return w.slice(0, -3) + 'y';
        if (n > 5 && w.slice(-3) === 'ing') return w.slice(0, -3);
        if (n > 4 && w.slice(-2) === 'ed') return w.slice(0, -2);
        if (n > 3 && w.slice(-1) === 's' && w.slice(-2) !== 'ss') return w.slice(0, -1);
        return w;
      }
      function stems(s) { return words(s).map(stem); }

      function near(a, b) {
        if (Math.abs(a.length - b.length) > 1) return false;
        var i = 0;
        while (i < a.length && i < b.length && a[i] === b[i]) i++;
        if (i === a.length || i === b.length) return Math.abs(a.length - b.length) <= 1;
        if (a.length === b.length) {
          if (a.slice(i + 1) === b.slice(i + 1)) return true;
          if (a[i] === b[i + 1] && a[i + 1] === b[i] && a.slice(i + 2) === b.slice(i + 2)) return true;
          return false;
        }
        return a.length > b.length ? a.slice(i + 1) === b.slice(i) : b.slice(i + 1) === a.slice(i);
      }

      // Score of a typed word against the best word in a list: 3 exact, 2
      // prefix, 1.5 one-typo, 0 none.
      function best(t, list) {
        var b = 0;
        for (var i = 0; i < list.length; i++) {
          var w = list[i];
          if (w === t) return 3;
          if (t.length >= 4 && w.length >= 4 && (w.indexOf(t) === 0 || t.indexOf(w) === 0)) b = Math.max(b, 2);
          else if (t.length >= 5 && w.length >= 5 && near(t, w)) b = Math.max(b, 1.5);
        }
        return b;
      }

      FAQ.forEach(function (f) {
        f.qStems = stems(f.question);
        f.aStems = stems(f.answer);
        f.tagPhrases = f.tags.map(function (t) { return words(t).filter(function (w) { return !STOP[w]; }).map(stem); });
        f.tagStems = [].concat.apply([], f.tagPhrases);
        f.qJoined = f.qStems.join(' ');
        f.aJoined = f.aStems.join(' ');
      });

      function search(query) {
        var raw = words(query);
        var tokens = raw.filter(function (w) { return !STOP[w]; }).map(stem);
        if (!tokens.length) tokens = raw.map(stem);
        tokens = tokens.filter(function (t, i) { return tokens.indexOf(t) === i; });
        if (!tokens.length) return { hits: [], partial: false };
        var phrase = tokens.join(' ');
        var scored = [];
        FAQ.forEach(function (f) {
          var matched = 0, score = 0;
          tokens.forEach(function (t) {
            var q = best(t, f.qStems), g = best(t, f.tagStems), a = best(t, f.aStems) * 0.5;
            var top = Math.max(q, g, a);
            if (top > 0) {
              matched++;
              score += top + ((q > 0) + (g > 0) + (a > 0) - 1) * 0.5;
            }
          });
          if (!matched) return;
          if (tokens.length > 1) {
            if (f.qJoined.indexOf(phrase) !== -1) score += 4;
            if (f.aJoined.indexOf(phrase) !== -1) score += 1.5;
          }
          f.tagPhrases.forEach(function (tp) {
            var tj = tp.join(' ');
            if (tj === phrase) score += 6;
            else if (tokens.length > 1 && tj.indexOf(phrase) !== -1) score += 3;
          });
          scored.push({ f: f, matched: matched, score: score });
        });
        var byScore = function (x, y) { return y.score - x.score || x.f.id - y.f.id; };
        var full = scored.filter(function (s) { return s.matched === tokens.length; }).sort(byScore);
        var partial = false;
        // Partial matches (at least half the typed words) are the fallback when
        // nothing matches every word, and trail a short list of full matches.
        if (tokens.length > 1 && full.length < 3) {
          var need = Math.ceil(tokens.length / 2);
          var rest = scored.filter(function (s) { return s.matched < tokens.length && s.matched >= need; }).sort(byScore);
          var top = full.length ? full[0].score : (rest.length ? rest[0].score : 0);
          rest = rest.filter(function (s) { return s.score >= top * 0.5; });
          partial = !full.length && rest.length > 0;
          full = full.concat(rest.slice(0, 5 - full.length));
        }
        return { hits: full.map(function (s) { return s.f; }), partial: partial };
      }

      function setStatus(html) { statusEl.innerHTML = html; statusEl.style.display = html ? '' : 'none'; }
      function setNote(html) { noteEl.innerHTML = html; noteEl.style.display = html ? '' : 'none'; }

      function showCards(list) {
        list.forEach(function (f) {
          var card = document.createElement('div');
          card.className = 'hs-result';
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'hs-result-q';
          btn.setAttribute('aria-expanded', 'false');
          var icon = document.createElement('span');
          icon.className = 'hs-chevron';
          icon.setAttribute('aria-hidden', 'true');
          var q = document.createElement('span');
          q.className = 'hs-result-qtext';
          q.textContent = f.question;
          btn.appendChild(icon);
          btn.appendChild(q);
          var ans = document.createElement('div');
          ans.className = 'hs-result-answer';
          ans.hidden = true;
          ans.innerHTML = f.answerHtml;
          btn.addEventListener('click', function () {
            var open = ans.hidden;
            ans.hidden = !open;
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            card.classList.toggle('open', open);
            fitLanding();
          });
          card.appendChild(btn);
          card.appendChild(ans);
          resultsEl.appendChild(card);
        });
        fitLanding();
      }

      // On the landing page the panel is one scroll-snap screen, so only as many
      // rows as fit show (an opened row stays). Elsewhere all show.
      var landingPanel = document.querySelector('.landing-anchor--faq');
      function fitLanding() {
        if (!landingPanel) return;
        var cards = Array.prototype.slice.call(resultsEl.children);
        cards.forEach(function (c) { c.style.display = ''; });
        function overflows() {
          return landingPanel.getBoundingClientRect().height > window.innerHeight + 1;
        }
        for (var i = cards.length - 1; i > 0 && overflows(); i--) {
          if (!cards[i].classList.contains('open')) cards[i].style.display = 'none';
        }
      }
      window.addEventListener('resize', fitLanding);

      function render() {
        var q = input.value.trim();
        clearBtn.style.display = q ? '' : 'none';
        resultsEl.textContent = '';
        setStatus('');
        if (!q) {
          setNote('Search above via keyword or question, or visit our ' + DISCORD + '.');
          showCards(FAQ.filter(function (f) { return f.category === 'Getting Started'; }));
          return;
        }
        var res = search(q);
        if (!res.hits.length) {
          setNote('No matching results. Try again, or ask in our ' + DISCORD + '.');
          return;
        }
        setNote('Can\'t find an answer? Try asking in our ' + DISCORD + '.');
        setStatus(res.partial ? 'No exact matches \u2014 here are the closest ones.' : '');
        showCards(res.hits);
      }

      // Results appear after the visitor pauses typing; until then old results
      // are cleared and "Loading..." shows. Enter, Escape, Clear and an emptied
      // box skip the wait.
      var TYPING_PAUSE_MS = 1000;
      var typingTimer = null;
      function renderNow() {
        clearTimeout(typingTimer);
        typingTimer = null;
        render();
      }
      input.addEventListener('input', function () {
        clearTimeout(typingTimer);
        if (!input.value.trim()) { renderNow(); return; }
        resultsEl.textContent = '';
        setNote('');
        clearBtn.style.display = '';
        setStatus('Loading...');
        typingTimer = setTimeout(renderNow, TYPING_PAUSE_MS);
      });
      var HS_TOUCH = !!(window.matchMedia && window.matchMedia('(hover: none)').matches);
      if (HS_TOUCH) input.setAttribute('enterkeyhint', 'search');
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { input.value = ''; renderNow(); }
        else if (e.key === 'Enter') {
          renderNow();
          if (HS_TOUCH) input.blur();
        }
      });
      clearBtn.addEventListener('click', function () {
        input.value = ''; renderNow();
        if (HS_TOUCH) input.blur(); else input.focus();
      });
      render();
    })();
"""


_HELP_SUPPORT_HEAD = f'<link rel="stylesheet" href="/static/css/help-support.css?v={_HELP_SUPPORT_CSS_VERSION}" />'

# FAQ search box, results and notes, shared by Help & Support and the landing
# page's "GOT QUESTIONS?" panel.
_HELP_SUPPORT_SEARCH_MARKUP = """
    <div class="hs-search-group">
      <input type="text" class="hs-search" id="hsSearch" placeholder="Search the FAQ" autocomplete="off" />
      <button type="button" class="hs-search-clear" id="hsSearchClear" style="display:none;">Clear</button>
    </div>
    <p class="hs-status" id="hsStatus"></p>
    <div class="hs-results" id="hsResults"></div>
    <p class="hs-note" id="hsNote"></p>
"""


def _help_support_script() -> str:
    """The FAQ search script with the FAQ entries embedded."""
    faq_json = json.dumps(get_faq_items(), ensure_ascii=False).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return _HELP_SUPPORT_SCRIPT.replace("__FAQ_JSON__", faq_json)


def render_help_support(player: PlayerView) -> str:
    """The Help & Support page: a client-side search over the FAQ embedded in the
    page (app/faq.py, app/data/faq.json); see _HELP_SUPPORT_SCRIPT.
    """
    extra_head = _HELP_SUPPORT_HEAD
    script = _help_support_script()
    body = '<h2 class="page-title">Help &amp; Support</h2>' + _HELP_SUPPORT_SEARCH_MARKUP
    return _shell(
        title="Help & Support — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )


_SUMMARY_STATS = (
    # (element key, icon, alt text), all from /api/character-overview/summary
    # (GameAccount.character_summary_* plus account_type, synced by
    # MyscapeClient#syncCharacterSummary in myscape-plugin). For accountType the
    # script swaps icon and alt (see _ACCOUNT_TYPE_INFO).
    ("accountType", _ACCOUNT_TYPE_INFO["MAIN"][0], "Account type"),
    ("combatLevel", _ICON_SUMMARY_COMBAT_LEVEL, "Combat level"),
    ("totalLevel", _ICON_SUMMARY_TOTAL_LEVEL, "Total level"),
    ("totalXp", _ICON_SUMMARY_TOTAL_XP, "Total experience"),
    ("quests", _ICON_SUMMARY_QUESTS, "Quests completed"),
    ("achievements", _ICON_SUMMARY_ACHIEVEMENTS, "Achievements completed"),
    ("combatTasks", _ICON_SUMMARY_COMBAT_TASKS, "Combat tasks completed"),
    ("collections", _ICON_SUMMARY_COLLECTIONS, "Collections logged"),
)


_SKILL_GRID_ORDER = (
    # Row-major order for the 3x8 skill card in render_character_overview,
    # matching the in-game Skills tab. Sailing (the 24th skill) takes the slot
    # of the omitted "Total level" footer. SKILL_NAMES (app/mindmaps.py) is a
    # set, so this tuple holds the order.
    "attack", "hitpoints", "mining",
    "strength", "agility", "smithing",
    "defence", "herblore", "fishing",
    "ranged", "thieving", "cooking",
    "prayer", "crafting", "firemaking",
    "magic", "fletching", "woodcutting",
    "runecraft", "slayer", "farming",
    "construction", "hunter", "sailing",
)


# Backgrounds the shuffle button picks from (app/static/img/model-viewer-bg/):
# decorative, same for every player. Index 0 is the first-visit default; order
# otherwise doesn't matter.
_MODEL_VIEWER_BACKGROUNDS = (
    "/static/img/model-viewer-bg/castle-courtyard.jpg",
    "/static/img/model-viewer-bg/garden-bridge.jpg",
    "/static/img/model-viewer-bg/scene-01.jpg",
    "/static/img/model-viewer-bg/scene-02.jpg",
    "/static/img/model-viewer-bg/scene-03.jpg",
    "/static/img/model-viewer-bg/scene-04.jpg",
    "/static/img/model-viewer-bg/scene-05.jpg",
    "/static/img/model-viewer-bg/scene-06.jpg",
    "/static/img/model-viewer-bg/scene-07.jpg",
    "/static/img/model-viewer-bg/scene-08.jpg",
    "/static/img/model-viewer-bg/scene-09.jpg",
    "/static/img/model-viewer-bg/scene-10.jpg",
    "/static/img/model-viewer-bg/scene-11.jpg",
    "/static/img/model-viewer-bg/scene-12.jpg",
    "/static/img/model-viewer-bg/scene-13.jpg",
    "/static/img/model-viewer-bg/scene-14.jpg",
    "/static/img/model-viewer-bg/scene-15.jpg",
    "/static/img/model-viewer-bg/scene-16.jpg",
    "/static/img/model-viewer-bg/scene-17.jpg",
    "/static/img/model-viewer-bg/scene-18.jpg",
    "/static/img/model-viewer-bg/scene-19.jpg",
    "/static/img/model-viewer-bg/scene-20.jpg",
    "/static/img/model-viewer-bg/scene-21.jpg",
    "/static/img/model-viewer-bg/scene-22.jpg",
    "/static/img/model-viewer-bg/scene-23.jpg",
    "/static/img/model-viewer-bg/scene-24.jpg",
    "/static/img/model-viewer-bg/scene-25.jpg",
    "/static/img/model-viewer-bg/scene-26.jpg",
    "/static/img/model-viewer-bg/scene-27.jpg",
    "/static/img/model-viewer-bg/scene-28.jpg",
    "/static/img/model-viewer-bg/scene-29.jpg",
    "/static/img/model-viewer-bg/scene-30.jpg",
    "/static/img/model-viewer-bg/scene-31.jpg",
    "/static/img/model-viewer-bg/scene-32.jpg",
    "/static/img/model-viewer-bg/scene-33.jpg",
    "/static/img/model-viewer-bg/scene-34.jpg",
    "/static/img/model-viewer-bg/scene-35.jpg",
    "/static/img/model-viewer-bg/scene-36.jpg",
    "/static/img/model-viewer-bg/scene-37.jpg",
    "/static/img/model-viewer-bg/scene-38.jpg",
    "/static/img/model-viewer-bg/scene-39.jpg",
    "/static/img/model-viewer-bg/scene-40.jpg",
    "/static/img/model-viewer-bg/scene-41.jpg",
    "/static/img/model-viewer-bg/scene-42.jpg",
    "/static/img/model-viewer-bg/scene-43.jpg",
    "/static/img/model-viewer-bg/scene-44.jpg",
    "/static/img/model-viewer-bg/scene-45.jpg",
    "/static/img/model-viewer-bg/scene-46.jpg",
    "/static/img/model-viewer-bg/scene-47.jpg",
    "/static/img/model-viewer-bg/scene-48.jpg",
    "/static/img/model-viewer-bg/scene-49.jpg",
    "/static/img/model-viewer-bg/scene-50.jpg",
    "/static/img/model-viewer-bg/scene-51.jpg",
    "/static/img/model-viewer-bg/scene-52.jpg",
    "/static/img/model-viewer-bg/scene-53.jpg",
    "/static/img/model-viewer-bg/scene-54.jpg",
    "/static/img/model-viewer-bg/scene-55.jpg",
    "/static/img/model-viewer-bg/scene-56.jpg",
    "/static/img/model-viewer-bg/scene-57.jpg",
    "/static/img/model-viewer-bg/scene-58.jpg",
    "/static/img/model-viewer-bg/scene-59.jpg",
    "/static/img/model-viewer-bg/scene-60.jpg",
    "/static/img/model-viewer-bg/scene-61.jpg",
    "/static/img/model-viewer-bg/scene-62.jpg",
    "/static/img/model-viewer-bg/scene-63.jpg",
    "/static/img/model-viewer-bg/scene-64.jpg",
    "/static/img/model-viewer-bg/scene-65.jpg",
    "/static/img/model-viewer-bg/scene-66.jpg",
    "/static/img/model-viewer-bg/scene-67.jpg",
    "/static/img/model-viewer-bg/scene-68.jpg",
    "/static/img/model-viewer-bg/scene-69.jpg",
    "/static/img/model-viewer-bg/scene-70.jpg",
    "/static/img/model-viewer-bg/scene-71.jpg",
    "/static/img/model-viewer-bg/scene-72.jpg",
    "/static/img/model-viewer-bg/scene-73.jpg",
    "/static/img/model-viewer-bg/scene-74.jpg",
    "/static/img/model-viewer-bg/scene-75.jpg",
)

_MODEL_VIEWER_HEAD = """
<script type="importmap">
{
  "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.169.0/examples/jsm/"
  }
}
</script>
<script type="module">
  import * as THREE from "three";
  import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
  import { OrbitControls } from "three/addons/controls/OrbitControls.js";

  (function () {
    var wrap = document.getElementById("modelViewerCanvasWrap");
    var canvas = document.getElementById("modelViewerCanvas");
    var emptyEl = document.getElementById("modelViewerEmpty");
    if (!wrap || !canvas) return;

    var bgEl = document.getElementById("modelViewerBg");
    var bgShuffleBtn = document.getElementById("mvBgShuffleBtn");
    var playPauseBtn = document.getElementById("mvPlayPauseBtn");
    var playIcon = document.getElementById("mvPlayIcon");
    var pauseIcon = document.getElementById("mvPauseIcon");
    var resetBtn = document.getElementById("mvResetBtn");

    // Backdrop behind the alpha:true canvas, changed by the shuffle button; a
    // plain <div> since it never interacts with the three.js scene (see
    // .model-viewer-bg in character-overview.css).
    var MODEL_VIEWER_BACKGROUNDS = __MODEL_VIEWER_BACKGROUNDS_JSON__;
    // Persists the chosen background: localStorage for first paint, then the
    // account's saved pick (GameAccount.model_viewer_background_index, via
    // applyModelViewerBackgroundFromServer) so devices agree. A null key
    // (__MODEL_VIEWER_BG_STORAGE_KEY_JSON__) disables persistence; the landing
    // preview uses it to always start on index 0.
    var MODEL_VIEWER_BG_STORAGE_KEY = __MODEL_VIEWER_BG_STORAGE_KEY_JSON__;
    var bgIndex = 0;
    if (MODEL_VIEWER_BG_STORAGE_KEY) {
      try {
        var storedBgIndex = parseInt(localStorage.getItem(MODEL_VIEWER_BG_STORAGE_KEY), 10);
        if (!isNaN(storedBgIndex) && storedBgIndex >= 0 && storedBgIndex < MODEL_VIEWER_BACKGROUNDS.length) {
          bgIndex = storedBgIndex;
        }
      } catch (e) {
        // localStorage can throw (private browsing, disabled storage); the
        // index-0 default is fine then.
      }
    }

    function applyBackground() {
      if (bgEl && MODEL_VIEWER_BACKGROUNDS.length) {
        bgEl.style.backgroundImage = 'url("' + MODEL_VIEWER_BACKGROUNDS[bgIndex] + '")';
      }
    }
    applyBackground();

    function shuffleBackground() {
      if (MODEL_VIEWER_BACKGROUNDS.length < 2) return;
      var next = bgIndex;
      while (next === bgIndex) {
        next = Math.floor(Math.random() * MODEL_VIEWER_BACKGROUNDS.length);
      }
      bgIndex = next;
      applyBackground();
      if (MODEL_VIEWER_BG_STORAGE_KEY) {
        try {
          localStorage.setItem(MODEL_VIEWER_BG_STORAGE_KEY, String(bgIndex));
        } catch (e) {}
      }
      // Fire-and-forget sync to GameAccount.model_viewer_background_index so
      // public-profile visitors see the current pick (see
      // applyServerBackground). Requiring the real page's exact storage key
      // keeps this off the landing preview (null key) and public views (per-code
      // key).
      if (MODEL_VIEWER_BG_STORAGE_KEY === "myscape.modelViewerBgIndex") {
        fetch("/api/players/me/model-viewer-background", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ index: bgIndex }),
        }).catch(function () {
        });
      }
    }
    if (bgShuffleBtn) bgShuffleBtn.addEventListener("click", shuffleBackground);

    // Lets the wrapper script (outside this IIFE) push the owner's synced
    // background (from /api/public/<code>/summary) into the viewer. Only
    // render_public_character_overview's wrapper_script calls it, since public
    // visitors have no shuffle button or saved history.
    function applyModelViewerBackgroundFromServer(index) {
      if (typeof index !== "number" || isNaN(index) || index < 0 || index >= MODEL_VIEWER_BACKGROUNDS.length) {
        return;
      }
      bgIndex = index;
      applyBackground();
      // On the signed-in page, keep this browser's copy in step with the
      // account's so the next load doesn't flash a stale image first.
      if (MODEL_VIEWER_BG_STORAGE_KEY === "myscape.modelViewerBgIndex") {
        try {
          localStorage.setItem(MODEL_VIEWER_BG_STORAGE_KEY, String(index));
        } catch (e) {}
      }
    }
    window.myscapeApplyModelViewerBackground = applyModelViewerBackgroundFromServer;
    // This module script is deferred, but the wrapper's classic <script> runs
    // synchronously, so its fetch shim can call
    // window.myscapeApplyModelViewerBackground before it exists. The wrapper
    // also stashes the value in window.__myscapePendingModelViewerBg for this to
    // pick up, so whichever finishes second wins.
    if (typeof window.__myscapePendingModelViewerBg !== "undefined") {
      applyModelViewerBackgroundFromServer(window.__myscapePendingModelViewerBg);
    }

    // Syncs the play/pause button's SVGs and title/aria-label with a boolean;
    // shared by the play/pause and reset buttons (wired in initViewer).
    function setPlayPauseIcon(paused) {
      // `.hidden = x` is a no-op on inline <svg> in some browsers (it only
      // creates an expando), so set/remove the real attribute that the [hidden]
      // UA rule uses.
      function setHidden(el, isHidden) {
        if (!el) return;
        if (isHidden) el.setAttribute("hidden", "");
        else el.removeAttribute("hidden");
      }
      setHidden(playIcon, !paused);
      setHidden(pauseIcon, paused);
      if (playPauseBtn) {
        var label = paused ? "Play rotation" : "Pause rotation";
        playPauseBtn.setAttribute("data-tooltip", label);
        playPauseBtn.setAttribute("aria-label", label);
      }
    }

    function showEmpty(message) {
      wrap.style.display = "none";
      if (emptyEl) {
        if (message) emptyEl.textContent = message;
        emptyEl.style.display = "block";
      }
    }

    // GET /api/character-overview/model (app/main.py) serves the .glb uploaded
    // by MyscapeClient#syncCharacterModel; 404 until the plugin's "Export 3D
    // model" has been used. The landing preview substitutes a static URL via
    // __MODEL_VIEWER_MODEL_URL_JSON__ (see _character_overview_panel_markup), so
    // it needs no fetch shim.
    var MODEL_VIEWER_MODEL_URL = __MODEL_VIEWER_MODEL_URL_JSON__;
    fetch(MODEL_VIEWER_MODEL_URL)
      .then(function (r) {
        if (r.status === 404) {
          // No captured model: fall back to a shared static default model so the
          // viewer always shows something. The info popup explains how to
          // replace it.
          return fetch("/static/models/default-character.glb").then(function (r2) {
            return r2.ok ? r2.arrayBuffer() : Promise.reject();
          });
        }
        return r.ok ? r.arrayBuffer() : Promise.reject();
      })
      .then(function (buffer) {
        if (buffer) initViewer(buffer);
      })
      .catch(function (err) {
        // Log the real failure reason (network error, bad response) so a missing
        // model is diagnosable.
        if (window.console) console.error("[model-viewer] failed to fetch the model:", err);
        showEmpty("Could not load your 3D model right now.");
      });

    function initViewer(buffer) {
      var scene = new THREE.Scene();

      var camera = new THREE.PerspectiveCamera(35, wrap.clientWidth / wrap.clientHeight, 0.1, 1000);
      camera.position.set(0, 1.6, 3.2);

      var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(wrap.clientWidth, wrap.clientHeight);

      // A lost WebGL context (driver reset, too many contexts) would leave the
      // canvas blank with no sign. event.preventDefault() in the lost handler
      // lets the browser restore it; three.js re-uploads on the next render, so
      // restore only logs.
      var contextLost = false;
      canvas.addEventListener("webglcontextlost", function (event) {
        event.preventDefault();
        contextLost = true;
        if (window.console) console.warn("[model-viewer] WebGL context lost -- waiting to see if the browser restores it");
      });
      canvas.addEventListener("webglcontextrestored", function () {
        contextLost = false;
        if (window.console) console.warn("[model-viewer] WebGL context restored -- resuming rendering");
      });

      var controls = new OrbitControls(camera, renderer.domElement);
      controls.target.set(0, 1, 0);
      controls.enableDamping = true;
      // Panning is off: right-click would pan the camera off the character.
      controls.enablePan = false;
      // Zoom is off: the camera is framed once at a fixed distance.
      controls.enableZoom = false;
      // Dragging is off since autoRotate drives the camera (the canvas cursor
      // rule in character-overview.css drops the grab cursor too).
      controls.enableRotate = false;
      // Slow continuous spin instead of user orbit. autoRotate only turns the
      // azimuth, so DEFAULT_VERTICAL_TILT holds. It ignores enableRotate but
      // respects min/maxAzimuthAngle (left unset for a full revolution), and is
      // paced by elapsed time, independent of refresh rate.
      controls.autoRotate = true;
      var ROTATION_SECONDS_PER_REVOLUTION = 45;
      controls.autoRotateSpeed = 60 / ROTATION_SECONDS_PER_REVOLUTION;

      var loader = new GLTFLoader();
      loader.parse(
        buffer,
        "",
        function (gltf) {
          var model = gltf.scene;
          scene.add(model);

          // Per-face render-priority handling. OSRS paints faces in priority
          // order rather than depth-testing, so gear modeled flush against the
          // body (cape, necklace) can sit slightly inside what it layers on and
          // still draw on top. The export (ModelMeshBuilder/GlbWriter in
          // myscape-plugin) carries each primitive's priority as glTF extras,
          // which GLTFLoader copies onto geometry.userData.
          //
          // To emulate that, nudge each tagged primitive's view-space Z by a
          // fixed world-unit amount via a vertex-shader patch
          // (Material#onBeforeCompile), keeping the depth test on so unrelated
          // gaps stay ordered. renderOrder only breaks exact ties, depthTest =
          // false breaks self-occlusion, and polygonOffset uses non-linear
          // units. This is RuneProfile's technique
          // (packages/model-renderer/src/priority-offset.ts), with one
          // per-material uniform instead of a per-vertex attribute since the
          // exporter splits each (texture, priority, bias, translucent)
          // combination into its own primitive.
          //
          // Step and cap are RuneProfile's tuned constants: 3 game units per
          // priority step, capped at 6 steps. No 1/128 root scale here, so the
          // raw game-unit step is used. The missing-texture dimming below is
          // unrelated to priority.
          var PRIORITY_STEP_GAME_UNITS = 3.0;
          var PRIORITY_MAX_STEPS = 6;
          // Fixed, not user-adjustable: half of RuneProfile's tuned 1.0, for a
          // gentler nudge.
          var PRIORITY_NUDGE_MULTIPLIER = 0.5;

          function applyPriorityNudge(material, nudge) {
            material.onBeforeCompile = function (shader) {
              shader.uniforms.uPriorityNudge = { value: nudge };
              shader.vertexShader = shader.vertexShader
                .replace(
                  "#include <common>",
                  "#include <common>\\nuniform float uPriorityNudge;"
                )
                .replace(
                  "#include <project_vertex>",
                  [
                    "vec4 mvPosition = vec4( transformed, 1.0 );",
                    "#ifdef USE_BATCHING",
                    "	mvPosition = batchingMatrix * mvPosition;",
                    "#endif",
                    "#ifdef USE_INSTANCING",
                    "	mvPosition = instanceMatrix * mvPosition;",
                    "#endif",
                    "mvPosition = modelViewMatrix * mvPosition;",
                    // View space looks down -Z, so adding moves the vertex
                    // toward the camera.
                    "mvPosition.z += uPriorityNudge;",
                    "gl_Position = projectionMatrix * mvPosition;",
                  ].join("\\n")
                );
            };
            // Three keys its program cache on shader source, which
            // onBeforeCompile changes identically for every nudged material, so
            // a constant key shares one program.
            material.customProgramCacheKey = function () {
              return "osrs-priority-nudge";
            };
            material.needsUpdate = true;
          }

          model.traverse(function (node) {
            if (!node.isMesh || !node.geometry) return;
            if (node.material) {
              // GlbWriter always exports doubleSided: true, but the OSRS client
              // culls back faces, and thin cloth (a cape) is two coincident,
              // oppositely wound surfaces where culling picks the right one.
              // Double-sided z-fights them, so force FrontSide (as RuneProfile's
              // load-model.ts does), plus the depthWrite fix below.
              node.material.side = THREE.FrontSide;
              if (node.material.transparent) {
                node.material.depthWrite = false;
              }
            }
            if (!node.geometry.userData) return;
            var priority = node.geometry.userData.osrsPriority || 0;
            var bias = node.geometry.userData.osrsBias || 0;
            var missingTexture = !!node.geometry.userData.missingTexture;
            if ((priority !== 0 || bias !== 0 || missingTexture) && node.material) {
              node.material = node.material.clone();
              if (priority !== 0 || bias !== 0) {
                if (priority !== 0) {
                  var nudge = Math.min(priority, PRIORITY_MAX_STEPS) * PRIORITY_STEP_GAME_UNITS * PRIORITY_NUDGE_MULTIPLIER;
                  applyPriorityNudge(node.material, nudge);
                }
                if (window.console) {
                  console.log("[osrs-priority-debug]", {
                    name: node.name || "(unnamed)",
                    priority: priority,
                    bias: bias,
                  });
                }
              }
              if (missingTexture) {
                // The plugin couldn't capture this primitive's texture (see
                // GlbWriter/ModelExporter), leaving only COLOR_0 (lightness, no
                // hue): a bright near-white patch. Mute it to dim gray so it
                // reads as an unknown texture. Rarely triggers.
                node.material.color.setRGB(0.35, 0.35, 0.35);
                if (window.console) {
                  console.log("[osrs-missing-texture]", { name: node.name || "(unnamed)" });
                }
              }
            }
          });

          // Translucent draw order. Translucent primitives have depthWrite=false
          // and share one origin, so three.js draws them in creation order and
          // the last drawn lands on top even if behind (e.g. the Bow of
          // Faerdhinen's limbs behind translucent armor). As RuneProfile does,
          // fold every plain translucent primitive into one mesh and re-sort its
          // triangles back-to-front each draw; the priority nudge becomes a
          // per-vertex attribute and part of the sort key. Textured ones, and
          // any a merged mesh can't carry, are left as they were.
          (function mergeTranslucent() {
            var candidates = [];
            model.traverse(function (node) {
              if (!node.isMesh || !node.geometry || !node.material) return;
              var m = node.material;
              if (Array.isArray(m) || !m.transparent || m.map) return;
              var g = node.geometry;
              if (!g.attributes.position || !g.attributes.color) return;
              if (g.userData && g.userData.missingTexture) return;
              if (!node.parent || !node.matrix.equals(new THREE.Matrix4())) return;
              candidates.push(node);
            });
            if (candidates.length < 2) return;
            var parent = candidates[0].parent;
            candidates = candidates.filter(function (n) { return n.parent === parent; });
            if (candidates.length < 2) return;

            var positions = [];
            var colors = [];
            var nudges = [];
            var tris = [];
            var base = 0;
            candidates.forEach(function (node) {
              var g = node.geometry;
              var p = g.attributes.position;
              var c = g.attributes.color;
              var m = node.material;
              var priority = (g.userData && g.userData.osrsPriority) || 0;
              var nudge = Math.min(priority, PRIORITY_MAX_STEPS) * PRIORITY_STEP_GAME_UNITS * PRIORITY_NUDGE_MULTIPLIER;
              for (var i = 0; i < p.count; i++) {
                positions.push(p.getX(i), p.getY(i), p.getZ(i));
                colors.push(
                  c.getX(i) * m.color.r,
                  c.getY(i) * m.color.g,
                  c.getZ(i) * m.color.b,
                  (c.itemSize === 4 ? c.getW(i) : 1) * m.opacity
                );
                nudges.push(nudge);
              }
              var idx = g.index;
              var count = idx ? idx.count : p.count;
              for (var j = 0; j < count; j += 3) {
                tris.push(idx
                  ? [base + idx.getX(j), base + idx.getX(j + 1), base + idx.getX(j + 2)]
                  : [base + j, base + j + 1, base + j + 2]);
              }
              base += p.count;
            });
            if (!tris.length) return;

            var geometry = new THREE.BufferGeometry();
            geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
            geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 4));
            geometry.setAttribute("aPriorityNudge", new THREE.Float32BufferAttribute(nudges, 1));
            var indexArray = new Uint32Array(tris.length * 3);
            var indexAttr = new THREE.BufferAttribute(indexArray, 1);
            indexAttr.setUsage(THREE.DynamicDrawUsage);
            geometry.setIndex(indexAttr);

            var material = candidates[0].material.clone();
            material.color.setRGB(1, 1, 1);
            material.opacity = 1;
            material.side = THREE.FrontSide;
            material.transparent = true;
            material.depthWrite = false;
            material.vertexColors = true;
            material.onBeforeCompile = function (shader) {
              shader.vertexShader = shader.vertexShader
                .replace(
                  "#include <common>",
                  "#include <common>\\nattribute float aPriorityNudge;"
                )
                .replace(
                  "#include <project_vertex>",
                  [
                    "vec4 mvPosition = vec4( transformed, 1.0 );",
                    "mvPosition = modelViewMatrix * mvPosition;",
                    "mvPosition.z += aPriorityNudge;",
                    "gl_Position = projectionMatrix * mvPosition;",
                  ].join("\\n")
                );
            };
            material.customProgramCacheKey = function () {
              return "osrs-priority-nudge-attr";
            };
            material.needsUpdate = true;

            var triCount = tris.length;
            var centroids = new Float32Array(triCount * 3);
            var triNudge = new Float32Array(triCount);
            for (var t = 0; t < triCount; t++) {
              var a = tris[t][0], b = tris[t][1], d = tris[t][2];
              for (var k = 0; k < 3; k++) {
                centroids[t * 3 + k] = (positions[a * 3 + k] + positions[b * 3 + k] + positions[d * 3 + k]) / 3;
              }
              triNudge[t] = (nudges[a] + nudges[b] + nudges[d]) / 3;
            }
            var order = new Array(triCount);
            var depth = new Float32Array(triCount);
            var viewMatrix = new THREE.Matrix4();
            var lastView = new Float32Array(16);

            var merged = new THREE.Mesh(geometry, material);
            merged.name = "translucent_merged";
            merged.frustumCulled = false;
            merged.onBeforeRender = function (renderer, sceneArg, camera) {
              viewMatrix.multiplyMatrices(camera.matrixWorldInverse, merged.matrixWorld);
              var e = viewMatrix.elements;
              var same = true;
              for (var q = 0; q < 16; q++) {
                if (e[q] !== lastView[q]) { same = false; break; }
              }
              if (same) return;
              for (var q2 = 0; q2 < 16; q2++) lastView[q2] = e[q2];
              for (var i2 = 0; i2 < triCount; i2++) {
                order[i2] = i2;
                depth[i2] = e[2] * centroids[i2 * 3] + e[6] * centroids[i2 * 3 + 1] + e[10] * centroids[i2 * 3 + 2] + e[14] + triNudge[i2];
              }
              // View space looks down -Z: the most negative value is farthest,
              // drawn first.
              order.sort(function (x, y) { return depth[x] - depth[y]; });
              for (var i3 = 0; i3 < triCount; i3++) {
                var tri = tris[order[i3]];
                indexArray[i3 * 3] = tri[0];
                indexArray[i3 * 3 + 1] = tri[1];
                indexArray[i3 * 3 + 2] = tri[2];
              }
              indexAttr.needsUpdate = true;
            };

            candidates.forEach(function (node) {
              parent.remove(node);
              node.geometry.dispose();
              if (node.material && node.material.dispose) node.material.dispose();
            });
            parent.add(merged);
          })();

          // Frame the camera to the model's real bounding box with the standard
          // "fit object in view" distance, which works in any units. The export
          // origin isn't guaranteed to be the visual midpoint, so center/size
          // come from the geometry.
          var box = new THREE.Box3().setFromObject(model);
          var size = box.getSize(new THREE.Vector3());
          var center = box.getCenter(new THREE.Vector3());

          // Snug fit: zoom is disabled, so this is the only view. Each axis is
          // fit against its own extent (size.y vs the vertical FOV, size.x vs
          // the horizontal FOV via aspect); one largest-dimension value would
          // over-pad portrait viewports.
          var vFovHalfTan = Math.tan((Math.PI * camera.fov) / 360);
          var fitHeightDistance = Math.max(size.y, 1e-6) / (2 * vFovHalfTan);
          var fitWidthDistance = Math.max(size.x, 1e-6) / (2 * vFovHalfTan * camera.aspect);
          // 1.3 rather than a snug 1.15, leaving room for the button row
          // (.model-viewer-controls) inside the same frame.
          var CAMERA_DISTANCE_MULTIPLIER = 1.3;
          var distance = CAMERA_DISTANCE_MULTIPLIER * Math.max(fitHeightDistance, fitWidthDistance);

          // Orbit around and frame on the bounding box's geometric center.
          controls.target.copy(center);

          // Default view tilted 10 degrees down from level (polar angle below
          // 90) so more of the head top reads.
          var DEFAULT_VERTICAL_TILT = (10 * Math.PI) / 180;
          var defaultSpherical = new THREE.Spherical(distance, Math.PI / 2 - DEFAULT_VERTICAL_TILT, 0);
          camera.position.setFromSpherical(defaultSpherical).add(center);

          camera.near = distance / 100;
          camera.far = distance * 100;
          camera.updateProjectionMatrix();

          // Pan the image up via a 2D projection shift (applyVerticalFramePan,
          // near onResize), not by moving camera.position/controls.target, which
          // changes the viewing angle. setViewOffset leaves the 3D camera, and
          // what reset/pause freeze to, untouched while clearing space for
          // .model-viewer-controls.
          applyVerticalFramePan();

          // No orbit limits: nothing drags the camera, and unclamped azimuth
          // lets autoRotate complete a full revolution (DEFAULT_VERTICAL_TILT
          // holds since only azimuth changes).
          controls.update();

          // Snapshot of the framed view (post vertical shift) for the reset
          // button.
          var defaultCameraPosition = camera.position.clone();
          var defaultTarget = controls.target.clone();

          // enableDamping keeps autoRotate momentum alive briefly after it
          // switches off, which would read as a coast after pause or an offset
          // after reset. One extra update() with damping off consumes the whole
          // pending delta; damping is then restored.
          function killDampingMomentum() {
            var wasDamping = controls.enableDamping;
            controls.enableDamping = false;
            controls.update();
            controls.enableDamping = wasDamping;
          }

          if (playPauseBtn) {
            playPauseBtn.addEventListener("click", function () {
              controls.autoRotate = !controls.autoRotate;
              if (!controls.autoRotate) killDampingMomentum();
              setPlayPauseIcon(!controls.autoRotate);
            });
          }
          if (resetBtn) {
            resetBtn.addEventListener("click", function () {
              // Drain leftover autoRotate momentum against the current position
              // first, or update() would apply a stale delta on top of the reset
              // position.
              controls.autoRotate = false;
              killDampingMomentum();
              camera.position.copy(defaultCameraPosition);
              controls.target.copy(defaultTarget);
              // Reset also pauses; spinning away again immediately would defeat
              // the point.
              setPlayPauseIcon(true);
              controls.update();
            });
          }
        },
        undefined,
        function (err) {
          // As with the fetch-level catch above: GLTFLoader passes the real
          // parse error here; log it.
          if (window.console) console.error("[model-viewer] GLTFLoader failed to parse the model:", err);
          showEmpty("Could not display your 3D model right now.");
        }
      );

      // Fraction of canvas height to pan the image up via camera.setViewOffset
      // (a post-projection shift). Passing width/height as both full frame and
      // visible size, with only offsetY nonzero, avoids any scaling.
      var VERTICAL_FRAME_PAN_FRACTION = 0.03;
      function applyVerticalFramePan() {
        var w = wrap.clientWidth;
        var h = wrap.clientHeight;
        if (w <= 0 || h <= 0) return;
        camera.setViewOffset(w, h, 0, h * VERTICAL_FRAME_PAN_FRACTION, w, h);
      }

      function onResize() {
        var w = wrap.clientWidth;
        var h = wrap.clientHeight;
        if (w <= 0 || h <= 0) return;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
        applyVerticalFramePan();
      }
      window.addEventListener("resize", onResize);

      // animateFailed latches the first time a frame throws (context loss is
      // handled via contextLost): log once and freeze on the last good frame
      // rather than throwing every frame.
      var animateFailed = false;
      (function animate() {
        requestAnimationFrame(animate);
        if (contextLost || animateFailed) return;
        try {
          controls.update();
          renderer.render(scene, camera);
        } catch (err) {
          animateFailed = true;
          if (window.console) console.error("[model-viewer] render loop failed:", err);
        }
      })();
    }
  })();
</script>
"""


def _character_overview_panel_markup(preview: bool = False, public_code: Optional[str] = None, public_character_name: Optional[str] = None) -> Tuple[str, str, str]:
    """Character Overview's real body/script, split out so the landing preview
    (render_landing_character_overview_preview) can reuse it verbatim.
    render_character_overview is this plus a _shell(...) call.
    
    preview=True (landing preview only) renders the same six sections; only
    two extra_head _MODEL_VIEWER_HEAD substitutions differ (background storage
    key and model-fetch URL), so the viewer opens on the default courtyard
    with the frozen demo model.
    
    public_code (render_public_character_overview only, never with preview)
    points those substitutions at another account's live model: GET
    /api/public/<code>/model and a per-code background key
    (myscape.modelViewerBgIndex.public.<code>). The owner-only settings card
    (public_profile_settings_btn) is omitted here and in preview.
    
    public_character_name (only with public_code) replaces the <h2> with the
    visited character's name; it is escape()'d like other player-controlled
    strings.
    
    Summary row (.co-summary-row): eight icon+stat pairs (_SUMMARY_STATS), alt
    text as hover tooltip (accountType excepted, see _ACCOUNT_TYPE_INFO).
    Values start as em dashes and are filled from
    /api/character-overview/summary. Combat level is rounded and total level
    has no thousands separator, unlike formatInt.
    
    Skills card (.skills-card in .co-left-col): 3x8 grid of .skill-cell in
    _SKILL_GRID_ORDER, each level a fixed 3ch wide. Shows VIRTUAL levels
    (levelForXp; xp table duplicated from Mindmaps), so maxed reads 126. Icons
    are app/static/skill-icons; data from GET /api/players/me/skills. Cells
    link to the wiki in a new tab; data-tooltip (.myscape-tooltip, _shell's
    shared_script) starts as the skill name and gains XP in setSkillTooltip.
    
    The collection log card (.clog-card) sits beside .co-left-col in
    .co-main-row; see character-overview.css.
    """
    stat_tiles = "\n      ".join(
        f"""<div class="co-stat">
        <img class="co-stat-icon" src="{escape(icon)}" alt="{escape(alt)}" data-tooltip="{escape(alt)}" {f'id="co-icon-{key}"' if key == "accountType" else ""} />
        <div class="co-stat-value" id="co-{key}">&mdash;</div>
      </div>"""
        for key, icon, alt in _SUMMARY_STATS
    )

    skill_cells = "\n      ".join(
        f"""<a class="skill-cell" id="skill-cell-{key}" data-tooltip="{key.capitalize()}" href="https://oldschool.runescape.wiki/w/{key.capitalize()}" target="_blank" rel="noopener">
        <img class="skill-cell-icon" src="/static/skill-icons/{key}.png" alt="{key.capitalize()}" />
        <span class="skill-cell-level" id="skill-{key}">&mdash;</span>
      </a>"""
        for key in _SKILL_GRID_ORDER
    )

    # Skills/Quests/Achievement Diaries/Combat Achievements (.co-quad-row)
    # render unconditionally, including in the landing preview, whose fetch shim
    # answers GET /api/character-overview/progress and /api/players/me/skills
    # (DEMO_PROGRESS / DEMO_SKILLS).
    quad_row_section = f"""
    <div class="co-quad-row" id="coQuadRow">
      <div class="skills-card" id="skillsCard">
        <div class="skills-grid">
          {skill_cells}
        </div>
      </div>

      <div class="quests-card" id="questsCard">
        <div class="quests-empty" id="questsEmpty">No quest data yet &mdash; open your quest list in-game with the myscape RuneLite plugin running, then refresh this page.</div>
        <div class="quests-list" id="questsList"></div>
      </div>

      <div class="diaries-card" id="diariesCard">
        <div class="diaries-list" id="diariesList"></div>
      </div>

      <div class="ca-card" id="caCard">
        <div class="ca-list" id="caList"></div>
      </div>
    </div>"""

    # The "i" tooltip and shuffle-background buttons are omitted for public_code
    # visitors (kept in preview as marketing): the plugin hint doesn't apply to
    # them and shuffling only changes their local pick. Omitting the markup is
    # safe because the script guards `if (bgShuffleBtn)`; the "i" button needs
    # no guard since its data-tooltip is read by the shared hover listener.
    mv_info_btn = "" if public_code else '<button class="model-viewer-btn" id="mvInfoBtn" type="button" data-tooltip="Set your character model in the myscape\nplugin sidebar on RuneLite." aria-label="Set your character model in the myscape\nplugin sidebar on RuneLite."><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="11"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg></button>'
    mv_shuffle_btn = "" if public_code else '<button class="model-viewer-btn" id="mvBgShuffleBtn" type="button" data-tooltip="Shuffle background" aria-label="Shuffle background"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 3 21 3 21 8"></polyline><line x1="4" y1="20" x2="21" y2="3"></line><polyline points="21 16 21 21 16 21"></polyline><line x1="15" y1="15" x2="21" y2="21"></line><line x1="4" y1="4" x2="9" y2="9"></line></svg></button>'

    # Owner's settings cog, absent in preview and public_code modes. The script
    # guards on `if (publicProfileSettingsBtn)`. Looks like the Storages
    # Viewer's .pm-settings-btn (see .co-settings-btn in character-overview.css)
    # and is a cog because it is opened rarely. The private/public card is
    # appended to this same wrap span below.
    public_profile_settings_btn = "" if (preview or public_code) else (
        ' <span class="co-settings-wrap">'
        '<button type="button" class="co-settings-btn" id="publicProfileSettingsBtn" aria-label="Public profile settings" data-tooltip="Public profile settings">'
        '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M8.65 6.20 L9.54 2.82 L14.46 2.82 L15.35 6.20 L18.72 5.28 L21.18 9.54 L18.70 12.00 L21.18 14.46 L18.72 18.72 L15.35 17.80 L14.46 21.18 L9.54 21.18 L8.65 17.80 L5.28 18.72 L2.82 14.46 L5.30 12.00 L2.82 9.54 L5.28 5.28 Z"></path>'
        '<circle cx="12" cy="12" r="3.1"></circle>'
        '</svg></button>'
    )

    # Public visitors see the character's name instead of "Character Overview".
    page_heading = escape(public_character_name) if public_character_name else "Character Overview"

    # Floats under the cog (position: absolute, see .public-profile-card in
    # character-overview.css) as a sibling of publicProfileSettingsBtn in
    # .co-settings-wrap. PRIVATE/PUBLIC segmented control (markup duplicated
    # from Mindmaps' .mm-segment-group), a readonly link field and two buttons.
    if not (preview or public_code):
        public_profile_settings_btn += (
            '<div class="public-profile-card" id="publicProfileCard" hidden>'
            '<div class="public-profile-seg-group">'
            '<button type="button" class="public-profile-seg-btn active" id="publicProfileSegPrivate" data-segment-value="private" data-tooltip="Makes your profile invisible to everyone\n(except those on your friends list)" data-tooltip-wide>Private</button>'
            '<button type="button" class="public-profile-seg-btn" id="publicProfileSegPublic" data-segment-value="public" data-tooltip="Makes your profile visible\nto anyone with your URL">Public</button>'
            '</div>'
            '<button type="button" class="public-profile-link-btn public-profile-link-display" id="publicProfileLinkBtn" disabled></button>'
            '<button class="public-profile-link-btn" id="publicProfileRegenerateBtn" type="button" data-tooltip="Generating a new link will render your old link\nobsolete. You can do this once every 24 hours.">Generate new link</button>'
            '</div>'
            '</span>'
        )

    body = f"""
    <h2 class="page-title">{page_heading}{public_profile_settings_btn}</h2>

    <div class="co-summary-row" id="coSummaryRow">
      {stat_tiles}
    </div>

    <div class="co-main-row">
      <div class="co-left-col">
        <div class="model-viewer-card" id="modelViewerCard">
          <div class="model-viewer-canvas-wrap" id="modelViewerCanvasWrap">
            <div class="model-viewer-bg" id="modelViewerBg"></div>
            <canvas id="modelViewerCanvas"></canvas>
            <div class="model-viewer-controls" id="modelViewerControls">
              {mv_info_btn}
              {mv_shuffle_btn}
              <button class="model-viewer-btn" id="mvPlayPauseBtn" type="button" data-tooltip="Pause rotation" aria-label="Pause rotation"><svg id="mvPlayIcon" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none" hidden><polygon points="6 3 20 12 6 21 6 3"></polygon></svg><svg id="mvPauseIcon" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg></button>
              <button class="model-viewer-btn" id="mvResetBtn" type="button" data-tooltip="Reset rotation" aria-label="Reset rotation"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg></button>
            </div>
          </div>
          <div class="model-viewer-empty" id="modelViewerEmpty">No 3D model captured yet &mdash; use the &ldquo;Export 3D model&rdquo; button in the myscape RuneLite plugin&rsquo;s sidebar, then refresh this page.</div>
        </div>
      </div>

      <div class="clog-card" id="clogCard">
        <div class="clog-empty" id="clogEmpty">No collection log data yet &mdash; open your collection log in-game with the myscape RuneLite plugin running, then refresh this page.</div>
        <div class="clog-body" id="clogBody">
          <div class="clog-toolbar">
            <div class="clog-tabs-wrap" id="clogTabsWrap">
              <div class="clog-tabs" id="clogTabs"></div>
              <span class="clog-tabs-arrow clog-tabs-arrow--left" aria-hidden="true"></span>
              <span class="clog-tabs-arrow clog-tabs-arrow--right" aria-hidden="true"></span>
            </div>
            <button class="clog-sync-btn" id="clogSyncBtn" type="button" data-tooltip="Refresh kill counts from official hiscores"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg></button>
          </div>
          <div class="clog-panes">
            <div class="clog-pages" id="clogPages"></div>
            <div class="clog-items-col" id="clogItemsCol">
              <div class="clog-items-header" id="clogItemsHeader"></div>
              <div class="clog-items" id="clogItems"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
    {quad_row_section}
    """

    script = """
    (function () {
      function formatInt(n) {
        return Math.round(n || 0).toLocaleString('en-US');
      }
      // Like formatInt but without thousands separators (combat/total level).
      function formatIntPlain(n) {
        return String(Math.round(n || 0));
      }
      function setStat(key, text) {
        var el = document.getElementById('co-' + key);
        if (el) el.textContent = text;
      }
      function setFraction(key, completed, total) {
        if (completed == null || total == null) return;
        setStat(key, formatInt(completed) + ' / ' + formatInt(total));
      }
      // (icon url, label) per GameAccount.account_type code, see
      // _ACCOUNT_TYPE_INFO in app/pages.py. The accountType tile is the only one
      // whose icon is swapped; MAIN's coin icon is the pre-fetch default.
      var ACCOUNT_TYPE_INFO = __ACCOUNT_TYPE_INFO_JSON__;
      function setAccountType(code) {
        var info = code != null ? ACCOUNT_TYPE_INFO[code] : null;
        if (!info) return;
        var icon = document.getElementById('co-icon-accountType');
        if (icon) {
          icon.src = info[0];
          icon.alt = info[1];
          // data-tooltip is not swapped: it always reads the fixed "Account
          // type" label from the static markup (stat_tiles).
        }
        setStat('accountType', info[1]);
      }
      // OSRS xp-per-level curve for levels 1-126 (virtual levels past 99): xp(L)
      // = floor(1/4 * sum[l=1..L-1] of floor(l + 300*2^(l/7))), see
      // https://oldschool.runescape.wiki/w/Experience. Duplicated from
      // SKILL_XP_TABLE in Mindmaps' script. Index 0 is unused; SKILL_XP_TABLE[1]
      // is 0.
      var SKILL_XP_TABLE = (function () {
        var table = [0, 0];
        var cumulative = 0;
        for (var l = 1; l < 126; l++) {
          cumulative += Math.floor(l + 300 * Math.pow(2, l / 7));
          table[l + 1] = Math.floor(cumulative / 4);
        }
        return table;
      })();
      // Largest (virtual) level whose requirement is at or below xp, like
      // levelForXp in Mindmaps' script. Used instead of GameAccount.skills'
      // capped level so maxed skills read 126.
      function levelForXp(xp) {
        for (var l = 126; l >= 1; l--) {
          if (xp >= SKILL_XP_TABLE[l]) return l;
        }
        return 1;
      }
      function setSkillLevel(key, xp) {
        if (xp == null) return;
        var el = document.getElementById('skill-' + key);
        if (el) el.textContent = String(levelForXp(xp));
      }
      // Appends XP to the cell's data-tooltip (skill name from skill_cells in
      // app/pages.py) with the usual middle-dot join.
      function setSkillTooltip(key, xp) {
        var el = document.getElementById('skill-cell-' + key);
        if (!el) return;
        var name = key.charAt(0).toUpperCase() + key.slice(1);
        el.setAttribute('data-tooltip', xp != null ? name + ' · ' + formatInt(xp) + ' xp' : name);
      }

      fetch('/api/character-overview/summary')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data) return;
          // The shuffled background is saved on the account (the shuffle button
          // POSTs it) so all devices agree; localStorage only covers first
          // paint. The pending value covers this response arriving before the
          // viewer's module script runs (__myscapePendingModelViewerBg).
          if (typeof data.modelViewerBackgroundIndex === 'number') {
            window.__myscapePendingModelViewerBg = data.modelViewerBackgroundIndex;
            if (typeof window.myscapeApplyModelViewerBackground === 'function') {
              window.myscapeApplyModelViewerBackground(data.modelViewerBackgroundIndex);
            }
          }
          setAccountType(data.accountType);
          if (data.combatLevel != null) setStat('combatLevel', formatIntPlain(data.combatLevel));
          if (data.totalLevel != null) setStat('totalLevel', formatIntPlain(data.totalLevel));
          if (data.totalXp != null) setStat('totalXp', formatInt(data.totalXp) + ' xp');
          setFraction('quests', data.questsCompleted, data.questsTotal);
          setFraction('achievements', data.achievementsCompleted, data.achievementsTotal);
          setFraction('combatTasks', data.combatTasksCompleted, data.combatTasksTotal);
          setFraction('collections', data.collectionsCompleted, data.collectionsTotal);
        })
        .catch(function () { /* leave this row's em dashes showing */ });

      // Same GameAccount.skills snapshot the Mindmaps/Goal Tracking skill picker
      // reads (/api/players/me/skills in app/main.py).
      fetch('/api/players/me/skills')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data || !data.skills) return;
          Object.keys(data.skills).forEach(function (key) {
            var entry = data.skills[key];
            if (!entry) return;
            setSkillLevel(key, entry.xp);
            setSkillTooltip(key, entry.xp);
          });
        })
        .catch(function () { /* leave this card's em dashes showing */ });

      // Collection Log (GET /api/players/me/collection-log)

      // Quests / Achievement Diaries / Combat Achievements: one GET
      // /api/character-overview/progress feeds all three .co-quad-row cards (see
      // its docstring in app/main.py).

      // Same convention as the Mindmaps goal editor's diary-area search
      // (render_mindmaps); duplicated since the page scripts are independent.
      var DIARY_AREA_LABELS = {
        ardougne: 'Ardougne', desert: 'Desert', falador: 'Falador',
        fremennik: 'Fremennik', kandarin: 'Kandarin', karamja: 'Karamja',
        kourend_kebos: 'Kourend & Kebos', lumbridge_draynor: 'Lumbridge & Draynor',
        morytania: 'Morytania', varrock: 'Varrock',
        western_provinces: 'Western Provinces', wilderness: 'Wilderness',
      };
      // Each area's "Main reward" icon per tier (easy/medium/hard/elite,
      // matching DIARY_TIER_ORDER); renderDiaries picks the highest completed
      // tier. URLs come from the Main Reward column of the wiki's
      // Achievement_Diary "List of diaries" table, which is the only place all
      // 48 icons are available.
      var DIARY_AREA_TIER_ICON = {
        ardougne: [
          'https://oldschool.runescape.wiki/images/Ardougne_cloak_1.png',
          'https://oldschool.runescape.wiki/images/Ardougne_cloak_2.png',
          'https://oldschool.runescape.wiki/images/Ardougne_cloak_3.png',
          'https://oldschool.runescape.wiki/images/Ardougne_cloak_4.png',
        ],
        desert: [
          'https://oldschool.runescape.wiki/images/Desert_amulet_1.png',
          'https://oldschool.runescape.wiki/images/Desert_amulet_2.png',
          'https://oldschool.runescape.wiki/images/Desert_amulet_3.png',
          'https://oldschool.runescape.wiki/images/Desert_amulet_4.png',
        ],
        falador: [
          'https://oldschool.runescape.wiki/images/Falador_shield_1.png',
          'https://oldschool.runescape.wiki/images/Falador_shield_2.png',
          'https://oldschool.runescape.wiki/images/Falador_shield_3.png',
          'https://oldschool.runescape.wiki/images/Falador_shield_4.png',
        ],
        fremennik: [
          'https://oldschool.runescape.wiki/images/Fremennik_sea_boots_1.png',
          'https://oldschool.runescape.wiki/images/Fremennik_sea_boots_2.png',
          'https://oldschool.runescape.wiki/images/Fremennik_sea_boots_3.png',
          'https://oldschool.runescape.wiki/images/Fremennik_sea_boots_4.png',
        ],
        kandarin: [
          'https://oldschool.runescape.wiki/images/Kandarin_headgear_1.png',
          'https://oldschool.runescape.wiki/images/Kandarin_headgear_2.png',
          'https://oldschool.runescape.wiki/images/Kandarin_headgear_3.png',
          'https://oldschool.runescape.wiki/images/Kandarin_headgear_4.png',
        ],
        karamja: [
          'https://oldschool.runescape.wiki/images/Karamja_gloves_1.png',
          'https://oldschool.runescape.wiki/images/Karamja_gloves_2.png',
          'https://oldschool.runescape.wiki/images/Karamja_gloves_3.png',
          'https://oldschool.runescape.wiki/images/Karamja_gloves_4.png',
        ],
        kourend_kebos: [
          "https://oldschool.runescape.wiki/images/Rada%27s_blessing_1.png",
          "https://oldschool.runescape.wiki/images/Rada%27s_blessing_2.png",
          "https://oldschool.runescape.wiki/images/Rada%27s_blessing_3.png",
          "https://oldschool.runescape.wiki/images/Rada%27s_blessing_4.png",
        ],
        lumbridge_draynor: [
          "https://oldschool.runescape.wiki/images/Explorer%27s_ring_1.png",
          "https://oldschool.runescape.wiki/images/Explorer%27s_ring_2.png",
          "https://oldschool.runescape.wiki/images/Explorer%27s_ring_3.png",
          "https://oldschool.runescape.wiki/images/Explorer%27s_ring_4.png",
        ],
        morytania: [
          'https://oldschool.runescape.wiki/images/Morytania_legs_1.png',
          'https://oldschool.runescape.wiki/images/Morytania_legs_2.png',
          'https://oldschool.runescape.wiki/images/Morytania_legs_3.png',
          'https://oldschool.runescape.wiki/images/Morytania_legs_4.png',
        ],
        varrock: [
          'https://oldschool.runescape.wiki/images/Varrock_armour_1.png',
          'https://oldschool.runescape.wiki/images/Varrock_armour_2.png',
          'https://oldschool.runescape.wiki/images/Varrock_armour_3.png',
          'https://oldschool.runescape.wiki/images/Varrock_armour_4.png',
        ],
        western_provinces: [
          'https://oldschool.runescape.wiki/images/Western_banner_1.png',
          'https://oldschool.runescape.wiki/images/Western_banner_2.png',
          'https://oldschool.runescape.wiki/images/Western_banner_3.png',
          'https://oldschool.runescape.wiki/images/Western_banner_4.png',
        ],
        wilderness: [
          'https://oldschool.runescape.wiki/images/Wilderness_sword_1.png',
          'https://oldschool.runescape.wiki/images/Wilderness_sword_2.png',
          'https://oldschool.runescape.wiki/images/Wilderness_sword_3.png',
          'https://oldschool.runescape.wiki/images/Wilderness_sword_4.png',
        ],
      };
      // Shown for an area with zero tiers completed; saved locally at
      // app/static/img/diary-not-started.png.
      var DIARY_AREA_NOT_STARTED_ICON = '/static/img/diary-not-started.png';
      // In-game area order (matches the journal's tabs), not the alphabetical
      // order DIARY_AREAS/get_diary_tier_totals iterate in.
      var DIARY_AREA_ORDER = [
        'ardougne', 'desert', 'falador', 'fremennik', 'kandarin', 'karamja',
        'kourend_kebos', 'lumbridge_draynor', 'morytania', 'varrock',
        'western_provinces', 'wilderness',
      ];
      var DIARY_TIER_ORDER = ['easy', 'medium', 'hard', 'elite'];
      var CA_TIER_ORDER = ['easy', 'medium', 'hard', 'elite', 'master', 'grandmaster'];
      function titleCase(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
      function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
          return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
      }

      function questWikiUrl(name) {
        return 'https://oldschool.runescape.wiki/w/' + encodeURIComponent(String(name).replace(/ /g, '_'));
      }
      function renderQuests(quests) {
        var listEl = document.getElementById('questsList');
        var emptyEl = document.getElementById('questsEmpty');
        if (!listEl || !quests) return;
        var groups = [['Free Quests', quests.free], ["Members' Quests", quests.members], ['Miniquests', quests.miniquests]];
        var html = '';
        groups.forEach(function (group) {
          var label = group[0];
          var items = group[1] || [];
          if (!items.length) return;
          html += '<div class="quests-group-title">' + escapeHtml(label) + '</div>';
          items.forEach(function (q) {
            html += '<a class="quest-row quest-row--' + q.state + '" href="' + questWikiUrl(q.name) + '" target="_blank" rel="noopener">' + escapeHtml(q.name) + '</a>';
          });
        });
        listEl.innerHTML = html;
        if (emptyEl) emptyEl.hidden = html.length > 0;
      }

      // Same convention as questWikiUrl: spaces become underscores before
      // encodeURIComponent (so "&" in "Kourend & Kebos" comes out %26).
      function diaryWikiUrl(area) {
        var label = DIARY_AREA_LABELS[area] || titleCase(area);
        return 'https://oldschool.runescape.wiki/w/' + encodeURIComponent(label.replace(/ /g, '_')) + '_Diary';
      }

      function renderDiaries(diaries) {
        var listEl = document.getElementById('diariesList');
        if (!listEl || !Array.isArray(diaries)) return;
        var byArea = {};
        diaries.forEach(function (d) { byArea[d.area] = d; });
        var html = '';
        DIARY_AREA_ORDER.forEach(function (area) {
          var d = byArea[area];
          if (!d) return;
          // Highest completed tier picks the reward icon (DIARY_TIER_ORDER is
          // easy->elite, so the last match wins). -1 means no tiers completed.
          var highestCompletedIndex = -1;
          DIARY_TIER_ORDER.forEach(function (tier, i) {
            if (d.tiers && d.tiers[tier] === 'completed') highestCompletedIndex = i;
          });
          var icon = highestCompletedIndex >= 0
            ? (DIARY_AREA_TIER_ICON[area] || [])[highestCompletedIndex]
            : DIARY_AREA_NOT_STARTED_ICON;
          var label = DIARY_AREA_LABELS[area] || titleCase(area);
          html += '<a class="diary-row" href="' + diaryWikiUrl(area) + '" target="_blank" rel="noopener">'
            + '<div class="diary-row-header">'
            + '<img class="diary-row-icon" src="' + icon + '" alt="" />'
            + '<span class="diary-row-label">' + escapeHtml(label) + '</span>'
            + '<span class="diary-row-count">' + d.completed + '/' + d.total + '</span>'
            + '</div>'
            + '<div class="diary-row-bar">'
            + DIARY_TIER_ORDER.map(function (tier) {
                var state = (d.tiers && d.tiers[tier]) || 'not_completed';
                return '<div class="diary-tier-seg' + (state === 'completed' ? ' diary-tier-seg--completed' : '') + '"></div>';
              }).join('')
            + '</div>'
            + '</a>';
        });
        listEl.innerHTML = html;
      }

      function renderCombatAchievements(items) {
        var listEl = document.getElementById('caList');
        if (!listEl || !Array.isArray(items)) return;
        var byTier = {};
        items.forEach(function (item) { byTier[item.tier] = item; });
        var html = '';
        CA_TIER_ORDER.forEach(function (tier) {
          var item = byTier[tier];
          if (!item) return;
          var completed = item.completed;
          var total = item.total;
          var pct = (completed != null && total) ? Math.min(100, (completed / total) * 100) : 0;
          html += '<a class="ca-tile" href="https://oldschool.runescape.wiki/w/Combat_Achievements/' + titleCase(tier) + '" target="_blank" rel="noopener">'
            + '<span class="ca-tile-label">' + titleCase(tier) + '</span>'
            + '<img class="ca-tile-icon" src="/static/img/combat-achievement-tiers/' + tier + '.png" alt="" />'
            + '<span class="ca-tile-count">' + (completed != null ? completed : '\u2014') + '/' + total + '</span>'
            + '<div class="ca-tile-bar"><div class="ca-tile-bar-fill" style="width: ' + pct + '%"></div></div>'
            + '</a>';
        });
        listEl.innerHTML = html;
      }

      fetch('/api/character-overview/progress')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data) return;
          renderQuests(data.quests);
          renderDiaries(data.diaries);
          renderCombatAchievements(data.combatAchievements);
        })
        .catch(function () { /* leave each card's own empty/em-dash state showing */ });

      // Collection Log (GET /api/players/me/collection-log): tabs -> pages ->
      // items from the static schema (get_collection_log_tabs in
      // app/collectionlog.py) plus the obtained-item map
      // (GameAccount.collection_log_items, {item id string: quantity}, captured
      // by CollectionLogItemCapture in the Mootrius/myscape-plugin repo).
      // Rendered client-side.
      var clogCard = document.getElementById('clogCard');
      var clogEmpty = document.getElementById('clogEmpty');
      var clogBody = document.getElementById('clogBody');
      var clogTabsEl = document.getElementById('clogTabs');
      var clogPagesEl = document.getElementById('clogPages');
      var clogItemsEl = document.getElementById('clogItems');
      var clogItemsHeaderEl = document.getElementById('clogItemsHeader');
      var clogSyncBtn = document.getElementById('clogSyncBtn');

      var clogTabs = [];
      var clogObtained = {};
      // page name -> array of kill/completion counts
      // (collection_log_page_kill_counts in app/bosses.py; see
      // read_collection_log in app/main.py). Only boss/raid/clue pages have
      // entries; absent means no count shown. Several elements mean a combo page
      // (twin bosses, normal/hard-mode raids), see renderClogItemsHeader.
      var clogKillCounts = {};
      var clogActiveTab = 0;
      var clogActivePage = 0;

      // Same RuneLite item-icon CDN as item_icon_url in app/purchase_goals.py;
      // built from the bare numeric id since get_collection_log_tabs returns
      // bare ids.
      function clogIconUrl(itemId) {
        return 'https://static.runelite.net/cache/item/icon/' + itemId + '.png';
      }

      // Item ids repeat across pages (~205 do, e.g. clue rewards on several
      // tiers), so totals must dedupe by id rather than sum list lengths. Used
      // for the grand total and each tab's count.
      function clogUniqueIds(items) {
        var seen = {};
        var ids = [];
        items.forEach(function (item) {
          if (!seen[item.id]) { seen[item.id] = true; ids.push(item.id); }
        });
        return ids;
      }

      function clogObtainedCount(ids) {
        var count = 0;
        ids.forEach(function (id) { if (clogObtained[String(id)] != null) count++; });
        return count;
      }

      // Phone width: the tab strip scrolls sideways, and these classes drive the
      // edge fade and arrow (.clog-tabs-wrap in character-overview.css). Never
      // set on desktop.
      var clogTabsWrapEl = document.getElementById('clogTabsWrap');
      function updateClogTabsFade() {
        if (!clogTabsWrapEl) return;
        var max = clogTabsEl.scrollWidth - clogTabsEl.clientWidth;
        clogTabsWrapEl.classList.toggle('can-scroll-left', clogTabsEl.scrollLeft > 2);
        clogTabsWrapEl.classList.toggle('can-scroll-right', clogTabsEl.scrollLeft < max - 2);
      }
      clogTabsEl.addEventListener('scroll', updateClogTabsFade, { passive: true });
      window.addEventListener('resize', updateClogTabsFade);

      function renderClogTabs() {
        // Emptying the strip collapses it and would reset the scroll to the
        // first tab, so the scroll position is kept across the rebuild.
        var keepScrollLeft = clogTabsEl.scrollLeft;
        clogTabsEl.innerHTML = '';
        clogTabs.forEach(function (tab, tabIndex) {
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'clog-tab' + (tabIndex === clogActiveTab ? ' active' : '');
          btn.textContent = tab.name;
          btn.addEventListener('click', function () {
            clogActiveTab = tabIndex;
            clogActivePage = 0;
            renderClogTabs();
            renderClogPages();
            renderClogItems();
            renderClogItemsHeader();
            // Switching tabs resets to the first page and scrolls both panes to
            // the top. Replacing innerHTML doesn't do this since scrollTop lives
            // on clogPagesEl/clogItemsEl, which persist.
            clogPagesEl.scrollTop = 0;
            clogItemsEl.scrollTop = 0;
          });
          clogTabsEl.appendChild(btn);
        });
        clogTabsEl.scrollLeft = keepScrollLeft;
        updateClogTabsFade();
      }

      function renderClogPages() {
        clogPagesEl.innerHTML = '';
        var tab = clogTabs[clogActiveTab];
        if (!tab) return;
        tab.pages.forEach(function (page, pageIndex) {
          var obtainedCount = clogObtainedCount(clogUniqueIds(page.items));
          // Red/yellow/green by progress; a 0/0 page reads as complete.
          var progressState = obtainedCount === page.items.length ? 'complete'
            : obtainedCount === 0 ? 'zero'
            : 'started';
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'clog-page-btn ' + progressState
            + (pageIndex === clogActivePage ? ' active' : '');
          var label = document.createElement('span');
          label.textContent = page.name;
          var count = document.createElement('span');
          count.className = 'clog-page-count';
          count.textContent = formatInt(obtainedCount) + '/' + formatInt(page.items.length);
          btn.appendChild(label);
          btn.appendChild(count);
          btn.addEventListener('click', function () {
            clogActivePage = pageIndex;
            renderClogPages();
            renderClogItems();
            renderClogItemsHeader();
            // Reset the items grid to the top for the new page. .clog-pages
            // keeps its scroll position (unlike a tab switch) since the page
            // list stays the same.
            clogItemsEl.scrollTop = 0;
          });
          clogPagesEl.appendChild(btn);
        });
      }

      // Same wiki-URL shape as itemWikiUrl (gear slots); each render_* script is
      // independent, so it is a local copy.
      function clogItemWikiUrl(itemName) {
        return 'https://oldschool.runescape.wiki/w/' + encodeURIComponent(String(itemName).replace(/ /g, '_'));
      }
      function renderClogItems() {
        clogItemsEl.innerHTML = '';
        var tab = clogTabs[clogActiveTab];
        var page = tab && tab.pages[clogActivePage];
        if (!page) return;
        page.items.forEach(function (item) {
          var qty = clogObtained[String(item.id)];
          var tile = document.createElement('a');
          tile.className = 'clog-item' + (qty != null ? ' obtained' : '');
          tile.href = clogItemWikiUrl(item.name);
          tile.target = '_blank';
          tile.rel = 'noopener';
          // Site-styled tooltip (.myscape-tooltip in myscape.css, driven by
          // _shell's shared_script) with just the item name.
          tile.setAttribute('data-tooltip', item.name);
          var img = document.createElement('img');
          img.className = 'clog-item-icon';
          img.src = clogIconUrl(item.id);
          img.alt = '';
          img.loading = 'lazy';
          img.onerror = function () { img.style.display = 'none'; };
          tile.appendChild(img);
          if (qty != null && qty > 1) {
            var badge = document.createElement('div');
            badge.className = 'clog-item-qty';
            badge.textContent = formatInt(qty);
            tile.appendChild(badge);
          }
          clogItemsEl.appendChild(tile);
        });
      }

      // Active page's name + kill/completion count above the item grid. The
      // count is omitted when clogKillCounts has no entry. Pages with several
      // counts show them joined by a middot rather than summed (e.g. Callisto
      // and Artio). No personal-best time since nothing tracks one.
      function renderClogItemsHeader() {
        clogItemsHeaderEl.innerHTML = '';
        var tab = clogTabs[clogActiveTab];
        var page = tab && tab.pages[clogActivePage];
        if (!page) return;
        var name = document.createElement('span');
        name.className = 'clog-items-header-name';
        name.textContent = page.name;
        clogItemsHeaderEl.appendChild(name);
        var killCounts = clogKillCounts[page.name];
        if (killCounts != null && killCounts.length) {
          var kc = document.createElement('span');
          kc.className = 'clog-items-header-kc';
          kc.textContent = killCounts.map(formatInt).join(' \\u00b7 ');
          clogItemsHeaderEl.appendChild(kc);
        }
      }

      // Same empty-state swap as showEmpty in the model viewer's module script;
      // only called once there is nothing to show.
      function showClogEmpty() {
        clogBody.style.display = 'none';
        clogEmpty.style.display = 'block';
      }

      // Locks .clog-pages/.clog-items height to .model-viewer-card's rendered
      // height instead of a fixed px value in CSS. The .clog-tabs height depends
      // on the RuneScapePlain11 web font's line-height (font-display: optional
      // in myscape.css), which varies with network, environment and browser, so
      // it is computed from the real boxes.
      var modelViewerCard = document.getElementById('modelViewerCard');
      function syncClogHeight() {
        if (!modelViewerCard || !clogCard || !clogPagesEl || !clogItemsEl || !clogItemsHeaderEl) return;
        // Phone layout (700px breakpoint, as in character-overview.css): the log
        // stacks below the viewer, so drop inline heights and use the
        // stylesheet's.
        if (window.matchMedia('(max-width: 700px)').matches) {
          clogPagesEl.style.height = '';
          clogItemsEl.style.height = '';
          return;
        }
        var modelBoxHeight = modelViewerCard.getBoundingClientRect().height;
        if (!modelBoxHeight) return;
        var clogCS = getComputedStyle(clogCard);
        // Read .clog-toolbar, not .clog-tabs: the toolbar (wrapping .clog-tabs +
        // .clog-sync-btn) carries the row's margin-bottom, so using .clog-tabs
        // would under-subtract 8px.
        var toolbarEl = clogCard.querySelector('.clog-toolbar');
        var toolbarCS = toolbarEl ? getComputedStyle(toolbarEl) : null;
        var panesHeight = modelBoxHeight
          - parseFloat(clogCS.paddingTop)
          - parseFloat(clogCS.paddingBottom)
          - parseFloat(clogCS.borderTopWidth)
          - parseFloat(clogCS.borderBottomWidth)
          - (toolbarEl ? toolbarEl.getBoundingClientRect().height : 0)
          - (toolbarCS ? parseFloat(toolbarCS.marginBottom) : 0);
        if (panesHeight > 0) {
          // .clog-pages has no header, so it gets the whole budget;
          // .clog-items-header eats only into .clog-items' share (see
          // .clog-items-col in character-overview.css).
          clogPagesEl.style.height = panesHeight + 'px';
          var headerCS = getComputedStyle(clogItemsHeaderEl);
          var itemsHeight = panesHeight
            - clogItemsHeaderEl.getBoundingClientRect().height
            - parseFloat(headerCS.marginBottom);
          if (itemsHeight > 0) {
            clogItemsEl.style.height = itemsHeight + 'px';
          }
        }
      }
      if (modelViewerCard && window.ResizeObserver) {
        new ResizeObserver(syncClogHeight).observe(modelViewerCard);
      } else {
        window.addEventListener('resize', syncClogHeight);
      }
      syncClogHeight();
      // Re-run once the web font swaps in (see font-display: optional in
      // myscape.css); ResizeObserver on modelViewerCard won't catch it since the
      // card's height is width-driven.
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(syncClogHeight);
      }

      // Touch screens only show a tap tooltip for these: summary-row icons, the
      // model viewer info button, the Collection Log refresh button and item
      // tiles, Skills cells, and the PRIVATE/PUBLIC buttons in the
      // public-profile popup. Read by the shared tooltip script in _shell.
      window.myscapeTouchTooltipFilter = function (el) {
        return !!(el.closest && el.closest(
          '.co-summary-row, #mvInfoBtn, #clogSyncBtn, .clog-item, .skill-cell, ' +
          '#publicProfileSegPrivate, #publicProfileSegPublic'
        ));
      };

      // Tapping the summary-row icons or the viewer's info button a second time
      // dismisses their tooltip (same shared tooltip script).
      window.myscapeTouchTooltipToggle = function (el) {
        return !!(el.closest && el.closest('.co-summary-row, #mvInfoBtn'));
      };

      // Drawn scrollbars for the four scrolling lists (Collection Log pages +
      // items, Quests, Achievement Diaries), shown only at phone width; see
      // "Scrollbars on the scrolling lists" in character-overview.css. Always
      // built, CSS decides display. The thumb is sized from scrollTop and
      // draggable.
      (function () {
        function attach(list) {
          if (!list || !list.parentElement) return;
          var track = document.createElement('div');
          track.className = 'co-sb';
          track.setAttribute('aria-hidden', 'true');
          var thumb = document.createElement('div');
          thumb.className = 'co-sb-thumb';
          track.appendChild(thumb);
          list.parentElement.appendChild(track);

          var thumbH = 0;
          function update() {
            var ch = list.clientHeight;
            var sh = list.scrollHeight;
            var scrollable = ch > 0 && sh > ch + 1;
            track.classList.toggle('co-sb--on', scrollable);
            if (!scrollable) return;
            track.style.top = list.offsetTop + 'px';
            track.style.height = list.offsetHeight + 'px';
            track.style.left = (list.offsetLeft + list.offsetWidth - 16) + 'px';
            thumbH = Math.max(28, Math.round(ch * ch / sh));
            thumb.style.height = thumbH + 'px';
            var maxTop = list.offsetHeight - thumbH;
            var y = maxTop * list.scrollTop / (sh - ch);
            thumb.style.transform = 'translateY(' + Math.max(0, Math.min(maxTop, Math.round(y))) + 'px)';
          }
          list.addEventListener('scroll', update, { passive: true });
          window.addEventListener('resize', update);
          if (window.ResizeObserver) new ResizeObserver(update).observe(list);
          if (window.MutationObserver) new MutationObserver(update).observe(list, { childList: true });

          var dragStartY = 0;
          var dragStartScroll = 0;
          thumb.addEventListener('pointerdown', function (e) {
            dragStartY = e.clientY;
            dragStartScroll = list.scrollTop;
            thumb.classList.add('dragging');
            thumb.setPointerCapture(e.pointerId);
            e.preventDefault();
          });
          thumb.addEventListener('pointermove', function (e) {
            if (!thumb.classList.contains('dragging')) return;
            var travel = list.offsetHeight - thumbH;
            if (travel <= 0) return;
            list.scrollTop = dragStartScroll + (e.clientY - dragStartY) * (list.scrollHeight - list.clientHeight) / travel;
          });
          function endDrag() { thumb.classList.remove('dragging'); }
          thumb.addEventListener('pointerup', endDrag);
          thumb.addEventListener('pointercancel', endDrag);
          update();
        }
        ['clogPages', 'clogItems', 'questsList', 'diariesList'].forEach(function (id) {
          attach(document.getElementById(id));
        });
      })();

      // Named so the manual sync button can re-run it after a resync.
      function loadCollectionLog() {
        return fetch('/api/players/me/collection-log')
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (data) {
            if (!data || !data.syncedAt || !Array.isArray(data.tabs) || !data.tabs.length) {
              showClogEmpty();
              return;
            }
            clogTabs = data.tabs;
            clogObtained = data.obtainedItems || {};
            clogKillCounts = data.killCounts || {};
            renderClogTabs();
            renderClogPages();
            renderClogItems();
            renderClogItemsHeader();
            // Re-sync heights now that .clog-tabs and .clog-items-header have
            // content (both are 0px tall until now).
            syncClogHeight();
          })
          .catch(function () { showClogEmpty(); });
      }
      if (clogCard) {
        loadCollectionLog();
      }

      // Manual hiscores refresh for the counts renderClogItemsHeader shows. POST
      // /api/players/me/hiscores/sync is otherwise only triggered at link time
      // (sync_hiscores in app/hiscores.py), so later-added stats (e.g.
      // COLLECTION_LOG_CLUE_PAGE_TIERS in app/bosses.py) would stay empty. Only
      // clogKillCounts can change, so loadCollectionLog() is re-run.
      if (clogSyncBtn) {
        clogSyncBtn.addEventListener('click', function () {
          if (clogSyncBtn.disabled) return;
          clogSyncBtn.classList.remove('sync-failed');
          clogSyncBtn.disabled = true;
          clogSyncBtn.classList.add('syncing');
          fetch('/api/players/me/hiscores/sync', { method: 'POST' })
            .then(function (r) { return r.ok ? loadCollectionLog() : Promise.reject(); })
            .catch(function () {
              clogSyncBtn.classList.add('sync-failed');
              setTimeout(function () { clogSyncBtn.classList.remove('sync-failed'); }, 2500);
            })
            .then(function () {
              clogSyncBtn.disabled = false;
              clogSyncBtn.classList.remove('syncing');
            });
        });
      }

      // Public-profile settings card (#publicProfileCard). Absent in
      // preview/public_code mode (see publicProfileSettingsBtn in
      // render_character_overview); this guard makes that a no-op.
      var publicProfileSettingsBtn = document.getElementById('publicProfileSettingsBtn');
      if (publicProfileSettingsBtn) {
        var publicProfileCard = document.getElementById('publicProfileCard');
        var publicProfileSegBtns = [document.getElementById('publicProfileSegPrivate'), document.getElementById('publicProfileSegPublic')];
        var publicProfileLinkBtn = document.getElementById('publicProfileLinkBtn');
        var publicProfileRegenerateBtn = document.getElementById('publicProfileRegenerateBtn');

        // Collapsed by default; the cog toggles a floating popup under the
        // button (.co-settings-wrap). Mirrors the Storages Viewer's
        // pmSettingsBtn/pmSettingsMenu (setSettingsMenuOpen in app/pages.py),
        // including the .active class and outside-click close. No refetch on
        // open since the initial GET already ran.
        function setPublicProfileOpen(open) {
          publicProfileCard.hidden = !open;
          publicProfileSettingsBtn.classList.toggle('active', open);
        }
        publicProfileSettingsBtn.addEventListener('click', function () {
          setPublicProfileOpen(publicProfileCard.hidden);
        });
        document.addEventListener('click', function (e) {
          var wrap = document.querySelector('.co-settings-wrap');
          if (wrap && !wrap.contains(e.target)) setPublicProfileOpen(false);
        });

        function applyPublicProfileState(data) {
          if (!data) return;
          var activeValue = data.isPublic ? 'public' : 'private';
          publicProfileSegBtns.forEach(function (btn) {
            btn.classList.toggle('active', btn.getAttribute('data-segment-value') === activeValue);
          });
          publicProfileLinkBtn.dataset.url = data.url || '';
          publicProfileLinkBtn.textContent = data.url || '';
          // A private page has no link to copy: the real disabled attribute (not
          // just styling) stops the click handler, matching
          // .public-profile-link-btn:disabled.
          publicProfileLinkBtn.disabled = !data.isPublic;
          // The data-tooltip attribute is removed while private, since "Click to
          // copy" would describe an action the disabled button can't do.
          if (data.isPublic) {
            publicProfileLinkBtn.setAttribute('data-tooltip', 'Click to copy');
          } else {
            publicProfileLinkBtn.removeAttribute('data-tooltip');
          }
        }

        fetch('/api/players/me/public-profile')
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(applyPublicProfileState)
          .catch(function () { /* leave the segmented control at its default (Private) */ });

        publicProfileSegBtns.forEach(function (btn) {
          btn.addEventListener('click', function () {
            if (btn.classList.contains('active')) return;
            var wantPublic = btn.getAttribute('data-segment-value') === 'public';
            publicProfileSegBtns.forEach(function (b) { b.disabled = true; });
            fetch('/api/players/me/public-profile', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ is_public: wantPublic }),
            })
              .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
              .then(applyPublicProfileState)
              .catch(function () {})
              .then(function () { publicProfileSegBtns.forEach(function (b) { b.disabled = false; }); });
          });
        });

        // The link display is the copy button, as in Loot Tracker's
        // lootShareLinkBtn (app/pages.py) and the Account page's Shared Links
        // table. The URL is held in data-url since textContent swaps to "COPIED"
        // briefly.
        publicProfileLinkBtn.addEventListener('click', function () {
          var url = publicProfileLinkBtn.dataset.url;
          if (!url) return;
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url);
          } else {
            var temp = document.createElement('textarea');
            temp.value = url;
            temp.style.position = 'fixed';
            temp.style.opacity = '0';
            document.body.appendChild(temp);
            temp.select();
            document.execCommand('copy');
            document.body.removeChild(temp);
          }
          publicProfileLinkBtn.textContent = 'COPIED';
          setTimeout(function () { publicProfileLinkBtn.textContent = url; }, 1200);
        });

        // Server-side limit is once per day (regenerate_public_profile_code in
        // app/main.py); a 429 flashes the button red like the collection log's
        // hiscores-sync failure.
        publicProfileRegenerateBtn.addEventListener('click', function () {
          publicProfileRegenerateBtn.disabled = true;
          fetch('/api/players/me/public-profile/regenerate-code', { method: 'POST' })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
            .then(applyPublicProfileState)
            .catch(function () {
              publicProfileRegenerateBtn.classList.add('action-failed');
              setTimeout(function () { publicProfileRegenerateBtn.classList.remove('action-failed'); }, 2500);
            })
            .then(function () { publicProfileRegenerateBtn.disabled = false; });
        });
      }
    })();
    """.replace("__ACCOUNT_TYPE_INFO_JSON__", json.dumps(_ACCOUNT_TYPE_INFO))

    extra_head = (
        f'<link rel="stylesheet" href="/static/css/character-overview.css?v={_CHARACTER_OVERVIEW_CSS_VERSION}" />'
        + _MODEL_VIEWER_HEAD.replace(
            "__MODEL_VIEWER_BACKGROUNDS_JSON__", json.dumps(_MODEL_VIEWER_BACKGROUNDS)
        ).replace(
            "__MODEL_VIEWER_BG_STORAGE_KEY_JSON__",
            json.dumps(
                None if preview
                else f"myscape.modelViewerBgIndex.public.{public_code}" if public_code
                else "myscape.modelViewerBgIndex"
            ),
        ).replace(
            "__MODEL_VIEWER_MODEL_URL_JSON__",
            json.dumps(
                "/static/img/landing-character-overview-demo-model.glb" if preview
                else f"/api/public/{public_code}/model" if public_code
                else "/api/character-overview/model"
            ),
        )
    )
    return extra_head, body, script


def render_character_overview(player: PlayerView) -> str:
    """The real, authenticated Character Overview page:
    _character_overview_panel_markup's default output in the page shell. The
    landing preview (render_landing_character_overview_preview) and public
    view (render_public_character_overview) reuse the same body/script.
    """
    extra_head, body, script = _character_overview_panel_markup()
    return _shell(
        title="Character Overview — myscape",
        player=player,
        body=body,
        extra_head=extra_head,
        extra_script=script,
    )


def render_public_character_overview(game_account: "GameAccount", viewer: Optional[PlayerView]) -> str:
    """myscape.io/c/<code>: a visitor's view of someone else's public Character
    Overview. public_character_overview_page in app/main.py resolves the code
    and 404s if missing/private; viewer is whoever is signed in, used only for
    nav state.
    
    Reuses _character_overview_panel_markup(public_code=...) with a wrapper
    fetch shim that calls the code-scoped endpoints (GET
    /api/public/<code>/summary|progress|skills|collection-log in app/main.py)
    instead of the "me" endpoints. `fetch` is shadowed only inside this IIFE;
    window.fetch is untouched (see _MODEL_VIEWER_HEAD).
    
    accountType rides in the public summary response (low exposure).
    #clogSyncBtn gets the same hoverable-but-inert cloneNode+replaceWith
    treatment as the landing preview.
    """
    code = game_account.public_code
    display_name = game_account.runescape_name or "This player"
    extra_head, body, script = _character_overview_panel_markup(
        public_code=code, public_character_name=display_name
    )

    wrapper_script = f"""
    (function () {{
      var PUBLIC_CODE = {json.dumps(code)};

      // fetch shim: forwards to the real, public endpoints
      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        function fail() {{ return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{}}); }} }}); }}

        if (url === '/api/character-overview/summary' && method === 'GET') {{
          return window.fetch('/api/public/' + PUBLIC_CODE + '/summary').then(function (r) {{
            // Hands the owner's synced model-viewer background
            // (modelViewerBackgroundIndex in this response, see app/main.py) to
            // the 3D viewer, since a visitor has no shuffle history of their own
            // (see myscapeApplyModelViewerBackground in _MODEL_VIEWER_HEAD).
            // r.clone() because the reused script still reads this body and a
            // Response body can be consumed once.
            if (r.ok) {{
              r.clone().json().then(function (data) {{
                // Stashed on window whether or not the bridge function exists
                // yet: this fetch can resolve before the deferred module script
                // runs (see the handshake next to
                // window.myscapeApplyModelViewerBackground in
                // _MODEL_VIEWER_HEAD).
                window.__myscapePendingModelViewerBg = data.modelViewerBackgroundIndex;
                if (window.myscapeApplyModelViewerBackground) {{
                  window.myscapeApplyModelViewerBackground(data.modelViewerBackgroundIndex);
                }}
              }}).catch(function () {{}});
            }}
            return r;
          }});
        }}
        if (url === '/api/character-overview/progress' && method === 'GET') {{
          return window.fetch('/api/public/' + PUBLIC_CODE + '/progress');
        }}
        if (url === '/api/players/me/skills' && method === 'GET') {{
          return window.fetch('/api/public/' + PUBLIC_CODE + '/skills');
        }}
        if (url === '/api/players/me/collection-log' && method === 'GET') {{
          return window.fetch('/api/public/' + PUBLIC_CODE + '/collection-log');
        }}
        // #clogSyncBtn's click listener would fire this; unreachable in practice
        // (see the cloneNode+replaceWith strip below), answered with a graceful
        // failure anyway.
        if (url === '/api/players/me/hiscores/sync' && method === 'POST') {{
          return fail();
        }}
        // Anything else the reused script could call beyond the cases above.
        return fail();
      }};

      {script}

      var clogSyncBtn = document.getElementById('clogSyncBtn');
      if (clogSyncBtn) {{
        clogSyncBtn.replaceWith(clogSyncBtn.cloneNode(true));
      }}

      // friend-request button, next to the character's name. Uses the real
      // window.fetch on purpose (the local `fetch` answers only the Character
      // Overview endpoints).
      (function () {{
        var title = document.querySelector('h2.page-title');
        if (!title) return;
        var wrap = document.createElement('span');
        wrap.className = 'co-friend-wrap';
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'co-friend-btn';
        btn.id = 'friendRequestBtn';
        btn.hidden = true;
        wrap.appendChild(btn);
        title.appendChild(document.createTextNode(' '));
        title.appendChild(wrap);

        var ICON_ADD = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M19 8v6"></path><path d="M22 11h-6"></path></svg>';
        var ICON_DONE = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M16 11l2 2 4-4"></path></svg>';

        var state = 'none';
        var restoreTimer = null;
        function setState(next) {{
          state = next;
          btn.classList.remove('co-friend-btn--done');
          btn.disabled = false;
          if (next === 'self' || next === 'own') {{ btn.hidden = true; return; }}
          btn.hidden = false;
          var tip;
          if (next === 'friends') {{
            btn.innerHTML = ICON_DONE; tip = 'Friends';
            btn.classList.add('co-friend-btn--done'); btn.disabled = true;
          }} else if (next === 'pending_out') {{
            btn.innerHTML = ICON_DONE; tip = 'Friend request sent';
            btn.classList.add('co-friend-btn--done'); btn.disabled = true;
          }} else if (next === 'pending_in') {{
            btn.innerHTML = ICON_ADD; tip = 'Accept friend request';
          }} else if (next === 'anonymous') {{
            btn.innerHTML = ICON_ADD; tip = 'Log in to send a friend request';
          }} else {{
            btn.innerHTML = ICON_ADD; tip = 'Send friend request';
          }}
          btn.setAttribute('data-tooltip', tip);
          btn.setAttribute('aria-label', tip);
        }}

        window.fetch('/api/friends/status/' + encodeURIComponent(PUBLIC_CODE))
          .then(function (r) {{ return r.ok ? r.json() : null; }})
          .then(function (d) {{ if (d && d.state) setState(d.state); }})
          .catch(function () {{}});

        btn.addEventListener('click', function () {{
          if (state === 'anonymous') {{ window.location.href = '/login'; return; }}
          if (state !== 'none' && state !== 'pending_in') return;
          btn.disabled = true;
          window.fetch('/api/friends/requests', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ code: PUBLIC_CODE }}),
          }}).then(function (r) {{
            return r.json().catch(function () {{ return {{}}; }}).then(function (d) {{ return {{ ok: r.ok, data: d }}; }});
          }}).then(function (res) {{
            if (res.ok) {{
              if (window.myscapePollFriendNotifications) window.myscapePollFriendNotifications();
              setState(res.data.status === 'accepted' ? 'friends' : 'pending_out');
              return;
            }}
            var msg = (res.data && typeof res.data.detail === 'string') ? res.data.detail : 'Could not send that request.';
            btn.disabled = false;
            var previous = btn.getAttribute('data-tooltip');
            btn.setAttribute('data-tooltip', msg);
            clearTimeout(restoreTimer);
            restoreTimer = setTimeout(function () {{ btn.setAttribute('data-tooltip', previous); }}, 3500);
          }}).catch(function () {{ btn.disabled = false; }});
        }});
      }})();
    }})();
    """

    return _shell(
        title=f"{display_name} — myscape",
        player=viewer,
        body=body,
        extra_head=extra_head,
        extra_script=wrapper_script,
        meta_description=(
            f"{display_name}'s public myscape page — complete with their "
            "collection log data, skill levels, quest completions, "
            "achievement diary tiers, and combat task tiers."
        ),
    )


def render_landing_character_overview_preview() -> Optional[Tuple[str, str, str]]:
    """Landing page's interactive Character Overview preview: reuses
    _character_overview_panel_markup(preview=True) unmodified with a demo
    wrapper script. Backed by app/data/landing_character_overview_demo.json
    (real summary, progress and collection log snapshot; see
    _get_landing_character_overview_demo_data) plus a static .glb model.
    Returns (extra_head, body, script) for render_landing, or None if the
    snapshot is missing. First preview on the page, ahead of Loot Tracker.
    
    All six sections work like the real page; background shuffle works but
    never persists (see __MODEL_VIEWER_BG_STORAGE_KEY_JSON__). The container
    uses the usual fixed-height/clipped/feathered treatment
    (.landing-character-overview-preview in character-overview.css), so extra
    cards are reached by touch drag/keyboard. #clogSyncBtn stays visible and
    hoverable but inert (cloneNode+replaceWith strip, as for Loot Tracker's
    range button).
    
    1. A scoped `fetch` shim answers GET /api/character-overview/summary,
    /api/character-overview/progress, /api/players/me/skills and
    /api/players/me/collection-log from the snapshot, and fails the
    hiscores-sync POST gracefully. The 3D model bypasses the shim
    (__MODEL_VIEWER_MODEL_URL_JSON__ points at a static asset).
    2. No polling interval: each endpoint is fetched once on load.
    """
    demo = _get_landing_character_overview_demo_data()
    if demo is None:
        return None
    extra_head, body, script = _character_overview_panel_markup(preview=True)

    # Hero row: tagline wrap first, character second so the character lands on
    # the right; same flex/bottom-align as other previews (see
    # .loot-preview-hero in loot-tracker.css). The reused body's <h2> is hidden
    # via .landing-character-overview-preview .page-title.
    hero_markup = """
    <div class="co-preview-hero">
      <div class="co-preview-tagline-wrap">
        <p class="co-preview-tagline">
          <span class="co-preview-tagline-gold">CHARACTER OVERVIEWS</span> <span class="co-preview-tagline-white">that you can share with your friends.</span>
        </p>
      </div>
      <picture class="co-preview-char">
        <source srcset="/static/img/landing-character-overview-preview-char.webp" type="image/webp">
        <img src="/static/img/landing-character-overview-preview-char.png" alt="" />
      </picture>
    </div>
    """
    body = hero_markup + body

    summary_json = json.dumps(demo.get("summary") or {})
    progress_json = json.dumps(demo.get("progress") or {})
    skills_json = json.dumps(demo.get("skills") or {})
    collection_log_json = json.dumps(demo.get("collectionLog") or {})
    wrapper_script = f"""
    (function () {{
      // The captured snapshot (see _get_landing_character_overview_demo_data for
      // the sources). Static, since nothing in this preview mutates it.
      var DEMO_SUMMARY = {summary_json};
      var DEMO_PROGRESS = {progress_json};
      var DEMO_SKILLS = {skills_json};
      var DEMO_COLLECTION_LOG = {collection_log_json};

      // fetch shim
      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        function ok(data) {{ return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(data); }} }}); }}
        function fail() {{ return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{}}); }} }}); }}

        if (url === '/api/character-overview/summary' && method === 'GET') {{
          return ok(DEMO_SUMMARY);
        }}
        if (url === '/api/character-overview/progress' && method === 'GET') {{
          return ok(DEMO_PROGRESS);
        }}
        if (url === '/api/players/me/skills' && method === 'GET') {{
          return ok(DEMO_SKILLS);
        }}
        if (url === '/api/players/me/collection-log' && method === 'GET') {{
          return ok(DEMO_COLLECTION_LOG);
        }}
        // Hiscores-sync POST from #clogSyncBtn's click listener; unreachable in
        // practice (see the cloneNode+replaceWith strip below), answered
        // gracefully anyway.
        if (url === '/api/players/me/hiscores/sync' && method === 'POST') {{
          return fail();
        }}
        // Fallback: a harmless failure for anything unexpected.
        return fail();
      }};

      {script}

      // Neutralizes the collection log's hiscores refresh button. Runs after the
      // reused script has wired its click listener, so the node is replaced
      // outright (cloneNode(true) copies markup but not listeners), as for Loot
      // Tracker's range button (render_landing_loot_preview). The button keeps
      // its hover styling and tooltip but does nothing on click.
      var clogSyncBtn = document.getElementById('clogSyncBtn');
      if (clogSyncBtn) {{
        clogSyncBtn.replaceWith(clogSyncBtn.cloneNode(true));
      }}

      // accountType ("MAIN", summary.accountType in
      // app/data/landing_character_overview_demo.json) flows through the summary
      // shim above like every other stat; no override needed.
    }})();
    """
    return extra_head, body, wrapper_script


def render_account(player: PlayerView) -> str:
    """The header's Account link (see _nav_sides): log out, change email, change
    password, delete account (/api/auth/change-email, /change-password,
    /delete-account in app/routers/auth.py, which stay reachable
    pre-verification). `player` is not Optional since account_page in
    app/main.py redirects logged-out visitors to /login.
    """
    current_email = escape(player.email or "")
    body = f"""
    <div class="auth-shell account-shell">
      <div class="auth-card">
        <h2>ACCOUNT</h2>
        <p class="account-email">{current_email}</p>
        <button class="account-logout-link" id="logoutBtn" type="button">LOG OUT</button>

        <div class="account-section">
          <div class="auth-error" id="gameAccountsError"></div>
          <div class="game-accounts-list" id="gameAccountsList"></div>
          <button class="secondary" id="addGameAccountBtn" type="button">+ ADD CHARACTER</button>
        </div>

        <div class="account-section" id="friendsSection">
          <p class="account-section-title account-section-title--center">FRIENDS LIST</p>
          <p class="shared-links-empty" id="friendsHint" hidden></p>
          <div id="friendsBody">
            <form class="friends-add-form" id="friendsAddForm" autocomplete="off">
              <div class="friends-code-wrap" id="friendsCodeWrap" hidden>
                <span class="friends-code-label">My code</span>
                <button type="button" class="shared-link-code-btn" id="friendsCodeBtn" data-tooltip="Click to copy"></button>
                <span class="friends-add-divider" aria-hidden="true"></span>
              </div>
              <input type="text" id="friendsAddInput" maxlength="5" placeholder="Friend code" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Friend code" />
              <button class="secondary" type="submit" id="friendsAddBtn">SEND REQUEST</button>
            </form>
            <div class="auth-error" id="friendsError"></div>
            <div class="auth-success" id="friendsSuccess"></div>
            <div class="friends-requests" id="friendsRequests" hidden>
              <p class="friends-requests-title">Friend requests</p>
              <div id="friendsRequestsList"></div>
            </div>
            <div class="friends-table-wrap" id="friendsTableWrap" style="display:none;">
              <table class="friends-table">
                <thead>
                  <tr>
                    <th><button type="button" class="friend-sort-header" data-friend-sort-key="friend" data-tooltip="Sort by friend">Friend<span class="friend-sort-arrow"></span></button></th>
                    <th><button type="button" class="friend-sort-header" data-friend-sort-key="since" data-tooltip="Sort by date">Since<span class="friend-sort-arrow"></span></button></th>
                    <th>Removal</th>
                  </tr>
                </thead>
                <tbody id="friendsTableBody"></tbody>
              </table>
            </div>
            <p class="shared-links-empty" id="friendsEmpty" style="display:none;">No friends yet.</p>
          </div>
        </div>

        <div class="account-section">
          <p class="account-section-title account-section-title--center">SHARED LINKS</p>
          <div class="auth-error" id="sharedLinksError"></div>
          <div class="shared-links-table-wrap" id="sharedLinksTableWrap" style="display:none;">
            <table class="shared-links-table">
              <thead>
                <tr>
                  <th><button type="button" class="shared-link-sort-header" data-sort-key="character" data-tooltip="Sort by character">Character<span class="shared-link-sort-arrow"></span></button></th>
                  <th><button type="button" class="shared-link-sort-header" data-sort-key="app" data-tooltip="Sort by type">Type<span class="shared-link-sort-arrow"></span></button></th>
                  <th>Code</th>
                  <th><button type="button" class="shared-link-sort-header" data-sort-key="expiration" data-tooltip="Sort by expiration">Expiration<span class="shared-link-sort-arrow"></span></button></th>
                  <th><button type="button" class="shared-link-delete-all-header" id="sharedLinksDeleteAllBtn" data-tooltip="Delete all shared links">Deletion</button></th>
                </tr>
              </thead>
              <tbody id="sharedLinksTableBody"></tbody>
            </table>
          </div>
          <p class="shared-links-empty" id="sharedLinksEmpty" style="display:none;">No shared links yet.</p>
        </div>

        <div class="account-section">
          <div class="account-tab-row">
            <button class="secondary" type="button" id="emailToggleBtn">UPDATE EMAIL</button>
            <button class="secondary" type="button" id="passwordToggleBtn">UPDATE PASSWORD</button>
            <button class="danger" type="button" id="deleteToggleBtn">DELETE ACCOUNT</button>
          </div>

          <div class="account-collapse-body" id="emailBody" hidden>
            <div class="auth-error" id="emailError"></div>
            <div class="auth-success" id="emailSuccess"></div>
            <form id="emailForm">
              <div class="field">
                <label for="newEmail">New email</label>
                <input type="email" id="newEmail" name="newEmail" placeholder="you@example.com" required />
              </div>
              <div class="field">
                <label for="emailPassword">Password</label>
                <input type="password" id="emailPassword" name="emailPassword" placeholder="Your password" required />
              </div>
              <button class="primary" type="submit">UPDATE EMAIL</button>
            </form>
          </div>

          <div class="account-collapse-body" id="passwordBody" hidden>
            <div class="auth-error" id="passwordError"></div>
            <div class="auth-success" id="passwordSuccess"></div>
            <form id="passwordForm">
              <div class="field">
                <label for="currentPassword">Current password</label>
                <input type="password" id="currentPassword" name="currentPassword" placeholder="Current password" required />
              </div>
              <div class="field">
                <label for="newPassword">New password</label>
                <input type="password" id="newPassword" name="newPassword" placeholder="At least 8 characters" required minlength="8" />
              </div>
              <div class="field">
                <label for="confirmNewPassword">Confirm new password</label>
                <input type="password" id="confirmNewPassword" name="confirmNewPassword" placeholder="Re-enter your new password" required minlength="8" />
              </div>
              <button class="primary" type="submit">UPDATE PASSWORD</button>
            </form>
          </div>

          <div class="account-collapse-body" id="deleteBody" hidden>
            <p class="account-section-hint account-section-hint--center">This will <span class="account-hint-emphasis">PERMANENTLY</span> delete your myscape account and all data attached to it. You can create a new account afterward, but you <span class="account-hint-emphasis">CANNOT</span> undo this action.</p>
            <div class="auth-error" id="deleteError"></div>
            <form id="deleteForm">
              <div class="field">
                <label for="deletePassword">Password</label>
                <input type="password" id="deletePassword" name="deletePassword" placeholder="Your password" required />
              </div>
              <button class="danger danger--filled" type="submit" id="deleteSubmitBtn" data-armed="false">DELETE ACCOUNT</button>
            </form>
          </div>
        </div>
      </div>
    </div>
    """
    script = """
    (function () {
      // No tap tooltips on touch screens for the Account page; read by the
      // shared tooltip script in _shell.
      window.myscapeTouchTooltipFilter = function () { return false; };

      // Same trash icon as Goal Tracking's .gt-goal-delete (goalRowHtml); shared
      // by DEACTIVATE (Shared Links) and DELETE CHARACTER (Linked Accounts) via
      // trashDeleteBtnHtml.
      const TRASH_ICON_SVG = '<svg class="trash-delete-icon" width="15" height="15" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M2 4H14" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><path d="M6 4V2.5C6 2.22386 6.22386 2 6.5 2H9.5C9.77614 2 10 2.22386 10 2.5V4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M3.5 4L4.1 13.2C4.13 13.66 4.51 14 4.97 14H11.03C11.49 14 11.87 13.66 11.9 13.2L12.5 4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6.5 6.5V11.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><path d="M9.5 6.5V11.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>';

      function trashDeleteBtnHtml(confirmLabel) {
        return TRASH_ICON_SVG + '<span class="trash-delete-confirm">' + confirmLabel + '</span>';
      }

      // First click arms the button (shows the confirm label); a second click
      // runs `onConfirm`. A click elsewhere disarms it via the shared
      // outside-click listener below, like Goal Tracking's delete button.
      function wireTrashDeleteBtn(btn, onConfirm) {
        btn.addEventListener('click', () => {
          if (btn.classList.contains('trash-delete-btn--confirm')) {
            onConfirm();
            return;
          }
          document.querySelectorAll('.trash-delete-btn--confirm').forEach((b) => {
            if (b !== btn) b.classList.remove('trash-delete-btn--confirm');
          });
          disarmDeleteAllLinksHeader();
          btn.classList.add('trash-delete-btn--confirm');
        });
      }

      // Resets the DELETION header to its resting label/color whenever a
      // different destructive confirm is armed, so only one confirm shows at a
      // time.
      function disarmDeleteAllLinksHeader() {
        const btn = document.getElementById('sharedLinksDeleteAllBtn');
        if (!btn) return;
        btn.classList.remove('shared-link-delete-all-header--confirm');
        btn.textContent = 'Deletion';
      }

      document.addEventListener('click', (e) => {
        if (e.target.closest('.trash-delete-btn')) return;
        document.querySelectorAll('.trash-delete-btn--confirm').forEach((b) => {
          b.classList.remove('trash-delete-btn--confirm');
        });
        if (!e.target.closest('.shared-link-delete-all-header')) {
          disarmDeleteAllLinksHeader();
        }
      });

      // Update Email / Update Password / Delete Account share one row
      // (.account-tab-row) with accordion behavior: at most one
      // .account-collapse-body is visible; clicking the open tab closes it.
      const accountTabs = [
        ['emailToggleBtn', 'emailBody'],
        ['passwordToggleBtn', 'passwordBody'],
        ['deleteToggleBtn', 'deleteBody'],
      ];
      accountTabs.forEach(([toggleId, bodyId]) => {
        const toggleBtn = document.getElementById(toggleId);
        const body = document.getElementById(bodyId);
        toggleBtn.addEventListener('click', () => {
          const wasOpen = !body.hidden;
          accountTabs.forEach(([otherToggleId, otherBodyId]) => {
            document.getElementById(otherBodyId).hidden = true;
            document.getElementById(otherToggleId).classList.remove('active');
          });
          if (!wasOpen) {
            body.hidden = false;
            toggleBtn.classList.add('active');
          }
        });
      });

      const emailForm = document.getElementById('emailForm');
      emailForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const errorEl = document.getElementById('emailError');
        const successEl = document.getElementById('emailSuccess');
        errorEl.classList.remove('show');
        successEl.classList.remove('show');
        const newEmail = document.getElementById('newEmail').value;
        const currentPassword = document.getElementById('emailPassword').value;
        const submitBtn = emailForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        try {
          const res = await fetch('/api/auth/change-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_email: newEmail, current_password: currentPassword }),
          });
          if (res.ok) {
            successEl.textContent = 'Email updated -- check your new inbox for a fresh verification link.';
            successEl.classList.add('show');
            emailForm.reset();
            return;
          }
          const data = await res.json().catch(() => ({}));
          errorEl.textContent = describeError(data, 'Could not update your email.');
          errorEl.classList.add('show');
        } catch (err) {
          errorEl.textContent = 'Something went wrong. Please try again.';
          errorEl.classList.add('show');
        } finally {
          submitBtn.disabled = false;
        }
      });

      const passwordForm = document.getElementById('passwordForm');
      passwordForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const errorEl = document.getElementById('passwordError');
        const successEl = document.getElementById('passwordSuccess');
        errorEl.classList.remove('show');
        successEl.classList.remove('show');
        const currentPassword = document.getElementById('currentPassword').value;
        const newPassword = document.getElementById('newPassword').value;
        const confirmNewPassword = document.getElementById('confirmNewPassword').value;
        if (newPassword !== confirmNewPassword) {
          errorEl.textContent = 'New passwords do not match.';
          errorEl.classList.add('show');
          return;
        }
        const submitBtn = passwordForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        try {
          const res = await fetch('/api/auth/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
          });
          if (res.ok) {
            successEl.textContent = 'Password updated. Every other signed-in session has been logged out.';
            successEl.classList.add('show');
            passwordForm.reset();
            return;
          }
          const data = await res.json().catch(() => ({}));
          errorEl.textContent = describeError(data, 'Could not update your password.');
          errorEl.classList.add('show');
        } catch (err) {
          errorEl.textContent = 'Something went wrong. Please try again.';
          errorEl.classList.add('show');
        } finally {
          submitBtn.disabled = false;
        }
      });

      const deleteForm = document.getElementById('deleteForm');
      const deleteSubmitBtn = document.getElementById('deleteSubmitBtn');
      const deletePasswordInput = document.getElementById('deletePassword');

      // Editing the password disarms the confirm step so a stale "ARE YOU SURE?"
      // can't delete on the next click.
      deletePasswordInput.addEventListener('input', () => {
        if (deleteSubmitBtn.dataset.armed === 'true') {
          deleteSubmitBtn.dataset.armed = 'false';
          deleteSubmitBtn.textContent = 'DELETE ACCOUNT';
        }
      });

      deleteForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const errorEl = document.getElementById('deleteError');
        errorEl.classList.remove('show');

        if (deleteSubmitBtn.dataset.armed !== 'true') {
          // First press only arms the confirm step (the password field is
          // required, so it can't be empty).
          deleteSubmitBtn.dataset.armed = 'true';
          deleteSubmitBtn.textContent = 'ARE YOU SURE?';
          return;
        }

        // Second press deletes. The server still checks the password
        // (/api/auth/delete-account).
        const currentPassword = deletePasswordInput.value;
        deleteSubmitBtn.disabled = true;
        try {
          const res = await fetch('/api/auth/delete-account', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: currentPassword }),
          });
          if (res.ok) {
            window.location.href = '/';
            return;
          }
          const data = await res.json().catch(() => ({}));
          errorEl.textContent = describeError(data, 'Could not delete your account.');
          errorEl.classList.add('show');
          // Back to the first step so a failed attempt doesn't leave it armed.
          deleteSubmitBtn.dataset.armed = 'false';
          deleteSubmitBtn.textContent = 'DELETE ACCOUNT';
        } catch (err) {
          errorEl.textContent = 'Something went wrong. Please try again.';
          errorEl.classList.add('show');
          deleteSubmitBtn.dataset.armed = 'false';
          deleteSubmitBtn.textContent = 'DELETE ACCOUNT';
        } finally {
          deleteSubmitBtn.disabled = false;
        }
      });

      // Linked Accounts list (step 7 of docs/multi-account-scoping.md): fetched
      // on load rather than server-rendered, as with other JS-populated lists,
      // since switch/remove/add change it. Pending friend-request counts per
      // character (GET /api/friends/notifications) drive the badge on each card.
      let friendNotif = { total: 0, byCharacter: {} };
      const gameAccountsList = document.getElementById('gameAccountsList');
      const gameAccountsError = document.getElementById('gameAccountsError');
      const addGameAccountBtn = document.getElementById('addGameAccountBtn');

      function renderGameAccountRow(gameAccount) {
        const row = document.createElement('div');
        row.className = 'game-account-row';

        const nameEl = document.createElement('span');
        nameEl.className = 'game-account-name' + (gameAccount.linked ? '' : ' game-account-name--unlinked');
        nameEl.textContent = gameAccount.linked ? gameAccount.runescape_name : 'Not yet linked';
        row.appendChild(nameEl);

        if (gameAccount.active) {
          const badge = document.createElement('span');
          badge.className = 'game-account-active-badge';
          badge.textContent = 'ACTIVE';
          nameEl.appendChild(badge);
        }

        // A friend request waiting on this character; SWITCH to it to see the
        // sender in the Friends section.
        const pendingFriendRequests = (friendNotif.byCharacter || {})[gameAccount.id] || 0;
        if (pendingFriendRequests > 0) {
          const friendBadge = document.createElement('span');
          friendBadge.className = 'friend-badge game-account-friend-badge';
          friendBadge.textContent = String(pendingFriendRequests);
          friendBadge.setAttribute(
            'data-tooltip',
            pendingFriendRequests === 1 ? 'New friend request' : pendingFriendRequests + ' new friend requests'
          );
          nameEl.appendChild(friendBadge);
        }

        const actions = document.createElement('div');
        actions.className = 'game-account-actions';

        if (!gameAccount.active) {
          const switchBtn = document.createElement('button');
          switchBtn.type = 'button';
          switchBtn.className = 'secondary';
          switchBtn.textContent = 'SWITCH';
          switchBtn.addEventListener('click', async () => {
            gameAccountsError.classList.remove('show');
            switchBtn.disabled = true;
            try {
              const res = await fetch(`/api/link/game-accounts/${gameAccount.id}/activate`, { method: 'POST' });
              if (res.ok) {
                await loadGameAccounts();
                return;
              }
              const data = await res.json().catch(() => ({}));
              gameAccountsError.textContent = describeError(data, 'Could not switch accounts.');
              gameAccountsError.classList.add('show');
            } catch (err) {
              gameAccountsError.textContent = 'Something went wrong. Please try again.';
              gameAccountsError.classList.add('show');
            } finally {
              switchBtn.disabled = false;
            }
          });
          actions.appendChild(switchBtn);
        }

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'trash-delete-btn';
        removeBtn.setAttribute('aria-label', 'Delete character');
        removeBtn.setAttribute('data-tooltip', 'Delete character');
        removeBtn.innerHTML = trashDeleteBtnHtml('ARE YOU SURE?');
        // Same two-step, click-away-to-cancel confirm as the Shared Links
        // DEACTIVATE button.
        wireTrashDeleteBtn(removeBtn, async () => {
          gameAccountsError.classList.remove('show');
          removeBtn.disabled = true;
          try {
            const res = await fetch(`/api/link/game-accounts/${gameAccount.id}`, { method: 'DELETE' });
            if (res.ok) {
              await loadGameAccounts();
              return;
            }
            const data = await res.json().catch(() => ({}));
            gameAccountsError.textContent = describeError(data, 'Could not remove this account.');
            gameAccountsError.classList.add('show');
            removeBtn.classList.remove('trash-delete-btn--confirm');
          } catch (err) {
            gameAccountsError.textContent = 'Something went wrong. Please try again.';
            gameAccountsError.classList.add('show');
            removeBtn.classList.remove('trash-delete-btn--confirm');
          } finally {
            removeBtn.disabled = false;
          }
        });
        actions.appendChild(removeBtn);

        row.appendChild(actions);
        return row;
      }

      async function loadGameAccounts() {
        gameAccountsError.classList.remove('show');
        try {
          const [res, notifRes] = await Promise.all([
            fetch('/api/link/game-accounts'),
            fetch('/api/friends/notifications').catch(() => null),
          ]);
          if (!res.ok) {
            gameAccountsError.textContent = 'Could not load your linked accounts.';
            gameAccountsError.classList.add('show');
            return;
          }
          if (notifRes && notifRes.ok) {
            friendNotif = await notifRes.json().catch(() => friendNotif);
          }
          const gameAccounts = await res.json();
          gameAccountsList.innerHTML = '';
          gameAccounts.forEach((gameAccount) => gameAccountsList.appendChild(renderGameAccountRow(gameAccount)));
          // The active character may have changed (SWITCH/delete), so Friends
          // follows it.
          loadFriends();
        } catch (err) {
          gameAccountsError.textContent = 'Something went wrong. Please try again.';
          gameAccountsError.classList.add('show');
        }
      }

      addGameAccountBtn.addEventListener('click', async () => {
        gameAccountsError.classList.remove('show');
        addGameAccountBtn.disabled = true;
        try {
          const res = await fetch('/api/link/game-accounts', { method: 'POST' });
          if (res.ok) {
            // Reload (not just a re-fetch): the new slot becomes the session's
            // active GameAccount and the header's link banner (_link_banner in
            // app/pages.py) needs a fresh load to show its GENERATE CODE button.
            window.location.reload();
            return;
          }
          const data = await res.json().catch(() => ({}));
          gameAccountsError.textContent = describeError(data, 'Could not add another account.');
          gameAccountsError.classList.add('show');
        } catch (err) {
          gameAccountsError.textContent = 'Something went wrong. Please try again.';
          gameAccountsError.classList.add('show');
        } finally {
          addGameAccountBtn.disabled = false;
        }
      });

      // Shared Links: one row per valid share link from this Account's
      // GameAccounts (GET /api/account/shared-links; DELETE
      // /api/account/shared-links/<id>, see app/routers/account.py). Fetched on
      // load. sharedLinksData holds the last fetch; headers re-sort it in place,
      // like Storages Viewer's state.items/renderTable.
      const sharedLinksTableWrap = document.getElementById('sharedLinksTableWrap');
      const sharedLinksTableBody = document.getElementById('sharedLinksTableBody');
      const sharedLinksEmpty = document.getElementById('sharedLinksEmpty');
      const sharedLinksError = document.getElementById('sharedLinksError');
      let sharedLinksData = [];
      // Starts sorted by EXPIRATION, newest first, which matches the server
      // order (created_at desc); a sort stays active from then on.
      let sharedLinksSortKey = 'expiration';
      let sharedLinksSortDir = 'desc';

      // YYYY-MM-DD in the viewer's local timezone (server sends UTC), built from
      // getFullYear/getMonth/getDate so the format doesn't vary by locale. A
      // timestamp without a zone suffix is treated as UTC. Shared by the Shared
      // Links EXPIRATION column and the Friends SINCE column.
      function fmtLocalDate(iso) {
        if (!iso) return '\u2014';
        const hasZone = /[zZ]$|[+-]\\d{2}:?\\d{2}$/.test(iso);
        const d = new Date(hasZone ? iso : iso + 'Z');
        if (isNaN(d.getTime())) return '\u2014';
        const pad = (n) => String(n).padStart(2, '0');
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
      }

      function fmtExpiration(iso) {
        return fmtLocalDate(iso);
      }

      // No 'code' case: the Code column isn't sortable (plain text).
      function sharedLinkSortValue(link, key) {
        if (key === 'character') return (link.character_name || 'Unknown character').toLowerCase();
        if (key === 'app') return link.content_type_label.toLowerCase();
        if (key === 'expiration') return new Date(link.expires_at).getTime();
        return '';
      }

      function renderSharedLinkRow(link) {
        const row = document.createElement('tr');

        const characterCell = document.createElement('td');
        characterCell.textContent = link.character_name || 'Unknown character';
        row.appendChild(characterCell);

        const appCell = document.createElement('td');
        appCell.textContent = link.content_type_label;
        row.appendChild(appCell);

        const codeCell = document.createElement('td');
        const codeBtn = document.createElement('button');
        codeBtn.type = 'button';
        codeBtn.className = 'shared-link-code-btn';
        codeBtn.textContent = link.code;
        codeBtn.setAttribute('data-tooltip', 'Click to copy');
        // Copies the full https://myscape.io/s/<code> URL (link.url, built
        // server-side, see SharedLinkSummary in app/schemas.py), not just the
        // code shown, then flashes "COPIED" like publicProfileLinkBtn and
        // lootShareLinkBtn. The button's fixed width (.shared-link-code-btn in
        // myscape.css) keeps it from resizing.
        codeBtn.addEventListener('click', async () => {
          try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
              await navigator.clipboard.writeText(link.url);
            } else {
              const temp = document.createElement('textarea');
              temp.value = link.url;
              temp.style.position = 'fixed';
              temp.style.opacity = '0';
              document.body.appendChild(temp);
              temp.select();
              document.execCommand('copy');
              document.body.removeChild(temp);
            }
            codeBtn.textContent = 'COPIED';
            setTimeout(() => { codeBtn.textContent = link.code; }, 1200);
          } catch (err) {
            sharedLinksError.textContent = 'Could not copy the link -- please copy it manually.';
            sharedLinksError.classList.add('show');
          }
        });
        codeCell.appendChild(codeBtn);
        row.appendChild(codeCell);

        const expirationCell = document.createElement('td');
        expirationCell.textContent = fmtExpiration(link.expires_at);
        row.appendChild(expirationCell);

        const actionCell = document.createElement('td');
        const deactivateBtn = document.createElement('button');
        deactivateBtn.type = 'button';
        deactivateBtn.className = 'trash-delete-btn';
        deactivateBtn.setAttribute('aria-label', 'Delete');
        deactivateBtn.setAttribute('data-tooltip', 'Delete');
        deactivateBtn.innerHTML = trashDeleteBtnHtml('SURE?');
        // Same two-step, click-away-to-cancel confirm as DELETE CHARACTER below.
        wireTrashDeleteBtn(deactivateBtn, async () => {
          sharedLinksError.classList.remove('show');
          deactivateBtn.disabled = true;
          try {
            const res = await fetch(`/api/account/shared-links/${link.id}`, { method: 'DELETE' });
            if (res.ok) {
              await loadSharedLinks();
              return;
            }
            const data = await res.json().catch(() => ({}));
            sharedLinksError.textContent = describeError(data, 'Could not deactivate this link.');
            sharedLinksError.classList.add('show');
            deactivateBtn.classList.remove('trash-delete-btn--confirm');
          } catch (err) {
            sharedLinksError.textContent = 'Something went wrong. Please try again.';
            sharedLinksError.classList.add('show');
            deactivateBtn.classList.remove('trash-delete-btn--confirm');
          } finally {
            deactivateBtn.disabled = false;
          }
        });
        actionCell.appendChild(deactivateBtn);
        row.appendChild(actionCell);

        return row;
      }

      function renderSharedLinksTable() {
        sharedLinksTableBody.innerHTML = '';
        if (sharedLinksData.length === 0) {
          sharedLinksTableWrap.style.display = 'none';
          sharedLinksEmpty.style.display = '';
          return;
        }
        sharedLinksEmpty.style.display = 'none';
        sharedLinksTableWrap.style.display = '';
        let rows = sharedLinksData;
        if (sharedLinksSortKey) {
          rows = rows.slice().sort((a, b) => {
            const av = sharedLinkSortValue(a, sharedLinksSortKey);
            const bv = sharedLinkSortValue(b, sharedLinksSortKey);
            if (av < bv) return sharedLinksSortDir === 'asc' ? -1 : 1;
            if (av > bv) return sharedLinksSortDir === 'asc' ? 1 : -1;
            return 0;
          });
        }
        rows.forEach((link) => sharedLinksTableBody.appendChild(renderSharedLinkRow(link)));
      }

      // DELETION header: a destructive bulk action, not a sort column. First
      // click arms it (red, "SURE?"), a second revokes all of the account's
      // share links. Click-away cancel goes through disarmDeleteAllLinksHeader
      // in the shared document click listener above.
      const sharedLinksDeleteAllBtn = document.getElementById('sharedLinksDeleteAllBtn');
      if (sharedLinksDeleteAllBtn) {
        sharedLinksDeleteAllBtn.addEventListener('click', async () => {
          if (!sharedLinksDeleteAllBtn.classList.contains('shared-link-delete-all-header--confirm')) {
            document.querySelectorAll('.trash-delete-btn--confirm').forEach((b) => {
              b.classList.remove('trash-delete-btn--confirm');
            });
            sharedLinksDeleteAllBtn.classList.add('shared-link-delete-all-header--confirm');
            sharedLinksDeleteAllBtn.textContent = 'SURE?';
            return;
          }
          sharedLinksError.classList.remove('show');
          sharedLinksDeleteAllBtn.disabled = true;
          try {
            const res = await fetch('/api/account/shared-links', { method: 'DELETE' });
            if (res.ok) {
              await loadSharedLinks();
              return;
            }
            const data = await res.json().catch(() => ({}));
            sharedLinksError.textContent = describeError(data, 'Could not delete your shared links.');
            sharedLinksError.classList.add('show');
          } catch (err) {
            sharedLinksError.textContent = 'Something went wrong. Please try again.';
            sharedLinksError.classList.add('show');
          } finally {
            sharedLinksDeleteAllBtn.disabled = false;
            disarmDeleteAllLinksHeader();
          }
        });
      }

      // Header clicks sort the fetched data in place (no re-fetch); clicking the
      // active column flips direction, like Storages Viewer's .pm-sort-header.
      // Deletion isn't sortable (see sharedLinksDeleteAllBtn above).
      const sharedLinkSortHeaders = document.querySelectorAll('.shared-link-sort-header');
      function updateSharedLinkSortHeaders() {
        sharedLinkSortHeaders.forEach((btn) => {
          const key = btn.getAttribute('data-sort-key');
          const arrow = btn.querySelector('.shared-link-sort-arrow');
          if (key === sharedLinksSortKey) {
            btn.classList.add('active');
            arrow.textContent = sharedLinksSortDir === 'asc' ? ' \u2191' : ' \u2193';
          } else {
            btn.classList.remove('active');
            arrow.textContent = '';
          }
        });
      }
      // A sort is always active. A newly clicked column starts EXPIRATION newest
      // first and others ascending; clicking the active column flips it.
      sharedLinkSortHeaders.forEach((btn) => {
        btn.addEventListener('click', () => {
          const key = btn.getAttribute('data-sort-key');
          if (key !== sharedLinksSortKey) {
            sharedLinksSortKey = key;
            sharedLinksSortDir = key === 'expiration' ? 'desc' : 'asc';
          } else {
            sharedLinksSortDir = sharedLinksSortDir === 'asc' ? 'desc' : 'asc';
          }
          updateSharedLinkSortHeaders();
          renderSharedLinksTable();
        });
      });

      async function loadSharedLinks() {
        sharedLinksError.classList.remove('show');
        try {
          const res = await fetch('/api/account/shared-links');
          if (!res.ok) {
            sharedLinksError.textContent = 'Could not load your shared links.';
            sharedLinksError.classList.add('show');
            return;
          }
          sharedLinksData = await res.json();
          renderSharedLinksTable();
        } catch (err) {
          sharedLinksError.textContent = 'Something went wrong. Please try again.';
          sharedLinksError.classList.add('show');
        }
      }


      // Friends follows the session's ACTIVE character (GET /api/friends is
      // scoped server-side), so loadGameAccounts calls loadFriends at its end
      // (initial load, SWITCH, delete).
      const friendsHint = document.getElementById('friendsHint');
      const friendsBody = document.getElementById('friendsBody');
      const friendsCodeWrap = document.getElementById('friendsCodeWrap');
      const friendsCodeBtn = document.getElementById('friendsCodeBtn');
      const friendsAddForm = document.getElementById('friendsAddForm');
      const friendsAddInput = document.getElementById('friendsAddInput');
      const friendsAddBtn = document.getElementById('friendsAddBtn');
      const friendsError = document.getElementById('friendsError');
      const friendsSuccess = document.getElementById('friendsSuccess');
      const friendsRequests = document.getElementById('friendsRequests');
      const friendsRequestsList = document.getElementById('friendsRequestsList');
      const friendsTableWrap = document.getElementById('friendsTableWrap');
      const friendsTableBody = document.getElementById('friendsTableBody');
      const friendsEmpty = document.getElementById('friendsEmpty');
      let friendsCode = '';
      // Friends as last fetched (server order A-Z) plus the FRIEND/SINCE header
      // sort, same always-sorted cycle as Shared Links.
      let friendsData = [];
      // Starts sorted by SINCE, newest first.
      let friendsSortKey = 'since';
      let friendsSortDir = 'desc';

      // Circle with a dash (not a trash can); keeps .trash-delete-icon (same
      // shape as TRASH_ICON_SVG) to reuse the arm-then-confirm machinery.
      const REMOVE_FRIEND_ICON_SVG = '<svg class="trash-delete-icon" width="15" height="15" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><circle cx="8" cy="8" r="6.3" stroke="currentColor" stroke-width="1.4"/><path d="M5 8H11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';

      function clearFriendsMessages() {
        friendsError.classList.remove('show');
        friendsSuccess.classList.remove('show');
      }
      function showFriendsError(message) {
        friendsSuccess.classList.remove('show');
        friendsError.textContent = message;
        friendsError.classList.add('show');
      }
      function showFriendsSuccess(message) {
        friendsError.classList.remove('show');
        friendsSuccess.textContent = message;
        friendsSuccess.classList.add('show');
      }
      function refreshHeaderFriendBadge() {
        if (window.myscapePollFriendNotifications) window.myscapePollFriendNotifications();
      }

      async function copyFriendText(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
        } else {
          const temp = document.createElement('textarea');
          temp.value = text;
          temp.style.position = 'fixed';
          temp.style.opacity = '0';
          document.body.appendChild(temp);
          temp.select();
          document.execCommand('copy');
          document.body.removeChild(temp);
        }
      }

      friendsCodeBtn.addEventListener('click', async () => {
        try {
          await copyFriendText(friendsCode);
          friendsCodeBtn.textContent = 'COPIED';
          setTimeout(() => { friendsCodeBtn.textContent = friendsCode; }, 1200);
        } catch (err) {
          showFriendsError('Could not copy your code -- please copy it manually.');
        }
      });

      function renderFriendRequestRow(request) {
        const row = document.createElement('div');
        row.className = 'friend-request-row';

        const nameEl = document.createElement('span');
        nameEl.className = 'friend-request-name';
        nameEl.textContent = request.name;
        row.appendChild(nameEl);

        const actions = document.createElement('div');
        actions.className = 'friend-request-actions';

        async function respond(method, url, failMessage, btn) {
          clearFriendsMessages();
          btn.disabled = true;
          try {
            const res = await fetch(url, { method: method });
            if (res.ok) {
              await loadFriends();
              refreshHeaderFriendBadge();
              return;
            }
            const data = await res.json().catch(() => ({}));
            showFriendsError(describeError(data, failMessage));
          } catch (err) {
            showFriendsError('Something went wrong. Please try again.');
          } finally {
            btn.disabled = false;
          }
        }

        const acceptBtn = document.createElement('button');
        acceptBtn.type = 'button';
        acceptBtn.className = 'secondary';
        acceptBtn.textContent = 'ACCEPT';
        acceptBtn.addEventListener('click', () => {
          respond('POST', `/api/friends/requests/${request.id}/accept`, 'Could not accept this request.', acceptBtn);
        });
        actions.appendChild(acceptBtn);

        const declineBtn = document.createElement('button');
        declineBtn.type = 'button';
        declineBtn.className = 'secondary friend-decline-btn';
        declineBtn.textContent = 'DECLINE';
        declineBtn.addEventListener('click', () => {
          respond('DELETE', `/api/friends/requests/${request.id}`, 'Could not decline this request.', declineBtn);
        });
        actions.appendChild(declineBtn);

        row.appendChild(actions);
        return row;
      }

      function renderFriendRow(friend) {
        const row = document.createElement('tr');

        const nameCell = document.createElement('td');
        if (friend.code) {
          const link = document.createElement('a');
          link.className = 'friend-name-link';
          link.href = '/c/' + encodeURIComponent(friend.code);
          link.textContent = friend.name;
          link.setAttribute('data-tooltip', 'Visit profile');
          nameCell.appendChild(link);
        } else {
          nameCell.textContent = friend.name;
        }
        row.appendChild(nameCell);

        const sinceCell = document.createElement('td');
        sinceCell.textContent = fmtLocalDate(friend.since);
        row.appendChild(sinceCell);

        const removeCell = document.createElement('td');
        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'trash-delete-btn friend-remove-btn';
        removeBtn.setAttribute('aria-label', 'Remove friend');
        removeBtn.setAttribute('data-tooltip', 'Remove friend');
        removeBtn.innerHTML = REMOVE_FRIEND_ICON_SVG + '<span class="trash-delete-confirm">SURE?</span>';
        wireTrashDeleteBtn(removeBtn, async () => {
          clearFriendsMessages();
          removeBtn.disabled = true;
          try {
            const res = await fetch(`/api/friends/${friend.id}`, { method: 'DELETE' });
            if (res.ok) {
              await loadFriends();
              return;
            }
            const data = await res.json().catch(() => ({}));
            showFriendsError(describeError(data, 'Could not remove this friend.'));
            removeBtn.classList.remove('trash-delete-btn--confirm');
          } catch (err) {
            showFriendsError('Something went wrong. Please try again.');
            removeBtn.classList.remove('trash-delete-btn--confirm');
          } finally {
            removeBtn.disabled = false;
          }
        });
        removeCell.appendChild(removeBtn);
        row.appendChild(removeCell);

        return row;
      }

      function renderFriendsTable() {
        friendsTableBody.innerHTML = '';
        if (friendsData.length === 0) {
          friendsTableWrap.style.display = 'none';
          friendsEmpty.style.display = '';
          return;
        }
        friendsEmpty.style.display = 'none';
        friendsTableWrap.style.display = '';
        let rows = friendsData;
        if (friendsSortKey) {
          rows = rows.slice().sort((a, b) => {
            const av = friendsSortKey === 'since' ? (a.since || '') : a.name.toLowerCase();
            const bv = friendsSortKey === 'since' ? (b.since || '') : b.name.toLowerCase();
            if (av < bv) return friendsSortDir === 'asc' ? -1 : 1;
            if (av > bv) return friendsSortDir === 'asc' ? 1 : -1;
            return 0;
          });
        }
        rows.forEach((friend) => friendsTableBody.appendChild(renderFriendRow(friend)));
      }

      const friendSortHeaders = document.querySelectorAll('.friend-sort-header');
      function updateFriendSortHeaders() {
        friendSortHeaders.forEach((btn) => {
          const arrow = btn.querySelector('.friend-sort-arrow');
          if (btn.getAttribute('data-friend-sort-key') === friendsSortKey) {
            btn.classList.add('active');
            arrow.textContent = friendsSortDir === 'asc' ? ' \u2191' : ' \u2193';
          } else {
            btn.classList.remove('active');
            arrow.textContent = '';
          }
        });
      }
      friendSortHeaders.forEach((btn) => {
        btn.addEventListener('click', () => {
          const key = btn.getAttribute('data-friend-sort-key');
          // Same always-sorted behavior as Shared Links: SINCE starts newest
          // first, FRIEND A-Z; the active column flips.
          if (key !== friendsSortKey) {
            friendsSortKey = key;
            friendsSortDir = key === 'since' ? 'desc' : 'asc';
          } else {
            friendsSortDir = friendsSortDir === 'asc' ? 'desc' : 'asc';
          }
          updateFriendSortHeaders();
          renderFriendsTable();
        });
      });

      // Show the default sort in the headers immediately.
      updateFriendSortHeaders();

      function showFriendsHint(message) {
        friendsHint.textContent = message;
        friendsHint.hidden = false;
        friendsBody.hidden = true;
        friendsCodeWrap.hidden = true;
      }

      async function loadFriends() {
        clearFriendsMessages();
        try {
          const res = await fetch('/api/friends');
          if (res.status === 403) {
            showFriendsHint('Verify your email to use friends.');
            return;
          }
          if (res.status === 409) {
            showFriendsHint('Add a character to use friends.');
            return;
          }
          if (!res.ok) {
            showFriendsError('Could not load your friends.');
            return;
          }
          const data = await res.json();
          if (data.linked === false) {
            showFriendsHint('Link this character to use friends.');
            return;
          }
          friendsHint.hidden = true;
          friendsBody.hidden = false;
          friendsCode = data.code || '';
          friendsCodeBtn.textContent = friendsCode;
          friendsCodeWrap.hidden = !friendsCode;

          friendsRequestsList.innerHTML = '';
          data.incoming.forEach((request) => friendsRequestsList.appendChild(renderFriendRequestRow(request)));
          friendsRequests.hidden = data.incoming.length === 0;

          friendsData = data.friends;
          renderFriendsTable();
        } catch (err) {
          showFriendsError('Something went wrong. Please try again.');
        }
      }

      friendsAddForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        clearFriendsMessages();
        const code = friendsAddInput.value.trim();
        if (!code) return;
        friendsAddBtn.disabled = true;
        try {
          const res = await fetch('/api/friends/requests', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: code }),
          });
          const data = await res.json().catch(() => ({}));
          if (res.ok) {
            friendsAddInput.value = '';
            showFriendsSuccess(
              data.status === 'accepted'
                ? `You and ${data.name} are now friends.`
                : 'If there is a character with that code, a friend request has been sent.'
            );
            if (data.status === 'accepted') {
              await loadFriends();
              showFriendsSuccess(`You and ${data.name} are now friends.`);
              refreshHeaderFriendBadge();
            }
            return;
          }
          showFriendsError(describeError(data, 'Could not send that request.'));
        } catch (err) {
          showFriendsError('Something went wrong. Please try again.');
        } finally {
          friendsAddBtn.disabled = false;
        }
      });

      // The header poll (see _shell) broadcasts each result. When per-character
      // counts change, rebuild the card badges and the Friends section
      // (loadGameAccounts reloads it).
      window.addEventListener('myscape:friend-notifications', (e) => {
        const next = e.detail || { total: 0, byCharacter: {} };
        const changed = JSON.stringify(friendNotif.byCharacter) !== JSON.stringify(next.byCharacter);
        friendNotif = next;
        if (changed) loadGameAccounts();
      });

      // The friend code field only takes focus on a click or tab into it; any
      // other focus (browser, restored page, stray label click) is bounced off.
      let friendsInputIntent = false;
      document.addEventListener('pointerdown', (e) => {
        friendsInputIntent = e.target === friendsAddInput;
      }, true);
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Tab') friendsInputIntent = true;
      }, true);
      friendsAddInput.addEventListener('focus', () => {
        if (!friendsInputIntent) friendsAddInput.blur();
      });
      friendsAddInput.addEventListener('blur', () => { friendsInputIntent = false; });
      if (document.activeElement === friendsAddInput) friendsAddInput.blur();

      // Show the default sort in the headers immediately.
      updateSharedLinkSortHeaders();

      loadGameAccounts();
      loadSharedLinks();
    })();
    """
    return _shell(title="Account — myscape", player=player, body=body, extra_script=script)


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
          <div class="field">
            <label for="confirmPassword">Confirm password</label>
            <input type="password" id="confirmPassword" name="confirmPassword" placeholder="Re-enter your password" required minlength="8" />
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
      const password = document.getElementById('password').value;
      const confirmPassword = document.getElementById('confirmPassword').value;
      if (password !== confirmPassword) {
        errorEl.textContent = 'Passwords do not match.';
        errorEl.classList.add('show');
        return;
      }
      const submitBtn = e.target.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      try {
        const res = await fetch('/api/auth/signup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: document.getElementById('email').value,
            password: password,
          }),
        });
        if (res.ok) {
          // Straight to the dashboard, same as the login redirect below.
          window.location.href = '/dashboard';
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


def render_signup_coming_soon() -> str:
    """What /signup shows while sign-ups are switched off (see
    app/site_flags.py). Stands in for render_signup, which is untouched so
    re-enabling is just flipping the flag. Existing accounts can still log in,
    hence the link.
    """
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>SIGN UP</h2>
        <p class="verify-email-message signup-closed-message">myscape is coming soon.</p>
        <div class="auth-switch">Already have an account? <a href="/login">LOG IN</a></div>
      </div>
    </div>
    """
    return _shell(title="Coming soon — myscape", player=None, body=body)


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
          <div class="auth-forgot"><a href="/forgot-password">FORGOT PASSWORD?</a></div>
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
          // Go straight to the dashboard rather than the landing page.
          window.location.href = '/dashboard';
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


def render_forgot_password() -> str:
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>FORGOT PASSWORD</h2>
        <div class="auth-error" id="formError"></div>
        <div class="auth-success" id="formSuccess"></div>
        <form id="forgotForm">
          <div class="field">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" placeholder="you@example.com" required />
          </div>
          <button class="primary" type="submit">SEND RESET LINK</button>
        </form>
        <div class="auth-switch"><a href="/login">BACK TO LOG IN</a></div>
      </div>
    </div>
    """
    script = """
    document.getElementById('forgotForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const form = e.target;
      const errorEl = document.getElementById('formError');
      const successEl = document.getElementById('formSuccess');
      errorEl.classList.remove('show');
      successEl.classList.remove('show');
      const submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      try {
        const res = await fetch('/api/auth/forgot-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: document.getElementById('email').value,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
          // The backend returns the same generic message whether or not the
          // email has an account (see forgot_password in app/routers/auth.py),
          // so any 200 just swaps it in.
          form.style.display = 'none';
          successEl.textContent = data.detail || "If that email has an account, we've sent a password reset link.";
          successEl.classList.add('show');
          return;
        }
        errorEl.textContent = describeError(data, 'Something went wrong. Please try again.');
        errorEl.classList.add('show');
      } catch (err) {
        errorEl.textContent = 'Something went wrong. Please try again.';
        errorEl.classList.add('show');
      } finally {
        submitBtn.disabled = false;
      }
    });
    """
    return _shell(title="Forgot password — myscape", player=None, body=body, extra_script=script)


def render_reset_password() -> str:
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>RESET PASSWORD</h2>
        <div class="auth-error" id="formError"></div>
        <div class="auth-error" id="noTokenError">
          This password reset link is missing or invalid.
          <a href="/forgot-password">Request a new one</a>.
        </div>
        <form id="resetForm">
          <div class="field">
            <label for="password">New password</label>
            <input type="password" id="password" name="password" placeholder="At least 8 characters" required minlength="8" />
          </div>
          <div class="field">
            <label for="confirmPassword">Confirm new password</label>
            <input type="password" id="confirmPassword" name="confirmPassword" placeholder="Re-enter your new password" required minlength="8" />
          </div>
          <button class="primary" type="submit">RESET PASSWORD</button>
        </form>
      </div>
    </div>
    """
    script = """
    (function () {
      const token = new URLSearchParams(window.location.search).get('token');
      const form = document.getElementById('resetForm');
      const noTokenError = document.getElementById('noTokenError');
      if (!token) {
        // No token in the URL: nothing to submit, so offer a fresh reset request
        // instead of an empty form.
        form.style.display = 'none';
        noTokenError.classList.add('show');
        return;
      }
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const errorEl = document.getElementById('formError');
        errorEl.classList.remove('show');
        const password = document.getElementById('password').value;
        const confirmPassword = document.getElementById('confirmPassword').value;
        if (password !== confirmPassword) {
          errorEl.textContent = 'Passwords do not match.';
          errorEl.classList.add('show');
          return;
        }
        const submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        try {
          const res = await fetch('/api/auth/reset-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: token, password: password }),
          });
          if (res.ok) {
            // reset_password logs the player in on success
            // (app/routers/auth.py), so go straight into the app.
            window.location.href = '/dashboard';
            return;
          }
          const data = await res.json().catch(() => ({}));
          errorEl.textContent = describeError(data, 'Could not reset your password. The link may have expired.');
          errorEl.classList.add('show');
        } catch (err) {
          errorEl.textContent = 'Something went wrong. Please try again.';
          errorEl.classList.add('show');
        } finally {
          submitBtn.disabled = false;
        }
      });
    })();
    """
    return _shell(title="Reset password — myscape", player=None, body=body, extra_script=script)


def render_verify_email_required(player: PlayerView) -> str:
    body = f"""
    <div class="auth-shell">
      <div class="auth-card">
        <h2>VERIFY YOUR EMAIL</h2>
        <div class="auth-error" id="formError"></div>
        <div class="auth-success" id="formSuccess"></div>
        <p class="verify-email-message">We sent a confirmation link to <strong>{escape(player.email or "your email address")}</strong>.<br>Click it to finish setting up your account.</p>
        <button class="primary" id="resendBtn" type="button">RESEND EMAIL</button>
      </div>
    </div>
    """
    script = """
    document.getElementById('resendBtn').addEventListener('click', async (e) => {
      const btn = e.target;
      const errorEl = document.getElementById('formError');
      const successEl = document.getElementById('formSuccess');
      errorEl.classList.remove('show');
      successEl.classList.remove('show');
      btn.disabled = true;
      try {
        const res = await fetch('/api/auth/resend-verification-email', { method: 'POST' });
        if (res.ok) {
          successEl.textContent = "A new confirmation link is on its way.";
          successEl.classList.add('show');
          return;
        }
        const data = await res.json().catch(() => ({}));
        errorEl.textContent = describeError(data, 'Could not resend the email. Please try again.');
        errorEl.classList.add('show');
      } catch (err) {
        errorEl.textContent = 'Something went wrong. Please try again.';
        errorEl.classList.add('show');
      } finally {
        btn.disabled = false;
      }
    });
    """
    return _shell(title="Verify your email — myscape", player=player, body=body, extra_script=script)


def render_verify_email(player: Optional[PlayerView] = None) -> str:
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>VERIFY EMAIL</h2>
        <div class="auth-error" id="formError"></div>
        <div class="auth-error" id="noTokenError">
          You need to verify your email to access this content.<br>Your code may be expired — please try again.
        </div>
        <p class="verify-email-message" id="verifyingMessage">Confirming your email&hellip;</p>
      </div>
    </div>
    """
    script = """
    (function () {
      const token = new URLSearchParams(window.location.search).get('token');
      const noTokenError = document.getElementById('noTokenError');
      const verifyingMessage = document.getElementById('verifyingMessage');
      const errorEl = document.getElementById('formError');
      if (!token) {
        // No token in the URL: same no-token case as render_reset_password.
        verifyingMessage.style.display = 'none';
        noTokenError.classList.add('show');
        return;
      }
      (async () => {
        try {
          const res = await fetch('/api/auth/verify-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: token }),
          });
          if (res.ok) {
            // verify_email logs the player in on success (app/routers/auth.py),
            // so go straight into the app.
            window.location.href = '/dashboard';
            return;
          }
          const data = await res.json().catch(() => ({}));
          verifyingMessage.style.display = 'none';
          errorEl.textContent = describeError(data, 'Could not verify your email. The link may have expired.');
          errorEl.classList.add('show');
        } catch (err) {
          verifyingMessage.style.display = 'none';
          errorEl.textContent = 'Something went wrong. Please try again.';
          errorEl.classList.add('show');
        }
      })();
    })();
    """
    return _shell(title="Verify email — myscape", player=player, body=body, extra_script=script)


def render_not_found(player: Optional[PlayerView] = None) -> str:
    """The styled 404 page, used by the exception handler in app/main.py. The
    handler loads the player itself and passes it in, so the header shows
    Dashboard/Log out for signed-in visitors. The same check points the
    home-teleport icon at /dashboard when signed in and / otherwise.
    """
    teleport_href = "/dashboard" if player else "/"
    body = f"""
    <div class="auth-shell not-found-shell">
      <div class="auth-card">
        <h2>PAGE NOT FOUND</h2>
        <div class="not-found-code">404</div>
        <a href="{teleport_href}" class="not-found-teleport" title="Cast Home Teleport">
          <img class="not-found-icon" src="/static/img/icon-home-teleport.png" alt="Home Teleport icon" />
        </a>
        <p class="verify-email-message">You must be lost, friend.<br>Try casting your home teleport.</p>
      </div>
    </div>
    """
    return _shell(title="Page not found — myscape", player=player, body=body)


def _purchase_goals_panel_markup() -> Tuple[str, str, str]:
    """Builds Purchase Goals' (extra_head, body, script) triple. Split from
    render_purchase_goals so the landing page preview
    (render_landing_purchase_preview) can embed the same panel. Doesn't
    reference `player`: everything below the header shell is rendered
    client-side from one polled JSON payload (GET /api/gear-setups), so
    mutation endpoints can return fresh state and reuse the same render().
    """
    extra_head = (
        f'<link rel="stylesheet" href="/static/css/purchase-goals.css?v={_PURCHASE_GOALS_CSS_VERSION}" />'
    )

    # Share icon next to the title (same markup as Loot Tracker's
    # loot_share_icon_btn, duplicated rather than shared across stylesheets).
    # Toggles pgShareCard, which holds the share-link flow for the active setup
    # (PG.activeSetupId); see pgShareGenerateBtn and
    # build_purchase_goal_share_snapshot in app/purchase_goals.py.
    purchase_share_icon_btn = (
        ' <span class="pg-share-wrap">'
        '<button type="button" class="pg-share-icon-btn" id="pgShareIconBtn" aria-label="Export the currently selected setup" data-tooltip="Export the currently selected setup">'
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
        '<polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line>'
        '</svg></button>'
        '<div class="pg-share-card" id="pgShareCard" hidden>'
        '<button type="button" class="pg-share-generate-btn" id="pgShareGenerateBtn">GENERATE SHAREABLE LINK</button>'
        '<button type="button" class="pg-share-link-btn" id="pgShareLinkBtn" data-tooltip="Click to copy" hidden></button>'
        '<p class="pg-share-popup-hint">Links are active for 30 days, but can be<br>deleted sooner on your Account page.</p>'
        '</div>'
        '</span>'
    )

    body = f"""
    <h2 class="page-title">Purchase Goals{purchase_share_icon_btn}</h2>

    <div class="pg-header">
      <div class="tracker-icon-row" id="setupIconRow"></div>
      <div class="tracker-menu-wrap">
        <button class="icon-menu-btn" id="setupMenuBtn" type="button" data-tooltip="Setup options">
          <span class="hamburger-icon"><span></span><span></span><span></span></span>
        </button>
        <div class="tracker-menu" id="setupMenu" style="display:none;">
          <button class="tracker-menu-item" id="menuNewSetup" type="button">New setup</button>
          <button class="tracker-menu-item" id="menuDuplicateSetup" type="button">Duplicate setup</button>
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
        <img class="overlay-icon" src="{_ICON_COINS}" alt="Coins" />
        <span class="overlay-amount" id="pgCoinsAmount">0 gp</span>
      </div>
      <div class="overlay-progress">
        <div class="progress-track overlay-track"><div class="progress-fill" id="pgOverlayFill" style="width:0%;"></div></div>
      </div>
      <div class="overlay-side overlay-target">
        <div class="overlay-icon-wrap" id="pgIconTrigger">
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
      var PG = {
        data: null,
        activeSetupId: null,
        picker: null,       // { slotType, slot, targets } while a gear/inventory slot is open for editing
        iconPicker: false,  // true while the setup-icon picker is open
        nameFormMode: null, // 'new' | 'rename' | null
        // Sockets shift-clicked into a pending group (see
        // toggleSlotSelected/wireSlotClicks). Cleared on setup switch, icon
        // picker open, or plain click outside the group.
        multiSelect: [],    // [{ slotType, slot }, ...]
        pollTimer: null,
        dragSuppressClick: false, // true for one click right after a completed drag-and-drop (see wireSlotClicks)
        // True while a "Still to Purchase" row is being dragged. The background
        // poll skips while set: loadState() -> render() rebuilds #pgSummaryList
        // and would pull the dragged node out of the DOM, ending the native
        // drag.
        dragging: false,
        // Bumped whenever a direct action (click, drop, submit) applies a server
        // response to PG.data. loadState() snapshots it before its fetch and
        // drops the poll's response if it changed meanwhile.
        stateVersion: 0,
      };

      // Remembers the last active setup across reloads. Plain localStorage,
      // deliberately not scoped per player: a stale id matches no setup and
      // loadState falls back to the first. try/catch because storage can throw
      // (private browsing, disabled/full).
      var ACTIVE_SETUP_STORAGE_KEY = 'myscape:purchaseGoals:activeSetupId';
      function loadStoredActiveSetupId() {
        try { return localStorage.getItem(ACTIVE_SETUP_STORAGE_KEY); } catch (e) { return null; }
      }
      function setActiveSetupId(id) {
        // A generated link describes the setup active when it was made, so reset
        // it on every setup switch. Harmless on boot (no-op), same as Loot
        // Tracker's resetLootShareState.
        resetGearSetupShareState();
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

      // formatGp plus a ' gp' suffix. Kept separate because formatGp is also
      // used inside text that already ends in "gp" (see pgNpAmount).
      function formatGpLabel(n) {
        return formatGp(n) + ' gp';
      }

      // Ticks an element's text to a new target over 0.5s instead of popping.
      // Works because pgCoinsAmount/pgCostAmount are persistent elements (see
      // static markup), not rebuilt per poll. Keyed per element (WeakMap) so a
      // running tween is cancelled rather than racing a new one over the same
      // textContent.
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

        // First set, or already at the target: show it outright.
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
        // Snapshot the version before the request; if a direct action applied a
        // newer response meanwhile (PG.stateVersion moved), drop this stale one.
        var versionAtStart = PG.stateVersion;
        const data = await apiCall('/api/gear-setups');
        if (!data) return;
        if (PG.stateVersion !== versionAtStart) return;
        PG.stateVersion++;
        PG.data = data;
        if (!PG.activeSetupId || !data.gearSetups.some(function (s) { return s.id === PG.activeSetupId; })) {
          // On first load or if the active setup vanished, prefer the stored id
          // (see setActiveSetupId), else the first setup.
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

      // Top-level render

      function render() {
        renderIconRow();
        renderContent();
      }

      function renderIconRow() {
        var row = document.getElementById('setupIconRow');
        // Null on pages that hide .pg-header (see render_purchase_goals_share);
        // same guard as Loot Tracker's lootShareIconBtn listener.
        if (!row) return;
        if (!PG.data) { row.innerHTML = ''; return; }
        row.innerHTML = PG.data.gearSetups.map(function (s) {
          var active = s.id === PG.activeSetupId ? ' active' : '';
          if (s.icon && s.icon.icon) {
            return '<button class="tracker-icon-btn' + active + '" data-setup-id="' + esc(s.id) + '" draggable="true" type="button" data-tooltip="' + esc(s.name) + '">' +
              '<img src="' + esc(s.icon.icon) + '" alt="" /></button>';
          }
          var label = esc((s.icon && s.icon.itemName) || s.name || '?').slice(0, 3);
          return '<button class="tracker-icon-btn' + active + '" data-setup-id="' + esc(s.id) + '" draggable="true" type="button" data-tooltip="' + esc(s.name) + '">' +
            '<span class="tracker-icon-fallback">' + label + '</span></button>';
        }).join('');
        row.querySelectorAll('[data-setup-id]').forEach(function (btn) {
          btn.addEventListener('click', function () {
            // A completed drag shouldn't also register as a click that switches
            // setup; same dragSuppressClick convention as wireSlotClicks, set on
            // dragend and cleared here.
            if (PG.dragSuppressClick) {
              PG.dragSuppressClick = false;
              return;
            }
            setActiveSetupId(btn.getAttribute('data-setup-id'));
            PG.picker = null;
            PG.iconPicker = false;
            // A pending shift-click group belongs to its setup; carrying it over
            // would apply a search to the wrong sockets.
            PG.multiSelect = [];
            var tappedId = btn.getAttribute('data-setup-id');
            render();
            // render() replaced the button the tap tooltip was waiting on;
            // retarget it (touch only).
            if (window.matchMedia && window.matchMedia('(hover: none)').matches) {
              var fresh = null;
              document.querySelectorAll('#setupIconRow [data-setup-id]').forEach(function (n) {
                if (n.getAttribute('data-setup-id') === tappedId) fresh = n;
              });
              if (fresh) fresh.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
            }
          });
        });
        wireSetupIconDrag(row);
      }

      // Drag-and-drop reordering for the setup icon row: same
      // FLIP-preview/live-DOM-order/full-replacement shape as wireSummaryDrag,
      // over data-setup-id rows, always active. Animates both x and y since
      // .tracker-icon-row wraps.
      function wireSetupIconDrag(row) {
        var draggedEl = null;
        var dropped = false;

        function iconKey(btn) {
          return btn.getAttribute('data-setup-id');
        }

        function animateReorder(mutate) {
          var btns = Array.prototype.slice.call(row.querySelectorAll('.tracker-icon-btn'));
          var firstRects = {};
          btns.forEach(function (btn) { firstRects[iconKey(btn)] = btn.getBoundingClientRect(); });

          mutate();

          btns.forEach(function (btn) {
            if (btn === draggedEl) return;
            var first = firstRects[iconKey(btn)];
            var last = btn.getBoundingClientRect();
            var dx = first.left - last.left;
            var dy = first.top - last.top;
            if (!dx && !dy) return;
            btn.style.transition = 'none';
            btn.style.transform = 'translate(' + dx + 'px,' + dy + 'px)';
            btn.getBoundingClientRect();
            btn.style.transition = 'transform 150ms ease';
            btn.style.transform = '';
            btn.addEventListener('transitionend', function handler() {
              btn.style.transition = '';
              btn.removeEventListener('transitionend', handler);
            });
          });
        }

        async function commitDomOrder() {
          var order = Array.prototype.slice.call(row.querySelectorAll('.tracker-icon-btn')).map(function (btn) {
            return btn.getAttribute('data-setup-id');
          });
          const data = await apiCall('/api/gear-setups/order', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order: order }),
          });
          if (data) { PG.stateVersion++; PG.data = data; render(); }
        }

        row.querySelectorAll('.tracker-icon-btn').forEach(function (btn) {
          btn.addEventListener('dragstart', function (e) {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', btn.getAttribute('data-setup-id'));
            draggedEl = btn;
            dropped = false;
            // Sets PG.dragging like wireSummaryDrag so the poll skips mid-drag;
            // otherwise a poll rebuilds the row (including the drag source) and
            // silently cancels the native drag.
            PG.dragging = true;
            btn.classList.add('dragging');
          });
          btn.addEventListener('dragend', function () {
            btn.classList.remove('dragging');
            draggedEl = null;
            PG.dragging = false;
            // A completed drag shouldn't also register as a click; see the click
            // handler above.
            PG.dragSuppressClick = true;
            // A drag ending without a drop leaves the live-preview order
            // unsaved; re-rendering from PG.data restores the real order.
            if (!dropped) renderIconRow();
          });
          btn.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            if (!draggedEl || draggedEl === btn) return;
            var rect = btn.getBoundingClientRect();
            var before = e.clientX < rect.left + rect.width / 2;
            var alreadyBefore = btn.previousElementSibling === draggedEl;
            var alreadyAfter = btn.nextElementSibling === draggedEl;
            if (before ? alreadyBefore : alreadyAfter) return;
            animateReorder(function () {
              row.insertBefore(draggedEl, before ? btn : btn.nextSibling);
            });
          });
          btn.addEventListener('drop', function (e) {
            e.preventDefault();
            dropped = true;
            commitDomOrder();
          });
        });
      }

      // Pins .pg-doll-wrap's width to the gear frame's rendered width. Also runs
      // on window resize: the frame changes shape at the phone breakpoint, and a
      // stale pinned width leaves it stretched. min-content lets it report its
      // natural width first.
      function pinDollWrapWidth() {
        var dollWrapEl = document.querySelector('.pg-doll-wrap');
        var gearFrameEl = document.getElementById('pgGearFrame');
        if (!dollWrapEl || !gearFrameEl) return;
        dollWrapEl.style.width = 'min-content';
        dollWrapEl.style.width = gearFrameEl.offsetWidth + 'px';
      }
      window.addEventListener('resize', pinDollWrapWidth);

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
          emptyEl.textContent = 'No gear setups yet \\u2014 click the button above to create one.';
          return;
        }

        overlayEl.style.display = '';
        bodyEl.style.display = '';
        emptyEl.style.display = 'none';

        updateOverlay(setup);

        // 11 paperdoll slots plus 8 misc slots (see MISC_EQUIPMENT_SLOTS in
        // app/schemas.py), rendered as two grids in one flex column (.gear-doll)
        // so the misc block can be sized independently.
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

        // Pin the column to the gear frame's width (see .pg-doll-wrap in
        // purchase-goals.css); otherwise the slot picker would stretch the row
        // and push the summary column out.
        pinDollWrapWidth();

        wireSlotClicks();
        renderIconPicker();
        renderSlotPicker();
      }

      // Updates the overlay's GP numbers/bar and next-purchase mini bar in place
      // on fixed elements, so tickNumberText and the .progress-fill transition
      // animate instead of flickering.
      function updateOverlay(setup) {
        var pct = Math.max(0, Math.min(100, setup.progressPct));
        tickNumberText(document.getElementById('pgCoinsAmount'), PG.data.coins, formatGpLabel);
        tickNumberText(document.getElementById('pgCostAmount'), setup.totalCost, formatGpLabel);

        var fillEl = document.getElementById('pgOverlayFill');
        fillEl.style.width = pct + '%';
        fillEl.classList.toggle('funded-fill', !!setup.funded);

        var iconImgEl = document.getElementById('pgOverlayIconImg');
        var iconPlaceholderEl = document.getElementById('pgOverlayIconPlaceholder');
        var iconTriggerEl = document.getElementById('pgIconTrigger');
        if (setup.icon && setup.icon.icon) {
          iconImgEl.src = setup.icon.icon;
          iconImgEl.style.display = '';
          iconPlaceholderEl.style.display = 'none';
          iconTriggerEl.setAttribute('data-tooltip', 'Change setup icon');
        } else {
          iconImgEl.style.display = 'none';
          iconPlaceholderEl.style.display = '';
          iconTriggerEl.setAttribute('data-tooltip', 'Add a setup icon');
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
      // Eight planning-only slots (runes, teleports, etc.) in two rows of 4
      // below the paperdoll (.gear-doll-misc). Mirrors MISC_EQUIPMENT_SLOTS in
      // app/schemas.py, as MAIN_EQUIPMENT_SLOTS above mirrors EQUIPMENT_SLOTS.
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

      // Shift-click multi-select: build a group of sockets, search once, apply
      // the item to all of them (see wireSlotClicks and saveSlot). Slots are
      // (slotType, slot); slot is String()ed because DOM attributes are strings.
      function isSlotSelected(slotType, slot) {
        return PG.multiSelect.some(function (s) { return s.slotType === slotType && String(s.slot) === String(slot); });
      }
      function toggleSlotSelected(slotType, slot) {
        var idx = PG.multiSelect.findIndex(function (s) { return s.slotType === slotType && String(s.slot) === String(slot); });
        if (idx >= 0) PG.multiSelect.splice(idx, 1);
        else PG.multiSelect.push({ slotType: slotType, slot: slot });
      }

      // Syncs the shared picker with PG.multiSelect after each shift-click
      // toggle (args: whether the group was empty, and the picker that was
      // open). Closes when the group empties, else opens or retargets it,
      // keeping typed text.
      // If a single-slot picker was already open at the first shift-click of a
      // new group, that slot is folded in (only on that wasEmpty transition, so
      // it can be toggled off later).
      function syncMultiSelectPicker(wasEmpty, priorPicker) {
        if (!PG.multiSelect.length) {
          PG.picker = null;
          return;
        }
        if (wasEmpty && priorPicker && !isSlotSelected(priorPicker.slotType, priorPicker.slot)) {
          PG.multiSelect.unshift({ slotType: priorPicker.slotType, slot: priorPicker.slot });
        }
        if (PG.picker) {
          PG.picker.targets = PG.multiSelect.slice();
        } else {
          var first = PG.multiSelect[0];
          openSlotPicker(first.slotType, first.slot, PG.multiSelect.slice());
        }
        PG.iconPicker = false;
      }

      function slotHtml(resolved, slotType, slot, extraClass) {
        var picking = PG.picker && PG.picker.slotType === slotType && String(PG.picker.slot) === String(slot);
        var selected = isSlotSelected(slotType, slot);
        var cls = slotClasses(resolved) + (extraClass ? ' ' + extraClass : '') + (picking ? ' picking' : '') + (selected ? ' multi-selected' : '');
        // draggable="false": <img> is draggable by default and would steal the
        // drag from the .gear-slot (draggable="true"). Paired with
        // -webkit-user-drag: none in purchase-goals.css for Safari.
        var inner = resolved && resolved.icon
          ? '<img class="gear-slot-icon" src="' + esc(resolved.icon) + '" alt="" draggable="false" />'
          : (resolved ? '<span class="tracker-icon-fallback">' + esc(resolved.itemName || '?').slice(0, 6) + '</span>' : '');
        // Blank slots get no tooltip; filled ones use data-tooltip (site-wide
        // custom tooltip, .myscape-tooltip) rather than title.
        var tooltipAttr = resolved ? ' data-tooltip="' + esc(resolved.itemName) + '"' : '';
        var itemNameAttr = resolved ? ' data-item-name="' + esc(resolved.itemName) + '"' : '';
        // The remove ("x") button exists only on filled slots and shows on hover
        // (.gear-slot-remove). Its own data-tooltip wins over the slot's since
        // the tooltip script matches the closest [data-tooltip].
        var removeBtn = resolved ? '<button class="gear-slot-remove" type="button" data-tooltip="Remove">&times;</button>' : '';
        // Only filled slots are draggable; every slot is still a drop target
        // (see wireSlotClicks).
        var draggableAttr = resolved ? ' draggable="true"' : '';
        return '<div class="' + cls + '" data-slot-type="' + slotType + '" data-slot="' + esc(slot) + '"' + itemNameAttr + draggableAttr + tooltipAttr + '>' +
          inner + removeBtn + '</div>';
      }

      // On touch, only these taps show a tooltip: gear/inventory slots, setup
      // icons and overview icons. Labelled or self-explanatory controls show
      // none. Read by the shared tooltip script in _shell.
      if (!document.body.classList.contains('landing')) {
        window.myscapeTouchTooltipFilter = function (el) {
          return !(el.closest && el.closest(
            '.sort-btn, .icon-menu-btn, .pg-share-icon-btn, .pg-share-link-btn, .pg-import-icon-btn, .gear-slot-remove'
          ));
        };
      }
      document.addEventListener('click', function (e) {
        var armed = document.querySelectorAll('.gear-slot.touch-armed');
        if (!armed.length) return;
        var hit = e.target.closest && e.target.closest('.gear-slot.touch-armed');
        armed.forEach(function (n) { if (n !== hit) n.classList.remove('touch-armed'); });
      });

      // Touch only, Purchase Goals only (not the homepage preview)
      if (!document.body.classList.contains('landing')
          && window.matchMedia && window.matchMedia('(hover: none)').matches) {

        // Keyboard: the picker focuses its search box with preventScroll, so the
        // on-screen keyboard can cover it. Keep a focused text field, plus some
        // of its suggestion list, inside the visual viewport.
        (function () {
          var vv = window.visualViewport;
          var pending = null;
          function isTextField(el) {
            if (!el) return false;
            if (el.tagName === 'TEXTAREA') return true;
            return el.tagName === 'INPUT' && /^(text|search|)$/.test(el.type || '');
          }
          function reveal() {
            var el = document.activeElement;
            if (!isTextField(el)) return;
            var viewTop = vv ? vv.offsetTop : 0;
            var viewBottom = viewTop + (vv ? vv.height : window.innerHeight);
            var r = el.getBoundingClientRect();
            var need = r.bottom + 16;
            var sug = el.parentElement && el.parentElement.querySelector('.suggestions.show');
            if (sug) need = Math.min(sug.getBoundingClientRect().bottom, r.bottom + 170) + 8;
            var dy = need - viewBottom;
            if (dy > 0) {
              // Never push the field itself off the top.
              dy = Math.min(dy, Math.max(0, r.top - viewTop - 8));
              if (dy > 0) window.scrollBy({ top: dy, left: 0, behavior: 'smooth' });
            } else if (r.top < viewTop + 8) {
              window.scrollBy({ top: r.top - viewTop - 8, left: 0, behavior: 'smooth' });
            }
          }
          function schedule(delay) {
            clearTimeout(pending);
            pending = setTimeout(reveal, delay);
          }
          document.addEventListener('focusin', function (e) {
            if (!isTextField(e.target)) return;
            // The keyboard animates in over a few hundred ms.
            schedule(150); setTimeout(reveal, 450); setTimeout(reveal, 800);
          });
          document.addEventListener('input', function (e) {
            if (isTextField(e.target)) schedule(450);
          });
          if (vv) vv.addEventListener('resize', function () {
            if (isTextField(document.activeElement)) schedule(60);
          });
        })();

        // Long-press drag. HTML5 drag-and-drop doesn't start reliably from a
        // finger, so a ~0.35s hold on a draggable setup icon, summary row or
        // filled slot fires the same drag events at the same handlers (with a
        // stand-in dataTransfer) while a ghost follows the finger. Moving before
        // the hold completes is a normal scroll.
        (function () {
          var HOLD_MS = 350, MOVE_TOL = 10, EDGE = 90;
          var st = null;
          var SOURCE_SEL = '#pgBody [draggable="true"], #setupIconRow [draggable="true"]';

          function makeDT() {
            var d = {};
            return {
              effectAllowed: 'none', dropEffect: 'none', types: [],
              setData: function (k, v) { d[k] = String(v); },
              getData: function (k) { return d[k] || ''; },
              clearData: function () { d = {}; },
              setDragImage: function () {}
            };
          }
          function fire(type, target, x, y, dt) {
            var ev = new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window });
            Object.defineProperty(ev, 'dataTransfer', { value: dt });
            return target.dispatchEvent(ev); // false when a handler called preventDefault
          }
          function moveGhost() {
            if (!st || !st.ghost) return;
            st.ghost.style.left = (st.x - st.gx) + 'px';
            st.ghost.style.top = (st.y - st.gy) + 'px';
          }
          function hover() {
            if (!st || !st.active) return;
            var el = document.elementFromPoint(st.x, st.y);
            if (el !== st.over) {
              if (st.over) fire('dragleave', st.over, st.x, st.y, st.dt);
              st.over = el;
              if (el) fire('dragenter', el, st.x, st.y, st.dt);
            }
            if (el) fire('dragover', el, st.x, st.y, st.dt);
          }
          function scrollLoop() {
            if (!st || !st.active) return;
            var dy = 0;
            if (st.y < EDGE) dy = -Math.ceil((EDGE - st.y) / 6);
            else if (st.y > window.innerHeight - EDGE) dy = Math.ceil((st.y - (window.innerHeight - EDGE)) / 6);
            if (dy) { window.scrollBy(0, dy); moveGhost(); hover(); }
            st.raf = requestAnimationFrame(scrollLoop);
          }
          function release(s) {
            if (s.src && s.wasDraggable != null) s.src.setAttribute('draggable', s.wasDraggable);
            PG.dragging = false;
          }
          function begin() {
            if (!st || st.active) return;
            if (!document.contains(st.src)) { st = null; PG.dragging = false; return; }
            st.active = true;
            fire('dragstart', st.src, st.x, st.y, st.dt);
            var r = st.src.getBoundingClientRect();
            var g = st.src.cloneNode(true);
            g.removeAttribute('id');
            g.classList.remove('dragging', 'touch-armed');
            g.style.cssText = 'position:fixed;margin:0;pointer-events:none;z-index:9999;opacity:0.9;' +
              'width:' + r.width + 'px;height:' + r.height + 'px;transform:scale(1.08);' +
              'box-shadow:0 6px 18px rgba(0,0,0,0.5);transition:none;';
            document.body.appendChild(g);
            st.ghost = g; st.gx = st.x0 - r.left; st.gy = st.y0 - r.top;
            moveGhost();
            if (navigator.vibrate) { try { navigator.vibrate(12); } catch (err) {} }
            st.raf = requestAnimationFrame(scrollLoop);
          }
          function finish(doDrop) {
            if (!st) return;
            var s = st; st = null;
            clearTimeout(s.timer);
            release(s);
            if (!s.active) return;
            cancelAnimationFrame(s.raf);
            var el = document.elementFromPoint(s.x, s.y);
            if (doDrop && el) {
              var ok = fire('dragover', el, s.x, s.y, s.dt);
              if (ok === false) fire('drop', el, s.x, s.y, s.dt);
            } else if (s.over) {
              fire('dragleave', s.over, s.x, s.y, s.dt);
            }
            fire('dragend', s.src, s.x, s.y, s.dt);
            PG.dragging = false;
            if (s.ghost && s.ghost.parentNode) s.ghost.parentNode.removeChild(s.ghost);
            // A long press yields no click; clear the swallow-next-click flag
            // dragend sets.
            setTimeout(function () { PG.dragSuppressClick = false; }, 400);
          }

          document.addEventListener('touchstart', function (e) {
            if (st || e.touches.length !== 1) return;
            var src = e.target.closest && e.target.closest(SOURCE_SEL);
            if (!src) return;
            var t = e.touches[0];
            st = { src: src, x0: t.clientX, y0: t.clientY, x: t.clientX, y: t.clientY,
                   active: false, dt: makeDT(), over: null, ghost: null, raf: 0,
                   timer: setTimeout(begin, HOLD_MS) };
            // Hold off the background refresh for the whole gesture; a poll
            // would detach the pressed element.
            PG.dragging = true;
            // Chrome on Android starts its own drag after ~0.5s, cancelling the
            // touch sequence (touchcancel). Turn native dragging off for the
            // length of the touch.
            st.wasDraggable = src.getAttribute('draggable');
            src.setAttribute('draggable', 'false');
          }, { passive: true });
          document.addEventListener('touchmove', function (e) {
            if (!st) return;
            var t = e.touches[0];
            st.x = t.clientX; st.y = t.clientY;
            if (!st.active) {
              if (Math.abs(st.x - st.x0) > MOVE_TOL || Math.abs(st.y - st.y0) > MOVE_TOL) {
                clearTimeout(st.timer); release(st); st = null;
              }
              return;
            }
            e.preventDefault(); // hold page scroll while dragging
            moveGhost();
            hover();
          }, { passive: false });
          document.addEventListener('touchend', function (e) {
            if (st && st.active && e.cancelable) e.preventDefault(); // no synthetic click
            finish(true);
          }, { passive: false });
          document.addEventListener('touchcancel', function () { finish(false); });
          // Suppress the browser's long-press image/link menu and native drag.
          document.addEventListener('contextmenu', function (e) {
            if (st || (e.target.closest && e.target.closest(SOURCE_SEL))) e.preventDefault();
          });
          document.addEventListener('dragstart', function (e) {
            if (e.isTrusted && e.target.closest && e.target.closest(SOURCE_SEL)) e.preventDefault();
          }, true);
        })();
      }

      function wireSlotClicks() {
        document.querySelectorAll('.gear-slot').forEach(function (el) {
          var removeBtn = el.querySelector('.gear-slot-remove');
          if (removeBtn) {
            removeBtn.addEventListener('click', function (e) {
              // Stop bubbling to the slot's click handler, which would also open
              // the item's wiki page.
              e.stopPropagation();
              var slotType = el.getAttribute('data-slot-type');
              var slot = slotType === 'inventory' ? parseInt(el.getAttribute('data-slot'), 10) : el.getAttribute('data-slot');
              removeSlotItem(slotType, slot);
            });
          }
          // Drag-and-drop: move a filled slot onto another slot, or swap if the
          // destination is filled; works between equipment and inventory. Only
          // filled slots are `draggable` (see slotHtml), but every slot needs
          // the dragover/drop listeners.
          if (el.getAttribute('draggable') === 'true') {
            el.addEventListener('dragstart', function (e) {
              var slotType = el.getAttribute('data-slot-type');
              var slot = el.getAttribute('data-slot');
              e.dataTransfer.effectAllowed = 'move';
              // text/plain rather than a custom MIME type so a drop outside the
              // app degrades harmlessly (some browsers refuse to start the drag
              // otherwise).
              e.dataTransfer.setData('text/plain', JSON.stringify({ slotType: slotType, slot: slot }));
              el.classList.add('dragging');
            });
            el.addEventListener('dragend', function () {
              el.classList.remove('dragging');
              document.querySelectorAll('.gear-slot.drag-over').forEach(function (t) {
                t.classList.remove('drag-over');
              });
              // Suppress the click that follows a completed drag (it would open
              // the wiki); cleared after one use.
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
            // Dropped on its own slot: nothing to do.
            if (fromSlotType === toSlotType && String(fromSlot) === String(toSlot)) return;
            moveSlotItem(fromSlotType, fromSlot, toSlotType, toSlot);
          });

          el.addEventListener('click', function (e) {
            if (PG.dragSuppressClick) {
              PG.dragSuppressClick = false;
              return;
            }
            var slotType = el.getAttribute('data-slot-type');
            var slot = slotType === 'inventory' ? parseInt(el.getAttribute('data-slot'), 10) : el.getAttribute('data-slot');

            // Shift-click toggles this slot in the multi-select group (never
            // opens the wiki). syncMultiSelectPicker opens the shared picker on
            // the first add and keeps it updated until the group empties.
            if (e.shiftKey) {
              var pickerWasOpen = !!PG.picker;
              var wasEmpty = PG.multiSelect.length === 0;
              var priorPicker = PG.picker;
              toggleSlotSelected(slotType, slot);
              syncMultiSelectPicker(wasEmpty, priorPicker);
              renderContent();
              // Only focus the search box when going from no picker to open, so
              // growing the group doesn't steal focus or reselect typed text.
              if (PG.picker && !pickerWasOpen) {
                var newInput = document.getElementById('slotSearchInput');
                if (newInput) {
                  newInput.focus({ preventScroll: true });
                  newInput.select();
                }
                scrollPickerIntoView();
              }
              return;
            }

            var itemName = el.getAttribute('data-item-name');

            // Touch: a filled slot's first tap arms it (tooltip and remove "x"
            // appear, since there is no hover); a second tap opens the wiki.
            // Tapping elsewhere disarms it (document listener below).
            if (itemName && window.matchMedia && window.matchMedia('(hover: none)').matches
                && !document.body.classList.contains('landing') && !el.classList.contains('touch-armed')) {
              document.querySelectorAll('.gear-slot.touch-armed').forEach(function (n) { n.classList.remove('touch-armed'); });
              el.classList.add('touch-armed');
              return;
            }

            // A plain click (no shift) abandons any pending multi-select group
            // and its picker, and acts on just this slot.
            var hadSelection = PG.multiSelect.length > 0;
            if (hadSelection) {
              PG.multiSelect = [];
              PG.picker = null;
            }

            // A filled slot links out to the wiki; removing is the hover "x" and
            // adding only happens on empty slots.
            if (itemName) {
              window.open(itemWikiUrl(itemName), '_blank', 'noopener');
              if (hadSelection) renderContent();
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
                // preventScroll avoids a competing native scroll-into-view;
                // scrollPickerIntoView is the only thing that moves the page.
                // select() readies leftover text in a re-opened picker for
                // replacement.
                input.focus({ preventScroll: true });
                input.select();
              }
              scrollPickerIntoView();
            }
          });
        });
      }

      // Smoothly scrolls the just-opened picker's search box into view. The
      // picker renders below the grid and may sit below the fold. Scrolls a bit
      // past the box (MARGIN_BELOW) to leave room for the suggestions dropdown;
      // no-op if already visible. Called after renderContent() rebuilds
      // #pgSlotPicker.
      function scrollPickerIntoView() {
        var target = document.getElementById('slotSearchInput') || document.getElementById('pgSlotPicker');
        if (!target) return;
        var MARGIN_BELOW = 160;
        var rect = target.getBoundingClientRect();
        var overflowBelow = rect.bottom + MARGIN_BELOW - window.innerHeight;
        if (overflowBelow > 0) {
          window.scrollBy({ top: overflowBelow, left: 0, behavior: 'smooth' });
        } else if (rect.top < 0) {
          // Picker is above the current scroll position: bring it in from the
          // top.
          window.scrollBy({ top: rect.top - 24, left: 0, behavior: 'smooth' });
        }
      }

      // Closes the slot picker (and the selection that opened it) on any click
      // outside the search box or a gear/inventory slot. Scoped to
      // .pg-doll-wrap, which wraps both #pgGearFrame and #pgSlotPicker, so
      // clicking another slot still just switches the picker.
      // Registered on the capture phase (unlike the other outside-click
      // listeners): a slot click rebuilds #pgGearFrame's innerHTML mid-dispatch,
      // so a bubbling listener would see a detached e.target that
      // .pg-doll-wrap.contains() can't find and wrongly treat the click as
      // outside.
      document.addEventListener('click', function (e) {
        if (!PG.picker) return;
        var wrap = document.querySelector('.pg-doll-wrap');
        if (wrap && !wrap.contains(e.target)) {
          PG.picker = null;
          PG.multiSelect = [];
          renderContent();
        }
      }, true);

      // Still to Purchase: sort mode buttons + drag-to-reorder

      // One button per metric (GP, A-Z) that toggles direction, plus a
      // standalone CUSTOM button (the order last dragged into; see
      // wireSummaryDrag). Same convention as Loot Tracker's sort tabs
      // (_sort_tabs/updateSortTabs in app/pages.py). SORT_METRIC_MODE maps
      // metric+direction to the five sort_mode strings the API accepts
      // (STILL_TO_PURCHASE_SORT_MODES in app/schemas.py; it's a real field on
      // the setup, so the vocabulary is fixed); SORT_MODE_METRIC is its reverse.
      var SORT_METRIC_MODE = {
        gp: { asc: 'low_to_high', desc: 'high_to_low' },
        alpha: { asc: 'alphabetical', desc: 'reverse_alphabetical' },
      };
      var SORT_MODE_METRIC = {
        low_to_high: { metric: 'gp', dir: 'asc' },
        high_to_low: { metric: 'gp', dir: 'desc' },
        alphabetical: { metric: 'alpha', dir: 'asc' },
        reverse_alphabetical: { metric: 'alpha', dir: 'desc' },
        custom: { metric: 'custom', dir: null },
      };
      // Direction used when switching to a metric from another (or CUSTOM): gp
      // descending, alpha ascending. Clicking the active metric flips direction
      // instead. Mirrors Loot Tracker's SORT_METRIC_DEFAULT_DIR.
      var SORT_METRIC_DEFAULT_DIR = { gp: 'desc', alpha: 'asc' };

      // Rebuilt every render so the active button tracks
      // setup.stillToPurchaseSort, which can change server-side.
      function renderSortButtons(setup) {
        var el = document.getElementById('pgSortButtons');
        if (!el) return;
        var mode = setup.stillToPurchaseSort || 'low_to_high';
        var active = SORT_MODE_METRIC[mode] || SORT_MODE_METRIC.low_to_high;
        function arrow(metric) {
          if (active.metric !== metric) return '';
          return active.dir === 'asc' ? ' \\u2191' : ' \\u2193';
        }
        el.innerHTML =
          '<button type="button" class="sort-btn' + (active.metric === 'gp' ? ' active' : '') + '" data-sort-metric="gp" data-tooltip="Sort by GP value">GP<span class="sort-btn-arrow">' + arrow('gp') + '</span></button>' +
          '<button type="button" class="sort-btn' + (active.metric === 'alpha' ? ' active' : '') + '" data-sort-metric="alpha" data-tooltip="Sort alphabetically">A-Z<span class="sort-btn-arrow">' + arrow('alpha') + '</span></button>' +
          '<button type="button" class="sort-btn' + (mode === 'custom' ? ' active' : '') + '" data-sort-metric="custom" data-tooltip="Sort by custom order">Custom</button>';
        el.querySelectorAll('.sort-btn').forEach(function (btn) {
          btn.addEventListener('click', function () {
            var metric = btn.getAttribute('data-sort-metric');
            var newMode;
            if (metric === 'custom') {
              newMode = 'custom';
            } else {
              var dir = active.metric === metric ? (active.dir === 'asc' ? 'desc' : 'asc') : (SORT_METRIC_DEFAULT_DIR[metric] || 'desc');
              newMode = SORT_METRIC_MODE[metric][dir];
            }
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

      // True if any gear (including misc) or inventory slot holds an item; used
      // by renderSummaryList to choose its empty-state message.
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

      // Only the list and empty message; the next-purchase mini bar above is a
      // fixed element updated in place by updateOverlay().
      function renderSummaryList(setup) {
        var emptyEl = document.getElementById('pgSummaryEmpty');
        var listEl = document.getElementById('pgSummaryList');
        if (!setup.stillToPurchase.length) {
          // An empty list is ambiguous: nothing added yet versus everything
          // already owned. setupHasAnyItems checks the real slots to tell which
          // message to show.
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
        // Rows are draggable only in custom sort mode; other modes re-sort by
        // live cost on the next render.
        var customMode = (setup.stillToPurchaseSort || 'low_to_high') === 'custom';
        listEl.innerHTML = setup.stillToPurchase.map(function (item) {
          var rowCls = 'gear-summary-row' + (item.purchasable ? '' : ' unpurchasable') + (customMode ? ' draggable' : '');
          var costHtml = item.purchasable
            ? '<span class="gear-summary-row-cost">' + formatGpLabel(item.cost) + '</span>'
            : '<span class="gear-summary-row-cost na">n/a</span>';
          var draggableAttr = customMode ? ' draggable="true"' : '';
          var slotAttrs = ' data-slot-type="' + esc(item.slotType) + '" data-slot="' + esc(item.slot) + '"';
          // draggable="false" on the icon, same reason as .gear-slot-icon (see
          // slotHtml).
          return '<div class="' + rowCls + '"' + slotAttrs + draggableAttr + '>' +
            (item.icon ? '<img class="gear-summary-row-icon" src="' + esc(item.icon) + '" alt="" draggable="false" />' : '<span class="gear-summary-row-icon"></span>') +
            '<span class="gear-summary-row-name">' + esc(item.itemName) + '</span>' +
            costHtml +
            '</div>';
        }).join('');
        wireSummaryDrag(customMode);
      }

      // Nudges the CUSTOM sort button (like Mindmaps' glowEditModeButton) when a
      // row is clicked/dragged outside Custom mode, since the gesture does
      // nothing there. Remove-class/reflow/add-class so a repeat attempt
      // restarts the pulse.
      function glowCustomSortButton() {
        var btn = document.querySelector('#pgSortButtons .sort-btn[data-sort-metric="custom"]');
        if (!btn) return;
        btn.classList.remove('glow');
        void btn.offsetWidth;
        btn.classList.add('glow');
      }

      // Drag-and-drop reordering for custom sort mode: same dragstart/dragend
      // shape as wireSlotClicks, but rows live-reorder while dragging
      // (animateReorder). draggedEl/dropped are per-call since renderSummaryList
      // rewires everything each render.
      function wireSummaryDrag(customMode) {
        var listEl = document.getElementById('pgSummaryList');
        if (!customMode) {
          // Rows outside Custom mode have no draggable attribute, so only a
          // plain press reaches here. pointerdown (not click) matches
          // glowEditModeButton and fires on drag attempts too.
          listEl.querySelectorAll('.gear-summary-row').forEach(function (el) {
            el.addEventListener('pointerdown', function () { glowCustomSortButton(); });
          });
          return;
        }
        var draggedEl = null;
        var dropped = false;

        function rowKey(row) {
          return row.getAttribute('data-slot-type') + '::' + row.getAttribute('data-slot');
        }

        // FLIP-animates every other row from its position before `mutate` to
        // after, so a live reorder slides instead of snapping. The dragged row
        // is skipped (the browser carries it).
        function animateReorder(mutate) {
          var rows = Array.prototype.slice.call(listEl.querySelectorAll('.gear-summary-row'));
          var firstRects = {};
          rows.forEach(function (row) { firstRects[rowKey(row)] = row.getBoundingClientRect(); });

          mutate();

          rows.forEach(function (row) {
            if (row === draggedEl) return;
            var first = firstRects[rowKey(row)];
            var last = row.getBoundingClientRect();
            var dy = first.top - last.top;
            if (!dy) return;
            row.style.transition = 'none';
            row.style.transform = 'translateY(' + dy + 'px)';
            // Force layout so the translateY paints before the transition is
            // re-enabled; otherwise both writes coalesce and the row snaps.
            row.getBoundingClientRect();
            row.style.transition = 'transform 150ms ease';
            row.style.transform = '';
            row.addEventListener('transitionend', function handler() {
              row.style.transition = '';
              row.removeEventListener('transitionend', handler);
            });
          });
        }

        // The live preview already leaves the DOM in the order to save; read the
        // rows back.
        async function commitDomOrder() {
          var order = Array.prototype.slice.call(listEl.querySelectorAll('.gear-summary-row')).map(function (row) {
            var slotType = row.getAttribute('data-slot-type');
            var slot = row.getAttribute('data-slot');
            return { slot_type: slotType, slot: slotType === 'inventory' ? parseInt(slot, 10) : slot };
          });
          const data = await apiCall('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/still-to-purchase-order', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order: order }),
          });
          // Unlike setStillToPurchaseSort, the CUSTOM order is frozen into a
          // share snapshot (customOrder in build_purchase_goal_share_snapshot);
          // see resetGearSetupShareState.
          if (data) { PG.stateVersion++; PG.data = data; resetGearSetupShareState(); render(); }
        }

        document.querySelectorAll('#pgSummaryList .gear-summary-row').forEach(function (el) {
          el.addEventListener('dragstart', function (e) {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', JSON.stringify({
              slotType: el.getAttribute('data-slot-type'),
              slot: el.getAttribute('data-slot'),
            }));
            draggedEl = el;
            dropped = false;
            PG.dragging = true;
            el.classList.add('dragging');
          });
          el.addEventListener('dragend', function () {
            el.classList.remove('dragging');
            draggedEl = null;
            PG.dragging = false;
            // A drag ending without a drop leaves an unsaved live-preview order;
            // re-rendering from setup.stillToPurchase restores it.
            if (!dropped) {
              var setup = activeSetup();
              if (setup) renderSummaryList(setup);
            }
          });
          el.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            if (!draggedEl || draggedEl === el) return;
            var rect = el.getBoundingClientRect();
            var before = e.clientY < rect.top + rect.height / 2;
            var alreadyBefore = el.previousElementSibling === draggedEl;
            var alreadyAfter = el.nextElementSibling === draggedEl;
            if (before ? alreadyBefore : alreadyAfter) return;
            animateReorder(function () {
              listEl.insertBefore(draggedEl, before ? el : el.nextSibling);
            });
          });
          el.addEventListener('drop', function (e) {
            e.preventDefault();
            dropped = true;
            commitDomOrder();
          });
        });
      }

      // Setup icon picker

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
          // Icon change on the active setup; see resetGearSetupShareState.
          if (data) { PG.stateVersion++; PG.data = data; PG.iconPicker = false; resetGearSetupShareState(); render(); }
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
            if (data) { PG.stateVersion++; PG.data = data; PG.iconPicker = false; resetGearSetupShareState(); render(); }
          });
        });
      }

      // Gear/inventory slot picker

      // targets defaults to just this slot; pass the multi-select group (see
      // wireSlotClicks) to apply a pick to several sockets.
      function openSlotPicker(slotType, slot, targets) {
        PG.picker = {
          slotType: slotType,
          slot: slot,
          query: '',
          targets: (targets && targets.length) ? targets : [{ slotType: slotType, slot: slot }],
        };
      }

      function renderSlotPicker() {
        var el = document.getElementById('pgSlotPicker');
        if (!el) return;
        var p = PG.picker;
        if (!p) { el.innerHTML = ''; return; }

        // Just the search box; clicking a suggestion saves immediately (see
        // renderSlotSuggestions). Search covers live GE matches,
        // item-combination recipes and every named item (see search_items in
        // app/purchase_goals.py); combination items are expanded into parts
        // server-side (expand_recipe_components in app/recipes.py).
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
          // Combination items (e.g. "Neitiznot faceguard") have no GE listing or
          // data-item-id but are normal click-to-select suggestions; the server
          // prices them from their components (app/recipes.py).
          var idAttr = r.id != null ? ' data-item-id="' + r.id + '"' : '';
          return '<div class="suggestion" data-item-name="' + esc(r.name) + '"' + idAttr + '>' +
            (r.icon ? '<img src="' + esc(r.icon) + '" alt="" />' : '') + '<span>' + esc(r.name) + '</span></div>';
        }).join('');

        // No match (typo, or not in the game): a plain non-interactive message.
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

      // Applies `item` to every target in the picker's group (one slot unless
      // opened on a multi-select group): one PUT per socket. Sequential because
      // each response is the full recomputed setup, so later saves build on what
      // landed. Stops at the first failure (apiCall already showed the error)
      // but keeps targets that saved.
      async function saveSlot(item) {
        var p = PG.picker;
        var targets = (p.targets && p.targets.length) ? p.targets : [{ slotType: p.slotType, slot: p.slot }];
        var data = null;
        for (var i = 0; i < targets.length; i++) {
          var t = targets[i];
          var result = await apiCall('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/slot', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ slot_type: t.slotType, slot: t.slot, item: item }),
          });
          if (!result) break;
          data = result;
          PG.stateVersion++;
          PG.data = data;
        }
        // Close the picker (and group) only if at least one target saved; a
        // total failure leaves everything intact for retry.
        if (data) {
          PG.picker = null;
          PG.multiSelect = [];
          // Slots changed on the active setup; see resetGearSetupShareState.
          resetGearSetupShareState();
          render();
        }
      }

      // Removes a slot's item from its hover "x". Doesn't use PG.picker (filled
      // slots open none), so the slot is passed explicitly.
      async function removeSlotItem(slotType, slot) {
        const data = await apiCall('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/slot', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ slot_type: slotType, slot: slot, item: null }),
        });
        // Slot cleared; see resetGearSetupShareState.
        if (data) { PG.stateVersion++; PG.data = data; resetGearSetupShareState(); render(); }
      }

      // Drag-and-drop: moves the item from (fromSlotType, fromSlot) to
      // (toSlotType, toSlot) across equipment and inventory. move_gear_slot_item
      // in app/main.py does the move-or-swap against the raw stored item, so
      // combo components travel intact. Closes any open picker, whose target may
      // now be stale.
      async function moveSlotItem(fromSlotType, fromSlot, toSlotType, toSlot) {
        const data = await apiCall('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/slot/move', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            from_slot_type: fromSlotType, from_slot: fromSlot,
            to_slot_type: toSlotType, to_slot: toSlot,
          }),
        });
        // Item moved; see resetGearSetupShareState.
        if (data) { PG.stateVersion++; PG.data = data; PG.picker = null; resetGearSetupShareState(); render(); }
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

      // pgIconTrigger is a fixed element, so it's wired once here rather than on
      // every renderContent().
      document.getElementById('pgIconTrigger').addEventListener('click', function () {
        var opening = !PG.iconPicker;
        PG.iconPicker = opening;
        PG.picker = null;
        PG.multiSelect = [];
        renderIconPicker();
        document.getElementById('pgSlotPicker').innerHTML = '';
        if (opening) {
          // Focus the search box ready to type, like opening a slot picker.
          // select() readies leftover text for replacement.
          var input = document.getElementById('iconSearchInput');
          if (input) {
            input.focus({ preventScroll: true });
            input.select();
          }
        }
      });

      // Setup CRUD (menu + name form)

      // Also resets Delete's armed "Are you sure?" state (same
      // click-away-to-cancel convention as Mindmaps' closeMenu) so closing the
      // menu any other way never leaves a stale confirm.
      function closeSetupMenu() {
        document.getElementById('setupMenu').style.display = 'none';
        document.getElementById('setupMenuBtn').classList.remove('active');
        var deleteBtn = document.getElementById('menuDeleteSetup');
        if (deleteBtn) {
          deleteBtn.classList.remove('tracker-menu-item--confirm');
          deleteBtn.textContent = 'Delete setup';
        }
      }
      document.getElementById('setupMenuBtn').addEventListener('click', function () {
        var menu = document.getElementById('setupMenu');
        if (menu.style.display === 'none') {
          menu.style.display = 'flex';
          document.getElementById('setupMenuBtn').classList.add('active');
        } else { closeSetupMenu(); }
      });
      document.addEventListener('click', function (e) {
        var wrap = document.querySelector('.tracker-menu-wrap');
        if (wrap && !wrap.contains(e.target)) closeSetupMenu();
      });

      document.getElementById('menuNewSetup').addEventListener('click', function () {
        closeSetupMenu();
        openNameForm('new', '');
      });
      // Copies the active setup immediately; the server names it "<name> (copy)"
      // and selects it.
      document.getElementById('menuDuplicateSetup').addEventListener('click', async function () {
        closeSetupMenu();
        var setup = activeSetup();
        if (!setup) { showError('Create a setup first.'); return; }
        const data = await apiCall('/api/gear-setups/' + encodeURIComponent(setup.id) + '/duplicate', { method: 'POST' });
        if (data) {
          PG.stateVersion++;
          PG.data = data;
          if (data.newSetupId) setActiveSetupId(data.newSetupId);
          render();
        }
      });
      document.getElementById('menuRenameSetup').addEventListener('click', function () {
        closeSetupMenu();
        var setup = activeSetup();
        if (!setup) { showError('Create a setup first.'); return; }
        openNameForm('rename', setup.name);
      });
      // First click arms ("Are you sure?", red); a second click deletes. Same
      // two-step confirm as Mindmaps' Delete.
      document.getElementById('menuDeleteSetup').addEventListener('click', async function () {
        var btn = document.getElementById('menuDeleteSetup');
        var setup = activeSetup();
        if (!setup) { closeSetupMenu(); return; }
        if (!btn.classList.contains('tracker-menu-item--confirm')) {
          btn.classList.add('tracker-menu-item--confirm');
          btn.textContent = 'Are you sure?';
          return;
        }
        closeSetupMenu();
        const data = await apiCall('/api/gear-setups/' + encodeURIComponent(setup.id), { method: 'DELETE' });
        if (data) { PG.stateVersion++; PG.data = data; setActiveSetupId(data.gearSetups.length ? data.gearSetups[0].id : null); render(); }
      });

      function openNameForm(mode, initialValue) {
        PG.nameFormMode = mode;
        var form = document.getElementById('pgNameForm');
        var input = document.getElementById('pgNameInput');
        form.style.display = 'flex';
        input.value = initialValue || '';
        input.classList.remove('invalid');
        input.focus();
      }

      // Required-field miss gets a red border only (site-wide); clear it as soon
      // as the person types.
      document.getElementById('pgNameInput').addEventListener('input', function () {
        this.classList.remove('invalid');
      });

      document.getElementById('pgNameCancel').addEventListener('click', function () {
        document.getElementById('pgNameForm').style.display = 'none';
        document.getElementById('pgNameInput').classList.remove('invalid');
        PG.nameFormMode = null;
      });
      document.getElementById('pgNameSave').addEventListener('click', async function () {
        var nameInput = document.getElementById('pgNameInput');
        var name = (nameInput.value || '').trim();
        if (!name) { nameInput.classList.add('invalid'); return; }
        nameInput.classList.remove('invalid');
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
          // Rename; the name is part of what a share link freezes, see
          // resetGearSetupShareState.
          if (data) { PG.stateVersion++; PG.data = data; resetGearSetupShareState(); render(); }
        }
      });

      // Share (export a frozen myscape.io/s/<code> link)

      // Resets the share card (button shown, any generated link hidden). Called
      // from setActiveSetupId on a real setup change and after every edit to the
      // active setup (icon, slot, slot move, custom order, rename), so an old
      // link never silently describes something no longer on screen (same as
      // Loot Tracker's resetLootShareState). Deliberately not called from
      // setStillToPurchaseSort: the share page re-derives every sort except
      // CUSTOM from a frozen list (see build_purchase_goal_share_snapshot in
      // app/purchase_goals.py).
      function resetGearSetupShareState() {
        var genBtn = document.getElementById('pgShareGenerateBtn');
        var linkBtn = document.getElementById('pgShareLinkBtn');
        // Null on the landing preview and the share page, which render no
        // .pg-share-wrap (this script runs unmodified on both; see
        // render_purchase_goals_share).
        if (!genBtn || !linkBtn) return;
        genBtn.hidden = false;
        genBtn.disabled = false;
        genBtn.classList.remove('action-failed');
        linkBtn.hidden = true;
        linkBtn.textContent = '';
        delete linkBtn.dataset.url;
      }

      // Share icon: floating popup under the button (.pg-share-wrap), closed by
      // re-clicking or clicking elsewhere. Mirrors the Storages Viewer's
      // setSettingsMenuOpen (app/pages.py) as setPgShareOpen. Null-guarded like
      // resetGearSetupShareState.
      var pgShareIconBtn = document.getElementById('pgShareIconBtn');
      var pgShareCard = document.getElementById('pgShareCard');
      if (pgShareIconBtn) {
        function setPgShareOpen(open) {
          pgShareCard.hidden = !open;
          pgShareIconBtn.classList.toggle('open', open);
        }
        pgShareIconBtn.addEventListener('click', function () {
          setPgShareOpen(pgShareCard.hidden);
        });
        document.addEventListener('click', function (e) {
          var wrap = document.querySelector('.pg-share-wrap');
          if (wrap && !wrap.contains(e.target)) setPgShareOpen(false);
        });
      }

      // GENERATE SHAREABLE LINK: freezes the currently active setup (read at
      // click time, like Loot Tracker's lootUrl()) into a new SharedContent row.
      // Only this click generates; afterwards pgShareLinkBtn replaces the button
      // until resetGearSetupShareState restores it. See
      // build_purchase_goal_share_snapshot in app/purchase_goals.py.
      var pgShareGenerateBtn = document.getElementById('pgShareGenerateBtn');
      if (pgShareGenerateBtn) {
        pgShareGenerateBtn.addEventListener('click', function () {
          var btn = this;
          if (!PG.activeSetupId) return;
          btn.disabled = true;
          fetch('/api/gear-setups/' + encodeURIComponent(PG.activeSetupId) + '/share', { method: 'POST' })
            .then(function (res) { return res.ok ? res.json() : Promise.reject(); })
            .then(function (data) {
              var linkBtn = document.getElementById('pgShareLinkBtn');
              linkBtn.dataset.url = data.url;
              linkBtn.textContent = data.url;
              btn.hidden = true;
              linkBtn.hidden = false;
            })
            .catch(function () {
              btn.classList.add('action-failed');
              setTimeout(function () { btn.classList.remove('action-failed'); }, 2500);
            })
            .then(function () { btn.disabled = false; });
        });
      }

      // pgShareLinkBtn is the link once generated; click-to-copy then flash
      // "COPIED", like Loot Tracker's lootShareLinkBtn.
      var pgShareLinkBtn = document.getElementById('pgShareLinkBtn');
      if (pgShareLinkBtn) {
        pgShareLinkBtn.addEventListener('click', function () {
          var btn = this;
          var url = btn.dataset.url;
          if (!url) return;
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url);
          } else {
            var temp = document.createElement('textarea');
            temp.value = url;
            temp.style.position = 'fixed';
            temp.style.opacity = '0';
            document.body.appendChild(temp);
            temp.select();
            document.execCommand('copy');
            document.body.removeChild(temp);
          }
          btn.textContent = 'COPIED';
          setTimeout(function () { btn.textContent = url; }, 1200);
        });
      }

      // Boot + poll

      loadState();
      PG.pollTimer = setInterval(function () {
        // Skip the background refresh while an editor is open so a
        // rename/slot-pick isn't yanked away.
        if (PG.picker || PG.iconPicker || PG.nameFormMode || PG.dragging) return;
        loadState();
      }, 5000);
    })();
    """
    return extra_head, body, script


def render_purchase_goals(player: PlayerView) -> str:
    """The Purchase Goals page: _purchase_goals_panel_markup wrapped in the
    logged-in shell, same split as render_loot_tracker.
    """
    extra_head, body, script = _purchase_goals_panel_markup()
    return _shell(
        title="Purchase Goals — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )


def _loot_tracker_panel_markup() -> Tuple[str, str, str]:
    """Builds the Loot Tracker's (extra_head, body, script) triple. Split from
    render_loot_tracker so the landing preview (render_landing_loot_preview)
    can embed the same panel. Doesn't reference `player`: the page is a thin
    shell drawn client-side from one polled JSON payload.
    """
    extra_head = f'<link rel="stylesheet" href="/static/css/loot-tracker.css?v={_LOOT_TRACKER_CSS_VERSION}" />'

    # Feather "eye" outline for the "show hidden" toggle below and the default
    # state of the per-tile hide button (see EYE_GLYPH/EYE_OFF_GLYPH in the
    # script).
    _EYE_GLYPH_SVG = (
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>'
        '<circle cx="12" cy="12" r="3"></circle></svg>'
    )

    def _sort_tabs(tabs_id: str, count_label: str, count_tooltip: str, hide_toggle_id: str, hide_label: str) -> str:
        # One button per metric (GP, count_label, A-Z, TIME). Clicking the
        # active one flips direction; another switches at its
        # SORT_METRIC_DEFAULT_DIR (script below). Same convention as Storages
        # Viewer's sort headers (updateSortHeaders/SORT_DEFAULT_DIR). The arrow
        # is drawn only on the active button via .loot-sort-arrow (cf.
        # .pm-sort-arrow). data-sort-metric is the bare metric; splitSort
        # combines it with "-asc"/"-desc" into the sort strings sortEntries
        # reads.
        return f"""
          <div class="loot-sort-tabs" id="{tabs_id}">
            <button type="button" class="loot-sort-tab" data-sort-metric="gp" data-tooltip="Sort by GP value">GP<span class="loot-sort-arrow"></span></button>
            <button type="button" class="loot-sort-tab" data-sort-metric="count" data-tooltip="{count_tooltip}">{count_label}<span class="loot-sort-arrow"></span></button>
            <button type="button" class="loot-sort-tab" data-sort-metric="alpha" data-tooltip="Sort alphabetically">A-Z<span class="loot-sort-arrow"></span></button>
            <button type="button" class="loot-sort-tab" data-sort-metric="time" data-tooltip="Sort by time">TIME<span class="loot-sort-arrow"></span></button>
            <button type="button" class="loot-hide-toggle" id="{hide_toggle_id}" data-tooltip="Show hidden {hide_label}">{_EYE_GLYPH_SVG}</button>
          </div>
        """

    # Export icon next to the title (same chrome/popup pattern as Purchase
    # Goals' .pg-share-icon-btn). Toggles .lootShareCard as a popup under the
    # button (.loot-share-wrap in loot-tracker.css), closed by re-clicking or
    # clicking elsewhere; the card holds the lazy GENERATE SHAREABLE LINK flow.
    # Feather "upload" glyph, labelled "Export".
    loot_share_icon_btn = (
        ' <span class="loot-share-wrap">'
        '<button type="button" class="loot-share-icon-btn" id="lootShareIconBtn" aria-label="Share the currently displayed loot data" data-tooltip="Share the currently displayed loot data">'
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
        '<polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line>'
        '</svg></button>'
        '<div class="loot-share-card" id="lootShareCard" hidden>'
        '<button type="button" class="loot-share-generate-btn" id="lootShareGenerateBtn">GENERATE SHAREABLE LINK</button>'
        '<button type="button" class="loot-share-link-btn" id="lootShareLinkBtn" data-tooltip="Click to copy" hidden></button>'
        '<p class="loot-share-popup-hint">Links are active for 30 days, but can be<br>deleted sooner on your Account page.</p>'
        '</div>'
        '</span>'
    )

    body = f"""
    <h2 class="page-title">Loot Tracker{loot_share_icon_btn}</h2>

    <div class="auth-error" id="lootError"></div>
    <p class="pg-empty" id="lootEmptyMsg">Loading&hellip;</p>
    <div id="lootBody" style="display:none;">
      <div class="loot-chart-card">
        <div class="loot-chart-header">
          <div class="loot-chart-range" id="lootChartRange">
            <button type="button" class="loot-range-btn" id="lootRangeBtn" data-tooltip="Change date range">
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
                  <input type="text" id="lootRangeStart" value="____-__-__" placeholder="YYYY-MM-DD" inputmode="numeric" autocomplete="off" spellcheck="false" />
                </label>
                <label class="loot-range-custom-field">End
                  <input type="text" id="lootRangeEnd" value="____-__-__" placeholder="YYYY-MM-DD" inputmode="numeric" autocomplete="off" spellcheck="false" />
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
            <div class="loot-search-group">
              <input type="text" class="loot-search" id="lootNpcSearch" placeholder="Search for an NPC" autocomplete="off" />
              <button type="button" class="loot-search-clear" id="lootNpcSearchClear" style="display:none;">Clear</button>
            </div>
            {_sort_tabs("lootNpcSortTabs", "KC", "Sort by kill count", "lootNpcHideToggle", "NPCs")}
          </div>
          <p class="loot-column-empty" id="lootNpcEmpty" style="display:none;">
            No NPCs killed in this range.
          </p>
          <div class="loot-npc-row" id="lootNpcRow"></div>
        </div>
        <div class="loot-panel">
          <div class="loot-panel-controls">
            <div class="loot-search-group">
              <input type="text" class="loot-search" id="lootItemSearch" placeholder="Search for an item" autocomplete="off" />
              <button type="button" class="loot-search-clear" id="lootItemSearchClear" style="display:none;">Clear</button>
            </div>
            {_sort_tabs("lootItemSortTabs", "Qty", "Sort by quantity", "lootItemHideToggle", "items")}
          </div>
          <p class="loot-column-empty" id="lootItemEmpty" style="display:none;">
            No items dropped in this range.
          </p>
          <div class="loot-item-list" id="lootItemList"></div>
        </div>
      </div>
    </div>
    """
    script = """
    (function () {
      var state = {
        // Ordered list, not a Set: selection order feeds the chart title
        // (renderBarChart). A plain click collapses to one entry (or empties
        // it); shift-click toggles one name; see the NPC row click handler.
        selectedNpcs: [], npcSort: 'gp-desc', npcSearch: '', itemSort: 'gp-desc', itemSearch: '',
        rangeKey: '24h', customStart: null, customEnd: null,
        // The clicked bar's {start, end, value, killCount, index}, or null.
        // Mutually exclusive with selectedNpcs (bar click scopes to a time
        // slice, NPC click to an identity). See currentNpcs/currentItems and
        // renderBarChart. `index` is the real identity: loadState overwrites the
        // other fields in place each poll with whichever bucket now sits at that
        // index, so a rolling preset's drift moves the selection along.
        selectedBucket: null,
        // Local UI state, never persisted: each panel's "show hidden" eye toggle
        // (.loot-hide-toggle). Off by default, so hidden NPCs/items are gone,
        // not dimmed (see visibleNpcEntries/visibleItemEntries).
        npcShowHidden: false, itemShowHidden: false,
      };
      var lastData = null;
      // Scoped payload for state.selectedBucket, separate from lastData (which
      // always covers the whole range for the chart): an extra GET
      // /api/players/me/loot for that bucket's [start, end) window
      // (bucketUrl/loadBucketData). Null when nothing is selected or the first
      // fetch is in flight.
      var bucketData = null;
      // Bumped by clearSelectedBucket and every loadBucketData call; guards
      // against a superseded slow fetch clobbering the panels (same as
      // npcRowRenderToken/itemListRenderToken).
      var bucketFetchToken = 0;

      // Feather eye/eye-off for the per-tile hide button in each NPC/item box
      // (renderNpcRow/renderItemList): open eye when clicking would hide,
      // crossed-out when it would unhide. The sort-row toggle (_EYE_GLYPH_SVG in
      // render_loot_tracker) is the open eye only.
      var EYE_GLYPH = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>';
      var EYE_OFF_GLYPH = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19M14.12 14.12a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>';

      // An NPC whose items are all individually hidden (item.hidden, set by
      // build_loot_state in app/loot.py) is treated as hidden for display
      // (filtered out, or dimmed with the toggle on). Its eye button still acts
      // only on the explicit n.hidden (see the #lootNpcRow click handler), so
      // unhiding one item doesn't require hiding the NPC.
      function npcAllItemsHidden(name) {
        var items = lastData && lastData.npcItems && lastData.npcItems[name];
        if (!items || !items.length) return false;
        return items.every(function (it) { return it.hidden; });
      }
      function npcEffectiveHidden(n) {
        return !!n.hidden || npcAllItemsHidden(n.sourceName);
      }

      var RANGE_LABELS = {
        '24h': '24 HOURS', '1w': '1 WEEK', '1m': '1 MONTH',
        '3m': '3 MONTHS', '6m': '6 MONTHS', '1y': '1 YEAR', 'custom': 'CUSTOM',
      };

      // Case-insensitive substring match on the given name field (sourceName for
      // NPCs, itemName for items).
      function filterByName(list, query, nameKey) {
        if (!query) return list;
        var q = query.toLowerCase();
        return list.filter(function (entry) {
          return (entry[nameKey] || '').toLowerCase().indexOf(q) !== -1;
        });
      }

      // Splits a "<metric>-<dir>" sort string (gp-desc, count-asc, ...) into its
      // parts; a bare metric defaults to 'desc'.
      function splitSort(sortStr) {
        var sep = sortStr.indexOf('-');
        return sep === -1
          ? { metric: sortStr, dir: 'desc' }
          : { metric: sortStr.slice(0, sep), dir: sortStr.slice(sep + 1) };
      }

      // Each metric's first-click direction: gp/count/time descending, alpha
      // ascending (cf. Storages Viewer's SORT_DEFAULT_DIR). Clicking the active
      // metric flips direction instead.
      var SORT_METRIC_DEFAULT_DIR = { gp: 'desc', count: 'desc', alpha: 'asc', time: 'desc' };

      // Shared by both panels' sort tabs. sortMode is "<metric>-<dir>": gp sorts
      // by valueKey, count by countKey (killCount for NPCs, quantity for items),
      // alpha by nameKey, time by recentKey (ISO timestamp: lastKillAt /
      // lastDroppedAt). desc is high-to-low / Z-to-A / newest-first. Never
      // mutates the input.
      function sortEntries(list, sortMode, nameKey, valueKey, recentKey, countKey) {
        var out = list.slice();
        var sort = splitSort(sortMode);
        if (sort.metric === 'count') {
          out.sort(function (a, b) { return sort.dir === 'asc' ? (a[countKey] || 0) - (b[countKey] || 0) : (b[countKey] || 0) - (a[countKey] || 0); });
        } else if (sort.metric === 'alpha') {
          out.sort(function (a, b) { return sort.dir === 'asc' ? (a[nameKey] || '').localeCompare(b[nameKey] || '') : (b[nameKey] || '').localeCompare(a[nameKey] || ''); });
        } else if (sort.metric === 'time') {
          out.sort(function (a, b) { var diff = new Date(b[recentKey] || 0) - new Date(a[recentKey] || 0); return sort.dir === 'asc' ? -diff : diff; });
        } else {
          out.sort(function (a, b) { return sort.dir === 'asc' ? (a[valueKey] || 0) - (b[valueKey] || 0) : (b[valueKey] || 0) - (a[valueKey] || 0); });
        }
        return out;
      }

      // Marks the active sort-tab button and draws its arrow, within one
      // .loot-sort-tabs container (shared markup, see _sort_tabs). activeSort is
      // the "<metric>-<dir>" string; same arrow convention as Storages Viewer's
      // updateSortHeaders.
      function updateSortTabs(containerId, activeSort) {
        var container = document.getElementById(containerId);
        var active = splitSort(activeSort);
        var btns = container.querySelectorAll('.loot-sort-tab');
        for (var i = 0; i < btns.length; i++) {
          var btn = btns[i];
          var isActive = btn.getAttribute('data-sort-metric') === active.metric;
          btn.classList.toggle('active', isActive);
          var arrow = btn.querySelector('.loot-sort-arrow');
          if (arrow) arrow.textContent = isActive ? (active.dir === 'asc' ? ' \\u2191' : ' \\u2193') : '';
        }
      }

      // Sums per-bucket gp across selected NPCs' npcBucketValues (see
      // build_loot_state in app/loot.py) into one array; null unless 2+ are
      // selected.
      function mergedNpcBucketValues(npcBucketValues, selectedNpcs, numBuckets) {
        var merged = new Array(numBuckets).fill(0);
        selectedNpcs.forEach(function (name) {
          var values = npcBucketValues[name];
          if (!values) return;
          for (var i = 0; i < numBuckets; i++) merged[i] += values[i] || 0;
        });
        return merged;
      }

      // Sums quantity/value per item (keyed like _add_item_totals server-side:
      // itemId, else itemName) across selected NPCs' npcItems. Keeps the latest
      // lastDroppedAt; icon and hidden flag are identical across occurrences.
      function mergedNpcItems(npcItems, selectedNpcs) {
        var byKey = {};
        var order = [];
        selectedNpcs.forEach(function (name) {
          var items = npcItems[name] || [];
          items.forEach(function (it) {
            var key = it.itemId != null ? it.itemId : it.itemName;
            var totals = byKey[key];
            if (!totals) {
              totals = { itemId: it.itemId, itemName: it.itemName, icon: it.icon, quantity: 0, value: 0, lastDroppedAt: it.lastDroppedAt, hidden: it.hidden };
              byKey[key] = totals;
              order.push(key);
            }
            totals.quantity += it.quantity;
            totals.value += it.value;
            if (new Date(it.lastDroppedAt) > new Date(totals.lastDroppedAt)) totals.lastDroppedAt = it.lastDroppedAt;
          });
        });
        return order.map(function (key) { return byKey[key]; });
      }

      // The NPC row's source list: a clicked bar (state.selectedBucket) wins
      // over lastData.windowNpcs, as in currentItems. All NPC-row callers go
      // through this.
      function currentNpcs() {
        if (state.selectedBucket) return bucketData ? (bucketData.windowNpcs || []) : [];
        return (lastData && lastData.windowNpcs) || [];
      }

      // Item panel source: all NPCs' items when none selected, the one NPC's
      // items when one is, summed items (mergedNpcItems) for 2+ (see
      // windowItems/npcItems in build_loot_state, app/loot.py). A clicked bar
      // takes priority (mutually exclusive with selectedNpcs) and reads
      // bucketData, since only its scoped fetch has that bucket's items. Empty
      // while that fetch is in flight, to avoid flashing the too-broad range
      // items.
      function currentItems() {
        if (state.selectedBucket) return bucketData ? (bucketData.windowItems || []) : [];
        if (!lastData) return [];
        var npcItems = lastData.npcItems || {};
        if (state.selectedNpcs.length === 1) {
          return npcItems[state.selectedNpcs[0]] || [];
        }
        if (state.selectedNpcs.length > 1) {
          return mergedNpcItems(npcItems, state.selectedNpcs);
        }
        return lastData.windowItems || [];
      }

      function fmtGp(n) {
        n = n || 0;
        return n.toLocaleString('en-US');
      }

      // Compact axis label for a gp amount ("12.4k" / "3.1M") to fit the narrow
      // gutter.
      function fmtGpCompact(n) {
        var sign = n < 0 ? '-' : '';
        var abs = Math.abs(n || 0);
        if (abs >= 1e6) return sign + (abs / 1e6).toFixed(abs >= 1e7 ? 0 : 1).replace(/\\.0$/, '') + 'M';
        if (abs >= 1e3) return sign + (abs / 1e3).toFixed(abs >= 1e4 ? 0 : 1).replace(/\\.0$/, '') + 'k';
        return sign + Math.round(abs).toLocaleString('en-US');
      }

      // Rounds a chart max up to a "nice" number (step x power of ten) so
      // gridlines are clean. targetFrac scales the ceiling so the tallest bar
      // lands near that fraction of the axis; dividing by it before rounding,
      // with a finer step table, keeps the tallest bar in a tight band (about
      // 60-80% for a 0.8 target) instead of swinging 50-100%.
      function niceMax(value, targetFrac) {
        targetFrac = targetFrac || 1;
        if (!value || value <= 0) return 100;
        var target = value / targetFrac;
        var magnitude = Math.pow(10, Math.floor(Math.log10(target)));
        var normalized = target / magnitude;
        var steps = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
        var niceNormalized = steps[steps.length - 1];
        for (var i = 0; i < steps.length; i++) {
          if (normalized <= steps[i]) { niceNormalized = steps[i]; break; }
        }
        return niceNormalized * magnitude;
      }

      function fmtClock(isoString) {
        if (!isoString) return '';
        return new Date(isoString).toLocaleTimeString('en-US', { hour: 'numeric' });
      }

      // A bucket's x-axis tick, formatted by the range's granularity (see
      // _bucket_plan in app/loot.py): clock time hourly, short date
      // daily/weekly, month monthly.
      function fmtBucketLabel(granularity, isoString) {
        if (!isoString) return '';
        var d = new Date(isoString);
        if (granularity === 'hourly') return d.toLocaleTimeString('en-US', { hour: 'numeric' });
        if (granularity === 'monthly') return d.toLocaleDateString('en-US', { month: 'short' });
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      }

      // Whether an ISO timestamp is close enough to now to label the last bar
      // "NOW"; a CUSTOM range ending earlier gets its real date/time.
      function isNowish(isoString) {
        if (!isoString) return false;
        return Math.abs(new Date(isoString).getTime() - Date.now()) < 5 * 60 * 1000;
      }

      // 'YYYY-MM-DD' (<input type="date"> value) to a short display date for the
      // range button's CUSTOM label.
      function fmtDateShort(isoDate) {
        if (!isoDate) return '';
        var d = new Date(isoDate + 'T00:00:00');
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      }

      // Local-time zero-padded 'YYYY-MM-DD' for a Date, built by hand
      // (toLocaleDateString has no ISO-basic format).
      function fmtIsoDateLocal(d) {
        var month = String(d.getMonth() + 1);
        if (month.length < 2) month = '0' + month;
        var day = String(d.getDate());
        if (day.length < 2) day = '0' + day;
        return d.getFullYear() + '-' + month + '-' + day;
      }

      // A clicked bar's exact time range for the chart title (see
      // renderBarChart), using the bucket's real start/end (bucket boundaries
      // aren't calendar-aligned; see fmtBucketLabel). Dates use YYYY-MM-DD
      // (fmtIsoDateLocal). The end shown is 1s before the exclusive boundary (as
      // in bucketUrl), so 3:00-3:59 doesn't read as 3:00-4:00 and overlap the
      // next bar. The end date is shown only when it differs from the start's.
      function fmtBucketRangeLabel(startIso, endIso) {
        var start = new Date(startIso);
        var end = new Date(new Date(endIso).getTime() - 1000);
        var timeOpts = { hour: 'numeric', minute: '2-digit' };
        var startDateStr = fmtIsoDateLocal(start);
        var endDateStr = fmtIsoDateLocal(end);
        var startTimeStr = start.toLocaleTimeString('en-US', timeOpts);
        var endTimeStr = end.toLocaleTimeString('en-US', timeOpts);
        if (startDateStr === endDateStr) {
          return startDateStr + ', ' + startTimeStr + ' \\u2013 ' + endTimeStr;
        }
        return startDateStr + ', ' + startTimeStr + ' \\u2013 ' + endDateStr + ', ' + endTimeStr;
      }

      function rangeButtonLabel() {
        if (state.rangeKey === 'custom' && state.customStart && state.customEnd) {
          return fmtDateShort(state.customStart) + ' \\u2013 ' + fmtDateShort(state.customEnd);
        }
        return RANGE_LABELS[state.rangeKey] || RANGE_LABELS['24h'];
      }

      // An item's OSRS Wiki article title is almost always its in-game name
      // (itemName), URL-encoded as for item_icon_url in app/purchase_goals.py;
      // MediaWiki treats %20 like an underscore. A mismatched name lands on
      // Special:Search, which redirects to an exact title match.
      function wikiItemUrl(name) {
        return 'https://oldschool.runescape.wiki/w/Special:Search?search=' + encodeURIComponent(name || '') + '&go=Go';
      }

      function iconImg(src, alt, cls) {
        if (!src) return '';
        // Hidden on a 404 (guessed wiki filename) rather than showing a
        // broken-image icon, like item icons elsewhere.
        return '<img class="' + cls + '" src="' + src + '" alt="" ' +
          'onerror="this.style.display=\\'none\\'" />';
      }

      // Preloads these icon URLs (skipping falsy ones) before the caller swaps
      // in the HTML, so new rows paint decoded instead of popping in. Capped at
      // ICON_PRELOAD_TIMEOUT_MS so a dead wiki image can't stall the swap;
      // iconImg's onerror still hides broken icons.
      var ICON_PRELOAD_TIMEOUT_MS = 400;
      function preloadIcons(urls) {
        var pending = urls.filter(Boolean).map(function (src) {
          return new Promise(function (resolve) {
            var img = new Image();
            img.onload = resolve;
            img.onerror = resolve;
            img.src = src;
          });
        });
        if (!pending.length) return Promise.resolve();
        return Promise.race([
          Promise.all(pending),
          new Promise(function (resolve) { setTimeout(resolve, ICON_PRELOAD_TIMEOUT_MS); }),
        ]);
      }

      function escapeHtml(s) {
        var div = document.createElement('div');
        div.textContent = s == null ? '' : String(s);
        return div.innerHTML;
      }

      // renderNpcRow/renderItemList rebuild their whole list when a hide/unhide
      // changes its entries (see each key comment). With no min-height reserved,
      // the height change shifts the page below. Re-pin the scroll position
      // around the swap, synchronously so no in-between frame paints.
      function swapListHtml(el, html) {
        var scrollY = window.scrollY;
        el.innerHTML = html;
        if (window.scrollY !== scrollY) window.scrollTo(0, scrollY);
      }

      // Used instead of swapListHtml when the set or order of boxes changes (new
      // kill/drop, re-sort, hide/unhide): new boxes are built aside and boxes
      // already on screen (matched by keyFn) are kept and moved, so their <img>
      // isn't re-created, which made icons flicker out. Only new boxes get a new
      // <img> (already fetched by preloadIcons); a kept box whose icon failed
      // gets a fresh <img> to retry.
      function reconcileBoxes(el, html, boxSel, keyFn) {
        var scrollY = window.scrollY;
        var tpl = document.createElement('template');
        tpl.innerHTML = html;
        var oldByKey = {};
        Array.prototype.forEach.call(el.children, function (w) {
          var k = keyFn(w);
          if (k != null) oldByKey[k] = w;
        });
        var frag = document.createDocumentFragment();
        Array.prototype.slice.call(tpl.content.children).forEach(function (nw) {
          var k = keyFn(nw);
          var ow = k != null ? oldByKey[k] : null;
          if (!ow) { frag.appendChild(nw); return; }
          delete oldByKey[k];
          ow.className = nw.className;
          var ob = ow.querySelector(boxSel), nb = nw.querySelector(boxSel);
          if (!ob || !nb) { frag.appendChild(nw); return; }
          Array.prototype.slice.call(ob.attributes).forEach(function (a) { ob.removeAttribute(a.name); });
          Array.prototype.slice.call(nb.attributes).forEach(function (a) { ob.setAttribute(a.name, a.value); });
          var oImg = ob.querySelector('img'), nImg = nb.querySelector('img');
          var kids = Array.prototype.slice.call(nb.childNodes);
          if (oImg && nImg && oImg.getAttribute('src') === nImg.getAttribute('src') &&
              oImg.className === nImg.className && oImg.style.display !== 'none') {
            kids[kids.indexOf(nImg)] = oImg;
          }
          ob.replaceChildren.apply(ob, kids);
          var oe = ow.querySelector('.loot-eye-btn'), ne = nw.querySelector('.loot-eye-btn');
          if (oe && ne) oe.replaceWith(ne);
          frag.appendChild(ow);
        });
        el.replaceChildren(frag);
        if (window.scrollY !== scrollY) window.scrollTo(0, scrollY);
      }

      // Bar chart over the selected range, bucketed by its span (see
      // _bucket_plan in app/loot.py), oldest on the left; ported from the
      // original tool's renderVorkathBarChart. With NPCs selected
      // (state.selectedNpcs), each bar shows a full-height outline at the bucket
      // total plus a solid fill for the selected NPCs' share
      // (mergedNpcBucketValues for 2+). maxValue comes from the totals so the
      // axis stays put. Reuses bar-col elements when the bucket count is
      // unchanged so the CSS height transition animates between polls; a range
      // change rebuilds.
      function renderBarChart(buckets, windowValue, windowKills, npcBucketValues, selectedNpcs, windowNpcs, granularity, rangeEnd, selectedBucket) {
        buckets = buckets || [];
        npcBucketValues = npcBucketValues || {};
        selectedNpcs = selectedNpcs || [];
        granularity = granularity || 'hourly';
        // Three mutually exclusive sources for the header gp/kc and the title,
        // in priority order: clicked bar (selectedBucket), NPC selection
        // (selectedNpcs), whole range. The click handlers clear the other
        // selection, but the priority still matters for the one render that
        // lands before the clearing.
        var headerValue, headerKills, titleText;
        if (selectedBucket) {
          // Reads selectedBucket directly; loadState keeps it fresh each poll
          // (see state's comment), so these are current numbers.
          headerValue = selectedBucket.value;
          headerKills = selectedBucket.killCount;
          titleText = fmtBucketRangeLabel(selectedBucket.start, selectedBucket.end);
        } else {
          // With NPCs selected, header gp/kc show just their totals (from
          // windowNpcs value/killCount) so they match the chart's partial fill.
          var selectedEntries = selectedNpcs.length && windowNpcs
            ? windowNpcs.filter(function (n) { return selectedNpcs.indexOf(n.sourceName) !== -1; })
            : [];
          headerValue = selectedEntries.length ? selectedEntries.reduce(function (sum, n) { return sum + n.value; }, 0) : windowValue;
          headerKills = selectedEntries.length ? selectedEntries.reduce(function (sum, n) { return sum + n.killCount; }, 0) : windowKills;
          // Selected NPC names are uppercased in JS, not via CSS text-transform
          // on .loot-chart-title, which would turn the "ALL NPCs" fallback into
          // "ALL NPCS". Multiple names are joined with a small dot (·) in
          // selection order.
          titleText = 'ALL NPCs';
          if (selectedNpcs.length === 1) {
            titleText = selectedNpcs[0].toUpperCase();
          } else if (selectedNpcs.length > 1) {
            titleText = selectedNpcs.map(function (n) { return n.toUpperCase(); }).join(' \\u00b7 ');
          }
        }
        document.getElementById('lootChartTotal').textContent = fmtGp(headerValue) + ' gp';
        document.getElementById('lootChartKills').textContent = (headerKills || 0).toLocaleString('en-US') + ' kc';
        document.getElementById('lootChartTitle').textContent = titleText;

        // 0.8 target puts the tallest bar around 4/5 up the axis (see niceMax).
        var maxValue = niceMax(Math.max.apply(null, [0].concat(buckets.map(function (b) { return b.value; }))), 0.8);
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

        var selectedValues = selectedNpcs.length === 1
          ? (npcBucketValues[selectedNpcs[0]] || buckets.map(function () { return 0; }))
          : (selectedNpcs.length > 1 ? mergedNpcBucketValues(npcBucketValues, selectedNpcs, buckets.length) : null);

        // The outline always sits at the bucket's total height and never
        // animates. Only the solid fill (see fillPct) changes with selection:
        // with nothing selected the fill covers the outline completely, and
        // selecting an NPC shrinks the fill to reveal it.
        function outlinePct(b) {
          return maxValue > 0 ? Math.max(0, Math.min(100, (b.value / maxValue) * 100)) : 0;
        }
        // A bordered box paints its border even at height:0, so a zero-loot hour
        // would show a sliver. Only enable the border for buckets with something
        // to outline. Not tied to selection: the outline's visibility never
        // changes, only the fill's height.
        function outlineActive(b) {
          return b.value > 0;
        }
        function fillValue(b, i) {
          return selectedNpcs.length ? (selectedValues[i] || 0) : b.value;
        }
        function fillPct(b, i) {
          var v = fillValue(b, i);
          return maxValue > 0 ? Math.max(0, Math.min(100, (v / maxValue) * 100)) : 0;
        }
        // With a selection, a bucket the selection had no part in keeps
        // outlineActive but gets fillPct 0, exposing the whole outline including
        // its bottom border, which reads as a baseline line. Suppress just the
        // bottom edge (loot-bar-outline.no-bottom-border); top/left/right still
        // show that loot existed.
        function outlineHideBottomBorder(b, i) {
          return selectedNpcs.length > 0 && fillPct(b, i) <= 0;
        }

        // Whether column i is the one state.selectedBucket points at. Matched by
        // index, not start/end, since rolling presets drift each poll (see
        // state's comment on selectedBucket).
        function isSelectedCol(i) {
          return !!(selectedBucket && i === selectedBucket.index);
        }

        var barsEl = document.getElementById('lootBarBars');
        var existingCols = barsEl.children;
        if (existingCols.length !== buckets.length) {
          barsEl.innerHTML = buckets.map(function (b, i) {
            return '<div class="loot-bar-col' + (isSelectedCol(i) ? ' selected' : '') + '" data-bucket-index="' + i + '">' +
              '<div class="loot-bar-outline' + (outlineActive(b) ? ' active' : '') + (outlineHideBottomBorder(b, i) ? ' no-bottom-border' : '') + '" style="height:' + outlinePct(b) + '%;"></div>' +
              '<div class="loot-bar-fill' + (fillPct(b, i) > 0 ? ' has-value' : '') + '" style="height:' + fillPct(b, i) + '%;"></div>' +
            '</div>';
          }).join('');
        } else {
          buckets.forEach(function (b, i) {
            var col = existingCols[i];
            col.setAttribute('data-bucket-index', i);
            col.classList.toggle('selected', isSelectedCol(i));
            var outline = col.querySelector('.loot-bar-outline');
            outline.style.height = outlinePct(b) + '%';
            outline.classList.toggle('active', outlineActive(b));
            outline.classList.toggle('no-bottom-border', outlineHideBottomBorder(b, i));
            var fill = col.querySelector('.loot-bar-fill');
            var fp = fillPct(b, i);
            fill.style.height = fp + '%';
            fill.classList.toggle('has-value', fp > 0);
          });
        }

        // Label roughly every 1/7th of the chart width (24 hourly buckets: every
        // 4th), scaling with bucket count. The last bucket gets "NOW" only when
        // the range end is near now (see isNowish).
        var labelStep = Math.max(1, Math.ceil(buckets.length / 7));
        var endIsNow = isNowish(rangeEnd);
        document.getElementById('lootBarXLabels').innerHTML = buckets.map(function (b, i) {
          if (i === buckets.length - 1 && endIsNow) return '<div class="loot-bar-x-label now">NOW</div>';
          var label = (i % labelStep === 0) ? fmtBucketLabel(granularity, b.start) : '';
          return '<div class="loot-bar-x-label">' + label + '</div>';
        }).join('');
      }

      // The clickable "By NPC" row, one box per NPC killed in the range. A plain
      // click selects just that NPC (clicking the sole selected one clears it);
      // shift-click toggles it in/out of the selection, folding in a single
      // plain-selected NPC on first use (see the click handler). Re-renders from
      // the last-polled data with no fetch. One selected NPC gets the gold
      // .active border; 2+ get the blue .multi-selected outline (cf.
      // .gear-slot.multi-selected in purchase-goals.css).
      // The row's HTML (and its <img> icons) is rebuilt only when the set/order
      // changes; otherwise active/title state is patched in place, since
      // rebuilding every poll made icons flicker. The list is filtered by
      // state.npcSearch and sorted by state.npcSort, so the dedup key must
      // include search/sort state too.
      var lastNpcKey = null;
      // Bumped on every rebuild; guards the preloadIcons().then() callback so a
      // superseded rebuild can't clobber the row with stale boxes.
      var npcRowRenderToken = 0;
      function renderNpcRow(npcs) {
        var emptyEl = document.getElementById('lootNpcEmpty');
        var rowEl = document.getElementById('lootNpcRow');
        if (!npcs.length) {
          emptyEl.textContent = 'No NPCs killed in this range.';
          emptyEl.style.display = '';
          rowEl.innerHTML = '';
          lastNpcKey = null;
          npcRowRenderToken++;
          return;
        }

        // Toggle off (default): hidden NPCs, explicit or effective
        // (npcEffectiveHidden), are filtered out. On: all show, hidden ones
        // dimmed (hidden-entry class). See .loot-hide-toggle in
        // loot-tracker.css.
        var visible = state.npcShowHidden ? npcs : npcs.filter(function (n) { return !npcEffectiveHidden(n); });
        if (!visible.length) {
          emptyEl.textContent = npcs.length ? 'Every NPC in this range is hidden.' : 'No NPCs killed in this range.';
          emptyEl.style.display = '';
          rowEl.innerHTML = '';
          lastNpcKey = null;
          npcRowRenderToken++;
          return;
        }

        var sorted = sortEntries(filterByName(visible, state.npcSearch, 'sourceName'), state.npcSort, 'sourceName', 'value', 'lastKillAt', 'killCount');
        if (!sorted.length) {
          emptyEl.textContent = 'No NPCs match your search.';
          emptyEl.style.display = '';
          rowEl.innerHTML = '';
          lastNpcKey = null;
          npcRowRenderToken++;
          return;
        }
        emptyEl.style.display = 'none';

                // Sources whose wiki art is a large "detail" render (reads
                // oversized in the shared 56px NPC icon box) get a dedicated
                // 70%-scale class (.loot-npc-box-icon-* in loot-tracker.css);
                // see _NPC_DISPLAY_OVERRIDES in app/loot.py. Reward caskets are
                // always "Reward casket (<tier>)" (npc_like_name in
                // build_loot_state), so this can't match a real NPC.
        function isCasketNpc(n) {
          return /^Reward casket \\(/i.test(n.sourceName);
        }

        // Exact name; Guardians of the Rift's per-round reward.
        function isIntricatePouch(n) {
          return n.sourceName === 'Intricate pouch';
        }

        // Real NPCs whose bare wiki-name guess is right but reads large.
        // Exact-name matches, so similarly named NPCs ("Giant spider", "Goblin
        // (Dorgesh-Kaan)", see app/npc_names.py) are left alone.
        function isCrawlingHand(n) {
          return /^Crawling Hand$/i.test(n.sourceName);
        }

        function isSpider(n) {
          return /^Spider$/i.test(n.sourceName);
        }

        function isDeathSpawn(n) {
          return /^Death spawn$/i.test(n.sourceName);
        }

        function isGoblin(n) {
          return /^Goblin$/i.test(n.sourceName);
        }

        // Yama's reward container (see _NPC_DISPLAY_OVERRIDES in app/loot.py).
        function isDossier(n) {
          return /^Dossier$/i.test(n.sourceName);
        }

        function isUnsired(n) {
          return /^Unsired$/i.test(n.sourceName);
        }

        // The nine Tarnished NPCs folded into one tile, shown under a bundled
        // battleaxe image.
        function isTarnishedItems(n) {
          return n.sourceName === 'Tarnished items';
        }

        // Every impling type. Matched by a "<word> impling" suffix so new types
        // are picked up automatically.
        function isImpling(n) {
          return /\\bimpling$/i.test(n.sourceName);
        }

        // Seed pack / bird nest: event-type loot sources (see
        // _NPC_DISPLAY_OVERRIDES in app/loot.py), exact names. Only this panel
        // uses the detail render; renderItemList always shows the plain icon.
        function isSeedPackSource(n) {
          return n.sourceName === 'Seed pack';
        }
        function isBirdNestSource(n) {
          return n.sourceName === 'Bird nest';
        }

        // Sailing salvage tiers (8 of them, see _NPC_DISPLAY_OVERRIDES in
        // app/loot.py), matched by a "<word> salvage" suffix; no other source
        // name ends in " salvage".
        function isSalvageSource(n) {
          return /\\bsalvage$/i.test(n.sourceName);
        }


        // hiddenFlags joins the key because hide/unhide can change which entries
        // are dimmed without changing membership or order (same as Storages
        // Viewer's pinnedKey in render_possessions).
        var hiddenFlags = sorted.map(function (n) { return npcEffectiveHidden(n) ? '1' : '0'; }).join('');
        var key = state.npcSearch + '\\u0001' + state.npcSort + '\\u0001' + (state.npcShowHidden ? '1' : '0') + '\\u0001' +
          hiddenFlags + '\\u0001' + sorted.map(function (n) { return n.sourceName; }).join('|');
        if (key !== lastNpcKey) {
          var html = sorted.map(function (n) {
            // A solo selection gets the gold .active border; 2+ get the blue
            // .multi-selected outline (see .loot-npc-box in loot-tracker.css).
            var isSelected = state.selectedNpcs.indexOf(n.sourceName) !== -1;
            var active = isSelected && state.selectedNpcs.length === 1;
            var multiSelected = isSelected && state.selectedNpcs.length > 1;
            var hidden = npcEffectiveHidden(n);
            var explicitHidden = !!n.hidden;
            var eyeTooltip = (explicitHidden ? 'Show ' : 'Hide ') + 'NPC';
            // A <button> can't nest in a <button> (see .loot-npc-box-wrap in
            // loot-tracker.css), so the eye toggle is a sibling of the box
            // inside a non-interactive div. That also means clicking it needs no
            // stopPropagation, as with Storages Viewer's pin button.
            return '<div class="loot-npc-box-wrap' + (hidden ? ' hidden-entry' : '') + '">' +
              '<button type="button" class="loot-npc-box' + (active ? ' active' : '') + (multiSelected ? ' multi-selected' : '') + '" data-npc="' +
                escapeHtml(n.sourceName) + '" data-tooltip="' + escapeHtml(n.sourceName) + '">' +
                iconImg(n.icon, n.sourceName, 'loot-npc-box-icon' + (isCasketNpc(n) ? ' loot-npc-box-icon-casket' : '') + (isIntricatePouch(n) ? ' loot-npc-box-icon-pouch' : '') + (isCrawlingHand(n) ? ' loot-npc-box-icon-crawling-hand' : '') + (isImpling(n) ? ' loot-npc-box-icon-impling' : '') + (isSeedPackSource(n) ? ' loot-npc-box-icon-seedpack' : '') + (isBirdNestSource(n) ? ' loot-npc-box-icon-birdnest' : '') + (isSalvageSource(n) ? ' loot-npc-box-icon-salvage' : '') + (isSpider(n) ? ' loot-npc-box-icon-spider' : '') + (isDeathSpawn(n) ? ' loot-npc-box-icon-death-spawn' : '') + (isGoblin(n) ? ' loot-npc-box-icon-goblin' : '') + (isDossier(n) ? ' loot-npc-box-icon-dossier' : '') + (isUnsired(n) ? ' loot-npc-box-icon-unsired' : '') + (isTarnishedItems(n) ? ' loot-npc-box-icon-tarnished' : '')) +
                '<div class="loot-npc-box-kc">' + n.killCount + ' kc</div>' +
                '<div class="loot-npc-box-value">' + fmtGpCompact(n.value) + ' gp</div>' +
              '</button>' +
              '<button type="button" class="loot-eye-btn" data-hide-name="' + escapeHtml(n.sourceName) +
                '" data-hidden="' + (explicitHidden ? '1' : '0') + '" data-tooltip="' + escapeHtml(eyeTooltip) + '">' +
                (hidden ? EYE_OFF_GLYPH : EYE_GLYPH) +
              '</button>' +
            '</div>';
          }).join('');
          // Preload icons before swapping the HTML in so boxes and pictures
          // appear together.
          var token = ++npcRowRenderToken;
          preloadIcons(sorted.map(function (n) { return n.icon; })).then(function () {
            if (token !== npcRowRenderToken) return;
            lastNpcKey = key;
            reconcileBoxes(rowEl, html, '.loot-npc-box', function (w) {
              var b = w.querySelector('.loot-npc-box');
              return b ? b.getAttribute('data-npc') : null;
            });
          });
          return;
        }

        // Same set/order: keep the boxes and their <img>s, but refresh kc/value
        // text and title in place. Queried by .loot-npc-box-wrap, as in
        // render_possessions' patch branch.
        var wraps = rowEl.querySelectorAll('.loot-npc-box-wrap');
        sorted.forEach(function (n, i) {
          var wrap = wraps[i];
          if (!wrap) return;
          var box = wrap.querySelector('.loot-npc-box');
          var isSelected = state.selectedNpcs.indexOf(n.sourceName) !== -1;
          box.classList.toggle('active', isSelected && state.selectedNpcs.length === 1);
          box.classList.toggle('multi-selected', isSelected && state.selectedNpcs.length > 1);
          box.setAttribute('data-tooltip', n.sourceName);
          var kcEl = box.querySelector('.loot-npc-box-kc');
          if (kcEl) kcEl.textContent = n.killCount + ' kc';
          var valEl = box.querySelector('.loot-npc-box-value');
          if (valEl) valEl.textContent = fmtGpCompact(n.value) + ' gp';
        });
      }

      // Item panel: all NPCs' items, or the selected NPC's (see currentItems),
      // filtered by state.itemSearch and sorted by state.itemSort. Keyed on
      // itemId (falling back to itemName, like _add_item_totals server-side),
      // plus the selected NPC and search/sort state, so switching rebuilds but
      // an unchanged poll reuses the DOM.
      var lastItemKey = null;
      // See npcRowRenderToken.
      var itemListRenderToken = 0;

      // The item panel always uses the plain flat RuneLite-CDN pixel icon
      // (it.icon, from item_icon_url in app/loot.py), never the wiki's detail
      // render. The NPC/source panel is the only place detail renders appear.

      function renderItemList(items) {
        var emptyEl = document.getElementById('lootItemEmpty');
        var listEl = document.getElementById('lootItemList');
        // Same as renderNpcRow's visible filter; an item has no sub-items, so
        // it.hidden alone decides.
        var visible = state.itemShowHidden ? items : items.filter(function (it) { return !it.hidden; });
        if (!visible.length) {
          emptyEl.textContent = items.length ? 'Every item here is hidden.' : 'No items dropped in this range.';
          emptyEl.style.display = '';
          listEl.innerHTML = '';
          lastItemKey = null;
          itemListRenderToken++;
          return;
        }

        var sorted = sortEntries(filterByName(visible, state.itemSearch, 'itemName'), state.itemSort, 'itemName', 'value', 'lastDroppedAt', 'quantity');
        if (!sorted.length) {
          emptyEl.textContent = 'No items match your search.';
          emptyEl.style.display = '';
          listEl.innerHTML = '';
          lastItemKey = null;
          itemListRenderToken++;
          return;
        }
        emptyEl.style.display = 'none';

                // hiddenFlags in the key, as in renderNpcRow.
        var hiddenFlags = sorted.map(function (it) { return it.hidden ? '1' : '0'; }).join('');
        var key = state.selectedNpcs.join('\\u0002') + '\\u0001' + state.itemSearch + '\\u0001' + state.itemSort + '\\u0001' +
          (state.itemShowHidden ? '1' : '0') + '\\u0001' + hiddenFlags + '\\u0001' +
          sorted.map(function (it) { return it.itemId != null ? it.itemId : it.itemName; }).join('|');
        if (key !== lastItemKey) {
          var html = sorted.map(function (it) {
            var eyeTooltip = (it.hidden ? 'Show ' : 'Hide ') + 'item';
            // Sibling wrap as in renderNpcRow: an <a> can't contain a <button>
            // either.
            return '<div class="loot-item-box-wrap' + (it.hidden ? ' hidden-entry' : '') + '">' +
              '<a class="loot-item-box" href="' + wikiItemUrl(it.itemName) + '" target="_blank" rel="noopener" data-tooltip="' + escapeHtml(it.itemName) + '">' +
                iconImg(it.icon, it.itemName, 'loot-item-box-icon') +
                '<div class="loot-item-box-qty">' + '\\u00d7' + fmtGpCompact(it.quantity) + '</div>' +
                '<div class="loot-item-box-value">' + fmtGpCompact(it.value) + ' gp</div>' +
              '</a>' +
              '<button type="button" class="loot-eye-btn" data-hide-item-id="' + (it.itemId != null ? it.itemId : '') +
                '" data-hide-name="' + escapeHtml(it.itemName) + '" data-hidden="' + (it.hidden ? '1' : '0') +
                '" data-tooltip="' + escapeHtml(eyeTooltip) + '">' +
                (it.hidden ? EYE_OFF_GLYPH : EYE_GLYPH) +
              '</button>' +
            '</div>';
          }).join('');
          // Preload before swap, as in renderNpcRow; this branch runs on every
          // NPC selection change, when icons are most likely new.
          var token = ++itemListRenderToken;
          preloadIcons(sorted.map(function (it) { return it.icon; })).then(function () {
            if (token !== itemListRenderToken) return;
            lastItemKey = key;
            reconcileBoxes(listEl, html, '.loot-item-box', function (w) {
              var e = w.querySelector('.loot-eye-btn');
              return e ? e.getAttribute('data-hide-item-id') + '|' + e.getAttribute('data-hide-name') : null;
            });
          });
          return;
        }

        // Same reuse branch as renderNpcRow: keep icons, refresh qty/value text
        // and title.
        var wraps = listEl.querySelectorAll('.loot-item-box-wrap');
        sorted.forEach(function (it, i) {
          var wrap = wraps[i];
          if (!wrap) return;
          var box = wrap.querySelector('.loot-item-box');
          box.setAttribute('data-tooltip', it.itemName);
          var qtyEl = box.querySelector('.loot-item-box-qty');
          if (qtyEl) qtyEl.textContent = '\\u00d7' + fmtGpCompact(it.quantity);
          var valEl = box.querySelector('.loot-item-box-value');
          if (valEl) valEl.textContent = fmtGpCompact(it.value) + ' gp';
        });
      }

      // Hiding/unhiding an NPC or item: call the endpoint
      // (set_npc_hidden/set_item_hidden in app/loot.py), then re-poll with
      // loadState() rather than patching client state, since the server knows
      // how hiding reshapes every total (see build_loot_state).
      async function hideLootNpc(name) {
        await fetch('/api/players/me/loot/hidden-npcs', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name }),
        });
        await loadState();
      }
      async function unhideLootNpc(name) {
        await fetch('/api/players/me/loot/hidden-npcs', {
          method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name }),
        });
        await loadState();
      }
      async function hideLootItem(itemId, itemName) {
        await fetch('/api/players/me/loot/hidden-items', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ item_id: itemId, item_name: itemName }),
        });
        await loadState();
      }
      async function unhideLootItem(itemId, itemName) {
        await fetch('/api/players/me/loot/hidden-items', {
          method: 'DELETE', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ item_id: itemId, item_name: itemName }),
        });
        await loadState();
      }

      function rerenderChart(data) {
        renderBarChart(
          data.buckets || [], data.windowValue || 0, data.windowKills || 0,
          data.npcBucketValues || {}, state.selectedNpcs, data.windowNpcs || [],
          data.granularity, data.rangeEnd, state.selectedBucket
        );
      }

      document.getElementById('lootNpcRow').addEventListener('click', function (e) {
        // The eye button is a sibling of .loot-npc-box, so it never matches
        // .closest('.loot-npc-box') below; checked first anyway to make the
        // priority explicit.
        var eyeBtn = e.target.closest('.loot-eye-btn');
        if (eyeBtn) {
          var eyeName = eyeBtn.getAttribute('data-hide-name');
          if (eyeBtn.getAttribute('data-hidden') === '1') unhideLootNpc(eyeName);
          else hideLootNpc(eyeName);
          return;
        }
        var btn = e.target.closest('.loot-npc-box');
        if (!btn || !lastData) return;
        var name = btn.getAttribute('data-npc');
        // Selecting an NPC scopes by identity, so clear any bar selection first
        // (mirror of the #lootBarBars handler).
        clearSelectedBucket();
        if (e.shiftKey) {
          // Shift-click toggles this NPC in/out without touching the rest; a
          // single plain-selected NPC folds into the new group.
          var idx = state.selectedNpcs.indexOf(name);
          if (idx !== -1) state.selectedNpcs.splice(idx, 1);
          else state.selectedNpcs.push(name);
        } else {
          // A plain click replaces the whole selection with this NPC; clicking
          // the sole selected one clears it.
          var wasSoleSelection = state.selectedNpcs.length === 1 && state.selectedNpcs[0] === name;
          state.selectedNpcs = wasSoleSelection ? [] : [name];
        }
        rerenderChart(lastData);
        renderNpcRow(currentNpcs());
        renderItemList(currentItems());
      });

      document.getElementById('lootBarBars').addEventListener('click', function (e) {
        // Matched against the outline/fill themselves, not the whole
        // .loot-bar-col (full plot height), so only the rendered bar shape hits.
        // A zero-value bucket renders at 0% height and does nothing here; see
        // the outside-click handler below.
        var bar = e.target.closest('.loot-bar-outline, .loot-bar-fill');
        var col = bar && bar.closest('.loot-bar-col');
        if (!col || !lastData) return;
        var idx = parseInt(col.getAttribute('data-bucket-index'), 10);
        var b = (lastData.buckets || [])[idx];
        if (!b) return;
        // Toggle-off is keyed on index, not start/end, since polls drift those
        // (see selectedBucket in state).
        var alreadySelected = state.selectedBucket && state.selectedBucket.index === idx;
        if (alreadySelected) {
          // Clicking the selected bar clears back to the whole range, like
          // re-clicking the sole selected NPC.
          clearSelectedBucket();
        } else {
          // Scoping by time clears any NPC selection first (mirror of the
          // #lootNpcRow handler). value/killCount are captured too so the header
          // is correct before loadBucketData resolves; loadState keeps all four
          // current afterwards.
          state.selectedNpcs = [];
          state.selectedBucket = { start: b.start, end: b.end, value: b.value, killCount: b.killCount, index: idx };
          bucketData = null;
          loadBucketData();
        }
        rerenderChart(lastData);
        renderNpcRow(currentNpcs());
        renderItemList(currentItems());
      });
      // Any click that isn't on a bar clears a bucket selection. Skips clicks on
      // a bar itself, which its own handler owns (including toggle-off).
      document.addEventListener('click', function (e) {
        if (!state.selectedBucket) return;
        if (e.target.closest('.loot-bar-outline, .loot-bar-fill')) return;
        clearSelectedBucket();
        rerenderChart(lastData);
        renderNpcRow(currentNpcs());
        renderItemList(currentItems());
      });
      // Outside-click clear for NPC selections: anything that isn't a
      // .loot-npc-box clears it. Skips clicks on the box, which the #lootNpcRow
      // handler owns.
      document.addEventListener('click', function (e) {
        if (!state.selectedNpcs.length) return;
        if (e.target.closest('.loot-npc-box')) return;
        state.selectedNpcs = [];
        rerenderChart(lastData);
        renderNpcRow(currentNpcs());
        renderItemList(currentItems());
      });

      // CLEAR text button as in Storages Viewer's search box
      // (pmSearchClear/updateSearchClear in render_possessions): shown only
      // while the field has text. Shared styling in
      // .loot-search-group/.loot-search-clear (loot-tracker.css).
      var lootNpcSearchInput = document.getElementById('lootNpcSearch');
      var lootNpcSearchClear = document.getElementById('lootNpcSearchClear');
      function updateNpcSearchClear() {
        lootNpcSearchClear.style.display = lootNpcSearchInput.value ? '' : 'none';
      }
      lootNpcSearchInput.addEventListener('input', function (e) {
        state.npcSearch = e.target.value;
        updateNpcSearchClear();
        if (lastData) renderNpcRow(currentNpcs());
      });
      lootNpcSearchClear.addEventListener('click', function () {
        lootNpcSearchInput.value = '';
        state.npcSearch = '';
        updateNpcSearchClear();
        if (lastData) renderNpcRow(currentNpcs());
        // Keep focus on desktop to keep typing; on touch, blur so the on-screen
        // keyboard goes away.
        if (window.matchMedia('(hover: none)').matches) lootNpcSearchInput.blur();
        else lootNpcSearchInput.focus();
      });
      document.getElementById('lootNpcSortTabs').addEventListener('click', function (e) {
        var toggleBtn = e.target.closest('.loot-hide-toggle');
        if (toggleBtn) {
          state.npcShowHidden = !state.npcShowHidden;
          toggleBtn.classList.toggle('active', state.npcShowHidden);
          toggleBtn.setAttribute('data-tooltip', (state.npcShowHidden ? 'Hide hidden' : 'Show hidden') + ' NPCs');
          if (lastData) renderNpcRow(currentNpcs());
          return;
        }
        var btn = e.target.closest('.loot-sort-tab');
        if (!btn || !lastData) return;
        var metric = btn.getAttribute('data-sort-metric');
        var current = splitSort(state.npcSort);
        var dir = metric === current.metric ? (current.dir === 'asc' ? 'desc' : 'asc') : (SORT_METRIC_DEFAULT_DIR[metric] || 'desc');
        state.npcSort = metric + '-' + dir;
        updateSortTabs('lootNpcSortTabs', state.npcSort);
        renderNpcRow(currentNpcs());
      });
      document.getElementById('lootItemList').addEventListener('click', function (e) {
        var eyeBtn = e.target.closest('.loot-eye-btn');
        if (!eyeBtn) return;
        var itemIdAttr = eyeBtn.getAttribute('data-hide-item-id');
        var itemId = itemIdAttr ? parseInt(itemIdAttr, 10) : null;
        var itemName = eyeBtn.getAttribute('data-hide-name');
        if (eyeBtn.getAttribute('data-hidden') === '1') unhideLootItem(itemId, itemName);
        else hideLootItem(itemId, itemName);
      });
      // Same CLEAR button as the NPC search box.
      // On touch, taps on the date range picker, share icon and link button,
      // sort buttons and eye buttons (show-hidden toggles and per-tile) show no
      // tooltip; all others do. Read by the shared tooltip script in _shell.
      window.myscapeTouchTooltipFilter = function (el) {
        return !(el.closest && el.closest(
          '.loot-share-icon-btn, .loot-share-link-btn, .loot-sort-tab, .loot-hide-toggle, .loot-eye-btn, .loot-range-btn'
        ));
      };
      var lootItemSearchInput = document.getElementById('lootItemSearch');
      var lootItemSearchClear = document.getElementById('lootItemSearchClear');
      function updateItemSearchClear() {
        lootItemSearchClear.style.display = lootItemSearchInput.value ? '' : 'none';
      }
      lootItemSearchInput.addEventListener('input', function (e) {
        state.itemSearch = e.target.value;
        updateItemSearchClear();
        renderItemList(currentItems());
      });
      lootItemSearchClear.addEventListener('click', function () {
        lootItemSearchInput.value = '';
        state.itemSearch = '';
        updateItemSearchClear();
        renderItemList(currentItems());
        // Same as the NPC box's CLEAR.
        if (window.matchMedia('(hover: none)').matches) lootItemSearchInput.blur();
        else lootItemSearchInput.focus();
      });
      document.getElementById('lootItemSortTabs').addEventListener('click', function (e) {
        var toggleBtn = e.target.closest('.loot-hide-toggle');
        if (toggleBtn) {
          state.itemShowHidden = !state.itemShowHidden;
          toggleBtn.classList.toggle('active', state.itemShowHidden);
          toggleBtn.setAttribute('data-tooltip', (state.itemShowHidden ? 'Hide hidden' : 'Show hidden') + ' items');
          renderItemList(currentItems());
          return;
        }
        var btn = e.target.closest('.loot-sort-tab');
        if (!btn) return;
        var metric = btn.getAttribute('data-sort-metric');
        var current = splitSort(state.itemSort);
        var dir = metric === current.metric ? (current.dir === 'asc' ? 'desc' : 'asc') : (SORT_METRIC_DEFAULT_DIR[metric] || 'desc');
        state.itemSort = metric + '-' + dir;
        updateSortTabs('lootItemSortTabs', state.itemSort);
        renderItemList(currentItems());
      });
      updateSortTabs('lootNpcSortTabs', state.npcSort);
      updateSortTabs('lootItemSortTabs', state.itemSort);

      // Range button (presets + CUSTOM date pair)
      // Picking a preset applies and reloads immediately; CUSTOM reveals two
      // date inputs + Apply inline, and nothing changes until Apply with both
      // dates filled.

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
        document.getElementById('lootRangeBtn').classList.remove('active');
      }

      document.getElementById('lootRangeBtn').addEventListener('click', function () {
        var menu = document.getElementById('lootRangeMenu');
        var opening = menu.style.display === 'none';
        menu.style.display = opening ? 'flex' : 'none';
        if (!opening) document.getElementById('lootRangeCustom').style.display = 'none';
        // Gold-highlighted (.loot-range-btn.active) while its dropdown is open.
        // Every close path goes through closeRangeMenu, which un-highlights, so
        // only the open path sets it.
        this.classList.toggle('active', opening);
      });
      document.addEventListener('click', function (e) {
        var wrap = document.getElementById('lootChartRange');
        if (wrap && !wrap.contains(e.target)) closeRangeMenu();
      });
      // Typed 'YYYY-MM-DD' text fields rather than native date pickers. The 'd'
      // slots are masked live (digits only, fixed dashes, unfilled slots shown
      // as "_"), and isValidIsoDate rejects impossible dates like "2024-13-40".
      var DATE_MASK = 'dddd-dd-dd';

      function digitsOnly(s) {
        return (s || '').replace(/\\D/g, '').slice(0, 8);
      }

      function maskValueFromDigits(digits) {
        var out = '', di = 0;
        for (var i = 0; i < DATE_MASK.length; i++) {
          if (DATE_MASK[i] === 'd') {
            out += di < digits.length ? digits[di] : '_';
            di++;
          } else {
            out += DATE_MASK[i];
          }
        }
        return out;
      }

      // Blank means no digits typed: an empty string or the all-underscores
      // skeleton (value="____-__-__" in the HTML).
      function isBlankMaskValue(s) {
        return digitsOnly(s).length === 0;
      }

      function applyDateMask(input) {
        var digits = digitsOnly(input.value);
        input.value = maskValueFromDigits(digits);
        // Cursor lands after the last filled digit, so typing/backspacing edits
        // from the end. Editing a digit mid-date isn't supported; clear and
        // retype.
        var pos = 0, di = 0;
        for (var i = 0; i < DATE_MASK.length; i++) {
          if (DATE_MASK[i] === 'd' && di < digits.length) { pos = i + 1; di++; }
        }
        input.setSelectionRange(pos, pos);
        input.classList.remove('invalid');
      }

      function isValidIsoDate(s) {
        var m = /^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(s || '');
        if (!m) return false;
        var year = parseInt(m[1], 10), month = parseInt(m[2], 10), day = parseInt(m[3], 10);
        if (month < 1 || month > 12) return false;
        var daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
        return day >= 1 && day <= daysInMonth;
      }

      document.getElementById('lootRangeMenu').addEventListener('click', function (e) {
        var opt = e.target.closest('.loot-range-option');
        if (!opt) return;
        var key = opt.getAttribute('data-range');
        if (key === 'custom') {
          var startInput = document.getElementById('lootRangeStart');
          var endInput = document.getElementById('lootRangeEnd');
          if (isBlankMaskValue(startInput.value) || isBlankMaskValue(endInput.value)) {
            var today = new Date();
            var weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
            var toIsoDate = function (d) { return d.toISOString().slice(0, 10); };
            if (isBlankMaskValue(startInput.value)) startInput.value = state.customStart || toIsoDate(weekAgo);
            if (isBlankMaskValue(endInput.value)) endInput.value = state.customEnd || toIsoDate(today);
          }
          startInput.classList.remove('invalid');
          endInput.classList.remove('invalid');
          document.getElementById('lootRangeCustom').style.display = 'flex';
          return;
        }
        state.rangeKey = key;
        state.selectedNpcs = [];
        // A picked bar belongs to the range it was clicked in; switching ranges
        // invalidates it, like an NPC selection.
        clearSelectedBucket();
        // A link generated for the previous range would go stale; see
        // resetLootShareState.
        resetLootShareState();
        closeRangeMenu();
        updateRangeMenuActive();
        loadState();
      });
      function applyCustomRange() {
        var startInput = document.getElementById('lootRangeStart');
        var endInput = document.getElementById('lootRangeEnd');
        var startVal = startInput.value.trim();
        var endVal = endInput.value.trim();
        var startOk = isValidIsoDate(startVal);
        var endOk = isValidIsoDate(endVal);
        startInput.classList.toggle('invalid', !startOk);
        endInput.classList.toggle('invalid', !endOk);
        if (!startOk || !endOk) return;
        state.rangeKey = 'custom';
        state.customStart = startVal;
        state.customEnd = endVal;
        state.selectedNpcs = [];
        clearSelectedBucket();
        resetLootShareState();
        closeRangeMenu();
        updateRangeMenuActive();
        loadState();
      }
      document.getElementById('lootRangeApply').addEventListener('click', applyCustomRange);
      // Enter applies from either field.
      ['lootRangeStart', 'lootRangeEnd'].forEach(function (id) {
        var input = document.getElementById(id);
        input.addEventListener('keydown', function (e) {
          if (e.key === 'Enter') applyCustomRange();
        });
        input.addEventListener('input', function () { applyDateMask(input); });
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

      // A clicked bar's scoped request: same endpoint as lootUrl, with
      // range=custom and the bucket's exact start/end as full ISO timestamps
      // (parse_loot_range_bound in app/loot.py accepts these). bucket.end is the
      // next bucket's start (exclusive, see build_loot_state) but the endpoint's
      // end bound is inclusive, so back off 1ms to avoid double-counting a
      // boundary event.
      function bucketUrl(bucket) {
        var params = new URLSearchParams();
        params.set('range', 'custom');
        params.set('start', bucket.start);
        params.set('end', new Date(new Date(bucket.end).getTime() - 1).toISOString());
        return '/api/players/me/loot?' + params.toString();
      }

      // Fetches bucketData for the selected bucket: once after a bar click, then
      // on every loadState poll (a bucket including "now" can gain kills). Fails
      // quietly rather than showing lootError, since it refines a page that is
      // already showing something.
      async function loadBucketData() {
        if (!state.selectedBucket) return;
        var token = ++bucketFetchToken;
        try {
          var res = await fetch(bucketUrl(state.selectedBucket));
          if (!res.ok || token !== bucketFetchToken) return;
          var data = await res.json();
          // A newer click or a deselect may have landed meanwhile; discard
          // rather than clobber.
          if (token !== bucketFetchToken) return;
          bucketData = data;
          renderNpcRow(currentNpcs());
          renderItemList(currentItems());
        } catch (err) {
          // Quiet; see this function's doc comment.
        }
      }

      // Clears a bucket selection back to the whole range. Shared by the
      // #lootBarBars toggle-off and every scope change (new NPC, new
      // range/CUSTOM), which also reset state.selectedNpcs.
      function clearSelectedBucket() {
        state.selectedBucket = null;
        bucketData = null;
        bucketFetchToken++;
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

          // Drop any selected NPC that aged out of the range (a rolling preset
          // like 24 HOURS) or is now hidden with the NPC panel's toggle off (see
          // npcEffectiveHidden); its tile is gone, so it can't be clicked back.
          // Falls back to "all sources" only if every selected NPC did.
          var rangeNpcs = data.windowNpcs || [];
          state.selectedNpcs = state.selectedNpcs.filter(function (name) {
            var stillPresent = rangeNpcs.filter(function (n) { return n.sourceName === name; })[0];
            return stillPresent && (state.npcShowHidden || !npcEffectiveHidden(stillPresent));
          });

          // A selected bar stays pinned to its index: rolling presets' buckets
          // drift every 10s poll (width is span/count, not calendar-aligned; see
          // _bucket_plan in app/loot.py), so start/end/value/killCount are
          // re-read from whatever bucket now sits at that index. Clears the
          // selection if the index no longer exists (safety net; bucket-count
          // changes already clear it).
          if (state.selectedBucket) {
            var freshBuckets = data.buckets || [];
            var freshBucket = freshBuckets[state.selectedBucket.index];
            if (freshBucket) {
              state.selectedBucket = {
                start: freshBucket.start, end: freshBucket.end,
                value: freshBucket.value, killCount: freshBucket.killCount,
                index: state.selectedBucket.index,
              };
            } else {
              clearSelectedBucket();
            }
          }

          document.getElementById('lootEmptyMsg').style.display = 'none';
          document.getElementById('lootBody').style.display = '';
          rerenderChart(data);
          renderNpcRow(currentNpcs());
          renderItemList(currentItems());
          // Keeps the selected bucket's panel data on the same 10s cadence;
          // quiet on failure (see loadBucketData).
          if (state.selectedBucket) loadBucketData();
        } catch (err) {
          errorEl.textContent = 'Something went wrong loading your loot.';
          errorEl.classList.add('show');
        }
      }

      // Share icon: floating popup under the button (.loot-share-wrap,
      // loot-tracker.css), closed by re-clicking or clicking elsewhere. Mirrors
      // the Storages Viewer's setSettingsMenuOpen (app/pages.py) as
      // setLootShareOpen; nothing is fetched on open. Null-guarded because
      // render_loot_tracker_share strips the icon's <h2> from the body before
      // this script runs (a share visitor isn't the owner).
      var lootShareIconBtn = document.getElementById('lootShareIconBtn');
      var lootShareCard = document.getElementById('lootShareCard');
      if (lootShareIconBtn) {
        function setLootShareOpen(open) {
          lootShareCard.hidden = !open;
          lootShareIconBtn.classList.toggle('open', open);
        }
        lootShareIconBtn.addEventListener('click', function () {
          setLootShareOpen(lootShareCard.hidden);
        });
        document.addEventListener('click', function (e) {
          var wrap = document.querySelector('.loot-share-wrap');
          if (wrap && !wrap.contains(e.target)) setLootShareOpen(false);
        });
      }

      // Resets the share card (GENERATE SHAREABLE LINK shown, any generated link
      // hidden). Called from both range-change paths (preset click and CUSTOM
      // Apply) when state.rangeKey/customStart/customEnd actually change, so an
      // old link never looks current for a new range. Not called when merely
      // toggling the card, polling, or clicking a bucket: only a range change
      // invalidates a link. Regenerating for the same range is still one click
      // away.
      function resetLootShareState() {
        var genBtn = document.getElementById('lootShareGenerateBtn');
        var linkBtn = document.getElementById('lootShareLinkBtn');
        // Both null on the share page and the landing preview, whose wrapper
        // scripts strip .loot-share-wrap (see
        // render_loot_tracker_share/render_landing_loot_preview); this script
        // runs unmodified on both.
        if (!genBtn || !linkBtn) return;
        genBtn.hidden = false;
        genBtn.disabled = false;
        genBtn.classList.remove('action-failed');
        linkBtn.hidden = true;
        linkBtn.textContent = '';
        delete linkBtn.dataset.url;
      }

      // GENERATE SHAREABLE LINK: snapshots the current range
      // (state.rangeKey/customStart/customEnd, as lootUrl() reads). Only this
      // click generates; afterwards lootShareLinkBtn replaces the button until
      // resetLootShareState restores it on a range change. See
      // build_loot_share_snapshot in app/loot.py and SharedContent in
      // app/models.py. Null-guarded: on the share and landing-preview pages the
      // button is stripped, and an unguarded addEventListener would throw and
      // halt the IIFE, leaving loadState()/setInterval unrun and the page stuck
      // on "Loading...".
      var lootShareGenerateBtn = document.getElementById('lootShareGenerateBtn');
      if (lootShareGenerateBtn) {
        lootShareGenerateBtn.addEventListener('click', function () {
          var btn = this;
          btn.disabled = true;
          var body = { range: state.rangeKey };
          if (state.rangeKey === 'custom' && state.customStart && state.customEnd) {
            body.start = state.customStart;
            body.end = state.customEnd;
          }
          fetch('/api/players/me/loot/share', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          })
            .then(function (res) { return res.ok ? res.json() : Promise.reject(); })
            .then(function (data) {
              var linkBtn = document.getElementById('lootShareLinkBtn');
              linkBtn.dataset.url = data.url;
              linkBtn.textContent = data.url;
              btn.hidden = true;
              linkBtn.hidden = false;
            })
            .catch(function () {
              btn.classList.add('action-failed');
              setTimeout(function () { btn.classList.remove('action-failed'); }, 2500);
            })
            .then(function () { btn.disabled = false; });
        });
      }

      // lootShareLinkBtn is the link once generated: click copies data-url
      // (textContent swaps to "COPIED" and back) and flashes "COPIED", like the
      // Account page's .shared-link-code-btn handler (app/pages.py).
      // Null-guarded like lootShareGenerateBtn.
      var lootShareLinkBtn = document.getElementById('lootShareLinkBtn');
      if (lootShareLinkBtn) {
        lootShareLinkBtn.addEventListener('click', function () {
          var btn = this;
          var url = btn.dataset.url;
          if (!url) return;
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url);
          } else {
            var temp = document.createElement('textarea');
            temp.value = url;
            temp.style.position = 'fixed';
            temp.style.opacity = '0';
            document.body.appendChild(temp);
            temp.select();
            document.execCommand('copy');
            document.body.removeChild(temp);
          }
          btn.textContent = 'COPIED';
          setTimeout(function () { btn.textContent = url; }, 1200);
        });
      }

      loadState();
      setInterval(loadState, 10000);
    })();
    """
    return extra_head, body, script


def render_loot_tracker(player: PlayerView) -> str:
    """The Loot Tracker page: a thin server-rendered shell around
    _loot_tracker_panel_markup. Everything is drawn client-side from one
    polled JSON payload (GET /api/players/me/loot, build_loot_state in
    app/loot.py).
    """
    extra_head, body, script = _loot_tracker_panel_markup()
    return _shell(
        title="Loot Tracker — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )


def render_landing_loot_preview() -> Optional[Tuple[str, str, str]]:
    """Interactive Loot Tracker preview for the landing page. Returns
    (extra_head, body, script) for render_landing, or None if
    app/data/landing_loot_demo.json (built by
    scripts/gen_landing_loot_demo.py) is missing/corrupt, so the page falls
    back to the plain marketing image.
    
    Reuses _loot_tracker_panel_markup unmodified; a wrapper script adds:
    1. A `fetch` shim (local `var fetch`) serving every /api/players/me/loot*
    call from the snapshot, so none reach the real endpoint with a visitor's
    cookie. Hide/unhide is tracked in in-memory Sets
    (recomputeAggregates/applyHiddenFlags).
    2. A non-interactive range selector (button listener stripped; dropdown
    kept).
    3. The reused 10s setInterval(loadState) just re-renders the static
    payload.
    """
    demo = _get_landing_loot_demo_data()
    if demo is None:
        return None
    extra_head, body, script = _loot_tracker_panel_markup()

    # Landing-preview hero row prepended to the reused body; its "Loot Tracker"
    # <h2> is hidden via CSS (.landing-loot-preview .page-title).
    hero_markup = """
    <div class="loot-preview-hero">
      <picture class="loot-preview-char loot-preview-char--flipped">
        <source srcset="/static/img/landing-loot-preview-char.webp" type="image/webp">
        <img src="/static/img/landing-loot-preview-char.png" alt="" />
      </picture>
      <div class="loot-preview-tagline-wrap">
        <p class="loot-preview-tagline">
          <span class="loot-preview-tagline-gold">LOOT TRACKING</span> <span class="loot-preview-tagline-white">like you've never experienced it before.</span>
        </p>
      </div>
    </div>
    """
    body = hero_markup + body

    demo_json = json.dumps(demo["full"])
    bucket_states_json = json.dumps(demo["buckets"])
    hide_breakdown_json = json.dumps(demo["hideBreakdown"])
    wrapper_script = f"""
    (function () {{
      var DEMO_STATE = {demo_json};
      var DEMO_BUCKET_STATES = {bucket_states_json};
      // One entry per hour: {{npcName: {{killCount, items: {{itemHideKey:
      // value}}}}}} for the NPCs that killed something that hour (see
      // scripts/gen_landing_loot_demo.py).
      var HIDE_BREAKDOWN = {hide_breakdown_json};
      var ALL_HOUR_INDICES = HIDE_BREAKDOWN.map(function (_, i) {{ return i; }});

      var hiddenNpcs = new Set();
      var hiddenItemKeys = new Set();
      function npcHideKey(name) {{ return (name || '').trim().toLowerCase(); }}
      function itemHideKey(itemId, itemName) {{
        return itemId != null ? ('id:' + itemId) : ('name:' + (itemName || '').trim().toLowerCase());
      }}

      // Recomputes what a hide/unhide changes in a GET response (see
      // build_loot_state in app/loot.py): a hidden NPC's kills leave the
      // buckets/windowValue/windowKills, a hidden item's value leaves every
      // total it fed. `hourIndices` lists the absolute hour(s) (0-23) this
      // payload covers.
      function recomputeAggregates(hourIndices) {{
        var buckets = [];
        var npcBucketValues = {{}};
        var npcTotalValue = {{}};
        hourIndices.forEach(function (hourIdx, i) {{
          var hourData = HIDE_BREAKDOWN[hourIdx] || {{}};
          var bucketValue = 0, bucketKills = 0;
          Object.keys(hourData).forEach(function (npcName) {{
            var entry = hourData[npcName];
            var visibleValue = 0;
            Object.keys(entry.items).forEach(function (key) {{
              if (!hiddenItemKeys.has(key)) visibleValue += entry.items[key];
            }});
            if (!npcBucketValues[npcName]) npcBucketValues[npcName] = hourIndices.map(function () {{ return 0; }});
            npcBucketValues[npcName][i] = visibleValue;
            npcTotalValue[npcName] = (npcTotalValue[npcName] || 0) + visibleValue;
            // An NPC's own tile/bar always shows its real kill count and
            // item-hidden-filtered value, hidden or not; only chart/header
            // totals skip a hidden NPC.
            if (!hiddenNpcs.has(npcHideKey(npcName))) {{
              bucketValue += visibleValue;
              bucketKills += entry.killCount;
            }}
          }});
          buckets.push({{ value: bucketValue, killCount: bucketKills }});
        }});
        var windowValue = buckets.reduce(function (s, b) {{ return s + b.value; }}, 0);
        var windowKills = buckets.reduce(function (s, b) {{ return s + b.killCount; }}, 0);
        return {{ buckets: buckets, npcBucketValues: npcBucketValues, npcTotalValue: npcTotalValue, windowValue: windowValue, windowKills: windowKills }};
      }}

      function applyHiddenFlags(payload, hourIndices) {{
        var out = JSON.parse(JSON.stringify(payload));
        var agg = recomputeAggregates(hourIndices);
        out.buckets.forEach(function (b, i) {{ b.value = agg.buckets[i].value; b.killCount = agg.buckets[i].killCount; }});
        out.windowValue = agg.windowValue;
        out.windowKills = agg.windowKills;
        (out.windowNpcs || []).forEach(function (n) {{
          n.hidden = hiddenNpcs.has(npcHideKey(n.sourceName));
          if (agg.npcTotalValue.hasOwnProperty(n.sourceName)) n.value = agg.npcTotalValue[n.sourceName];
        }});
        if (out.npcBucketValues) {{
          Object.keys(out.npcBucketValues).forEach(function (name) {{
            if (agg.npcBucketValues.hasOwnProperty(name)) out.npcBucketValues[name] = agg.npcBucketValues[name];
          }});
        }}
        (out.windowItems || []).forEach(function (it) {{ it.hidden = hiddenItemKeys.has(itemHideKey(it.itemId, it.itemName)); }});
        if (out.npcItems) {{
          Object.keys(out.npcItems).forEach(function (name) {{
            (out.npcItems[name] || []).forEach(function (it) {{ it.hidden = hiddenItemKeys.has(itemHideKey(it.itemId, it.itemName)); }});
          }});
        }}
        return out;
      }}

      // Shadows the global fetch inside this IIFE only: the reused script calls
      // bare `fetch(...)`, which resolves to this var without any change to that
      // script. Takes `options` to tell POST/DELETE from GET and read who is
      // being hidden.
      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        var qIndex = url.indexOf('?');
        var path = qIndex === -1 ? url : url.slice(0, qIndex);
        var params = new URLSearchParams(qIndex === -1 ? '' : url.slice(qIndex + 1));

        if (path === '/api/players/me/loot' && method === 'GET') {{
          var payload = DEMO_STATE;
          var hourIndices = ALL_HOUR_INDICES;
          if (params.get('range') === 'custom' && params.get('start')) {{
            var startParam = params.get('start');
            for (var i = 0; i < DEMO_STATE.buckets.length; i++) {{
              if (DEMO_STATE.buckets[i].start === startParam) {{ payload = DEMO_BUCKET_STATES[i]; hourIndices = [i]; break; }}
            }}
          }}
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(applyHiddenFlags(payload, hourIndices)); }} }});
        }}
        if (path === '/api/players/me/loot/hidden-npcs') {{
          var npcBody = opts.body ? JSON.parse(opts.body) : {{}};
          var npcKey = npcHideKey(npcBody.name);
          if (method === 'POST') hiddenNpcs.add(npcKey);
          else if (method === 'DELETE') hiddenNpcs.delete(npcKey);
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{}}); }} }});
        }}
        if (path === '/api/players/me/loot/hidden-items') {{
          var itemBody = opts.body ? JSON.parse(opts.body) : {{}};
          var itemKey = itemHideKey(itemBody.item_id, itemBody.item_name);
          if (method === 'POST') hiddenItemKeys.add(itemKey);
          else if (method === 'DELETE') hiddenItemKeys.delete(itemKey);
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{}}); }} }});
        }}
        return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{}}); }} }});
      }};

      {script}

      // Neutralize the range/date selector. This runs after the reused script
      // wired the button's click listener, so replace the node (cloneNode(true)
      // drops listeners). The dropdown stays in the DOM because the reused
      // script calls document.getElementById('lootRangeMenu') on every render
      // and would throw on null.
      var rangeBtn = document.getElementById('lootRangeBtn');
      if (rangeBtn) {{
        rangeBtn.replaceWith(rangeBtn.cloneNode(true));
        document.getElementById('lootRangeBtn').classList.add('loot-range-btn--static');
      }}

      // Remove the export icon and its popup (both nested in .loot-share-wrap):
      // nothing to share from an anonymous demo, and the reused script never
      // looks them up again.
      var shareWrap = document.querySelector('.loot-share-wrap');
      if (shareWrap) shareWrap.remove();

    }})();
    """
    return extra_head, body, wrapper_script


def render_loot_tracker_share(share: "SharedContent", game_account: Optional["GameAccount"], viewer: Optional[PlayerView]) -> str:
    """myscape.io/s/<code> for a Loot Tracker share: a read-only view of the one
    range the owner picked, frozen in share.payload (see POST
    /api/players/me/loot/share in app/main.py, build_loot_share_snapshot in
    app/loot.py). Reuses _loot_tracker_panel_markup like
    render_landing_loot_preview (fetch shim, client-side hide/unhide,
    range-button neutering) with ALL_BUCKET_INDICES/bucketIndices instead of
    the hour indices, since share buckets aren't always hourly (_bucket_plan
    in app/loot.py).
    
    Deliberately not live: a range-queryable endpoint behind a share link
    would expose the account's whole loot history.
    
    The body's "Loot Tracker" <h2> is replaced by a range line plus "Shared by
    <name>". game_account comes from the caller (GET /s/{{code}} in
    app/main.py) and can be None if the row was deleted ("A player"). The
    range line is filled in client-side so the UTC instants show in the
    visitor's timezone; its date helpers are duplicated because the reused
    script keeps its own private.
    """
    extra_head, body, script = _loot_tracker_panel_markup()
    # Strip the reused body's "Loot Tracker" <h2> (and the share button in it);
    # keep what follows the first "</h2>".
    _, _, body = body.partition("</h2>")

    owner_name = (game_account.runescape_name if game_account else None) or "A player"
    range_start_iso = share.payload["full"]["rangeStart"]
    range_end_iso = share.payload["full"]["rangeEnd"]
    range_start = datetime.fromisoformat(range_start_iso)
    range_end = datetime.fromisoformat(range_end_iso)
    # Server-rendered UTC fallback, overwritten by the inline script with the
    # local-time range (shows only if JS is disabled).
    range_label_fallback = (
        f"{range_start.strftime('%b %-d, %Y, %-I:%M %p')} "
        f"– {range_end.strftime('%b %-d, %Y, %-I:%M %p')} UTC"
    )
    # "Shared by <name>" takes over .page-title; the range line keeps .subtitle
    # (spacing: .loot-share-range in loot-tracker.css).
    banner_markup = f"""
    <p class="subtitle loot-share-range"><span id="lootShareRangeLine">{escape(range_label_fallback)}</span></p>
    <h2 class="page-title">Shared by {escape(owner_name)}</h2>
    <script>
    (function () {{
      // Zero-padded 'YYYY-MM-DD' for a JS Date in local time, like
      // fmtIsoDateLocal in the reused script (duplicated, not shared);
      // toLocaleDateString has no ISO format.
      function fmtIsoDateLocal(d) {{
        var month = String(d.getMonth() + 1);
        if (month.length < 2) month = '0' + month;
        var day = String(d.getDate());
        if (day.length < 2) day = '0' + day;
        return d.getFullYear() + '-' + month + '-' + day;
      }}
      var start = new Date("{range_start_iso}");
      var end = new Date("{range_end_iso}");
      var timeOpts = {{ hour: 'numeric', minute: '2-digit' }};
      var startDateStr = fmtIsoDateLocal(start);
      var endDateStr = fmtIsoDateLocal(end);
      var startTimeStr = start.toLocaleTimeString('en-US', timeOpts);
      var endTimeStr = end.toLocaleTimeString('en-US', timeOpts);
      var rangeText = (startDateStr === endDateStr)
        ? (startDateStr + ', ' + startTimeStr + ' \u2013 ' + endTimeStr)
        : (startDateStr + ', ' + startTimeStr + ' \u2013 ' + endDateStr + ', ' + endTimeStr);
      document.getElementById('lootShareRangeLine').textContent = rangeText + ' (LOCAL)';
    }})();
    </script>
    """
    body = banner_markup + body

    full_json = json.dumps(share.payload["full"])
    bucket_states_json = json.dumps(share.payload["buckets"])
    hide_breakdown_json = json.dumps(share.payload["hideBreakdown"])
    wrapper_script = f"""
    (function () {{
      var SHARE_STATE = {full_json};
      var SHARE_BUCKET_STATES = {bucket_states_json};
      // One entry per top-level bucket, index-aligned with SHARE_STATE.buckets
      // (build_loot_share_snapshot in app/loot.py): {{npcName: {{killCount,
      // items: {{itemHideKey: value}}}}}}.
      var HIDE_BREAKDOWN = {hide_breakdown_json};
      var ALL_BUCKET_INDICES = HIDE_BREAKDOWN.map(function (_, i) {{ return i; }});

      var hiddenNpcs = new Set();
      var hiddenItemKeys = new Set();
      function npcHideKey(name) {{ return (name || '').trim().toLowerCase(); }}
      function itemHideKey(itemId, itemName) {{
        return itemId != null ? ('id:' + itemId) : ('name:' + (itemName || '').trim().toLowerCase());
      }}

      // Recomputes the parts of a GET response that a hide/unhide changes (see
      // build_loot_state in app/loot.py); same as recomputeAggregates in
      // render_landing_loot_preview but over `bucketIndices`.
      function recomputeAggregates(bucketIndices) {{
        var buckets = [];
        var npcBucketValues = {{}};
        var npcTotalValue = {{}};
        bucketIndices.forEach(function (bucketIdx, i) {{
          var bucketData = HIDE_BREAKDOWN[bucketIdx] || {{}};
          var bucketValue = 0, bucketKills = 0;
          Object.keys(bucketData).forEach(function (npcName) {{
            var entry = bucketData[npcName];
            var visibleValue = 0;
            Object.keys(entry.items).forEach(function (key) {{
              if (!hiddenItemKeys.has(key)) visibleValue += entry.items[key];
            }});
            if (!npcBucketValues[npcName]) npcBucketValues[npcName] = bucketIndices.map(function () {{ return 0; }});
            npcBucketValues[npcName][i] = visibleValue;
            npcTotalValue[npcName] = (npcTotalValue[npcName] || 0) + visibleValue;
            if (!hiddenNpcs.has(npcHideKey(npcName))) {{
              bucketValue += visibleValue;
              bucketKills += entry.killCount;
            }}
          }});
          buckets.push({{ value: bucketValue, killCount: bucketKills }});
        }});
        var windowValue = buckets.reduce(function (s, b) {{ return s + b.value; }}, 0);
        var windowKills = buckets.reduce(function (s, b) {{ return s + b.killCount; }}, 0);
        return {{ buckets: buckets, npcBucketValues: npcBucketValues, npcTotalValue: npcTotalValue, windowValue: windowValue, windowKills: windowKills }};
      }}

      function applyHiddenFlags(payload, bucketIndices) {{
        var out = JSON.parse(JSON.stringify(payload));
        var agg = recomputeAggregates(bucketIndices);
        // Rewrite out.buckets' value/killCount only when index-aligned with
        // bucketIndices: true for the whole-range fetch, not for a bucket-scoped
        // drill-down (SHARE_BUCKET_STATES[i], bucketIndices = [i]), whose
        // "buckets" are sub-buckets. Nothing reads them while a bucket is
        // selected, and rewriting would index agg.buckets[i] out of bounds,
        // throwing silently inside loadBucketData's catch so the NPC/item panels
        // never load.
        if (out.buckets.length === agg.buckets.length) {{
          out.buckets.forEach(function (b, i) {{ b.value = agg.buckets[i].value; b.killCount = agg.buckets[i].killCount; }});
        }}
        out.windowValue = agg.windowValue;
        out.windowKills = agg.windowKills;
        (out.windowNpcs || []).forEach(function (n) {{
          n.hidden = hiddenNpcs.has(npcHideKey(n.sourceName));
          if (agg.npcTotalValue.hasOwnProperty(n.sourceName)) n.value = agg.npcTotalValue[n.sourceName];
        }});
        if (out.npcBucketValues) {{
          Object.keys(out.npcBucketValues).forEach(function (name) {{
            if (agg.npcBucketValues.hasOwnProperty(name)) out.npcBucketValues[name] = agg.npcBucketValues[name];
          }});
        }}
        (out.windowItems || []).forEach(function (it) {{ it.hidden = hiddenItemKeys.has(itemHideKey(it.itemId, it.itemName)); }});
        if (out.npcItems) {{
          Object.keys(out.npcItems).forEach(function (name) {{
            (out.npcItems[name] || []).forEach(function (it) {{ it.hidden = hiddenItemKeys.has(itemHideKey(it.itemId, it.itemName)); }});
          }});
        }}
        return out;
      }}

      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        var qIndex = url.indexOf('?');
        var path = qIndex === -1 ? url : url.slice(0, qIndex);
        var params = new URLSearchParams(qIndex === -1 ? '' : url.slice(qIndex + 1));

        if (path === '/api/players/me/loot' && method === 'GET') {{
          var payload = SHARE_STATE;
          var bucketIndices = ALL_BUCKET_INDICES;
          if (params.get('range') === 'custom' && params.get('start')) {{
            var startParam = params.get('start');
            for (var i = 0; i < SHARE_STATE.buckets.length; i++) {{
              if (SHARE_STATE.buckets[i].start === startParam) {{ payload = SHARE_BUCKET_STATES[i]; bucketIndices = [i]; break; }}
            }}
          }}
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(applyHiddenFlags(payload, bucketIndices)); }} }});
        }}
        if (path === '/api/players/me/loot/hidden-npcs') {{
          var npcBody = opts.body ? JSON.parse(opts.body) : {{}};
          var npcKey = npcHideKey(npcBody.name);
          if (method === 'POST') hiddenNpcs.add(npcKey);
          else if (method === 'DELETE') hiddenNpcs.delete(npcKey);
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{}}); }} }});
        }}
        if (path === '/api/players/me/loot/hidden-items') {{
          var itemBody = opts.body ? JSON.parse(opts.body) : {{}};
          var itemKey = itemHideKey(itemBody.item_id, itemBody.item_name);
          if (method === 'POST') hiddenItemKeys.add(itemKey);
          else if (method === 'DELETE') hiddenItemKeys.delete(itemKey);
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{}}); }} }});
        }}
        return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{}}); }} }});
      }};

      {script}

      // Neutralize the range/date selector: a share has one range and nothing to
      // switch to (same cloneNode+replaceWith strip as
      // render_landing_loot_preview, dropdown left in place).
      var rangeBtn = document.getElementById('lootRangeBtn');
      if (rangeBtn) {{
        rangeBtn.replaceWith(rangeBtn.cloneNode(true));
        document.getElementById('lootRangeBtn').classList.add('loot-range-btn--static');
        // No "Change date range" tooltip on a shared page.
        document.getElementById('lootRangeBtn').removeAttribute('data-tooltip');
      }}

      // The clone keeps the server-rendered "24 HOURS" label, wrong for a share.
      // Overwrite it with this share's range in the short "Mon D" form
      // (fmtDateShort/rangeButtonLabel), in local dates like the banner,
      // collapsed to one date within a local day.
      var rangeBtnLabelEl = document.getElementById('lootRangeBtnLabel');
      if (rangeBtnLabelEl) {{
        var btnFmtDate = function (d) {{ return d.toLocaleDateString('en-US', {{ month: 'short', day: 'numeric' }}); }};
        var btnStartStr = btnFmtDate(new Date("{range_start_iso}"));
        var btnEndStr = btnFmtDate(new Date("{range_end_iso}"));
        rangeBtnLabelEl.textContent = (btnStartStr === btnEndStr) ? btnStartStr : (btnStartStr + ' \u2013 ' + btnEndStr);
      }}

      // No share-icon removal is needed here: lootShareIconBtn/lootShareCard
      // live inside the "Loot Tracker" <h2> that render_loot_tracker_share
      // already strips.
    }})();
    """

    return _shell(
        title=f"{owner_name}'s shared Loot Tracker — myscape",
        player=viewer,
        body=body,
        extra_head=extra_head,
        extra_script=wrapper_script,
        meta_description=f"{owner_name} shared a snapshot from their Loot Tracker on myscape.",
    )


def render_landing_purchase_preview() -> Optional[Tuple[str, str, str]]:
    """Interactive Purchase Goals preview for the landing page, like
    render_landing_loot_preview: reuses _purchase_goals_panel_markup
    unmodified with a wrapper script. The data is
    app/data/landing_purchase_demo.json, a frozen GET /api/gear-setups
    response trimmed to one "Tombs of Amascut" setup (to replace it, GET
    /api/gear-setups and keep that setup's object). Returns (extra_head, body,
    script), or None if the snapshot can't be read.
    
    Narrower than the real page: one setup (.pg-header hidden in
    purchase-goals.css), no heading, and a read-only gear grid except that a
    filled slot still opens its wiki page. Sorting "Still to Purchase" (incl.
    Custom drag) works on local state (currentSort/customOrder).
    
    1. A `fetch` shim answers GET /api/gear-setups from the snapshot
    (sortStillToPurchase/buildStatePayload), handles the two sort PUTs locally
    and fails anything else, so no call carries a visitor's cookie.
    2. mousedown/dragstart/click in #pgGearFrame are filtered by one
    capturing-phase listener (cloneNode+replaceWith wouldn't survive
    wireSlotClicks rewiring every .gear-slot per render).
    3. #pgIconTrigger is wired once, so it gets the cloneNode+replaceWith
    strip.
    4. The reused 5s setInterval(loadState) just re-renders local state.
    """
    demo = _get_landing_purchase_demo_data()
    if demo is None:
        return None
    extra_head, body, script = _purchase_goals_panel_markup()

    # Hero row, mirrored vs the loot preview (character left, tagline right;
    # .purchase-preview-hero). The "Purchase Goals" <h2> is hidden via CSS.
    hero_markup = """
    <div class="purchase-preview-hero">
      <div class="purchase-preview-tagline-wrap">
        <p class="purchase-preview-tagline">
          <span class="purchase-preview-tagline-gold">PURCHASE GOALS</span> <span class="purchase-preview-tagline-white">to plan your next big spending spree.</span>
        </p>
      </div>
      <picture class="purchase-preview-char purchase-preview-char--flipped">
        <source srcset="/static/img/landing-purchase-preview-char.webp" type="image/webp">
        <img src="/static/img/landing-purchase-preview-char.png" alt="" />
      </picture>
    </div>
    """
    body = hero_markup + body

    demo_json = json.dumps(demo)
    wrapper_script = f"""
    (function () {{
      // The frozen GET /api/gear-setups response for the "Tombs of Amascut"
      // setup: {{coins, pricesError, mappingError, gearSetups: [oneSetup],
      // ownedItems}}. Never mutated; buildStatePayload overlays only the fields
      // sorting changes.
      var DEMO_BASE = {demo_json};
      var SETUP_ID = DEMO_BASE.gearSetups[0].id;

      // Local sort state (gone on refresh), mirroring
      // GearSetup.still_to_purchase_sort_mode/_custom_order.
      var currentSort = DEMO_BASE.gearSetups[0].stillToPurchaseSort || 'low_to_high';
      var customOrder = null; // [{{slotType, slot}}, ...] once a Custom drag lands, else null

      function stillToPurchaseKey(entry) {{ return entry.slotType + '::' + entry.slot; }}

      // Mirrors the sort branch of _still_to_purchase_summary in
      // app/purchase_goals.py: five modes; custom falls back to cost-ascending
      // for items not in customOrder, ranked after those that are. Sorts a copy
      // of the snapshot's already-resolved stillToPurchase list.
      function sortStillToPurchase(items, mode, order) {{
        var out = items.slice();
        if (mode === 'high_to_low') {{
          out.sort(function (a, b) {{ return b.cost - a.cost; }});
        }} else if (mode === 'alphabetical') {{
          out.sort(function (a, b) {{ return a.itemName.toLowerCase() < b.itemName.toLowerCase() ? -1 : a.itemName.toLowerCase() > b.itemName.toLowerCase() ? 1 : 0; }});
        }} else if (mode === 'reverse_alphabetical') {{
          out.sort(function (a, b) {{ return a.itemName.toLowerCase() < b.itemName.toLowerCase() ? 1 : a.itemName.toLowerCase() > b.itemName.toLowerCase() ? -1 : 0; }});
        }} else if (mode === 'custom') {{
          var orderIndex = {{}};
          (order || []).forEach(function (entry, i) {{ orderIndex[stillToPurchaseKey(entry)] = i; }});
          var fallbackIndex = (order || []).length;
          out.sort(function (a, b) {{
            var ia = orderIndex.hasOwnProperty(stillToPurchaseKey(a)) ? orderIndex[stillToPurchaseKey(a)] : fallbackIndex;
            var ib = orderIndex.hasOwnProperty(stillToPurchaseKey(b)) ? orderIndex[stillToPurchaseKey(b)] : fallbackIndex;
            if (ia !== ib) return ia - ib;
            return a.cost - b.cost;
          }});
        }} else {{
          out.sort(function (a, b) {{ return a.cost - b.cost; }});
        }}
        return out;
      }}

      // Rebuilds the GET /api/gear-setups payload from DEMO_BASE plus the
      // current sort: only stillToPurchaseSort, stillToPurchase and nextPurchase
      // (always stillToPurchase[0]) change.
      function buildStatePayload() {{
        var base = DEMO_BASE.gearSetups[0];
        var sorted = sortStillToPurchase(base.stillToPurchase, currentSort, customOrder);
        var nextPurchase = null;
        if (sorted.length) {{
          var top = sorted[0];
          var cost = top.cost;
          nextPurchase = Object.assign({{}}, top, {{
            progressPct: cost <= 0 ? 100 : Math.round(Math.min(DEMO_BASE.coins, cost) / cost * 1000) / 10,
            funded: DEMO_BASE.coins >= cost,
          }});
        }}
        var setup = Object.assign({{}}, base, {{
          stillToPurchaseSort: currentSort,
          stillToPurchase: sorted,
          nextPurchase: nextPurchase,
        }});
        return Object.assign({{}}, DEMO_BASE, {{ gearSetups: [setup] }});
      }}

      // Shadows the global fetch inside this IIFE only; the reused script's bare
      // `fetch(...)` resolves to this var.
      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        var qIndex = url.indexOf('?');
        var path = qIndex === -1 ? url : url.slice(0, qIndex);

        if (path === '/api/gear-setups' && method === 'GET') {{
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(buildStatePayload()); }} }});
        }}
        if (path === '/api/gear-setups/' + SETUP_ID + '/still-to-purchase-sort' && method === 'PUT') {{
          var sortBody = opts.body ? JSON.parse(opts.body) : {{}};
          currentSort = sortBody.sort_mode || currentSort;
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(buildStatePayload()); }} }});
        }}
        if (path === '/api/gear-setups/' + SETUP_ID + '/still-to-purchase-order' && method === 'PUT') {{
          var orderBody = opts.body ? JSON.parse(opts.body) : {{}};
          customOrder = (orderBody.order || []).map(function (e) {{ return {{ slotType: e.slot_type, slot: e.slot }}; }});
          currentSort = 'custom';
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(buildStatePayload()); }} }});
        }}
        return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{ message: 'Not available in this preview.' }}); }} }});
      }};

      {script}

      // Neutralize the setup-icon trigger: wired once on load (unlike the
      // .gear-slot elements rewired every render), so the one-time
      // cloneNode+replaceWith strip works.
      var iconTrigger = document.getElementById('pgIconTrigger');
      if (iconTrigger) {{
        iconTrigger.replaceWith(iconTrigger.cloneNode(true));
        document.getElementById('pgIconTrigger').style.cursor = 'default';
      }}

      // Swallow every mousedown/dragstart inside the gear doll + inventory grid,
      // and every click except a plain click on a FILLED slot's item
      // (wireSlotClicks only turns that into a wiki link). Empty-slot clicks
      // (add-item picker), the hover "x" and shift-click (multi-select) stay
      // blocked. A capturing-phase listener fires before wireSlotClicks' own,
      // and #pgGearFrame survives every render (only its innerHTML is replaced),
      // so one registration covers rebuilt slots. preventDefault stops the
      // native drag; stopImmediatePropagation keeps blocked events from reaching
      // the slot listeners.
      var gearFrame = document.getElementById('pgGearFrame');
      if (gearFrame) {{
        ['mousedown', 'dragstart'].forEach(function (evt) {{
          gearFrame.addEventListener(evt, function (e) {{
            e.stopImmediatePropagation();
            e.preventDefault();
          }}, true);
        }});
        gearFrame.addEventListener('click', function (e) {{
          if (e.shiftKey) {{ e.stopImmediatePropagation(); e.preventDefault(); return; }}
          if (e.target.closest('.gear-slot-remove')) {{ e.stopImmediatePropagation(); e.preventDefault(); return; }}
          var slotEl = e.target.closest('.gear-slot');
          if (!slotEl || !slotEl.classList.contains('filled')) {{ e.stopImmediatePropagation(); e.preventDefault(); return; }}
        }}, true);
      }}

    }})();
    """
    return extra_head, body, wrapper_script


def render_purchase_goals_share(share: "SharedContent", game_account: Optional["GameAccount"], viewer: Optional[PlayerView]) -> str:
    """myscape.io/s/<code> for a Purchase Goals share: a read-only, frozen view
    of one gear setup (see POST /api/gear-setups/{setup_id}/share in
    app/main.py and build_purchase_goal_share_snapshot in
    app/purchase_goals.py).
    
    Reuses _purchase_goals_panel_markup like render_landing_purchase_preview
    (fetch shim, #pgIconTrigger strip, #pgGearFrame neutering) from
    share.payload, with:
    1. currentSort hardcoded to 'low_to_high', so a share always opens on the
    same default; CUSTOM still lands on customOrder.
    2. customOrder seeded from share.payload['customOrder'] rather than null.
    3. A localStorage shadow (as in render_landing_mindmap_preview): /s/<code>
    shares an origin with the real app, so the reused script's
    myscape:purchaseGoals:activeSetupId would otherwise be overwritten.
    
    coins is always 0 and items resolve against EMPTY owned pools, so every
    item is owned: False with cost == fullCost, except those
    _is_always_attainable_item (app/purchase_goals.py) force-owns. So Still to
    Purchase / Next Purchase cover the whole setup (runes, food, potions, ammo
    excepted), and the GP number and progress bar are hidden via CSS
    (.purchase-goal-share #pgCoinsAmount/.overlay-progress) so they never read
    as the owner's live GP. Gear slots lose their ownership border colors
    (.purchase-goal-share .gear-slot.owned/.not-owned/.affordable), which
    describe the visitor's own bank, and the hover "remove" button is hidden.
    
    The "Purchase Goals" <h2> (with its share icon and .pg-share-wrap card) is
    stripped via body.partition; banner_markup adds the setup name and "Shared
    by <name>" styled as .page-title. .pg-header is hidden via CSS.
    game_account comes from the caller (GET /s/{code}) and can be None ("A
    player").
    """
    extra_head, body, script = _purchase_goals_panel_markup()
    # Strip the reused body's "Purchase Goals" <h2> (and the share button in
    # it); keep what follows the first "</h2>".
    _, _, body = body.partition("</h2>")

    owner_name = (game_account.runescape_name if game_account else None) or "A player"
    setup_name = share.payload["gearSetup"]["name"]

    # Download icon next to "Shared by <name>": the share tray icon mirrored
    # into a download arrow. Chosen server-side:
    # - Signed in: a <button> toggling a confirm popup whose SAVE TO MY MYSCAPE
    # button POSTs /api/shares/<code>/import, then opens the player's Purchase
    # Goals page with the import selected at the end of their list
    # (import_gear_setup_from_share_payload in app/purchase_goals.py).
    # - Signed out: a plain <a> to /signup with no JS.
    import_icon_svg = (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
        '<polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line>'
        '</svg>'
    )
    # Signed in: the icon toggles a confirm popup (like
    # pgShareIconBtn/pgShareCard) so a stray click can't import. Signed out: a
    # plain <a> to /signup.
    if viewer is not None:
        import_icon_btn = (
            ' <span class="pg-import-wrap">'
            '<button type="button" class="pg-import-icon-btn" id="pgImportBtn" aria-label="Save to your account" title="Save to your account">'
            f'{import_icon_svg}</button>'
            '<div class="pg-import-card" id="pgImportCard" hidden>'
            '<button type="button" class="pg-import-save-btn" id="pgImportSaveBtn">SAVE TO MY MYSCAPE</button>'
            '<p class="pg-import-popup-hint">Clicking the button above will save a copy<br>of this setup to your Purchase Goals.</p>'
            '</div>'
            '</span>'
        )
    else:
        import_icon_btn = (
            ' <a class="pg-import-icon-btn" href="/signup" aria-label="Sign up to save this" title="Sign up to save this">'
            f'{import_icon_svg}</a>'
        )

    banner_markup = f"""
    <p class="subtitle pg-share-label">{escape(setup_name)}</p>
    <h2 class="page-title">Shared by {escape(owner_name)}{import_icon_btn}</h2>
    """
    body = banner_markup + body
    body = f'<div class="purchase-goal-share">{body}</div>'

    payload_json = json.dumps(share.payload)
    wrapper_script = f"""
    (function () {{
      var PAYLOAD = {payload_json};
      var SETUP_ID = PAYLOAD.gearSetup.id;

      var currentSort = 'low_to_high';
      var customOrder = PAYLOAD.customOrder || null;

      function stillToPurchaseKey(entry) {{ return entry.slotType + '::' + entry.slot; }}

      function sortStillToPurchase(items, mode, order) {{
        var out = items.slice();
        if (mode === 'high_to_low') {{
          out.sort(function (a, b) {{ return b.cost - a.cost; }});
        }} else if (mode === 'alphabetical') {{
          out.sort(function (a, b) {{ return a.itemName.toLowerCase() < b.itemName.toLowerCase() ? -1 : a.itemName.toLowerCase() > b.itemName.toLowerCase() ? 1 : 0; }});
        }} else if (mode === 'reverse_alphabetical') {{
          out.sort(function (a, b) {{ return a.itemName.toLowerCase() < b.itemName.toLowerCase() ? 1 : a.itemName.toLowerCase() > b.itemName.toLowerCase() ? -1 : 0; }});
        }} else if (mode === 'custom') {{
          var orderIndex = {{}};
          (order || []).forEach(function (entry, i) {{ orderIndex[stillToPurchaseKey(entry)] = i; }});
          var fallbackIndex = (order || []).length;
          out.sort(function (a, b) {{
            var ia = orderIndex.hasOwnProperty(stillToPurchaseKey(a)) ? orderIndex[stillToPurchaseKey(a)] : fallbackIndex;
            var ib = orderIndex.hasOwnProperty(stillToPurchaseKey(b)) ? orderIndex[stillToPurchaseKey(b)] : fallbackIndex;
            if (ia !== ib) return ia - ib;
            return a.cost - b.cost;
          }});
        }} else {{
          out.sort(function (a, b) {{ return a.cost - b.cost; }});
        }}
        return out;
      }}

      function buildStatePayload() {{
        var base = PAYLOAD.gearSetup;
        var sorted = sortStillToPurchase(base.stillToPurchase, currentSort, customOrder);
        var nextPurchase = null;
        if (sorted.length) {{
          var top = sorted[0];
          var cost = top.cost;
          nextPurchase = Object.assign({{}}, top, {{
            progressPct: cost <= 0 ? 100 : Math.round(Math.min(PAYLOAD.coins, cost) / cost * 1000) / 10,
            funded: PAYLOAD.coins >= cost,
          }});
        }}
        var setup = Object.assign({{}}, base, {{
          stillToPurchaseSort: currentSort,
          stillToPurchase: sorted,
          nextPurchase: nextPurchase,
        }});
        return {{ coins: PAYLOAD.coins, gearSetups: [setup] }};
      }}

      var localStorage = (function () {{
        var store = {{}};
        return {{
          getItem: function (k) {{ return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; }},
          setItem: function (k, v) {{ store[k] = String(v); }},
          removeItem: function (k) {{ delete store[k]; }},
        }};
      }})();

      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        var qIndex = url.indexOf('?');
        var path = qIndex === -1 ? url : url.slice(0, qIndex);

        if (path === '/api/gear-setups' && method === 'GET') {{
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(buildStatePayload()); }} }});
        }}
        if (path === '/api/gear-setups/' + SETUP_ID + '/still-to-purchase-sort' && method === 'PUT') {{
          var sortBody = opts.body ? JSON.parse(opts.body) : {{}};
          currentSort = sortBody.sort_mode || currentSort;
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(buildStatePayload()); }} }});
        }}
        if (path === '/api/gear-setups/' + SETUP_ID + '/still-to-purchase-order' && method === 'PUT') {{
          var orderBody = opts.body ? JSON.parse(opts.body) : {{}};
          customOrder = (orderBody.order || []).map(function (e) {{ return {{ slotType: e.slot_type, slot: e.slot }}; }});
          currentSort = 'custom';
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(buildStatePayload()); }} }});
        }}
        return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{ message: 'Not available on a shared link.' }}); }} }});
      }};

      {script}

      var iconTrigger = document.getElementById('pgIconTrigger');
      if (iconTrigger) {{
        iconTrigger.replaceWith(iconTrigger.cloneNode(true));
        document.getElementById('pgIconTrigger').style.cursor = 'default';
      }}

      var gearFrame = document.getElementById('pgGearFrame');
      if (gearFrame) {{
        ['mousedown', 'dragstart'].forEach(function (evt) {{
          gearFrame.addEventListener(evt, function (e) {{
            e.stopImmediatePropagation();
            e.preventDefault();
          }}, true);
        }});
        gearFrame.addEventListener('click', function (e) {{
          if (e.shiftKey) {{ e.stopImmediatePropagation(); e.preventDefault(); return; }}
          if (e.target.closest('.gear-slot-remove')) {{ e.stopImmediatePropagation(); e.preventDefault(); return; }}
          var slotEl = e.target.closest('.gear-slot');
          if (!slotEl || !slotEl.classList.contains('filled')) {{ e.stopImmediatePropagation(); e.preventDefault(); return; }}
        }}, true);
      }}

      // Nothing to remove: pgShareIconBtn/pgShareCard live inside .pg-share-wrap
      // in the "Purchase Goals" <h2> that render_purchase_goals_share already
      // strips.

      // Import icon next to "Shared by <name>": a <button> only when the viewer
      // was signed in at render time; signed out it is a plain <a
      // href="/signup?..."> with no JS. Toggles pgImportCard (.pg-import-wrap in
      // purchase-goals.css), closed by an outside click. Nothing is imported
      // until pgImportSaveBtn is clicked.
      var pgImportBtn = document.getElementById('pgImportBtn');
      var pgImportCard = document.getElementById('pgImportCard');
      if (pgImportBtn) {{
        function setPgImportOpen(open) {{
          pgImportCard.hidden = !open;
          pgImportBtn.classList.toggle('open', open);
        }}
        pgImportBtn.addEventListener('click', function () {{
          setPgImportOpen(pgImportCard.hidden);
        }});
        document.addEventListener('click', function (e) {{
          var wrap = document.querySelector('.pg-import-wrap');
          if (wrap && !wrap.contains(e.target)) setPgImportOpen(false);
        }});
      }}

      // SAVE TO MY MYSCAPE: imports this share's frozen setup into the visitor's
      // Purchase Goals list (POST
      // /api/shares/{share.code}/import in app/main.py), then -- only
      // once that succeeds, navigates there with the setup appended and
      // selected. A failed import leaves the card open and flashes the button
      // red for 2.5s like pgShareGenerateBtn.
      //
      // IMPORTANT: call window.fetch/window.localStorage explicitly. The bare
      // identifiers resolve to this IIFE's `var fetch` shim and `var
      // localStorage` shadow, which only keep the reused panel harmless; this
      // handler is real behavior, and writing the new setup's id to the shadow
      // would never reach the Purchase Goals page's real key.
      var pgImportSaveBtn = document.getElementById('pgImportSaveBtn');
      if (pgImportSaveBtn) {{
        pgImportSaveBtn.addEventListener('click', function () {{
          var btn = this;
          btn.disabled = true;
          window.fetch('/api/shares/{share.code}/import', {{ method: 'POST' }})
            .then(function (res) {{ return res.ok ? res.json() : Promise.reject(); }})
            .then(function (data) {{
              try {{
                if (data && data.importedSetupId) {{
                  window.localStorage.setItem('myscape:purchaseGoals:activeSetupId', data.importedSetupId);
                }}
              }} catch (e) {{ /* same best-effort posture setActiveSetupId's own try/catch takes above -- losing the auto-select is fine, the import itself already succeeded */ }}
              window.location.href = '/dashboard/purchase-goals';
            }})
            .catch(function () {{
              btn.disabled = false;
              btn.classList.add('action-failed');
              setTimeout(function () {{ btn.classList.remove('action-failed'); }}, 2500);
            }});
        }});
      }}
    }})();
    """

    return _shell(
        title=f"{owner_name}'s shared Purchase Goal — myscape",
        player=viewer,
        body=body,
        extra_head=extra_head,
        extra_script=wrapper_script,
        meta_description=f'{owner_name} shared their "{setup_name}" Purchase Goal setup on myscape.',
    )


def render_landing_mindmap_preview() -> Optional[Tuple[str, str, str]]:
    """Interactive Mindmaps preview for the landing page, like
    render_landing_loot_preview/render_landing_purchase_preview: reuses
    _mindmaps_panel_markup unmodified with a wrapper script. The data is
    app/data/landing_mindmap_demo.json, a frozen GET /api/mindmaps pull of the
    real "Example" mindmap. Returns (extra_head, body, script), or None if the
    snapshot or its search-pools sidecar
    (_get_landing_mindmap_search_pools_data) can't be read.
    
    Unlike the other previews this one is fully editable, in memory only. Tree
    mutations in app/mindmaps.py never touch account state, so they are ported
    to JS. A node's `completed` flag (evaluate_completion) depends on live
    account state and is frozen per node id, except the gray manual toggle
    (setNodeGoal) and the root's flag (withRecomputedRoot).
    
    1. A `fetch` shim (local `var fetch`) that serves GET /api/mindmaps from
    DEMO_MINDMAP, applies the node-mutation endpoints to it in memory
    (validation failures reject as {{detail: "..."}} like the real 400),
    answers /api/npcs|items|quests/search from the bundled SEARCH_POOLS, and
    fails anything else so no call carries a visitor's session cookie.
    2. `localStorage` is shadowed by an in-memory object: the reused script
    persists myscape:mindmaps:editMode and :activeMindmapId, and the landing
    page shares an origin with the real Mindmaps page, so the preview would
    otherwise inherit and overwrite the visitor's real preferences.
    3. #mmSwitchBtn is wired once, so it gets the cloneNode+replaceWith strip.
    4. Wheel-zoom is disabled and touch pan/pinch only works in fullscreen, so
    the page keeps scrolling (see the comments in the wrapper script). No
    setInterval: the real page doesn't poll either.
    """
    demo = _get_landing_mindmap_demo_data()
    search_pools = _get_landing_mindmap_search_pools_data()
    if demo is None or search_pools is None:
        return None
    extra_head, body, script = _mindmaps_panel_markup()

    # Hero row (tagline left, image right; .mindmap-preview-hero in
    # mindmaps.css). The "Mindmaps" <h2> is hidden via CSS.
    hero_markup = """
    <div class="mindmap-preview-hero">
      <div class="mindmap-preview-tagline-wrap">
        <p class="mindmap-preview-tagline">
          <span class="mindmap-preview-tagline-gold">MINDMAPS</span> <span class="mindmap-preview-tagline-white">to plan every step of your grind.</span>
        </p>
      </div>
      <picture class="mindmap-preview-char">
        <source srcset="/static/img/landing-mindmap-preview-char.webp" type="image/webp">
        <img src="/static/img/landing-mindmap-preview-char.png" alt="" />
      </picture>
    </div>
    """
    body = hero_markup + body

    demo_json = json.dumps(demo)
    search_pools_json = json.dumps(search_pools)
    wrapper_script = f"""
    (function () {{
      var DEMO_STATE = {demo_json};
      var DEMO_MINDMAP = DEMO_STATE.mindmaps[0];
      var SEARCH_POOLS = {search_pools_json};
      var ITEM_ICON_CDN_BASE = 'https://static.runelite.net/cache/item/icon/';

      var localStorage = (function () {{
        var store = {{}};
        return {{
          getItem: function (k) {{ return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; }},
          setItem: function (k, v) {{ store[k] = String(v); }},
          removeItem: function (k) {{ delete store[k]; }},
        }};
      }})();

      // Mutation logic ported from app/mindmaps.py. Each function mirrors its
      // Python counterpart (validation, defaults, a new node array, never
      // mutated in place) so the fetch shim returns the real response shape;
      // withRecomputedRoot handles the one field never carried over.
      var NODE_COLORS = ['gray', 'red', 'orange', 'yellow', 'green', 'blue', 'purple', 'white'];
      var DEFAULT_COLOR = 'gray';
      var DEFAULT_TEXT = 'New';
      var MAX_NODE_TEXT_LENGTH = 120;
      var MAX_NODE_NOTE_LENGTH = 200;
      var GOAL_TYPE_BY_COLOR = {{ gray: 'manual', red: 'kc', orange: 'item', yellow: 'gp', green: 'skill', blue: 'quest', purple: 'diary', white: null }};
      var KC_ACTIVITY_TYPES = ['npc', 'pickpocket', 'event'];
      var SKILL_NAMES = {{}};
      ['attack', 'defence', 'strength', 'hitpoints', 'ranged', 'prayer', 'magic', 'cooking', 'woodcutting', 'fletching',
       'fishing', 'firemaking', 'crafting', 'smithing', 'mining', 'herblore', 'agility', 'thieving', 'slayer', 'farming',
       'runecraft', 'hunter', 'construction', 'sailing'].forEach(function (s) {{ SKILL_NAMES[s] = true; }});
      var DIARY_AREAS = {{}};
      ['ardougne', 'desert', 'falador', 'fremennik', 'kandarin', 'karamja', 'kourend_kebos', 'lumbridge_draynor',
       'morytania', 'varrock', 'western_provinces', 'wilderness'].forEach(function (a) {{ DIARY_AREAS[a] = true; }});
      var DIARY_TIERS = ['easy', 'medium', 'hard', 'elite'];
      var MAX_GOAL_NAME_LENGTH = 80;
      var MAX_KC_TARGET = 1000000, MAX_ITEM_QTY_TARGET = 2000000000, MAX_GP_TARGET = 100000000000;
      var MIN_SKILL_LEVEL = 1, MAX_SKILL_LEVEL = 126, MIN_SKILL_XP = 0, MAX_SKILL_XP = 200000000;

      function newNodeId() {{
        if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {{
          var r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
          return v.toString(16);
        }});
      }}
      function cleanText(text, allowEmpty) {{
        text = String(text == null ? '' : text).trim().slice(0, MAX_NODE_TEXT_LENGTH).trim();
        if (allowEmpty) return text;
        return text || DEFAULT_TEXT;
      }}
      function cleanNote(note) {{
        var cleaned = String(note == null ? '' : note).trim();
        var lines = cleaned.split('\\n');
        if (lines.length > 2) cleaned = lines.slice(0, 2).join('\\n');
        return cleaned.slice(0, MAX_NODE_NOTE_LENGTH);
      }}
      function cleanColor(color, isRoot) {{
        if (isRoot) return 'white';
        var cleaned = NODE_COLORS.indexOf(color) !== -1 ? color : DEFAULT_COLOR;
        return cleaned === 'white' ? DEFAULT_COLOR : cleaned;
      }}
      function cleanGoalText(value, fieldName) {{
        var text = String(value == null ? '' : value).trim().slice(0, MAX_GOAL_NAME_LENGTH);
        if (!text) throw new Error(fieldName + " can't be empty.");
        return text;
      }}
      function cleanIntInRange(value, fieldName, minimum, maximum) {{
        var n = Number(value);
        if (!isFinite(n)) throw new Error(fieldName + ' must be a whole number.');
        n = Math.trunc(n);
        if (n < minimum || n > maximum) throw new Error(fieldName + ' must be between ' + minimum + ' and ' + maximum + '.');
        return n;
      }}
      function cleanGoalDate(value, fieldName) {{
        var text = String(value == null ? '' : value).trim();
        if (!/^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(text)) throw new Error(fieldName + ' must be a YYYY-MM-DD date.');
        return text;
      }}
      function defaultGoal(color) {{
        var t = GOAL_TYPE_BY_COLOR[color];
        if (t === 'manual') return {{ manualComplete: false }};
        if (t == null) return null;
        return {{}};
      }}
      function cleanGoal(color, goal, requireComplete) {{
        var t = GOAL_TYPE_BY_COLOR[color];
        goal = (goal && typeof goal === 'object') ? goal : {{}};
        if (t === 'manual') return {{ manualComplete: !!goal.manualComplete }};
        if (t == null) return null;
        var cleaned = {{}};
        function field(name, cleanFn, missingMsg) {{
          var value = goal[name];
          if (value == null || value === '') {{
            if (requireComplete) throw new Error(missingMsg);
            return;
          }}
          cleaned[name] = cleanFn(value);
        }}
        if (t === 'kc') {{
          field('activityType', function (v) {{
            if (KC_ACTIVITY_TYPES.indexOf(v) === -1) throw new Error('activityType must be one of ' + KC_ACTIVITY_TYPES.join(', ') + '.');
            return v;
          }}, 'Pick what kind of activity this goal tracks.');
          field('sourceName', function (v) {{ return cleanGoalText(v, 'sourceName'); }}, 'Pick an NPC.');
          field('targetCount', function (v) {{ return cleanIntInRange(v, 'targetCount', 1, MAX_KC_TARGET); }}, 'Set a target kc.');
          if (goal.sinceDate) cleaned.sinceDate = cleanGoalDate(goal.sinceDate, 'sinceDate');
          return cleaned;
        }}
        if (t === 'item') {{
          field('itemName', function (v) {{ return cleanGoalText(v, 'itemName'); }}, 'Pick an item.');
          field('targetQty', function (v) {{ return cleanIntInRange(v, 'targetQty', 1, MAX_ITEM_QTY_TARGET); }}, 'Set a target quantity.');
          return cleaned;
        }}
        if (t === 'gp') {{
          field('targetGp', function (v) {{ return cleanIntInRange(v, 'targetGp', 1, MAX_GP_TARGET); }}, 'Set a gp target.');
          return cleaned;
        }}
        if (t === 'skill') {{
          field('skill', function (v) {{
            v = String(v).trim().toLowerCase();
            if (!SKILL_NAMES[v]) throw new Error('skill must be a real OSRS skill.');
            return v;
          }}, 'Pick a skill.');
          field('metric', function (v) {{
            if (v !== 'level' && v !== 'xp') throw new Error("metric must be 'level' or 'xp'.");
            return v;
          }}, 'Pick level or experience.');
          if (cleaned.metric === 'xp') {{
            field('target', function (v) {{ return cleanIntInRange(v, 'target', MIN_SKILL_XP, MAX_SKILL_XP); }}, 'Set an experience target.');
          }} else {{
            field('target', function (v) {{ return cleanIntInRange(v, 'target', MIN_SKILL_LEVEL, MAX_SKILL_LEVEL); }}, 'Set a level target.');
          }}
          return cleaned;
        }}
        if (t === 'quest') {{
          field('questName', function (v) {{ return cleanGoalText(v, 'questName'); }}, 'Pick a quest.');
          return cleaned;
        }}
        if (t === 'diary') {{
          field('area', function (v) {{
            v = String(v).trim().toLowerCase();
            if (!DIARY_AREAS[v]) throw new Error('area must be a real diary area.');
            return v;
          }}, 'Pick a diary area.');
          field('tier', function (v) {{
            v = String(v).trim().toLowerCase();
            if (DIARY_TIERS.indexOf(v) === -1) throw new Error('tier must be one of ' + DIARY_TIERS.join(', ') + '.');
            return v;
          }}, 'Pick a tier.');
          return cleaned;
        }}
        return cleaned;
      }}
      function findNode(nodes, id) {{
        for (var i = 0; i < nodes.length; i++) {{ if (nodes[i].id === id) return nodes[i]; }}
        return null;
      }}
      function childrenOf(nodes, parentId) {{
        return nodes.filter(function (n) {{ return n.parentId === parentId; }}).sort(function (a, b) {{ return a.order - b.order; }});
      }}
      function depthOf(nodes, id) {{
        var depth = 0, node = findNode(nodes, id);
        while (node && node.parentId != null) {{ node = findNode(nodes, node.parentId); depth++; }}
        return depth;
      }}
      function nextChildOrder(nodes, parentId) {{
        var kids = childrenOf(nodes, parentId);
        return kids.length ? kids[kids.length - 1].order + 1.0 : 0.0;
      }}
      function orderAfter(nodes, node) {{
        var sibs = childrenOf(nodes, node.parentId);
        var idx = sibs.findIndex(function (n) {{ return n.id === node.id; }});
        if (idx + 1 < sibs.length) return (node.order + sibs[idx + 1].order) / 2.0;
        return node.order + 1.0;
      }}
      function orderBefore(nodes, node) {{
        var sibs = childrenOf(nodes, node.parentId);
        var idx = sibs.findIndex(function (n) {{ return n.id === node.id; }});
        if (idx > 0) return (sibs[idx - 1].order + node.order) / 2.0;
        return node.order - 1.0;
      }}
      // Mirrors add_node in app/mindmaps.py; returns {{nodes, newId}}.
      function addNode(nodes, relativeId, relation, text, color, before) {{
        var relative = findNode(nodes, relativeId);
        if (!relative) throw new Error('That node no longer exists.');
        var newColor = cleanColor(color, false);
        var newNode = {{ id: newNodeId(), text: cleanText(text, true), color: newColor, goal: defaultGoal(newColor), completed: false }};
        if (relation === 'child') {{
          newNode.parentId = relativeId;
          newNode.order = nextChildOrder(nodes, relativeId);
          return {{ nodes: nodes.concat([newNode]), newId: newNode.id }};
        }}
        if (relation === 'sibling') {{
          if (relative.parentId == null) throw new Error("The root node can't have a sibling -- try adding a parent or child instead.");
          newNode.parentId = relative.parentId;
          newNode.order = before ? orderBefore(nodes, relative) : orderAfter(nodes, relative);
          return {{ nodes: nodes.concat([newNode]), newId: newNode.id }};
        }}
        if (relation === 'parent') {{
          if (relative.parentId == null) throw new Error("The root node can't have a parent added -- it's the one node every mindmap keeps.");
          newNode.parentId = relative.parentId;
          newNode.order = relative.order;
          var updated = nodes.map(function (n) {{
            if (n.id === relativeId) {{ n = Object.assign({{}}, n, {{ parentId: newNode.id, order: 0.0 }}); }}
            return n;
          }});
          return {{ nodes: updated.concat([newNode]), newId: newNode.id }};
        }}
        throw new Error("relation must be 'parent', 'child', or 'sibling'.");
      }}
      // Mirrors add_shared_child in app/mindmaps.py.
      function addSharedChild(nodes, parentIds, text, color) {{
        if (parentIds.length < 2) throw new Error('Select at least two nodes to add a shared child below them.');
        parentIds.forEach(function (pid) {{ if (!findNode(nodes, pid)) throw new Error('That node no longer exists.'); }});
        var depths = {{}};
        parentIds.forEach(function (pid) {{ depths[depthOf(nodes, pid)] = true; }});
        if (Object.keys(depths).length > 1) throw new Error('Selected nodes must all be at the same level to add a shared child below them.');
        var primaryParentId = parentIds[0];
        var newColor = cleanColor(color, false);
        var newNode = {{
          id: newNodeId(), text: cleanText(text, true), color: newColor, goal: defaultGoal(newColor), completed: false,
          parentId: primaryParentId, order: nextChildOrder(nodes, primaryParentId), extraParentIds: parentIds.slice(1),
        }};
        return {{ nodes: nodes.concat([newNode]), newId: newNode.id }};
      }}
      // Mirrors update_node in app/mindmaps.py: a color change resets `goal` to
      // a blank default and `completed` to false (the old criteria's frozen
      // value means nothing).
      function updateNode(nodes, nodeId, text, color, note) {{
        var node = findNode(nodes, nodeId);
        if (!node) throw new Error('That node no longer exists.');
        var isRoot = node.parentId == null;
        return nodes.map(function (n) {{
          if (n.id !== nodeId) return n;
          n = Object.assign({{}}, n);
          if (text != null) n.text = cleanText(text, false);
          if (color != null) {{
            var newColor = cleanColor(color, isRoot);
            if (newColor !== n.color) {{ n.goal = defaultGoal(newColor); n.completed = false; }}
            n.color = newColor;
          }}
          if (note != null) n.note = cleanNote(note);
          return n;
        }});
      }}
      function deleteNode(nodes, nodeId) {{
        var target = findNode(nodes, nodeId);
        if (!target) throw new Error('That node no longer exists.');
        if (target.parentId == null) throw new Error("The root node can't be deleted on its own -- delete the whole mindmap instead.");
        var toRemove = {{}};
        toRemove[nodeId] = true;
        var changed = true;
        while (changed) {{
          changed = false;
          nodes.forEach(function (n) {{
            if (!toRemove[n.id] && n.parentId != null && toRemove[n.parentId]) {{ toRemove[n.id] = true; changed = true; }}
          }});
        }}
        var kept = [];
        nodes.forEach(function (n) {{
          if (toRemove[n.id]) return;
          if (n.extraParentIds && n.extraParentIds.length) {{
            var pruned = n.extraParentIds.filter(function (pid) {{ return !toRemove[pid]; }});
            if (pruned.length !== n.extraParentIds.length) n = Object.assign({{}}, n, {{ extraParentIds: pruned }});
          }}
          kept.push(n);
        }});
        return kept;
      }}
      // Mirrors replace_nodes in app/mindmaps.py (what Undo/Redo restore
      // against). `completed` carries over from the restored snapshot rather
      // than being reset.
      function replaceNodes(nodes) {{
        if (!nodes || !nodes.length) throw new Error('A mindmap needs at least one node.');
        var ids = nodes.map(function (n) {{ return n.id; }});
        var idSet = {{}};
        var dup = false;
        ids.forEach(function (id) {{ if (id == null || idSet[id]) dup = true; idSet[id] = true; }});
        if (dup || Object.keys(idSet).length !== ids.length) throw new Error('Every node needs its own unique id.');
        var byId = {{}};
        nodes.forEach(function (n) {{ byId[n.id] = n; }});
        var roots = nodes.filter(function (n) {{ return n.parentId == null; }});
        if (roots.length !== 1) throw new Error('A mindmap needs exactly one root node.');
        nodes.forEach(function (n) {{ if (n.parentId != null && !idSet[n.parentId]) throw new Error("A node's parent must exist in the same tree."); }});
        nodes.forEach(function (n) {{
          var cur = n, hops = 0;
          while (cur && cur.parentId != null) {{
            hops++;
            if (hops > nodes.length) throw new Error('The submitted tree contains a cycle.');
            cur = byId[cur.parentId];
          }}
        }});
        return nodes.map(function (n) {{
          var isRoot = n.parentId == null;
          var newColor = cleanColor(n.color, isRoot);
          var newNode = {{
            id: n.id, parentId: n.parentId != null ? n.parentId : null,
            text: cleanText(n.text, true), color: newColor,
            goal: cleanGoal(newColor, n.goal, false),
            order: (typeof n.order === 'number') ? n.order : 0.0,
            completed: !!n.completed,
          }};
          if (n.note) newNode.note = cleanNote(n.note);
          if (n.extraParentIds && n.extraParentIds.length) {{
            var pruned = n.extraParentIds.filter(function (pid) {{ return idSet[pid] && pid !== n.id; }});
            if (pruned.length) newNode.extraParentIds = pruned;
          }}
          return newNode;
        }});
      }}
      // Mirrors set_node_goal in app/mindmaps.py. For a gray node `completed` IS
      // the cleaned manualComplete flag, the one completion check the demo can
      // keep live; other colors' `completed` stays as it was (criteria can't be
      // evaluated without account context).
      function setNodeGoal(nodes, nodeId, goal) {{
        var node = findNode(nodes, nodeId);
        if (!node) throw new Error('That node no longer exists.');
        var color = node.color || DEFAULT_COLOR;
        var cleaned = cleanGoal(color, goal, true);
        return nodes.map(function (n) {{
          if (n.id !== nodeId) return n;
          var out = Object.assign({{}}, n, {{ goal: cleaned }});
          if (color === 'gray') out.completed = !!(cleaned && cleaned.manualComplete);
          return out;
        }});
      }}
      // The root's `completed` is recomputed (evaluate_completion in
      // app/mindmaps.py): true iff there is at least one other node and every
      // one is complete. Other nodes' values are already known (frozen, or
      // toggled by setNodeGoal), so this is a pure aggregation.
      function findRootId(nodes) {{
        var r = nodes.find(function (n) {{ return n.parentId == null; }});
        return r ? r.id : null;
      }}
      function withRecomputedRoot(nodes) {{
        var rootId = findRootId(nodes);
        if (rootId == null) return nodes;
        var nonRoot = nodes.filter(function (n) {{ return n.id !== rootId; }});
        var rootComplete = nonRoot.length > 0 && nonRoot.every(function (n) {{ return !!n.completed; }});
        return nodes.map(function (n) {{ return n.id === rootId ? Object.assign({{}}, n, {{ completed: rootComplete }}) : n; }});
      }}
      function currentState() {{
        return {{ mindmaps: [Object.assign({{}}, DEMO_MINDMAP, {{ nodes: withRecomputedRoot(DEMO_MINDMAP.nodes) }})] }};
      }}

      // Local goal-criteria search (answered locally instead of reaching
      // /api/npcs|items|quests/search). Ranking is startswith then contains,
      // shortest first, as in search_npc_names/search_quest_names/search_items.
      function localSearchNames(list, query) {{
        var q = String(query || '').trim().toLowerCase();
        if (!q) return [];
        var starts = [], contains = [];
        list.forEach(function (name) {{
          var lname = name.toLowerCase();
          if (lname.indexOf(q) === 0) starts.push(name);
          else if (lname.indexOf(q) !== -1) contains.push(name);
        }});
        starts.sort(function (a, b) {{ return a.length - b.length; }});
        contains.sort(function (a, b) {{ return a.length - b.length; }});
        return starts.concat(contains).slice(0, 20);
      }}
      function localSearchItems(list, query) {{
        var q = String(query || '').trim().toLowerCase();
        if (!q) return [];
        var starts = [], contains = [];
        list.forEach(function (item) {{
          var lname = item.name.toLowerCase();
          if (lname.indexOf(q) === 0) starts.push(item);
          else if (lname.indexOf(q) !== -1) contains.push(item);
        }});
        starts.sort(function (a, b) {{ return a.name.length - b.name.length; }});
        contains.sort(function (a, b) {{ return a.name.length - b.name.length; }});
        return starts.concat(contains).slice(0, 20).map(function (item) {{
          return {{ id: item.id, name: item.name, icon: ITEM_ICON_CDN_BASE + item.id + '.png' }};
        }});
      }}

      // fetch shim
      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        var qIndex = url.indexOf('?');
        var path = qIndex === -1 ? url : url.slice(0, qIndex);
        var params = new URLSearchParams(qIndex === -1 ? '' : url.slice(qIndex + 1));
        function ok(data) {{ return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(data); }} }}); }}
        function fail(detail) {{ return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{ detail: detail }}); }} }}); }}

        if (path === '/api/mindmaps' && method === 'GET') {{
          return ok(currentState());
        }}
        if (path === '/api/npcs/search' && method === 'GET') {{
          return ok({{ results: localSearchNames(SEARCH_POOLS.npcs, params.get('q')) }});
        }}
        if (path === '/api/quests/search' && method === 'GET') {{
          return ok({{ results: localSearchNames(SEARCH_POOLS.quests, params.get('q')) }});
        }}
        if (path === '/api/items/search' && method === 'GET') {{
          return ok({{ results: localSearchItems(SEARCH_POOLS.items, params.get('q')) }});
        }}

        var mmPrefix = '/api/mindmaps/' + encodeURIComponent(DEMO_MINDMAP.id);
        var body = {{}};
        try {{ body = opts.body ? JSON.parse(opts.body) : {{}}; }} catch (e) {{ body = {{}}; }}

        if (path === mmPrefix + '/nodes' && method === 'POST') {{
          try {{
            var res = addNode(DEMO_MINDMAP.nodes, body.relative_to, body.relation, body.text, body.color, !!body.before);
            DEMO_MINDMAP.nodes = res.nodes;
            var state = currentState();
            state.newNodeId = res.newId;
            return ok(state);
          }} catch (e) {{ return fail(e.message); }}
        }}
        if (path === mmPrefix + '/nodes/shared-child' && method === 'POST') {{
          try {{
            var res2 = addSharedChild(DEMO_MINDMAP.nodes, body.parent_ids || [], body.text, body.color);
            DEMO_MINDMAP.nodes = res2.nodes;
            var state2 = currentState();
            state2.newNodeId = res2.newId;
            return ok(state2);
          }} catch (e) {{ return fail(e.message); }}
        }}
        if (path === mmPrefix + '/nodes' && method === 'PUT') {{
          try {{
            DEMO_MINDMAP.nodes = replaceNodes(body.nodes || []);
            return ok(currentState());
          }} catch (e) {{ return fail(e.message); }}
        }}
        if (path.indexOf(mmPrefix + '/nodes/') === 0) {{
          var rest = path.slice((mmPrefix + '/nodes/').length);
          var isGoal = rest.slice(-5) === '/goal';
          var nodeId = decodeURIComponent(isGoal ? rest.slice(0, -5) : rest);
          if (method === 'PATCH' && isGoal) {{
            try {{
              DEMO_MINDMAP.nodes = setNodeGoal(DEMO_MINDMAP.nodes, nodeId, body.goal || {{}});
              if (body.note != null) DEMO_MINDMAP.nodes = updateNode(DEMO_MINDMAP.nodes, nodeId, null, null, body.note);
              return ok(currentState());
            }} catch (e) {{ return fail(e.message); }}
          }}
          if (method === 'PATCH') {{
            try {{
              DEMO_MINDMAP.nodes = updateNode(DEMO_MINDMAP.nodes, nodeId, body.text, body.color, body.note);
              return ok(currentState());
            }} catch (e) {{ return fail(e.message); }}
          }}
          if (method === 'DELETE') {{
            try {{
              DEMO_MINDMAP.nodes = deleteNode(DEMO_MINDMAP.nodes, nodeId);
              return ok(currentState());
            }} catch (e) {{ return fail(e.message); }}
          }}
        }}
        return fail('Not available in this preview.');
      }};

      // Disable wheel-zoom on the landing preview: only the toolbar buttons
      // zoom, unlike the real page. A capturing listener with stopPropagation
      // would also starve the landing page's window-level 'wheel' listener,
      // which drives its JS section-snapping scroll. Instead addEventListener is
      // shadowed on #mmCanvas itself (this instance, not the prototype) and the
      // reused script's one 'wheel' listener is wrapped: a plain wheel over the
      // canvas skips it and bubbles on to scroll-snap the page, while wheels
      // over the note textarea or goal-search popover still reach its bail-out
      // logic. Other event types pass through. In fullscreen the canvas covers
      // the page, so scroll-to-zoom is let through; this is checked on every
      // wheel event, since a session can enter and exit fullscreen.
      var mmCanvasForWheelPatch = document.getElementById('mmCanvas');
      if (mmCanvasForWheelPatch) {{
        var mmRealAddEventListener = mmCanvasForWheelPatch.addEventListener.bind(mmCanvasForWheelPatch);
        mmCanvasForWheelPatch.addEventListener = function (type, listener, opts) {{
          // Same for touch: on the homepage a finger swipe on the non-fullscreen
          // preview scrolls the page, not the map. The first finger still
          // reaches pointerdown/up (a tap deselects) but its moves are skipped
          // (no pan) and a second finger is dropped (no pinch).
          if (type === 'pointerdown' || type === 'pointermove') {{
            return mmRealAddEventListener(type, function (e) {{
              if (e.pointerType === 'touch' && !mmCanvasForWheelPatch.classList.contains('mm-fullscreen')) {{
                if (type === 'pointermove' || !e.isPrimary) return;
              }}
              return listener.call(this, e);
            }}, opts);
          }}
          if (type !== 'wheel') return mmRealAddEventListener(type, listener, opts);
          return mmRealAddEventListener('wheel', function (e) {{
            if (mmCanvasForWheelPatch.classList.contains('mm-fullscreen')) return listener(e);
            if (e.target.closest('[data-role="node-note-input"], .mm-node-note-text')) return listener(e);
            if (e.target.closest('[data-role="popover"]')) return listener(e);
          }}, opts);
        }};
      }}

      {script}

      // Neutralize the mindmap-switcher trigger: wired once on load, so the
      // one-time cloneNode+replaceWith strip works. Its menu never opens (only
      // one mindmap here).
      var switchBtn = document.getElementById('mmSwitchBtn');
      if (switchBtn) {{
        switchBtn.replaceWith(switchBtn.cloneNode(true));
        document.getElementById('mmSwitchBtn').style.cursor = 'default';
      }}

      // Remove the export icon and its popup (both in .mm-share-wrap): nothing
      // to share from an anonymous demo, and the reused script never looks them
      // up again.
      var shareWrap = document.querySelector('.mm-share-wrap');
      if (shareWrap) shareWrap.remove();

    }})();
    """
    return extra_head, body, wrapper_script


def _mindmaps_panel_markup() -> Tuple[str, str, str]:
    """Builds Mindmaps' (extra_head, body, script) triple, split out of
    render_mindmaps so render_landing_mindmap_preview can embed the same
    panel. Everything is rendered client-side from one JSON payload (GET
    /api/mindmaps, build_mindmaps_state in app/mindmaps.py); mutations return
    the recomputed state for render() to redraw. No polling, since nothing
    external changes a mindmap. The canvas is positioned <div>s plus one <svg>
    overlay laid out by computeLayout; node width/height match mindmaps.css so
    layout needs no DOM measurement.
    """
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
          <button class="mm-switch-btn" id="mmSwitchBtn" type="button" data-tooltip="Mindmap options">
            <span class="mm-switch-name" id="mmSwitchName"></span>
            <span class="mm-switch-caret">&#9662;</span>
          </button>
          <div class="mm-menu" id="mmMenu" style="display:none;"></div>
        </div>
      </div>
      <div class="mm-canvas" id="mmCanvas">
        <div class="mm-zoom-controls">
          <button type="button" id="mmUndoBtn" data-tooltip="Undo" disabled>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>
          </button>
          <button type="button" id="mmRedoBtn" data-tooltip="Redo" disabled>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
          </button>
          <div class="mm-zoom-divider"></div>
          <button type="button" id="mmZoomIn" data-tooltip="Zoom in">+</button>
          <button type="button" id="mmZoomOut" data-tooltip="Zoom out">&minus;</button>
          <button type="button" id="mmZoomFit" data-tooltip="Fit to zoom">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="10.5" cy="10.5" r="6.5"></circle><line x1="20" y1="20" x2="15.5" y2="15.5"></line></svg>
          </button>
          <button type="button" id="mmFullscreenBtn" data-tooltip="Enter fullscreen">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>
          </button>
          <div class="mm-zoom-divider"></div>
          <button type="button" id="mmEditModeBtn" data-tooltip="Enter edit mode">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.83 2.83 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5Z"></path><path d="M15 5l4 4"></path></svg>
          </button>
        </div>
        <div class="mm-world" id="mmWorld">
          <svg class="mm-lines" id="mmLines"></svg>
          <div id="mmNodesLayer"></div>
        </div>
      </div>
    </div>
    """
    # Export icon next to the title, a popover like
    # loot-share-wrap/pm-share-wrap (duplicated with an mm- prefix) holding the
    # GENERATE SHAREABLE LINK flow (build_mindmap_share_snapshot in
    # app/mindmaps.py). Inserted via str.replace because body/script are plain
    # strings full of literal { }.
    mm_share_icon_btn = (
        ' <span class="mm-share-wrap">'
        '<button type="button" class="mm-share-icon-btn" id="mmShareIconBtn" aria-label="Share the currently selected mindmap" data-tooltip="Share the currently selected mindmap">'
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
        '<polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line>'
        '</svg></button>'
        '<div class="mm-share-card" id="mmShareCard" hidden>'
        '<button type="button" class="mm-share-generate-btn" id="mmShareGenerateBtn">GENERATE SHAREABLE LINK</button>'
        '<button type="button" class="mm-share-link-btn" id="mmShareLinkBtn" data-tooltip="Click to copy" hidden></button>'
        '<p class="mm-share-popup-hint">Links are active for 30 days, but can be<br>deleted sooner on your Account page.</p>'
        '</div>'
        '</span>'
    )
    body = body.replace(
        '<h2 class="page-title">Mindmaps</h2>',
        f'<h2 class="page-title">Mindmaps{mm_share_icon_btn}</h2>',
    )
    script = """
    (function () {
      // Must match mindmaps.css .mm-node width/height; layout is arithmetic on
      // these.
      var NODE_WIDTH = 160;
      var NODE_HEIGHT = 46;
      if (!document.body.classList.contains('landing')) {
        window.myscapeTouchTooltipFilter = function () { return false; };
      }
      var COL_WIDTH = 190;   // horizontal spacing between sibling leaf columns
      var ROW_HEIGHT = 110;  // vertical spacing between depth levels
      var MARGIN = 60;       // breathing room around the whole tree inside the world
      // Extra room below the last row for popovers that hang past their node
      // (POPOVER_HEIGHT_PAD); the tallest is about 260px.
      var POPOVER_HEIGHT_PAD = 420;

      // Mirrors NODE_COLORS in app/mindmaps.py (white is root-only); every
      // .mm-node-<color> CSS class assumes this set.
      var NODE_COLORS = ['gray', 'red', 'orange', 'yellow', 'green', 'blue', 'purple', 'white'];

      // Mirrors the goal-type constants in app/mindmaps.py (GOAL_TYPE_BY_COLOR,
      // SKILL_NAMES, DIARY_AREAS, DIARY_TIERS); the server re-validates via
      // clean_goal. Keep in sync.
      var GOAL_TYPE_BY_COLOR = {
        gray: 'manual', red: 'kc', orange: 'item', yellow: 'gp',
        green: 'skill', blue: 'quest', purple: 'diary', white: null,
      };
      // Goal-type picker options: every NODE_COLORS entry except "white", with
      // local clan rank icons (app/static/img/). Array order is the 3-column
      // grid order.
      var GOAL_TYPE_PICKER = [
        { color: 'red', label: 'KC', icon: '/static/img/icon-goal-kc.png' },
        { color: 'orange', label: 'ITEM', icon: '/static/img/icon-goal-item.png' },
        { color: 'yellow', label: 'GP', icon: '/static/img/icon-goal-gp.png' },
        { color: 'green', label: 'SKILL', icon: '/static/img/icon-goal-skill.png' },
        { color: 'blue', label: 'QUEST', icon: '/static/img/icon-goal-quest.png' },
        { color: 'purple', label: 'DIARY', icon: '/static/img/icon-goal-diary.png' },
        { color: 'gray', label: 'MANUAL' },
      ];
      var GOAL_TYPE_ICON_BY_COLOR = {};
      GOAL_TYPE_PICKER.forEach(function (opt) { if (opt.icon) GOAL_TYPE_ICON_BY_COLOR[opt.color] = opt.icon; });
      var NOTE_ICON_PAPER_SVG = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>';
      var NOTE_ICON_ARROW_SVG = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">' +
        '<line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>';
      var SKILL_NAMES = [
        'attack', 'defence', 'strength', 'hitpoints', 'ranged', 'prayer', 'magic',
        'cooking', 'woodcutting', 'fletching', 'fishing', 'firemaking', 'crafting',
        'smithing', 'mining', 'herblore', 'agility', 'thieving', 'slayer', 'farming',
        'runecraft', 'hunter', 'construction', 'sailing',
      ];
      // Mirrors MIN/MAX_SKILL_LEVEL and MIN/MAX_SKILL_XP in app/mindmaps.py for
      // validateSkillTarget. Levels run 1-126 (virtual levels); level 1 / 0 xp
      // are valid so the LVL/XP toggle never lands out of range.
      var MIN_SKILL_LEVEL = 1, MAX_SKILL_LEVEL = 126;
      var MIN_SKILL_XP = 0, MAX_SKILL_XP = 200000000;
      var MAX_KC_TARGET = 1000000;
      var MAX_ITEM_QTY_TARGET = 2000000000;
      var MAX_GP_TARGET = 100000000000;
      // OSRS xp-per-level curve for levels 1-126
      // (https://oldschool.runescape.wiki/w/Experience). SKILL_XP_TABLE[L] is
      // the xp for level L (index 0 unused).
      var SKILL_XP_TABLE = (function () {
        var table = [0, 0];
        var cumulative = 0;
        for (var l = 1; l < MAX_SKILL_LEVEL; l++) {
          cumulative += Math.floor(l + 300 * Math.pow(2, l / 7));
          table[l + 1] = Math.floor(cumulative / 4);
        }
        return table;
      })();
      function xpForLevel(level) {
        level = Math.max(MIN_SKILL_LEVEL, Math.min(MAX_SKILL_LEVEL, Math.round(level)));
        return SKILL_XP_TABLE[level];
      }
      function levelForXp(xp) {
        for (var l = MAX_SKILL_LEVEL; l >= MIN_SKILL_LEVEL; l--) {
          if (xp >= SKILL_XP_TABLE[l]) return l;
        }
        return MIN_SKILL_LEVEL;
      }
      var GOAL_SEARCH_ENDPOINTS = {
        npc: '/api/npcs/search',
        item: '/api/items/search',
        quest: '/api/quests/search',
      };
      var DIARY_AREAS = [
        'ardougne', 'desert', 'falador', 'fremennik', 'kandarin', 'karamja',
        'kourend_kebos', 'lumbridge_draynor', 'morytania', 'varrock',
        'western_provinces', 'wilderness',
      ];
      // Some diary names need explicit labels ("Kourend & Kebos", "Lumbridge &
      // Draynor").
      var DIARY_AREA_LABELS = {
        ardougne: 'Ardougne', desert: 'Desert', falador: 'Falador',
        fremennik: 'Fremennik', kandarin: 'Kandarin', karamja: 'Karamja',
        kourend_kebos: 'Kourend & Kebos', lumbridge_draynor: 'Lumbridge & Draynor',
        morytania: 'Morytania', varrock: 'Varrock',
        western_provinces: 'Western Provinces', wilderness: 'Wilderness',
      };
      var DIARY_TIERS = ['easy', 'medium', 'hard', 'elite'];
      function titleCase(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
      // Each diary's icon is its elite-tier reward item
      // (https://oldschool.runescape.wiki/w/Achievement_Diary), via RuneLite CDN
      // URLs like item_icon_url in app/purchase_goals.py.
      var DIARY_AREA_ICON = {
        ardougne: 'https://static.runelite.net/cache/item/icon/13124.png',
        desert: 'https://static.runelite.net/cache/item/icon/13136.png',
        falador: 'https://static.runelite.net/cache/item/icon/13120.png',
        fremennik: 'https://static.runelite.net/cache/item/icon/13132.png',
        kandarin: 'https://static.runelite.net/cache/item/icon/13140.png',
        karamja: 'https://static.runelite.net/cache/item/icon/13103.png',
        kourend_kebos: 'https://static.runelite.net/cache/item/icon/22947.png',
        lumbridge_draynor: 'https://static.runelite.net/cache/item/icon/13128.png',
        morytania: 'https://static.runelite.net/cache/item/icon/13115.png',
        varrock: 'https://static.runelite.net/cache/item/icon/13107.png',
        western_provinces: 'https://static.runelite.net/cache/item/icon/13144.png',
        wilderness: 'https://static.runelite.net/cache/item/icon/13111.png',
      };
      var LOCAL_SEARCH_POOLS = {
        skill: SKILL_NAMES.map(function (key) {
          return { value: key, label: titleCase(key), icon: '/static/skill-icons/' + key + '.png' };
        }).sort(function (a, b) { return a.label.localeCompare(b.label); }),
        diary: DIARY_AREAS.map(function (area) {
          return { value: area, label: DIARY_AREA_LABELS[area], icon: DIARY_AREA_ICON[area] };
        }).sort(function (a, b) { return a.label.localeCompare(b.label); }),
      };

      var MM = {
        data: null,
        activeMindmapId: null,
        selectedNodeId: null,
        focusNodeId: null, // one-shot: focus + select this node's text on the next render
        multiSelectIds: new Set(),
        flippedNodeIds: new Set(),
        nameFormMode: null, // 'new' | 'rename' | null
        pan: { x: 0, y: 0 },
        zoom: 1,
        lastLayout: null, // set by renderCanvas, read by zoomToFit
        undoStack: [],
        redoStack: [],
        editMode: false,
        fullscreen: false,
      };
      MM.editMode = loadStoredEditMode();

      var ACTIVE_MINDMAP_STORAGE_KEY = 'myscape:mindmaps:activeMindmapId';
      function loadStoredActiveMindmapId() {
        try { return localStorage.getItem(ACTIVE_MINDMAP_STORAGE_KEY); } catch (e) { return null; }
      }
      function setActiveMindmapId(id) {
        resetMindmapShareState();
        MM.activeMindmapId = id;
        MM.undoStack = [];
        MM.redoStack = [];
        try {
          if (id) localStorage.setItem(ACTIVE_MINDMAP_STORAGE_KEY, id);
          else localStorage.removeItem(ACTIVE_MINDMAP_STORAGE_KEY);
        } catch (e) { /* ignore -- see comment above */ }
      }

      // Edit Mode (pencil toggle, #mmEditModeBtn/updateEditModeButton),
      // persisted per browser like ACTIVE_MINDMAP_STORAGE_KEY.
      // - OFF (default): pan/zoom/select, plus the GRAY node's "Mark complete"
      // toggle.
      // - ON: the full editor (labels, edge "+" buttons, swatches, delete, goal
      // forms, multi-select/shared-child).
      var EDIT_MODE_STORAGE_KEY = 'myscape:mindmaps:editMode';
      function loadStoredEditMode() {
        try { return localStorage.getItem(EDIT_MODE_STORAGE_KEY) === '1'; } catch (e) { return false; }
      }
      function setEditMode(on) {
        if (on === MM.editMode) return;
        commitActiveLabelIfEditing();
        MM.editMode = on;
        try {
          if (on) localStorage.setItem(EDIT_MODE_STORAGE_KEY, '1');
          else localStorage.removeItem(EDIT_MODE_STORAGE_KEY);
        } catch (e) { /* ignore -- see ACTIVE_MINDMAP_STORAGE_KEY's own comment */ }
        if (!on && MM.multiSelectIds.size > 1) {
          MM.multiSelectIds = MM.selectedNodeId ? new Set([MM.selectedNodeId]) : new Set();
        }
        // Entering edit mode flips nodes back to their front face: the
        // note-toggle icon is hidden in edit mode (.mm-view-mode), so a flipped
        // note couldn't be flipped back.
        if (on) MM.flippedNodeIds.clear();
        render();
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

      // Tree layout: top-down, no library. Each leaf gets its own column so
      // subtrees can't overlap; each parent centers over its first and last
      // child.
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

        // A shared child (extraParentIds) is centered under all its linked
        // parents, clamped against same-depth nodes to keep one column of
        // spacing (keeps its own column if packed).
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
            clampedCenter = positions[n.id].x + NODE_WIDTH / 2;
          } else {
            if (clampedCenter < minAllowed) clampedCenter = minAllowed;
            if (clampedCenter > maxAllowed) clampedCenter = maxAllowed;
          }

          var oldCenter = positions[n.id].x + NODE_WIDTH / 2;
          var delta = clampedCenter - oldCenter;
          positions[n.id].x = clampedCenter - NODE_WIDTH / 2;
          if (delta !== 0) {
            (function shiftSubtree(nodeId) {
              (childrenMap.get(nodeId) || []).forEach(function (kid) {
                if (positions[kid.id]) {
                  positions[kid.id].x += delta;
                  shiftSubtree(kid.id);
                }
              });
            })(n.id);
          }
        });

        return {
          positions: positions,
          childrenMap: childrenMap,
          root: root,
          worldWidth: Math.max(1, leafCounter.value) * COL_WIDTH + MARGIN * 2,
          worldHeight: (maxDepth + 1) * ROW_HEIGHT + MARGIN * 2,
        };
      }

      // Pan/zoom

      var mmWorldEl = document.getElementById('mmWorld');
      function applyTransform() {
        mmWorldEl.style.transform =
          'translate(' + MM.pan.x + 'px, ' + MM.pan.y + 'px) scale(' + MM.zoom + ')';
        positionFloatingSuggestions();
      }

      var MIN_ZOOM = 0.2;
      var MAX_ZOOM = 2;

      // Zooms around (originX, originY) in viewport pixels (default: center) by
      // re-solving pan so the world point under the origin stays put.
      function setZoom(z, originX, originY) {
        var canvas = document.getElementById('mmCanvas');
        if (originX == null) originX = canvas.clientWidth / 2;
        if (originY == null) originY = canvas.clientHeight / 2;
        var newZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, z));
        if (newZoom !== MM.zoom) {
          var worldX = (originX - MM.pan.x) / MM.zoom;
          var worldY = (originY - MM.pan.y) / MM.zoom;
          MM.zoom = newZoom;
          MM.pan.x = originX - worldX * MM.zoom;
          MM.pan.y = originY - worldY * MM.zoom;
          applyTransform();
        }
        updateZoomButtons();
      }

      // Nudges the pan (never the zoom) so an open popover's edges clear
      // .mm-canvas when its node is near the bottom (POPOVER_HEIGHT_PAD) or off
      // to a side. Called after every render, since popover size varies by goal
      // type. Uses MM.pan/applyTransform instead of native scroll-into-view,
      // which scrolls .mm-canvas and drags the zoom controls out of the box.
      // Overflow is measured against the current MM.pan, never a remembered
      // baseline, which would snap the view back when switching from a tall goal
      // type to a short one that fits.
      function ensurePopoverVisible() {
        var popover = document.querySelector('#mmNodesLayer [data-role="popover"]');
        if (!popover) return;
        var layout = MM.lastLayout;
        var pos = layout && MM.selectedNodeId ? layout.positions[MM.selectedNodeId] : null;
        if (!pos) return;
        var canvas = document.getElementById('mmCanvas');
        var canvasRect = canvas.getBoundingClientRect();
        // Computed analytically, not via getBoundingClientRect(): .mm-world has
        // a 0.18s transform transition, so a rapid popover change would measure
        // it mid-glide. screen = pan + zoom * local (transform-origin 0 0) using
        // the authoritative MM.pan/MM.zoom; the popover's local box comes from
        // its CSS (.mm-node-popover: top calc(100% + 22px), left
        // 50%/translateX(-50%)) plus offsetWidth/offsetHeight.
        var localTop = pos.y + NODE_HEIGHT + 22;
        var localBottom = localTop + popover.offsetHeight;
        var localCenterX = pos.x + NODE_WIDTH / 2;
        var localLeft = localCenterX - popover.offsetWidth / 2;
        var localRight = localCenterX + popover.offsetWidth / 2;
        var MARGIN = 16;

        var targetPanY = MM.pan.y;
        var screenTop = canvasRect.top + targetPanY + MM.zoom * localTop;
        var screenBottom = canvasRect.top + targetPanY + MM.zoom * localBottom;
        var overflowBelow = screenBottom - (canvasRect.bottom - MARGIN);
        var overflowAbove = (canvasRect.top + MARGIN) - screenTop;
        if (overflowBelow > 0) {
          targetPanY -= overflowBelow;
        } else if (overflowAbove > 0) {
          targetPanY += overflowAbove;
        }
        if (targetPanY !== MM.pan.y) {
          MM.pan.y = targetPanY;
          applyTransform();
        }

        var targetPanX = MM.pan.x;
        var screenLeft = canvasRect.left + targetPanX + MM.zoom * localLeft;
        var screenRight = canvasRect.left + targetPanX + MM.zoom * localRight;
        var overflowRight = screenRight - (canvasRect.right - MARGIN);
        var overflowLeft = (canvasRect.left + MARGIN) - screenLeft;
        if (overflowRight > 0) {
          targetPanX -= overflowRight;
        } else if (overflowLeft > 0) {
          targetPanX += overflowLeft;
        }
        if (targetPanX !== MM.pan.x) {
          MM.pan.x = targetPanX;
          applyTransform();
        }
      }

      // Deliberate no-op: scrolling the outer page for a popover made it jerk on
      // ordinary clicks. Kept so its call sites stay unchanged.
      function scrollCanvasPopoverIntoView() {
        if (MM.fullscreen) return;
      }

      // Fits the tree's bounding box in the viewport (clamped to
      // MIN_ZOOM-MAX_ZOOM) and centers it, using the tight box of node positions
      // rather than layout.worldWidth/worldHeight. Also frames every
      // load/switch/create/delete.
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
        var pad = (window.matchMedia && window.matchMedia('(max-width: 700px)').matches) ? 16 : 40; // breathing room inside the viewport edges
        var availW = Math.max(1, viewW - pad * 2), availH = Math.max(1, viewH - pad * 2);
        var z = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Math.min(availW / boxW, availH / boxH)));
        MM.zoom = z;
        var boxCenterX = minX + boxW / 2, boxCenterY = minY + boxH / 2;
        MM.pan.x = viewW / 2 - boxCenterX * z;
        MM.pan.y = viewH / 2 - boxCenterY * z;
        applyTransform();
        updateZoomButtons();
      }

      function commitActiveLabelIfEditing() {
        var el = document.activeElement;
        if (el && el.isContentEditable && el.getAttribute && el.getAttribute('data-role') === 'label') el.blur();
      }

      var MM_FULLSCREEN_ENTER_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>';
      var MM_FULLSCREEN_EXIT_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline><line x1="14" y1="10" x2="21" y2="3"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>';

      // Fullscreen fills the window via a CSS class (.mm-canvas.mm-fullscreen),
      // not the Fullscreen API: no permission prompt, and Escape closes it.
      // Document scroll is locked because the canvas's slot collapses once
      // position: fixed.
      function setFullscreen(on) {
        if (on === MM.fullscreen) return;
        commitActiveLabelIfEditing();
        MM.fullscreen = on;
        document.getElementById('mmCanvas').classList.toggle('mm-fullscreen', on);
        document.documentElement.style.overflow = on ? 'hidden' : '';
        var btn = document.getElementById('mmFullscreenBtn');
        btn.classList.toggle('active', on);
        btn.setAttribute('data-tooltip', on ? 'Exit fullscreen' : 'Enter fullscreen');
        btn.innerHTML = on ? MM_FULLSCREEN_EXIT_ICON : MM_FULLSCREEN_ENTER_ICON;
        zoomToFit();
        // zoomToFit doesn't know a popover may be open, and fullscreen toggling
        // skips render()'s popover-visibility effect, so an open popover would
        // be left off-screen.
        if (MM.selectedNodeId) {
          // zoomToFit's applyTransform() just started the 0.18s transition, so
          // measuring the popover now would be mid-flight; land this step
          // instantly.
          mmWorldEl.style.transitionDuration = '0s';
          ensurePopoverVisible();
          scrollCanvasPopoverIntoView();
          mmWorldEl.style.transitionDuration = '';
        }
      }

      // Blurring a still-editing label fires its text-commit PATCH. A click on
      // the same node would race a second request and flash a stray caret, so
      // the click delegation awaits this first.
      var pendingLabelCommit = null;

      var canvasEl = document.getElementById('mmCanvas');
      var panState = { active: false, startX: 0, startY: 0, startPanX: 0, startPanY: 0, moved: false };
      canvasEl.addEventListener('pointerdown', function (e) {
        commitActiveLabelIfEditing();
        if (e.pointerType === 'touch') return;
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

      // Touch: pinch-to-zoom, two-finger pan, one-finger pan. .mm-canvas is
      // touch-action: none, so fingers arrive as pointer events (up to two
      // tracked). One finger pans past a small slop (so a tap on a node still
      // selects); two fingers pinch around the starting midpoint. Transitions
      // are off during the gesture and taps ending it are swallowed.
      var touchPtrs = {};
      var touchPan = null;
      var pinch = null;
      var touchClickBlockUntil = 0;
      var TOUCH_SLOP = 8;
      function touchIds() { return Object.keys(touchPtrs); }
      function touchIgnored(t) {
        return !!(t.closest && t.closest('.mm-zoom-controls, [data-role="popover"], .mm-suggestions, input, textarea, select, [contenteditable="true"], .mm-edge-btn, [data-role="manual-toggle"], [data-role="note-toggle"]'));
      }
      function touchFinish() {
        canvasEl.classList.remove('panning');
        mmWorldEl.style.transitionDuration = '';
      }
      function touchHoldPointer(id) {
        try { canvasEl.setPointerCapture(id); } catch (_) {}
      }
      function startPinch() {
        var ids = touchIds();
        var a = touchPtrs[ids[0]], b = touchPtrs[ids[1]];
        var rect = canvasEl.getBoundingClientRect();
        var mx = (a.x + b.x) / 2 - rect.left, my = (a.y + b.y) / 2 - rect.top;
        pinch = {
          dist: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)),
          zoom: MM.zoom,
          wx: (mx - MM.pan.x) / MM.zoom,
          wy: (my - MM.pan.y) / MM.zoom
        };
        touchPan = null;
        mmWorldEl.style.transitionDuration = '0s';
        canvasEl.classList.add('panning');
        touchClickBlockUntil = Date.now() + 600;
        ids.forEach(function (id) { touchHoldPointer(+id); });
      }
      function updatePinch() {
        var ids = touchIds();
        var a = touchPtrs[ids[0]], b = touchPtrs[ids[1]];
        if (!a || !b) return;
        var rect = canvasEl.getBoundingClientRect();
        var mx = (a.x + b.x) / 2 - rect.left, my = (a.y + b.y) / 2 - rect.top;
        var dist = Math.max(1, Math.hypot(a.x - b.x, a.y - b.y));
        var z = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, pinch.zoom * dist / pinch.dist));
        MM.zoom = z;
        MM.pan.x = mx - pinch.wx * z;
        MM.pan.y = my - pinch.wy * z;
        applyTransform();
        updateZoomButtons();
      }
      canvasEl.addEventListener('pointerdown', function (e) {
        if (e.pointerType !== 'touch' || touchIgnored(e.target)) return;
        if (touchIds().length >= 2) return; // a third finger is ignored
        touchPtrs[e.pointerId] = { x: e.clientX, y: e.clientY };
        if (touchIds().length === 1) {
          touchPan = {
            id: e.pointerId, sx: e.clientX, sy: e.clientY,
            px: MM.pan.x, py: MM.pan.y, moved: false,
            empty: !e.target.closest('.mm-node')
          };
        } else {
          startPinch();
        }
      }, true);
      canvasEl.addEventListener('pointermove', function (e) {
        if (e.pointerType !== 'touch') return;
        var p = touchPtrs[e.pointerId];
        if (!p) return;
        p.x = e.clientX; p.y = e.clientY;
        if (pinch) { updatePinch(); return; }
        if (!touchPan || touchPan.id !== e.pointerId) return;
        var dx = e.clientX - touchPan.sx, dy = e.clientY - touchPan.sy;
        if (!touchPan.moved) {
          if (Math.hypot(dx, dy) < TOUCH_SLOP) return;
          touchPan.moved = true;
          // Re-base so the view doesn't jump by the slop distance.
          touchPan.sx = e.clientX; touchPan.sy = e.clientY;
          touchPan.px = MM.pan.x; touchPan.py = MM.pan.y;
          dx = 0; dy = 0;
          touchHoldPointer(e.pointerId);
          canvasEl.classList.add('panning');
          mmWorldEl.style.transitionDuration = '0s';
        }
        MM.pan.x = touchPan.px + dx;
        MM.pan.y = touchPan.py + dy;
        applyTransform();
      });
      function touchEnd(e) {
        if (e.pointerType !== 'touch' || !touchPtrs[e.pointerId]) return;
        delete touchPtrs[e.pointerId];
        var left = touchIds();
        if (pinch) {
          pinch = null;
          touchClickBlockUntil = Date.now() + 600;
          if (left.length === 1) {
            // One finger still down: carry on as a one-finger pan.
            var rest = touchPtrs[left[0]];
            touchPan = { id: +left[0], sx: rest.x, sy: rest.y, px: MM.pan.x, py: MM.pan.y, moved: true, empty: false };
          } else {
            touchFinish();
          }
          return;
        }
        if (touchPan && touchPan.id === e.pointerId) {
          var tp = touchPan;
          touchPan = null;
          if (tp.moved) {
            touchClickBlockUntil = Date.now() + 400;
            touchFinish();
          } else if (tp.empty && e.type === 'pointerup') {
            selectNode(null); // a plain tap on empty canvas deselects
          }
        }
      }
      canvasEl.addEventListener('pointerup', touchEnd);
      canvasEl.addEventListener('pointercancel', touchEnd);
      canvasEl.addEventListener('click', function (e) {
        if (Date.now() < touchClickBlockUntil && !e.target.closest('.mm-zoom-controls')) {
          e.stopPropagation();
          e.preventDefault();
        }
      }, true);
      // Wheel-zoom. Transitions stay off while wheel events keep arriving and
      // return after wheelSettleMs without one; otherwise each tick restarts the
      // 0.18s transition and a constantly re-transitioning layer blurs the
      // canvas. Tick size scales exponentially with deltaY since trackpad ticks
      // vary. Ticks apply instantly rather than eased via requestAnimationFrame:
      // a sustained per-frame ramp makes Chrome's compositor trade raster
      // fidelity for it, so the canvas goes soft while moving.
      var wheelZoomSensitivity = 0.0013;
      var wheelSettleTimer = null;
      var wheelSettleMs = 200;
      canvasEl.addEventListener('wheel', function (e) {
        // A wheel event over a popover (e.g. a long .mm-suggestions list) must
        // not zoom the canvas: bail without preventDefault so the browser
        // scrolls it. The note textarea and back face are overflow: hidden, so
        // swallow the event there or it leaks to the page scroll.
        if (e.target.closest('[data-role="node-note-input"], .mm-node-note-text')) {
          e.preventDefault();
          return;
        }
        if (e.target.closest('[data-role="popover"]')) return;
        e.preventDefault();
        mmWorldEl.style.transitionDuration = '0s';
        setZoom(MM.zoom * Math.exp(-e.deltaY * wheelZoomSensitivity));
        clearTimeout(wheelSettleTimer);
        wheelSettleTimer = setTimeout(function () {
          mmWorldEl.style.transitionDuration = ''; // hand back to .mm-world's own smooth-zoom transition
        }, wheelSettleMs);
      }, { passive: false });

      document.getElementById('mmZoomIn').addEventListener('click', function () { setZoom(MM.zoom + 0.15); });
      document.getElementById('mmZoomOut').addEventListener('click', function () { setZoom(MM.zoom - 0.15); });
      document.getElementById('mmZoomFit').addEventListener('click', zoomToFit);
      document.getElementById('mmUndoBtn').addEventListener('click', undo);
      document.getElementById('mmRedoBtn').addEventListener('click', redo);
      document.getElementById('mmFullscreenBtn').addEventListener('click', function () { setFullscreen(!MM.fullscreen); });
      document.getElementById('mmEditModeBtn').addEventListener('click', function () { setEditMode(!MM.editMode); });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && MM.fullscreen) setFullscreen(false);
      });

      // Node selection + click delegation

      // A plain click REPLACES the selection (null clears it). Re-selecting the
      // same node is a no-op: a re-render would lose the caret in an editable
      // label.
      function selectNode(id) {
        var alreadyJustThis = id === MM.selectedNodeId && (
          (id === null && MM.multiSelectIds.size === 0) ||
          (id !== null && MM.multiSelectIds.size === 1 && MM.multiSelectIds.has(id))
        );
        if (alreadyJustThis) return;
        MM.selectedNodeId = id;
        MM.multiSelectIds = new Set(id ? [id] : []);
        var mmForFocus = activeMindmap();
        var nodeForFocus = mmForFocus && id ? mmForFocus.nodes.find(function (n) { return n.id === id; }) : null;
        var focusGoalType = nodeForFocus ? GOAL_TYPE_BY_COLOR[nodeForFocus.color] : null;
        var focusIsFreeText = (focusGoalType === 'manual' || !focusGoalType);
        MM.focusNodeId = (MM.editMode && id && focusIsFreeText) ? id : null;
        render();
      }

      // Shift-click toggles the node in the selection; the latest becomes the
      // anchor. A shared child only joins nodes at the same depth
      // (add_shared_child in app/mindmaps.py), so a mismatched node is silently
      // refused.
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
        // Edge buttons, the popover, the manual-complete checkbox and the
        // note-flip toggle work with or without Edit Mode; only a click on the
        // node body is gated on it.
        if (e.target.closest('.mm-edge-btn') || e.target.closest('[data-role="popover"]') || e.target.closest('[data-role="manual-toggle"]') || e.target.closest('[data-role="note-toggle"]')) return;
        if (!MM.editMode) { glowEditModeButton(); return; }
        if (e.shiftKey) { extendMultiSelect(el.getAttribute('data-node-id')); return; }
        selectNode(el.getAttribute('data-node-id'));
      });

      document.getElementById('mmNodesLayer').addEventListener('click', async function (e) {
        if (pendingLabelCommit) {
          await pendingLabelCommit;
          pendingLabelCommit = null;
        }
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
        var typeBtn = e.target.closest('.mm-type-btn');
        if (typeBtn) { updateSelectedNode({ color: typeBtn.getAttribute('data-color') }); return; }
        var segBtn = e.target.closest('.mm-segment-btn');
        if (segBtn) {
          var segGroup = segBtn.closest('[data-role="segment-group"]');
          if (!segGroup) return;
          segGroup.querySelectorAll('.mm-segment-btn').forEach(function (b) { b.classList.toggle('active', b === segBtn); });
          var segHidden = segGroup.nextElementSibling;
          if (segHidden && segHidden.matches('input[type="hidden"]')) segHidden.value = segBtn.getAttribute('data-segment-value');
          showGoalSaveError(null);
          if (segGroup.getAttribute('data-segment-field') === 'metric') {
            var fieldsWrapForMetric = segGroup.closest('[data-role="goal-fields"]');
            var targetForMetric = fieldsWrapForMetric && fieldsWrapForMetric.querySelector('[data-goal-field="target"]');
            if (targetForMetric) {
              var newMetric = segBtn.getAttribute('data-segment-value');
              var rawTargetForMetric = targetForMetric.value.trim();
              if (rawTargetForMetric !== '') {
                var nTargetForMetric = Number(parseMoneySuffix(rawTargetForMetric));
                if (Number.isInteger(nTargetForMetric)) {
                  targetForMetric.value = newMetric === 'xp'
                    ? xpForLevel(nTargetForMetric)
                    : levelForXp(nTargetForMetric);
                }
              }
              targetForMetric.placeholder = (newMetric === 'xp') ? 'Target experience' : 'Target level';
              validateSkillTarget(targetForMetric);
            }
          }
          return;
        }
        if (e.target.closest('[data-role="delete"]')) { deleteSelectedNode(); return; }
        if (e.target.closest('[data-role="add-shared-child"]')) { addSharedChildSelected(); return; }
        // Manual-complete checkbox on gray nodes: works in or out of Edit Mode;
        // reads the clicked node fresh so a quick double-click toggles
        // correctly.
        var toggleEl = e.target.closest('[data-role="manual-toggle"]');
        if (toggleEl) {
          var toggleNodeEl = toggleEl.closest('.mm-node');
          var toggleNodeId = toggleNodeEl && toggleNodeEl.getAttribute('data-node-id');
          var mmForToggle = activeMindmap();
          var toggleNode = mmForToggle && toggleNodeId
            ? mmForToggle.nodes.find(function (n) { return n.id === toggleNodeId; })
            : null;
          if (toggleNode) saveNodeGoal(toggleNodeId, { manualComplete: !(toggleNode.goal && toggleNode.goal.manualComplete) });
          return;
        }
        // Note-flip button: a local view toggle (MM.flippedNodeIds), no request.
        // Inert in Edit Mode (pointer-events: none in .mm-node-note-toggle);
        // this check is a backstop.
        var noteToggleEl = e.target.closest('[data-role="note-toggle"]');
        if (noteToggleEl) {
          if (MM.editMode) return;
          var noteToggleNodeEl = noteToggleEl.closest('.mm-node');
          var noteToggleNodeId = noteToggleNodeEl && noteToggleNodeEl.getAttribute('data-node-id');
          if (noteToggleNodeId) flipNodeNote(noteToggleNodeId);
          return;
        }
        if (e.target.closest('[data-role="goal-save"]')) {
          var popoverForSave = e.target.closest('[data-role="popover"]');
          var fieldsWrap = popoverForSave && popoverForSave.querySelector('[data-role="goal-fields"]');
          if (!fieldsWrap) return;
          var noteInputForSave = popoverForSave && popoverForSave.querySelector('[data-role="node-note-input"]');
          var noteValForSave = noteInputForSave ? noteInputForSave.value.trim() : '';
          var nodeForSave = selectedNode();
          if (nodeForSave && GOAL_TYPE_BY_COLOR[nodeForSave.color] === 'manual') {
            var textInput = fieldsWrap.querySelector('[data-role="node-text-input"]');
            var textVal = textInput ? textInput.value.trim() : '';
            if (!textVal) {
              if (textInput) textInput.classList.add('invalid');
              return;
            }
            var noteChangedForManual = noteValForSave !== (nodeForSave.note || '');
            if (textVal !== nodeForSave.text || noteChangedForManual) {
              saveSelectedNodeText(textVal, noteValForSave, true);
            } else {
              MM.selectedNodeId = null;
              MM.multiSelectIds = new Set();
              render();
            }
            return;
          }
          // sinceDate is the only masked date field here (like the Loot Tracker
          // custom range): as in applyCustomRange, refuse the save and flag it
          // red if digits are typed but not a real date; blank is fine.
          var sinceDateInput = fieldsWrap.querySelector('[data-goal-field="sinceDate"]');
          if (sinceDateInput) {
            var sinceDateVal = sinceDateInput.value.trim();
            if (sinceDateVal && !isValidIsoDate(sinceDateVal)) {
              sinceDateInput.classList.add('invalid');
              return;
            }
          }
          var typeForSave = GOAL_TYPE_BY_COLOR[nodeForSave.color];
          if (!validateGoalFieldsForSave(fieldsWrap, typeForSave)) return;
          var goal = {};
          fieldsWrap.querySelectorAll('[data-goal-field]').forEach(function (input) {
            var val = (input.value || '').trim();
            var field = input.getAttribute('data-goal-field');
            var isNumericTargetField = field === 'targetGp' || field === 'targetCount' || field === 'targetQty' || field === 'target';
            if (isNumericTargetField) val = parseMoneySuffix(val);
            if (val !== '') goal[field] = val;
          });
          saveSelectedNodeGoal(goal, noteValForSave, true);
        }
      });

      document.getElementById('mmNodesLayer').addEventListener('focusout', function (e) {
        var label = e.target.closest('[data-role="label"]');
        if (label) commitNodeTextFromLabel(label);
        // Close suggestions on blur after 150ms so a click on a suggestion can
        // read the box first, unless another field has since taken over the
        // shared box (activeSearchInput).
        var searchInput = e.target.closest('.mm-search-input');
        if (searchInput) {
          setTimeout(function () {
            if (activeSearchInput === searchInput) hideFloatingSuggestions();
          }, 150);
        }
      });
      // Debounced live search and live skill-target validation share one
      // delegated 'input' listener (a full render() would wipe other fields'
      // typing); timers are per input in a WeakMap.
      var searchDebounceTimers = new WeakMap();
      document.getElementById('mmNodesLayer').addEventListener('input', function (e) {
        if (e.target.closest('[data-role="goal-fields"]')) showGoalSaveError(null);
        var goalFieldInput = e.target.closest('[data-goal-field], [data-goal-field-target]');
        if (goalFieldInput) goalFieldInput.classList.remove('invalid');
        var searchInput = e.target.closest('.mm-search-input');
        if (searchInput) {
          clearTimeout(searchDebounceTimers.get(searchInput));
          searchDebounceTimers.set(searchInput, setTimeout(function () { runGoalSearch(searchInput); }, 200));
          return;
        }
        var numericField = e.target.closest(NUMERIC_SUFFIX_FIELDS_SELECTOR);
        if (numericField) filterNumericSuffixInput(numericField);
        var targetInput = e.target.closest('[data-goal-field="target"]');
        if (targetInput && targetInput.closest('.mm-goal-fields')) validateSkillTarget(targetInput);
        var sinceDateInput = e.target.closest('[data-goal-field="sinceDate"]');
        if (sinceDateInput) applyDateMask(sinceDateInput);
        var nodeTextInput = e.target.closest('[data-role="node-text-input"]');
        if (nodeTextInput) validateNodeText(nodeTextInput);
        var noteInput = e.target.closest('[data-role="node-note-input"]');
        if (noteInput) clampNoteInput(noteInput);
      });
      document.getElementById('mmNodesLayer').addEventListener('keydown', function (e) {
        var label = e.target.closest('[data-role="label"]');
        if (!label) return;
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); label.blur(); }
        else if (e.key === 'Escape') { e.preventDefault(); label.blur(); }
      });
      document.getElementById('mmNodesLayer').addEventListener('paste', function (e) {
        var label = e.target.closest('[data-role="label"]');
        if (!label) return;
        e.preventDefault();
        var text = (e.clipboardData || window.clipboardData).getData('text/plain');
        document.execCommand('insertText', false, text);
      });

      // Rendering

      function fmtNum(n) { return Number(n).toLocaleString('en-US'); }

      // Resolves K/M/B shorthand ("140k", "2.5m") in numeric goal targets to the
      // integer the server stores; commas are stripped first, anything else
      // passes through.
      function parseMoneySuffix(raw) {
        var s = (raw || '').trim().replace(/,/g, '');
        var m = /^([0-9]*\\.?[0-9]+)\\s*([kKmMbB])$/.exec(s);
        if (!m) return s;
        var mult = { k: 1e3, m: 1e6, b: 1e9 }[m[2].toLowerCase()];
        return String(Math.round(parseFloat(m[1]) * mult));
      }

      var NUMERIC_SUFFIX_FIELDS_SELECTOR =
        '[data-goal-field="targetCount"], [data-goal-field="targetQty"], ' +
        '[data-goal-field="targetGp"], [data-goal-field="target"]';

      // Restricts numeric-target fields to digits, commas, a decimal point and
      // k/m/b. They're type="text" inputmode="decimal" because a number input
      // can't take the shorthand.
      var NUMERIC_SUFFIX_DISALLOWED_RE = /[^0-9,.kKmMbB]/g;

      function filterNumericSuffixInput(input) {
        var cleaned = input.value.replace(NUMERIC_SUFFIX_DISALLOWED_RE, '');
        if (cleaned === input.value) return;
        var cursor = input.selectionStart;
        var keptBeforeCursor = input.value.slice(0, cursor).replace(NUMERIC_SUFFIX_DISALLOWED_RE, '').length;
        input.value = cleaned;
        input.setSelectionRange(keptBeforeCursor, keptBeforeCursor);
      }

      // sinceDate masks like the Loot Tracker custom range
      // (DATE_MASK/applyDateMask/isValidIsoDate in render_loot_tracker's script,
      // ported since page scripts are self-contained).
      var DATE_MASK = 'dddd-dd-dd';

      function digitsOnly(s) {
        return (s || '').replace(/\\D/g, '').slice(0, 8);
      }

      function maskValueFromDigits(digits) {
        var out = '', di = 0;
        for (var i = 0; i < DATE_MASK.length; i++) {
          if (DATE_MASK[i] === 'd') {
            out += di < digits.length ? digits[di] : '_';
            di++;
          } else {
            out += DATE_MASK[i];
          }
        }
        return out;
      }

      function applyDateMask(input) {
        var digits = digitsOnly(input.value);
        input.value = digits.length ? maskValueFromDigits(digits) : '';
        var pos = 0, di = 0;
        for (var i = 0; i < DATE_MASK.length; i++) {
          if (DATE_MASK[i] === 'd' && di < digits.length) { pos = i + 1; di++; }
        }
        input.setSelectionRange(pos, pos);
        input.classList.remove('invalid');
      }

      function isValidIsoDate(s) {
        var m = /^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(s || '');
        if (!m) return false;
        var year = parseInt(m[1], 10), month = parseInt(m[2], 10), day = parseInt(m[3], 10);
        if (month < 1 || month > 12) return false;
        var daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
        return day >= 1 && day <= daysInMonth;
      }

      // Floating goal-search suggestions dropdown. A scrollable overflow:auto
      // region inside .mm-world gets its own GPU layer, which re-rasterizes
      // .mm-world and blurs the canvas while searching (`contain: paint` and
      // will-change did not help). So it is one shared `position: fixed` element
      // on <body>, placed from the focused input's getBoundingClientRect() and
      // re-synced from applyTransform.
      var floatingSuggestionsEl = null;
      var activeSearchInput = null;
      function getFloatingSuggestionsEl() {
        if (!floatingSuggestionsEl) {
          floatingSuggestionsEl = document.createElement('div');
          floatingSuggestionsEl.className = 'mm-suggestions';
          floatingSuggestionsEl.setAttribute('data-role', 'mm-suggestions');
          document.body.appendChild(floatingSuggestionsEl);
          floatingSuggestionsEl.addEventListener('click', function (e) {
            var suggestionEl = e.target.closest('.mm-suggestion');
            if (!suggestionEl || !activeSearchInput) return;
            var value = suggestionEl.getAttribute('data-value');
            var label = suggestionEl.getAttribute('data-label');
            activeSearchInput.value = (label != null) ? label : value;
            activeSearchInput.classList.remove('invalid');
            var hidden = hiddenTargetFor(activeSearchInput);
            if (hidden) hidden.value = value;
            hideFloatingSuggestions();
            showGoalSaveError(null);
          });
        }
        return floatingSuggestionsEl;
      }
      function positionFloatingSuggestions() {
        if (!activeSearchInput || !floatingSuggestionsEl || !floatingSuggestionsEl.classList.contains('show')) return;
        if (!document.body.contains(activeSearchInput)) { hideFloatingSuggestions(); return; }
        var rect = activeSearchInput.getBoundingClientRect();
        floatingSuggestionsEl.style.left = rect.left + 'px';
        floatingSuggestionsEl.style.top = (rect.bottom + 2) + 'px';
        floatingSuggestionsEl.style.width = rect.width + 'px';
      }
      function hideFloatingSuggestions() {
        if (!floatingSuggestionsEl) return;
        floatingSuggestionsEl.classList.remove('show');
        floatingSuggestionsEl.innerHTML = '';
        activeSearchInput = null;
      }

      function hiddenTargetFor(input) {
        var targetFieldName = input.getAttribute('data-goal-field-target');
        if (!targetFieldName) return null;
        var wrap = input.closest('.mm-search-wrap');
        return wrap && wrap.querySelector('[data-goal-field="' + targetFieldName + '"]');
      }

      async function runGoalSearch(input) {
        var query = input.value.trim();
        var hidden = hiddenTargetFor(input);
        if (!query) {
          if (hidden) hidden.value = '';
          if (activeSearchInput === input) hideFloatingSuggestions();
          return;
        }
        var kind = input.getAttribute('data-search-kind');
        var localPool = LOCAL_SEARCH_POOLS[kind];
        if (localPool) {
          if (!document.body.contains(input) || document.activeElement !== input) return;
          activeSearchInput = input;
          var q = query.toLowerCase();
          // Keep the hidden field in sync on every keystroke with what the text
          // resolves to exactly (or clear it), so a typed full name saves
          // without clicking a suggestion.
          if (hidden) {
            var exact = localPool.filter(function (item) { return item.label.toLowerCase() === q; })[0];
            hidden.value = exact ? exact.value : '';
          }
          var matches = localPool.filter(function (item) { return item.label.toLowerCase().indexOf(q) !== -1; });
          renderGoalSuggestions(getFloatingSuggestionsEl(), kind, matches);
          return;
        }
        var endpoint = GOAL_SEARCH_ENDPOINTS[kind];
        if (!endpoint) return;
        var data = await apiCall(endpoint + '?q=' + encodeURIComponent(query));
        // Bail if the popover or input is gone when the request resolves; the
        // activeElement check also stops a slow response clobbering the shared
        // box.
        if (!document.body.contains(input) || document.activeElement !== input) return;
        activeSearchInput = input;
        renderGoalSuggestions(getFloatingSuggestionsEl(), kind, data ? data.results : []);
      }

      function normalizeSearchResults(kind, raw) {
        if (kind === 'skill' || kind === 'diary') return raw;
        if (kind === 'item') return raw.map(function (r) { return { value: r.name, label: r.name, icon: r.icon }; });
        return raw.map(function (name) { return { value: name, label: name, icon: null }; });
      }

      // Render one search field's suggestion dropdown.
      function renderGoalSuggestions(box, kind, rawResults) {
        var results = normalizeSearchResults(kind, rawResults);
        if (!results.length) {
          var emptyLabel = kind === 'npc' ? 'No NPCs found' : kind === 'quest' ? 'No quests found' :
            kind === 'skill' ? 'No skills found' : kind === 'diary' ? 'No diaries found' : 'No items found';
          box.innerHTML = '<div class="mm-suggestion-empty">' + esc(emptyLabel) + '</div>';
        } else {
          box.innerHTML = results.map(function (r) {
            return '<div class="mm-suggestion" data-kind="' + esc(kind) + '" data-value="' + esc(r.value) + '" data-label="' + esc(r.label) + '">' +
              (r.icon ? '<img src="' + esc(r.icon) + '" alt="">' : '') +
              '<span>' + esc(r.label) + '</span></div>';
          }).join('');
        }
        box.classList.add('show');
        positionFloatingSuggestions();
      }

      // Live range check for the skill target, mirroring MIN/MAX_SKILL_LEVEL/XP
      // (the server re-validates). Invalid is a red border only;
      // showEmptyAsInvalid is off for live calls and on from
      // validateGoalFieldsForSave. Returns validity.
      function validateSkillTarget(input, showEmptyAsInvalid) {
        var fieldsWrap = input.closest('[data-role="goal-fields"]');
        var metricHidden = fieldsWrap && fieldsWrap.querySelector('[data-goal-field="metric"]');
        var metric = (metricHidden && metricHidden.value === 'xp') ? 'xp' : 'level';
        var raw = input.value.trim();
        if (raw === '') { input.classList.toggle('invalid', !!showEmptyAsInvalid); return false; }
        var n = Number(parseMoneySuffix(raw));
        var min = metric === 'xp' ? MIN_SKILL_XP : MIN_SKILL_LEVEL;
        var max = metric === 'xp' ? MAX_SKILL_XP : MAX_SKILL_LEVEL;
        var ok = Number.isInteger(n) && n >= min && n <= max;
        input.classList.toggle('invalid', !ok);
        return ok;
      }

      function validateNodeText(input) {
        if (input.value.trim() !== '') input.classList.remove('invalid');
      }

      var REQUIRED_GOAL_FIELDS = {
        kc: ['sourceName'],
        item: ['itemName'],
        gp: [],
        skill: ['skill'],
        quest: ['questName'],
        diary: ['area'],
      };
      var NUMERIC_TARGET_FIELD = {
        kc: { field: 'targetCount', min: 1, max: MAX_KC_TARGET },
        item: { field: 'targetQty', min: 1, max: MAX_ITEM_QTY_TARGET },
        gp: { field: 'targetGp', min: 1, max: MAX_GP_TARGET },
      };

      function visibleGoalFieldEl(fieldsWrap, name) {
        return fieldsWrap.querySelector('[data-goal-field-target="' + name + '"]') ||
          fieldsWrap.querySelector('[data-goal-field="' + name + '"]');
      }

      // Mirror of clean_goal's required+range checks, run before Save collects
      // fields: toggles .invalid per field instead of a server round trip;
      // showGoalSaveError is the fallback.
      function validateGoalFieldsForSave(fieldsWrap, type) {
        var ok = true;
        (REQUIRED_GOAL_FIELDS[type] || []).forEach(function (name) {
          var visible = visibleGoalFieldEl(fieldsWrap, name);
          var real = fieldsWrap.querySelector('[data-goal-field="' + name + '"]');
          var filled = real && real.value.trim() !== '';
          if (visible) visible.classList.toggle('invalid', !filled);
          if (!filled) ok = false;
        });
        var numericSpec = NUMERIC_TARGET_FIELD[type];
        if (numericSpec) {
          var input = fieldsWrap.querySelector('[data-goal-field="' + numericSpec.field + '"]');
          if (input) {
            var raw = input.value.trim();
            var n = Number(parseMoneySuffix(raw));
            var fieldOk = raw !== '' && Number.isInteger(n) && n >= numericSpec.min && n <= numericSpec.max;
            input.classList.toggle('invalid', !fieldOk);
            if (!fieldOk) ok = false;
          }
        }
        if (type === 'skill') {
          var targetInput = fieldsWrap.querySelector('[data-goal-field="target"]');
          if (targetInput && !validateSkillTarget(targetInput, true)) ok = false;
        }
        return ok;
      }

      // Shows (or with a falsy msg clears) a trackable node's error in its
      // popover, since the #mmError banner can be off-screen on a full-screen
      // canvas. No-op without a goal-save-error slot (manual).
      function showGoalSaveError(msg) {
        var errEl = document.querySelector('[data-role="popover"] [data-role="goal-save-error"]');
        if (!errEl) return;
        if (!msg) { errEl.textContent = ''; errEl.classList.remove('show'); return; }
        errEl.textContent = msg;
        errEl.classList.add('show');
      }

      // A trackable node's text is derived from its goal (clean_goal in
      // app/mindmaps.py): kc "<count> <activity> kc", item "x<qty> <item>", gp
      // "<amount> gp", skill "<xp> <skill> xp" or "lvl <level> <skill>", quest
      // "<quest name>", diary "<diary area> <tier>". Gray and white use
      // free-typed node.text.
      function goalDisplayText(node) {
        var type = GOAL_TYPE_BY_COLOR[node.color];
        var goal = node.goal || {};
        if (type === 'kc') {
          if (!goal.targetCount || !goal.sourceName) return 'Set KC goal';
          return fmtNum(goal.targetCount) + ' ' + goal.sourceName + ' kc';
        }
        if (type === 'item') {
          if (!goal.targetQty || !goal.itemName) return 'Set item goal';
          return 'x' + fmtNum(goal.targetQty) + ' ' + goal.itemName;
        }
        if (type === 'gp') {
          if (!goal.targetGp) return 'Set GP goal';
          return fmtNum(goal.targetGp) + ' gp';
        }
        if (type === 'skill') {
          if (!goal.skill || !goal.metric || !goal.target) return 'Set skill goal';
          var skillLabel = titleCase(goal.skill);
          return goal.metric === 'xp'
            ? fmtNum(goal.target) + ' ' + skillLabel + ' xp'
            : 'Lvl ' + goal.target + ' ' + skillLabel;
        }
        if (type === 'quest') {
          return goal.questName || 'Set quest goal';
        }
        if (type === 'diary') {
          if (!goal.area || !goal.tier) return 'Set diary goal';
          return DIARY_AREA_LABELS[goal.area] + ' ' + titleCase(goal.tier);
        }
        return node.text;
      }

      // Wraps an item goal's leading "x" in a span forced to lowercase (.mm-node
      // uppercases everything else).
      function renderNodeLabelHtml(goalType, text) {
        if (goalType === 'item') {
          var m = /^x(\\d.*)$/.exec(text);
          if (m) return '<span class="mm-node-x-lower">x</span>' + esc(m[1]);
        }
        return esc(text);
      }

      function renderCanvas(mm) {
        var layout = computeLayout(mm.nodes);
        MM.lastLayout = layout;

        var world = document.getElementById('mmWorld');
        // No width padding (a 250px popover overhangs a 160px node by 45px per
        // side, inside MARGIN's 60px). Height padding applies on every render,
        // since the closing render has already dropped the popover.
        world.style.width = layout.worldWidth + 'px';
        world.style.height = (layout.worldHeight + POPOVER_HEIGHT_PAD) + 'px';

        var nodesLayer = document.getElementById('mmNodesLayer');
        nodesLayer.classList.toggle('mm-view-mode', !MM.editMode);

        nodesLayer.innerHTML = mm.nodes.map(function (n) {
          var pos = layout.positions[n.id];
          // Selected nodes get the same brighten treatment, in Edit Mode only,
          // so non-editable nodes don't look pressed.
          var isSelected = MM.multiSelectIds.has(n.id);
          var isAnchor = n.id === MM.selectedNodeId;
          var isRoot = n.parentId === null;
          var selectedCls = (isSelected && MM.editMode) ? ' selected' : '';
          var completedCls = n.completed ? ' completed' : '';
          var goalType = GOAL_TYPE_BY_COLOR[n.color];
          var isFreeText = (goalType === 'manual' || !goalType);
          // Only the root (white, goalType null) is edited inline. A gray node
          // renames via a textbox in its popover (renderGoalFieldsHtml's
          // "manual" branch), so its label is never contenteditable and has no
          // data-role="label"; the post-render focus effect falls back to
          // [data-role="node-text-input"].
          var isInlineEditable = !goalType;
          var editableAttr = (MM.editMode && isInlineEditable && isSelected && MM.multiSelectIds.size === 1) ? ' contenteditable="true" spellcheck="false"' : '';
          var displayText = isFreeText ? n.text : goalDisplayText(n);
          var showManualCheckbox = goalType === 'manual' && !!(n.text && n.text.trim());
          var manualChecked = !!(n.goal && n.goal.manualComplete);
          var iconSrc = GOAL_TYPE_ICON_BY_COLOR[n.color];
          var hasLeftSlot = !!iconSrc || showManualCheckbox;
          var labelCls = 'mm-node-label' + (hasLeftSlot ? ' mm-node-label-with-icon' : '');
          // With a left slot, data-role="label"/editableAttr go on the inner
          // span, since a checkbox inside a contenteditable region would be
          // swept into select-all or mangled by editing.
          var labelInner;
          if (hasLeftSlot) {
            var leftSlotHtml = showManualCheckbox
              ? '<input type="checkbox" class="mm-node-checkbox" data-role="manual-toggle" title="Mark complete"' + (manualChecked ? ' checked' : '') + '>'
              : '<img class="mm-node-icon" src="' + iconSrc + '" alt="">';
            var innerLabelAttrs = isInlineEditable ? (' data-role="label"' + editableAttr) : '';
            labelInner = leftSlotHtml + '<span class="mm-node-label-text"' + innerLabelAttrs + '>' + renderNodeLabelHtml(goalType, displayText) + '</span>';
          } else {
            labelInner = esc(displayText);
          }
          // The root can't get a parent or sibling (the backend enforces it), so
          // only its "add child" edge button shows. Edge buttons are
          // Edit-Mode-only.
          var edgeButtonsHtml = !MM.editMode ? '' :
            (isRoot ? '' : '<button type="button" class="mm-edge-btn mm-edge-top" data-relation="parent">+</button>') +
            '<button type="button" class="mm-edge-btn mm-edge-bottom" data-relation="child">+</button>' +
            (isRoot ? '' : '<button type="button" class="mm-edge-btn mm-edge-left" data-relation="sibling" data-before="1">+</button>') +
            (isRoot ? '' : '<button type="button" class="mm-edge-btn mm-edge-right" data-relation="sibling" data-before="0">+</button>');
          // The anchor node's popover: the full editor for a sole selection
          // (renderNodePopoverHtml), or the "add shared child" button once a
          // second node is shift-added.
          var popoverHtml = '';
          if (isAnchor && MM.multiSelectIds.size === 1) popoverHtml = renderNodePopoverHtml(n);
          else if (isAnchor && MM.multiSelectIds.size >= 2) popoverHtml = renderSharedChildPopoverHtml();
          var labelAttrs = hasLeftSlot ? '' : (isInlineEditable ? (' data-role="label"' + editableAttr) : '');
          // Optional note flip (renderNoteFieldHtml): no note means no toggle or
          // back face. hasNote drops a stale MM.flippedNodeIds entry when a note
          // is cleared.
          var hasNote = !!(n.note && n.note.trim());
          if (!hasNote) MM.flippedNodeIds.delete(n.id);
          var isFlipped = hasNote && MM.flippedNodeIds.has(n.id);
          var noteToggleHtml = !hasNote ? '' :
            '<button type="button" class="mm-node-note-toggle" data-role="note-toggle">' +
            (isFlipped ? NOTE_ICON_ARROW_SVG : NOTE_ICON_PAPER_SVG) + '</button>';
          // The front face is wrapped in a face div so flipNodeNote has one
          // element (.mm-node-flip-inner) to animate; nodes without a note get
          // no wrapper.
          var faceHtml = hasNote
            ? '<div class="mm-node-flip-inner">' +
              (isFlipped
                ? '<div class="mm-node-face mm-node-face-back"><div class="mm-node-note-text">' + esc(n.note) + '</div></div>'
                : '<div class="mm-node-face mm-node-face-front"><div class="' + labelCls + '"' + labelAttrs + '>' + labelInner + '</div></div>') +
              '</div>'
            : '<div class="' + labelCls + '"' + labelAttrs + '>' + labelInner + '</div>';
          return '<div class="mm-node mm-node-' + esc(n.color) + selectedCls + completedCls + '" data-node-id="' + esc(n.id) + '" ' +
            'style="left:' + pos.x + 'px; top:' + pos.y + 'px;">' +
            faceHtml +
            noteToggleHtml +
            edgeButtonsHtml +
            popoverHtml +
            '</div>';
        }).join('');

        // A newly selected node (selectNode) is focused with its text selected
        // once the DOM lands. Deferred with setTimeout(..., 0) because render()
        // runs inside the pointerdown handler, and the browser's default focus
        // resolution afterwards would blur a not-yet-focusable node. Always
        // scheduled so ensurePopoverVisible checks every fresh popover.
        var focusIdForThisRender = MM.focusNodeId;
        MM.focusNodeId = null;
        setTimeout(function () {
          if (focusIdForThisRender) {
            var nodeEl = document.querySelector('.mm-node[data-node-id="' + focusIdForThisRender + '"]');
            if (nodeEl) {
              var label = nodeEl.querySelector('[data-role="label"]');
              if (label) {
                label.focus({ preventScroll: true });
                var range = document.createRange();
                range.selectNodeContents(label);
                var sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
              } else {
                var textInput = nodeEl.querySelector('[data-role="node-text-input"]');
                if (textInput) {
                  textInput.focus({ preventScroll: true });
                  textInput.select();
                }
              }
            }
          }
          ensurePopoverVisible();
          scrollCanvasPopoverIntoView();
        }, 0);

        var svg = document.getElementById('mmLines');
        svg.setAttribute('width', layout.worldWidth);
        svg.setAttribute('height', layout.worldHeight);
        var pathsHtml = '';
        layout.childrenMap.forEach(function (kids, parentId) {
          if (parentId === null || !kids.length) return; // the null bucket just holds the root itself, not a real edge
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

        // Fan-in connectors for shared-child nodes (several parents converging
        // on one child); a separate pass since they have no single parentId.
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
          '<button type="button" class="mm-menu-item" id="mmMenuDuplicate">Duplicate mindmap</button>' +
          '<button type="button" class="mm-menu-item" id="mmMenuRename">Rename mindmap</button>' +
          '<button type="button" class="mm-menu-item danger" id="mmMenuDelete">Delete mindmap</button>';
      }

      // The selected node's popover: swatches, goal form and Save/Delete (Edit
      // Mode only). Shares its shell with renderSharedChildPopoverHtml;
      // renderCanvas shows one of the two. The root has nothing to show (always
      // white, can't be deleted), so bail before rendering an empty shell.
      function renderNodePopoverHtml(node) {
        if (node.parentId === null || !MM.editMode) return '';
        var goalType = GOAL_TYPE_BY_COLOR[node.color];
        var showSave = !!goalType;
        var actionsHtml = '<div class="mm-popover-actions" data-role="popover-actions">' +
          '<button type="button" class="btn-secondary mm-delete-btn mm-color-popover-delete" data-role="delete">Delete</button>' +
          (showSave ? '<button type="button" class="btn-secondary mm-goal-save-btn" data-role="goal-save">SAVE</button>' : '') +
          '</div>';
        // A trackable type's server-validated error
        // (saveNodeGoal/showGoalSaveError) lands here above Save/Delete, not in
        // the page banner.
        return '<div class="mm-node-popover mm-node-popover-wide" data-role="popover">' +
          renderGoalTypePickerHtml(node) +
          renderGoalFieldsHtml(node) +
          renderNoteFieldHtml(node) +
          '<div class="mm-field-error mm-goal-save-error" data-role="goal-save-error"></div>' +
          actionsHtml +
          '</div>';
      }

      // Note two-line cap. A scrollbar inside .mm-world re-triggers the
      // compositing blur (see getFloatingSuggestionsEl) and the textarea and
      // node back face can't move outside it, so notes are capped to 2 lines
      // (overflow: hidden as a backstop). The font is proportional, so the cap
      // measures a candidate value's rendered height in a hidden mirror matching
      // the back face (.mm-node-note-text: 9.5px, line-height 1.35, NODE_WIDTH
      // content width; keep in sync with mindmaps.css).
      var noteMeasureEl = null;
      function getNoteMeasureEl() {
        if (!noteMeasureEl) {
          noteMeasureEl = document.createElement('div');
          noteMeasureEl.style.position = 'fixed';
          noteMeasureEl.style.visibility = 'hidden';
          noteMeasureEl.style.pointerEvents = 'none';
          noteMeasureEl.style.top = '-9999px';
          noteMeasureEl.style.left = '-9999px';
          noteMeasureEl.style.boxSizing = 'border-box';
          noteMeasureEl.style.width = (NODE_WIDTH - 20) + 'px'; // NODE_WIDTH minus .mm-node-face's 10px+10px padding
          noteMeasureEl.style.fontFamily = 'RuneScapePlain11';
          noteMeasureEl.style.fontSize = '9.5px';
          noteMeasureEl.style.lineHeight = '1.35';
          noteMeasureEl.style.whiteSpace = 'pre-wrap';
          noteMeasureEl.style.wordBreak = 'break-word';
          document.body.appendChild(noteMeasureEl);
        }
        return noteMeasureEl;
      }
      var NOTE_MAX_LINES = 2;
      function clampNoteToLines(value) {
        if (!value) return value;
        var mirror = getNoteMeasureEl();
        mirror.textContent = 'M';
        var oneLine = mirror.getBoundingClientRect().height;
        var maxHeight = oneLine * NOTE_MAX_LINES + 1; // +1px slack for sub-pixel rounding
        mirror.textContent = value;
        if (mirror.getBoundingClientRect().height <= maxHeight) return value;
        var lo = 0, hi = value.length;
        while (lo < hi) {
          var mid = (lo + hi + 1) >> 1;
          mirror.textContent = value.slice(0, mid);
          if (mirror.getBoundingClientRect().height <= maxHeight) lo = mid; else hi = mid - 1;
        }
        return value.slice(0, lo);
      }
      // Called from the note textarea's 'input': clamps in place and, if a
      // character was cut, parks the caret at the end (imprecise for a mid-note
      // paste, accepted).
      function clampNoteInput(textarea) {
        var clamped = clampNoteToLines(textarea.value);
        if (clamped !== textarea.value) {
          textarea.value = clamped;
          textarea.setSelectionRange(clamped.length, clamped.length);
        }
      }

      // The optional note every non-root type gets, above Save/Delete. It is
      // saved by the same Save click on the request the node type already sends
      // (one undo step). A plain <textarea>, not resizable (2-line cap,
      // clampNoteInput); maxlength is a backstop matching MAX_NODE_NOTE_LENGTH.
      function renderNoteFieldHtml(node) {
        return '<div class="mm-note-wrap">' +
          '<textarea class="mm-goal-input mm-note-input" data-role="node-note-input" placeholder="Notes (optional)" maxlength="200" rows="2">' +
          esc(node.note || '') + '</textarea>' +
          '</div>';
      }

      // Goal-type picker (GOAL_TYPE_PICKER). Clicking one sets the node's
      // `color` (data-color), which resets its goal (update_node in
      // app/mindmaps.py). "White" is omitted: it is root-only (NODE_COLORS).
      function renderGoalTypePickerHtml(node) {
        var buttons = GOAL_TYPE_PICKER.map(function (opt) {
          var activeCls = (opt.color === node.color) ? ' active' : '';
          var inner = (opt.color === 'gray')
            ? '<span class="mm-type-btn-swatch mm-type-btn-swatch-manual"></span>'
            : '<img class="mm-type-btn-icon" src="' + opt.icon + '" alt="">';
          return '<button type="button" class="mm-type-btn' + activeCls + '" data-color="' + opt.color + '">' +
            inner + '<span class="mm-type-btn-label">' + opt.label + '</span></button>';
        }).join('');
        return '<div class="mm-type-picker">' + buttons + '</div>';
      }

      // A text input with a live search dropdown (KC NPC, ITEM, QUEST;
      // GOAL_SEARCH_ENDPOINTS/runGoalSearch). Typing a name without picking a
      // suggestion still saves.
      function renderSearchFieldHtml(fieldName, searchKind, placeholder, currentValue) {
        return '<div class="mm-search-wrap">' +
          '<input class="mm-goal-input mm-search-input" type="text" autocomplete="off" ' +
          'data-goal-field="' + fieldName + '" data-search-kind="' + searchKind + '" ' +
          'placeholder="' + esc(placeholder) + '" maxlength="80" value="' + esc(currentValue || '') + '">' +
          '</div>';
      }

      // Like renderSearchFieldHtml but backed by LOCAL_SEARCH_POOLS, for fields
      // whose saved value differs from the displayed one (skill key vs name,
      // diary slug vs "Kourend & Kebos"). The visible input's
      // data-goal-field-target points at a hidden companion holding the real
      // data-goal-field.
      function renderLocalSearchFieldHtml(fieldName, searchKind, placeholder, currentValue, labelFor) {
        var displayValue = currentValue ? labelFor(currentValue) : '';
        return '<div class="mm-search-wrap">' +
          '<input class="mm-goal-input mm-search-input" type="text" autocomplete="off" ' +
          'data-goal-field-target="' + fieldName + '" data-search-kind="' + searchKind + '" ' +
          'placeholder="' + esc(placeholder) + '" maxlength="80" value="' + esc(displayValue) + '">' +
          '<input type="hidden" data-goal-field="' + fieldName + '" value="' + esc(currentValue || '') + '">' +
          '</div>';
      }

      function renderSegmentedToggleHtml(fieldName, options, currentValue) {
        var value = options.some(function (o) { return o[0] === currentValue; }) ? currentValue : options[0][0];
        var buttons = options.map(function (o) {
          var activeCls = (o[0] === value) ? ' active' : '';
          return '<button type="button" class="mm-segment-btn' + activeCls + '" data-segment-value="' + o[0] + '">' + esc(o[1]) + '</button>';
        }).join('');
        return '<div class="mm-segment-group" data-role="segment-group" data-segment-field="' + fieldName + '">' + buttons + '</div>' +
          '<input type="hidden" data-goal-field="' + fieldName + '" value="' + esc(value) + '">';
      }

      // The current color's goal fields, prefilled from the node's `goal`
      // (clean_goal/ default_goal in app/mindmaps.py). Only runs in Edit Mode,
      // never for the root; Save reads fields fresh off the DOM. "gray"/manual
      // has no goal criteria but gets a textbox for the node's NAME, saved via
      // PATCH .../nodes/<id> rather than .../goal (saveSelectedNodeText).
      function renderGoalFieldsHtml(node) {
        var goal = node.goal || {};
        var type = GOAL_TYPE_BY_COLOR[node.color];
        if (!type) return '';
        if (type === 'manual') {
          return '<div class="mm-goal-fields" data-role="goal-fields">' +
            '<div class="mm-goal-target-wrap">' +
              '<input class="mm-goal-input" type="text" data-role="node-text-input" placeholder="Type something" maxlength="120" value="' + esc(node.text || '') + '">' +
            '</div>' +
            '</div>';
        }
        var fields = '';
        if (type === 'kc') {
          fields =
            renderSearchFieldHtml('sourceName', 'npc', 'Search for an NPC', goal.sourceName) +
            '<input type="hidden" data-goal-field="activityType" value="npc">' +
            '<input class="mm-goal-input" type="text" inputmode="decimal" data-goal-field="targetCount" placeholder="Target kc" value="' + esc(goal.targetCount != null ? goal.targetCount : '') + '">' +
            // Optional: counts kc only from this date on; not shown on the node
            // face (see clean_goal). A masked YYYY-MM-DD field like the Loot
            // Tracker custom range, with a hint line since the placeholder
            // vanishes once typed.
            '<div class="mm-goal-date-wrap">' +
              '<input class="mm-goal-input" type="text" data-goal-field="sinceDate" inputmode="numeric" autocomplete="off" spellcheck="false" placeholder="YYYY-MM-DD" value="' + esc(goal.sinceDate || '') + '">' +
              '<div class="mm-goal-hint">Only count kc from this date on (optional)</div>' +
            '</div>';
        } else if (type === 'item') {
          fields =
            renderSearchFieldHtml('itemName', 'item', 'Search for an item', goal.itemName) +
            '<input class="mm-goal-input" type="text" inputmode="decimal" data-goal-field="targetQty" placeholder="Target quantity" value="' + esc(goal.targetQty != null ? goal.targetQty : '') + '">';
        } else if (type === 'gp') {
          fields =
            '<input class="mm-goal-input" type="text" inputmode="decimal" data-goal-field="targetGp" placeholder="Target gp (coins + tokens)" value="' + esc(goal.targetGp != null ? goal.targetGp : '') + '">';
        } else if (type === 'skill') {
          var metric = goal.metric === 'xp' ? 'xp' : 'level';
          var targetPlaceholder = metric === 'xp' ? 'Target experience' : 'Target level';
          fields =
            '<div class="mm-goal-skill-row">' +
              renderLocalSearchFieldHtml('skill', 'skill', 'Search for a skill', goal.skill, titleCase) +
              renderSegmentedToggleHtml('metric', [['level', 'LVL'], ['xp', 'XP']], goal.metric) +
            '</div>' +
            '<div class="mm-goal-target-wrap">' +
              '<input class="mm-goal-input" type="text" inputmode="decimal" data-goal-field="target" placeholder="' + esc(targetPlaceholder) + '" value="' + esc(goal.target != null ? goal.target : '') + '">' +
            '</div>';
        } else if (type === 'quest') {
          fields = renderSearchFieldHtml('questName', 'quest', 'Search for a quest or miniquest', goal.questName);
        } else if (type === 'diary') {
          fields =
            renderLocalSearchFieldHtml('area', 'diary', 'Search for a diary', goal.area, function (a) { return DIARY_AREA_LABELS[a] || a; }) +
            renderSegmentedToggleHtml('tier', DIARY_TIERS.map(function (t) { return [t, titleCase(t)]; }), goal.tier);
        }
        return '<div class="mm-goal-fields" data-role="goal-fields">' + fields + '</div>';
      }

      function renderSharedChildPopoverHtml() {
        return '<div class="mm-node-popover" data-role="popover">' +
          '<button type="button" class="btn-secondary mm-add-shared-child-btn" data-role="add-shared-child">Add shared child</button>' +
          '</div>';
      }

      function render() {
        hideFloatingSuggestions();
        updateHistoryButtons();
        updateEditModeButton();
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

      // Mindmap switcher menu

      function closeMenu() {
        document.getElementById('mmMenu').style.display = 'none';
        var deleteBtn = document.getElementById('mmMenuDelete');
        if (deleteBtn) {
          deleteBtn.classList.remove('mm-menu-item--confirm');
          deleteBtn.textContent = 'Delete mindmap';
        }
      }
      document.getElementById('mmSwitchBtn').addEventListener('click', function () {
        commitActiveLabelIfEditing();
        var menu = document.getElementById('mmMenu');
        if (menu.style.display === 'none') { menu.style.display = 'flex'; } else { closeMenu(); }
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
            zoomToFit();
          }
          return;
        }
        if (e.target.id === 'mmMenuNew') { closeMenu(); openNameForm('new', ''); return; }
        if (e.target.id === 'mmMenuDuplicate') {
          closeMenu();
          duplicateActiveMindmap();
          return;
        }
        if (e.target.id === 'mmMenuRename') {
          closeMenu();
          var mm = activeMindmap();
          if (mm) openNameForm('rename', mm.name);
          return;
        }
        if (e.target.id === 'mmMenuDelete') {
          if (e.target.classList.contains('mm-menu-item--confirm')) {
            closeMenu();
            deleteActiveMindmap();
            return;
          }
          e.target.classList.add('mm-menu-item--confirm');
          e.target.textContent = 'Are you sure?';
          return;
        }
      });

      async function duplicateActiveMindmap() {
        var mm = activeMindmap();
        if (!mm) return;
        const data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id) + '/duplicate', { method: 'POST' });
        if (data) {
          MM.data = data;
          if (data.newMindmapId) {
            setActiveMindmapId(data.newMindmapId);
            MM.selectedNodeId = null;
          }
          render();
          zoomToFit();
        }
      }

      async function deleteActiveMindmap() {
        var mm = activeMindmap();
        if (!mm) return;
        const data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id), { method: 'DELETE' });
        if (data) {
          MM.data = data;
          MM.selectedNodeId = null;
          setActiveMindmapId(data.mindmaps.length ? data.mindmaps[0].id : null);
          render();
          zoomToFit();
        }
      }

      // New/rename mindmap form

      function openNameForm(mode, initialValue) {
        MM.nameFormMode = mode;
        var form = document.getElementById('mmNameForm');
        var input = document.getElementById('mmNameInput');
        form.style.display = 'flex';
        input.value = initialValue || '';
        input.classList.remove('invalid');
        input.focus();
      }
      document.getElementById('mmCreateFirstBtn').addEventListener('click', function () { openNameForm('new', ''); });
      document.getElementById('mmNameInput').addEventListener('input', function () {
        this.classList.remove('invalid');
      });
      document.getElementById('mmNameCancel').addEventListener('click', function () {
        document.getElementById('mmNameForm').style.display = 'none';
        document.getElementById('mmNameInput').classList.remove('invalid');
        MM.nameFormMode = null;
      });
      document.getElementById('mmNameSave').addEventListener('click', async function () {
        var nameInput = document.getElementById('mmNameInput');
        var name = (nameInput.value || '').trim();
        if (!name) { nameInput.classList.add('invalid'); return; }
        nameInput.classList.remove('invalid');
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
              zoomToFit();
            }
          }
        } else if (mode === 'rename') {
          var mm = activeMindmap();
          if (!mm) return;
          data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id), {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name }),
          });
          // Renamed the active mindmap; see resetMindmapShareState.
          if (data) { MM.data = data; resetMindmapShareState(); render(); }
        }
      });

      // Undo/redo. Each node-tree edit records the tree from just before it into
      // MM.undoStack once it succeeds, so undo swaps in a whole snapshot with no
      // per-action inverse (and deletes need no confirm).
      var MAX_HISTORY = 50;

      function updateHistoryButtons() {
        var undoBtn = document.getElementById('mmUndoBtn');
        var redoBtn = document.getElementById('mmRedoBtn');
        if (undoBtn) undoBtn.disabled = !MM.undoStack.length;
        if (redoBtn) redoBtn.disabled = !MM.redoStack.length;
      }

      function updateZoomButtons() {
        var zoomInBtn = document.getElementById('mmZoomIn');
        var zoomOutBtn = document.getElementById('mmZoomOut');
        if (zoomInBtn) zoomInBtn.disabled = MM.zoom >= MAX_ZOOM;
        if (zoomOutBtn) zoomOutBtn.disabled = MM.zoom <= MIN_ZOOM;
      }

      function updateEditModeButton() {
        var btn = document.getElementById('mmEditModeBtn');
        if (!btn) return;
        btn.classList.toggle('active', MM.editMode);
        btn.setAttribute('data-tooltip', MM.editMode ? 'Exit edit mode' : 'Enter edit mode');
      }

      // Pulses the Edit Mode button when a node body is clicked outside Edit
      // Mode. mm-glow is a fixed-iteration CSS animation; removing the class and
      // forcing a reflow restarts it.
      function glowEditModeButton() {
        var btn = document.getElementById('mmEditModeBtn');
        if (!btn) return;
        btn.classList.remove('mm-glow');
        void btn.offsetWidth;
        btn.classList.add('mm-glow');
      }

      function flipNodeNote(nodeId) {
        if (MM.flippedNodeIds.has(nodeId)) MM.flippedNodeIds.delete(nodeId);
        else MM.flippedNodeIds.add(nodeId);
        render();
      }

      function recordUndoableEdit(preNodes) {
        MM.undoStack.push(preNodes);
        if (MM.undoStack.length > MAX_HISTORY) MM.undoStack.shift();
        // A fresh edit discards the redo stack, like any undo history.
        MM.redoStack = [];
      }

      // True if the mindmap an in-flight edit was made against is still on
      // screen, so a slow response never touches another mindmap's history or
      // tree.
      function isStillActiveMindmap(mmId) {
        return MM.activeMindmapId === mmId;
      }

      async function restoreNodesSnapshot(nodes) {
        var mm = activeMindmap();
        if (!mm) return null;
        return apiCall('/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nodes: nodes }),
        });
      }

      async function undo() {
        var mm = activeMindmap();
        if (!MM.undoStack.length || !mm) return;
        var mmId = mm.id;
        var prev = MM.undoStack[MM.undoStack.length - 1];
        var preUndoNodes = mm.nodes;
        const data = await restoreNodesSnapshot(prev);
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) {
          MM.undoStack.pop();
          MM.redoStack.push(preUndoNodes);
          MM.selectedNodeId = null;
          resetMindmapShareState();
        }
        render();
      }

      async function redo() {
        var mm = activeMindmap();
        if (!MM.redoStack.length || !mm) return;
        var mmId = mm.id;
        var next = MM.redoStack[MM.redoStack.length - 1];
        var preRedoNodes = mm.nodes;
        const data = await restoreNodesSnapshot(next);
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) {
          MM.redoStack.pop();
          MM.undoStack.push(preRedoNodes);
          MM.selectedNodeId = null;
          resetMindmapShareState();
        }
        render();
      }

      // Selected-node actions

      async function updateSelectedNode(patch) {
        var mm = activeMindmap();
        var node = selectedNode();
        if (!mm || !node) return;
        var mmId = mm.id;
        var preNodes = mm.nodes;
        const data = await apiCall(
          '/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/' + encodeURIComponent(node.id),
          { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) }
        );
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) { recordUndoableEdit(preNodes); resetMindmapShareState(); }
        render();
      }

      // Replaces the selected node's goal (set_node_goal in app/mindmaps.py) via
      // PATCH .../goal, for the trackable Save button and the gray
      // manual-complete toggle. `closePopover` (Save only) deselects the node on
      // success. Takes an explicit `nodeId` because the checkbox works on any
      // gray node. `note` rides on the same request for one undo step; the
      // checkbox leaves it undefined (JSON.stringify drops the key), so ticking
      // never touches the note.
      async function saveNodeGoal(nodeId, goal, note, closePopover) {
        var mm = activeMindmap();
        var node = mm && mm.nodes.find(function (n) { return n.id === nodeId; });
        if (!mm || !node) return;
        var mmId = mm.id;
        var preNodes = mm.nodes;
        // Not the shared apiCall helper, which sends failures to the top banner.
        // A 400 here is clean_goal's "missing field" message, which belongs in
        // the popover; other failures keep the banner.
        var res, data;
        try {
          res = await fetch(
            '/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/' + encodeURIComponent(node.id) + '/goal',
            { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ goal: goal, note: note }) }
          );
          data = await res.json().catch(function () { return {}; });
        } catch (err) {
          showError('Something went wrong. Please try again.');
          return;
        }
        if (!res.ok) {
          showGoalSaveError(describeError(data, 'Something went wrong. Please try again.'));
          return;
        }
        showGoalSaveError(null);
        showError(null);
        MM.data = data;
        if (isStillActiveMindmap(mmId)) { recordUndoableEdit(preNodes); resetMindmapShareState(); }
        if (closePopover) {
          MM.selectedNodeId = null;
          MM.multiSelectIds = new Set();
        }
        render();
      }
      function saveSelectedNodeGoal(goal, note, closePopover) {
        if (!MM.selectedNodeId) return;
        return saveNodeGoal(MM.selectedNodeId, goal, note, closePopover);
      }

      // A gray (manual) node's Save commits its NAME via the plain node PATCH
      // (updateSelectedNode), not .../goal (update_node vs set_node_goal);
      // `note` goes with the text.
      async function saveSelectedNodeText(text, note, closePopover) {
        var mm = activeMindmap();
        var node = selectedNode();
        if (!mm || !node) return;
        var mmId = mm.id;
        var preNodes = mm.nodes;
        const data = await apiCall(
          '/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/' + encodeURIComponent(node.id),
          { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text, note: note }) }
        );
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) { recordUndoableEdit(preNodes); resetMindmapShareState(); }
        if (closePopover) {
          MM.selectedNodeId = null;
          MM.multiSelectIds = new Set();
        }
        render();
      }

      function commitNodeTextFromLabel(label) {
        pendingLabelCommit = null;
        var node = selectedNode();
        if (!node) return;
        var val = (label.textContent || '').trim();
        if (!val || val === node.text) { label.textContent = node.text; return; }
        pendingLabelCommit = updateSelectedNode({ text: val });
      }

      // Adds a node relative to `nodeId`, which need not be the selected one
      // (edge-hover "+" buttons). `before` only matters for "sibling"
      // (_order_before/_order_after in app/mindmaps.py).
      async function addNodeRelativeTo(nodeId, relation, before) {
        var mm = activeMindmap();
        if (!mm) return;
        var mmId = mm.id;
        var preNodes = mm.nodes;
        var body = { relative_to: nodeId, relation: relation, text: '', color: 'gray' };
        if (relation === 'sibling') body.before = !!before;
        const data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        });
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) {
          recordUndoableEdit(preNodes);
          resetMindmapShareState();
          selectNode(data.newNodeId || null);
        } else {
          render();
        }
      }

      async function deleteSelectedNode() {
        var mm = activeMindmap();
        var node = selectedNode();
        if (!mm || !node || node.parentId === null) return;
        var mmId = mm.id;
        var preNodes = mm.nodes;
        const data = await apiCall(
          '/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/' + encodeURIComponent(node.id),
          { method: 'DELETE' }
        );
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) {
          recordUndoableEdit(preNodes);
          MM.selectedNodeId = null;
          resetMindmapShareState();
        }
        render();
      }

      // Multi-select: add a shared child below several nodes

      // Adds one node as a shared CHILD of every node in MM.multiSelectIds, e.g.
      // several "blocklist" nodes feeding one "setup" node. The nodes needn't
      // share a parent or depth (add_shared_child in app/mindmaps.py); the
      // button only shows with 2+ selected.
      async function addSharedChildSelected() {
        var mm = activeMindmap();
        if (!mm || MM.multiSelectIds.size < 2) return;
        var mmId = mm.id;
        var preNodes = mm.nodes;
        const data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/shared-child', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          // Empty text, as in addNodeRelativeTo.
          body: JSON.stringify({ parent_ids: Array.from(MM.multiSelectIds), text: '', color: 'gray' }),
        });
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) {
          recordUndoableEdit(preNodes);
          resetMindmapShareState();
          selectNode(data.newNodeId || null);
        } else {
          render();
        }
      }

      // Share (export a frozen myscape.io/s/<code> link)

      // Export icon next to the title: a popup under the button
      // (.mm-share-wrap). Nothing is generated until GENERATE SHAREABLE LINK is
      // clicked. Null-guarded because render_mindmap_share strips this icon's
      // <h2>.
      var mmShareIconBtn = document.getElementById('mmShareIconBtn');
      var mmShareCard = document.getElementById('mmShareCard');
      if (mmShareIconBtn) {
        function setMmShareOpen(open) {
          mmShareCard.hidden = !open;
          mmShareIconBtn.classList.toggle('open', open);
        }
        mmShareIconBtn.addEventListener('click', function () {
          setMmShareOpen(mmShareCard.hidden);
        });
        document.addEventListener('click', function (e) {
          var wrap = document.querySelector('.mm-share-wrap');
          if (wrap && !wrap.contains(e.target)) setMmShareOpen(false);
        });
      }

      // Resets the share card when the active mindmap changes and after every
      // edit to it: build_mindmap_share_snapshot (app/mindmaps.py) freezes the
      // whole mindmap, so an edit makes an old link stale.
      function resetMindmapShareState() {
        var genBtn = document.getElementById('mmShareGenerateBtn');
        var linkBtn = document.getElementById('mmShareLinkBtn');
        if (!genBtn || !linkBtn) return;
        genBtn.hidden = false;
        genBtn.disabled = false;
        genBtn.classList.remove('action-failed');
        linkBtn.hidden = true;
        linkBtn.textContent = '';
        delete linkBtn.dataset.url;
      }

      // GENERATE SHAREABLE LINK: freezes the active mindmap into a new
      // SharedContent row, then shows mmShareLinkBtn with the link.
      // Null-guarded: an unguarded addEventListener would throw and halt this
      // IIFE before loadState(), leaving the share page on "Loading...".
      var mmShareGenerateBtn = document.getElementById('mmShareGenerateBtn');
      if (mmShareGenerateBtn) {
        mmShareGenerateBtn.addEventListener('click', function () {
          var btn = this;
          if (!MM.activeMindmapId) return;
          btn.disabled = true;
          fetch('/api/mindmaps/' + encodeURIComponent(MM.activeMindmapId) + '/share', { method: 'POST' })
            .then(function (res) { return res.ok ? res.json() : Promise.reject(); })
            .then(function (data) {
              var linkBtn = document.getElementById('mmShareLinkBtn');
              linkBtn.dataset.url = data.url;
              linkBtn.textContent = data.url;
              btn.hidden = true;
              linkBtn.hidden = false;
            })
            .catch(function () {
              btn.classList.add('action-failed');
              setTimeout(function () { btn.classList.remove('action-failed'); }, 2500);
            })
            .then(function () { btn.disabled = false; });
        });
      }

      var mmShareLinkBtn = document.getElementById('mmShareLinkBtn');
      if (mmShareLinkBtn) {
        mmShareLinkBtn.addEventListener('click', function () {
          var btn = this;
          var url = btn.dataset.url;
          if (!url) return;
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url);
          } else {
            var temp = document.createElement('textarea');
            temp.value = url;
            temp.style.position = 'fixed';
            temp.style.opacity = '0';
            document.body.appendChild(temp);
            temp.select();
            document.execCommand('copy');
            document.body.removeChild(temp);
          }
          btn.textContent = 'COPIED';
          setTimeout(function () { btn.textContent = url; }, 1200);
        });
      }

      // Boot

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
        zoomToFit();
      }

      loadState();
    })();
    """
    return extra_head, body, script


def render_mindmaps(player: PlayerView) -> str:
    """The Mindmaps page: _mindmaps_panel_markup's markup/script inside the
    _shell wrapper. render_landing_mindmap_preview embeds the same panel
    without _shell.
    """
    extra_head, body, script = _mindmaps_panel_markup()
    return _shell(
        title="Mindmaps — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )


def render_mindmap_share(share: "SharedContent", game_account: Optional["GameAccount"], viewer: Optional[PlayerView]) -> str:
    """GET /s/<code> for a Mindmap share: a read-only, frozen snapshot of the
    mindmap the owner picked (build_mindmap_share_snapshot in
    app/mindmaps.py).
    
    Reuses _mindmaps_panel_markup's body/script unmodified, with a fetch shim
    answering GET /api/mindmaps from PAYLOAD and localStorage shadowed
    (/s/<code> shares an origin with the real page). The switcher, Undo/Redo
    and Edit Mode toggle are hidden via CSS (.mindmap-share in mindmaps.css),
    not stripped, so no null guards are needed.
    
    The reused "Mindmaps" <h2> is stripped; banner_markup adds the mindmap
    name and "Shared by <name>" with an import icon. game_account may be None;
    falls back to "A player".
    """
    extra_head, body, script = _mindmaps_panel_markup()
    # Strip the reused body's "Mindmaps" <h2 class="page-title"> and its export
    # button by keeping only what follows the first "</h2>".
    _, _, body = body.partition("</h2>")

    owner_name = (game_account.runescape_name if game_account else None) or "A player"
    mindmap_name = share.payload["mindmap"]["name"]

    # Import icon next to "Shared by <name>"; same signed-in/signed-out split as
    # import_icon_btn in render_purchase_goals_share.
    import_icon_svg = (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
        '<polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line>'
        '</svg>'
    )
    if viewer is not None:
        import_icon_btn = (
            ' <span class="mm-import-wrap">'
            '<button type="button" class="mm-import-icon-btn" id="mmImportBtn" aria-label="Save to your account" title="Save to your account">'
            f'{import_icon_svg}</button>'
            '<div class="mm-import-card" id="mmImportCard" hidden>'
            '<button type="button" class="mm-import-save-btn" id="mmImportSaveBtn">SAVE TO MY MYSCAPE</button>'
            '<p class="mm-import-popup-hint">Clicking the button above will save a copy<br>of this mindmap to your Mindmaps app.</p>'
            '</div>'
            '</span>'
        )
    else:
        import_icon_btn = (
            ' <a class="mm-import-icon-btn" href="/signup" aria-label="Sign up to save this" title="Sign up to save this">'
            f'{import_icon_svg}</a>'
        )

    banner_markup = f"""
    <p class="subtitle mm-share-label">{escape(mindmap_name)}</p>
    <h2 class="page-title">Shared by {escape(owner_name)}{import_icon_btn}</h2>
    """
    body = banner_markup + body
    body = f'<div class="mindmap-share">{body}</div>'

    payload_json = json.dumps(share.payload)
    wrapper_script = f"""
    (function () {{
      var PAYLOAD = {payload_json};

      // Same-origin localStorage shadow (see the doc comment above); the
      // visitor's own preferences must not be read or overwritten.
      var localStorage = (function () {{
        var store = {{}};
        return {{
          getItem: function (k) {{ return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; }},
          setItem: function (k, v) {{ store[k] = String(v); }},
          removeItem: function (k) {{ delete store[k]; }},
        }};
      }})();

      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        var qIndex = url.indexOf('?');
        var path = qIndex === -1 ? url : url.slice(0, qIndex);

        if (path === '/api/mindmaps' && method === 'GET') {{
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{ mindmaps: [PAYLOAD.mindmap] }}); }} }});
        }}
        // Every node- and mindmap-mutation endpoint gets a graceful ok:false
        // instead of reaching the real API with the visitor's session cookie.
        // ok:false (not an empty-object success, as in Loot Tracker) is the only
        // safe catch-all here: the reused script assigns MM.data from any
        // successful response and then reads its 'mindmaps' array, so an empty
        // object would crash. Nothing should reach this in practice (Edit Mode
        // never turns on; the gray-node checkbox is locked via pointer-events:
        // none in mindmaps.css).
        return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{ detail: 'Not available on a shared link.' }}); }} }});
      }};

      {script}

      // The switcher, Undo, Redo and Edit Mode are hidden via CSS only
      // (.mindmap-share in mindmaps.css), so nothing here needs to strip them.

      // Import icon: a real <button> only when the viewer was signed in at
      // render time (null-guarded otherwise; signed out it is a plain link to
      // /signup). Toggles mmImportCard like mmShareIconBtn/mmShareCard; nothing
      // imports until mmImportSaveBtn is clicked.
      var mmImportBtn = document.getElementById('mmImportBtn');
      var mmImportCard = document.getElementById('mmImportCard');
      if (mmImportBtn) {{
        function setMmImportOpen(open) {{
          mmImportCard.hidden = !open;
          mmImportBtn.classList.toggle('open', open);
        }}
        mmImportBtn.addEventListener('click', function () {{
          setMmImportOpen(mmImportCard.hidden);
        }});
        document.addEventListener('click', function (e) {{
          var wrap = document.querySelector('.mm-import-wrap');
          if (wrap && !wrap.contains(e.target)) setMmImportOpen(false);
        }});
      }}

      // SAVE TO MY MYSCAPE -- imports THIS share's own frozen mindmap
      // into the signed-in visitor's own Mindmaps list (POST /api/
      // mindmaps/shares/{share.code}/import in app/main.py), then --
      // only once that succeeds -- navigates there so they land right
      // on it, appended at the end of their own mindmap list AND
      // already selected (see below). A failed import (expired link,
      // or this specific race: the code was still valid when the page
      // loaded but lapses before the click) leaves this card open
      // exactly as-is and flashes this button red for 2.5s, same
      // pattern as mmShareGenerateBtn's own .action-failed handling
      // above.
      //
      // IMPORTANT: this calls window.fetch/window.localStorage
      // explicitly, not the bare fetch(...)/localStorage every other
      // handler in this wrapper script uses -- the plain identifiers
      // would resolve to THIS SAME IIFE's own local shim/shadow above
      // (harmless by design against the reused panel script, see this
      // function's own doc comment), which would mean this handler's
      // own fetch call never actually reaches the real server at all,
      // and writing the newly imported mindmap's id to the SHADOWED
      // localStorage would set a key nothing outside this one page
      // load ever reads -- same bug/fix Purchase Goals' own
      // pgImportSaveBtn handler already documents for its identical
      // choice.
      var mmImportSaveBtn = document.getElementById('mmImportSaveBtn');
      if (mmImportSaveBtn) {{
        mmImportSaveBtn.addEventListener('click', function () {{
          var btn = this;
          btn.disabled = true;
          window.fetch('/api/mindmaps/shares/{share.code}/import', {{ method: 'POST' }})
            .then(function (res) {{ return res.ok ? res.json() : Promise.reject(); }})
            .then(function (data) {{
              try {{
                if (data && data.importedMindmapId) {{
                  window.localStorage.setItem('myscape:mindmaps:activeMindmapId', data.importedMindmapId);
                }}
              }} catch (e) {{ /* same best-effort posture setActiveMindmapId's own try/catch takes above -- losing the auto-select is fine, the import itself already succeeded */ }}
              window.location.href = '/dashboard/mindmaps';
            }})
            .catch(function () {{
              btn.disabled = false;
              btn.classList.add('action-failed');
              setTimeout(function () {{ btn.classList.remove('action-failed'); }}, 2500);
            }});
        }});
      }}
    }})();
    """

    return _shell(
        title=f"{owner_name}'s shared Mindmap — myscape",
        player=viewer,
        body=body,
        extra_head=extra_head,
        extra_script=wrapper_script,
        meta_description=f'{owner_name} shared their "{mindmap_name}" Mindmap on myscape.',
    )


# Location filter groups of raw storage keys (POSSESSION_STORAGE_KEYS in
# app/schemas.py); a click toggles all keys in a group, while shownQuantity
# still sums by raw key.
_POSSESSION_LOCATION_GROUPS = [
    ("BANK", ["bank", "potion_storage"]),
    ("SEED VAULT", ["seed_vault"]),
    ("PoH", ["poh"]),
    ("BOATS", ["boat_cargo"]),
    ("PORTABLE", ["looting_bag", "rune_pouch", "tackle_box", "forestry_kit", "master_scroll_book", "seed_box", "huntsmans_kit"]),
    ("CHARACTER", ["equipment", "inventory"]),
]

# Display label for every POSSESSION_STORAGE_KEYS entry, used by the
# settings-menu checkboxes. Keep in sync by hand with buildStatusStorageLabels
# in MyscapePanel.java (separate repo).
_POSSESSION_STORAGE_LABELS = {
    "bank": "Bank",
    "equipment": "Equipment",
    "inventory": "Inventory",
    "potion_storage": "Potion Storage",
    "rune_pouch": "Rune Pouch",
    "seed_vault": "Seed Vault",
    "looting_bag": "Looting Bag",
    "tackle_box": "Tackle Box",
    "poh": "PoH",
    "forestry_kit": "Forestry Kit",
    "master_scroll_book": "Master Scroll Book",
    "seed_box": "Seed Box",
    "huntsmans_kit": "Huntsman's Kit",
    "boat_cargo": "Boat Cargo",
}


def _possessions_panel_markup() -> Tuple[str, str, str]:
    """Builds Storages Viewer's (extra_head, body, script) triple, split from
    render_possessions so the landing preview can embed it without _shell.
    
    A table of everything the player owns (get_owned_breakdown in
    app/possessions.py), loaded from GET /api/possessions/summary and
    re-polled every 5 seconds. Location filters only reshape the counted
    quantity client-side (shownQuantity); the gear menu holds persisted
    storage checkboxes (HiddenPossessionStorage); pinned rows
    (PinnedPossessionItem) sit above a divider. TRADEABLE means tradeable on
    the Grand Exchange.
    """
    extra_head = f'<link rel="stylesheet" href="/static/css/possessions.css?v={_POSSESSIONS_CSS_VERSION}" />'

    location_buttons = "".join(
        # PoH keeps its mixed-case label via the pm-filter-btn-cased rule in
        # possessions.css.
        f'<button type="button" class="pm-filter-btn{" pm-filter-btn-cased" if label == "PoH" else ""} active" '
        f'data-locations="{",".join(keys)}">{escape(label)}</button>'
        for label, keys in _POSSESSION_LOCATION_GROUPS
    )

    settings_checkboxes = "".join(
        f'<label class="pm-settings-item{" pm-settings-item-cased" if key == "poh" else ""}">'
        f'<input type="checkbox" data-storage-key="{key}" checked /> {escape(label)}</label>'
        for key, label in sorted(_POSSESSION_STORAGE_LABELS.items(), key=lambda kv: kv[1].lower())
    )

    # Feather "filter" funnel glyph for the per-column filter trigger
    # (.pm-filter-icon-btn, wireFilterIcons); shared by all five headers.
    funnel_glyph = (
        '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon></svg>'
    )

    # Export icon popup, like loot-share-wrap in Loot Tracker. GENERATE
    # SHAREABLE LINK POSTs only the active location filter (state.locations) to
    # /api/possessions/share; the rest is read server-side
    # (build_possessions_share_snapshot).
    pm_share_icon_btn = (
        ' <span class="pm-share-wrap">'
        '<button type="button" class="pm-share-icon-btn" id="pmShareIconBtn" aria-label="Share a snapshot of your storages&#39; contents, with only the currently selected storages" data-tooltip="Share a snapshot of your storages&#39; contents, with only the currently selected storages">'
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
        '<polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line>'
        '</svg></button>'
        '<div class="pm-share-card" id="pmShareCard" hidden>'
        '<button type="button" class="pm-share-generate-btn" id="pmShareGenerateBtn">GENERATE SHAREABLE LINK</button>'
        '<button type="button" class="pm-share-link-btn" id="pmShareLinkBtn" data-tooltip="Click to copy" hidden></button>'
        '<p class="pm-share-popup-hint">Links are active for 30 days, but can be<br>deleted sooner on your Account page.</p>'
        '</div>'
        '</span>'
    )

    body = f"""
    <h2 class="page-title">Storages Viewer{pm_share_icon_btn}</h2>
    <div class="auth-error" id="pmError"></div>

    <section class="pm-section">
      <div class="pm-controls-row">
        <div class="pm-control-group pm-search-group">
          <input type="text" class="loot-search" id="pmSearch" placeholder="Search for an item" autocomplete="off" />
          <button type="button" class="pm-search-clear" id="pmSearchClear" style="display:none;">Clear</button>
        </div>
        <div class="pm-control-group pm-location-group">
          <div class="pm-loc-wrap" id="pmLocWrap">
            <div class="pm-loc-scroll" id="pmLocScroll">{location_buttons}</div>
            <span class="pm-scroll-arrow pm-scroll-arrow--left" aria-hidden="true"></span>
            <span class="pm-scroll-arrow pm-scroll-arrow--right" aria-hidden="true"></span>
          </div>
        </div>
        <div class="pm-control-group pm-settings-wrap">
          <button type="button" class="pm-settings-btn" id="pmSettingsBtn" data-tooltip="Toggle specific storages">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.65 6.20 L9.54 2.82 L14.46 2.82 L15.35 6.20 L18.72 5.28 L21.18 9.54 L18.70 12.00 L21.18 14.46 L18.72 18.72 L15.35 17.80 L14.46 21.18 L9.54 21.18 L8.65 17.80 L5.28 18.72 L2.82 14.46 L5.30 12.00 L2.82 9.54 L5.28 5.28 Z"></path><circle cx="12" cy="12" r="3.1"></circle></svg>
          </button>
          <div class="pm-settings-menu" id="pmSettingsMenu" style="display:none;">
            {settings_checkboxes}
          </div>
        </div>
      </div>

      <p class="pg-empty" id="pmEmpty" style="display:none;">Nothing synced yet.</p>

      <div class="pm-views-wrap" id="pmViewsWrap">
        <div class="pm-views-row" id="pmViewsRow"></div>
        <span class="pm-scroll-arrow pm-scroll-arrow--left" aria-hidden="true"></span>
        <span class="pm-scroll-arrow pm-scroll-arrow--right" aria-hidden="true"></span>
      </div>

      <div class="pm-table" id="pmTable" style="display:none;">
        <div class="pm-row pm-row-header">
          <div class="pm-col pm-col-image pm-header-cell">
            <button type="button" class="pm-sort-header" data-sort-key="alpha" data-tooltip="Sort by item name">Item<span class="pm-sort-arrow"></span></button>
            <button type="button" class="pm-filter-icon-btn" data-filter-col="alpha" data-tooltip="Filter by item name" aria-label="Filter by item name">{funnel_glyph}</button>
          </div>
          <div class="pm-col pm-col-qty pm-header-cell">
            <button type="button" class="pm-sort-header" data-sort-key="qty" data-tooltip="Sort by quantity"><span class="pm-hl-full">Quantity</span><span class="pm-hl-short">Qty</span><span class="pm-sort-arrow"></span></button>
            <button type="button" class="pm-filter-icon-btn" data-filter-col="qty" data-tooltip="Filter by quantity" aria-label="Filter by quantity">{funnel_glyph}</button>
          </div>
          <div class="pm-col pm-col-ge pm-header-cell">
            <button type="button" class="pm-sort-header" data-sort-key="ge" data-tooltip="Sort by GE value"><span class="pm-hl-full">GE Value</span><span class="pm-hl-short">GE</span><span class="pm-sort-arrow"></span></button>
            <button type="button" class="pm-filter-icon-btn" data-filter-col="ge" data-tooltip="Filter by GE value" aria-label="Filter by GE value">{funnel_glyph}</button>
          </div>
          <div class="pm-col pm-col-ha pm-header-cell">
            <button type="button" class="pm-sort-header" data-sort-key="ha" data-tooltip="Sort by HA value"><span class="pm-hl-full">HA Value</span><span class="pm-hl-short">HA</span><span class="pm-sort-arrow"></span></button>
            <button type="button" class="pm-filter-icon-btn" data-filter-col="ha" data-tooltip="Filter by HA value" aria-label="Filter by HA value">{funnel_glyph}</button>
          </div>
          <div class="pm-col pm-col-tradeable pm-header-cell">
            <button type="button" class="pm-sort-header" data-sort-key="tradeable" data-tooltip="Sort by tradability"><span class="pm-hl-full">Tradeable?</span><span class="pm-hl-short">Trade?</span><span class="pm-sort-arrow"></span></button>
            <button type="button" class="pm-filter-icon-btn" data-filter-col="tradeable" data-tooltip="Filter by tradability" aria-label="Filter by tradability">{funnel_glyph}</button>
          </div>
        </div>
        <div id="pmRows"></div>
      </div>
    </section>
    """

    script = """
    (function () {
      // Direction each column sorts in on its first click: numeric/boolean
      // columns high-to-low, name A-Z. Clicking the active header flips it.
      var SORT_DEFAULT_DIR = { alpha: 'asc', qty: 'desc', ge: 'desc', ha: 'desc', tradeable: 'desc' };

      // Touch screens show no tooltip for these controls (their popups speak for
      // themselves). Read by the shared tooltip script in _shell.
      if (!document.body.classList.contains('landing')) {
        window.myscapeTouchTooltipFilter = function (el) {
          return !(el.closest && el.closest(
            '.pm-sort-header, .pm-share-icon-btn, .pm-share-link-btn, .pm-pin-btn, .pm-filter-icon-btn, .pm-settings-btn, .pm-view-add-btn'
          ));
        };
      }

      // GE VALUE, highest first, is the default sort.
      //
      // locations/enabledStorages MUST list every key of POSSESSION_STORAGE_KEYS
      // (app/schemas.py): a missing key reads as undefined and looks like the
      // storage being off.
      var state = {
        items: [],
        search: '',
        sortKey: 'ge',
        sortDir: 'desc',
        locations: { bank: true, potion_storage: true, seed_vault: true, poh: true, boat_cargo: true, equipment: true, inventory: true, looting_bag: true, rune_pouch: true, tackle_box: true, forestry_kit: true, master_scroll_book: true, seed_box: true, huntsmans_kit: true },
        enabledStorages: { bank: true, potion_storage: true, seed_vault: true, poh: true, boat_cargo: true, equipment: true, inventory: true, looting_bag: true, rune_pouch: true, tackle_box: true, forestry_kit: true, master_scroll_book: true, seed_box: true, huntsmans_kit: true },
        filters: {},
        views: [],
        activeViewId: null,
      };

      var lastPossessionsSignature = null;

      function showError(msg) {
        var el = document.getElementById('pmError');
        if (!msg) { el.classList.remove('show'); el.textContent = ''; return; }
        el.textContent = msg;
        el.classList.add('show');
      }

      async function apiCall(url, options) {
        try {
          var res = await fetch(url, options);
          var data = await res.json().catch(function () { return {}; });
          if (!res.ok) {
            showError((data && data.detail) || 'Something went wrong. Please try again.');
            return null;
          }
          showError(null);
          return data;
        } catch (err) {
          showError('Something went wrong. Please try again.');
          return null;
        }
      }

      // Full unabbreviated numbers with comma separators, never "15k"/"1.2M".
      function fmtNum(n) {
        return Math.round(n || 0).toLocaleString('en-US');
      }

      function escapeHtml(s) {
        var div = document.createElement('div');
        div.textContent = s == null ? '' : String(s);
        return div.innerHTML;
      }

      function iconImg(src) {
        if (!src) return '<div class="pm-row-icon pm-icon-blank"></div>';
        return '<img class="pm-row-icon" src="' + src + '" alt="" loading="lazy" onerror="this.style.display=\\'none\\'" />';
      }

      // Hand-drawn drawing-pin glyph in Feather's stroke style (Feather has no
      // thumbtack). One markup for both states; .pm-pin-btn/.pinned in
      // possessions.css color it gray vs. gold via currentColor.
      var PIN_GLYPH = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 4h8"></path><path d="M9 4v6l-2 4v2h10v-2l-2-4V4"></path><path d="M12 16v5"></path></svg>';

      // Wiki-search-redirect link for item icons/names; self-contained per page
      // (cf. wikiItemUrl in Loot Tracker).
      function wikiItemUrl(name) {
        return 'https://oldschool.runescape.wiki/w/Special:Search?search=' + encodeURIComponent(name || '') + '&go=Go';
      }

      // Preloads icon URLs before swapping in HTML that references them, so a
      // rebuilt table paints with icons decoded (same as Loot Tracker's helper).
      var ICON_PRELOAD_TIMEOUT_MS = 400;
      function preloadIcons(urls) {
        var pending = urls.filter(Boolean).map(function (src) {
          return new Promise(function (resolve) {
            var img = new Image();
            img.onload = resolve;
            img.onerror = resolve;
            img.src = src;
          });
        });
        if (!pending.length) return Promise.resolve();
        return Promise.race([
          Promise.all(pending),
          new Promise(function (resolve) { setTimeout(resolve, ICON_PRELOAD_TIMEOUT_MS); }),
        ]);
      }

      // Sort (click a column header; see SORT_DEFAULT_DIR)

      var sortHeaders = document.querySelectorAll('.pm-sort-header');

      function updateSortHeaders() {
        sortHeaders.forEach(function (btn) {
          var key = btn.getAttribute('data-sort-key');
          var arrow = btn.querySelector('.pm-sort-arrow');
          if (key === state.sortKey) {
            btn.classList.add('active');
            arrow.textContent = state.sortDir === 'asc' ? ' \\u2191' : ' \\u2193';
          } else {
            btn.classList.remove('active');
            arrow.textContent = '';
          }
        });
      }

      sortHeaders.forEach(function (btn) {
        btn.addEventListener('click', function () {
          var key = btn.getAttribute('data-sort-key');
          if (key === state.sortKey) {
            state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
          } else {
            state.sortKey = key;
            state.sortDir = SORT_DEFAULT_DIR[key] || 'desc';
          }
          updateSortHeaders();
          clearActiveViewHighlight();
          renderTable();
        });
      });

      // Per-column filter popovers: the funnel is a separate click target from
      // .pm-sort-header and stops propagation, so filtering never re-sorts.

      var FILTER_COLUMNS = { alpha: 'text', qty: 'numeric', ge: 'numeric', ha: 'numeric', tradeable: 'tradeable' };
      var NUMERIC_PLACEHOLDERS = { qty: 'Quantity', ge: 'Value', ha: 'Value' };

      // Mode/operator choices are segmented controls (.pm-segment-* is this
      // page's copy of Mindmaps' recipe). Numeric operator labels are
      // pre-escaped HTML, since a raw "<"/">" would parse as a tag.
      var TEXT_MODE_OPTIONS = [['contains', 'Contains'], ['not_contains', 'Does Not Contain']];
      var NUMERIC_OP_OPTIONS = [['>', '&gt;'], ['>=', '&ge;'], ['<', '&lt;'], ['<=', '&le;'], ['=', '='], ['!=', '&ne;'], ['between', 'Between']];
      var TRADEABLE_MODE_OPTIONS = [['tradeable', 'Tradeable'], ['untradeable', 'Untradeable']];
      var STACK_MODE_OPTIONS = [['stack', 'Stack'], ['single', 'Single']];

      function segmentGroupHtml(role, options, currentValue) {
        var value = options.some(function (o) { return o[0] === currentValue; }) ? currentValue : options[0][0];
        var buttons = options.map(function (o) {
          var cls = 'pm-segment-btn' + (o[0] === value ? ' active' : '');
          return '<button type="button" class="' + cls + '" data-segment-value="' + o[0] + '">' + o[1] + '</button>';
        }).join('');
        return '<div class="pm-segment-group" data-role="' + role + '">' + buttons + '</div>';
      }

      function filterPopoverHtml(col) {
        var kind = FILTER_COLUMNS[col];
        var current = state.filters[col] || null;
        var actions = (
          '<div class="pm-filter-popover-actions">' +
          '<button type="button" class="pm-filter-clear-btn" data-action="clear">Clear</button>' +
          '<button type="button" class="pm-filter-apply-btn" data-action="apply">Apply</button>' +
          '</div>'
        );
        if (kind === 'text') {
          var mode = (current && current.mode) || 'contains';
          var text = current ? (current.text || '') : '';
          var placeholder = mode === 'not_contains' ? 'Name does not contain...' : 'Name contains...';
          return (
            segmentGroupHtml('mode', TEXT_MODE_OPTIONS, mode) +
            '<input type="text" class="pm-filter-input" data-role="text" placeholder="' + placeholder + '" value="' + escapeHtml(text) + '" />' +
            actions
          );
        }
        if (kind === 'numeric') {
          var op = (current && current.op) || '>=';
          var value = current && typeof current.value === 'number' ? current.value : '';
          var min = current && typeof current.min === 'number' ? current.min : '';
          var max = current && typeof current.max === 'number' ? current.max : '';
          var isBetween = op === 'between';
          var placeholder = NUMERIC_PLACEHOLDERS[col] || 'Value';
          var showStackToggle = (col === 'ge' || col === 'ha');
          var valueMode = showStackToggle ? ((current && current.valueMode) || 'stack') : null;
          // The Min/Max pair lives inside .pm-filter-value-row too, so toggling
          // Between only swaps which sibling is visible and the popover height
          // stays constant.
          var valueRow = (
            '<div class="pm-filter-value-row">' +
            (showStackToggle ? segmentGroupHtml('stackMode', STACK_MODE_OPTIONS, valueMode) : '') +
            '<input type="text" inputmode="decimal" class="pm-filter-input" data-role="value" placeholder="' + placeholder + '" value="' + value + '"' + (isBetween ? ' style="display:none;"' : '') + ' />' +
            '<div class="pm-filter-input-pair" data-role="between-row"' + (isBetween ? '' : ' style="display:none;"') + '>' +
            '<input type="text" inputmode="decimal" class="pm-filter-input" data-role="min" placeholder="Min" value="' + min + '" />' +
            '<span class="pm-filter-input-pair-sep">&ndash;</span>' +
            '<input type="text" inputmode="decimal" class="pm-filter-input" data-role="max" placeholder="Max" value="' + max + '" />' +
            '</div>' +
            '</div>'
          );
          return (
            segmentGroupHtml('op', NUMERIC_OP_OPTIONS, op) +
            valueRow +
            actions
          );
        }
        var mode = (current && current.mode) || 'tradeable';
        return segmentGroupHtml('mode', TRADEABLE_MODE_OPTIONS, mode) + actions;
      }

      // Numeric filter fields accept k/m/b shorthand and comma grouping, so they
      // are type="text" (a number input rejects letters). sanitizeAmountChars
      // filters while typing; parseAmount parses.
      function sanitizeAmountChars(raw) {
        return (raw || '').replace(/[^0-9.,kmbKMB]/g, '');
      }

      function parseAmount(raw) {
        if (raw === null || raw === undefined) return null;
        var s = String(raw).trim();
        if (!s) return null;
        var match = /^([0-9]*\\.?[0-9]+|[0-9]{1,3}(?:,[0-9]{3})*(?:\\.[0-9]+)?)\\s*([kKmMbB])?$/.exec(s);
        if (!match) return null;
        var numPart = match[1].replace(/,/g, '');
        var n = parseFloat(numPart);
        if (isNaN(n)) return null;
        var suffix = match[2] ? match[2].toLowerCase() : '';
        var multiplier = suffix === 'k' ? 1e3 : suffix === 'm' ? 1e6 : suffix === 'b' ? 1e9 : 1;
        return n * multiplier;
      }

      function numOrNull(input) {
        if (!input) return null;
        return parseAmount(input.value);
      }

      // Reads the open popover into the filter object matchesFilters expects;
      // null (empty or non-numeric input) means no filter on that column.
      function buildFilterFromPopover(col, popoverEl) {
        var kind = FILTER_COLUMNS[col];
        function segmentValue(role, fallback) {
          var active = popoverEl.querySelector('[data-role="' + role + '"] .pm-segment-btn.active');
          return active ? active.getAttribute('data-segment-value') : fallback;
        }
        if (kind === 'text') {
          var input = popoverEl.querySelector('[data-role="text"]');
          var text = input ? input.value.trim() : '';
          if (!text) return null;
          return { mode: segmentValue('mode', 'contains'), text: text };
        }
        if (kind === 'numeric') {
          var op = segmentValue('op', '>=');
          var valueMode = (col === 'ge' || col === 'ha') ? segmentValue('stackMode', 'stack') : null;
          if (op === 'between') {
            var min = numOrNull(popoverEl.querySelector('[data-role="min"]'));
            var max = numOrNull(popoverEl.querySelector('[data-role="max"]'));
            if (min === null || max === null) return null;
            var betweenFilter = { op: 'between', min: min, max: max };
            if (valueMode) betweenFilter.valueMode = valueMode;
            return betweenFilter;
          }
          var value = numOrNull(popoverEl.querySelector('[data-role="value"]'));
          if (value === null) return null;
          var valueFilter = { op: op, value: value };
          if (valueMode) valueFilter.valueMode = valueMode;
          return valueFilter;
        }
        return { mode: segmentValue('mode', 'tradeable') };
      }

      function wirePopoverControls(col, popoverEl) {
        // Click delegation like Mindmaps' segmented toggle: the clicked segment
        // becomes active and its siblings in the same group are cleared.
        popoverEl.querySelectorAll('.pm-segment-group').forEach(function (group) {
          group.querySelectorAll('.pm-segment-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
              group.querySelectorAll('.pm-segment-btn').forEach(function (b) { b.classList.remove('active'); });
              btn.classList.add('active');
              var value = btn.getAttribute('data-segment-value');

              if (group.getAttribute('data-role') === 'mode' && col === 'alpha') {
                var textInput = popoverEl.querySelector('[data-role="text"]');
                if (textInput) textInput.placeholder = value === 'not_contains' ? 'Name does not contain...' : 'Name contains...';
              }
              if (group.getAttribute('data-role') === 'op') {
                var valueInput = popoverEl.querySelector('[data-role="value"]');
                var betweenRow = popoverEl.querySelector('[data-role="between-row"]');
                var isBetween = value === 'between';
                if (valueInput) valueInput.style.display = isBetween ? 'none' : '';
                if (betweenRow) betweenRow.style.display = isBetween ? '' : 'none';
              }
            });
          });
        });
        // Strips anything but digits, commas, periods and k/m/b on every
        // keystroke (and paste, since 'input' fires).
        popoverEl.querySelectorAll('[data-role="value"], [data-role="min"], [data-role="max"]').forEach(function (input) {
          input.addEventListener('input', function () {
            var cleaned = sanitizeAmountChars(input.value);
            if (cleaned !== input.value) input.value = cleaned;
          });
        });
        var clearBtn = popoverEl.querySelector('[data-action="clear"]');
        if (clearBtn) clearBtn.addEventListener('click', function () {
          delete state.filters[col];
          closeAllFilterPopovers();
          clearActiveViewHighlight();
          updateFilterIconStates();
          renderTable();
        });
        var applyBtn = popoverEl.querySelector('[data-action="apply"]');
        if (applyBtn) applyBtn.addEventListener('click', function () {
          var filter = buildFilterFromPopover(col, popoverEl);
          if (filter) { state.filters[col] = filter; } else { delete state.filters[col]; }
          closeAllFilterPopovers();
          clearActiveViewHighlight();
          updateFilterIconStates();
          renderTable();
        });
        // Keep clicks inside the popover from reaching the document-level
        // outside-click closer in wireFilterIcons.
        popoverEl.addEventListener('click', function (e) { e.stopPropagation(); });
      }

      function closeAllFilterPopovers() {
        document.querySelectorAll('.pm-filter-popover').forEach(function (el) { el.remove(); });
      }

      function updateFilterIconStates() {
        document.querySelectorAll('.pm-filter-icon-btn').forEach(function (btn) {
          btn.classList.toggle('active', !!state.filters[btn.getAttribute('data-filter-col')]);
        });
      }

      function wireFilterIcons() {
        document.querySelectorAll('.pm-filter-icon-btn').forEach(function (btn) {
          btn.addEventListener('click', function (e) {
            e.stopPropagation();
            var col = btn.getAttribute('data-filter-col');
            var cell = btn.closest('.pm-header-cell');
            var alreadyOpenHere = cell.querySelector('.pm-filter-popover');
            closeAllFilterPopovers();
            if (alreadyOpenHere) return; // this button's own popover was the one open -- treat as a toggle-off
            var popover = document.createElement('div');
            popover.className = 'pm-filter-popover';
            popover.innerHTML = filterPopoverHtml(col);
            cell.appendChild(popover);
            wirePopoverControls(col, popover);
          });
        });
        document.addEventListener('click', function () { closeAllFilterPopovers(); });
      }
      wireFilterIcons();

      // Export icon popup under the button (.pm-share-wrap), closed by
      // re-clicking or clicking elsewhere. Null-guarded because
      // render_storages_share strips this <h2>.
      var pmShareIconBtn = document.getElementById('pmShareIconBtn');
      var pmShareCard = document.getElementById('pmShareCard');
      if (pmShareIconBtn) {
        function setPmShareOpen(open) {
          pmShareCard.hidden = !open;
          pmShareIconBtn.classList.toggle('open', open);
        }
        pmShareIconBtn.addEventListener('click', function () {
          setPmShareOpen(pmShareCard.hidden);
        });
        document.addEventListener('click', function (e) {
          var wrap = document.querySelector('.pm-share-wrap');
          if (wrap && !wrap.contains(e.target)) setPmShareOpen(false);
        });
      }

      // Resets the share card when the possessions, hidden storages or shown
      // location groups change. Not called for search/sort/column filters/pins.
      function resetPossessionsShareState() {
        var genBtn = document.getElementById('pmShareGenerateBtn');
        var linkBtn = document.getElementById('pmShareLinkBtn');
        if (!genBtn || !linkBtn) return;
        genBtn.hidden = false;
        genBtn.disabled = false;
        genBtn.classList.remove('action-failed');
        linkBtn.hidden = true;
        linkBtn.textContent = '';
        delete linkBtn.dataset.url;
      }

      // GENERATE SHAREABLE LINK: freezes a snapshot of everything owned
      // (build_possessions_share_snapshot), sending only the active location
      // groups. Null-guarded on the share page, where an unguarded listener
      // would halt the IIFE.
      var pmShareGenerateBtn = document.getElementById('pmShareGenerateBtn');
      if (pmShareGenerateBtn) {
        pmShareGenerateBtn.addEventListener('click', function () {
          var btn = this;
          btn.disabled = true;
          var activeLocations = Object.keys(state.locations).filter(function (k) { return state.locations[k]; });
          fetch('/api/possessions/share', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ locations: activeLocations }),
          })
            .then(function (res) { return res.ok ? res.json() : Promise.reject(); })
            .then(function (data) {
              var linkBtn = document.getElementById('pmShareLinkBtn');
              linkBtn.dataset.url = data.url;
              linkBtn.textContent = data.url;
              btn.hidden = true;
              linkBtn.hidden = false;
            })
            .catch(function () {
              btn.classList.add('action-failed');
              setTimeout(function () { btn.classList.remove('action-failed'); }, 2500);
            })
            .then(function () { btn.disabled = false; });
        });
      }

      var pmShareLinkBtn = document.getElementById('pmShareLinkBtn');
      if (pmShareLinkBtn) {
        pmShareLinkBtn.addEventListener('click', function () {
          var btn = this;
          var url = btn.dataset.url;
          if (!url) return;
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url);
          } else {
            var temp = document.createElement('textarea');
            temp.value = url;
            temp.style.position = 'fixed';
            temp.style.opacity = '0';
            document.body.appendChild(temp);
            temp.select();
            document.execCommand('copy');
            document.body.removeChild(temp);
          }
          btn.textContent = 'COPIED';
          setTimeout(function () { btn.textContent = url; }, 1200);
        });
      }

      // Locations (multi-select groups, all on by default)
      // A click turns a whole group (data-locations, comma-separated raw keys)
      // off if every key is on, otherwise on.

      document.querySelectorAll('.pm-filter-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var keys = btn.getAttribute('data-locations').split(',');
          var allActive = keys.every(function (k) { return state.locations[k]; });
          var next = !allActive;
          keys.forEach(function (k) { state.locations[k] = next; });
          btn.classList.toggle('active', next);
          // Active location groups go into the share request body
          // (resetPossessionsShareState) and a saved view's config, so a hand
          // click clears the active view highlight.
          resetPossessionsShareState();
          clearActiveViewHighlight();
          renderTable();
        });
      });

      function updateLocationButtonStates() {
        document.querySelectorAll('.pm-filter-btn').forEach(function (btn) {
          var keys = btn.getAttribute('data-locations').split(',');
          var allActive = keys.every(function (k) { return state.locations[k]; });
          btn.classList.toggle('active', allActive);
        });
      }

      // Settings (per-storage on/off, persisted server-side): gear menu
      // checkboxes backed by HiddenPossessionStorage, reconciled on every
      // loadSummary poll (applyHiddenStorageKeys); toggles post/delete
      // immediately.

      var pmSettingsBtn = document.getElementById('pmSettingsBtn');
      var pmSettingsMenu = document.getElementById('pmSettingsMenu');

      // Gold border/icon while open (same .active as .pm-filter-btn.active);
      // kept in sync on every path that closes the menu.
      function setSettingsMenuOpen(open) {
        pmSettingsMenu.style.display = open ? 'flex' : 'none';
        pmSettingsBtn.classList.toggle('active', open);
      }

      pmSettingsBtn.addEventListener('click', function () {
        setSettingsMenuOpen(pmSettingsMenu.style.display === 'none');
      });
      document.addEventListener('click', function (e) {
        var wrap = document.querySelector('.pm-settings-wrap');
        if (wrap && !wrap.contains(e.target)) setSettingsMenuOpen(false);
      });

      // A location button disappears once every key it covers is off; the search
      // box (flex: 1 1 220px in possessions.css) grows to fill the space.
      function updateFilterButtonVisibility() {
        document.querySelectorAll('.pm-filter-btn').forEach(function (btn) {
          var keys = btn.getAttribute('data-locations').split(',');
          var anyEnabled = keys.some(function (k) { return state.enabledStorages[k]; });
          btn.style.display = anyEnabled ? '' : 'none';
        });
      }

      function applyHiddenStorageKeys(hiddenKeys) {
        var hidden = {};
        (hiddenKeys || []).forEach(function (k) { hidden[k] = true; });
        Object.keys(state.enabledStorages).forEach(function (k) {
          state.enabledStorages[k] = !hidden[k];
        });
        document.querySelectorAll('.pm-settings-item input[type="checkbox"]').forEach(function (cb) {
          cb.checked = !!state.enabledStorages[cb.getAttribute('data-storage-key')];
        });
        updateFilterButtonVisibility();
      }

      document.querySelectorAll('.pm-settings-item input[type="checkbox"]').forEach(function (cb) {
        cb.addEventListener('change', async function () {
          var key = cb.getAttribute('data-storage-key');
          var enable = cb.checked;
          var data = await apiCall('/api/possessions/hidden-storages/' + key, { method: enable ? 'DELETE' : 'POST' });
          if (!data) { cb.checked = !enable; return; }
          applyHiddenStorageKeys(data.hiddenStorageKeys);
          // Hidden storages are read fresh at GENERATE SHAREABLE LINK time too,
          // so reset the share state.
          resetPossessionsShareState();
          renderTable();
        });
      });

      // Search + CLEAR button (shown only while the field has text)

      var pmSearchInput = document.getElementById('pmSearch');
      var pmSearchClear = document.getElementById('pmSearchClear');

      function updateSearchClear() {
        pmSearchClear.style.display = pmSearchInput.value ? '' : 'none';
      }

      pmSearchInput.addEventListener('input', function (e) {
        state.search = e.target.value;
        updateSearchClear();
        renderTable();
      });

      pmSearchClear.addEventListener('click', function () {
        pmSearchInput.value = '';
        state.search = '';
        updateSearchClear();
        renderTable();
        // On touch screens CLEAR also drops focus to close the on-screen
        // keyboard; with a mouse the box stays focused.
        if (window.matchMedia('(hover: none)').matches) pmSearchInput.blur();
        else pmSearchInput.focus();
      });

      // Table

      function shownQuantity(item) {
        var total = 0;
        for (var key in item.byLocation) {
          if (state.locations[key] && state.enabledStorages[key]) total += item.byLocation[key];
        }
        return total;
      }

      // Per-column filters (funnel icon beside each header, see wireFilterIcons)

      function numericMatch(value, filter) {
        if (filter.op === 'between') {
          var lo = Math.min(filter.min, filter.max);
          var hi = Math.max(filter.min, filter.max);
          return value >= lo && value <= hi;
        }
        switch (filter.op) {
          case '>': return value > filter.value;
          case '>=': return value >= filter.value;
          case '<': return value < filter.value;
          case '<=': return value <= filter.value;
          case '=': return value === filter.value;
          case '!=': return value !== filter.value;
          default: return true;
        }
      }

      // A row must pass ALL active column filters; columns with no filter are
      // skipped.
      function matchesFilters(item, qty) {
        var f = state.filters;
        if (f.alpha) {
          var needle = (f.alpha.text || '').toLowerCase();
          var hit = needle ? item.name.toLowerCase().indexOf(needle) !== -1 : true;
          if (f.alpha.mode === 'not_contains') hit = !hit;
          if (!hit) return false;
        }
        if (f.qty && !numericMatch(qty, f.qty)) return false;
        // GE/HA compare against the stack total (default) or the single price
        // per the filter's Stack/Single toggle; a missing valueMode counts as
        // 'stack'.
        if (f.ge) {
          var geValue = f.ge.valueMode === 'single' ? (item.gePrice || 0) : (item.gePrice || 0) * qty;
          if (!numericMatch(geValue, f.ge)) return false;
        }
        if (f.ha) {
          var haValue = f.ha.valueMode === 'single' ? (item.highAlch || 0) : (item.highAlch || 0) * qty;
          if (!numericMatch(haValue, f.ha)) return false;
        }
        if (f.tradeable) {
          var wantTradeable = f.tradeable.mode === 'tradeable';
          if (!!item.tradeable !== wantTradeable) return false;
        }
        return true;
      }

      function visibleRows() {
        var q = state.search.toLowerCase();
        var out = [];
        for (var i = 0; i < state.items.length; i++) {
          var item = state.items[i];
          var qty = shownQuantity(item);
          if (qty <= 0) continue;
          if (q && item.name.toLowerCase().indexOf(q) === -1) continue;
          if (!matchesFilters(item, qty)) continue;
          out.push({ item: item, qty: qty });
        }
        out.sort(function (a, b) {
          var ascResult;
          if (state.sortKey === 'alpha') {
            ascResult = a.item.name.localeCompare(b.item.name);
          } else if (state.sortKey === 'ge') {
            ascResult = ((a.item.gePrice || 0) * a.qty) - ((b.item.gePrice || 0) * b.qty);
          } else if (state.sortKey === 'ha') {
            ascResult = ((a.item.highAlch || 0) * a.qty) - ((b.item.highAlch || 0) * b.qty);
          } else if (state.sortKey === 'tradeable') {
            ascResult = (a.item.tradeable ? 1 : 0) - (b.item.tradeable ? 1 : 0);
          } else {
            ascResult = a.qty - b.qty;
          }
          return state.sortDir === 'asc' ? ascResult : -ascResult;
        });
        return out;
      }

      // Splits the sorted/filtered rows into pinned and the rest, each keeping
      // the column sort order. renderTable shows pinned first, then a divider.
      function visibleRowGroups() {
        var rows = visibleRows();
        var pinned = [];
        var rest = [];
        for (var i = 0; i < rows.length; i++) {
          (rows[i].item.pinned ? pinned : rest).push(rows[i]);
        }
        return { pinned: pinned, rest: rest };
      }

      // Two lines per value cell: the stack's worth ("N gp") and, when qty > 1,
      // one unit's ("N ea"); an em dash with no price. The "each" div is omitted
      // otherwise so the line centers.
      //
      // `derived` (GE, item.geDerived) marks a value computed from a linked item
      // (derived_price_for in app/purchase_goals.py), shown with a leading "~"
      // in its own span that pm-derived-mark lowers, since the pixel font draws
      // "~" high.
      function valueCell(unitValue, qty, derived) {
        if (unitValue == null) {
          return '<div class="pm-value-cell">' +
            '<div class="pm-value-stack pm-value-none">&mdash;</div>' +
          '</div>';
        }
        var eachText = qty > 1 ? (fmtNum(unitValue) + ' ea') : '';
        var prefix = derived ? '<span class="pm-derived-mark">~</span>' : '';
        var eachHtml = eachText ? ('<div class="pm-value-each">' + prefix + eachText + '</div>') : '';
        return '<div class="pm-value-cell">' +
          '<div class="pm-value-stack">' + prefix + fmtNum(unitValue * qty) + ' gp</div>' +
          eachHtml +
        '</div>';
      }

      // The row is an <a>; the pin button is its SIBLING inside .pm-row-wrap,
      // since a <button> inside an <a> is invalid HTML and a click then never
      // triggers the link.
      function rowHtml(v) {
        var item = v.item;
        var tradeableCls = item.tradeable ? 'pm-badge-yes' : 'pm-badge-no';
        var tradeableText = item.tradeable ? 'YES' : 'NO';
        var pinCls = 'pm-pin-btn' + (item.pinned ? ' pinned' : '');
        var pinLabel = item.pinned ? 'Unpin this item' : 'Pin this item';
        return '<div class="pm-row-wrap">' +
          '<button type="button" class="' + pinCls + '" data-item-id="' + item.itemId + '" data-pinned="' + (item.pinned ? '1' : '0') + '" data-tooltip="' + pinLabel + '" aria-label="' + pinLabel + '">' + PIN_GLYPH + '</button>' +
          '<a class="pm-row" href="' + wikiItemUrl(item.name) + '" target="_blank" rel="noopener">' +
            '<div class="pm-col pm-col-image">' + iconImg(item.icon) +
              '<span class="pm-row-name">' + escapeHtml(item.name) + '</span></div>' +
            '<div class="pm-col pm-col-qty">x' + fmtNum(v.qty) + '</div>' +
            '<div class="pm-col pm-col-ge">' + valueCell(item.gePrice, v.qty, item.geDerived) + '</div>' +
            '<div class="pm-col pm-col-ha">' + valueCell(item.highAlch, v.qty) + '</div>' +
            '<div class="pm-col pm-col-tradeable"><span class="pm-badge ' + tradeableCls + '">' + tradeableText + '</span></div>' +
          '</a>' +
        '</div>';
      }

      // Rebuild rows only when the visible set/order changed (dedup key below);
      // otherwise patch text in place so icons do not flicker. lastPmRowRefs
      // caches each row's child elements so patch polls skip repeated
      // querySelector calls.
      var lastPmKey = null;
      var lastPmRowRefs = [];
      var pmTableRenderToken = 0;

      function renderTable() {
        var table = document.getElementById('pmTable');
        var rowsEl = document.getElementById('pmRows');
        var empty = document.getElementById('pmEmpty');

        if (!state.items.length) {
          table.style.display = 'none';
          empty.textContent = 'Nothing synced yet.';
          empty.style.display = '';
          lastPmKey = null;
          lastPmRowRefs = [];
          pmTableRenderToken++;
          return;
        }

        var groups = visibleRowGroups();
        var visible = groups.pinned.concat(groups.rest);
        if (!visible.length) {
          table.style.display = 'none';
          empty.textContent = 'No items match your search/filters.';
          empty.style.display = '';
          lastPmKey = null;
          lastPmRowRefs = [];
          pmTableRenderToken++;
          return;
        }

        empty.style.display = 'none';
        table.style.display = '';

        var activeLocations = Object.keys(state.locations).filter(function (k) { return state.locations[k]; }).sort().join(',');
        // pinnedKey forces a rebuild on a pin toggle even when no row position
        // changes (single visible item).
        var pinnedKey = groups.pinned.map(function (v) { return v.item.itemId; }).join(',');
        // filterKey: a filter change can alter the visible set without changing
        // the sorted id sequence, so it is part of the key.
        var filterKey = JSON.stringify(state.filters);
        var key = state.sortKey + '\\u0001' + state.sortDir + '\\u0001' + state.search + '\\u0001' + activeLocations + '\\u0001' + pinnedKey + '\\u0001' + filterKey + '\\u0001' +
          visible.map(function (v) { return v.item.itemId; }).join('|');

        if (key !== lastPmKey) {
          var html = groups.pinned.map(rowHtml).join('') +
            (groups.pinned.length && groups.rest.length ? '<div class="pm-pinned-divider"></div>' : '') +
            groups.rest.map(rowHtml).join('');
          var token = ++pmTableRenderToken;
          preloadIcons(visible.map(function (v) { return v.item.icon; })).then(function () {
            if (token !== pmTableRenderToken) return;
            lastPmKey = key;
            rowsEl.innerHTML = html;
            var rowEls = rowsEl.querySelectorAll('.pm-row-wrap');
            lastPmRowRefs = Array.prototype.map.call(rowEls, function (row) {
              return {
                link: row.querySelector('.pm-row'),
                qtyEl: row.querySelector('.pm-col-qty'),
                geEl: row.querySelector('.pm-col-ge'),
                haEl: row.querySelector('.pm-col-ha'),
                badge: row.querySelector('.pm-badge'),
              };
            });
          });
          return;
        }

        // Same item set/order/pin state: keep the rows and icons but refresh the
        // quantity/value/tradeable text in place.
        visible.forEach(function (v, i) {
          var refs = lastPmRowRefs[i];
          if (!refs) return;
          var item = v.item;
          if (refs.qtyEl) refs.qtyEl.textContent = 'x' + fmtNum(v.qty);
          if (refs.geEl) refs.geEl.innerHTML = valueCell(item.gePrice, v.qty, item.geDerived);
          if (refs.haEl) refs.haEl.innerHTML = valueCell(item.highAlch, v.qty);
          if (refs.badge) {
            refs.badge.className = 'pm-badge ' + (item.tradeable ? 'pm-badge-yes' : 'pm-badge-no');
            refs.badge.textContent = item.tradeable ? 'YES' : 'NO';
          }
        });
      }

      function possessionsSnapshotSignature(items) {
        return JSON.stringify(
          (items || [])
            .map(function (it) { return [it.itemId, it.byLocation]; })
            .sort(function (a, b) { return a[0] - b[0]; })
        );
      }

      async function loadSummary() {
        var data = await apiCall('/api/possessions/summary');
        if (!data) return;
        // A generated share link freezes the possessions at click time
        // (build_possessions_share_snapshot), so a poll that sees different
        // possessions invalidates it. See resetPossessionsShareState for the
        // location-filter/hidden-storage side.
        var signature = possessionsSnapshotSignature(data.items);
        if (lastPossessionsSignature !== null && signature !== lastPossessionsSignature) {
          resetPossessionsShareState();
        }
        lastPossessionsSignature = signature;
        state.items = data.items || [];
        applyHiddenStorageKeys(data.hiddenStorageKeys);
        renderTable();
      }

      async function setPinned(itemId, pinned) {
        var data = await apiCall(
          '/api/possessions/pins/' + itemId,
          { method: pinned ? 'POST' : 'DELETE' }
        );
        if (!data) return;
        var pinnedIds = {};
        (data.pinnedItemIds || []).forEach(function (id) { pinnedIds[id] = true; });
        state.items.forEach(function (item) { item.pinned = !!pinnedIds[item.itemId]; });
        renderTable();
      }

      // One delegated listener on the rows container, since rows are replaced
      // wholesale on rebuild.
      document.getElementById('pmRows').addEventListener('click', function (e) {
        var btn = e.target.closest('.pm-pin-btn');
        if (!btn) return;
        var itemId = Number(btn.getAttribute('data-item-id'));
        var currentlyPinned = btn.getAttribute('data-pinned') === '1';
        setPinned(itemId, !currentlyPinned);
      });

      // Saved views (named, reorderable, server-persisted; PossessionView in
      // app/models.py)
      // state.enabledStorages stays account-wide. state.activeViewId is cleared
      // on any manual sort/filter/location change (clearActiveViewHighlight).

      var viewDragSuppressClick = false;

      function currentConfigSnapshot() {
        return { sortKey: state.sortKey, sortDir: state.sortDir, filters: state.filters, locations: state.locations };
      }

      function clearActiveViewHighlight() {
        if (state.activeViewId === null) return;
        state.activeViewId = null;
        renderViewsRow();
      }

      function applyView(view) {
        var config = view.config || {};
        state.sortKey = config.sortKey || 'ge';
        state.sortDir = config.sortDir || 'desc';
        state.filters = config.filters || {};
        var savedLocations = config.locations || null;
        Object.keys(state.locations).forEach(function (k) {
          state.locations[k] = savedLocations ? !!savedLocations[k] : true;
        });
        state.activeViewId = view.id;
        updateSortHeaders();
        updateFilterIconStates();
        updateLocationButtonStates();
        renderViewsRow();
        renderTable();
      }

      function openSaveViewPopover() {
        closeAllFilterPopovers();
        var row = document.getElementById('pmViewsWrap');
        var existing = row.querySelector('.pm-view-save-popover');
        if (existing) { existing.remove(); return; }
        var popover = document.createElement('div');
        popover.className = 'pm-view-save-popover';
        popover.innerHTML = (
          '<div class="pm-filter-popover-label">Save current filters &amp; sort as</div>' +
          '<input type="text" class="pm-filter-input" data-role="view-name" placeholder="View name" />' +
          '<div class="pm-filter-popover-actions">' +
          '<button type="button" class="pm-filter-clear-btn pm-view-cancel-btn" data-action="cancel">Cancel</button>' +
          '<button type="button" class="pm-filter-apply-btn" data-action="save">Save</button>' +
          '</div>'
        );
        row.appendChild(popover);
        popover.addEventListener('click', function (e) { e.stopPropagation(); });
        var input = popover.querySelector('[data-role="view-name"]');
        input.focus();
        popover.querySelector('[data-action="cancel"]').addEventListener('click', function () { popover.remove(); });
        popover.querySelector('[data-action="save"]').addEventListener('click', async function () {
          var name = input.value.trim();
          if (!name) { input.focus(); return; }
          var data = await apiCall('/api/possessions/views', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, config: currentConfigSnapshot() }),
          });
          popover.remove();
          if (!data) return;
          state.views = data.views || [];
          // A new view always sorts last (next_possession_view_sort_order in
          // app/possessions.py), so the array's last entry is the one just
          // created.
          var saved = state.views[state.views.length - 1];
          if (saved) state.activeViewId = saved.id;
          renderViewsRow();
        });
        input.addEventListener('keydown', function (e) {
          if (e.key === 'Enter') popover.querySelector('[data-action="save"]').click();
        });
      }
      document.addEventListener('click', function () {
        var existing = document.querySelector('.pm-view-save-popover');
        if (existing) existing.remove();
      });

      function renderViewsRow() {
        var row = document.getElementById('pmViewsRow');
        row.innerHTML = state.views.map(function (v) {
          var active = v.id === state.activeViewId ? ' active' : '';
          return (
            '<button type="button" class="pm-view-chip' + active + '" data-view-id="' + v.id + '" draggable="true">' +
            '<span class="pm-view-chip-name">' + escapeHtml(v.name) + '</span>' +
            '<span class="pm-view-delete" data-view-delete="' + v.id + '" data-tooltip="Delete" aria-label="Delete this view">&times;</span>' +
            '</button>'
          );
        }).join('') + '<button type="button" class="pm-view-add-btn" id="pmViewAddBtn" data-tooltip="Save current categories, filters, and sorts">+ Save View</button>';

        row.querySelectorAll('.pm-view-chip').forEach(function (chip) {
          chip.addEventListener('click', function (e) {
            if (e.target.closest('.pm-view-delete')) return;
            if (viewDragSuppressClick) { viewDragSuppressClick = false; return; }
            var id = chip.getAttribute('data-view-id');
            if (id === state.activeViewId) {
              // Clicking the active chip again deselects it and returns to the
              // page defaults.
              state.sortKey = 'ge'; state.sortDir = 'desc'; state.filters = {}; state.activeViewId = null;
              Object.keys(state.locations).forEach(function (k) { state.locations[k] = true; });
              updateSortHeaders(); updateFilterIconStates(); updateLocationButtonStates(); renderViewsRow(); renderTable();
              return;
            }
            var view = state.views.filter(function (v) { return v.id === id; })[0];
            if (view) applyView(view);
          });
        });
        row.querySelectorAll('[data-view-delete]').forEach(function (btn) {
          btn.addEventListener('click', async function (e) {
            e.stopPropagation();
            var id = btn.getAttribute('data-view-delete');
            var data = await apiCall('/api/possessions/views/' + id, { method: 'DELETE' });
            if (!data) return;
            state.views = data.views || [];
            if (state.activeViewId === id) state.activeViewId = null;
            renderViewsRow();
          });
        });
        var addBtn = document.getElementById('pmViewAddBtn');
        if (addBtn) addBtn.addEventListener('click', function (e) {
          e.stopPropagation();
          openSaveViewPopover();
        });

        wireViewChipDrag(row);
      }

      function wireViewChipDrag(row) {
        var draggedEl = null;
        var dropped = false;

        function chipKey(btn) { return btn.getAttribute('data-view-id'); }

        function animateReorder(mutate) {
          var chips = Array.prototype.slice.call(row.querySelectorAll('.pm-view-chip'));
          var firstRects = {};
          chips.forEach(function (c) { firstRects[chipKey(c)] = c.getBoundingClientRect(); });

          mutate();

          chips.forEach(function (c) {
            if (c === draggedEl) return;
            var first = firstRects[chipKey(c)];
            var last = c.getBoundingClientRect();
            var dx = first.left - last.left;
            var dy = first.top - last.top;
            if (!dx && !dy) return;
            c.style.transition = 'none';
            c.style.transform = 'translate(' + dx + 'px,' + dy + 'px)';
            c.getBoundingClientRect();
            c.style.transition = 'transform 150ms ease';
            c.style.transform = '';
            c.addEventListener('transitionend', function handler() {
              c.style.transition = '';
              c.removeEventListener('transitionend', handler);
            });
          });
        }

        async function commitDomOrder() {
          var order = Array.prototype.slice.call(row.querySelectorAll('.pm-view-chip')).map(function (c) {
            return c.getAttribute('data-view-id');
          });
          var data = await apiCall('/api/possessions/views/order', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order: order }),
          });
          if (data) { state.views = data.views || []; renderViewsRow(); }
        }

        row.querySelectorAll('.pm-view-chip').forEach(function (chip) {
          chip.addEventListener('dragstart', function (e) {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', chip.getAttribute('data-view-id'));
            draggedEl = chip;
            dropped = false;
            chip.classList.add('dragging');
          });
          chip.addEventListener('dragend', function () {
            chip.classList.remove('dragging');
            draggedEl = null;
            viewDragSuppressClick = true;
            if (!dropped) renderViewsRow();
          });
          chip.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            if (!draggedEl || draggedEl === chip) return;
            var rect = chip.getBoundingClientRect();
            var before = e.clientX < rect.left + rect.width / 2;
            var alreadyBefore = chip.previousElementSibling === draggedEl;
            var alreadyAfter = chip.nextElementSibling === draggedEl;
            if (before ? alreadyBefore : alreadyAfter) return;
            animateReorder(function () {
              row.insertBefore(draggedEl, before ? chip : chip.nextSibling);
            });
          });
          chip.addEventListener('drop', function (e) {
            e.preventDefault();
            dropped = true;
            commitDomOrder();
          });
        });
      }

      async function loadViews() {
        var data = await apiCall('/api/possessions/views');
        if (!data) return;
        state.views = data.views || [];
        renderViewsRow();
      }

      function wireScrollCue(wrap, scroller) {
        if (!wrap || !scroller) return;
        function update() {
          var max = scroller.scrollWidth - scroller.clientWidth;
          wrap.classList.toggle('can-scroll-left', scroller.scrollLeft > 2);
          wrap.classList.toggle('can-scroll-right', scroller.scrollLeft < max - 2);
        }
        scroller.addEventListener('scroll', update, { passive: true });
        window.addEventListener('resize', update);
        if (window.ResizeObserver) new ResizeObserver(update).observe(scroller);
        if (window.MutationObserver) {
          new MutationObserver(update).observe(scroller, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class'] });
        }
        setTimeout(update, 0);
        setTimeout(update, 400);
      }
      wireScrollCue(document.getElementById('pmLocWrap'), document.getElementById('pmLocScroll'));
      wireScrollCue(document.getElementById('pmViewsWrap'), document.getElementById('pmViewsRow'));

      updateSortHeaders();
      updateFilterIconStates();
      loadSummary();
      loadViews();
      setInterval(loadSummary, 5000);
    })();
    """
    return extra_head, body, script


def render_landing_storages_preview() -> Optional[Tuple[str, str, str]]:
    """The landing page's Storages Viewer preview: _possessions_panel_markup's
    body/script plus a wrapper script, backed by
    app/data/landing_storages_demo.json (see _get_landing_storages_demo_data).
    Returns (extra_head, body, script), or None if the snapshot is missing.
    
    A fetch shim local to the wrapper IIFE serves everything in memory
    (DEMO_PINNED_IDS, DEMO_HIDDEN_KEYS, DEMO_VIEWS); anything else fails
    harmlessly.
    """
    demo = _get_landing_storages_demo_data()
    if demo is None:
        return None
    extra_head, body, script = _possessions_panel_markup()

    hero_markup = """
    <div class="storages-preview-hero">
      <picture class="storages-preview-char">
        <source srcset="/static/img/landing-storages-preview-char.webp" type="image/webp">
        <img src="/static/img/landing-storages-preview-char.png" alt="" />
      </picture>
      <div class="storages-preview-tagline-wrap">
        <p class="storages-preview-tagline">
          <span class="storages-preview-tagline-gold">STORAGES VIEWING</span> <span class="storages-preview-tagline-white">to keep track of everything you own.</span>
        </p>
      </div>
    </div>
    """
    body = hero_markup + body

    items_json = json.dumps(demo.get("items") or [])
    hidden_keys_json = json.dumps(demo.get("hiddenStorageKeys") or [])
    wrapper_script = f"""
    (function () {{
      // The captured PoH-free snapshot (see _get_landing_storages_demo_data):
      // items shaped like the real summary response's `items`.
      var DEMO_ITEMS = {items_json};
      // Working, mutable copies (not re-derived from DEMO_ITEMS on each read),
      // so a pin or settings toggle survives the 5-second re-poll.
      var DEMO_PINNED_IDS = new Set(DEMO_ITEMS.filter(function (i) {{ return i.pinned; }}).map(function (i) {{ return i.itemId; }}));
      var DEMO_HIDDEN_KEYS = new Set({hidden_keys_json});
      var DEMO_VIEWS = [];

      function newViewId() {{
        if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {{
          var r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
          return v.toString(16);
        }});
      }}

      function currentSummary() {{
        return {{
          items: DEMO_ITEMS.map(function (item) {{
            return Object.assign({{}}, item, {{ pinned: DEMO_PINNED_IDS.has(item.itemId) }});
          }}),
          hiddenStorageKeys: Array.from(DEMO_HIDDEN_KEYS),
        }};
      }}

      // fetch shim
      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        function ok(data) {{ return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(data); }} }}); }}
        function fail(detail) {{ return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{ detail: detail }}); }} }}); }}

        if (url === '/api/possessions/summary' && method === 'GET') {{
          return ok(currentSummary());
        }}

        if (url.indexOf('/api/possessions/pins/') === 0) {{
          var itemId = Number(decodeURIComponent(url.slice('/api/possessions/pins/'.length)));
          if (method === 'POST') DEMO_PINNED_IDS.add(itemId);
          else if (method === 'DELETE') DEMO_PINNED_IDS.delete(itemId);
          else return fail('Not available in this preview.');
          return ok({{ pinnedItemIds: Array.from(DEMO_PINNED_IDS) }});
        }}

        if (url.indexOf('/api/possessions/hidden-storages/') === 0) {{
          var key = decodeURIComponent(url.slice('/api/possessions/hidden-storages/'.length));
          if (method === 'POST') DEMO_HIDDEN_KEYS.add(key);
          else if (method === 'DELETE') DEMO_HIDDEN_KEYS.delete(key);
          else return fail('Not available in this preview.');
          return ok({{ hiddenStorageKeys: Array.from(DEMO_HIDDEN_KEYS) }});
        }}

        if (url === '/api/possessions/views' && method === 'GET') {{
          return ok({{ views: DEMO_VIEWS }});
        }}
        if (url === '/api/possessions/views' && method === 'POST') {{
          var body = {{}};
          try {{ body = opts.body ? JSON.parse(opts.body) : {{}}; }} catch (e) {{ body = {{}}; }}
          var name = String(body.name == null ? '' : body.name).trim().slice(0, 80);
          if (!name) return fail("A view needs a name.");
          DEMO_VIEWS.push({{ id: newViewId(), name: name, config: body.config || {{}} }});
          return ok({{ views: DEMO_VIEWS }});
        }}
        if (url === '/api/possessions/views/order' && method === 'PUT') {{
          var orderBody = {{}};
          try {{ orderBody = opts.body ? JSON.parse(opts.body) : {{}}; }} catch (e) {{ orderBody = {{}}; }}
          var order = orderBody.order || [];
          var byId = {{}};
          DEMO_VIEWS.forEach(function (v) {{ byId[v.id] = v; }});
          var reordered = order.map(function (id) {{ return byId[id]; }}).filter(Boolean);
          // Views missing from the given order stay appended at the end rather
          // than vanishing.
          DEMO_VIEWS.forEach(function (v) {{ if (order.indexOf(v.id) === -1) reordered.push(v); }});
          DEMO_VIEWS = reordered;
          return ok({{ views: DEMO_VIEWS }});
        }}
        if (url.indexOf('/api/possessions/views/') === 0 && method === 'DELETE') {{
          var delId = decodeURIComponent(url.slice('/api/possessions/views/'.length));
          DEMO_VIEWS = DEMO_VIEWS.filter(function (v) {{ return v.id !== delId; }});
          return ok({{ views: DEMO_VIEWS }});
        }}

        // View rename (PATCH /api/possessions/views/<id>), which the reused
        // script never calls, and anything else: a graceful failure, never the
        // real network.
        return fail('Not available in this preview.');
      }};

      {script}

      // Removed outright (export icon and popup are nested in .pm-share-wrap):
      // nothing real to share from an anonymous demo, and nothing later looks
      // them up.
      var shareWrap = document.querySelector('.pm-share-wrap');
      if (shareWrap) shareWrap.remove();

      // Fixed-height container with an always-on bottom-edge feather
      // (.landing-storages-preview in possessions.css).
    }})();
    """
    return extra_head, body, wrapper_script


def render_possessions(player: PlayerView) -> str:
    extra_head, body, script = _possessions_panel_markup()
    return _shell(
        title="Storages Viewer — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )


def render_storages_share(share: "SharedContent", game_account: Optional["GameAccount"], viewer: Optional[PlayerView]) -> str:
    """GET /s/<code> for a Storages Viewer share: a frozen snapshot of what the
    owner had on screen (build_possessions_share_snapshot in
    app/possessions.py).
    
    Reuses _possessions_panel_markup's body/script unmodified, with a fetch
    shim answering GET /api/possessions/summary and /views from PAYLOAD.
    Read-only: a capturing-phase click listener blocks the settings checkboxes
    and pin buttons (like #pgGearFrame in render_purchase_goals_share); the
    cog trigger (#pmSettingsBtn) stays clickable. Location filter buttons stay
    interactive (state.locations is never persisted). #pmViewsRow is hidden
    via CSS, not stripped, since loadViews()/renderViewsRow() run without a
    null guard.
    
    The reused <h2> is stripped; banner_markup adds "SNAPSHOT AS OF: <date>
    <time> (LOCAL)" above "Shared by <name>". game_account may be None; falls
    back to "A player".
    """
    extra_head, body, script = _possessions_panel_markup()
    # Strip the reused body's "Storages Viewer" <h2 class="page-title"> and its
    # export button by keeping only what follows the first "</h2>".
    _, _, body = body.partition("</h2>")

    owner_name = (game_account.runescape_name if game_account else None) or "A player"

    # "SNAPSHOT AS OF" line: one point in time (the row's created_at), unlike
    # Loot Tracker's range line. The server-rendered fallback is a written-out
    # UTC form (not YYYY-MM-DD) so it is not mistaken for the local-time version
    # when JS is disabled.
    created_at_iso = share.created_at.isoformat()
    asof_fallback = f"SNAPSHOT AS OF: {share.created_at.strftime('%b %-d, %Y, %-I:%M %p')} UTC"
    banner_markup = f"""
    <p class="subtitle pm-share-asof"><span id="pmShareAsOfLine">{escape(asof_fallback)}</span></p>
    <h2 class="page-title">Shared by {escape(owner_name)}</h2>
    <script>
    (function () {{
      // Zero-padded 'YYYY-MM-DD' in local time, hand-built as in
      // render_loot_tracker_share's range script (toLocaleDateString has no ISO
      // form).
      function fmtIsoDateLocal(d) {{
        var month = String(d.getMonth() + 1);
        if (month.length < 2) month = '0' + month;
        var day = String(d.getDate());
        if (day.length < 2) day = '0' + day;
        return d.getFullYear() + '-' + month + '-' + day;
      }}
      var d = new Date("{created_at_iso}");
      var timeStr = d.toLocaleTimeString('en-US', {{ hour: 'numeric', minute: '2-digit' }});
      document.getElementById('pmShareAsOfLine').textContent = 'SNAPSHOT AS OF: ' + fmtIsoDateLocal(d) + ' ' + timeStr + ' (LOCAL)';
    }})();
    </script>
    """
    body = banner_markup + body
    body = f'<div class="possessions-share">{body}</div>'

    payload_json = json.dumps(share.payload)
    wrapper_script = f"""
    (function () {{
      var PAYLOAD = {payload_json};

      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        var qIndex = url.indexOf('?');
        var path = qIndex === -1 ? url : url.slice(0, qIndex);

        if (path === '/api/possessions/summary' && method === 'GET') {{
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{
            items: PAYLOAD.items,
            mappingError: PAYLOAD.mappingError,
            priceError: PAYLOAD.priceError,
            hiddenStorageKeys: PAYLOAD.hiddenStorageKeys,
          }}); }} }});
        }}
        if (path === '/api/possessions/views' && method === 'GET') {{
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{ views: [] }}); }} }});
        }}
        // Second line of defense behind the capturing-phase click listener
        // below: echo the frozen PAYLOAD values, since an empty object would
        // read as nothing pinned/hidden and reconcile every row to match.
        if (path.indexOf('/api/possessions/pins/') === 0) {{
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{
            pinnedItemIds: PAYLOAD.items.filter(function (i) {{ return i.pinned; }}).map(function (i) {{ return i.itemId; }}),
          }}); }} }});
        }}
        if (path.indexOf('/api/possessions/hidden-storages/') === 0) {{
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{ hiddenStorageKeys: PAYLOAD.hiddenStorageKeys }}); }} }});
        }}
        // Harmless no-op fallback for anything else, like the other
        // share/preview shims.
        return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{}}); }} }});
      }};

      {script}

      // Simulates the sharer's frozen location-filter selection (state.locations
      // is never persisted), then permanently blocks clicks on location buttons,
      // settings checkboxes and pin buttons, so the simulation is the only click
      // they act on.
      var activeLocations = PAYLOAD.activeLocations || [];
      document.querySelectorAll('.pm-filter-btn').forEach(function (btn) {{
        var keys = btn.getAttribute('data-locations').split(',');
        var shouldBeActive = keys.every(function (k) {{ return activeLocations.indexOf(k) !== -1; }});
        if (!shouldBeActive) btn.click();
      }});

      document.addEventListener('click', function (e) {{
        if (e.target.closest('.pm-pin-btn') || e.target.closest('.pm-settings-item')) {{
          e.stopImmediatePropagation();
          e.preventDefault();
        }}
      }}, true);
    }})();
    """
    return _shell(
        title=f"{owner_name}'s shared Storages Viewer — myscape",
        player=viewer,
        body=body,
        extra_head=extra_head,
        extra_script=wrapper_script,
        meta_description=f"{owner_name} shared a snapshot of their Storages Viewer on myscape.",
    )


def _goal_tracking_panel_markup() -> Tuple[str, str, str]:
    extra_head = f'<link rel="stylesheet" href="/static/css/goal-tracking.css?v={_GOAL_TRACKING_CSS_VERSION}" />'

    boss_slug_by_name_json = json.dumps({name: slug for slug, name, _has_icon in HISCORE_BOSSES})
    # SKILL_NAMES (app/mindmaps.py) is in the in-game skills-tab order;
    # re-sorted alphabetically for the wizard's skill search list.
    skill_names_json = json.dumps(sorted(SKILL_NAMES))

    body = """
    <h2 class="page-title">Goal Tracking <span class="gt-share-wrap"><button type="button" class="gt-share-icon-btn" id="gtShareIconBtn" aria-label="Share your list of goals" data-tooltip="Share your list of goals"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg></button><div class="gt-share-card" id="gtShareCard" hidden><button type="button" class="gt-share-generate-btn" id="gtShareGenerateBtn">GENERATE SHAREABLE LINK</button><button type="button" class="gt-share-link-btn" id="gtShareLinkBtn" data-tooltip="Click to copy" hidden></button><p class="gt-share-popup-hint">Links are active for 30 days, but can be<br>deleted sooner on your Account page.</p></div></span></h2>
    <div class="auth-error" id="gtError"></div>

    <div class="gt-wizard" id="gtWizard">
      <button type="button" class="gt-wizard-add-btn" id="gtWizardAddBtn">Add goal</button>
      <div class="gt-wizard-expanded" id="gtWizardExpanded" style="display:none;">
        <div id="gtWizardStage"></div>
      </div>
    </div>

    <div class="gt-card gt-list-card">
      <div class="gt-sort-tabs" id="gtSortTabs">
        <button type="button" class="gt-sort-tab" data-sort-metric="progress" data-tooltip="Sort by progress">Progress<span class="gt-sort-arrow"></span></button>
        <button type="button" class="gt-sort-tab" data-sort-metric="type" data-tooltip="Sort by type">Type<span class="gt-sort-arrow"></span></button>
        <button type="button" class="gt-sort-tab" data-sort-metric="alpha" data-tooltip="Sort alphabetically">A-Z<span class="gt-sort-arrow"></span></button>
        <button type="button" class="gt-sort-tab" data-sort-metric="time" data-tooltip="Sort by time created">Time<span class="gt-sort-arrow"></span></button>
        <button type="button" class="gt-sort-tab" data-sort="custom" data-tooltip="Sort by custom order">Custom</button>
      </div>
      <p class="gt-empty" id="gtEmpty" style="display:none;">Add a goal above to start tracking.</p>
      <div class="gt-goal-list" id="gtGoalList"></div>
    </div>
    """

    script = (
        "var BOSS_SLUG_BY_NAME = " + boss_slug_by_name_json + ";\n"
        "var SKILL_NAMES_LIST = " + skill_names_json + ";\n"
        + """
    (function () {
      // Generic per-TYPE badge: used by the type-picker buttons and by item
      // goals' row icons. kc/skill rows use their boss/skill sprite (goalRowHtml
      // iconSrc).
      var TYPE_ICON = {
        kc: '/static/img/icon-goal-kc.png',
        skill: '/static/img/icon-goal-skill.png',
        item: '/static/img/icon-goal-item.png',
      };
      // Grouping order for the "Type" sort tab; same kc/skill/item order as
      // TYPE_ICON.
      var GOAL_TYPE_SORT_ORDER = { kc: 0, skill: 1, item: 2 };
      var TARGET_BOUNDS = {
        kc: { min: 1, max: 2147483647 },
        item: { min: 1, max: 2147483647 },
        skill_level: { min: 1, max: 126 },
        skill_xp: { min: 1, max: 200000000 },
      };


      function parseMoneySuffix(raw) {
        var s = (raw || '').trim().replace(/,/g, '');
        var m = /^([0-9]*\\.?[0-9]+)\\s*([kKmMbB])$/.exec(s);
        if (!m) return s;
        var mult = { k: 1e3, m: 1e6, b: 1e9 }[m[2].toLowerCase()];
        return String(Math.round(parseFloat(m[1]) * mult));
      }

      // Keeps only valid target-field characters (digits, commas, a decimal
      // point, k/m/b). Hence type="text" inputmode="decimal": a number input
      // cannot accept K/M/B.
      var NUMERIC_SUFFIX_DISALLOWED_RE = /[^0-9,.kKmMbB]/g;

      function filterNumericSuffixInput(input) {
        var cleaned = input.value.replace(NUMERIC_SUFFIX_DISALLOWED_RE, '');
        if (cleaned === input.value) return;
        var cursor = input.selectionStart;
        var keptBeforeCursor = input.value.slice(0, cursor).replace(NUMERIC_SUFFIX_DISALLOWED_RE, '').length;
        input.value = cleaned;
        input.setSelectionRange(keptBeforeCursor, keptBeforeCursor);
      }

      // OSRS xp-per-level curve for levels 1-126 including virtual levels
      // (https://oldschool.runescape.wiki/w/Experience): xp(L) = floor(1/4 *
      // sum[l=1..L-1] of floor(l + 300*2^(l/7))). SKILL_XP_TABLE[L] is the total
      // xp for level L; index 0 is unused.
      var SKILL_XP_TABLE = (function () {
        var maxLevel = TARGET_BOUNDS.skill_level.max;
        var table = [0, 0];
        var cumulative = 0;
        for (var l = 1; l < maxLevel; l++) {
          cumulative += Math.floor(l + 300 * Math.pow(2, l / 7));
          table[l + 1] = Math.floor(cumulative / 4);
        }
        return table;
      })();
      // The xp a level needs, clamped into range; used when the metric toggle
      // goes LVL to XP.
      function xpForLevel(level) {
        var b = TARGET_BOUNDS.skill_level;
        level = Math.max(b.min, Math.min(b.max, Math.round(level)));
        return SKILL_XP_TABLE[level];
      }
      // The largest level whose xp requirement is at or below the given xp
      // (5,750 xp is level 22); used when the toggle goes XP to LVL.
      function levelForXp(xp) {
        var b = TARGET_BOUNDS.skill_level;
        for (var l = b.max; l >= b.min; l--) {
          if (xp >= SKILL_XP_TABLE[l]) return l;
        }
        return b.min;
      }

      var GT = {
        goals: [],
        sortMode: 'alphabetical',
        wizardStage: 0,
        recurring: null, // null | 'one_time' | 'recurring' -- picked in stage 1
        type: null,
        skillMetric: 'level',
        itemId: null, // the chosen search result's real item id, if any -- see Goal.item_id's own docstring in app/models.py
        // GAIN/REACH for a one-time kc or xp-skill goal (#gtTargetModeToggle,
        // see targetModeApplies); defaults to 'gain' (Goal.baseline_value in
        // app/models.py). Not reset when switching away, so Back/Forward keeps
        // it; LEVEL -> XP resets it to 'gain'.
        targetMode: 'gain',
        recurInterval: '', // stage 4's own text field, kept here so re-rendering that stage (e.g. after Back then forward again) doesn't lose it
        recurUnit: 'day', // stage 4's own segmented-control selection
        recurStart: 'now', // stage 5's own NOW/CUSTOM segmented-control selection -- NOW by default, same "the simple choice is the default" convention GT.targetMode/GT.recurUnit already follow
        recurStartAt: '', // stage 5's own masked "YYYY-MM-DD HH:MM" text field, kept here for the same Back-then-forward reason GT.recurInterval is; only ever read when recurStart === 'custom'
        // sortMode + JSON of the goals last rendered; null until the first
        // render. Lets applyGoalsResponse skip an unchanged rebuild.
        renderKey: null,
      };
      var BOSS_NAMES = Object.keys(BOSS_SLUG_BY_NAME);

      function showError(msg) {
        var el = document.getElementById('gtError');
        if (!msg) { el.classList.remove('show'); el.textContent = ''; return; }
        el.textContent = msg;
        el.classList.add('show');
      }

      async function apiCall(url, options) {
        try {
          var res = await fetch(url, options);
          var data = await res.json().catch(function () { return {}; });
          if (!res.ok) {
            showError((data && data.detail) || 'Something went wrong. Please try again.');
            return null;
          }
          showError(null);
          return data;
        } catch (err) {
          showError('Something went wrong. Please try again.');
          return null;
        }
      }

      function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
          return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
      }

      function fmtNum(n) { return Math.round(n || 0).toLocaleString('en-US'); }

      function debounce(fn, wait) {
        var t = null;
        return function () {
          var args = arguments;
          clearTimeout(t);
          t = setTimeout(function () { fn.apply(null, args); }, wait);
        };
      }

      // Add-goal wizard
      // Stages: 1 one-time vs recurring, 2 goal type (recurring drops item;
      // RECURRING_GOAL_TYPES in app/goals.py), 3 target + value, 4 recurring
      // cadence, 5 recurring start. One-time goals save from stage 3.

      var wizardExpanded = document.getElementById('gtWizardExpanded');
      var wizardStageEl = document.getElementById('gtWizardStage');
      var wizardTarget = { name: '', itemId: null, value: null };

      function openWizard() {
        GT.wizardStage = 1;
        GT.recurring = null;
        GT.type = null;
        GT.skillMetric = 'level';
        GT.itemId = null;
        GT.targetMode = 'gain';
        GT.recurInterval = '';
        GT.recurUnit = 'day';
        GT.recurStart = 'now';
        GT.recurStartAt = '';
        renderWizard();
      }

      function closeWizard() {
        GT.wizardStage = 0;
        renderWizard();
      }

      function wizardPickRecurrence(recurring) {
        GT.recurring = recurring;
        GT.wizardStage = 2;
        renderWizard();
      }

      function wizardPickType(type) {
        GT.type = type;
        // A recurring skill goal is XP-only; forced here so a stale Lvl pick
        // from an earlier one-time goal is not carried over.
        if (GT.recurring === 'recurring' && type === 'skill') { GT.skillMetric = 'xp'; }
        // The one place stage 3 is entered fresh (first time, or after
        // re-picking a type), so wizardTarget is cleared here and not in
        // wireWizardStage.
        wizardTarget = { name: '', itemId: null, value: null };
        GT.wizardStage = 3;
        renderWizard();
      }

      function wizardBack() {
        if (GT.wizardStage === 5) {
          GT.wizardStage = 4;
        } else if (GT.wizardStage === 4) {
          GT.wizardStage = 3;
        } else if (GT.wizardStage === 3) {
          GT.wizardStage = 2;
          GT.type = null;
          GT.skillMetric = 'level';
          GT.itemId = null;
          GT.targetMode = 'gain';
        } else if (GT.wizardStage === 2) {
          GT.wizardStage = 1;
          GT.recurring = null;
        }
        renderWizard();
      }

      document.getElementById('gtWizardAddBtn').addEventListener('click', openWizard);
      // One page-wide listener (stage 3's suggestions box is rebuilt on every
      // render); looks elements up on each click, so it no-ops on other stages.
      document.addEventListener('click', function (e) {
        var suggestions = document.getElementById('gtWizardSuggestions');
        var searchInput = document.getElementById('gtWizardSearchInput');
        if (suggestions && !suggestions.contains(e.target) && e.target !== searchInput) {
          suggestions.classList.remove('show');
        }
      });

      function renderWizard() {
        var addBtn = document.getElementById('gtWizardAddBtn');
        if (GT.wizardStage === 0) {
          addBtn.style.display = '';
          wizardExpanded.style.display = 'none';
          return;
        }
        addBtn.style.display = 'none';
        wizardExpanded.style.display = '';
        var stageHtml = {
          1: wizardStageRecurrenceHtml,
          2: wizardStageTypeHtml,
          3: wizardStageTargetHtml,
          4: wizardStageCadenceHtml,
          5: wizardStageStartHtml,
        }[GT.wizardStage];
        wizardStageEl.innerHTML = stageHtml();
        wireWizardStage();
      }

      var ONE_TIME_ICON_SVG =
        '<svg class="gt-recur-icon" viewBox="0 0 24 24" width="32" height="32" fill="none" ' +
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<path d="M8.5 7L11.5 5V19"/>' +
        '<path d="M8 19H15"/>' +
        '<path d="M16.5 11.5L21 16"/>' +
        '<path d="M21 11.5L16.5 16"/>' +
        '</svg>';
      var RECURRING_ICON_SVG =
        '<svg class="gt-recur-icon" viewBox="0 0 24 24" width="32" height="32" fill="none" ' +
        'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<rect x="3.5" y="5.5" width="17" height="15" rx="2"/>' +
        '<path d="M8 3V7"/>' +
        '<path d="M16 3V7"/>' +
        '<path d="M9.8 13.5a2.6 2.6 0 0 1 4.7-1.6" stroke-width="1.4"/>' +
        '<path d="M14.9 10.8L15.1 12.5L13.4 12.4"/>' +
        '<path d="M14.2 14.9a2.6 2.6 0 0 1-4.7 1.6" stroke-width="1.4"/>' +
        '<path d="M9.1 17.6L8.9 15.9L10.6 16.0"/>' +
        '</svg>';

      // Stage 1: one-time vs recurring. Reuses stage 2's type-card/Cancel
      // wrapper with 2 cards and SVG icons
      // (ONE_TIME_ICON_SVG/RECURRING_ICON_SVG).
      function wizardStageRecurrenceHtml() {
        return '' +
          '<div class="gt-wizard-stage1-wrap">' +
          '  <div class="gt-wizard-stage1">' +
          '    <button type="button" class="gt-wizard-type-btn" data-recur="one_time">' +
                 ONE_TIME_ICON_SVG + '<span>One-Time</span></button>' +
          '    <button type="button" class="gt-wizard-type-btn" data-recur="recurring">' +
                 RECURRING_ICON_SVG + '<span>Recurring</span></button>' +
          '  </div>' +
          '  <div class="gt-wizard-stage1-actions">' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-cancel" id="gtWizardCancel">Cancel</button>' +
          '  </div>' +
          '</div>';
      }

      // Stage 2: type picker. Recurring goals offer kc/skill only (an item's
      // owned quantity is not a monotonic lifetime total; RECURRING_GOAL_TYPES
      // in app/goals.py).
      var GOAL_TYPE_OPTIONS = [
        { type: 'item', icon: '/static/img/icon-goal-item.png', label: 'Item Qty' },
        { type: 'kc', icon: '/static/img/icon-goal-kc.png', label: 'Boss KC' },
        { type: 'skill', icon: '/static/img/icon-goal-skill.png', label: 'Skill Lvl/Xp' },
      ];

      function wizardStageTypeHtml() {
        var options = (GT.recurring === 'recurring')
          ? GOAL_TYPE_OPTIONS.filter(function (o) { return o.type !== 'item'; })
          : GOAL_TYPE_OPTIONS;
        var cards = options.map(function (o) {
          // A recurring skill goal is XP-only, so its card says just "Skill Xp"
          // rather than promising a level option.
          var label = (o.type === 'skill' && GT.recurring === 'recurring') ? 'Skill Xp' : o.label;
          return '<button type="button" class="gt-wizard-type-btn" data-type="' + o.type + '">' +
            '<img src="' + o.icon + '" alt="" /><span>' + label + '</span></button>';
        }).join('');
        return '' +
          '<div class="gt-wizard-stage1-wrap">' +
          '  <div class="gt-wizard-stage1">' + cards + '</div>' +
          '  <div class="gt-wizard-stage1-actions">' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-back" id="gtWizardBack">Back</button>' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-cancel" id="gtWizardCancel">Cancel</button>' +
          '  </div>' +
          '</div>';
      }

      var WIZARD_SEARCH_PLACEHOLDER = { item: 'Search for an item', kc: 'Search for a boss', skill: 'Search for a skill' };

      // Whether GAIN/REACH applies to the current pick; mirrors
      // app.goals.target_mode_allows_gain (level-metric skill and item goals are
      // REACH-only).
      function targetModeApplies() {
        if (GT.recurring === 'recurring') return false;
        if (GT.type === 'kc') return true;
        if (GT.type === 'skill') return GT.skillMetric === 'xp';
        return false;
      }

      function targetModeVisible() {
        if (GT.recurring === 'recurring') return false;
        if (GT.type === 'kc') return true;
        if (GT.type === 'skill') return true;
        return false;
      }

      function wizardTargetPlaceholder() {
        var gain = targetModeApplies() && GT.targetMode === 'gain';
        if (GT.type === 'kc') return gain ? 'Kc to gain' : 'Target kc';
        if (GT.type === 'skill') {
          if (GT.skillMetric === 'xp') return gain ? 'Experience to gain' : 'Target experience';
          return 'Target level';
        }
        return 'Target quantity';
      }

      // Stage 3 in one fixed-size box (.gt-wizard-expanded in
      // goal-tracking.css): search + target fields, the segmented controls row
      // (#gtWizardSegRow), then Back/Cancel/Save-or-Next (Next for recurring
      // goals). #gtTargetModeField is an always-present wrapper that
      // wireTargetModeToggle fills or empties in place.
      function wizardStageTargetHtml() {
        // No Lvl/Xp choice for a recurring skill goal; wizardPickType forces
        // GT.skillMetric to 'xp'.
        var metricToggle = (GT.type !== 'skill' || GT.recurring === 'recurring') ? '' : (
          '<div class="gt-metric-toggle" id="gtMetricToggle">' +
          '  <button type="button" class="gt-metric-btn" data-metric="level">Lvl</button>' +
          '  <button type="button" class="gt-metric-btn" data-metric="xp">XP</button>' +
          '</div>'
        );
        var saveLabel = (GT.recurring === 'recurring') ? 'Next' : 'Save';
        // Next uses the secondary look (like Back/Cancel) since a real Save
        // still follows on stage 4.
        var saveBtnClass = 'gt-add-btn' + (GT.recurring === 'recurring' ? ' gt-wizard-btn-next' : '');
        return '' +
          '<div class="gt-wizard-stage2">' +
          '  <div class="gt-wizard-row">' +
          '    <div class="gt-field gt-field-target-search">' +
          '      <div class="gt-search-box">' +
          '        <input type="text" id="gtWizardSearchInput" placeholder="' + WIZARD_SEARCH_PLACEHOLDER[GT.type] + '" autocomplete="off" />' +
          '        <div class="gt-suggestions" id="gtWizardSuggestions"></div>' +
          '      </div>' +
          '    </div>' +
          '    <div class="gt-field gt-field-target">' +
          '      <input type="text" inputmode="decimal" id="gtTargetValue" placeholder="' + wizardTargetPlaceholder() + '" autocomplete="off" />' +
          '    </div>' +
          '  </div>' +
          '  <div class="gt-wizard-segrow" id="gtWizardSegRow">' +
          metricToggle +
          '    <div id="gtTargetModeField"></div>' +
          '  </div>' +
          '  <div class="gt-wizard-actions">' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-back" id="gtWizardBack">Back</button>' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-cancel" id="gtWizardCancel">Cancel</button>' +
          '    <button type="button" class="' + saveBtnClass + '" id="gtWizardSave">' + saveLabel + '</button>' +
          '  </div>' +
          '</div>';
      }

      function targetModeToggleHtml() {
        return '' +
          '<div class="gt-target-mode-toggle" id="gtTargetModeToggle">' +
          '  <button type="button" class="gt-target-mode-btn" data-mode="gain">Gain</button>' +
          '  <button type="button" class="gt-target-mode-btn" data-mode="reach">Reach</button>' +
          '</div>';
      }

      // Fills #gtTargetModeField (or empties it) to match targetModeVisible()
      // and wires its buttons; called when stage 3 renders and from the Lvl/Xp
      // handler. When visible but not applicable (skill goal on LEVEL) it is
      // .gt-target-mode-toggle--disabled with no handler or .active button.
      function wireTargetModeToggle() {
        var field = document.getElementById('gtTargetModeField');
        if (!field) return;
        if (!targetModeVisible()) {
          field.innerHTML = '';
          updateWizardSegRowVisibility();
          return;
        }
        var applies = targetModeApplies();
        field.innerHTML = targetModeToggleHtml();
        var toggleEl = document.getElementById('gtTargetModeToggle');
        toggleEl.classList.toggle('gt-target-mode-toggle--disabled', !applies);
        document.querySelectorAll('#gtTargetModeToggle .gt-target-mode-btn').forEach(function (btn) {
          btn.classList.toggle('active', applies && btn.getAttribute('data-mode') === GT.targetMode);
          if (!applies) return;
          btn.addEventListener('click', function () {
            var newMode = btn.getAttribute('data-mode');
            if (newMode === GT.targetMode) return;
            GT.targetMode = newMode;
            document.querySelectorAll('#gtTargetModeToggle .gt-target-mode-btn').forEach(function (b) {
              b.classList.toggle('active', b === btn);
            });
            // Update the target placeholder in place ("Kc to gain" <-> "Target
            // kc"), like the Lvl/Xp toggle handler.
            updateWizardTargetField();
          });
        });
        updateWizardSegRowVisibility();
      }

      // Collapses #gtWizardSegRow when no toggle applies (item goal, or skill
      // goal on Lvl). CSS :empty cannot do this since #gtTargetModeField is
      // always a child. Called from wireTargetModeToggle, the one place the
      // row's contents can change.
      function updateWizardSegRowVisibility() {
        var segRow = document.getElementById('gtWizardSegRow');
        if (!segRow) return;
        var hasContent = !!segRow.querySelector('.gt-metric-toggle, .gt-target-mode-toggle');
        segRow.classList.toggle('gt-wizard-segrow--empty', !hasContent);
      }

      // Recurring units in the order of app.goals.RECUR_UNITS (display order
      // only; the server validates recur_unit).
      var RECUR_UNIT_OPTIONS = [
        { unit: 'hour', label: 'Hour' },
        { unit: 'day', label: 'Day' },
        { unit: 'week', label: 'Week' },
        { unit: 'month', label: 'Month' },
        { unit: 'year', label: 'Year' },
      ];
      // Mirrors app.goals.MAX_RECUR_INTERVAL; the server re-validates
      // (validateRecurField).
      var MAX_RECUR_INTERVAL = 999;

      // "Every x days" etc.; doubles as the field's label. Derived from
      // RECUR_UNIT_OPTIONS' label (lowercase + "s").
      function recurIntervalPlaceholder() {
        var opt = RECUR_UNIT_OPTIONS.filter(function (o) { return o.unit === GT.recurUnit; })[0];
        var unitWord = opt ? opt.label.toLowerCase() : 'day';
        return 'Every x ' + unitWord + 's';
      }

      function wizardStageCadenceHtml() {
        var unitButtons = RECUR_UNIT_OPTIONS.map(function (o) {
          return '<button type="button" class="gt-recur-unit-btn' + (o.unit === GT.recurUnit ? ' active' : '') + '" data-unit="' + o.unit + '">' + o.label + '</button>';
        }).join('');
        return '' +
          '<div class="gt-wizard-stage2">' +
          '  <div class="gt-wizard-recur-fields">' +
          '    <input type="text" inputmode="numeric" class="gt-recur-interval-input" id="gtRecurInterval" placeholder="' + recurIntervalPlaceholder() + '" autocomplete="off" maxlength="4" value="' + escapeHtml(GT.recurInterval || '') + '" />' +
          '  </div>' +
          '  <div class="gt-wizard-segrow">' +
          '    <div class="gt-recur-unit-toggle" id="gtRecurUnitToggle">' + unitButtons + '</div>' +
          '  </div>' +
          '  <div class="gt-wizard-actions">' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-back" id="gtWizardBack">Back</button>' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-cancel" id="gtWizardCancel">Cancel</button>' +
          '    <button type="button" class="gt-add-btn gt-wizard-btn-next" id="gtWizardSave">Next</button>' +
          '  </div>' +
          '</div>';
      }

      // Stage 5 (recurring only, last page): when the cadence starts. The
      // date/time field always renders (disabled while NOW, wireStartStage) so
      // the row order is fixed. RECUR_START_MASK is a longer copy of Loot
      // Tracker's DATE_MASK (pages share no script module).
      function wizardStageStartHtml() {
        var startPlaceholder = (GT.recurStart === 'custom') ? 'YYYY-MM-DD HH:MM' : 'Start now';
        var startValue = (GT.recurStart === 'custom') ? (GT.recurStartAt || RECUR_START_BLANK) : '';
        return '' +
          '<div class="gt-wizard-stage2">' +
          '  <div class="gt-wizard-recur-fields">' +
          '    <input type="text" inputmode="numeric" class="gt-recur-start-input" id="gtRecurStartInput" placeholder="' + escapeHtml(startPlaceholder) + '" autocomplete="off" spellcheck="false" ' +
                 (GT.recurStart === 'custom' ? '' : 'disabled ') + 'value="' + escapeHtml(startValue) + '" />' +
          '  </div>' +
          '  <div class="gt-wizard-segrow">' +
          '    <div class="gt-recur-start-toggle" id="gtRecurStartToggle">' +
          '      <button type="button" class="gt-recur-start-btn' + (GT.recurStart === 'now' ? ' active' : '') + '" data-start="now">Now</button>' +
          '      <button type="button" class="gt-recur-start-btn' + (GT.recurStart === 'custom' ? ' active' : '') + '" data-start="custom">Custom</button>' +
          '    </div>' +
          '  </div>' +
          '  <div class="gt-wizard-actions">' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-back" id="gtWizardBack">Back</button>' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-cancel" id="gtWizardCancel">Cancel</button>' +
          '    <button type="button" class="gt-add-btn" id="gtWizardSave">Save</button>' +
          '  </div>' +
          '</div>';
      }

      function wizardOptionLabel(raw) {
        return (GT.type === 'skill') ? (raw.charAt(0).toUpperCase() + raw.slice(1)) : raw;
      }

      function wireWizardStage() {
        if (GT.wizardStage === 1) {
          document.querySelectorAll('.gt-wizard-type-btn').forEach(function (btn) {
            btn.addEventListener('click', function () { wizardPickRecurrence(btn.getAttribute('data-recur')); });
          });
          document.getElementById('gtWizardCancel').addEventListener('click', closeWizard);
          return;
        }

        if (GT.wizardStage === 2) {
          document.querySelectorAll('.gt-wizard-type-btn').forEach(function (btn) {
            btn.addEventListener('click', function () { wizardPickType(btn.getAttribute('data-type')); });
          });
          document.getElementById('gtWizardBack').addEventListener('click', wizardBack);
          document.getElementById('gtWizardCancel').addEventListener('click', closeWizard);
          return;
        }

        if (GT.wizardStage === 4) {
          wireCadenceStage();
          return;
        }

        if (GT.wizardStage === 5) {
          wireStartStage();
          return;
        }

        // Does not reset wizardTarget: renderWizard rebuilds this stage on every
        // visit, including Back from stage 4, and a reset would blank the picks.
        // wizardPickType is the fresh start.
        document.getElementById('gtWizardBack').addEventListener('click', wizardBack);
        document.getElementById('gtWizardCancel').addEventListener('click', closeWizard);

        var searchInput = document.getElementById('gtWizardSearchInput');
        var suggestions = document.getElementById('gtWizardSuggestions');
        searchInput.value = wizardTarget.name || '';

        function showSuggestions(names, iconFor) {
          if (!names.length) { suggestions.classList.remove('show'); suggestions.innerHTML = ''; return; }
          suggestions.innerHTML = names.map(function (raw) {
            var label = wizardOptionLabel(raw);
            var icon = iconFor ? iconFor(raw) : null;
            return '<div class="gt-suggestion" data-raw="' + escapeHtml(raw) + '" data-label="' + escapeHtml(label) + '">' +
              (icon ? '<img src="' + escapeHtml(icon) + '" alt="" />' : '') +
              '<span>' + escapeHtml(label) + '</span></div>';
          }).join('');
          suggestions.classList.add('show');
        }

        function showItemSuggestions(results) {
          if (!results.length) { suggestions.classList.remove('show'); suggestions.innerHTML = ''; return; }
          suggestions.innerHTML = results.map(function (r) {
            return '<div class="gt-suggestion" data-raw="' + escapeHtml(r.name) + '" data-label="' + escapeHtml(r.name) +
              '" data-item-id="' + (r.id || '') + '">' +
              (r.icon ? '<img src="' + escapeHtml(r.icon) + '" alt="" />' : '') +
              '<span>' + escapeHtml(r.name) + '</span></div>';
          }).join('');
          suggestions.classList.add('show');
        }

        suggestions.addEventListener('click', function (e) {
          var row = e.target.closest('.gt-suggestion');
          if (!row) return;
          var label = row.getAttribute('data-label');
          searchInput.value = label;
          searchInput.classList.remove('invalid');
          wizardTarget.name = row.getAttribute('data-raw');
          var itemId = row.getAttribute('data-item-id');
          wizardTarget.itemId = (GT.type === 'item' && itemId) ? parseInt(itemId, 10) : null;
          suggestions.classList.remove('show');
          suggestions.innerHTML = '';
        });

        if (GT.type === 'item') {
          searchInput.addEventListener('input', debounce(async function () {
            searchInput.classList.remove('invalid');
            wizardTarget.name = searchInput.value.trim();
            wizardTarget.itemId = null;
            var q = wizardTarget.name;
            if (!q) { showItemSuggestions([]); return; }
            var data = await apiCall('/api/items/search?q=' + encodeURIComponent(q));
            showItemSuggestions(data ? data.results : []);
          }, 200));
        } else {
          var pool = (GT.type === 'kc') ? BOSS_NAMES : SKILL_NAMES_LIST;
          var iconFor = (GT.type === 'kc')
            ? function (raw) { return '/static/boss-icons/' + BOSS_SLUG_BY_NAME[raw] + '.png'; }
            : function (raw) { return '/static/skill-icons/' + raw + '.png'; };
          searchInput.addEventListener('input', debounce(function () {
            searchInput.classList.remove('invalid');
            wizardTarget.name = searchInput.value.trim();
            var q = wizardTarget.name.toLowerCase();
            var matches = !q ? [] : pool.filter(function (raw) {
              return wizardOptionLabel(raw).toLowerCase().indexOf(q) !== -1;
            }).slice(0, 20);
            showSuggestions(matches, iconFor);
          }, 120));
        }

        if (GT.type === 'skill' && GT.recurring !== 'recurring') {
          document.querySelectorAll('.gt-metric-btn').forEach(function (btn) {
            btn.classList.toggle('active', btn.getAttribute('data-metric') === GT.skillMetric);
            btn.addEventListener('click', function () {
              var newMetric = btn.getAttribute('data-metric');
              if (newMetric !== GT.skillMetric) {
                // Carries the field's number across the switch (5,750 xp <->
                // level 22) via xpForLevel/levelForXp, like Mindmaps' skill-goal
                // metric toggle.
                var targetInputForSwitch = document.getElementById('gtTargetValue');
                var rawForSwitch = targetInputForSwitch.value.trim();
                if (rawForSwitch !== '') {
                  var nForSwitch = Number(parseMoneySuffix(rawForSwitch));
                  if (Number.isInteger(nForSwitch)) {
                    targetInputForSwitch.value = String(
                      newMetric === 'xp' ? xpForLevel(nForSwitch) : levelForXp(nForSwitch)
                    );
                  }
                }
                // LEVEL -> XP makes GAIN/REACH usable, so GT.targetMode resets
                // to 'gain'. XP -> LEVEL only disables the toggle.
                if (newMetric === 'xp') GT.targetMode = 'gain';
                GT.skillMetric = newMetric;
              }
              document.querySelectorAll('.gt-metric-btn').forEach(function (b) {
                b.classList.toggle('active', b === btn);
              });
              wireTargetModeToggle();
              updateWizardTargetField();
              validateTargetField();
            });
          });
        }

        var targetInput = document.getElementById('gtTargetValue');
        // Restores wizardTarget.value captured the last time Next was pressed
        // here (null on the first visit).
        if (wizardTarget.value != null) targetInput.value = String(wizardTarget.value);
        targetInput.addEventListener('input', function () {
          filterNumericSuffixInput(targetInput);
          validateTargetField();
        });

        wireTargetModeToggle();
        updateWizardTargetField();
        document.getElementById('gtWizardSave').addEventListener('click', function () {
          var targetName = wizardTarget.name.trim();
          searchInput.classList.toggle('invalid', !targetName);
          var valueOk = validateTargetField(true);
          if (!targetName || !valueOk) return;
          wizardTarget.value = Number(parseMoneySuffix(document.getElementById('gtTargetValue').value.trim()));
          if (GT.recurring === 'recurring') {
            GT.wizardStage = 4;
            renderWizard();
          } else {
            wizardAddGoal();
          }
        });
      }

      function wireCadenceStage() {
        document.getElementById('gtWizardBack').addEventListener('click', wizardBack);
        document.getElementById('gtWizardCancel').addEventListener('click', closeWizard);

        var intervalInput = document.getElementById('gtRecurInterval');
        intervalInput.addEventListener('input', function () {
          // Digits only: a plain count, no k/m/b shorthand or decimal point.
          var cursor = intervalInput.selectionStart;
          var cleaned = intervalInput.value.replace(/[^0-9]/g, '');
          if (cleaned !== intervalInput.value) {
            var keptBeforeCursor = intervalInput.value.slice(0, cursor).replace(/[^0-9]/g, '').length;
            intervalInput.value = cleaned;
            intervalInput.setSelectionRange(keptBeforeCursor, keptBeforeCursor);
          }
          GT.recurInterval = intervalInput.value;
          validateRecurField();
        });

        document.querySelectorAll('.gt-recur-unit-btn').forEach(function (btn) {
          btn.addEventListener('click', function () {
            GT.recurUnit = btn.getAttribute('data-unit');
            document.querySelectorAll('.gt-recur-unit-btn').forEach(function (b) {
              b.classList.toggle('active', b === btn);
            });
            // Updates only the placeholder: a full renderWizard() would wipe
            // what is typed in the field (GT.recurInterval is read back only on
            // render).
            intervalInput.placeholder = recurIntervalPlaceholder();
          });
        });

        // Validates and advances to stage 5 (never saves). GT.recurInterval is
        // already kept current by the keystroke handler above.
        document.getElementById('gtWizardSave').addEventListener('click', function () {
          if (!validateRecurField(true)) return;
          GT.wizardStage = 5;
          renderWizard();
        });
      }

      // Like validateTargetField, against 1..MAX_RECUR_INTERVAL, with the same
      // showEmptyAsInvalid quiet-while-typing/loud-at-save split.
      function validateRecurField(showEmptyAsInvalid) {
        var input = document.getElementById('gtRecurInterval');
        if (!input) return false;
        var raw = input.value.trim();
        if (raw === '') { input.classList.toggle('invalid', !!showEmptyAsInvalid); return false; }
        var n = Number(raw);
        var ok = Number.isInteger(n) && n >= 1 && n <= MAX_RECUR_INTERVAL;
        input.classList.toggle('invalid', !ok);
        return ok;
      }

      var RECUR_START_MASK = 'dddd-dd-dd dd:dd';
      // All-underscores skeleton the field starts at and falls back to when
      // emptied; built from RECUR_START_MASK's length.
      var RECUR_START_BLANK = RECUR_START_MASK.replace(/d/g, '_');
      // Count of 'd' slots in the mask (12), computed once for
      // recurStartDigitsOnly and validateRecurStartField (partial vs. fully
      // filled).
      var RECUR_START_DIGIT_COUNT = (RECUR_START_MASK.match(/d/g) || []).length;

      function recurStartDigitsOnly(s) {
        return (s || '').replace(/\\D/g, '').slice(0, RECUR_START_DIGIT_COUNT);
      }

      function recurStartMaskFromDigits(digits) {
        var out = '', di = 0;
        for (var i = 0; i < RECUR_START_MASK.length; i++) {
          if (RECUR_START_MASK[i] === 'd') {
            out += di < digits.length ? digits[di] : '_';
            di++;
          } else {
            out += RECUR_START_MASK[i];
          }
        }
        return out;
      }

      function applyRecurStartMask(input) {
        var digits = recurStartDigitsOnly(input.value);
        input.value = recurStartMaskFromDigits(digits);
        // Cursor lands after the last filled digit, as in Loot Tracker's
        // applyDateMask.
        var pos = 0, di = 0;
        for (var i = 0; i < RECUR_START_MASK.length; i++) {
          if (RECUR_START_MASK[i] === 'd' && di < digits.length) { pos = i + 1; di++; }
        }
        input.setSelectionRange(pos, pos);
        input.classList.remove('invalid');
      }

      // Requires a real calendar date and clock time (rejects "2024-13-40
      // 25:99"); like Loot Tracker's isValidIsoDate plus an hour/minute check.
      function isValidRecurStartDateTime(s) {
        var m = /^(\\d{4})-(\\d{2})-(\\d{2}) (\\d{2}):(\\d{2})$/.exec(s || '');
        if (!m) return false;
        var year = parseInt(m[1], 10), month = parseInt(m[2], 10), day = parseInt(m[3], 10);
        var hour = parseInt(m[4], 10), minute = parseInt(m[5], 10);
        if (month < 1 || month > 12) return false;
        var daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
        if (day < 1 || day > daysInMonth) return false;
        return hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59;
      }

      // Like validateRecurField for the masked field; always valid while NOW is
      // picked. An incomplete value is quiet (gated by showEmptyAsInvalid),
      // since red on every keystroke reads as broken. Only Save passes true.
      function validateRecurStartField(showIncompleteAsInvalid) {
        if (GT.recurStart !== 'custom') return true;
        var input = document.getElementById('gtRecurStartInput');
        if (!input) return false;
        if (recurStartDigitsOnly(input.value).length < RECUR_START_DIGIT_COUNT) {
          input.classList.toggle('invalid', !!showIncompleteAsInvalid);
          return false;
        }
        var ok = isValidRecurStartDateTime(input.value.trim());
        input.classList.toggle('invalid', !ok);
        return ok;
      }

      // Converts the masked local "YYYY-MM-DD HH:MM" to the ISO UTC string
      // payload.recur_start_at expects (GoalCreateRequest in app/schemas.py):
      // new Date(y, m-1, d, h, min) reads local time, toISOString() gives UTC.
      // Call after isValidRecurStartDateTime passes.
      function recurStartIsoFromMasked(s) {
        var m = /^(\\d{4})-(\\d{2})-(\\d{2}) (\\d{2}):(\\d{2})$/.exec(s || '');
        if (!m) return null;
        var d = new Date(
          parseInt(m[1], 10), parseInt(m[2], 10) - 1, parseInt(m[3], 10),
          parseInt(m[4], 10), parseInt(m[5], 10)
        );
        return d.toISOString();
      }

      function nowRecurStartMasked() {
        var d = new Date();
        function pad2(n) { return (n < 10 ? '0' : '') + n; }
        return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) +
          ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
      }

      function wireStartStage() {
        document.getElementById('gtWizardBack').addEventListener('click', wizardBack);
        document.getElementById('gtWizardCancel').addEventListener('click', closeWizard);

        var input = document.getElementById('gtRecurStartInput');
        input.addEventListener('input', function () {
          applyRecurStartMask(input);
          GT.recurStartAt = input.value;
          validateRecurStartField();
        });

        document.querySelectorAll('.gt-recur-start-btn').forEach(function (btn) {
          btn.addEventListener('click', function () {
            var newStart = btn.getAttribute('data-start');
            if (newStart === GT.recurStart) return;
            GT.recurStart = newStart;
            document.querySelectorAll('.gt-recur-start-btn').forEach(function (b) {
              b.classList.toggle('active', b === btn);
            });
            input.disabled = (newStart !== 'custom');
            input.placeholder = (newStart === 'custom') ? 'YYYY-MM-DD HH:MM' : 'Start now';
            input.classList.remove('invalid');
            if (newStart === 'custom') {
              // Prefill with the current time only the first time CUSTOM is
              // picked (GT.recurStartAt empty); see nowRecurStartMasked.
              if (!GT.recurStartAt) {
                input.value = nowRecurStartMasked();
                GT.recurStartAt = input.value;
              } else {
                input.value = GT.recurStartAt;
              }
              input.focus();
            } else {
              input.value = '';
            }
          });
        });

        document.getElementById('gtWizardSave').addEventListener('click', wizardAddGoal);
      }

      function currentTargetBounds() {
        if (GT.type === 'kc') return TARGET_BOUNDS.kc;
        if (GT.type === 'skill') return (GT.skillMetric === 'xp') ? TARGET_BOUNDS.skill_xp : TARGET_BOUNDS.skill_level;
        return TARGET_BOUNDS.item;
      }

      function updateWizardTargetField() {
        document.getElementById('gtTargetValue').placeholder = wizardTargetPlaceholder();
      }

      // Live range check for the target field (mirrors Mindmaps'
      // validateSkillTarget; server re-validates). Goes through parseMoneySuffix
      // so "150k" does not flash. Invalid is a red border only; empty is neutral
      // while typing but invalid on Save (showEmptyAsInvalid).
      function validateTargetField(showEmptyAsInvalid) {
        var input = document.getElementById('gtTargetValue');
        if (!input) return false;
        var raw = input.value.trim();
        if (raw === '') { input.classList.toggle('invalid', !!showEmptyAsInvalid); return false; }
        var n = Number(parseMoneySuffix(raw));
        var bounds = currentTargetBounds();
        var ok = Number.isInteger(n) && n >= bounds.min && n <= bounds.max;
        input.classList.toggle('invalid', !ok);
        return ok;
      }

      // The stage-3 name/value (wizardTarget) and the cadence were validated on
      // earlier stages and their DOM is gone; only the CUSTOM start field is
      // validated here.
      async function wizardAddGoal() {
        var payload = { goal_type: GT.type, target_name: wizardTarget.name, target_value: wizardTarget.value };
        if (GT.type === 'skill') { payload.metric = GT.skillMetric; }
        if (GT.type === 'item' && wizardTarget.itemId) { payload.item_id = wizardTarget.itemId; }
        if (GT.recurring === 'recurring') {
          if (!validateRecurStartField(true)) return;
          payload.is_recurring = true;
          payload.recur_interval = Number(GT.recurInterval);
          payload.recur_unit = GT.recurUnit;
          if (GT.recurStart === 'custom') {
            payload.recur_start_at = recurStartIsoFromMasked(document.getElementById('gtRecurStartInput').value.trim());
          }
        } else if (targetModeApplies()) {
          payload.target_mode = GT.targetMode;
        }

        var data = await apiCall('/api/goals', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
        if (!data) return;
        GT.goals.push(data);
        // A new goal changes the list; see resetGoalTrackingShareState.
        resetGoalTrackingShareState();
        renderGoalList();
        closeWizard();
      }

      // Goal list

      function goalName(g) {
        if (g.goal_type === 'skill') return g.target_name.charAt(0).toUpperCase() + g.target_name.slice(1);
        return g.target_name;
      }

      // Live current/target progress in the goal's unit ("LVL" prefix, "XP"/"KC"
      // suffix, none for items), followed by a recurring goal's cadence;
      // g.current_value is already this period's progress.
      function goalProgressLabel(g) {
        var cur = fmtNum(g.current_value);
        var tgt = fmtNum(g.target_value);
        var base;
        if (g.goal_type === 'kc') base = cur + ' / ' + tgt + ' KC';
        else if (g.goal_type === 'skill') base = (g.metric === 'xp') ? (cur + ' / ' + tgt + ' XP') : ('LVL ' + cur + ' / ' + tgt);
        else base = cur + ' / ' + tgt;
        var cadence = recurCadenceLabel(g);
        var info = goalInfoIconHtml(g);
        return cadence ? (base + ' · ' + cadence + info) : (base + info);
      }

      var RECUR_UNIT_LABEL = { hour: 'HOUR', day: 'DAY', week: 'WEEK', month: 'MONTH', year: 'YEAR' };
      function recurCadenceLabel(g) {
        if (!g.is_recurring) return '';
        var unit = RECUR_UNIT_LABEL[g.recur_unit] || String(g.recur_unit || '').toUpperCase();
        if (g.recur_interval === 1) return 'EVERY ' + unit;
        return 'EVERY ' + fmtNum(g.recur_interval) + ' ' + unit + 'S';
      }

      var RECUR_UNIT_SECONDS = { hour: 3600, day: 86400, week: 7 * 86400, month: 30 * 86400, year: 365 * 86400 };

      // Unit/letter pairs (Y, M, W, D, H, M) by greedy decomposition with
      // RECUR_UNIT_SECONDS, matching goalInfoIconHtml. Zero units are omitted
      // unless all are zero ("0M"); negative input clamps to zero. Not
      // zero-padded.
      function fmtRecurCountdown(totalSeconds) {
        var sec = Math.max(0, Math.round(totalSeconds));
        var y = Math.floor(sec / RECUR_UNIT_SECONDS.year); sec -= y * RECUR_UNIT_SECONDS.year;
        var mo = Math.floor(sec / RECUR_UNIT_SECONDS.month); sec -= mo * RECUR_UNIT_SECONDS.month;
        var w = Math.floor(sec / RECUR_UNIT_SECONDS.week); sec -= w * RECUR_UNIT_SECONDS.week;
        var d = Math.floor(sec / RECUR_UNIT_SECONDS.day); sec -= d * RECUR_UNIT_SECONDS.day;
        var h = Math.floor(sec / 3600); sec -= h * 3600;
        var mi = Math.floor(sec / 60);
        var units = [[y, 'Y'], [mo, 'M'], [w, 'W'], [d, 'D'], [h, 'H'], [mi, 'M']];
        var shown = units.filter(function (u) { return u[0] !== 0; });
        if (!shown.length) shown = [units[units.length - 1]];
        return shown.map(function (u) { return u[0] + u[1]; }).join(' ');
      }

      // The hoverable "i" (a title attribute): recurring goals show "Resets in
      // [countdown]", one-time GAIN goals show "Started at [baseline] [UNIT]"
      // (g.baseline_value, kc and xp-skill only). Returns '' otherwise.
      function goalInfoIconHtml(g) {
        var tooltip = null;
        if (g.is_recurring && g.recur_period_start) {
          var unitSeconds = RECUR_UNIT_SECONDS[g.recur_unit];
          if (unitSeconds) {
            var periodStartMs = new Date(g.recur_period_start).getTime();
            var periodEndMs = periodStartMs + g.recur_interval * unitSeconds * 1000;
            var remainingSeconds = (periodEndMs - Date.now()) / 1000;
            tooltip = 'Resets in ' + fmtRecurCountdown(remainingSeconds);
          }
        } else if (!g.is_recurring && g.baseline_value != null) {
          var unit = (g.goal_type === 'kc') ? ' KC' : (g.goal_type === 'skill' && g.metric === 'xp') ? ' XP' : '';
          tooltip = 'Started at ' + fmtNum(g.baseline_value) + unit;
        }
        if (!tooltip) return '';
        return '<span class="gt-goal-info-icon" title="' + escapeHtml(tooltip) + '">' +
          '<svg width="11" height="11" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
          '<circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.3"/>' +
          '<path d="M8 7.3V11.4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>' +
          '<circle cx="8" cy="4.9" r="0.9" fill="currentColor"/>' +
          '</svg>' +
          '</span>';
      }

      function goalIconSrc(g) {
        if (g.goal_type === 'kc') {
          var slug = BOSS_SLUG_BY_NAME[g.target_name];
          if (slug) return '/static/boss-icons/' + slug + '.png';
        } else if (g.goal_type === 'skill') {
          return '/static/skill-icons/' + g.target_name + '.png';
        } else if (g.goal_type === 'item' && g.item_icon) {
          return g.item_icon;
        }
        return TYPE_ICON[g.goal_type];
      }

      // Delete button: the first click (delegated on #gtGoalList) arms
      // gt-goal-delete--confirm, a second calls deleteGoal. customMode adds
      // draggable/data-goal-id; the icon has draggable="false" so a drag grabs
      // the row.
      function goalRowHtml(g, customMode) {
        // Uses g.progress_pct (computed in xp server-side,
        // app.goals.progress_pct) rather than current/target, since a
        // LEVEL-metric goal's levels are not linear in effort.
        var pct = g.progress_pct;
        var done = g.current_value >= g.target_value;
        var rowCls = 'gt-goal-row' + (done ? ' gt-goal-done' : '') + (customMode ? ' draggable' : '');
        var draggableAttr = customMode ? ' draggable="true"' : '';
        return '' +
          '<div class="' + rowCls + '" data-goal-id="' + g.id + '"' + draggableAttr + '>' +
          '  <img class="gt-goal-icon" src="' + goalIconSrc(g) + '" alt="" draggable="false" />' +
          '  <div class="gt-goal-info">' +
          '    <div class="gt-goal-headline">' +
          '      <span class="gt-goal-name">' + escapeHtml(goalName(g)) + '</span>' +
          '      <span class="gt-goal-sub">' + goalProgressLabel(g) + '</span>' +
          '    </div>' +
          '    <div class="gt-goal-bar"><div class="gt-goal-bar-fill" style="width:' + pct + '%"></div></div>' +
          '  </div>' +
          '  <button type="button" class="gt-goal-delete" data-goal-id="' + g.id + '" data-tooltip="Delete goal" aria-label="Delete goal">' +
          '    <svg class="gt-goal-delete-icon" width="15" height="15" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
          '      <path d="M2 4H14" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>' +
          '      <path d="M6 4V2.5C6 2.22386 6.22386 2 6.5 2H9.5C9.77614 2 10 2.22386 10 2.5V4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>' +
          '      <path d="M3.5 4L4.1 13.2C4.13 13.66 4.51 14 4.97 14H11.03C11.49 14 11.87 13.66 11.9 13.2L12.5 4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>' +
          '      <path d="M6.5 6.5V11.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>' +
          '      <path d="M9.5 6.5V11.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>' +
          '    </svg>' +
          '    <span class="gt-goal-delete-confirm">Are you sure?</span>' +
          '  </button>' +
          '</div>';
      }

      // Powers #gtSortTabs (GT.sortMode); sorts a copy. Server twin:
      // GOAL_SORT_MODES in app/schemas.py. 'custom' uses g.sort_order;
      // never-dragged goals sort last, oldest first.
      function sortGoals(list, sortMode) {
        var out = list.slice();
        function byNameAsc(a, b) { return goalName(a).toLowerCase().localeCompare(goalName(b).toLowerCase()); }
        function byType(a, b) {
          var byT = GOAL_TYPE_SORT_ORDER[a.goal_type] - GOAL_TYPE_SORT_ORDER[b.goal_type];
          return byT !== 0 ? byT : byNameAsc(a, b);
        }
        if (sortMode === 'progress_desc') {
          out.sort(function (a, b) { return b.progress_pct - a.progress_pct; });
        } else if (sortMode === 'progress_asc') {
          out.sort(function (a, b) { return a.progress_pct - b.progress_pct; });
        } else if (sortMode === 'type_asc') {
          out.sort(byType);
        } else if (sortMode === 'type_desc') {
          out.sort(function (a, b) { return -byType(a, b); });
        } else if (sortMode === 'reverse_alphabetical') {
          out.sort(function (a, b) { return -byNameAsc(a, b); });
        } else if (sortMode === 'recent') {
          out.sort(function (a, b) { return new Date(b.created_at) - new Date(a.created_at); });
        } else if (sortMode === 'oldest') {
          out.sort(function (a, b) { return new Date(a.created_at) - new Date(b.created_at); });
        } else if (sortMode === 'custom') {
          out.sort(function (a, b) {
            if (a.sort_order == null && b.sort_order == null) return new Date(a.created_at) - new Date(b.created_at);
            if (a.sort_order == null) return 1;
            if (b.sort_order == null) return -1;
            return a.sort_order - b.sort_order;
          });
        } else {
          out.sort(byNameAsc);
        }
        return out;
      }

      // Maps the 9 persisted sort_mode strings to and from {metric, dir} pairs
      // for the 5-button row. Keyed by full mode string since they do not all
      // follow "metric-dir" ("reverse_alphabetical"); custom has no direction.
      var SORT_MODE_METRIC = {
        progress_desc: { metric: 'progress', dir: 'desc' },
        progress_asc: { metric: 'progress', dir: 'asc' },
        type_desc: { metric: 'type', dir: 'desc' },
        type_asc: { metric: 'type', dir: 'asc' },
        alphabetical: { metric: 'alpha', dir: 'asc' },
        reverse_alphabetical: { metric: 'alpha', dir: 'desc' },
        recent: { metric: 'time', dir: 'desc' },
        oldest: { metric: 'time', dir: 'asc' },
      };
      var SORT_METRIC_MODE = {
        progress: { asc: 'progress_asc', desc: 'progress_desc' },
        type: { asc: 'type_asc', desc: 'type_desc' },
        alpha: { asc: 'alphabetical', desc: 'reverse_alphabetical' },
        time: { asc: 'oldest', desc: 'recent' },
      };
      // Direction a metric starts at on a fresh click: alpha ascending, every
      // other metric descending (as in Loot Tracker's SORT_METRIC_DEFAULT_DIR).
      var SORT_METRIC_DEFAULT_DIR = { progress: 'desc', type: 'desc', alpha: 'asc', time: 'desc' };

      function updateSortTabs() {
        var active = SORT_MODE_METRIC[GT.sortMode];
        document.querySelectorAll('#gtSortTabs .gt-sort-tab').forEach(function (b) {
          var metric = b.getAttribute('data-sort-metric');
          // !!(...) is required: active is undefined for 'custom', and
          // classList.toggle('active', undefined) flips the class instead of
          // forcing it off, leaving a metric button stuck active after Custom is
          // picked.
          var isActive = !!(metric ? (active && active.metric === metric) : (b.getAttribute('data-sort') === GT.sortMode));
          b.classList.toggle('active', isActive);
          var arrow = b.querySelector('.gt-sort-arrow');
          if (arrow) arrow.textContent = isActive && active ? (active.dir === 'asc' ? ' ↑' : ' ↓') : '';
        });
      }

      function applyGoalsResponse(data) {
        GT.goals = data.goals || [];
        GT.sortMode = data.sort_mode || GT.sortMode;
        updateSortTabs();
        renderGoalList();
      }

      // Rows are draggable only in "custom" sort mode. Skips the rebuild when
      // GT.sortMode + GT.goals match what is on screen (GT.renderKey): the
      // 5-second poll calls this every tick, and recreating each row's <img>
      // flickers. The recur-countdown tooltip can go stale meanwhile
      // (hover-only).
      function renderGoalList() {
        var listEl = document.getElementById('gtGoalList');
        var emptyEl = document.getElementById('gtEmpty');
        var sortTabsEl = document.getElementById('gtSortTabs');
        if (!GT.goals.length) {
          GT.renderKey = GT.sortMode + '|[]';
          listEl.innerHTML = '';
          emptyEl.style.display = '';
          sortTabsEl.style.display = 'none';
          return;
        }
        var renderKey = GT.sortMode + '|' + JSON.stringify(GT.goals);
        if (renderKey === GT.renderKey) return;
        GT.renderKey = renderKey;
        emptyEl.style.display = 'none';
        sortTabsEl.style.display = '';
        var customMode = GT.sortMode === 'custom';
        var sorted = sortGoals(GT.goals, GT.sortMode);
        listEl.innerHTML = sorted.map(function (g) { return goalRowHtml(g, customMode); }).join('');
        fixGoalNameMinWidths(listEl);
        wireGoalDrag(customMode);
        // Touch screens never show a native title tooltip, so the info icon's
        // text goes in data-tooltip for the shared tap-tooltip script.
        if (GT_TOUCH) {
          listEl.querySelectorAll('.gt-goal-info-icon[title]').forEach(function (ic) {
            ic.setAttribute('data-tooltip', ic.getAttribute('title'));
            ic.removeAttribute('title');
          });
        }
      }

      // Keeps the gap between a goal's title and progress readout constant:
      // .gt-goal-name has min-width: 48px (goal-tracking.css), which pads short
      // titles. The floor is lowered per row to the measured title width (reused
      // canvas 2D context; character counts are unreliable in this bitmap font).
      // Runs after each rebuild.
      var goalNameMeasureCtx = document.createElement('canvas').getContext('2d');
      var ON_LANDING = document.body.classList.contains('landing');
      var GT_TOUCH = !!(window.matchMedia && window.matchMedia('(hover: none)').matches);
      var GT_GOAL_NAME_MIN_WIDTH = 48; // matches .gt-goal-name's own min-width in goal-tracking.css
      function fixGoalNameMinWidths(listEl) {
        listEl.querySelectorAll('.gt-goal-name').forEach(function (el) {
          var cs = getComputedStyle(el);
          goalNameMeasureCtx.font = cs.fontStyle + ' ' + cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
          var natural = goalNameMeasureCtx.measureText(el.textContent).width;
          el.style.minWidth = Math.min(GT_GOAL_NAME_MIN_WIDTH, natural) + 'px';
        });
      }

      // Persists the active sort tab (GameAccount.goal_sort_mode): PUT, then
      // apply the response (as setStillToPurchaseSort does), not optimistically.
      async function setGoalSortMode(mode) {
        var data = await apiCall('/api/goals/sort-mode', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sort_mode: mode }),
        });
        if (data) applyGoalsResponse(data);
      }

      document.getElementById('gtSortTabs').addEventListener('click', function (e) {
        var btn = e.target.closest('.gt-sort-tab');
        if (!btn) return;
        var metric = btn.getAttribute('data-sort-metric');
        var mode;
        if (!metric) {
          // Custom has no direction, just its literal mode string.
          mode = btn.getAttribute('data-sort');
        } else {
          var current = SORT_MODE_METRIC[GT.sortMode];
          var dir = (current && current.metric === metric)
            ? (current.dir === 'asc' ? 'desc' : 'asc')
            : SORT_METRIC_DEFAULT_DIR[metric];
          mode = SORT_METRIC_MODE[metric][dir];
        }
        if (mode === GT.sortMode) return;
        setGoalSortMode(mode);
      });
      updateSortTabs();

      // Delegated on the list container (survives the per-poll rebuild). First
      // click arms a delete button ("Are you sure?"), a second deletes; clicking
      // elsewhere disarms, so one row is mid-confirm at a time.
      document.getElementById('gtGoalList').addEventListener('click', function (e) {
        var btn = e.target.closest('.gt-goal-delete');
        if (!btn) return;
        if (btn.classList.contains('gt-goal-delete--confirm')) {
          deleteGoal(btn.getAttribute('data-goal-id'));
          return;
        }
        document.querySelectorAll('.gt-goal-delete--confirm').forEach(function (b) {
          b.classList.remove('gt-goal-delete--confirm');
        });
        btn.classList.add('gt-goal-delete--confirm');
      });

      document.addEventListener('click', function (e) {
        if (e.target.closest('.gt-goal-delete')) return;
        document.querySelectorAll('.gt-goal-delete--confirm').forEach(function (b) {
          b.classList.remove('gt-goal-delete--confirm');
        });
      });

      async function deleteGoal(goalId) {
        var data = await apiCall('/api/goals/' + encodeURIComponent(goalId), { method: 'DELETE' });
        if (data === null) return;
        GT.goals = GT.goals.filter(function (g) { return g.id !== goalId; });
        resetGoalTrackingShareState();
        renderGoalList();
      }

      // Nudges the CUSTOM sort tab (like glowCustomSortButton in Purchase Goals)
      // when a row is pressed outside Custom mode, where drag does nothing.
      // Removes the class, forces a reflow and re-adds it so the pulse restarts.
      function glowCustomSortTab() {
        var btn = document.querySelector('#gtSortTabs .gt-sort-tab[data-sort="custom"]');
        if (!btn) return;
        btn.classList.remove('glow');
        void btn.offsetWidth;
        btn.classList.add('glow');
      }

      function wireGoalDrag(customMode) {
        var listEl = document.getElementById('gtGoalList');
        if (!customMode) {
          // Rows outside Custom have no draggable attribute, so only a plain
          // press reaches here. Ignores presses on .gt-goal-delete, which should
          // not glow the CUSTOM tab.
          if (GT_TOUCH) return;
          listEl.querySelectorAll('.gt-goal-row').forEach(function (el) {
            el.addEventListener('pointerdown', function (e) {
              if (e.target.closest('.gt-goal-delete')) return;
              glowCustomSortTab();
            });
          });
          return;
        }
        var draggedEl = null;
        var dropped = false;

        function rowKey(row) { return row.getAttribute('data-goal-id'); }

        function animateReorder(mutate) {
          var rows = Array.prototype.slice.call(listEl.querySelectorAll('.gt-goal-row'));
          var firstRects = {};
          rows.forEach(function (row) { firstRects[rowKey(row)] = row.getBoundingClientRect(); });

          mutate();

          rows.forEach(function (row) {
            if (row === draggedEl) return;
            var first = firstRects[rowKey(row)];
            var last = row.getBoundingClientRect();
            var dy = first.top - last.top;
            if (!dy) return;
            row.style.transition = 'none';
            row.style.transform = 'translateY(' + dy + 'px)';
            row.getBoundingClientRect();
            row.style.transition = 'transform 150ms ease';
            row.style.transform = '';
            row.addEventListener('transitionend', function handler() {
              row.style.transition = '';
              row.removeEventListener('transitionend', handler);
            });
          });
        }

        // The live preview already leaves the DOM in the order to save; just
        // read the rows back.
        async function commitDomOrder() {
          var order = Array.prototype.slice.call(listEl.querySelectorAll('.gt-goal-row')).map(rowKey);
          var data = await apiCall('/api/goals/reorder', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order: order }),
          });
          if (data) applyGoalsResponse(data);
        }

        listEl.querySelectorAll('.gt-goal-row').forEach(function (el) {
          el.addEventListener('dragstart', function (e) {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', el.getAttribute('data-goal-id'));
            draggedEl = el;
            dropped = false;
            el.classList.add('dragging');
          });
          el.addEventListener('dragend', function () {
            el.classList.remove('dragging');
            draggedEl = null;
            // A drag that ends without a drop (outside the list, or Escape)
            // leaves the preview DOM order unsaved; re-rendering from GT.goals
            // snaps it back.
            if (!dropped) renderGoalList();
          });
          el.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            if (!draggedEl || draggedEl === el) return;
            var rect = el.getBoundingClientRect();
            var before = e.clientY < rect.top + rect.height / 2;
            var alreadyBefore = el.previousElementSibling === draggedEl;
            var alreadyAfter = el.nextElementSibling === draggedEl;
            if (before ? alreadyBefore : alreadyAfter) return;
            animateReorder(function () {
              listEl.insertBefore(draggedEl, before ? el : el.nextSibling);
            });
          });
          el.addEventListener('drop', function (e) {
            e.preventDefault();
            dropped = true;
            commitDomOrder();
          });
        });
      }

      var gtShareIconBtn = document.getElementById('gtShareIconBtn');
      var gtShareCard = document.getElementById('gtShareCard');
      if (gtShareIconBtn) {
        function setGtShareOpen(open) {
          gtShareCard.hidden = !open;
          gtShareIconBtn.classList.toggle('open', open);
        }
        gtShareIconBtn.addEventListener('click', function () {
          setGtShareOpen(gtShareCard.hidden);
        });
        document.addEventListener('click', function (e) {
          var wrap = document.querySelector('.gt-share-wrap');
          if (wrap && !wrap.contains(e.target)) setGtShareOpen(false);
        });
      }

      function resetGoalTrackingShareState() {
        var genBtn = document.getElementById('gtShareGenerateBtn');
        var linkBtn = document.getElementById('gtShareLinkBtn');
        if (!genBtn || !linkBtn) return;
        genBtn.hidden = false;
        genBtn.disabled = false;
        genBtn.classList.remove('action-failed');
        linkBtn.hidden = true;
        linkBtn.textContent = '';
        delete linkBtn.dataset.url;
      }

      // GENERATE SHAREABLE LINK: freezes the whole goal list into a
      // SharedContent row (POST /api/goals/share, app/main.py); no id to pick.
      // Null-guarded like gtShareIconBtn (see mmShareGenerateBtn).
      var gtShareGenerateBtn = document.getElementById('gtShareGenerateBtn');
      if (gtShareGenerateBtn) {
        gtShareGenerateBtn.addEventListener('click', function () {
          var btn = this;
          btn.disabled = true;
          fetch('/api/goals/share', { method: 'POST' })
            .then(function (res) { return res.ok ? res.json() : Promise.reject(); })
            .then(function (data) {
              var linkBtn = document.getElementById('gtShareLinkBtn');
              linkBtn.dataset.url = data.url;
              linkBtn.textContent = data.url;
              btn.hidden = true;
              linkBtn.hidden = false;
            })
            .catch(function () {
              btn.classList.add('action-failed');
              setTimeout(function () { btn.classList.remove('action-failed'); }, 2500);
            })
            .then(function () { btn.disabled = false; });
        });
      }

      var gtShareLinkBtn = document.getElementById('gtShareLinkBtn');
      if (gtShareLinkBtn) {
        gtShareLinkBtn.addEventListener('click', function () {
          var btn = this;
          var url = btn.dataset.url;
          if (!url) return;
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url);
          } else {
            var temp = document.createElement('textarea');
            temp.value = url;
            temp.style.position = 'fixed';
            temp.style.opacity = '0';
            document.body.appendChild(temp);
            temp.select();
            document.execCommand('copy');
            document.body.removeChild(temp);
          }
          btn.textContent = 'COPIED';
          setTimeout(function () { btn.textContent = url; }, 1200);
        });
      }

      // Load + poll (5s like PG.pollTimer/loadSummary); one endpoint serves the
      // initial paint and refreshes.

      async function loadGoals() {
        if (GT.dragging) return; // a touch long-press drag is in flight
        var data = await apiCall('/api/goals');
        if (!data || GT.dragging) return;
        applyGoalsResponse(data);
      }


      // Touch only (real page and homepage preview)
      if (GT_TOUCH) {
        // Tap tooltips: only the info icon has content. On the homepage this
        // filter is shared with the other previews, whose tooltips stay.
        window.myscapeTouchTooltipFilter = function (el) {
          if (ON_LANDING && !(el.closest && el.closest('.landing-goal-tracking-preview'))) return true;
          return !(el.closest && el.closest('.gt-sort-tab, .gt-share-icon-btn, .gt-share-link-btn, .gt-goal-delete'));
        };

        // Keyboard: keep a focused text field (and some of its suggestion list)
        // above the on-screen keyboard.
        (function () {
          var vv = window.visualViewport;
          var pending = null;
          function isTextField(el) {
            return !!el && el.tagName === 'INPUT' && /^(text|search|number|tel|)$/.test(el.type || '');
          }
          function reveal() {
            var el = document.activeElement;
            if (!isTextField(el)) return;
            var viewTop = vv ? vv.offsetTop : 0;
            var viewBottom = viewTop + (vv ? vv.height : window.innerHeight);
            var r = el.getBoundingClientRect();
            var need = r.bottom + 16;
            var sug = document.querySelector('.gt-suggestions.show');
            if (sug) need = Math.min(sug.getBoundingClientRect().bottom, r.bottom + 170) + 8;
            var dy = need - viewBottom;
            if (dy > 0) {
              dy = Math.min(dy, Math.max(0, r.top - viewTop - 8));
              if (dy > 0) window.scrollBy({ top: dy, left: 0, behavior: 'smooth' });
            } else if (r.top < viewTop + 8) {
              window.scrollBy({ top: r.top - viewTop - 8, left: 0, behavior: 'smooth' });
            }
          }
          function schedule(delay) { clearTimeout(pending); pending = setTimeout(reveal, delay); }
          document.addEventListener('focusin', function (e) {
            if (!isTextField(e.target)) return;
            schedule(150); setTimeout(reveal, 450); setTimeout(reveal, 800);
          });
          document.addEventListener('input', function (e) {
            if (isTextField(e.target)) schedule(450);
          });
          if (vv) vv.addEventListener('resize', function () {
            if (isTextField(document.activeElement)) schedule(60);
          });
        })();

        // Long-press drag (Custom sort): a ~0.35s hold fires the same drag
        // events at the same handlers (stand-in dataTransfer) with a ghost copy,
        // since HTML5 drag is unreliable from a finger.
        (function () {
          var HOLD_MS = 350, MOVE_TOL = 10, EDGE = 90;
          var st = null;
          var SOURCE_SEL = '#gtGoalList .gt-goal-row[draggable="true"]';
          function makeDT() {
            var d = {};
            return {
              effectAllowed: 'none', dropEffect: 'none', types: [],
              setData: function (k, v) { d[k] = String(v); },
              getData: function (k) { return d[k] || ''; },
              clearData: function () { d = {}; },
              setDragImage: function () {}
            };
          }
          function fire(type, target, x, y, dt) {
            var ev = new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window });
            Object.defineProperty(ev, 'dataTransfer', { value: dt });
            return target.dispatchEvent(ev);
          }
          function moveGhost() {
            if (!st || !st.ghost) return;
            st.ghost.style.left = (st.x - st.gx) + 'px';
            st.ghost.style.top = (st.y - st.gy) + 'px';
          }
          function hover() {
            if (!st || !st.active) return;
            var el = document.elementFromPoint(st.x, st.y);
            if (el !== st.over) {
              if (st.over) fire('dragleave', st.over, st.x, st.y, st.dt);
              st.over = el;
              if (el) fire('dragenter', el, st.x, st.y, st.dt);
            }
            if (el) fire('dragover', el, st.x, st.y, st.dt);
          }
          function scrollLoop() {
            if (!st || !st.active) return;
            var dy = 0;
            // Not on the homepage: its page is snap-scrolled screens and the
            // preview is one screen.
            if (ON_LANDING) { /* no edge auto-scroll */ }
            else if (st.y < EDGE) dy = -Math.ceil((EDGE - st.y) / 6);
            else if (st.y > window.innerHeight - EDGE) dy = Math.ceil((st.y - (window.innerHeight - EDGE)) / 6);
            if (dy) { window.scrollBy(0, dy); moveGhost(); hover(); }
            st.raf = requestAnimationFrame(scrollLoop);
          }
          function release(s) {
            if (s.src && s.wasDraggable != null) s.src.setAttribute('draggable', s.wasDraggable);
            GT.dragging = false;
          }
          function begin() {
            if (!st || st.active) return;
            if (!document.contains(st.src)) { st = null; GT.dragging = false; return; }
            st.active = true;
            fire('dragstart', st.src, st.x, st.y, st.dt);
            var r = st.src.getBoundingClientRect();
            var g = st.src.cloneNode(true);
            g.classList.remove('dragging');
            g.style.cssText = 'position:fixed;margin:0;pointer-events:none;z-index:9999;' +
              'width:' + r.width + 'px;height:' + r.height + 'px;transform:scale(1.03);box-sizing:border-box;' +
              'background:var(--panel);border:1px solid var(--gold-dim);opacity:1;' +
              'box-shadow:0 6px 18px rgba(0,0,0,0.5);transition:none;';
            document.body.appendChild(g);
            st.ghost = g; st.gx = st.x0 - r.left; st.gy = st.y0 - r.top;
            moveGhost();
            if (navigator.vibrate) { try { navigator.vibrate(12); } catch (err) {} }
            st.raf = requestAnimationFrame(scrollLoop);
          }
          function finish(doDrop) {
            if (!st) return;
            var s = st; st = null;
            clearTimeout(s.timer);
            release(s);
            if (!s.active) return;
            cancelAnimationFrame(s.raf);
            var el = document.elementFromPoint(s.x, s.y);
            if (doDrop && el) {
              var ok = fire('dragover', el, s.x, s.y, s.dt);
              if (ok === false) fire('drop', el, s.x, s.y, s.dt);
            } else if (s.over) {
              fire('dragleave', s.over, s.x, s.y, s.dt);
            }
            fire('dragend', s.src, s.x, s.y, s.dt);
            GT.dragging = false;
            if (s.ghost && s.ghost.parentNode) s.ghost.parentNode.removeChild(s.ghost);
          }
          document.addEventListener('touchstart', function (e) {
            if (st || e.touches.length !== 1) return;
            var src = e.target.closest && e.target.closest(SOURCE_SEL);
            if (!src || e.target.closest('.gt-goal-delete')) return;
            var t = e.touches[0];
            st = { src: src, x0: t.clientX, y0: t.clientY, x: t.clientX, y: t.clientY,
                   active: false, dt: makeDT(), over: null, ghost: null, raf: 0,
                   timer: setTimeout(begin, HOLD_MS) };
            GT.dragging = true; // hold off the 5s refresh for the whole gesture
            // Chrome on Android starts a native drag after ~0.5s, cancelling the
            // touch; switch it off for this touch.
            st.wasDraggable = src.getAttribute('draggable');
            src.setAttribute('draggable', 'false');
          }, { passive: true });
          document.addEventListener('touchmove', function (e) {
            if (!st) return;
            var t = e.touches[0];
            st.x = t.clientX; st.y = t.clientY;
            if (!st.active) {
              if (Math.abs(st.x - st.x0) > MOVE_TOL || Math.abs(st.y - st.y0) > MOVE_TOL) {
                clearTimeout(st.timer); release(st); st = null;
              }
              return;
            }
            e.preventDefault(); // hold page scroll while dragging
            moveGhost();
            hover();
          }, { passive: false });
          document.addEventListener('touchend', function (e) {
            if (st && st.active && e.cancelable) e.preventDefault();
            finish(true);
          }, { passive: false });
          document.addEventListener('touchcancel', function () { finish(false); });
          document.addEventListener('contextmenu', function (e) {
            if (st || (e.target.closest && e.target.closest(SOURCE_SEL))) e.preventDefault();
          });
          document.addEventListener('dragstart', function (e) {
            if (e.isTrusted && e.target.closest && e.target.closest(SOURCE_SEL)) e.preventDefault();
          }, true);
        })();
      }

      loadGoals();
      setInterval(loadGoals, 5000);
    })();
    """
    )
    return extra_head, body, script


def render_landing_goal_tracking_preview() -> Optional[Tuple[str, str, str]]:
    """The landing page's interactive Goal Tracking preview. Reuses the real
    _goal_tracking_panel_markup body/script unmodified, with demo-only
    behavior layered on by a wrapper script, backed by the curated snapshot
    app/data/landing_goal_tracking_demo.json. Returns (extra_head, body,
    script) for render_landing, or None if the snapshot is missing.
    
    Sort tabs and custom-mode drag-reorder work as on the real page. Disabled
    via this preview's CSS, not by editing the markup:
    - The add-goal wizard (#gtWizard): new goals need live account totals this
    demo cannot supply.
    - The row delete button (.gt-goal-delete) stays visible and hoverable, but
    a capture-phase click interceptor keeps clicks from the reused delegated
    listener. Other row clicks (select, drag) are untouched.
    
    The wrapper's fetch shim serves GET /api/goals from in-memory
    DEMO_GOALS/DEMO_SORT_MODE (mutated directly so changes survive the real
    page's 5-second loadGoals poll), plus PUT /api/goals/sort-mode and PUT
    /api/goals/reorder in the real {goals, sort_mode} shape (reorder sets the
    mode to "custom", as the server does). DELETE, GET /api/items/search and
    POST /api/goals are implemented but unreachable with the wizard and delete
    disabled; they keep the shim a complete stand-in. Anything else fails with
    "Not available in this preview" (shown via #gtError).
    
    No localStorage shadowing is needed; the 5-second poll is left running.
    """
    demo = _get_landing_goal_tracking_demo_data()
    if demo is None:
        return None
    search_pools = _get_landing_mindmap_search_pools_data()
    items_pool = (search_pools or {}).get("items") or []
    extra_head, body, script = _goal_tracking_panel_markup()

    # Hero row: tagline first, character second so he lands on the right (same
    # as the Loot Tracker and Mindmaps previews; Purchase Goals and Storages
    # Viewer put the character first). The reused "Goal Tracking" <h2> is hidden
    # via .landing-goal-tracking-preview .page-title.
    hero_markup = """
    <div class="gt-preview-hero">
      <picture class="gt-preview-char gt-preview-char--flipped">
        <source srcset="/static/img/landing-goal-tracking-preview-char.webp" type="image/webp">
        <img src="/static/img/landing-goal-tracking-preview-char.png" alt="" />
      </picture>
      <div class="gt-preview-tagline-wrap">
        <p class="gt-preview-tagline">
          <span class="gt-preview-tagline-gold">GOAL TRACKING</span> <span class="gt-preview-tagline-white">for those days when you need some dopamine.</span>
        </p>
      </div>
    </div>
    """
    body = hero_markup + body

    goals_json = json.dumps(demo.get("goals") or [])
    sort_mode_json = json.dumps(demo.get("sort_mode") or "alphabetical")
    items_pool_json = json.dumps(items_pool)
    wrapper_script = f"""
    (function () {{
      // Curated snapshot, shaped like the real GET /api/goals entries. Mutated
      // directly by the delete/sort-mode/reorder handlers so GET reflects what
      // the visitor has done.
      var DEMO_GOALS = {goals_json};
      var DEMO_SORT_MODE = {sort_mode_json};
      // Curated item pool shared with the Mindmaps preview.
      var DEMO_ITEMS_POOL = {items_pool_json};
      var ITEM_ICON_CDN_BASE = 'https://static.runelite.net/cache/item/icon/';

      // Startswith-then-contains ranking, same as the Mindmaps preview's
      // localSearchItems (copied, since each preview wrapper is self-contained).
      function localSearchItems(query) {{
        var q = String(query || '').trim().toLowerCase();
        if (!q) return [];
        var starts = [], contains = [];
        DEMO_ITEMS_POOL.forEach(function (item) {{
          var lname = item.name.toLowerCase();
          if (lname.indexOf(q) === 0) starts.push(item);
          else if (lname.indexOf(q) !== -1) contains.push(item);
        }});
        starts.sort(function (a, b) {{ return a.name.length - b.name.length; }});
        contains.sort(function (a, b) {{ return a.name.length - b.name.length; }});
        return starts.concat(contains).slice(0, 20).map(function (item) {{
          return {{ id: item.id, name: item.name, icon: ITEM_ICON_CDN_BASE + item.id + '.png' }};
        }});
      }}

      // fetch shim
      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        var qIndex = url.indexOf('?');
        var path = qIndex === -1 ? url : url.slice(0, qIndex);
        var params = new URLSearchParams(qIndex === -1 ? '' : url.slice(qIndex + 1));
        function ok(data) {{ return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(data); }} }}); }}
        function fail(detail) {{ return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{ detail: detail }}); }} }}); }}

        if (path === '/api/goals' && method === 'GET') {{
          return ok({{ goals: DEMO_GOALS, sort_mode: DEMO_SORT_MODE }});
        }}
        if (path === '/api/items/search' && method === 'GET') {{
          return ok({{ results: localSearchItems(params.get('q')) }});
        }}
        if (path === '/api/goals/sort-mode' && method === 'PUT') {{
          var modeBody = {{}};
          try {{ modeBody = opts.body ? JSON.parse(opts.body) : {{}}; }} catch (e) {{ modeBody = {{}}; }}
          if (modeBody.sort_mode) DEMO_SORT_MODE = modeBody.sort_mode;
          return ok({{ goals: DEMO_GOALS, sort_mode: DEMO_SORT_MODE }});
        }}
        if (path === '/api/goals/reorder' && method === 'PUT') {{
          var reorderBody = {{}};
          try {{ reorderBody = opts.body ? JSON.parse(opts.body) : {{}}; }} catch (e) {{ reorderBody = {{}}; }}
          var order = reorderBody.order || [];
          var byId = {{}};
          DEMO_GOALS.forEach(function (g) {{ byId[g.id] = g; }});
          order.forEach(function (id, index) {{
            if (byId[id]) byId[id].sort_order = index;
          }});
          DEMO_SORT_MODE = 'custom';
          return ok({{ goals: DEMO_GOALS, sort_mode: DEMO_SORT_MODE }});
        }}
        if (path.indexOf('/api/goals/') === 0 && method === 'DELETE') {{
          var delId = decodeURIComponent(path.slice('/api/goals/'.length));
          DEMO_GOALS = DEMO_GOALS.filter(function (g) {{ return g.id !== delId; }});
          return ok({{}});
        }}

        // Wizard Save (POST /api/goals) and anything else not handled above:
        // fail gracefully, never hit the network.
        return fail('Not available in this preview.');
      }};

      {script}

      // Make each row's delete button inert. A capturing-phase listener on
      // #gtGoalList fires before the reused bubble-phase delegated listener, so
      // stopPropagation keeps it from ever arming or confirming a delete. The
      // button still hovers and focuses normally; clicks elsewhere on the row
      // (select, drag) pass through.
      document.getElementById('gtGoalList').addEventListener('click', function (e) {{
        if (e.target.closest('.gt-goal-delete')) e.stopPropagation();
      }}, true);

      // Remove the share icon and its card (as the other previews do): a demo
      // visitor has no real goal list to freeze. Removed rather than hidden
      // since nothing depends on its layout space.
      var shareWrap = document.querySelector('.gt-share-wrap');
      if (shareWrap) shareWrap.remove();

      // Fixed-height container with an always-on bottom-edge feather, like the
      // other previews (see .landing-goal-tracking-preview in
      // goal-tracking.css).
    }})();
    """
    return extra_head, body, wrapper_script


def render_goal_tracking(player: PlayerView) -> str:
    """The Goal Tracking page: a player-built list of targets (boss kill count,
    skill level/xp, or item quantity), each with live progress.
    
    Not server-rendered with the goal list (PlayerView has no goals field and
    a query per request is wasteful). Like Purchase Goals and Possessions, it
    renders an empty shell that GET /api/goals fills on load and re-polls
    every 5 seconds.
    
    Unlinked players (player.account_hash is None) get a prompt to link
    instead, since /api/goals requires a verified, linked GameAccount.
    """
    extra_head = f'<link rel="stylesheet" href="/static/css/goal-tracking.css?v={_GOAL_TRACKING_CSS_VERSION}" />'
    is_linked = player.account_hash is not None

    if not is_linked:
        body = """
        <h2 class="page-title">Goal Tracking</h2>
        <div class="gt-card">
          <p class="gt-link-note">Link your RuneLite account to start tracking goals.</p>
        </div>
        """
        return _shell(title="Goal Tracking — myscape", player=player, body=body, extra_head=extra_head)

    extra_head, body, script = _goal_tracking_panel_markup()
    return _shell(
        title="Goal Tracking — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )


def render_goal_tracking_share(share: "SharedContent", game_account: Optional["GameAccount"], viewer: Optional[PlayerView]) -> str:
    """myscape.io/s/<code> for a Goal Tracking share: a read-only, frozen view of
    the sharer's entire goal list (see POST /api/goals/share and
    build_goal_tracking_share_snapshot in app/main.py), same contract as the
    other render_*_share pages.
    
    Reuses _goal_tracking_panel_markup unmodified behind a fetch shim serving
    GET /api/goals, PUT /api/goals/sort-mode and PUT /api/goals/reorder from
    an in-memory copy of the share's goals (mirrors the DEMO_GOALS shim in
    render_landing_goal_tracking_preview). Adjustments:
    - The add-goal wizard is hidden via CSS (.goal-tracking-share .gt-wizard).
    - The delete button stays visible but inert (same capture-phase
    interceptor as the landing preview); the goals belong to the sharer.
    - Sort tabs and drag-reorder stay live: they only change how the frozen
    snapshot is displayed.
    
    The reused "Goal Tracking" <h2> and export button are replaced by
    banner_markup (stripped via body.partition like the other share pages): a
    "GOAL TRACKING SNAPSHOT: YYYY-MM-DD" .subtitle line (share.created_at,
    UTC, rendered server-side), then "Shared by <name>" styled as .page-title
    with an import icon. Signed in, it opens the SAVE TO MY MYSCAPE popup;
    signed out, it is a plain <a> to /signup (see render_mindmap_share).
    
    game_account is the share's owner, looked up by the caller (GET /s/<code>
    in app/main.py); it can be None if that row was deleted, in which case the
    name falls back to "A player".
    """
    extra_head, body, script = _goal_tracking_panel_markup()
    # Strip the reused body's "Goal Tracking" <h2 class="page-title"> and its
    # export button (see banner_markup above). The body always opens with
    # exactly one such heading, so keeping only what follows the first "</h2>"
    # removes it.
    _, _, body = body.partition("</h2>")

    owner_name = (game_account.runescape_name if game_account else None) or "A player"
    snapshot_date = share.created_at.strftime("%Y-%m-%d")

    import_icon_svg = (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
        '<polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line>'
        '</svg>'
    )
    if viewer is not None:
        import_icon_btn = (
            ' <span class="gt-import-wrap">'
            '<button type="button" class="gt-import-icon-btn" id="gtImportBtn" aria-label="Save to your account" title="Save to your account">'
            f'{import_icon_svg}</button>'
            '<div class="gt-import-card" id="gtImportCard" hidden>'
            '<button type="button" class="gt-import-save-btn" id="gtImportSaveBtn">SAVE TO MY MYSCAPE</button>'
            '<p class="gt-import-popup-hint">CLICKING THE BUTTON ABOVE WILL SAVE ALL OF<br>THESE GOALS TO YOUR GOAL TRACKING APP.</p>'
            '</div>'
            '</span>'
        )
    else:
        import_icon_btn = (
            ' <a class="gt-import-icon-btn" href="/signup" aria-label="Sign up to save this" title="Sign up to save this">'
            f'{import_icon_svg}</a>'
        )

    banner_markup = f"""
    <p class="subtitle gt-share-label">GOAL TRACKING SNAPSHOT: {snapshot_date}</p>
    <h2 class="page-title">Shared by {escape(owner_name)}{import_icon_btn}</h2>
    """
    body = banner_markup + body
    body = f'<div class="goal-tracking-share">{body}</div>'

    payload_json = json.dumps(share.payload)
    wrapper_script = f"""
    (function () {{
      var PAYLOAD = {payload_json};

      // Mutable in-memory copy of the frozen goals, so sort-tab changes and
      // drags survive the real page's 5-second poll (loadGoals replaces GT.goals
      // wholesale each tick). Same pattern as DEMO_GOALS in the landing preview.
      var currentGoals = PAYLOAD.goals || [];
      var currentSortMode = PAYLOAD.sortMode || 'alphabetical';

      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        var qIndex = url.indexOf('?');
        var path = qIndex === -1 ? url : url.slice(0, qIndex);
        function ok(data) {{ return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(data); }} }}); }}
        function fail(detail) {{ return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{ detail: detail }}); }} }}); }}

        if (path === '/api/goals' && method === 'GET') {{
          return ok({{ goals: currentGoals, sort_mode: currentSortMode }});
        }}
        if (path === '/api/goals/sort-mode' && method === 'PUT') {{
          var modeBody = {{}};
          try {{ modeBody = opts.body ? JSON.parse(opts.body) : {{}}; }} catch (e) {{ modeBody = {{}}; }}
          if (modeBody.sort_mode) currentSortMode = modeBody.sort_mode;
          return ok({{ goals: currentGoals, sort_mode: currentSortMode }});
        }}
        if (path === '/api/goals/reorder' && method === 'PUT') {{
          var reorderBody = {{}};
          try {{ reorderBody = opts.body ? JSON.parse(opts.body) : {{}}; }} catch (e) {{ reorderBody = {{}}; }}
          var order = reorderBody.order || [];
          var byId = {{}};
          currentGoals.forEach(function (g) {{ byId[g.id] = g; }});
          order.forEach(function (id, index) {{
            if (byId[id]) byId[id].sort_order = index;
          }});
          currentSortMode = 'custom';
          return ok({{ goals: currentGoals, sort_mode: currentSortMode }});
        }}
        if (path.indexOf('/api/goals/') === 0 && method === 'DELETE') {{
          // Unreachable (the interceptor below blocks delete clicks) but kept so
          // the shim covers every request the reused script can issue.
          var delId = decodeURIComponent(path.slice('/api/goals/'.length));
          currentGoals = currentGoals.filter(function (g) {{ return g.id !== delId; }});
          return ok({{}});
        }}

        // Wizard Save (POST /api/goals) and anything else not handled above:
        // fail gracefully, never hit the network.
        return fail('Not available on a shared link.');
      }};

      {script}

      // Make the delete button inert; same capture-phase interceptor as the
      // landing preview (see render_landing_goal_tracking_preview).
      document.getElementById('gtGoalList').addEventListener('click', function (e) {{
        if (e.target.closest('.gt-goal-delete')) e.stopPropagation();
      }}, true);

      // Import icon: a real button only when the viewer was signed in at render
      // time (plain <a href="/signup"> otherwise, no JS). Toggles gtImportCard;
      // closes on outside click like gtShareIconBtn.
      var gtImportBtn = document.getElementById('gtImportBtn');
      var gtImportCard = document.getElementById('gtImportCard');
      if (gtImportBtn) {{
        function setGtImportOpen(open) {{
          gtImportCard.hidden = !open;
          gtImportBtn.classList.toggle('open', open);
        }}
        gtImportBtn.addEventListener('click', function () {{
          setGtImportOpen(gtImportCard.hidden);
        }});
        document.addEventListener('click', function (e) {{
          var wrap = document.querySelector('.gt-import-wrap');
          if (wrap && !wrap.contains(e.target)) setGtImportOpen(false);
        }});
      }}

      // SAVE TO MY MYSCAPE: imports this share's goals into the visitor's list
      // (POST /api/goals/shares/{share.code}/import in app/main.py), then --
      // navigates there once the import succeeds. Uses window.fetch because the
      // bare fetch resolves to this IIFE's local shim, which would never reach
      // the server.
      var gtImportSaveBtn = document.getElementById('gtImportSaveBtn');
      if (gtImportSaveBtn) {{
        gtImportSaveBtn.addEventListener('click', function () {{
          var btn = this;
          btn.disabled = true;
          window.fetch('/api/goals/shares/{share.code}/import', {{ method: 'POST' }})
            .then(function (res) {{ return res.ok ? res.json() : Promise.reject(); }})
            .then(function () {{
              window.location.href = '/dashboard/goal-tracking';
            }})
            .catch(function () {{
              btn.disabled = false;
              btn.classList.add('action-failed');
              setTimeout(function () {{ btn.classList.remove('action-failed'); }}, 2500);
            }});
        }});
      }}
    }})();
    """

    return _shell(
        title=f"{owner_name}'s shared Goal Tracking — myscape",
        player=viewer,
        body=body,
        extra_head=extra_head,
        extra_script=wrapper_script,
        meta_description=f"{owner_name} shared their Goal Tracking list on myscape.",
    )

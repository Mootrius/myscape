"""Server-rendered HTML pages (landing, signup, login, dashboard).

No template engine -- these are simple enough that plain f-strings beat
adding a Jinja2 dependency for a handful of pages. If the page count
grows past "a handful," that tradeoff is worth revisiting.
"""
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import TYPE_CHECKING, Optional, Tuple

from app.bosses import HISCORE_BOSSES
from app.mindmaps import SKILL_NAMES
from app.purchase_goals import item_icon_url

if TYPE_CHECKING:
    from app.models import Account, GameAccount


@dataclass
class PlayerView:
    """The combined identity + game-data view every render_* function in
    this file needs for its header nav and page content. Post the
    multi-account split (see docs/multi-account-scoping.md), a signed-in
    website login (Account) and its currently-active linked OSRS
    character (GameAccount) are two separate database rows -- this is
    the one shape this file works with regardless, built fresh per
    request by build_player_view below (in app/auth.py's session
    dependencies) from whichever Account+GameAccount pair a session
    resolves to. Nothing in this file ever queries either model
    directly."""

    id: uuid.UUID
    email: Optional[str]
    email_verified_at: Optional[datetime]
    runescape_name: Optional[str]
    account_hash: Optional[str]
    # Goal Tracking's hiscores snapshot (see app/hiscores.py and
    # GameAccount's own docstring in app/models.py) -- an empty dict
    # means "never synced", not "synced, ranked for nothing" (every
    # boss synced at least once is a key, 0 or otherwise).
    boss_kill_counts: dict
    hiscores_synced_at: Optional[datetime]


def build_player_view(account: "Account", game_account: Optional["GameAccount"]) -> PlayerView:
    """Combines a signed-in Account with its (possibly absent, e.g. a
    stale/edge-case session -- see _resolve_active_game_account's own
    docstring in app/auth.py for why that's normally unreachable) active
    GameAccount into the single PlayerView this file's render_*
    functions expect. The identity fields (id, email, email_verified_at)
    always come from the Account; the game-data fields (runescape_name,
    account_hash, boss_kill_counts, hiscores_synced_at) come from the
    GameAccount when there is one."""
    return PlayerView(
        id=account.id,
        email=account.email,
        email_verified_at=account.email_verified_at,
        runescape_name=game_account.runescape_name if game_account else None,
        account_hash=game_account.account_hash if game_account else None,
        boss_kill_counts=dict(game_account.boss_kill_counts or {}) if game_account else {},
        hiscores_synced_at=game_account.hiscores_synced_at if game_account else None,
    )

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

# The landing page's own interactive Loot Tracker preview (see
# render_landing_loot_preview below) is backed by a static, curated
# snapshot rather than a live account -- see scripts/gen_landing_loot_demo.py's
# own module docstring for how it's built/regenerated. Lazily read once
# and memoized (same one-JSON-file-behind-a-getter shape as
# app/npc_names.py's get_npc_names), not baked in at import time, so a
# missing/corrupt file fails the one page that needs it instead of the
# whole app failing to start.
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

# Same idea again, for the landing page's own interactive Purchase
# Goals preview (see render_landing_purchase_preview below) -- a
# static, curated snapshot rather than a live account, this one a
# real (not synthetic) gear setup: a one-time GET /api/gear-setups
# pull of the actual "Tombs of Amascut" setup, trimmed down to just
# that one setup -- see that function's own docstring for why a real
# snapshot rather than a generated one, unlike Loot Tracker's.
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

# Same idea a third time, for the landing page's own interactive
# Mindmaps preview (see render_landing_mindmap_preview below) -- a
# real (not synthetic) mindmap, same reasoning as Purchase Goals'
# above: a one-time GET /api/mindmaps pull of the account's own real
# "Example" mindmap, trimmed down to just that one mindmap (there was
# only one to begin with). Unlike Loot Tracker/Purchase Goals, this
# preview genuinely lets a visitor edit -- add/move/recolor/delete
# nodes, undo/redo, fill in goal criteria -- entirely against this
# frozen snapshot in memory (see that function's own docstring for how
# the mutation logic is ported to JS), so there's nothing to keep in
# sync with the real account either; a visitor's edits never touch it.
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

# The Mindmaps preview's goal-criteria search fields (KC/item/quest)
# normally hit session-authenticated endpoints (/api/npcs/search,
# /api/items/search, /api/quests/search -- see app/main.py) that would
# either 401 for an anonymous visitor or, for a logged-in one browsing
# back to "/", send their own real session cookie to a request this
# preview triggered -- neither of which this preview should ever do
# (same "never reach the real API with a visitor's own session cookie"
# discipline as every other shimmed endpoint here). Rather than just
# failing those searches outright (which would make three of the
# eight goal types feel broken in a preview that's supposed to let
# people "edit all they want"), this bundles a curated LOCAL snapshot
# to filter client-side instead -- the full real NPC (1,334) and quest
# (218) name lists (small enough to just ship whole, via
# app/npc_names.py/app/quest_names.py, the exact same snapshots
# search_npc_names/search_quest_names already search), plus a hand-
# picked ~175-item subset of well-known goal-worthy items (the full
# item snapshot is 11.5k entries/~1MB -- far too much to ship on a
# landing page for what's a curated demo, not the real search). An
# obscure item won't turn up here the way it would on the real page;
# see render_landing_mindmap_preview's own wrapper script for how
# these get searched (the exact same startswith-then-contains ranking
# search_npc_names/search_quest_names/search_items use server-side,
# ported to JS).
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

# The landing page's own Storages Viewer preview (render_landing_
# storages_preview) is backed by one real, curated snapshot: a one-time
# GET /api/possessions/summary pull of the account's own real current
# possessions -- every item owned across every synced storage, exactly
# as the real page would show it -- with every PoH (Player-Owned-House,
# i.e. Costume Room) item stripped out first (both the ones whose ONLY
# location was "poh", dropped entirely, and the "poh" key itself
# removed from any item that also owned some elsewhere, though the
# real snapshot this was captured from happened to have none of the
# latter). See render_landing_storages_preview's own docstring for how
# the rest of the page (search/sort/filter/pin/saved views) stays
# genuinely interactive against this one frozen, PoH-free snapshot.
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

# Same idea a fifth time for the landing page's own Goal Tracking
# preview (render_landing_goal_tracking_preview): one real, one-time
# GET /api/goals pull of the account's own real current goals --
# every goal exactly as the real page would show it -- with two
# numbers nudged by hand afterward (Monkey nuts' own current_value,
# and the recurring Sailing goal's own current_value, each with
# progress_pct recomputed to match -- see that function's own
# docstring for the exact values) purely so the demo has a goal
# that's neither empty nor already complete to show off a progress
# bar with. See render_landing_storages_preview's own docstring just
# above for how the rest of the page (sort tabs/delete/drag-reorder/
# the add-goal wizard) stays genuinely interactive against this one
# frozen snapshot.
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

# Same cache-busting trick again, for the Mindmaps page's own stylesheet.
_MINDMAPS_CSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "css", "mindmaps.css"
)
try:
    _MINDMAPS_CSS_VERSION = int(os.path.getmtime(_MINDMAPS_CSS_PATH))
except OSError:
    _MINDMAPS_CSS_VERSION = 0

# Same cache-busting trick again, for the Storages Viewer page's
# own stylesheet.
_POSSESSIONS_CSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "css", "possessions.css"
)
try:
    _POSSESSIONS_CSS_VERSION = int(os.path.getmtime(_POSSESSIONS_CSS_PATH))
except OSError:
    _POSSESSIONS_CSS_VERSION = 0

# Same cache-busting trick again, for the Goal Tracking page's own
# stylesheet.
_GOAL_TRACKING_CSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "css", "goal-tracking.css"
)
try:
    _GOAL_TRACKING_CSS_VERSION = int(os.path.getmtime(_GOAL_TRACKING_CSS_PATH))
except OSError:
    _GOAL_TRACKING_CSS_VERSION = 0


def _nav_sides(player: Optional[PlayerView]) -> tuple[str, str]:
    """The single link/button that goes on each side of the centered
    logo in the header (see _shell). Logged out: Log in on the left,
    Sign up on the right. Logged in: Dashboard on the left, Account on
    the right (log out itself lives on that page now, alongside
    change email/change password/delete account -- see render_account)
    -- the email address used to show here too, but there's no room
    for it next to a centered logo without crowding the nav, so it's
    dropped (still shown on the dashboard itself)."""
    if player:
        return (
            '<a href="/dashboard">Dashboard</a>',
            '<a href="/account">Account</a>',
        )
    return (
        '<a href="/login">Log in</a>',
        '<a href="/signup">Sign up</a>',
    )


def _link_banner(player: Optional[PlayerView]) -> str:
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
    has no way to tell this browser tab about it directly. Also hidden
    for a not-yet-verified player -- GENERATE CODE calls
    POST /api/link/start, which (like the rest of the real app) is
    gated on having a confirmed email (see
    get_current_verified_player_from_session in app/auth.py), so
    showing this banner before that would just be a button that fails
    with a generic error instead of the specific "verify your email
    first" one render_verify_email_required actually gives them."""
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
    """A site-wide footer, the visual mirror of the header (see the
    `header` rule in myscape.css and its comment) -- same full-width
    darkening gradient technique, but stronger and fading upward
    instead of down, so it unmistakably reads as a floor under the
    page rather than a second, weaker header.

    Holds two things, neither of which is really page content: the same
    GitHub/Discord/Patreon icon row the RuneLite plugin's own sidebar
    shows (see buildSocialLinksRow in MyscapePanel.java in the
    myscape-plugin repo -- everything there except its own myscape.io
    icon, since a link back to the site the player is already standing
    on would be pointless here), and the OSRS trademark attribution.
    Both belong on every page regardless of login state, same as each
    other. (This used to also carry a "Linked to <name>" status with
    its own "Unlink" button, mirroring the dashboard's game-account
    chrome -- removed as redundant now that the account page's own
    "LINKED ACCOUNTS" section (render_account()) is the one place that
    actually manages linked characters.)

    `extra` is page-specific content to render ahead of all of that,
    still inside .footer-inner -- currently only render_landing()'s
    "ARE YOU READY?" call-to-action, threaded through from _shell()'s
    own footer_extra param. Empty for every other page, so this footer
    looks exactly as it always has anywhere but the landing page."""
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


# The canonical production domain -- used to build absolute URLs for
# og:url/og:image/twitter:image and the landing page's <link
# rel="canonical">, regardless of which environment actually renders
# the page (local dev included). That's deliberate: these tags exist
# for search engines and link-preview crawlers hitting the live site,
# so they should always point at the one real place this content
# lives, not wherever it happened to be generated from.
_SITE_URL = "https://myscape.io"

# The site-wide fallback for <meta name="description">/og:description/
# twitter:description -- every _shell() call gets this unless a page
# passes its own via meta_description (nothing currently does; the
# landing page's own pitch already covers what a search result or a
# shared link should say, so the other pages -- login, signup, the
# dashboard tools -- just inherit it rather than needing their own).
_DEFAULT_META_DESCRIPTION = (
    "myscape is a free companion site for Old School RuneScape -- track loot from "
    "every NPC you kill, plan Grand Exchange purchases against your real bank, map "
    "out your goals, and see everything you own across every storage, all synced "
    "straight from RuneLite."
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
          btn.textContent = 'COPIED TO CLIPBOARD';
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
  <meta name="description" content="{escape(meta_description)}" />
  <!-- Everything on this site except the landing page is either
       behind a login (dashboard and its four tools, account) or a
       thin auth-flow utility page (signup/login/forgot-reset-verify)
       -- none of that is content worth a search result of its own,
       and letting Google index e.g. a logged-out "please log in"
       shell under /dashboard/loot would just dilute the one page
       that's actually meant to be found. noindex defaults to True in
       _shell()'s own signature above for exactly that reason -- the
       landing page's own render_landing() is the one call site that
       opts back in. nofollow alongside it since a crawler that
       respects noindex has no reason to be crawling a noindexed
       page's own links for more URLs to discover either. -->
  {'<meta name="robots" content="noindex, nofollow" />' if noindex else ""}
  {f'<link rel="canonical" href="{escape(_SITE_URL + canonical_path)}" />' if canonical_path else ""}
  <!-- Open Graph + Twitter Card -- what a link to this page previews
       as in Discord/Twitter/Slack/etc. Rendered on every page (not
       just the indexable landing one) since a player might still
       paste e.g. a dashboard link to themselves or a friend even
       though it requires login -- there's no reason that should
       preview as a bare, description-less URL when the branded
       fallback costs nothing. og-image.jpg is a 1200x630 render of
       the same wordmark the landing page's own intro anchor uses,
       composited onto the site's real background color (matching
       myscape.css's --bg) rather than left as the source PNG's
       transparency, since a transparent image previews against an
       unpredictable -- often white -- background on most platforms. -->
  <meta property="og:site_name" content="myscape" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="{escape(title)}" />
  <meta property="og:description" content="{escape(meta_description)}" />
  <meta property="og:image" content="{escape(_SITE_URL + '/static/img/og-image.jpg')}" />
  <meta property="og:image:width" content="1200" />
  <meta property="og:image:height" content="630" />
  {f'<meta property="og:url" content="{escape(_SITE_URL + canonical_path)}" />' if canonical_path else ""}
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{escape(title)}" />
  <meta name="twitter:description" content="{escape(meta_description)}" />
  <meta name="twitter:image" content="{escape(_SITE_URL + '/static/img/og-image.jpg')}" />
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
<body{f' class="{body_class}"' if body_class else ""}>
  {_link_banner(player)}
  <header>
    <nav class="wrap header-inner">
      <div class="nav-side nav-left">{nav_left}</div>
      <!-- ?home=1 only while player is set -- see root()'s own comment
           in main.py for the full story: it's the one way a logged-in
           player can reach the actual landing page here instead of
           root()'s auto-redirect to /dashboard, which is what every
           other click or typed-in "/" gets now. Left off while
           logged out, since that redirect never fires for this page
           then anyway -- nothing to opt out of. -->
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
    # root() (main.py) redirects a logged-in player to /dashboard
    # before this ever runs -- UNLESS that request carried ?home=1,
    # which is what the header's own "myscape" logo puts on its href
    # while player is set (see _shell()), specifically so a logged-in
    # player has one deliberate way back to this exact page. So this
    # still renders for both a logged-out visitor and a logged-in one
    # who followed that link, and takes/handles player either way --
    # same Optional[PlayerView] signature every other render_*
    # function here has, and the header's own logo/nav plus the
    # footer's linked-status note (both from _shell/player below)
    # already needed to handle either case on their own regardless.
    # (The "ready to start"/CTA buttons below do too -- see the
    # if player: block just past this comment.)
    # The footer's own "ARE YOU READY?" call to action (see _footer()'s
    # extra param and _shell()'s footer_extra) -- deliberately rendered
    # *inside* <footer> rather than as one more .landing-anchor, so it
    # shares that single scroll-snap stop with the footer below it
    # instead of being a fourth full-screen panel of its own (see
    # body.landing footer's min-height in myscape.css, which is what
    # actually gives this stop enough room that the purchase-planner
    # panel above it is fully scrolled out of view once you land here,
    # the same way every .landing-anchor already clears the one before
    # it). One button logged in (straight to the dashboard), two side
    # by side logged out -- the same Log in/Sign up split as the
    # header nav above, just as real buttons instead of plain text
    # links, since this is the page's actual closing pitch.
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
    # Interactive live preview of the real Loot Tracker feature (see
    # render_landing_loot_preview) in place of that panel's own
    # pre-composited marketing image below -- a visitor can actually
    # search/sort/hover/click through a genuine (if curated/fixed, not
    # this visitor's own) day of loot rather than just looking at a
    # picture of the feature. Falls back to the plain image (the
    # landing page's every OTHER feature panel still works this way --
    # see the three .landing-anchor sections below) if the curated
    # snapshot isn't there to read, same as before this existed.
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
    # Same idea again for Purchase Goals (see
    # render_landing_purchase_preview) -- replaces that same
    # pre-composited marketing panel below with a live, read-only
    # look at the account's own real "Tombs of Amascut" gear setup
    # (sorting still works; nothing can be added, removed, or moved).
    # Placed right after loot_anchor_section below (moved up from its
    # original spot at the very end of the anchor list) so the two
    # interactive previews run back to back.
    # Falls back to the plain image, same as loot_anchor_section above,
    # if the curated snapshot isn't there to read.
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
    # Same idea a third time for Mindmaps (see
    # render_landing_mindmap_preview) -- replaces that same
    # pre-composited marketing panel below with a genuinely editable
    # live copy of the account's own real "Example" mindmap (every
    # add/recolor/delete/reparent/undo/redo/goal-save actually works,
    # entirely in-memory -- nothing reaches the real account). Falls
    # back to the plain image, same as the two above, if either the
    # curated snapshot or its search-pools sidecar isn't there to read.
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
    # Same idea a fourth time for Storages Viewer (see
    # render_landing_storages_preview) -- replaces that same pre-
    # composited marketing panel below with a live, genuinely
    # interactive (search/sort/filter/pin/saved-views all actually
    # work) look at the account's own real current possessions, PoH
    # items excluded. Falls back to the plain image, same as the three
    # above, if the curated snapshot isn't there to read.
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
    # Same idea a fifth time for Goal Tracking (see
    # render_landing_goal_tracking_preview) -- replaces that same
    # pre-composited marketing panel below with a live, genuinely
    # interactive (sort tabs/delete-with-confirm/custom-mode drag-
    # reorder/item search in the add-goal wizard all actually work)
    # look at the account's own real current goals -- only the add-
    # goal wizard's own final Save is out of scope, same as Storages
    # Viewer's own scoped-out live-account-only features. Falls back
    # to the plain image, same as the four above, if the curated
    # snapshot isn't there to read.
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
        # Unlike the four above, Goal Tracking never had its own
        # pre-composited marketing anchor image to begin with (it
        # wasn't on the landing page at all before this preview) -- so
        # there's no separate "anchor-goal-tracking.png" to fall back
        # to here. Reuses this same preview's own character crop
        # instead (already shipped either way, see
        # render_landing_goal_tracking_preview) rather than a static
        # asset that would only ever exist for this one dead branch.
        goal_tracking_preview_head, goal_tracking_preview_script = "", ""
        goal_tracking_anchor_section = """
      <section class="landing-anchor">
        <picture>
          <source srcset="/static/img/landing-goal-tracking-preview-char.webp" type="image/webp">
          <img src="/static/img/landing-goal-tracking-preview-char.png" alt="Goal tracking -- for those days when you need some dopamine.">
        </picture>
      </section>"""
    # The remaining "anchor" panels -- pre-composited marketing art
    # (one per showcased feature -- except loot tracking, purchase
    # goals, mindmaps, and storages viewing now, see
    # loot_anchor_section/purchase_anchor_section/mindmap_anchor_section/
    # storages_anchor_section above), not live markup, since each one
    # is a fixed graphic that already has its own baked-in layout/
    # copy. The first one (landing-anchor--intro) shares a single stop
    # with the header above it (see myscape.css) instead of being its
    # own separate one, so scrolling doesn't stop twice just to reveal
    # the logo -- but it's still pinned to exactly one full screen
    # (header + logo + the "explore features" cue at the bottom,
    # nothing else) via that same CSS, with the script below measuring
    # the header's actual rendered height to make that work. webp first
    # (much smaller) with a png fallback for anything that doesn't
    # support it.
    body = f"""
    <div class="landing-anchors">
      <section class="landing-anchor landing-anchor--intro">
        <div class="landing-anchor-intro-media">
          <picture>
            <source srcset="/static/img/anchor-myscape.webp" type="image/webp">
            <img src="/static/img/anchor-myscape.png" alt="myscape -- a place for gains.">
          </picture>
        </div>
        <p class="landing-scroll-cue">
          <span class="landing-scroll-cue-arrow"></span>
          EXPLORE FEATURES
          <span class="landing-scroll-cue-arrow"></span>
        </p>
      </section>
      {loot_anchor_section}
      {purchase_anchor_section}
      {mindmap_anchor_section}
      {storages_anchor_section}
      {goal_tracking_anchor_section}
    </div>
    """
    # CSS scroll-snap (myscape.css) is the baseline -- it's what
    # handles touch-drag and keyboard scrolling. This script is on top
    # of that, just for wheel/trackpad input, and is what makes the
    # stop on each panel actually *hold*: it steps exactly one stop
    # per wheel gesture and locks out further input until that scroll
    # has genuinely finished (via the 'scrollend' event, not just a
    # guessed timeout), so a fast flick can't blow through two panels
    # at once the way plain CSS snap sometimes allows.
    script = """
    (function () {
      // body's first element child -- normally <header>, but the
      // "link your account" banner renders ahead of it for a
      // logged-in, not-yet-linked player (see myscape.css's matching
      // body.landing > *:first-child), so this has to match whichever
      // one is actually first rather than assuming header.
      var firstStop = document.body.firstElementChild;
      var anchors = Array.prototype.slice.call(
        document.querySelectorAll('.landing-anchor:not(.landing-anchor--intro)')
      );
      var footer = document.querySelector('footer');
      var stops = [firstStop].concat(anchors, [footer]).filter(Boolean);
      if (stops.length < 2) return;

      var current = 0;
      var locked = false;
      // Bumped on every goTo() call and captured by that call's own
      // fallback timeout below -- so a stale timeout from an older,
      // already-finished lock can't clear a newer one it has nothing
      // to do with.
      var lockGen = 0;

      // One persistent listener rather than adding/removing a fresh
      // one per goTo() call -- that churn is what caused the actual
      // bug here: with scrollend seemingly firing more than once for
      // a single logical scroll in some cases, add/remove pairs could
      // leave a stale listener behind, and it would then fire again
      // (logging twice, three times, ...) on a later, unrelated
      // scroll. A single listener has nothing to leak.
      window.addEventListener('scrollend', function () {
        locked = false;
      });

      // The footer (last stop) can't actually be scrolled to its own
      // offsetTop if the page isn't tall enough past it -- there's no
      // more content below to make room. Scrolling clamps that to the
      // real max scroll position instead, so comparing against a
      // stop's raw offsetTop would under-count how far it can go and
      // make this mistake the footer for the mindmaps panel above it.
      // Clamping every stop's expected position the same way the
      // browser clamps the real scroll keeps the comparison honest.
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
        // scrollend doesn't fire at all for a few real cases here --
        // notably a no-op scrollIntoView when already at that stop
        // (e.g. pushing "down" again while already on the last panel)
        // -- so this backstop is what clears the lock then, guarded
        // by lockGen so it can't clear a *later* goTo()'s lock if
        // scrollend was just slow rather than missing.
        window.setTimeout(function () {
          if (lockGen === myGen) locked = false;
        }, 900);
        stops[current].scrollIntoView({ behavior: 'smooth', block: 'start' });
      }

      window.addEventListener('wheel', function (e) {
        // ctrl+wheel is pinch-zoom on a trackpad -- leave that alone.
        if (e.ctrlKey || Math.abs(e.deltaY) < 4) return;
        e.preventDefault();
        if (locked) return;
        goTo(nearestStop() + (e.deltaY > 0 ? 1 : -1));
      }, { passive: false });
    })();

    // The intro panel (logo + "explore features" cue) needs to be
    // exactly one screen tall *combined with* the header above it --
    // header height isn't a fixed number (it grows if the "link your
    // account" banner is showing, and can wrap on a narrow viewport),
    // so this measures the real gap above the intro panel and feeds
    // it to a custom property that myscape.css's height calc uses.
    (function () {
      var intro = document.querySelector('.landing-anchor--intro');
      if (!intro) return;

      function sync() {
        var above = intro.getBoundingClientRect().top + window.scrollY;
        document.documentElement.style.setProperty('--landing-intro-above', above + 'px');
      }

      sync();
      window.addEventListener('resize', sync);
      // A late font swap (see @font-face's font-display: optional in
      // myscape.css) can change the header's rendered height after
      // this script's first pass -- re-measure once fonts settle.
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(sync);
      }
    })();
    """
    # The loot/purchase previews' own wrapper scripts (fetch shims,
    # neutered/read-only-ified controls -- see render_landing_loot_preview
    # and render_landing_purchase_preview) just tack onto the end here --
    # an empty string, and a no-op, for either one that was None above
    # (the static-image fallback needs no script of its own).
    script += (
        loot_preview_script
        + purchase_preview_script
        + mindmap_preview_script
        + storages_preview_script
        + goal_tracking_preview_script
    )
    # body_class="landing" scopes the scroll-snap CSS (see
    # myscape.css's `html:has(body.landing)`) to just this page --
    # every other page keeps its ordinary, un-snapped scrolling.
    return _shell(
        title="myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=(
            loot_preview_head
            + purchase_preview_head
            + mindmap_preview_head
            + storages_preview_head
            + goal_tracking_preview_head
        ),
        body_class="landing",
        footer_extra=landing_cta,
        # The one page on the whole site actually meant to be found --
        # see _shell()'s own noindex/canonical_path comment for why
        # every other page stays noindexed by default.
        canonical_path="/",
        noindex=False,
    )


# Icons for the dashboard cards below -- each a real OSRS item that's a
# fitting stand-in for its feature (Coins for Purchase Goals, Dragon
# bones for Loot Tracker, a Clueless scroll for Mindmaps, a Heavy
# casket, stuffed full of loot, for Storages Viewer's "everything you
# own") -- all four routed through item_icon_url (app/purchase_goals.py),
# RuneLite's own static icon CDN, by real item id, so a returning
# player recognizes them at a glance without this app hosting a single
# pixel of them itself.
# Coins uses the same id (995) Purchase Goals' own live GP figure
# already resolves to that CDN as -- confirmed to come back as the
# "biggest pile" denomination art, matching the site's usual
# denomination-scaled-icon convention (see item_icon_url's own
# comment). Dragon bones (536) has only the one real id.
#
# "Clueless scroll" (20249) is a real, actual OSRS item in its own
# right -- not a pun/mislabel for one of the Treasure Trail Clue
# scroll tiers, despite looking almost identical to one (same rolled-
# parchment shape, no colored seal): a novelty two-handed weapon
# reward for completing 400 medium clue scrolls, confirmed against
# the wiki (attempting to read it says "you attempt to make out the
# text, but it makes no sense whatsoever"). Perfect fit for Mindmaps
# either way -- an app for figuring out where to go next when you
# don't have a clue where to start -- and it turns out to be a real
# item named exactly that, not just a label this app made up.
_ICON_COINS = item_icon_url(995)
_ICON_BONES = item_icon_url(536)
_ICON_CLUELESS_SCROLL = item_icon_url(20249)
_ICON_HEAVY_CASKET = item_icon_url(19941)
_ICON_MAX_CAPE = item_icon_url(13280)


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


def render_dashboard(player: PlayerView) -> str:
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
            "Organize multiple setups to keep track of at once.",
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
            _ICON_CLUELESS_SCROLL,
            "Clueless scroll",
            "Mindmaps",
            "Organize your goals into a mindmap! Start from one goal and branch "
            "out with parent, child, and sibling nodes — all with autodetecting "
            "completion functionality.",
        )
        + "</a>"
    )
    possessions_card = (
        '<a href="/dashboard/possessions" style="display:block;color:inherit;text-decoration:none;">'
        + _dash_card(
            _ICON_HEAVY_CASKET,
            "Heavy casket",
            "Storages Viewer",
            "Keep an eye on what you own across every storage in the game. "
            "Search it all, sort by anything, and filter to your heart's "
            "content — all in one place!",
        )
        + "</a>"
    )
    goal_tracking_card = (
        '<a href="/dashboard/goal-tracking" style="display:block;color:inherit;text-decoration:none;">'
        + _dash_card(
            _ICON_MAX_CAPE,
            "Max cape",
            "Goal Tracking",
            "Visualize your goals by setting time-based or one-off quotas "
            "for yourself to meet, complete with auto-detecting and "
            "updating progress bars.",
        )
        + "</a>"
    )

    # No longer alphabetical (Goal Tracking, Loot Tracker, Mindmaps,
    # Purchase Goals, Storages Viewer) -- a deliberate, explicitly
    # chosen order instead: Loot Tracker, Purchase Goals, Mindmaps,
    # Storages Viewer, Goal Tracking. Nothing about this order is
    # derived from anything else (not the card variables' own
    # declaration order above, not each title's length or route name),
    # so a new card's *_card variable just gets inserted at whatever
    # position it's meant to appear -- there's no rule left to keep it
    # consistent with, unlike the old alphabetical version of this
    # comment.
    body = f"""
    <div class="dash-grid">
      {loot_tracker_card}
      {purchase_goals_card}
      {mindmaps_card}
      {possessions_card}
      {goal_tracking_card}
    </div>
    """
    return _shell(title="Dashboard — myscape", player=player, body=body)


def render_account(player: PlayerView) -> str:
    """The header's Account link (see _nav_sides) -- log out plus the
    three things a player can do to their own account: change email,
    change password, delete the account entirely (see the matching
    /api/auth/change-email, /change-password, /delete-account
    endpoints in app/routers/auth.py, all of which deliberately stay
    reachable pre-verification -- see each one's own docstring for
    why). Unlike render_verify_email et al., `player` here isn't
    Optional -- app/main.py's account_page route already redirects a
    logged-out visitor to /login before this ever gets called."""
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
          <button class="secondary" id="addGameAccountBtn" type="button">+ ADD ANOTHER CHARACTER</button>
        </div>

        <div class="account-section">
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

        <div class="account-section">
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

        <div class="account-section account-section--danger">
          <p class="account-section-title account-section-title--danger">ACCOUNT DELETION</p>
          <p class="account-section-hint">This will PERMANENTLY delete your myscape account and all data attached to it. You can create a new account afterward, but you CANNOT undo this action.</p>
          <div class="auth-error" id="deleteError"></div>
          <form id="deleteForm">
            <div class="field">
              <label for="deletePassword">Password</label>
              <input type="password" id="deletePassword" name="deletePassword" placeholder="Your password" required />
            </div>
            <button class="danger" type="submit" id="deleteSubmitBtn" data-armed="false">DELETE ACCOUNT</button>
          </form>
        </div>
      </div>
    </div>
    """
    script = """
    (function () {
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

      // Editing the password after arming the confirm step re-disarms
      // it -- otherwise a changed-their-mind retype could land on a
      // stale "ARE YOU SURE?" that actually deletes on the very next
      // click.
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
          // First press -- just arm the real confirm step below rather
          // than deleting immediately (the required attribute on the
          // password field already means this can't fire on an empty
          // one).
          deleteSubmitBtn.dataset.armed = 'true';
          deleteSubmitBtn.textContent = 'ARE YOU SURE?';
          return;
        }

        // Second press -- actually delete. The server still checks the
        // password itself (see /api/auth/delete-account) -- this step
        // is a confirm, not a client-side password check.
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
          // Back to the first step -- a failed attempt (wrong password,
          // most likely) shouldn't leave it armed to delete on the very
          // next click once they've fixed it.
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

      // Linked Accounts list (step 7 of docs/multi-account-scoping.md)
      // -- fetched fresh on load rather than rendered server-side,
      // same reasoning as every other JS-populated list on this site
      // (gear setups, mindmaps, ...): it's the same data an action
      // right here on this page (switch/remove/add) can immediately
      // change, so there's no point building it twice.
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
        removeBtn.className = 'danger';
        removeBtn.textContent = 'DELETE CHARACTER';
        removeBtn.dataset.armed = 'false';
        // Same arm-then-confirm two-step as DELETE ACCOUNT above, for
        // the same reason -- this is also a permanent, undoable-only-
        // by-losing-data action, just scoped to one character instead
        // of the whole login.
        removeBtn.addEventListener('click', async () => {
          gameAccountsError.classList.remove('show');
          if (removeBtn.dataset.armed !== 'true') {
            removeBtn.dataset.armed = 'true';
            removeBtn.textContent = 'ARE YOU SURE?';
            return;
          }
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
            removeBtn.dataset.armed = 'false';
            removeBtn.textContent = 'DELETE CHARACTER';
          } catch (err) {
            gameAccountsError.textContent = 'Something went wrong. Please try again.';
            gameAccountsError.classList.add('show');
            removeBtn.dataset.armed = 'false';
            removeBtn.textContent = 'DELETE CHARACTER';
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
          const res = await fetch('/api/link/game-accounts');
          if (!res.ok) {
            gameAccountsError.textContent = 'Could not load your linked accounts.';
            gameAccountsError.classList.add('show');
            return;
          }
          const gameAccounts = await res.json();
          gameAccountsList.innerHTML = '';
          gameAccounts.forEach((gameAccount) => gameAccountsList.appendChild(renderGameAccountRow(gameAccount)));
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
            // Reload rather than just re-fetching the list -- the new
            // slot is now this session's active GameAccount, and the
            // header's own link banner (see _link_banner in
            // app/pages.py) needs a fresh page load to notice that and
            // show its GENERATE CODE button for it, the same one a
            // brand new signup sees for its first link.
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

      loadGameAccounts();
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
          // Same reasoning as the login form's own redirect just below
          // -- straight to the dashboard, not the landing page.
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
          // Straight to the dashboard rather than '/' (the landing
          // page, which no longer bounces a logged-in visitor there
          // itself -- see root() in main.py) -- someone who just typed
          // their password in came here to use the app, not to see the
          // marketing page they clicked "Log in" away from.
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
          // The backend always returns the same generic message here
          // whether or not the email actually has an account (see
          // forgot_password's own docstring in app/routers/auth.py) --
          // so swapping in that message on any 200 is the whole story,
          // there's no separate "found" vs "not found" branch to add.
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
        // No token in the URL at all -- someone navigated here directly
        // rather than following a real reset link -- so there's nothing
        // to submit; point them at requesting a fresh one instead of
        // showing an empty form that can only ever fail.
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
            // Same reasoning as signup/login's own redirect -- reset-
            // password logs the player in immediately on success (see
            // reset_password in app/routers/auth.py), so send them
            // straight into the app rather than back to /login.
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
        // Someone navigated here directly rather than following a real
        // verification link -- same reasoning as render_reset_password's
        // own no-token case.
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
            // Same reasoning as reset_password's own redirect -- verify-email
            // logs the player in immediately on success (see verify_email in
            // app/routers/auth.py), so send them straight into the app.
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
    """The styled 404 page -- see the custom exception_handler in
    app/main.py for when this actually gets used instead of a raw
    {"detail": "Not Found"} JSON body. Unlike most of this module's
    other render_* functions, the caller here is an exception handler,
    not a route with Depends(get_optional_current_player_from_session)
    -- app/main.py loads the player itself with a manual DB session
    and passes it through, so the header nav still shows Dashboard/Log
    out for a signed-in visitor who hits a broken link instead of
    always showing Log in/Sign up. The same player check also picks
    where the home-teleport icon itself goes -- straight to /dashboard
    for a signed-in visitor (the landing page has nothing for them
    they don't already see there), and to / (the landing page) for
    everyone else, same as the header's own logo link right above it."""
    teleport_href = "/dashboard" if player else "/"
    body = f"""
    <div class="auth-shell">
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
    """Builds Purchase Goals' (extra_head, body, script) triple -- split
    out from render_purchase_goals below (same reasoning, and the same
    split _loot_tracker_panel_markup went through first) so the landing
    page's own interactive preview (render_landing_purchase_preview)
    can embed this exact same panel markup/script rather than forking a
    second copy of either. Nothing here references `player` at all --
    everything below the header shell is rendered client-side from a
    single polled JSON payload (GET /api/gear-setups, see that endpoint
    in app/main.py), the same self-contained-embeddable shape Loot
    Tracker's own panel already has.

    Named "gear setups" a player plans and tracks GP toward, ported
    feature-for-feature from the original single-user Maintrius tool's
    own Purchase Goals UI (see app/purchase_goals.py's module docstring
    for what changed and what didn't on the way over). Rendering
    everything from one polled payload (rather than server-rendered)
    is what the original tool did too (a local HTML file polling its
    own local server), and keeping that shape means every mutation
    endpoint can just hand back the freshly recomputed state and let
    the same render() function redraw everything, rather than juggling
    two different rendering paths."""
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
        picker: null,       // { slotType, slot, targets } while a gear/inventory slot is open for editing
        iconPicker: false,  // true while the setup-icon picker is open
        nameFormMode: null, // 'new' | 'rename' | null
        // Sockets (gear or inventory slots, filled or empty) shift-
        // clicked into a pending group -- see toggleSlotSelected/
        // wireSlotClicks below. Cleared whenever the player switches
        // setups, opens the icon picker, or plain-clicks a slot that
        // isn't part of the current group, so it never lingers into
        // a context it no longer applies to.
        multiSelect: [],    // [{ slotType, slot }, ...]
        pollTimer: null,
        dragSuppressClick: false, // true for one click right after a completed drag-and-drop (see wireSlotClicks)
        // True from the moment a "Still to Purchase" row picks up
        // until it's dropped or the drag is cancelled (see
        // wireSummaryDrag below) -- the background poll at the bottom
        // of this script skips itself while this is set, since
        // loadState() -> render() rebuilds #pgSummaryList's rows from
        // scratch, which would yank the actively-dragged DOM node out
        // of the document mid-gesture and silently end the browser's
        // native drag session -- this (a poll landing mid-drag) is
        // what made the live-preview reorder intermittently just stop
        // responding.
        dragging: false,
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
            return '<button class="tracker-icon-btn' + active + '" data-setup-id="' + esc(s.id) + '" draggable="true" type="button" title="' + esc(s.name) + '">' +
              '<img src="' + esc(s.icon.icon) + '" alt="" /></button>';
          }
          var label = esc((s.icon && s.icon.itemName) || s.name || '?').slice(0, 3);
          return '<button class="tracker-icon-btn' + active + '" data-setup-id="' + esc(s.id) + '" draggable="true" type="button" title="' + esc(s.name) + '">' +
            '<span class="tracker-icon-fallback">' + label + '</span></button>';
        }).join('');
        row.querySelectorAll('[data-setup-id]').forEach(function (btn) {
          btn.addEventListener('click', function () {
            // A completed drag shouldn't ALSO register as a click that
            // switches the active setup -- same dragSuppressClick
            // convention wireSlotClicks already uses for the same
            // reason, set on dragend below and cleared the instant this
            // fires.
            if (PG.dragSuppressClick) {
              PG.dragSuppressClick = false;
              return;
            }
            setActiveSetupId(btn.getAttribute('data-setup-id'));
            PG.picker = null;
            PG.iconPicker = false;
            // A pending shift-click group is specific to the setup it
            // was built on -- carrying it over to a different setup's
            // (unrelated) slots of the same type/index would silently
            // apply a future search to the wrong sockets.
            PG.multiSelect = [];
            render();
          });
        });
        wireSetupIconDrag(row);
      }

      // Drag-and-drop reordering for the setup icon row itself --
      // same FLIP-preview/live-DOM-order/full-replacement shape as
      // wireSummaryDrag below, just over data-setup-id rows instead of
      // data-slot-type/data-slot ones, and always active (no separate
      // "custom mode" gate -- reordering setups is never anything
      // other than a drag, there's no equivalent of the still-to-
      // purchase list's other four sort buttons to gate it behind).
      // Animates BOTH x and y, unlike wireSummaryDrag's y-only FLIP --
      // .tracker-icon-row wraps (see purchase-goals.css), so dragging
      // a setup can just as easily shift every icon after it sideways
      // within a row as bump it down to the next one.
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
            // Same PG.dragging flag wireSummaryDrag's own dragstart
            // sets -- the 5s background poll at the bottom of this
            // script checks it and skips its refresh while it's true.
            // Missing this was the actual bug behind a dropped setup
            // reorder silently not sticking: nothing here previously
            // told the poll a drag was in progress, so a poll landing
            // mid-drag would call render() -> renderIconRow(), which
            // tears down and rebuilds every button in this row from
            // the OLD (pre-drag) PG.data -- including the very button
            // the browser's native drag session was still tracking as
            // its source. Ripping that element out from under an
            // in-flight native drag silently ends the gesture, so the
            // drop the player thought they'd made never fires at all.
            PG.dragging = true;
            btn.classList.add('dragging');
          });
          btn.addEventListener('dragend', function () {
            btn.classList.remove('dragging');
            draggedEl = null;
            PG.dragging = false;
            // A completed drag shouldn't ALSO register as a click that
            // switches the active setup -- see the click handler above.
            PG.dragSuppressClick = true;
            // A drag that ends without a drop (dropped outside the
            // row, or cancelled with Escape) leaves the live-preview
            // DOM order sitting there with nothing saved server-side
            // to back it up -- a plain re-render from the untouched
            // PG.data snaps it straight back to the last real order.
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

      // Shift-click multi-select: lets a player build up a group of
      // sockets (gear or inventory, filled or empty, any mix) before
      // searching once and applying that one item to every socket in
      // the group -- see wireSlotClicks (where these are called) and
      // saveSlot (which actually applies the picked item to every
      // target). Slot identity is (slotType, slot) same as everywhere
      // else on this page; String(...) on the slot half since an
      // inventory slot is a number but the DOM attribute it's compared
      // against is always a string.
      function isSlotSelected(slotType, slot) {
        return PG.multiSelect.some(function (s) { return s.slotType === slotType && String(s.slot) === String(slot); });
      }
      function toggleSlotSelected(slotType, slot) {
        var idx = PG.multiSelect.findIndex(function (s) { return s.slotType === slotType && String(s.slot) === String(slot); });
        if (idx >= 0) PG.multiSelect.splice(idx, 1);
        else PG.multiSelect.push({ slotType: slotType, slot: slot });
      }

      // Keeps the shared picker in sync with PG.multiSelect -- called
      // right after every shift-click toggle (see wireSlotClicks), with
      // the state from just BEFORE that toggle: whether the group was
      // empty, and whatever picker (if any) was already open. Closes
      // the picker once the group empties back out (nothing left to
      // apply a pick to), otherwise opens it (if it isn't already) or
      // just refreshes which slots it targets (if it is), so a player
      // can freely add or remove slots mid-search without losing
      // whatever they've already typed.
      //
      // If an ordinary single-slot picker was already open (from a
      // plain, non-shift click) at the moment the FIRST shift-click of
      // a fresh group comes in, that slot is folded into the group too
      // -- shift-clicking a second slot while already searching for one
      // reads as "add this one too," not "throw away what I had open
      // and start over." Only ever folds in on that one transition
      // (wasEmpty), never again afterward, so shift-clicking that same
      // slot back off later actually removes it instead of it silently
      // reappearing.
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

          el.addEventListener('click', function (e) {
            if (PG.dragSuppressClick) {
              PG.dragSuppressClick = false;
              return;
            }
            var slotType = el.getAttribute('data-slot-type');
            var slot = slotType === 'inventory' ? parseInt(el.getAttribute('data-slot'), 10) : el.getAttribute('data-slot');

            // Shift-click toggles this slot in/out of the multi-select
            // group -- filled or empty, it never opens the wiki the way
            // a plain click on a filled slot would. syncMultiSelectPicker
            // opens the shared picker the moment the FIRST slot is
            // added (folding in whatever slot's picker was already open,
            // if any -- see its own comment) rather than needing a
            // separate follow-up click, and keeps it open/updated as
            // more slots are added or removed, closing it again once
            // the group empties back out.
            if (e.shiftKey) {
              var pickerWasOpen = !!PG.picker;
              var wasEmpty = PG.multiSelect.length === 0;
              var priorPicker = PG.picker;
              toggleSlotSelected(slotType, slot);
              syncMultiSelectPicker(wasEmpty, priorPicker);
              renderContent();
              // Only steal focus into the search box on the transition
              // from no picker to one open -- once the player's already
              // typing a query, further shift-clicks to grow or shrink
              // the group shouldn't yank focus or re-select their text.
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

            // A plain click (no shift) always abandons any pending
            // multi-select group -- and the shared picker that came
            // with it, if one's open -- and acts on just this slot,
            // same as it always has.
            var hadSelection = PG.multiSelect.length > 0;
            if (hadSelection) {
              PG.multiSelect = [];
              PG.picker = null;
            }

            // A filled slot's item is now a link out to the wiki instead
            // of an editor -- removing is handled by the hover "x"
            // (above) and adding only ever happens on an empty slot, so
            // there's nothing left for a filled slot's own click to open.
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
      // (cheapest first), down for descending (priciest first) -- the
      // standard up-means-ascending/down-means-descending convention
      // (same one Storages Viewer's own sortable column headers
      // use, and the same shorthand the Loot Tracker's own sort tabs
      // use now, see _sort_tabs in app/pages.py). The old single
      // "Alphabetical" button is likewise now two direction-specific
      // tabs, both labeled "A-Z" (same one-label-two-arrows pattern as
      // the "GP" pair beside them) -- "A-Z ↓" (Z-to-A, descending) and
      // "A-Z ↑" (A-to-Z, ascending) -- backed by the 'alphabetical'/
      // 'reverse_alphabetical' sort_mode values (see
      // STILL_TO_PURCHASE_SORT_MODES in app/schemas.py and
      // _still_to_purchase_summary in app/purchase_goals.py).
      var STILL_TO_PURCHASE_SORT_MODES = [
        { key: 'high_to_low', label: 'GP \\u2193', title: 'GP, high to low' },
        { key: 'low_to_high', label: 'GP \\u2191', title: 'GP, low to high' },
        { key: 'reverse_alphabetical', label: 'A-Z \\u2193', title: 'Z to A' },
        { key: 'alphabetical', label: 'A-Z \\u2191', title: 'A to Z' },
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

      // Nudges the CUSTOM sort button, the same way Mindmaps'
      // glowEditModeButton nudges its own Edit Mode button when a node
      // is clicked outside Edit Mode -- a "still to purchase" row only
      // accepts a click/drag attempt at all in Custom sort mode (see
      // wireSummaryDrag below); in any other mode that gesture
      // currently does nothing on its own, so this points at the
      // control that would actually let it do something instead of
      // just silently going nowhere. Same remove-class/reflow/add-
      // class dance as glowEditModeButton, for the same reason: it
      // lets a second attempt mid-glow restart the pulse from the
      // beginning instead of being ignored because the class was
      // already present.
      function glowCustomSortButton() {
        var btn = document.querySelector('#pgSortButtons .sort-btn[data-sort-mode="custom"]');
        if (!btn) return;
        btn.classList.remove('glow');
        void btn.offsetWidth;
        btn.classList.add('glow');
      }

      // Drag-and-drop reordering for the "custom" sort mode -- same
      // dragstart/dragend shape as wireSlotClicks' gear-slot dragging,
      // but rows now live-reorder as you drag over them (animateReorder
      // below) instead of just outlining a drop target and only moving
      // things once you let go, so it's obvious where a row is about to
      // land before you commit to it. draggedEl/dropped are scoped to
      // this one call, which is fine since renderSummaryList rebuilds
      // every row's markup (and rewires this) from scratch every render.
      function wireSummaryDrag(customMode) {
        var listEl = document.getElementById('pgSummaryList');
        if (!customMode) {
          // Rows outside Custom mode carry no draggable attribute at
          // all (see renderSummaryList), so a native HTML5 drag can
          // never actually start on one -- the only gesture that can
          // ever reach a row here is a plain press. pointerdown (not
          // click) to match glowEditModeButton's own trigger, and so
          // this fires the instant a drag is attempted too, not only
          // on a completed click.
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

        // FLIP-animates every OTHER row from its position just before
        // `mutate` runs to its position just after, so a live-preview
        // reorder reads as a slide instead of an instant snap. The
        // dragged row itself is skipped -- it's already being carried
        // by the browser's own native drag image, so sliding it too
        // would just fight that.
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
            // Forces layout so the translateY above actually paints
            // before the transition is switched back on below --
            // without this the browser coalesces both style writes into
            // one frame and the row just snaps straight to 0, with no
            // visible slide at all.
            row.getBoundingClientRect();
            row.style.transition = 'transform 150ms ease';
            row.style.transform = '';
            row.addEventListener('transitionend', function handler() {
              row.style.transition = '';
              row.removeEventListener('transitionend', handler);
            });
          });
        }

        // The live preview above already leaves the DOM in exactly the
        // order a drop should save -- no separate source/target diffing
        // needed, just read the rows back out in their current order.
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
          if (data) { PG.stateVersion++; PG.data = data; render(); }
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
            // A drag that ends without a drop (dropped outside the
            // list, or cancelled with Escape) leaves the live-preview
            // DOM order sitting there with nothing saved server-side to
            // back it up -- a plain re-render from the untouched
            // setup.stillToPurchase state snaps it straight back to the
            // last real order.
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

      // targets defaults to just this one slot -- passed explicitly as
      // the current multi-select group (see wireSlotClicks) when the
      // picker should apply whatever gets picked to more than one
      // socket at once.
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

      // Applies `item` to every target in the picker's group (just the
      // one slot it was opened on, unless it was opened on a multi-
      // select group -- see openSlotPicker/wireSlotClicks) -- one PUT
      // per socket, same request shape as the single-slot save this
      // replaced. Sequential, not parallel: each PUT's response is the
      // setup's full, freshly recomputed state, so the next target's
      // save (and everything the player sees if it stops partway) is
      // always built on top of what actually landed, not a stale
      // snapshot from before the loop started. Stops at the first
      // failure -- apiCall has already shown the error -- rather than
      // firing off the rest against whatever's wrong (an expired
      // session, say), but keeps whatever targets DID save rather than
      // discarding that progress.
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
        // Only close the picker (and drop the multi-select group with
        // it) once at least one target actually saved -- a total
        // failure on the very first (or only) target leaves everything
        // exactly as it was, same as a single-slot save always has, so
        // the player can just retry rather than losing their group and
        // having to reselect it.
        if (data) {
          PG.picker = null;
          PG.multiSelect = [];
          render();
        }
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
        PG.multiSelect = [];
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
        input.classList.remove('invalid');
        input.focus();
      }

      // Site-wide standard: a required-field miss just gets a red border
      // on the field itself, no popup/inline text anywhere -- clear it
      // as soon as the person starts typing so it never lingers past the
      // moment it's fixed.
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
          if (data) { PG.stateVersion++; PG.data = data; render(); }
        }
      });

      // ---- Boot + poll ------------------------------------------------------

      loadState();
      PG.pollTimer = setInterval(function () {
        // Skip a background refresh while the player has an editor open --
        // an in-flight rename/slot-pick shouldn't get yanked out from
        // under them by a poll landing mid-edit.
        if (PG.picker || PG.iconPicker || PG.nameFormMode || PG.dragging) return;
        loadState();
      }, 5000);
    })();
    """
    return extra_head, body, script


def render_purchase_goals(player: PlayerView) -> str:
    """The Purchase Goals page -- see _purchase_goals_panel_markup above
    for everything that actually builds it; this is now just that panel
    wrapped in the logged-in shell, the same split render_loot_tracker
    already has over _loot_tracker_panel_markup."""
    extra_head, body, script = _purchase_goals_panel_markup()
    return _shell(
        title="Purchase Goals — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )


def _loot_tracker_panel_markup() -> Tuple[str, str, str]:
    """Builds the Loot Tracker's (extra_head, body, script) triple --
    split out from render_loot_tracker below so the landing page's own
    interactive preview (render_landing_loot_preview) can embed the
    exact same panel markup/script rather than forking a second copy of
    either. Neither piece references `player` at all (this page is a
    thin server-rendered shell -- everything below it is drawn client-
    side from one polled JSON payload, see this function's own body),
    which is exactly what makes reusing it as a self-contained embedded
    panel possible in the first place: nothing here assumes it's being
    rendered inside _shell for a logged-in visitor."""
    extra_head = f'<link rel="stylesheet" href="/static/css/loot-tracker.css?v={_LOOT_TRACKER_CSS_VERSION}" />'

    # Feather's own "eye" outline -- the "show hidden" toggle button
    # below, and (as a JS string in the script further down) the
    # per-tile hide/unhide button's own default state -- see
    # EYE_GLYPH/EYE_OFF_GLYPH there for why this button never swaps to
    # the crossed-out variant the way that one does.
    _EYE_GLYPH_SVG = (
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>'
        '<circle cx="12" cy="12" r="3"></circle></svg>'
    )

    def _sort_tabs(tabs_id: str, count_label: str, hide_toggle_id: str) -> str:
        # count_label names whichever secondary number that panel's own
        # boxes show beside gp -- "KC" for the NPC panel, "Qty" for the
        # item panel -- so its two new count-based tabs read naturally on
        # each side (data-sort stays the same generic "count-high"/
        # "count-low" either way; see sortEntries in the script below for
        # which field that actually sorts by per panel). Labeled as the
        # metric name plus an arrow -- up for ascending (low-to-high, or
        # A-to-Z), down for descending (high-to-low, or Z-to-A), the
        # same up-means-ascending/down-means-descending convention
        # Storages Viewer's own sortable column headers use (see
        # the sortDir-driven arrow.textContent in the script further
        # down) and that spreadsheets/sortable tables use everywhere --
        # same shorthand Purchase Goals' own sort buttons use now too,
        # see STILL_TO_PURCHASE_SORT_MODES) rather than spelling out
        # "High to Low"/"Low to High" -- with this many tabs sharing one
        # row, the full text wrapped each button onto two lines, which
        # was both harder to scan and taller than intended. The old
        # single "Alphabetical"/"Alpha" button is likewise now two --
        # both labeled "A-Z" (matching the plain "GP"/count_label
        # pattern beside them -- one label, two arrow-only variants)
        # rather than one button saying "A" and the other "Z" -- "A-Z ↓"
        # (data-sort "alpha-desc", Z-to-A, descending) and "A-Z ↑"
        # (data-sort "alpha", A-to-Z, ascending) -- so each direction
        # gets its own one-click tab instead of a single button that
        # only ever sorted one way, matching the GP/count pairs beside
        # it (see sortEntries below for the alpha-desc branch). That's
        # an 8th button alongside the eye toggle now -- see
        # .loot-sort-tab/.loot-hide-toggle in loot-tracker.css for the
        # padding/font-size trim the row took to fit it.
        return f"""
          <div class="loot-sort-tabs" id="{tabs_id}">
            <button type="button" class="loot-sort-tab" data-sort="high" title="GP, high to low">GP &darr;</button>
            <button type="button" class="loot-sort-tab" data-sort="low" title="GP, low to high">GP &uarr;</button>
            <button type="button" class="loot-sort-tab" data-sort="count-high" title="{count_label}, high to low">{count_label} &darr;</button>
            <button type="button" class="loot-sort-tab" data-sort="count-low" title="{count_label}, low to high">{count_label} &uarr;</button>
            <button type="button" class="loot-sort-tab" data-sort="alpha-desc" title="Z to A">A-Z &darr;</button>
            <button type="button" class="loot-sort-tab" data-sort="alpha" title="A to Z">A-Z &uarr;</button>
            <button type="button" class="loot-sort-tab" data-sort="recent">Recent</button>
            <button type="button" class="loot-hide-toggle" id="{hide_toggle_id}" title="Show hidden">{_EYE_GLYPH_SVG}</button>
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
            <input type="text" class="loot-search" id="lootNpcSearch" placeholder="Search for an NPC" autocomplete="off" />
            {_sort_tabs("lootNpcSortTabs", "KC", "lootNpcHideToggle")}
          </div>
          <p class="loot-column-empty" id="lootNpcEmpty" style="display:none;">
            No NPCs killed in this range.
          </p>
          <div class="loot-npc-row" id="lootNpcRow"></div>
        </div>
        <div class="loot-panel">
          <div class="loot-panel-controls">
            <input type="text" class="loot-search" id="lootItemSearch" placeholder="Search for an item" autocomplete="off" />
            {_sort_tabs("lootItemSortTabs", "Qty", "lootItemHideToggle")}
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
        // An ordered list, not a Set -- selection order is what the
        // chart title below joins in (see renderBarChart), so a
        // shift-click that grows the group needs to append, not just
        // record membership. A plain click always collapses this back
        // to a single entry (or empties it, clicking the one already-
        // selected NPC); shift-click toggles one name in/out without
        // touching the rest -- see the NPC row's click handler below.
        selectedNpcs: [], npcSort: 'high', npcSearch: '', itemSort: 'high', itemSearch: '',
        rangeKey: '24h', customStart: null, customEnd: null,
        // The clicked bar's own {start, end, value, killCount, index}
        // (all captured straight off that bucket at click time), or
        // null when no bar is selected -- mutually exclusive with
        // selectedNpcs above (picking one always clears the other,
        // see the #lootBarBars/#lootNpcRow click handlers below): a
        // bar click re-scopes everything to a time slice, an NPC box
        // click re-scopes it to an identity, and combining both isn't
        // asked for here. See currentNpcs/currentItems and
        // renderBarChart's own selectedBucket handling for how this
        // drives the panels/header/title once set. `index` is the
        // selection's real identity -- start/end/value/killCount get
        // overwritten in place by loadState on every poll (see its
        // own comment) to whatever bucket now sits at that same
        // index, so a rolling preset's continuous drift moves the
        // selection's reported time/value along with it instead of
        // leaving it pointing at a bucket that no longer exists.
        selectedBucket: null,
        // Purely local UI state, never persisted -- each panel's own
        // "show hidden" eye toggle (see .loot-hide-toggle in
        // loot-tracker.css). Off by default: a hidden NPC/item starts
        // out actually gone from its panel, not just dimmed -- see
        // visibleNpcEntries/visibleItemEntries below.
        npcShowHidden: false, itemShowHidden: false,
      };
      var lastData = null;
      // The scoped payload for state.selectedBucket, kept separate
      // from lastData -- lastData always stays the whole selected
      // range (the chart needs every bucket regardless of what's
      // selected), while this is a full extra GET /api/players/me/loot
      // fetch for just that one bucket's own precise [start, end)
      // window -- see bucketUrl/loadBucketData below. Null both when
      // nothing's selected and while the first fetch for a freshly
      // clicked bar is still in flight.
      var bucketData = null;
      // Bumped by clearSelectedBucket and every loadBucketData call --
      // guards an in-flight fetch the same way npcRowRenderToken/
      // itemListRenderToken guard renderNpcRow/renderItemList's own
      // async icon-preload below, so a slow response that's since been
      // superseded (a different bar clicked, or the selection cleared,
      // while it was still in flight) can never clobber the panels
      // with stale data once it finally resolves.
      var bucketFetchToken = 0;

      // Feather's own "eye"/"eye-off" outlines -- the per-tile
      // hide/unhide button baked into every NPC/item box (see
      // renderNpcRow/renderItemList below), open when clicking would
      // HIDE this tile, crossed-out when clicking would UNhide it.
      // Same plain-line-icon convention as every other small control
      // on this site (see PIN_GLYPH in render_possessions, this same
      // file, for the most recent example) -- Feather has both of
      // these as real icons already, unlike the thumbtack that pin
      // button needed to hand-draw. The toggle button up in the sort
      // row (see _EYE_GLYPH_SVG in render_loot_tracker) is the plain
      // open eye only -- it doesn't hide anything itself, so it never
      // needs the crossed-out state this one does.
      var EYE_GLYPH = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>';
      var EYE_OFF_GLYPH = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19M14.12 14.12a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>';

      // An NPC whose every item is individually hidden (see
      // item.hidden, set server-side by build_loot_state in
      // app/loot.py) has nothing left to show even though the NPC
      // itself was never explicitly hidden -- treated the same as an
      // explicit hide for display purposes (filtered out with the
      // toggle off, dimmed with it on), even though the eye button on
      // its own tile still only ever acts on the real, explicit
      // n.hidden (see the click handler on #lootNpcRow below) -- hiding
      // every item one at a time and having the NPC vanish as a side
      // effect is a different action from explicitly hiding the NPC
      // itself, and unhiding one item shouldn't require having also
      // hidden the NPC by accident.
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
      // labels), 'alpha'/'alpha-desc' by nameKey (A-to-Z / Z-to-A --
      // the two "A-Z" tabs, up/down arrow respectively), 'recent' by
      // recentKey (an ISO timestamp -- lastKillAt for NPCs,
      // lastDroppedAt for items) newest first.
      // Never mutates the list it's given -- callers still hold the
      // original (unsorted, unfiltered) array from lastData.
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
        } else if (sortMode === 'alpha-desc') {
          out.sort(function (a, b) { return (b[nameKey] || '').localeCompare(a[nameKey] || ''); });
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

      // Sums per-bucket gp across every selected NPC's own npcBucketValues
      // array (see build_loot_state in app/loot.py) into one array the
      // same length as buckets -- null once nothing (or only one, which
      // already has its own array) is selected, since renderBarChart
      // only needs this for 2+.
      function mergedNpcBucketValues(npcBucketValues, selectedNpcs, numBuckets) {
        var merged = new Array(numBuckets).fill(0);
        selectedNpcs.forEach(function (name) {
          var values = npcBucketValues[name];
          if (!values) return;
          for (var i = 0; i < numBuckets; i++) merged[i] += values[i] || 0;
        });
        return merged;
      }

      // Sums quantity/value for the same item (same key as
      // _add_item_totals server-side -- itemId, falling back to
      // itemName) across every selected NPC's own npcItems list,
      // keeping whichever copy's lastDroppedAt is most recent and its
      // icon/hidden flag (identical for every occurrence of the same
      // item -- hidden comes from the player's own hidden-item set,
      // not anything NPC-specific -- so the first one seen is as good
      // as any).
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

      // The By-NPC row's own source list -- a clicked bar
      // (state.selectedBucket) wins over lastData's whole-range
      // windowNpcs the same way it wins in currentItems below, and for
      // the same reason (see that function's own comment). Every
      // other NPC-row caller already goes through this rather than
      // reading lastData.windowNpcs directly -- see the click/search/
      // sort/hide-toggle handlers on #lootNpcRow/#lootNpcSortTabs.
      function currentNpcs() {
        if (state.selectedBucket) return bucketData ? (bucketData.windowNpcs || []) : [];
        return (lastData && lastData.windowNpcs) || [];
      }

      // The item panel shows every NPC's items combined when nothing's
      // selected, just the one selected NPC's own items when exactly
      // one is, or all selected NPCs' items summed together (see
      // mergedNpcItems above) once 2+ are -- see build_loot_state's
      // windowItems/npcItems in app/loot.py for how those two lists
      // are computed. A clicked bar (state.selectedBucket) takes
      // priority over all of that -- mutually exclusive with
      // selectedNpcs (see that field's own comment), so this only ever
      // needs to check the one that's actually populated -- and reads
      // from bucketData instead of lastData, since only a fresh scoped
      // fetch for that bucket's own [start, end) window has its
      // items (lastData's windowItems/npcItems cover the whole
      // selected range, not any one bucket of it). Empty while that
      // fetch is still in flight (bucketData null) rather than
      // falling back to the whole range's items, which would flash a
      // wrong, too-broad answer before the real one arrives.
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

      // Rounds a chart's max value up to a "nice" number (a step x a
      // power of ten) so the gridlines land on clean values -- and,
      // via targetFrac, scales that ceiling so the tallest bar sits
      // close to a fixed height fraction of the axis instead of
      // wherever the nearest nice ceiling happens to land. The old
      // version (targetFrac defaulting to 1, with just 1/2/5/10
      // steps) rounded the raw value straight up to the next step, so
      // a bar just under a round number sat right at the top of the
      // chart while one just over a round number landed barely above
      // half -- a big, poll-to-poll inconsistency. Dividing by
      // targetFrac before rounding, plus a finer step table so each
      // rounding "hop" is smaller, keeps the tallest bar's height in
      // a tight band centered under targetFrac (worst case in the low
      // 60s% for a 0.8 target, typically closer to 70-80%) rather
      // than the old 50-100% swing.
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

      // Zero-padded 'YYYY-MM-DD' for a plain JS Date, in local time --
      // same convention isValidIsoDate/the range menu's own inputs
      // use, just built by hand rather than parsed, since
      // toLocaleDateString has no built-in ISO-basic output format.
      function fmtIsoDateLocal(d) {
        var month = String(d.getMonth() + 1);
        if (month.length < 2) month = '0' + month;
        var day = String(d.getDate());
        if (day.length < 2) day = '0' + day;
        return d.getFullYear() + '-' + month + '-' + day;
      }

      // A clicked bar's own precise time/date range, for the chart
      // title once state.selectedBucket is set (see renderBarChart) --
      // the bucket's own actual start/end rather than rounding to
      // whatever granularity produced it (see fmtBucketLabel's own
      // comment on why bucket boundaries are never calendar-aligned in
      // the first place). Dates use fmtIsoDateLocal's YYYY-MM-DD form
      // rather than the locale-formatted "Sep 20" style used elsewhere
      // on this page. The end shown is 1 second before the bucket's
      // real (exclusive) end boundary -- see bucketUrl's own comment
      // for why the fetch itself does the same -- so a bucket spanning
      // 3:00:00-3:59:59 reads as "3:00 - 3:59 PM" rather than the
      // confusingly-exact-looking "3:00 - 4:00 PM", which would look
      // like a full extra minute shared with the next bar. Only
      // repeats the date on the end side when it differs from the
      // start's -- the overwhelmingly common case (any bucket under a
      // day wide) is same-day, and repeating an identical date on both
      // sides would just be noise.
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

      // The OSRS Wiki's article title for an item is (almost always)
      // just its in-game name -- the same name this page already gets
      // back as itemName -- with spaces URL-encoded, same as this
      // file's own icon URLs already do server-side (see
      // item_icon_url in app/purchase_goals.py, which percent-encodes
      // the icon filename the same way); MediaWiki
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

      // Loads every one of these icon URLs (skipping any falsy one) in
      // the background BEFORE the caller swaps in the HTML that
      // references them, so a brand new row of boxes (switching NPCs,
      // or a search/sort that reshuffles the set) paints already
      // decoded instead of the icons visibly popping in a beat after
      // the boxes themselves already changed. Capped at
      // ICON_PRELOAD_TIMEOUT_MS so one slow or dead wiki image can
      // never hold the swap up indefinitely -- iconImg's own onerror
      // still hides a genuinely broken icon once it's actually in the
      // DOM either way, preload or not.
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

      // renderNpcRow/renderItemList below both tear down and rebuild
      // their whole list -- not just patch it in place -- every time a
      // hide/unhide changes which entries are in it (see each one's own
      // key comment for why). Hiding or restoring the last few items of
      // a wrapped-flex list like these often changes that list's total
      // height, which -- with no min-height reserved to hold its place
      // -- shifts everything below it and can visibly yank the whole
      // page up or down the instant the swap lands, even though nothing
      // ever called scrollTo. Re-pinning the scroll position right
      // around the swap (synchronously, so the browser never paints the
      // in-between frame) keeps the page from moving under the player's
      // cursor just because a list they're looking at got shorter or
      // taller.
      function swapListHtml(el, html) {
        var scrollY = window.scrollY;
        el.innerHTML = html;
        if (window.scrollY !== scrollY) window.scrollTo(0, scrollY);
      }

      // Bar chart over the currently-selected range, bucketed at
      // whatever granularity that range's span calls for (see
      // _bucket_plan in app/loot.py -- hourly for a short range like
      // the original 24-hour-only chart, coarser for a longer one),
      // oldest on the left -- ported from the original single-user
      // tool's Loot Tracker chart (renderVorkathBarChart), summed
      // across every source by default. When one or more NPCs are
      // selected (state.selectedNpcs, set by renderNpcRow's click
      // handler below) each bar instead shows two layers: a full-height
      // outline at the bucket's own total value (so the scale/shape of
      // the whole chart never changes), with a solid fill at the bottom
      // sized to just the selected NPCs' combined share of the same
      // bucket (see mergedNpcBucketValues above for 2+). maxValue is
      // always derived from the total buckets, never the selection's
      // own values, so the axis stays put when switching NPCs. Reuses
      // the existing bar-col elements when the bucket count hasn't
      // changed (the same range keeps the same bucket count on every
      // 10s poll) so the CSS height transition actually animates
      // between polls instead of snapping -- a range change does
      // change the bucket count, which is exactly when a full rebuild
      // (and a fresh grow-in) is right.
      function renderBarChart(buckets, windowValue, windowKills, npcBucketValues, selectedNpcs, windowNpcs, granularity, rangeEnd, selectedBucket) {
        buckets = buckets || [];
        npcBucketValues = npcBucketValues || {};
        selectedNpcs = selectedNpcs || [];
        granularity = granularity || 'hourly';
        // Three mutually-exclusive sources for the header's gp/kc and
        // the title above it, in priority order -- a clicked bar
        // (selectedBucket) beats an NPC-identity selection
        // (selectedNpcs) beats the plain whole-range default. Only one
        // of these is ever actually populated at a time (the
        // #lootBarBars/#lootNpcRow click handlers each clear the
        // other's selection on their way in), but the priority order
        // still matters for the one render that lands with the OLD
        // selection still passed in, right before that clearing takes
        // effect.
        var headerValue, headerKills, titleText;
        if (selectedBucket) {
          // Reads straight off selectedBucket rather than re-finding
          // a matching bucket here -- loadState already keeps it
          // fresh on every 10s poll (overwriting start/end/value/
          // killCount in place to whatever bucket now sits at its own
          // selectedBucket.index, see state's own comment on this),
          // so by the time a render reaches this point it's already
          // today's true numbers for wherever that bar has drifted
          // to, not a stale snapshot from the moment it was clicked.
          headerValue = selectedBucket.value;
          headerKills = selectedBucket.killCount;
          titleText = fmtBucketRangeLabel(selectedBucket.start, selectedBucket.end);
        } else {
          // With one or more NPCs selected, the header's gp/kc numbers
          // switch to just their own totals (summed from each one's
          // windowNpcs entry -- value/killCount, the same numbers its
          // own NPC box shows) instead of the whole range's --
          // otherwise selecting Guard would still show every other
          // NPC's loot summed in up top while the chart itself only
          // fills in Guard's share, which reads as a mismatch.
          var selectedEntries = selectedNpcs.length && windowNpcs
            ? windowNpcs.filter(function (n) { return selectedNpcs.indexOf(n.sourceName) !== -1; })
            : [];
          headerValue = selectedEntries.length ? selectedEntries.reduce(function (sum, n) { return sum + n.value; }, 0) : windowValue;
          headerKills = selectedEntries.length ? selectedEntries.reduce(function (sum, n) { return sum + n.killCount; }, 0) : windowKills;
          // A selected NPC's own name is shown in ALL CAPS (e.g.
          // "ZULRAH") -- uppercased here in JS rather than via a CSS
          // text-transform on .loot-chart-title, since that would also
          // force the "ALL NPCs" fallback into "ALL NPCS", capitalizing
          // the "s" it's deliberately meant to keep lowercase. With 2+
          // selected, each name gets the same uppercasing and the whole
          // row joins them with the same small-dot separator (·)
          // already used in this file's own tooltips (see titleFor
          // below) -- in selection order, so the title reads in the
          // order NPCs were added to the group rather than re-sorting.
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

        // 0.8 target so the tallest bucket's bar consistently lands
        // around 4/5 up the axis instead of anywhere from half height
        // to flush with the top -- see niceMax's comment.
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
          return selectedNpcs.length ? (selectedValues[i] || 0) : b.value;
        }
        function fillPct(b, i) {
          var v = fillValue(b, i);
          return maxValue > 0 ? Math.max(0, Math.min(100, (v / maxValue) * 100)) : 0;
        }
        function titleFor(b, i) {
          if (selectedNpcs.length) {
            return selectedNpcs.join(' \\u00b7 ') + ': ' + fmtGp(fillValue(b, i)) + ' gp \\u00b7 total ' + fmtGp(b.value) + ' gp';
          }
          return fmtGp(b.value) + ' gp' + (b.killCount ? ' \\u00b7 ' + b.killCount.toLocaleString('en-US') + ' kc' : '');
        }

        // Whether column index i is the one state.selectedBucket
        // points at -- matched by index rather than by the bucket's
        // own start/end, since index is the selection's real identity
        // now (see state's own comment on selectedBucket): a rolling
        // preset's buckets drift forward on every poll, so chasing the
        // exact start/end clicked would lose the highlight the moment
        // they moved, instead of keeping it pinned to the same bar.
        function isSelectedCol(i) {
          return !!(selectedBucket && i === selectedBucket.index);
        }

        var barsEl = document.getElementById('lootBarBars');
        var existingCols = barsEl.children;
        if (existingCols.length !== buckets.length) {
          barsEl.innerHTML = buckets.map(function (b, i) {
            return '<div class="loot-bar-col' + (isSelectedCol(i) ? ' selected' : '') + '" data-bucket-index="' + i + '" title="' + titleFor(b, i) + '">' +
              '<div class="loot-bar-outline' + (outlineActive(b) ? ' active' : '') + '" style="height:' + outlinePct(b) + '%;"></div>' +
              '<div class="loot-bar-fill' + (fillPct(b, i) > 0 ? ' has-value' : '') + '" style="height:' + fillPct(b, i) + '%;"></div>' +
            '</div>';
          }).join('');
        } else {
          buckets.forEach(function (b, i) {
            var col = existingCols[i];
            col.title = titleFor(b, i);
            col.setAttribute('data-bucket-index', i);
            col.classList.toggle('selected', isSelectedCol(i));
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
      // selected range. A plain click replaces state.selectedNpcs with
      // just that one NPC (clicking the already-sole-selected one
      // clears it back to "all sources"); a shift-click instead toggles
      // that NPC in/out of the existing selection, folding in whatever
      // single NPC was already plain-selected on its first use rather
      // than discarding it -- see the click handler below. Either way
      // re-renders the chart/row from the last-polled data, with no
      // extra fetch needed. A single selected NPC gets the classic gold
      // .active border; 2+ get the blue .multi-selected outline instead
      // (same treatment as Purchase Goals' own shift-click socket
      // group -- see .gear-slot.multi-selected in purchase-goals.css).
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
      // Bumped on every rebuild kicked off below -- guards the
      // preloadIcons().then() callback so a slow-to-resolve rebuild
      // that a newer one has since superseded (search/sort changed
      // again, say, while the first preload was still in flight) never
      // clobbers the row with stale boxes once it finally does resolve.
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

        // With the toggle off (the default), a hidden NPC -- explicit
        // or effective (see npcEffectiveHidden above) -- is filtered
        // out here entirely, same as it never happened; with it on,
        // every NPC shows, hidden ones just dimmed (see the
        // hidden-entry class below) -- see .loot-hide-toggle in
        // loot-tracker.css for the button that flips this.
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

        function npcTitle(n) {
          return n.sourceName + ' \\u2014 ' + fmtGp(n.value) + ' gp \\u00b7 ' + n.killCount + ' kc';
        }

        // A tiered clue casket's own sourceName is always exactly
        // "Reward casket (<tier>)" (see build_loot_state in
        // app/loot.py, npc_like_name) -- never a real NPC's name, so
        // this can't false-positive on an actual monster. Used below
        // to give the casket's own icon a dedicated class (see
        // .loot-npc-box-icon-casket in loot-tracker.css) since the
        // wiki's "detail" casket render (much bigger/more ornate than
        // a real NPC's own portrait) reads a little large at the same
        // 56px this box already sizes every other NPC icon at.
        function isCasketNpc(n) {
          return /^Reward casket \(/i.test(n.sourceName);
        }

        // hiddenFlags folds into the key alongside everything else that
        // already forces a rebuild (search/sort/toggle/the set itself)
        // -- a hide/unhide can change WHICH entries are dimmed without
        // changing the sorted set's membership or order at all (an
        // already-hidden-and-shown NPC just getting explicitly hidden
        // too, say), which the rest of the key wouldn't otherwise catch
        // -- same fix Storages Viewer's own pinnedKey made to
        // renderTable's key for the identical reason (see possessions.css/
        // app/pages.py's render_possessions).
        var hiddenFlags = sorted.map(function (n) { return npcEffectiveHidden(n) ? '1' : '0'; }).join('');
        var key = state.npcSearch + '\\u0001' + state.npcSort + '\\u0001' + (state.npcShowHidden ? '1' : '0') + '\\u0001' +
          hiddenFlags + '\\u0001' + sorted.map(function (n) { return n.sourceName; }).join('|');
        if (key !== lastNpcKey) {
          var html = sorted.map(function (n) {
            // Solo selection (plain click, or a shift-click group that's
            // shrunk back to one) keeps the classic gold .active border;
            // 2+ selected get the blue .multi-selected outline instead
            // -- see the click handler below and .loot-npc-box.active/
            // .multi-selected in loot-tracker.css.
            var isSelected = state.selectedNpcs.indexOf(n.sourceName) !== -1;
            var active = isSelected && state.selectedNpcs.length === 1;
            var multiSelected = isSelected && state.selectedNpcs.length > 1;
            var hidden = npcEffectiveHidden(n);
            var explicitHidden = !!n.hidden;
            var eyeTitle = (explicitHidden ? 'Unhide ' : 'Hide ') + n.sourceName;
            // A <button> can't validly nest inside another <button> --
            // see .loot-npc-box-wrap in loot-tracker.css -- so the eye
            // toggle is a DOM sibling of the box, not a child of it,
            // both wrapped in one non-interactive div. That sibling
            // relationship also means clicking the eye button never
            // needs preventDefault/stopPropagation to keep it from
            // also selecting the NPC underneath -- same reasoning as
            // Storages Viewer's own pin button.
            return '<div class="loot-npc-box-wrap' + (hidden ? ' hidden-entry' : '') + '">' +
              '<button type="button" class="loot-npc-box' + (active ? ' active' : '') + (multiSelected ? ' multi-selected' : '') + '" data-npc="' +
                escapeHtml(n.sourceName) + '" title="' + escapeHtml(npcTitle(n)) + '">' +
                iconImg(n.icon, n.sourceName, 'loot-npc-box-icon' + (isCasketNpc(n) ? ' loot-npc-box-icon-casket' : '')) +
                '<div class="loot-npc-box-kc">' + n.killCount + ' kc</div>' +
                '<div class="loot-npc-box-value">' + fmtGpCompact(n.value) + ' gp</div>' +
              '</button>' +
              '<button type="button" class="loot-eye-btn" data-hide-name="' + escapeHtml(n.sourceName) +
                '" data-hidden="' + (explicitHidden ? '1' : '0') + '" title="' + escapeHtml(eyeTitle) + '">' +
                (hidden ? EYE_OFF_GLYPH : EYE_GLYPH) +
              '</button>' +
            '</div>';
          }).join('');
          // Preload every icon this new row needs before swapping the
          // HTML in, so the boxes and their pictures appear together
          // instead of the icons popping in a beat after the (empty-
          // looking) boxes already showed.
          var token = ++npcRowRenderToken;
          preloadIcons(sorted.map(function (n) { return n.icon; })).then(function () {
            if (token !== npcRowRenderToken) return;
            lastNpcKey = key;
            swapListHtml(rowEl, html);
          });
          return;
        }

        // Same NPC set/order as last render (key unchanged) -- reuse
        // the existing boxes (and their <img> icons, avoiding the
        // flicker) but still refresh the kc/value text and title in
        // place, since a later poll can bump those numbers for an NPC
        // that's still sorted into the same slot. Queried by
        // .loot-npc-box-wrap (not rowEl.children directly), same
        // reasoning as renderTable's own patch branch in
        // render_possessions -- keeps this correct even if a future
        // change ever inserts a non-wrap sibling into #lootNpcRow.
        var wraps = rowEl.querySelectorAll('.loot-npc-box-wrap');
        sorted.forEach(function (n, i) {
          var wrap = wraps[i];
          if (!wrap) return;
          var box = wrap.querySelector('.loot-npc-box');
          var isSelected = state.selectedNpcs.indexOf(n.sourceName) !== -1;
          box.classList.toggle('active', isSelected && state.selectedNpcs.length === 1);
          box.classList.toggle('multi-selected', isSelected && state.selectedNpcs.length > 1);
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
      // Same reasoning/guard as npcRowRenderToken above.
      var itemListRenderToken = 0;
      function renderItemList(items) {
        var emptyEl = document.getElementById('lootItemEmpty');
        var listEl = document.getElementById('lootItemList');
        // Same filter-out-unless-toggled-on treatment as
        // renderNpcRow's own visible above -- no "effective" hiding to
        // compute here, an item has no sub-items of its own to derive
        // it from, so it.hidden alone decides.
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

        function itemTitle(it) {
          // No space between the × and the quantity that follows it
          // (unlike the — on either side of it) -- reads as a single
          // "x123"-style unit, the same way the box's own always-visible
          // .loot-item-box-qty badge just below already renders its
          // × + fmtGpCompact(it.quantity) with nothing between them.
          return it.itemName + ' \\u00d7' + fmtGp(it.quantity) + ' \\u2014 ' + fmtGp(it.value) + ' gp';
        }

        // Same hiddenFlags addition, same reason, as renderNpcRow's key
        // above.
        var hiddenFlags = sorted.map(function (it) { return it.hidden ? '1' : '0'; }).join('');
        var key = state.selectedNpcs.join('\\u0002') + '\\u0001' + state.itemSearch + '\\u0001' + state.itemSort + '\\u0001' +
          (state.itemShowHidden ? '1' : '0') + '\\u0001' + hiddenFlags + '\\u0001' +
          sorted.map(function (it) { return it.itemId != null ? it.itemId : it.itemName; }).join('|');
        if (key !== lastItemKey) {
          var html = sorted.map(function (it) {
            var eyeTitle = (it.hidden ? 'Unhide ' : 'Hide ') + it.itemName;
            // Same sibling-wrap reasoning as renderNpcRow's box above --
            // an <a> can't validly contain a <button> either.
            return '<div class="loot-item-box-wrap' + (it.hidden ? ' hidden-entry' : '') + '">' +
              '<a class="loot-item-box" href="' + wikiItemUrl(it.itemName) + '" target="_blank" rel="noopener" title="' + escapeHtml(itemTitle(it)) + '">' +
                iconImg(it.icon, it.itemName, 'loot-item-box-icon') +
                '<div class="loot-item-box-qty">' + '\\u00d7' + fmtGpCompact(it.quantity) + '</div>' +
                '<div class="loot-item-box-value">' + fmtGpCompact(it.value) + ' gp</div>' +
              '</a>' +
              '<button type="button" class="loot-eye-btn" data-hide-item-id="' + (it.itemId != null ? it.itemId : '') +
                '" data-hide-name="' + escapeHtml(it.itemName) + '" data-hidden="' + (it.hidden ? '1' : '0') +
                '" title="' + escapeHtml(eyeTitle) + '">' +
                (it.hidden ? EYE_OFF_GLYPH : EYE_GLYPH) +
              '</button>' +
            '</div>';
          }).join('');
          // Same preload-before-swap as renderNpcRow above -- this is
          // the branch that runs every time the NPC selection changes
          // (its own key includes state.selectedNpcs), which is
          // exactly when this list's icons are most likely to be brand
          // new and otherwise pop in a beat after the boxes.
          var token = ++itemListRenderToken;
          preloadIcons(sorted.map(function (it) { return it.icon; })).then(function () {
            if (token !== itemListRenderToken) return;
            lastItemKey = key;
            swapListHtml(listEl, html);
          });
          return;
        }

        // Same reasoning as renderNpcRow's reuse branch above: the item
        // set/order didn't change, so keep the existing icons, but
        // still refresh the qty/value text and title in case a later
        // poll bumped either for an item still sorted into this slot.
        var wraps = listEl.querySelectorAll('.loot-item-box-wrap');
        sorted.forEach(function (it, i) {
          var wrap = wraps[i];
          if (!wrap) return;
          var box = wrap.querySelector('.loot-item-box');
          box.title = itemTitle(it);
          var qtyEl = box.querySelector('.loot-item-box-qty');
          if (qtyEl) qtyEl.textContent = '\\u00d7' + fmtGpCompact(it.quantity);
          var valEl = box.querySelector('.loot-item-box-value');
          if (valEl) valEl.textContent = fmtGpCompact(it.value) + ' gp';
        });
      }

      // ---- Hiding/unhiding an NPC or item (see the eye button baked
      // into every box above, and the panel-level "show hidden" toggle
      // wired up further below) -- each just calls the matching
      // endpoint (see app/loot.py's set_npc_hidden/set_item_hidden)
      // then does a full loadState() re-poll rather than patching
      // client state by hand, same as picking a new range already
      // does -- simpler, and correct by construction since the server
      // is what actually knows how hiding something reshapes every
      // total downstream of it (see build_loot_state's own docstring).
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
        // The eye button is a sibling of .loot-npc-box (see
        // .loot-npc-box-wrap above), never a descendant of it, so a
        // click on it can never also match .closest('.loot-npc-box')
        // below -- checked first regardless, so this reads as the
        // deliberate priority it is rather than relying on that.
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
        // Selecting an NPC re-scopes the chart/panels by identity
        // instead of by time -- clears any bar selection first, same
        // mutual-exclusivity as the #lootBarBars click handler below
        // does in the other direction (see selectedBucket's own
        // comment on state).
        clearSelectedBucket();
        if (e.shiftKey) {
          // Shift-click toggles this NPC in/out of the selection
          // without touching the rest of it -- works whether nothing,
          // one, or several NPCs were already selected, so a single
          // plain-selected NPC folds straight into a new multi-select
          // group on the very first shift-click rather than being
          // discarded (state.selectedNpcs already holds it either way).
          var idx = state.selectedNpcs.indexOf(name);
          if (idx !== -1) state.selectedNpcs.splice(idx, 1);
          else state.selectedNpcs.push(name);
        } else {
          // A plain click always replaces the whole selection with just
          // this one NPC -- clicking the already-sole-selected one
          // clears it back to "all sources", same as before.
          var wasSoleSelection = state.selectedNpcs.length === 1 && state.selectedNpcs[0] === name;
          state.selectedNpcs = wasSoleSelection ? [] : [name];
        }
        rerenderChart(lastData);
        renderNpcRow(currentNpcs());
        renderItemList(currentItems());
      });

      document.getElementById('lootBarBars').addEventListener('click', function (e) {
        // Matched against the outline/fill themselves, not the whole
        // .loot-bar-col (which spans the full plot height so the
        // column lines up under its own x-axis label) -- both anchor
        // to the column's bottom edge and size to the bucket's own
        // value (see renderBarChart), so this only actually hits the
        // rendered bar shape itself, never the empty air above a
        // short bar. A zero-value bucket's outline/fill both render
        // at 0% height, so there's nothing there to hit at all --
        // clicking one of those is the same as clicking any other
        // empty part of the column, i.e. it does nothing here (see
        // the outside-click handler below for what clears a selection
        // instead).
        var bar = e.target.closest('.loot-bar-outline, .loot-bar-fill');
        var col = bar && bar.closest('.loot-bar-col');
        if (!col || !lastData) return;
        var idx = parseInt(col.getAttribute('data-bucket-index'), 10);
        var b = (lastData.buckets || [])[idx];
        if (!b) return;
        // Toggle-off is keyed on index, not start/end -- clicking the
        // same bar position again always deselects it, even if a poll
        // has since drifted its start/end away from what was clicked
        // last time (see selectedBucket's own comment on state).
        var alreadySelected = state.selectedBucket && state.selectedBucket.index === idx;
        if (alreadySelected) {
          // Clicking the already-selected bar clears it back to the
          // whole range -- same toggle-off convention as re-clicking
          // an already-sole-selected NPC box above.
          clearSelectedBucket();
        } else {
          // Re-scoping by time instead of by identity -- clears any
          // NPC selection first, same mutual-exclusivity as the
          // #lootNpcRow click handler above does in the other
          // direction (see selectedBucket's own comment on state).
          // value/killCount are captured here too (not just start/
          // end/index) so the header has something correct to show
          // immediately, before loadBucketData's own fetch (kicked off
          // below) has had a chance to resolve -- loadState's own poll
          // then keeps all four current from here on, see its comment.
          state.selectedNpcs = [];
          state.selectedBucket = { start: b.start, end: b.end, value: b.value, killCount: b.killCount, index: idx };
          bucketData = null;
          loadBucketData();
        }
        rerenderChart(lastData);
        renderNpcRow(currentNpcs());
        renderItemList(currentItems());
      });
      // Clicking anywhere that isn't an actual bar -- the empty part
      // of a bar's own column, a different panel, blank page space,
      // all of it -- clears a bucket selection the same way it
      // already gets cleared by picking an NPC or a new range. Skips
      // a click that landed on a bar itself (own handler just above
      // already owns that case, including the toggle-off click on the
      // already-selected bar) so the two listeners never fight over
      // the same click as it bubbles from the bar up to document.
      document.addEventListener('click', function (e) {
        if (!state.selectedBucket) return;
        if (e.target.closest('.loot-bar-outline, .loot-bar-fill')) return;
        clearSelectedBucket();
        rerenderChart(lastData);
        renderNpcRow(currentNpcs());
        renderItemList(currentItems());
      });
      // Same outside-click convention as the bucket one just above, for
      // an NPC selection (one or several) instead of a time-range one:
      // anything that isn't an actual .loot-npc-box -- the eye button
      // next to it, a different panel, blank page space -- clears it.
      // Skips a click on the box itself so this never fights the
      // #lootNpcRow handler above, which already owns setting/toggling/
      // toggle-off for that click (plain click, shift-click, or
      // re-clicking the sole-selected box).
      document.addEventListener('click', function (e) {
        if (!state.selectedNpcs.length) return;
        if (e.target.closest('.loot-npc-box')) return;
        state.selectedNpcs = [];
        rerenderChart(lastData);
        renderNpcRow(currentNpcs());
        renderItemList(currentItems());
      });

      document.getElementById('lootNpcSearch').addEventListener('input', function (e) {
        state.npcSearch = e.target.value;
        if (lastData) renderNpcRow(currentNpcs());
      });
      document.getElementById('lootNpcSortTabs').addEventListener('click', function (e) {
        var toggleBtn = e.target.closest('.loot-hide-toggle');
        if (toggleBtn) {
          state.npcShowHidden = !state.npcShowHidden;
          toggleBtn.classList.toggle('active', state.npcShowHidden);
          if (lastData) renderNpcRow(currentNpcs());
          return;
        }
        var btn = e.target.closest('.loot-sort-tab');
        if (!btn || !lastData) return;
        state.npcSort = btn.getAttribute('data-sort');
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
      document.getElementById('lootItemSearch').addEventListener('input', function (e) {
        state.itemSearch = e.target.value;
        renderItemList(currentItems());
      });
      document.getElementById('lootItemSortTabs').addEventListener('click', function (e) {
        var toggleBtn = e.target.closest('.loot-hide-toggle');
        if (toggleBtn) {
          state.itemShowHidden = !state.itemShowHidden;
          toggleBtn.classList.toggle('active', state.itemShowHidden);
          renderItemList(currentItems());
          return;
        }
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
        document.getElementById('lootRangeBtn').classList.remove('active');
      }

      document.getElementById('lootRangeBtn').addEventListener('click', function () {
        var menu = document.getElementById('lootRangeMenu');
        var opening = menu.style.display === 'none';
        menu.style.display = opening ? 'flex' : 'none';
        if (!opening) document.getElementById('lootRangeCustom').style.display = 'none';
        // Gold-highlighted (see .loot-range-btn.active in
        // loot-tracker.css) for as long as its own dropdown is open --
        // every path that actually closes the menu (outside click,
        // picking a preset, Apply) already routes through
        // closeRangeMenu above, which un-highlights it there, so this
        // is the only place that needs to turn it ON.
        this.classList.toggle('active', opening);
      });
      document.addEventListener('click', function (e) {
        var wrap = document.getElementById('lootChartRange');
        if (wrap && !wrap.contains(e.target)) closeRangeMenu();
      });
      // Typed 'YYYY-MM-DD' rather than a native <input type="date">'s
      // own calendar popup (see the input tags themselves) -- a plain
      // text field the way the rest of this menu already reads, no
      // separate widget popping up inside the range dropdown's own
      // popup. A bare text field would happily hold anything though,
      // so the 'd' slots below get masked live as you type (digits
      // only, dashes fixed in place, unfilled slots shown as "_") --
      // structural guidance a native date picker gave away for free --
      // and isValidIsoDate covers what the mask can't: an actual
      // calendar date, not just the right shape (rejects "2024-13-40").
      var DATE_MASK = 'dddd-dd-dd';

      function digitsOnly(s) {
        return (s || '').replace(/\D/g, '').slice(0, 8);
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

      // Blank in the sense that matters here -- no digits actually
      // typed yet -- covers both a genuinely empty string and the
      // all-underscores mask skeleton these inputs start with (see
      // their own value="____-__-__" in the HTML above).
      function isBlankMaskValue(s) {
        return digitsOnly(s).length === 0;
      }

      function applyDateMask(input) {
        var digits = digitsOnly(input.value);
        input.value = maskValueFromDigits(digits);
        // Cursor lands right after the last filled digit (skipping
        // past whichever dash/underscore comes next) every time, so a
        // plain typing-then-backspacing flow always edits from the end
        // -- the one thing this simple a mask doesn't handle well is
        // clicking into the middle of an already-filled date to tweak
        // one digit; clearing and retyping is the way through that.
        var pos = 0, di = 0;
        for (var i = 0; i < DATE_MASK.length; i++) {
          if (DATE_MASK[i] === 'd' && di < digits.length) { pos = i + 1; di++; }
        }
        input.setSelectionRange(pos, pos);
        input.classList.remove('invalid');
      }

      function isValidIsoDate(s) {
        var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || '');
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
        // A picked bar belongs to the range that was showing when it
        // was clicked -- switching ranges invalidates it the same way
        // it already invalidates an NPC selection just above.
        clearSelectedBucket();
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
        closeRangeMenu();
        updateRangeMenuActive();
        loadState();
      }
      document.getElementById('lootRangeApply').addEventListener('click', applyCustomRange);
      // Enter applies from either field -- there's no picker to close
      // out of any more, so typing a date and hitting Enter is the
      // natural way through this now, same as it would be for any
      // other single-line text field.
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

      // A clicked bar's own scoped request -- same endpoint lootUrl
      // above hits, but with range=custom and the bucket's own exact
      // start/end sent as full ISO timestamps (parse_loot_range_bound
      // in app/loot.py accepts those alongside the plain YYYY-MM-DD
      // dates the range menu's date inputs send) rather than a whole
      // calendar day, so this gets exactly that bucket's own NPCs/
      // items back, no wider. bucket.end is the *next* bucket's own
      // start (exclusive -- see build_loot_state in app/loot.py), but
      // this endpoint's own end bound is inclusive (same contract its
      // YYYY-MM-DD path has always had) -- backed off by 1ms so an
      // event landing exactly on the boundary can't get counted in
      // both this bucket and the next one.
      function bucketUrl(bucket) {
        var params = new URLSearchParams();
        params.set('range', 'custom');
        params.set('start', bucket.start);
        params.set('end', new Date(new Date(bucket.end).getTime() - 1).toISOString());
        return '/api/players/me/loot?' + params.toString();
      }

      // Fetches bucketData for the currently-selected bucket -- called
      // once right after a bar click sets state.selectedBucket, and
      // again on every loadState poll tick to keep it fresh (a
      // selected bucket that includes "now" can still pick up new
      // kills). Fails quietly rather than showing lootError the way
      // loadState's own initial fetch does -- this is a background
      // refinement of a page that's already showing something
      // (either the previous bucket's data, or nothing yet), the same
      // "don't interrupt over a poll the player didn't explicitly ask
      // for" reasoning as every other quiet background poll on this
      // site (see e.g. refreshSyncStatusInBackground in the
      // Mootrius/myscape-plugin repo for the same pattern elsewhere).
      async function loadBucketData() {
        if (!state.selectedBucket) return;
        var token = ++bucketFetchToken;
        try {
          var res = await fetch(bucketUrl(state.selectedBucket));
          if (!res.ok || token !== bucketFetchToken) return;
          var data = await res.json();
          // A newer click, or a deselect, could have landed while this
          // was in flight -- discard rather than clobber whatever's
          // now actually selected.
          if (token !== bucketFetchToken) return;
          bucketData = data;
          renderNpcRow(currentNpcs());
          renderItemList(currentItems());
        } catch (err) {
          // Quiet -- see this function's own doc comment above.
        }
      }

      // Clears a bucket selection back to the whole selected range --
      // shared by the #lootBarBars click handler's own toggle-off (re-
      // clicking the already-selected bar) and every place that
      // changes scope out from under it (a new NPC selected, a new
      // range/CUSTOM applied) the same way state.selectedNpcs = [] is
      // reset in each of those same spots.
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

          // Any selected NPC may have aged out of the range on a later
          // poll (its last kill in range just fell off the back of a
          // rolling preset like 24 HOURS) -- drop just that one from
          // the selection (falling all the way back to "all sources"
          // only if every selected NPC did) rather than silently
          // showing a flat/empty fill for it forever. Same fallback
          // when it's now hidden (explicitly or via all its own items
          // -- see npcEffectiveHidden above) with the NPC panel's own
          // toggle off: its tile just vanished from the row, same as
          // aging out, so there's no way left to click back to it
          // either.
          var rangeNpcs = data.windowNpcs || [];
          state.selectedNpcs = state.selectedNpcs.filter(function (name) {
            var stillPresent = rangeNpcs.filter(function (n) { return n.sourceName === name; })[0];
            return stillPresent && (state.npcShowHidden || !npcEffectiveHidden(stillPresent));
          });

          // A selected bar stays pinned to its own position (index)
          // rather than the instant it was clicked -- a rolling
          // preset's buckets all drift forward a little on every 10s
          // poll (bucket width is the range's own span divided evenly,
          // not calendar-aligned -- see _bucket_plan's own docstring
          // in app/loot.py -- so "now" moving forward shifts every
          // boundary with it), so re-reading start/end/value/killCount
          // off whatever bucket now sits at that same index is what
          // keeps the highlight, the title, and the header's gp/kc all
          // showing today's true numbers for that bar instead of a
          // frozen snapshot from the moment it was clicked. Falls back
          // to clearing the selection on the rare case the index no
          // longer exists at all (the bucket count itself changed --
          // every place that can cause that already clears the
          // selection on its own, so this is just a safety net, not
          // the expected path).
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
          // Keeps the selected bucket's own panel data on the same
          // 10s cadence as everything else -- see loadBucketData's
          // own doc comment for why this stays quiet on failure.
          if (state.selectedBucket) loadBucketData();
        } catch (err) {
          errorEl.textContent = 'Something went wrong loading your loot.';
          errorEl.classList.add('show');
        }
      }

      loadState();
      setInterval(loadState, 10000);
    })();
    """
    return extra_head, body, script


def render_loot_tracker(player: PlayerView) -> str:
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
    npcBucketValues/windowItems/npcItems shape.

    The actual markup/script live in _loot_tracker_panel_markup just
    above -- this is now just that plus the _shell wrapper a real,
    logged-in-or-not page visit needs (see render_landing_loot_preview
    for the OTHER caller, which skips _shell entirely and embeds the
    same panel inline on the landing page instead)."""
    extra_head, body, script = _loot_tracker_panel_markup()
    return _shell(
        title="Loot Tracker — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )


def render_landing_loot_preview() -> Optional[Tuple[str, str, str]]:
    """The landing page's own interactive Loot Tracker preview -- a
    real visitor, logged in or not, can search/sort/hover items exactly
    like the genuine page, click an NPC tile to filter down to its own
    items, and click a bar in the chart to drill into that hour, all
    without an account behind any of it. Returns (extra_head, body,
    script) for render_landing to splice into its own markup, or None
    if the curated snapshot (app/data/landing_loot_demo.json, built by
    scripts/gen_landing_loot_demo.py -- see that script's own module
    docstring for what's in it and why it's fixed rather than
    randomized) isn't there to read, so a missing/corrupt file quietly
    falls back to the plain marketing image render_landing used before
    this existed, rather than breaking the whole landing page.

    Reuses _loot_tracker_panel_markup's body/script completely
    unmodified -- not a fork -- and layers three demo-only behaviors on
    top purely from the outside, in a wrapper script appended after it:

    1. A `fetch` shim, scoped to just this wrapper (a local `var fetch`
       inside its own IIFE, never touching window.fetch), that answers
       every one of the panel's own calls to /api/players/me/loot* out
       of the static snapshot instead of the network -- the base 24h
       read, a bucket-click's own scoped read (matched by that bucket's
       `start` timestamp against the snapshot's precomputed per-bucket
       payloads -- see gen_landing_loot_demo.py), and the per-tile
       hide/unhide POST/DELETE calls, which this shim actually tracks
       (two in-memory Sets, gone on refresh -- there's no real account
       here for a hide to persist against) rather than just no-opping,
       so hiding something here visibly moves the chart bars and header
       kc/gp totals the same way it would on the real page -- see
       recomputeAggregates/applyHiddenFlags below for exactly how much
       of build_loot_state's own hidden-NPC/hidden-item math that reuses
       versus redoes, and why. Critically, this shim being hit at all
       (for every one of these calls) also means none of them ever
       reach the REAL endpoint with a visitor's own real session
       cookie, which plain unmodified fetch() would otherwise do for a
       logged-in visitor who followed the header's own ?home=1 logo
       link back to this page.
    2. The range/date selector neutered right after the reused script
       finishes its own wiring -- explicitly asked to be non-
       interactive here, since a fixed one-day snapshot has no other
       range to actually switch to. Only the button's own click
       listener is stripped (cloneNode+replaceWith); the dropdown
       itself stays in the DOM, inert, since the reused script still
       reaches for it by id from several other code paths on every
       render.
    3. setInterval(loadState, 10000) inside the reused script keeps
       polling every 10s regardless -- harmless (it just re-renders the
       same static payload) rather than worth special-casing away.
    """
    demo = _get_landing_loot_demo_data()
    if demo is None:
        return None
    extra_head, body, script = _loot_tracker_panel_markup()

    # Landing-preview-only hero row, prepended in front of the reused
    # panel body -- the character (cropped to just its upper half, see
    # scripts that generated landing-loot-preview-char.png/.webp) and
    # the gold/white tagline that replaced the old static marketing
    # image's own baked-in copy (see anchor-loot-tracking.png/webp,
    # still on disk but no longer referenced) once this preview took
    # its place. The reused body's own "Loot Tracker" <h2> is hidden
    # purely via CSS (.landing-loot-preview .page-title, in
    # loot-tracker.css) rather than stripped here, so this still never
    # touches _loot_tracker_panel_markup's own markup -- same reuse
    # discipline as everything else in this function. See
    # .loot-preview-hero/.loot-preview-tagline-wrap/.loot-preview-char's
    # own landing-preview rules in loot-tracker.css: a plain flex row
    # bottom-aligns the character flush with the chart card's own top
    # border (no overlap), while the tagline's own wrap stretches to
    # fill whatever's left beside it and centers the text there both
    # ways.
    hero_markup = """
    <div class="loot-preview-hero">
      <div class="loot-preview-tagline-wrap">
        <p class="loot-preview-tagline">
          <span class="loot-preview-tagline-gold">LOOT TRACKING</span> <span class="loot-preview-tagline-white">like you've never experienced it before.</span>
        </p>
      </div>
      <picture class="loot-preview-char">
        <source srcset="/static/img/landing-loot-preview-char.webp" type="image/webp">
        <img src="/static/img/landing-loot-preview-char.png" alt="" />
      </picture>
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
      // One entry per hour -- {{npcName: {{killCount, items: {{itemHideKey: value}}}}}}
      // for whichever NPCs killed something that hour -- see
      // scripts/gen_landing_loot_demo.py's own module docstring for
      // exactly how this was built (the same _resolve_loot_items
      // pricing build_loot_state itself calls, not re-derived here).
      var HIDE_BREAKDOWN = {hide_breakdown_json};
      var ALL_HOUR_INDICES = HIDE_BREAKDOWN.map(function (_, i) {{ return i; }});

      // The demo's own client-side hide/unhide state -- the real
      // hidden set lives in the HiddenLootEntry table (app/models.py)
      // behind a real account; there's no account here, so this is
      // just two in-memory Sets, gone on refresh, keyed exactly like
      // the real npc_hide_key/item_hide_key (app/loot.py) so a hide
      // made against one casing/id-vs-name still matches consistently.
      var hiddenNpcs = new Set();
      var hiddenItemKeys = new Set();
      function npcHideKey(name) {{ return (name || '').trim().toLowerCase(); }}
      function itemHideKey(itemId, itemName) {{
        return itemId != null ? ('id:' + itemId) : ('name:' + (itemName || '').trim().toLowerCase());
      }}

      // Recomputes exactly the parts of a GET response that a hide/
      // unhide actually changes server-side (see build_loot_state's
      // own docstring in app/loot.py): a hidden NPC's kills drop out
      // of the buckets/windowValue/windowKills entirely, a hidden
      // item's own value drops out of every total it fed (bucket/
      // window/NPC alike) without touching kill counts -- everything
      // else (item names/icons/quantities, an NPC's own kill count,
      // every bucket's start/end) is exactly what build_loot_state
      // already computed and never needs redoing. `hourIndices` is
      // which absolute hour(s) (0-23) this payload's own buckets
      // correspond to, in order -- all 24 for the full-day view,
      // exactly one for an hour drilled into (see bucketUrl's own
      // comment in the reused script above for why that's always a
      // single bucket).
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
            // This NPC's own tile/bar always reflects its real kill
            // count and item-hidden-filtered value, whether or not
            // the NPC itself is hidden -- only the chart/header
            // totals below skip a hidden NPC's contribution entirely.
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

      // Clones the static snapshot, patches every "hidden" flag (item
      // names/icons/quantities and an NPC's own kill count stay
      // exactly as precomputed -- see this function's own doc comment,
      // point 1, for why those never change), and overlays the live
      // recomputation above onto the fields that do.
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

      // Shadows the outer/global fetch for everything inside this one
      // IIFE only (see this function's own doc comment, point 1) --
      // the reused script text below calls bare `fetch(...)`, which
      // JS resolves against the nearest enclosing scope that declares
      // one, so it finds THIS var rather than window.fetch without
      // that script needing to change at all. Now takes `options` too
      // (the reused script's own hide/unhide calls send a method +
      // JSON body -- see hideLootNpc/unhideLootItem/etc. below) since
      // telling POST/DELETE apart from GET, and reading who's being
      // hidden, both need it.
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
        // Nothing else the reused script calls should ever land here,
        // but a harmless no-op beats a hard failure if it someday does.
        return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{}}); }} }});
      }};

      {script}

      // Neutralizes the range/date selector -- runs after the reused
      // script above has already finished its own synchronous DOM
      // wiring (including this button's click listener), so stripping
      // it means replacing the node outright: cloneNode(true) copies
      // its markup/children but none of the listeners attached to the
      // original, which is exactly what "no longer clickable" means
      // here. The dropdown menu itself is left alone (still in the DOM,
      // still starting from its own display:none) rather than removed
      // -- with the button's own listener gone it can never be opened
      // in the first place, and the reused script still calls
      // document.getElementById('lootRangeMenu') from several other
      // places (closeRangeMenu, updateRangeMenuActive, the outside-
      // click handler, the menu's own click handler) on every render,
      // not just the button's click -- removing the node made those
      // throw on the null it got back instead.
      var rangeBtn = document.getElementById('lootRangeBtn');
      if (rangeBtn) {{
        rangeBtn.replaceWith(rangeBtn.cloneNode(true));
        document.getElementById('lootRangeBtn').classList.add('loot-range-btn--static');
      }}

      // The bottom-edge feather itself (.landing-loot-preview::after)
      // is a plain, unconditional CSS rule now -- see loot-tracker.
      // css's own comment on that selector for why this preview no
      // longer needs any JS here to toggle it on/off: the container is
      // pinned to a fixed height (that same CSS rule) rather than
      // shrinking to fit whatever's currently inside it, so the
      // feather -- and everything else about this box's own size and
      // position -- stays put regardless of how a filter (an NPC box
      // click down in #lootNpcRow, a search, a bar drill-down) changes
      // how much content is actually in it.
    }})();
    """
    return extra_head, body, wrapper_script


def render_landing_purchase_preview() -> Optional[Tuple[str, str, str]]:
    """The landing page's own interactive Purchase Goals preview --
    same idea as render_landing_loot_preview above (reuses
    _purchase_goals_panel_markup's body/script completely unmodified,
    layering demo-only behavior on top from the outside in a wrapper
    script), but backed by one real, curated snapshot instead of a
    generated one: app/data/landing_purchase_demo.json is a one-time
    GET /api/gear-setups pull of the account's own actual "Tombs of
    Amascut" gear setup, trimmed down to just that one setup. Unlike
    Loot Tracker (which had no real account to draw a realistic demo
    from, so scripts/gen_landing_loot_demo.py generates one), this
    account's own real setup already exists and is exactly what the
    player asked this preview show -- "what I do/don't have
    currently" -- so there's nothing to synthesize; the file is just
    that API response, frozen. It stays frozen deliberately (no
    regeneration script) -- a visitor's own browsing never changes it
    (see the fetch shim below), and it's not expected to be
    refreshed just because real prices/ownership drift over time. If
    the setup is ever renamed or replaced, recapture this file (log
    in, GET /api/gear-setups, keep just that one setup's object) and
    replace it directly. Returns (extra_head, body, script) for
    render_landing to splice into its own markup, same as the loot
    preview, or None if the snapshot isn't there to read.

    This preview is explicitly narrower than the real page: only one
    setup (no setup selector, no new/rename/delete -- see the
    .pg-header CSS override in purchase-goals.css), no "Purchase
    Goals" heading (also CSS -- .page-title), and nothing in the gear
    doll/inventory grid can be ADDED, REMOVED, or MOVED (no setup-icon
    picker either) -- a visitor can look, sort, and click through to
    the wiki, never edit. A plain click on a FILLED slot is the one
    exception (see point 2 below): same as the real page, it just
    opens that item's wiki page in a new tab. Sorting the "Still to
    Purchase" list (including dragging rows in Custom mode) is the
    other genuinely interactive thing here, tracked entirely in this
    wrapper's own local state (currentSort/customOrder below), the
    same "real but local, never hits the genuine endpoint" treatment
    Loot Tracker's hide/unhide got.

    1. A `fetch` shim, scoped to just this wrapper (a local `var
       fetch` inside its own IIFE, never touching window.fetch),
       answering GET /api/gear-setups out of the static snapshot
       (recomputing the "Still to Purchase" order/next-purchase from
       whatever currentSort/customOrder currently are -- see
       sortStillToPurchase/buildStatePayload below), and the two
       sort-related PUT endpoints for real (updating that same local
       state and returning the same recomputed payload the real
       endpoints would). Every other gear-setups/items-search call
       this script could still in principle make (it shouldn't ever,
       given points 2/3 below, but a shim answers all of them anyway,
       same discipline as the loot preview) gets a harmless failure
       response instead of ever reaching the real API with a visitor's
       own session cookie.
    2. mousedown/dragstart originating anywhere inside the gear doll +
       inventory grid (#pgGearFrame) are unconditionally caught and
       swallowed by one capturing-phase listener attached to that
       element once, up front -- see the comment further down for why
       that's the one reliable way to neuter this particular part of
       the reused script: wireSlotClicks rewires a fresh listener on
       every single .gear-slot element on every render (unlike the
       range button below, or Loot Tracker's, which are wired once),
       so a one-time cloneNode+replaceWith strip (which only ever
       catches whatever's wired at that instant) would just get
       silently undone the next time the panel re-renders. A CLICK
       gets the same capturing-phase treatment, but filtered rather
       than blanket-blocked: it's swallowed for a shift-click, a click
       on the hover "x" remove button, or a click on an EMPTY slot
       (would open the add-item picker), but let through untouched for
       a plain click on a FILLED slot -- wireSlotClicks' own listener
       for that exact case (further down in the reused script) already
       does nothing but window.open() the item's wiki page, so there's
       nothing to block there in the first place.
    3. The setup-display-icon trigger (#pgIconTrigger) IS wired only
       once, on script load (see render_purchase_goals's own script),
       so that one small edit affordance -- unrelated to any single
       gear slot, so #2 above doesn't already cover it -- gets the
       ordinary one-time cloneNode+replaceWith strip instead, same
       technique as Loot Tracker's own range button.
    4. setInterval(loadState, 5000) inside the reused script keeps
       polling every 5s regardless -- harmless (it just re-renders the
       same static payload, recomputed through whatever sort state
       this visitor's own clicks have left it in) rather than worth
       special-casing away.
    """
    demo = _get_landing_purchase_demo_data()
    if demo is None:
        return None
    extra_head, body, script = _purchase_goals_panel_markup()

    # Landing-preview-only hero row, prepended in front of the reused
    # panel body -- same technique as render_landing_loot_preview's own
    # hero_markup (see that function's comment for the fuller
    # reasoning), mirrored left-to-right: the character sits on the
    # LEFT here instead of the right, and the tagline's own wrap takes
    # up whatever's left on the right instead of the left, purely by
    # swapping which element comes first in this flex row (see
    # .purchase-preview-hero in purchase-goals.css -- a plain flex row,
    # same as .loot-preview-hero, still bottom-aligning both children
    # flush with the first real card below (the GP overlay) with no
    # overlap and no gap). The reused body's own "Purchase Goals" <h2>
    # is already hidden via CSS (.landing-purchase-preview .page-title,
    # in purchase-goals.css), same as Loot Tracker's.
    hero_markup = """
    <div class="purchase-preview-hero">
      <picture class="purchase-preview-char">
        <source srcset="/static/img/landing-purchase-preview-char.webp" type="image/webp">
        <img src="/static/img/landing-purchase-preview-char.png" alt="" />
      </picture>
      <div class="purchase-preview-tagline-wrap">
        <p class="purchase-preview-tagline">
          <span class="purchase-preview-tagline-gold">PURCHASE GOALS</span> <span class="purchase-preview-tagline-white">to prepare for your next big spending spree.</span>
        </p>
      </div>
    </div>
    """
    body = hero_markup + body

    demo_json = json.dumps(demo)
    wrapper_script = f"""
    (function () {{
      // The captured snapshot itself, exactly as GET /api/gear-setups
      // returned it for the real account's real "Tombs of Amascut"
      // setup (see this function's own docstring) -- {{coins,
      // pricesError, mappingError, gearSetups: [oneSetup], ownedItems}}.
      // Never mutated in place; buildStatePayload below always starts
      // fresh from this and only overlays the two fields sorting can
      // actually change.
      var DEMO_BASE = {demo_json};
      var SETUP_ID = DEMO_BASE.gearSetups[0].id;

      // This demo's own local sort state -- there's no account behind
      // this preview for a sort choice to persist against, so (like
      // Loot Tracker's hiddenNpcs/hiddenItemKeys) it's just plain
      // variables, gone on refresh. Mirrors the two fields
      // GearSetup.still_to_purchase_sort_mode/_custom_order hold
      // server-side for a real setup.
      var currentSort = DEMO_BASE.gearSetups[0].stillToPurchaseSort || 'low_to_high';
      var customOrder = null; // [{{slotType, slot}}, ...] once a Custom drag lands, else null

      function stillToPurchaseKey(entry) {{ return entry.slotType + '::' + entry.slot; }}

      // Exactly mirrors _still_to_purchase_summary's own sort branch
      // in app/purchase_goals.py -- same five modes, same tie-break
      // (custom falls back to cost-ascending for anything not in
      // customOrder yet, ranked after everything that is). Sorts a
      // copy of the snapshot's own already-resolved stillToPurchase
      // list rather than re-deriving it from equipment/inventory --
      // that list is already exactly the right (owned-filtered,
      // purchasable-filtered) set, so there's nothing left to redo
      // except reordering it.
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

      // Rebuilds the full GET-/api/gear-setups-shaped payload from
      // DEMO_BASE plus whatever currentSort/customOrder are right now
      // -- same three fields a real sort/reorder PUT changes
      // server-side (stillToPurchaseSort, stillToPurchase, and
      // nextPurchase, which is always just stillToPurchase[0] -- see
      // _still_to_purchase_summary's own comment on that), nothing
      // else ever touched.
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

      // Shadows the outer/global fetch for everything inside this one
      // IIFE only (see this function's own doc comment, point 1) --
      // the reused script text below calls bare `fetch(...)`, which
      // resolves to this local var instead of window.fetch without
      // that script needing to change at all.
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
        // Nothing else the reused script calls should ever actually
        // reach here (see this function's own doc comment, points 2
        // and 3 -- every other mutation's own UI trigger is neutered
        // before a click can start one), but a graceful failure beats
        // a hard one if it someday does, same as apiCall already
        // handles for a real failed request.
        return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{ message: 'Not available in this preview.' }}); }} }});
      }};

      {script}

      // Neutralizes the setup-display-icon trigger -- wired only once,
      // on script load (unlike every .gear-slot below it, which is
      // rewired fresh on every render -- see this function's own doc
      // comment, point 3), so the same one-time cloneNode+replaceWith
      // strip Loot Tracker's own range button uses works here too.
      var iconTrigger = document.getElementById('pgIconTrigger');
      if (iconTrigger) {{
        iconTrigger.replaceWith(iconTrigger.cloneNode(true));
        document.getElementById('pgIconTrigger').style.cursor = 'default';
      }}

      // Swallows every mousedown/dragstart anywhere inside the gear
      // doll + inventory grid, and every CLICK except the one case
      // that's actually allowed here -- a plain click directly on a
      // FILLED slot's item, which wireSlotClicks' own click handler
      // (below, in the reused script) already treats as nothing more
      // than a link out to the wiki (window.open(itemWikiUrl(...))),
      // never a mutation -- see that handler's own "a filled slot's
      // item is now a link out to the wiki instead of an editor"
      // comment. Everything else stays blocked exactly as before:
      // clicking an EMPTY slot (would open the add-item picker), the
      // hover "x" remove button, and a shift-click (starts/extends the
      // multi-select-and-apply group) all still get swallowed here,
      // before wireSlotClicks' own (freshly re-wired every render --
      // see this function's own doc comment, point 2) listeners ever
      // see them.
      //
      // A capturing-phase listener fires top-down, before any
      // bubbling-phase listener on the element itself, and
      // #pgGearFrame's own identity survives every render
      // (renderContent only ever replaces its innerHTML, never the
      // element itself -- see that function in the reused script
      // above), so this one registration -- made once, right here --
      // keeps working no matter how many times the doll/grid inside it
      // gets rebuilt from scratch. mousedown/dragstart are blocked
      // unconditionally (neither one is ever needed for a wiki-link
      // click, and blocking dragstart is what actually prevents a
      // drag-to-move from ever starting -- preventDefault there stops
      // the browser's own native drag regardless of mousedown); click
      // is filtered instead of blanket-blocked, per the paragraph
      // above. stopImmediatePropagation is what actually matters on
      // whichever ones this DOES block (it keeps the event from ever
      // reaching wireSlotClicks' own listeners on the slot
      // underneath); preventDefault alongside it also blocks a drag
      // from starting at all on mousedown/dragstart, so dragover/drop
      // on some OTHER slot never gets meaningful data to act on
      // either.
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
          // Filled slot, plain click, not the remove button -- let it
          // through to wireSlotClicks' own listener below, which opens
          // the wiki in a new tab and does nothing else.
        }}, true);
      }}

      // Same fixed-height container + always-on bottom-edge feather as
      // Loot Tracker's own preview -- see .landing-purchase-preview in
      // purchase-goals.css, and render_landing_loot_preview's own
      // wrapper script for the fuller comment this mirrors. No JS
      // needed here any more either, for the same reason.
    }})();
    """
    return extra_head, body, wrapper_script


def render_landing_mindmap_preview() -> Optional[Tuple[str, str, str]]:
    """The landing page's own interactive Mindmaps preview -- same idea
    as render_landing_loot_preview/render_landing_purchase_preview
    (reuses _mindmaps_panel_markup's body/script completely unmodified,
    layering demo-only behavior on top from the outside in a wrapper
    script), backed by one real, curated snapshot: app/data/
    landing_mindmap_demo.json is a one-time GET /api/mindmaps pull of
    the account's own real "Example" mindmap (there was only one to
    begin with -- see that file's own comment above). Returns
    (extra_head, body, script) for render_landing to splice into its
    own markup, same as the other two previews, or None if either the
    mindmap snapshot or its search-pools sidecar (see
    _get_landing_mindmap_search_pools_data's own comment) isn't there
    to read.

    Unlike Loot Tracker/Purchase Goals -- which only ever let a visitor
    look, sort, or (Purchase Goals) click through to the wiki -- this
    preview is genuinely, fully editable: add/recolor/delete/reparent
    nodes, undo/redo, fill in every goal type's criteria, exactly like
    the real page, per the player's own request ("essentially have a
    window/viewport they can work with to edit the mindmap all they
    want"). That's possible here in a way it wasn't for the other two
    because a mindmap's own tree-shape mutations (app/mindmaps.py's
    add_node/add_shared_child/update_node/delete_node/replace_nodes/
    clean_goal) never touch account-specific game state at all --
    unlike an item's price/ownership or a kill's own gp value, a
    node's text/color/order/parentId/goal criteria are just plain data
    the player themselves fully controls -- so porting that logic to
    JS below is enough for the whole editing experience to work
    faithfully against this one frozen snapshot, in memory, never
    reaching the real API. The one thing genuinely entangled with live
    account state -- a node's `completed` flag (app/mindmaps.py's
    evaluate_completion, checked against the player's own synced
    skills/items/quests/diary/kc) -- is simply frozen at whatever the
    snapshot already baked in per node id, EXCEPT the gray "manual
    complete" toggle (the one completion check that was never
    account-derived in the first place -- see setNodeGoal below) and
    the root node's own completed flag (always just "every other node
    here is complete," recomputed fresh from whatever's currently true
    of the nodes that exist right now -- see withRecomputedRoot).

    1. A `fetch` shim, scoped to just this wrapper (a local `var
       fetch` inside its own IIFE, never touching window.fetch), that:
       - Answers GET /api/mindmaps out of DEMO_MINDMAP's current node
         list (buildState below).
       - Implements every node-mutation endpoint FOR REAL against
         DEMO_MINDMAP.nodes, in memory -- addNode/addSharedChild/
         updateNode/deleteNode/replaceNodes/setNodeGoal below are each
         a faithful JS port of their same-named Python counterpart in
         app/mindmaps.py (see each function's own comment for exactly
         what it mirrors), so every add/recolor/delete/reparent/undo/
         redo/goal-save genuinely works, recomputing and returning the
         same full-state shape the real endpoint would. A validation
         failure (a goal missing a required field, a malformed undo/
         redo snapshot, ...) rejects the same way the real endpoint's
         400 does -- {{detail: "..."}} -- so the panel's own existing
         error handling (showError/showGoalSaveError) surfaces it
         exactly as it would for real.
       - Answers the three goal-criteria search endpoints
         (/api/npcs/search, /api/items/search, /api/quests/search)
         out of the bundled local SEARCH_POOLS (see
         _get_landing_mindmap_search_pools_data's own comment for why
         these are shimmed too rather than left to hit the real,
         session-authenticated endpoints) using the same startswith-
         then-contains ranking app/npc_names.py's search_npc_names
         (and its item/quest siblings) use server-side -- see
         localSearchNames/localSearchItems below.
       - Anything else (a mindmap-level create/rename/delete -- there's
         only ever the one mindmap here, and #mmSwitchBtn is neutered
         below so its menu can never even open to reach those) gets a
         harmless failure response instead of ever reaching the real
         API with a visitor's own session cookie.
    2. `localStorage` is ALSO shadowed here (a local `var localStorage`
       backed by a plain in-memory object, never touching
       window.localStorage) -- not for privacy/API-cookie reasons like
       `fetch` above, but because the reused script persists two
       preferences under real per-origin localStorage keys (
       myscape:mindmaps:editMode, myscape:mindmaps:activeMindmapId --
       see loadStoredEditMode/setActiveMindmapId in the reused script)
       and this landing page shares an origin with the real,
       authenticated Mindmaps page. Without this, a visitor who'd
       previously left Edit Mode on (or a different mindmap active) on
       the real page would find this preview silently inheriting that
       state instead of starting fresh -- and, worse, every toggle
       made HERE would overwrite THEIR real stored preference out from
       under them. An empty in-memory store fixes both: this preview
       always starts in Edit Mode off (exactly as requested) regardless
       of the visitor's real history, and nothing it does here ever
       touches their actual browser storage.
    3. #mmSwitchBtn -- wired only once, on script load (unlike, say,
       Purchase Goals' .gear-slot, which rewires fresh every render --
       this one's more like that page's #pgIconTrigger) -- gets the
       same one-time cloneNode+replaceWith strip, so its mindmap-
       switcher menu (new/rename/delete, and switching between
       mindmaps there aren't more than one of here) can never open.
       The rest of the toolbar -- undo/redo, zoom in/out/fit,
       fullscreen, and Edit Mode itself -- is left completely alone,
       exactly as the player asked ("have the actual buttons available
       in the normal mindmap editor").
    4. Same fixed-height container + always-on bottom-edge feather as
       the other two previews (.landing-mindmap-preview in mindmaps.
       css), even though .mm-canvas already has its own fixed height --
       between the hero row above it and the toolbar, the WHOLE panel
       can still exceed a short viewport, same reasoning as the other
       two.

    No setInterval here at all (see _mindmaps_panel_markup's own
    docstring -- the real page doesn't poll either), so unlike the
    other two previews there's nothing background to leave running or
    neutralize.
    """
    demo = _get_landing_mindmap_demo_data()
    search_pools = _get_landing_mindmap_search_pools_data()
    if demo is None or search_pools is None:
        return None
    extra_head, body, script = _mindmaps_panel_markup()

    # Landing-preview-only hero row, prepended in front of the reused
    # panel body -- same technique as the other two previews' own
    # hero_markup, mirrored the SAME way Loot Tracker's own is (tagline
    # on the left, image on the right -- Purchase Goals' is the one
    # that flipped it), per the player's own request this round. See
    # .mindmap-preview-hero in mindmaps.css for the shared flex-row/
    # bottom-align treatment (same as .loot-preview-hero/
    # .purchase-preview-hero, just under this preview's own class
    # names since its markup/CSS are Mindmaps', not either other
    # page's). The reused body's own "Mindmaps" <h2> is hidden via CSS
    # (.landing-mindmap-preview .page-title), same as the other two.
    hero_markup = """
    <div class="mindmap-preview-hero">
      <div class="mindmap-preview-tagline-wrap">
        <p class="mindmap-preview-tagline">
          <span class="mindmap-preview-tagline-gold">MINDMAPS</span> <span class="mindmap-preview-tagline-white">to help you plan every step of your grind.</span>
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
      // The captured snapshot itself, exactly as GET /api/mindmaps
      // returned it for the real account's real "Example" mindmap
      // (see this function's own docstring) -- {{mindmaps: [oneMindmap]}}.
      var DEMO_STATE = {demo_json};
      var DEMO_MINDMAP = DEMO_STATE.mindmaps[0];
      // The curated local search data (see
      // _get_landing_mindmap_search_pools_data's own comment) --
      // {{npcs: [name, ...], quests: [name, ...], items: [{{name, id}}, ...]}}.
      var SEARCH_POOLS = {search_pools_json};
      var ITEM_ICON_CDN_BASE = 'https://static.runelite.net/cache/item/icon/';

      // ---- localStorage shadow -- see this function's own docstring,
      // point 2, for why. A plain in-memory object standing in for the
      // two methods the reused script actually calls
      // (getItem/setItem/removeItem) -- nothing fancier is needed
      // since nothing here ever iterates keys or reads .length.
      var localStorage = (function () {{
        var store = {{}};
        return {{
          getItem: function (k) {{ return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; }},
          setItem: function (k, v) {{ store[k] = String(v); }},
          removeItem: function (k) {{ delete store[k]; }},
        }};
      }})();

      // ---- Mutation logic, ported from app/mindmaps.py -----------------
      //
      // Every function below is a faithful JS port of its same-named
      // Python counterpart -- same validation, same defaults, same
      // return shape (a brand new node array, never mutated in
      // place, exactly like the Python originals) -- so the fetch
      // shim further down can apply them against DEMO_MINDMAP.nodes
      // and hand back a response indistinguishable in SHAPE from the
      // real endpoint's, even though nothing here ever touches a
      // database. `completed` rides along as a plain field on each
      // node object (exactly how the real API already serializes it
      // -- see serialize_mindmap) rather than a separate side table;
      // see each function's own comment for exactly when it resets
      // vs. carries over untouched, and withRecomputedRoot further
      // down for the one field NEVER just carried over as-is.
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
      // Mirrors clean_goal in app/mindmaps.py -- see that function's
      // own docstring for the require_complete distinction (true for
      // a fresh goal-form save, false for restoring an undo/redo
      // snapshot).
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
      // Mirrors add_node in app/mindmaps.py -- returns {{nodes, newId}}.
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
      // Mirrors update_node in app/mindmaps.py -- a color change resets
      // `goal` back to a blank default for the new color (same as the
      // real page) AND resets `completed` back to false (the demo's
      // own addition -- see this function's own docstring, point 1 of
      // the wrapper's overall doc comment: whatever the snapshot froze
      // for the OLD color's criteria means nothing once those criteria
      // are gone).
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
      // Mirrors delete_node in app/mindmaps.py -- cascades to the
      // whole subtree, then prunes the deleted id(s) out of every
      // remaining node's own extraParentIds.
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
      // Mirrors replace_nodes in app/mindmaps.py -- what Undo/Redo
      // restore against (MM.undoStack/MM.redoStack, in the reused
      // script below, hold past copies of this same mindmap's own
      // node list). `completed` is carried over from the snapshot
      // being restored (it's a genuine past server-shaped response,
      // not fresh player input) rather than reset, same as every
      // OTHER field here being re-cleaned but not re-derived.
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
      // Mirrors set_node_goal in app/mindmaps.py -- also how a gray
      // node's manual "Complete" checkbox works (see clean_goal's own
      // 'manual' branch): for a gray node specifically, `completed` IS
      // the cleaned manualComplete flag, applied right here -- the one
      // completion check this demo can genuinely, correctly keep live
      // (see this function's own doc comment, point 1, in the wrapper's
      // overall docstring). Every other color's `completed` is left
      // exactly as it was; filling in real criteria here doesn't
      // (and, without live account context, can't) newly evaluate it.
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
      // The root's own `completed` is never just carried over -- see
      // evaluate_completion's own root-completion comment in
      // app/mindmaps.py: true iff the mindmap has at least one other
      // node and every one of them is complete. Every other node's
      // `completed` already knows its own right answer (frozen from
      // the snapshot, or freshly toggled by setNodeGoal above), so
      // this is a pure aggregation over values already sitting right
      // there on each node -- no account context needed, unlike every
      // OTHER color's own completion check.
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

      // ---- Local goal-criteria search -- see this function's own
      // docstring for why these are answered locally instead of ever
      // reaching /api/npcs|items|quests/search for real. Same
      // startswith-then-contains ranking (shortest match first within
      // each tier) as search_npc_names/search_quest_names/search_items
      // in the real Python modules.
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

      // ---- fetch shim -----------------------------------------------------
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
        // A mindmap-level create/rename/delete -- unreachable in
        // practice (see #mmSwitchBtn's own neutering below), and
        // anything else this script doesn't otherwise call. Graceful
        // failure, never the real network -- same discipline as the
        // other two previews' own catch-all.
        return fail('Not available in this preview.');
      }};

      // Disables wheel/trackpad-scroll zooming here -- only the
      // toolbar's own +/-/fit buttons should zoom this preview (per
      // this preview's own follow-up request), unlike the real page,
      // where scrolling over the canvas also zooms it (see the reused
      // script's own canvasEl 'wheel' listener, registered a moment
      // from now, just below). A first attempt at this intercepted the
      // event on a capturing-phase listener on the whole preview
      // wrapper and called both preventDefault and stopPropagation --
      // that did stop the zoom, but stopPropagation there also stopped
      // the SAME event from ever reaching the landing page's own
      // window-level 'wheel' listener (see the intro panel's snap-
      // scroll IIFE, above -- this landing page scrolls itself
      // entirely through that JS-driven section-snapping, not native
      // body scrolling), so a visitor's wheel gesture over this
      // preview did nothing at all instead of moving down the page.
      // stopPropagation can't selectively skip just ONE listener
      // without also blocking every other listener anywhere else on
      // the event's path (both further down and further back up), so
      // there's no way to stop just the reused canvas listener that
      // way without also breaking the page's own scroll-snapping.
      //
      // Instead, this shadows addEventListener on #mmCanvas itself,
      // scoped to just this one element instance (not the shared
      // prototype) -- the exact same "intercept the call, never touch
      // the reused source" spirit as this wrapper's own fetch shim
      // above, just aimed at addEventListener instead -- and wraps
      // the one 'wheel' listener the reused script is about to
      // register a moment from now, rather than dropping it outright: a wheel
      // event over the note textarea or the goal-search popover still
      // reaches the reused listener's own existing bail-out/swallow
      // logic for those two cases unchanged (see its own comment,
      // just below, for why those still need to behave exactly as
      // they do on the real page), but a plain wheel-over-canvas
      // event now skips the reused listener entirely -- nothing here
      // calls preventDefault or stopPropagation for that case, so the
      // event is free to bubble all the way up to the landing page's
      // own window-level 'wheel' listener and scroll-snap the page,
      // same as a wheel event anywhere else on it. Every other event
      // type this or any later code registers on the canvas passes
      // through to the real addEventListener untouched.
      //
      // One exception to all of the above (per this preview's own
      // follow-up request): once fullscreen (see setFullscreen/
      // .mm-fullscreen further down) the canvas fills the whole
      // browser window over top of the landing page entirely -- there
      // is no page left behind it to scroll-snap out from under a
      // wheel gesture any more, so the real page's own reason to
      // swallow this event (above) no longer applies, and scroll-to-
      // zoom is let through to the reused listener exactly like the
      // real Mindmaps page. Checked fresh on every wheel event (not
      // just once at listener-registration time) since a single
      // preview session can enter/exit fullscreen any number of times.
      var mmCanvasForWheelPatch = document.getElementById('mmCanvas');
      if (mmCanvasForWheelPatch) {{
        var mmRealAddEventListener = mmCanvasForWheelPatch.addEventListener.bind(mmCanvasForWheelPatch);
        mmCanvasForWheelPatch.addEventListener = function (type, listener, opts) {{
          if (type !== 'wheel') return mmRealAddEventListener(type, listener, opts);
          return mmRealAddEventListener('wheel', function (e) {{
            if (mmCanvasForWheelPatch.classList.contains('mm-fullscreen')) return listener(e);
            if (e.target.closest('[data-role="node-note-input"], .mm-node-note-text')) return listener(e);
            if (e.target.closest('[data-role="popover"]')) return listener(e);
          }}, opts);
        }};
      }}

      {script}

      // Neutralizes the mindmap-switcher trigger -- wired only once,
      // on script load (unlike, say, Purchase Goals' own .gear-slot,
      // which rewires fresh every render), so the same one-time
      // cloneNode+replaceWith strip Loot Tracker's own range button
      // and Purchase Goals' own #pgIconTrigger both use works here
      // too. Its menu (new/rename/delete/switch) can now never open --
      // there's only the one mindmap here anyway.
      var switchBtn = document.getElementById('mmSwitchBtn');
      if (switchBtn) {{
        switchBtn.replaceWith(switchBtn.cloneNode(true));
        document.getElementById('mmSwitchBtn').style.cursor = 'default';
      }}

      // Same fixed-height container + always-on bottom-edge feather as
      // the other previews -- see .landing-mindmap-preview in
      // mindmaps.css, and render_landing_loot_preview's own wrapper
      // script for the fuller comment this mirrors. No JS needed here
      // any more either, for the same reason.
    }})();
    """
    return extra_head, body, wrapper_script


def _mindmaps_panel_markup() -> Tuple[str, str, str]:
    """Builds Mindmaps' (extra_head, body, script) triple -- split out
    from render_mindmaps below (same reasoning, and the same split
    _purchase_goals_panel_markup/_loot_tracker_panel_markup went
    through first) so the landing page's own interactive preview
    (render_landing_mindmap_preview) can embed this exact same panel
    markup/script rather than forking a second copy of either. Nothing
    here references `player` at all -- everything below is rendered
    client-side from one polled-once JSON payload (GET /api/mindmaps,
    see app/mindmaps.py's build_mindmaps_state), so every mutation
    endpoint can just hand back the freshly recomputed state and let
    the same render() redraw everything. Unlike Loot Tracker/Purchase
    Goals, there's no background poll -- nothing external (no RuneLite
    plugin, no wiki prices) ever changes a mindmap out from under the
    player, so there's nothing to poll for that their own last action
    here hasn't already applied.

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
          <button type="button" id="mmUndoBtn" title="Undo" disabled>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>
          </button>
          <button type="button" id="mmRedoBtn" title="Redo" disabled>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
          </button>
          <div class="mm-zoom-divider"></div>
          <button type="button" id="mmZoomIn" title="Zoom in">+</button>
          <button type="button" id="mmZoomOut" title="Zoom out">&minus;</button>
          <button type="button" id="mmZoomFit" title="Zoom to fit">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="10.5" cy="10.5" r="6.5"></circle><line x1="20" y1="20" x2="15.5" y2="15.5"></line></svg>
          </button>
          <button type="button" id="mmFullscreenBtn" title="Fill browser window">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>
          </button>
          <div class="mm-zoom-divider"></div>
          <button type="button" id="mmEditModeBtn" title="Toggle Edit Mode">
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
      // A popover (.mm-node-popover, mindmaps.css) hangs below whichever
      // node opened it, well outside that node's own NODE_HEIGHT box --
      // for a node in the tree's LAST row, that routinely extends past
      // #mmWorld's own height (see POPOVER_HEIGHT_PAD's use in
      // renderCanvas for the full reasoning), since MARGIN above is only
      // 60px of breathing room past the deepest row, nowhere near a
      // popover's real height. The tallest popover content actually
      // renders around 250-260px (a KC/ITEM goal's icon search + note
      // field, or a SKILL goal's select+toggle row + target-validation
      // line, each plus the Save/Delete row) -- 420 leaves comfortable
      // headroom past that without needing to special-case which goal
      // type is open.
      var POPOVER_HEIGHT_PAD = 420;

      // Mirrors NODE_COLORS in app/mindmaps.py -- the fixed palette a
      // node's color can be (white is root-only, see that file's own
      // comment). Not iterated to build the goal-type picker directly
      // (see GOAL_TYPE_PICKER below, which also carries each color's
      // label/icon), but every ".mm-node-<color>" CSS class still
      // assumes exactly this set.
      var NODE_COLORS = ['gray', 'red', 'orange', 'yellow', 'green', 'blue', 'purple', 'white'];

      // Everything below mirrors app/mindmaps.py's own goal-type
      // constants exactly (GOAL_TYPE_BY_COLOR, SKILL_NAMES,
      // DIARY_AREAS, DIARY_TIERS) -- there's no endpoint
      // that hands these lists to the client, since they're small,
      // fixed, and only ever used to build the goal-criteria form
      // below (renderGoalFieldsHtml), not validated here at all (the
      // server re-validates everything via clean_goal regardless of
      // what this form happens to submit). If a color/skill/area/tier
      // is ever added on the server, this list needs the same addition.
      var GOAL_TYPE_BY_COLOR = {
        gray: 'manual', red: 'kc', orange: 'item', yellow: 'gp',
        green: 'skill', blue: 'quest', purple: 'diary', white: null,
      };
      // The goal-type picker's own 7 options (see
      // renderGoalTypePickerHtml) -- every NODE_COLORS entry except
      // "white" (never player-pickable -- see NODE_COLORS' own
      // comment in app/mindmaps.py), each labeled and iconed the way
      // the player asked: the icon files are the OSRS clan-settings
      // "rank titles" icons that best match each goal type visually
      // (Beast/Carry/Explorer/Merchant/Quester/Achiever), saved
      // locally under app/static/img/ rather than hot-linked from the
      // wiki. "gray" has no icon file -- see its own comment in
      // renderGoalTypePickerHtml for what it shows instead.
      // Ordered (not just listed) to match the 3-column grid the
      // player asked for exactly: row 1 KC/ITEM/GP, row 2
      // SKILL/QUEST/DIARY, row 3 MANUAL alone -- see .mm-type-picker
      // in mindmaps.css, a plain 3-up grid that just lays these out
      // in array order, so the order here IS the grid position.
      var GOAL_TYPE_PICKER = [
        { color: 'red', label: 'KC', icon: '/static/img/icon-goal-kc.png' },
        { color: 'orange', label: 'ITEM', icon: '/static/img/icon-goal-item.png' },
        { color: 'yellow', label: 'GP', icon: '/static/img/icon-goal-gp.png' },
        { color: 'green', label: 'SKILL', icon: '/static/img/icon-goal-skill.png' },
        { color: 'blue', label: 'QUEST', icon: '/static/img/icon-goal-quest.png' },
        { color: 'purple', label: 'DIARY', icon: '/static/img/icon-goal-diary.png' },
        { color: 'gray', label: 'MANUAL' },
      ];
      // Icon path by color, for the same icon shown inside a node
      // itself next to its (goal-derived) label text -- see
      // goalDisplayText/renderCanvas. Built from GOAL_TYPE_PICKER
      // rather than duplicated, so the two never drift out of sync.
      var GOAL_TYPE_ICON_BY_COLOR = {};
      GOAL_TYPE_PICKER.forEach(function (opt) { if (opt.icon) GOAL_TYPE_ICON_BY_COLOR[opt.color] = opt.icon; });
      // The note-flip button's two icons (see renderCanvas) -- a plain
      // page/paper outline for "there's a note here, click to read it",
      // and a back-arrow for "click to flip back" once it's showing.
      // Same feather-icon-style stroke SVG as the zoom/edit-mode/undo/
      // redo toolbar buttons (see .mm-node-note-toggle svg in
      // mindmaps.css for the sizing).
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
      // Mirrors MIN_SKILL_LEVEL/MAX_SKILL_LEVEL/MIN_SKILL_XP/MAX_SKILL_XP
      // in app/mindmaps.py -- used only for the skill goal's inline,
      // as-you-type target validation (see validateSkillTarget); the
      // server re-validates against its own copy of these regardless.
      // Goes all the way up to 126 -- OSRS's "virtual level" cap, past
      // the real level-99 cap -- and down to 1 (not the trivially-
      // already-true 2 this used to start at): both ends are allowed
      // as goals now, on request, even though "reach level 1" is
      // always already met. MIN_SKILL_XP follows level 1 down to 0
      // (was 1) for the same reason -- level 1 IS 0 xp (see
      // SKILL_XP_TABLE below), and the LVL/XP conversion this enables
      // (see the metric segmented-toggle's click handler) needs 0 to
      // be a valid xp value or switching a level-1 target over to XP
      // would immediately show as out of range.
      var MIN_SKILL_LEVEL = 1, MAX_SKILL_LEVEL = 126;
      var MIN_SKILL_XP = 0, MAX_SKILL_XP = 200000000;
      // Mirrors MAX_KC_TARGET/MAX_ITEM_QTY_TARGET/MAX_GP_TARGET in
      // app/mindmaps.py -- used only for this popover's own client-side
      // required/range check before a save request is even sent (see
      // validateGoalFieldsForSave below); the server re-validates
      // against its own copies regardless. All three share the same
      // min of 1 as their server-side counterparts.
      var MAX_KC_TARGET = 1000000;
      var MAX_ITEM_QTY_TARGET = 2000000000;
      var MAX_GP_TARGET = 100000000000;
      // The OSRS xp-per-level curve (levels 1-126, including the
      // "virtual" levels above the real level-99 cap -- see
      // https://oldschool.runescape.wiki/w/Experience for the formula
      // this implements exactly: xp(L) = floor(1/4 * sum[l=1..L-1] of
      // floor(l + 300*2^(l/7))). Built once here off MAX_SKILL_LEVEL
      // rather than hardcoded, so it can never drift from whatever the
      // level cap above says, and used only to convert the skill
      // goal's target field between LVL and XP when that toggle
      // switches (see the metric segmented-toggle's click handler
      // below) -- SKILL_XP_TABLE[L] is the total xp needed for level
      // L; index 0 is unused (levels are 1-indexed) and
      // SKILL_XP_TABLE[1] is always 0.
      var SKILL_XP_TABLE = (function () {
        var table = [0, 0];
        var cumulative = 0;
        for (var l = 1; l < MAX_SKILL_LEVEL; l++) {
          cumulative += Math.floor(l + 300 * Math.pow(2, l / 7));
          table[l + 1] = Math.floor(cumulative / 4);
        }
        return table;
      })();
      // The xp SKILL_XP_TABLE says level "level" needs, clamped into
      // range -- used when the metric toggle switches from LVL to XP.
      function xpForLevel(level) {
        level = Math.max(MIN_SKILL_LEVEL, Math.min(MAX_SKILL_LEVEL, Math.round(level)));
        return SKILL_XP_TABLE[level];
      }
      // The level a given amount of xp has actually reached -- the
      // LARGEST level whose own requirement is at or below it (5,750
      // xp sits between level 22's 5,624 and level 23's 6,291, so this
      // reads as 22, same as the in-game skills tab would show), used
      // when the metric toggle switches from XP to LVL.
      function levelForXp(xp) {
        for (var l = MAX_SKILL_LEVEL; l >= MIN_SKILL_LEVEL; l--) {
          if (xp >= SKILL_XP_TABLE[l]) return l;
        }
        return MIN_SKILL_LEVEL;
      }
      // Endpoint each goal-field search box (see renderSearchFieldHtml/
      // runGoalSearch) queries, keyed by its data-search-kind. "item"
      // reuses Purchase Goals' own item search outright (see
      // app/main.py's item_search) -- no Mindmaps-specific backend
      // needed there at all.
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
      // A couple of these need their own label rather than a
      // mechanical underscore-to-space/title-case conversion (the
      // in-game diary names really are "Kourend & Kebos" and
      // "Lumbridge & Draynor", not "Kourend Kebos").
      var DIARY_AREA_LABELS = {
        ardougne: 'Ardougne', desert: 'Desert', falador: 'Falador',
        fremennik: 'Fremennik', kandarin: 'Kandarin', karamja: 'Karamja',
        kourend_kebos: 'Kourend & Kebos', lumbridge_draynor: 'Lumbridge & Draynor',
        morytania: 'Morytania', varrock: 'Varrock',
        western_provinces: 'Western Provinces', wilderness: 'Wilderness',
      };
      var DIARY_TIERS = ['easy', 'medium', 'hard', 'elite'];
      function titleCase(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
      // Each diary area's icon is its own elite-tier "main reward" item
      // (per https://oldschool.runescape.wiki/w/Achievement_Diary's
      // "List of diaries" table, 4th sub-column under "Main reward") --
      // "Ardougne cloak 4", "Rada's blessing 4", etc. Hardcoded RuneLite
      // CDN URLs (same static.runelite.net/cache/item/icon/<id>.png
      // scheme item_icon_url in app/purchase_goals.py already serves
      // every OTHER item icon from) rather than resolved through the
      // item search endpoint at render time -- these 12 are fixed and
      // already known, so there's nothing to look up live.
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
      // Backs the skill/diary goal fields' search boxes (see
      // renderLocalSearchFieldHtml) -- unlike the KC/ITEM/QUEST fields
      // (GOAL_SEARCH_ENDPOINTS), there's no server round-trip for
      // these: SKILL_NAMES/DIARY_AREAS are already the complete,
      // already-in-memory list, so runGoalSearch just filters one of
      // these two arrays client-side instead. Each entry's `value` is
      // what actually gets saved (a skill's lowercase key, a diary's
      // area slug -- exactly what the old <select>'s own option value
      // was); `label` is what the player types/sees/picks by (a
      // skill's title-cased name, a diary's real in-game name). Sorted
      // by label, same alphabetize-it convention used elsewhere on
      // this redesign (e.g. Goal Tracking's own skill/boss search
      // lists), rather than DIARY_AREAS' own slug order.
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
        // Which nodes are currently showing their note-flipped backside
        // (see the note-toggle button in renderCanvas) -- purely a
        // client-side view toggle, never sent to or read from the
        // server, so it's fine for this to reset on a page reload. Not
        // pruned when a mindmap switches or a node's deleted -- a
        // stale id left in here just never matches anything real again
        // (ids are UUIDs, never reused), same "harmless to leave"
        // reasoning as pointer/click state elsewhere on this page.
        flippedNodeIds: new Set(),
        nameFormMode: null, // 'new' | 'rename' | null
        pan: { x: 0, y: 0 },
        zoom: 1,
        lastLayout: null, // set by renderCanvas, read by zoomToFit
        // Per-mindmap edit history -- each entry is a full past
        // activeMindmap().nodes snapshot (this same mindmap's own
        // prior server-returned state), not a diff. See
        // recordUndoableEdit/undo/redo below; cleared whenever the active mindmap
        // changes (see setActiveMindmapId) since one mindmap's history
        // has no meaning against a different one's node tree.
        undoStack: [],
        redoStack: [],
        // Off by default -- a fresh visit (or a fresh browser) always
        // opens in view-only mode; see setEditMode below for what
        // toggling this actually changes. Loaded from storage right
        // after this object literal (loadStoredEditMode is a hoisted
        // function declaration, so the forward reference below is
        // fine even though its own definition sits further down next
        // to the other per-browser storage helpers).
        editMode: false,
        // Whether the canvas currently fills the browser window (see
        // setFullscreen below) -- unlike editMode/activeMindmapId just
        // above, deliberately NOT persisted across a reload: it's a
        // transient "focus on the map for a bit" view state, not a
        // standing preference, so a fresh visit always starts normal-
        // sized the way a video player doesn't remember you left it
        // fullscreen last time either.
        fullscreen: false,
      };
      MM.editMode = loadStoredEditMode();

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
        // A different mindmap's node-tree snapshots don't mean
        // anything against this one -- every switch (including the
        // very first load) starts its edit history fresh.
        MM.undoStack = [];
        MM.redoStack = [];
        try {
          if (id) localStorage.setItem(ACTIVE_MINDMAP_STORAGE_KEY, id);
          else localStorage.removeItem(ACTIVE_MINDMAP_STORAGE_KEY);
        } catch (e) { /* ignore -- see comment above */ }
      }

      // Edit Mode -- the pencil toggle below the zoom controls (see
      // #mmEditModeBtn/updateEditModeButton) that splits the canvas
      // into two very different interaction modes:
      //
      //   - OFF (the default): the player can pan/zoom/select a node
      //     to look at it, and -- the one exception -- still click a
      //     GRAY node's "Mark complete" toggle (see
      //     renderNodePopoverHtml), since checking off a manual goal
      //     isn't "editing" the tree the way changing its structure or
      //     criteria is. Renaming, recoloring, adding/deleting nodes,
      //     and filling in a trackable goal's criteria are all
      //     unavailable.
      //   - ON: everything above, plus the full editor -- contenteditable
      //     labels, the edge "+" buttons, color swatches, delete, the
      //     per-color goal criteria form, and multi-select/shared-child.
      //
      // Persisted per-browser (not per-player) the same way
      // ACTIVE_MINDMAP_STORAGE_KEY is, so leaving and coming back
      // doesn't silently drop the player into the other mode.
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
        // Leaving edit mode drops a 2+ multi-select down to just its
        // anchor -- shared-child selection has no meaning once the
        // "Add shared child" action that used it is no longer
        // reachable, so nothing should linger looking selected with
        // no available action attached to it.
        if (!on && MM.multiSelectIds.size > 1) {
          MM.multiSelectIds = MM.selectedNodeId ? new Set([MM.selectedNodeId]) : new Set();
        }
        // Entering edit mode also flips every flipped node back to its
        // front face. The note-toggle (paper) icon is hidden for the
        // whole duration of edit mode (see .mm-view-mode's rule in
        // mindmaps.css) since the edge buttons' own "+" icons are
        // already competing for the same corner of a node, so a note
        // left flipped open from browsing would just be dead, unreadable
        // clutter sitting there with no way to flip it back until edit
        // mode is left again -- clearing the flip set up front means
        // there's never a stuck-open back face to worry about instead.
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

          // Moving n itself isn't enough -- if n has its own children
          // (an ordinary node added below a shared child, say), THEIR
          // x was computed during the walk() above relative to n's
          // OLD (pre-nudge) position, and they never get touched by
          // this loop themselves (only nodes with their own
          // extraParentIds do). Left alone, the fan-out connector from
          // n down to its own first child ends up trying to join two
          // verticals that no longer share an x at all -- since that
          // segment is only ever bridged by a horizontal bus when n
          // has 2+ children (see the single-child branch below in the
          // connector-drawing pass), a single child just renders as a
          // disconnected floating stub. So shift n's WHOLE subtree
          // (every descendant, recursively, via childrenMap) by the
          // exact same delta as n itself moved -- that keeps their
          // positions relative to n frozen, so everything n carries
          // down with it stays visually attached and its connectors
          // stay straight, exactly as if the whole subtree had simply
          // been drawn starting from n's new spot to begin with.
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

      // ---- Pan/zoom ---------------------------------------------------

      // .mm-world carries a CSS transition on `transform` (see
      // mindmaps.css) so every zoom change -- the +/-/fit buttons, the
      // wheel, and every "just loaded/switched into a mindmap" moment
      // (see zoomToFit's own comment), all of which end up calling
      // applyTransform through setZoom/zoomToFit -- animates smoothly
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
        // The floating goal-search dropdown (see getFloatingSuggestionsEl)
        // lives outside .mm-world now, so it doesn't move on its own
        // when this transform changes the way an ordinary in-canvas
        // popover child would -- every call site that pans/zooms the
        // canvas funnels through here, so this is the one place that
        // needs to re-sync its screen position. A no-op whenever the
        // dropdown isn't actually open (see positionFloatingSuggestions).
        positionFloatingSuggestions();
      }

      // The outer zoom-out limit -- how far away the player can pull
      // back -- twice as far out as it used to be (was 0.4; a LOWER
      // zoom factor shows MORE of the world in the same viewport
      // pixels, so halving it is what doubles the visible width/height
      // -- see MIN_ZOOM's own use in setZoom/zoomToFit below, both
      // previously hardcoding 0.4 here). MAX_ZOOM (the zoom-IN limit)
      // is untouched -- only the zoom-out side of this was asked for.
      var MIN_ZOOM = 0.2;
      var MAX_ZOOM = 2;

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
        var newZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, z));
        if (newZoom !== MM.zoom) {
          var worldX = (originX - MM.pan.x) / MM.zoom;
          var worldY = (originY - MM.pan.y) / MM.zoom;
          MM.zoom = newZoom;
          MM.pan.x = originX - worldX * MM.zoom;
          MM.pan.y = originY - worldY * MM.zoom;
          applyTransform();
        }
        // Called even when newZoom didn't move MM.zoom at all (already
        // sitting right on a limit and asked to go further the same
        // way) -- cheap, and the buttons need to reflect that limit
        // whether this is the click that FIRST reached it or the
        // twentieth click that's still pinned there.
        updateZoomButtons();
      }

      // Nudges the pan (never the zoom) just enough that a freshly-
      // opened popover's edges clear .mm-canvas's own edges, when the
      // node it belongs to sits near the bottom (most common -- see
      // POPOVER_HEIGHT_PAD's own comment on why a popover routinely
      // reaches well past its node) OR off to either side of the
      // current view -- called after every render (see renderCanvas's
      // own post-render effect), since which node's selected and how
      // tall/wide its popover is (a bare swatch row vs. a full goal-
      // criteria form) both change render to render. Deliberately
      // goes through MM.pan/applyTransform rather than leaving it to
      // the browser's own native "scroll the focused element into
      // view" -- that scrolls .mm-canvas's own scrollTop, which every
      // OTHER absolutely-positioned child of .mm-canvas (the zoom
      // controls above all) visually rides along with, popping them
      // out past the canvas's own fixed on-screen box (still clipped
      // by its overflow: hidden) until the view's panned back
      // manually -- exactly the "toolbar buttons get left behind" bug
      // this replaces. MM.pan is the one thing this component ever
      // moves content through, so this is the only path that leaves
      // the zoom controls' own screen position alone. Purely a
      // vertical nudge, same margin idea as scrollPickerIntoView
      // elsewhere on the site (see its own comment) -- just through
      // this canvas's own pan instead of the page's scroll, and never
      // shrinking/zooming the popover to force it to fit.
      //
      // Always measures overflow against MM.pan itself -- wherever the
      // view is ACTUALLY resting right now, including any earlier
      // nudge from this same popover session -- never against some
      // remembered "where this popover session started" baseline. An
      // earlier version of this function anchored every measurement to
      // exactly that kind of baseline (nudge FROM the pan the popover
      // first opened at, every single render), specifically so that
      // switching to a shorter type would land back at that original
      // spot -- which sounds reasonable, but wasn't: it meant switching
      // from a tall type (a KC goal, say, which had nudged the view
      // down to fit) back to a short one (Item) actively snapped the
      // view back UP to the original spot on every single switch, even
      // though the short popup already fit perfectly well wherever the
      // tall one had left the view -- there was nothing there to
      // scroll for. That's exactly the reported bug: switching Item ->
      // KC scrolls down as expected (KC's popover genuinely doesn't
      // fit yet), but switching back to Item scrolled back up too,
      // even though Item's popover was never in any danger of running
      // past the view at all. Measuring from the current pan instead
      // makes this purely one-directional: a type that overflows
      // nudges the view just enough to fit it, and a type that
      // doesn't -- shorter or not -- never moves anything, because
      // there's nothing left here to "restore" toward.
      function ensurePopoverVisible() {
        var popover = document.querySelector('#mmNodesLayer [data-role="popover"]');
        if (!popover) return;
        var layout = MM.lastLayout;
        var pos = layout && MM.selectedNodeId ? layout.positions[MM.selectedNodeId] : null;
        // Nothing to line the popover up against without its node's own
        // layout position -- shouldn't happen while one's actually showing
        // (renderNodePopoverHtml/renderSharedChildPopoverHtml only ever
        // render for the current selection), but bail rather than throw
        // if render() and this ever end up looking at different nodes.
        if (!pos) return;
        var canvas = document.getElementById('mmCanvas');
        var canvasRect = canvas.getBoundingClientRect();
        // Worked out analytically instead of measuring the popover's live
        // getBoundingClientRect(), on purpose. .mm-world carries an
        // always-on 0.18s transform transition (see its own comment in
        // mindmaps.css), so switching node TYPE in the edit popup (or any
        // other rapid back-to-back popover change) can fire a fresh
        // render() -- and therefore a fresh call to this function -- well
        // within the PREVIOUS call's own 180ms glide, while that glide is
        // still carrying the world toward an earlier target. Reading
        // getBoundingClientRect() here would catch the popover wherever
        // that still-running glide happens to have painted it so far,
        // not where it's actually headed -- exactly the kind of
        // "seemingly random" up/down jump switching types used to
        // produce, since it depended on how far a still-running
        // transition had gotten rather than on the new type's actual
        // popover height.
        //
        // Computing the popover's box from data instead of the DOM's
        // current paint sidesteps all of that: .mm-world's transform is
        // `translate(pan.x, pan.y) scale(zoom)` with transform-origin 0 0
        // (mindmaps.css), so screen = pan + zoom * local for any point in
        // its LOCAL (pre-transform) coordinate space -- and MM.pan/MM.zoom
        // are the authoritative JS-tracked targets regardless of whatever
        // a CSS transition is still animating toward on screen. The
        // popover's local box comes from the exact same CSS it's actually
        // laid out with (.mm-node-popover: `top: calc(100% + 22px)` off
        // its node, `left: 50%` then `transform: translateX(-50%)` to
        // center under it) plus offsetWidth/offsetHeight -- pure layout
        // measurements render() just settled synchronously, and (unlike
        // getBoundingClientRect) never affected by .mm-world's own
        // pan/zoom transform, so they're accurate the instant this runs
        // no matter what's still mid-glide. That leaves nothing here
        // depending on transition timing at all.
        var localTop = pos.y + NODE_HEIGHT + 22;
        var localBottom = localTop + popover.offsetHeight;
        var localCenterX = pos.x + NODE_WIDTH / 2;
        var localLeft = localCenterX - popover.offsetWidth / 2;
        var localRight = localCenterX + popover.offsetWidth / 2;
        var MARGIN = 16;

        // Applied as a single target pan and left to glide there
        // normally -- never force-snapped first -- so a popover that
        // doesn't overflow from wherever the view already sits simply
        // never moves, and one that does gets exactly one smooth scroll
        // toward it, matching "only scroll if this type actually runs
        // past the view right now."
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

        // Same idea, sideways -- a node isn't always near the horizontal
        // center of the tree, and the popover is centered under its node,
        // so a node close to either edge of the current view can have its
        // popover run past .mm-canvas's own left/right edge exactly the
        // same way one near the bottom runs past the bottom edge above.
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

      // Used to scroll the outer PAGE (as opposed to ensurePopoverVisible
      // above, which only pans the canvas's own internal .mm-world) to
      // bring an off-the-page-fold popover into view in the embedded
      // (non-fullscreen) mindmap canvas -- deliberately a no-op now,
      // by request: interacting with anything inside the canvas (open a
      // popover, close it, switch from one node's to another's) must
      // never move the page's own scroll position while not in
      // full-browser view, even if that leaves a popover that opens
      // near the bottom of a long page partly below the fold. The
      // restore-on-close half of the old behavior (scrolling the page
      // back to wherever it was before a popover nudged it) was landing
      // wrong often enough to read as the canvas randomly jerking the
      // whole page up and down on ordinary clicks -- simplest correct
      // fix is to stop ever touching window.scrollY from here at all,
      // not to chase that restore logic further. Kept as a real
      // function (rather than deleted, with both call sites below
      // removed) purely so those call sites don't need touching --
      // still called in the same two places, still fullscreen-guarded
      // below for anyone tracing this by log/breakpoint, it just no
      // longer does anything.
      function scrollCanvasPopoverIntoView() {
        if (MM.fullscreen) return;
        // Deliberately empty -- see the comment above.
      }

      // Fits the WHOLE tree's bounding box inside the current viewport
      // -- picks whichever of width/height is the tighter constraint,
      // clamped to the same MIN_ZOOM-MAX_ZOOM range as everything else,
      // then centers the fitted box in the viewport. Uses the actual tight
      // bounding box of the node positions themselves (not
      // layout.worldWidth/worldHeight) -- those two are sized for
      // computeLayout's own arithmetic convenience and end up with
      // more empty margin past the last column/row than before the
      // first one, so centering THAT box visibly drags the real
      // content off-center (left/up) instead of centering what's
      // actually on screen.
      //
      // Also what every "just loaded/switched into a mindmap" moment
      // frames the view with -- the initial page load, switching
      // mindmaps from the menu, creating a new one, and deleting the
      // active one (see each one's own call below) -- so the very
      // first thing a player sees of a mindmap is the whole tree, not
      // whatever zoom/pan happened to be left over (or a fixed 1x
      // centered on just the root, which is what this used to do
      // before it was folded into zoomToFit here).
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
        var z = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Math.min(availW / boxW, availH / boxH)));
        MM.zoom = z;
        var boxCenterX = minX + boxW / 2, boxCenterY = minY + boxH / 2;
        MM.pan.x = viewW / 2 - boxCenterX * z;
        MM.pan.y = viewH / 2 - boxCenterY * z;
        applyTransform();
        updateZoomButtons();
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

      // Swapped into #mmFullscreenBtn's own innerHTML by setFullscreen
      // below -- Feather's maximize-2/minimize-2 glyphs, the same
      // Feather icon set the Undo/Redo/Zoom-fit buttons' own <svg>
      // markup (see the body HTML above) already draws its path data
      // from, kept as plain string constants here rather than two more
      // static <svg> tags in the HTML since only one of the two is
      // ever showing at a time.
      var MM_FULLSCREEN_ENTER_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>';
      var MM_FULLSCREEN_EXIT_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline><line x1="14" y1="10" x2="21" y2="3"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>';

      // Fills the browser window rather than the real Fullscreen API
      // (see .mm-canvas.mm-fullscreen in mindmaps.css for why) -- a
      // plain CSS class toggle on the canvas itself, so there's no
      // permission prompt and Escape backs out of it the same way it
      // would close a menu or popover (see the keydown listener below).
      // documentElement's own scroll is locked for the duration -- the
      // canvas's normal 620px slot in the page collapses to nothing
      // the instant it goes position: fixed, which would otherwise
      // leave just enough page height behind it for a stray keyboard/
      // touch scroll to reveal a sliver of the header/footer this is
      // now covering. zoomToFit() re-frames the tree to the new
      // viewport size either direction, same as clicking Zoom To Fit
      // by hand -- the pan/zoom transform has no way to know the
      // canvas just changed size out from under it otherwise.
      function setFullscreen(on) {
        if (on === MM.fullscreen) return;
        commitActiveLabelIfEditing();
        MM.fullscreen = on;
        document.getElementById('mmCanvas').classList.toggle('mm-fullscreen', on);
        document.documentElement.style.overflow = on ? 'hidden' : '';
        var btn = document.getElementById('mmFullscreenBtn');
        btn.classList.toggle('active', on);
        btn.title = on ? 'Exit full-browser view' : 'Fill browser window';
        btn.innerHTML = on ? MM_FULLSCREEN_EXIT_ICON : MM_FULLSCREEN_ENTER_ICON;
        zoomToFit();
        // zoomToFit just re-framed the WHOLE tree for the canvas's new
        // size, with no idea a popover might be open -- ensurePopoverVisible
        // and scrollCanvasPopoverIntoView normally handle keeping an open
        // popover on screen, but both only ever run from the render()
        // pipeline's own post-render effect, which entering/exiting
        // fullscreen never goes through. Left alone, a popover that was
        // open going into this call stays open coming out of it, parked
        // wherever zoomToFit's brand new pan happens to land -- which,
        // jumping between the fullscreen canvas and the much smaller
        // embedded one, is essentially never still in view (confirmed
        // live: exiting fullscreen with a popover open left it fully
        // rendered but positioned entirely below the viewport, nothing
        // ever having scrolled or panned to reveal it -- this is what
        // "closing out" of fullscreen with a popup still open was
        // leaving cut off).
        //
        // ensurePopoverVisible measures overflow straight off MM.pan
        // itself now (see its own comment), so there's no separate
        // baseline left to reset here either -- zoomToFit just set
        // MM.pan to the new canvas size's own correct resting spot, and
        // that's exactly what the very next ensurePopoverVisible call
        // below measures the popover against, same as it would after
        // any other render.
        // (scrollCanvasPopoverIntoView had its own version of this kind
        // of reset once too, for the outer page's own scroll position --
        // removed along with the rest of that function's body, see its
        // own comment, so there's nothing left to reset for it either.)
        if (MM.selectedNodeId) {
          // zoomToFit's own applyTransform() just kicked off .mm-world's
          // 0.18s CSS transition (see its own "carries a CSS transition"
          // comment) -- ensurePopoverVisible reading the popover's
          // getBoundingClientRect() right now would catch it mid flight,
          // not where zoomToFit is actually sending it. scrollCanvasPopoverIntoView
          // is still called right after, same as every other render, but
          // is a deliberate no-op now (see its own comment) -- nothing
          // left downstream of it to race against. Confirmed live in an
          // isolated harness against these exact functions: without
          // this, the popover still ended up cut off after exiting
          // fullscreen, just less than before -- the internal pan nudge
          // was landing on a wrong value computed from the pre-zoomToFit
          // popover position. Force this whole "canvas just changed
          // size, put the popover back in view" dance to land instantly
          // -- there's no reason to glide through it anyway, since the
          // canvas itself already jumps between fixed and absolute
          // positioning with no transition of its own the instant
          // fullscreen toggles.
          mmWorldEl.style.transitionDuration = '0s';
          ensurePopoverVisible();
          scrollCanvasPopoverIntoView();
          mmWorldEl.style.transitionDuration = '';
        }
      }

      // Blurring a still-editing label (see commitActiveLabelIfEditing
      // above) fires the label's own text-commit PATCH in the
      // background (see commitNodeTextFromLabel below) -- if a click
      // that's ALSO acting on that same node (recoloring it, adding a
      // node relative to it, deleting it...) fired its own request
      // immediately afterward, the two requests raced: whichever
      // response landed second would blow away and rebuild the node's
      // whole DOM out from under the first response's, still-settling
      // one, which is what produced a stray, wrongly-positioned caret
      // flashing in the node for an instant. The click delegation
      // below awaits this before doing anything else, so the text
      // commit's own render always finishes first.
      var pendingLabelCommit = null;

      var canvasEl = document.getElementById('mmCanvas');
      var panState = { active: false, startX: 0, startY: 0, startPanX: 0, startPanY: 0, moved: false };
      canvasEl.addEventListener('pointerdown', function (e) {
        commitActiveLabelIfEditing();
        // A node's own handler owns clicks on it (selection), and the
        // zoom/undo/redo control buttons need their native click to
        // fire normally -- setPointerCapture below would otherwise
        // redirect that click's events to the canvas instead, since
        // they're also DOM descendants of it, silently swallowing the
        // button press.
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
      // ---- Wheel-zoom ---------------------------------------------------
      // Same reasoning as the pan-dragging handlers just above: a real
      // scroll/pinch-to-zoom gesture fires MANY wheel events per second
      // (a trackpad especially), and .mm-world's CSS transition (see
      // mindmaps.css) means every single one of those ticks -- not just
      // the gesture as a whole -- would otherwise restart a fresh 0.18s
      // transform transition on top of whichever previous one is still
      // running. For the length of the whole gesture .mm-world would sit
      // in an unbroken, continuously-restarted transform ANIMATION rather
      // than a series of discrete jumps, which is exactly the kind of
      // sustained "layer actively transitioning transform" state that
      // degrades text/icon rendering across the whole shared canvas
      // layer while it's in flight (this is the same family of bug as
      // the preserve-3d blur fixed above, just triggered by continuous
      // wheel events instead of a persistent 3D layer). So: transitions
      // stay off for as long as wheel events keep arriving, and only get
      // handed back once the gesture actually settles (no wheel event
      // for wheelSettleMs), via the same debounce shape as endPan -- a
      // real gesture never leaves a 200ms gap between ticks, so this
      // doesn't clip a slow, deliberate scroll either.
      //
      // Each tick's own jump size is scaled by that tick's deltaY
      // (exponentially, so it composes the way repeated multiplication
      // should) rather than a fixed +/-0.12 regardless of how small the
      // tick was -- a trackpad's ticks vary a lot in size, and a fixed
      // step made a gentle scroll jump exactly as far as an aggressive
      // one.
      //
      // A later attempt tried to smooth this further with a
      // requestAnimationFrame loop that eased the applied zoom toward a
      // target across several frames -- turned out to reintroduce
      // blur, DURING the zoom specifically, and was reverted. That's a
      // different mechanism than the other fixes on this page: it's
      // not promote/demote layer churn from an unrelated property, it's
      // the ordinary GPU-texture-resampling softness every browser
      // shows while a raster layer's transform:scale is actively,
      // continuously changing (crisp again the instant it's still) --
      // and a monotonic per-frame ramp toward a target for 150-250ms
      // running via requestAnimationFrame is *exactly* the shape of
      // change Chrome's compositor treats as a live animation worth
      // trading raster fidelity for, will-change or no. Applying each
      // tick instantly and irregularly, tied to real (never perfectly
      // steady) input events, doesn't read as a continuous animation
      // the same way -- each jump fully settles before the next one
      // arrives, so there's no sustained "actively transforming" window
      // for the compositor to soften. Getting BOTH a silky continuous
      // ramp AND zero softness-while-moving isn't achievable this way
      // on raster/DOM content -- it'd need the canvas to stop scaling a
      // rasterized layer altogether (e.g. recompute each node's actual
      // px layout every frame instead of one CSS transform:scale on the
      // shared ancestor), which is a much bigger rendering change than
      // this bug-fix thread should make without dedicated testing.
      var wheelZoomSensitivity = 0.0013;
      var wheelSettleTimer = null;
      var wheelSettleMs = 200;
      canvasEl.addEventListener('wheel', function (e) {
        // A wheel event over the popover -- most commonly scrolling
        // through a long NPC/item/quest search-suggestions list (see
        // .mm-suggestions' own overflow-y: auto) -- was never excluded
        // here, so it bubbled straight up to this canvas-wide listener
        // same as a wheel event anywhere else on the canvas: preventing
        // the dropdown's own native scroll AND zooming the whole
        // mindmap out from under it instead. That's what the reported
        // "blurry when searching" actually was -- not a new rendering
        // bug, just this handler hijacking the scroll and triggering
        // the exact same "soft while actively zooming, crisp once
        // still" behavior described above, while the player was trying
        // to scroll a dropdown and had no reason to expect the canvas
        // to be zooming at all. Bailing out here (and deliberately NOT
        // calling preventDefault in that case) hands the event back to
        // the browser's own default handling, which is exactly "scroll
        // whatever's actually scrollable under the cursor" -- the
        // suggestions list or the note textarea, same as any other
        // scrollable element on the page.
        // The note textarea and the node's flipped-over back face are
        // BOTH deliberately non-scrollable now (overflow: hidden -- see
        // mindmaps.css, added to guarantee no scrollbar can ever appear
        // there and re-trigger the .mm-world compositing-layer blur bug).
        // Because neither one is a genuine overflow:auto/scroll element
        // any more, the browser doesn't treat a wheel event over them as
        // "targeting something locally scrollable" the way it did before
        // this change -- so the old "bail out and hand this off to
        // whatever's natively scrollable under the cursor" reasoning
        // below no longer applies to these two elements specifically:
        // there's nothing under the cursor for the browser to hand it
        // off TO any more, and the whole wheel delta was observed
        // leaking straight through to the page's own scroll instead
        // (worse than the old overflow:auto behavior, which at least
        // consumed the gesture locally up to its own content first).
        // Since nothing in either element should ever need to scroll
        // again, just swallow the event here: no canvas zoom (a wheel
        // over a note shouldn't zoom the whole mindmap either) and no
        // page scroll.
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
      // Global rather than scoped to the canvas/nodes-layer the way
      // the label-editing Escape handler further down is -- backing
      // out of filling the browser window should work no matter what
      // (if anything) happens to be focused at the time, the same way
      // Escape closing any other full-viewport overlay would.
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && MM.fullscreen) setFullscreen(false);
      });

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
        // Only worth queuing a focus at all when Edit Mode is on AND
        // the node is one of the free-text colors (gray/white) -- a
        // trackable node's label is derived from its goal, not typed,
        // so there's nothing for a focus to land in there. Which
        // element actually gets focused differs by color (see
        // renderCanvas's post-render focus effect): white's label is
        // still contenteditable right on the canvas, but gray renames
        // through a text box in its own popover instead now, so this
        // same MM.focusNodeId queue just resolves to a different
        // target for it.
        var mmForFocus = activeMindmap();
        var nodeForFocus = mmForFocus && id ? mmForFocus.nodes.find(function (n) { return n.id === id; }) : null;
        var focusGoalType = nodeForFocus ? GOAL_TYPE_BY_COLOR[nodeForFocus.color] : null;
        var focusIsFreeText = (focusGoalType === 'manual' || !focusGoalType);
        MM.focusNodeId = (MM.editMode && id && focusIsFreeText) ? id : null;
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
        // Edge buttons, the node popover (color swatches, or the "add
        // shared child" button), the gray manual-complete checkbox
        // (see renderNodeLabelHtml), and the note-flip toggle (see
        // renderCanvas) all handle themselves (via the click delegation
        // below), whether or not Edit Mode is on -- only a plain click
        // on the node's own body/label is gated on Edit Mode below.
        if (e.target.closest('.mm-edge-btn') || e.target.closest('[data-role="popover"]') || e.target.closest('[data-role="manual-toggle"]') || e.target.closest('[data-role="note-toggle"]')) return;
        // A node isn't clickable at all outside Edit Mode -- see
        // MM.editMode's own comment. The one thing that still worked
        // by clicking a node while just viewing (ticking a gray goal
        // complete) now lives on the node itself as that checkbox
        // instead (excluded above, before this check, so it never
        // triggers the glow below), so there's nothing left for a
        // plain click to do here until Edit Mode is on -- glow the
        // Edit Mode button a couple of times instead, as a nudge
        // toward the control that would actually let this click do
        // something.
        if (!MM.editMode) { glowEditModeButton(); return; }
        // Shift-click multi-select only means anything in Edit Mode
        // (its one use is "Add shared child" -- see
        // addSharedChildSelected).
        if (e.shiftKey) { extendMultiSelect(el.getAttribute('data-node-id')); return; }
        selectNode(el.getAttribute('data-node-id'));
      });

      // A second delegation, on 'click' rather than 'pointerdown' --
      // stopPropagation() above only stops the pointerdown from
      // reaching the canvas's own pan-start handler, it doesn't
      // suppress the click event the browser fires afterward, so a
      // button's own click still arrives here normally.
      document.getElementById('mmNodesLayer').addEventListener('click', async function (e) {
        // See pendingLabelCommit's comment above -- if this same click
        // just blurred a still-editing label on its way in (via the
        // pointerdown delegation's commitActiveLabelIfEditing call),
        // let that text-commit's own request+render fully finish
        // before this click's own action fires its own request.
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
        // A goal search field's suggestion click used to be handled
        // right here, but that dropdown now lives outside #mmNodesLayer
        // entirely (see getFloatingSuggestionsEl's own comment) and has
        // its own click listener alongside it instead -- nothing left
        // for this delegation to do for it.
        // A segmented toggle option (see renderSegmentedToggleHtml) --
        // the skill goal's level/experience choice, the diary goal's
        // tier choice. Marks the clicked option active and copies its
        // value into the hidden field right after the group (read
        // generically by goal-save below, same as any other
        // [data-goal-field] element).
        var segBtn = e.target.closest('.mm-segment-btn');
        if (segBtn) {
          var segGroup = segBtn.closest('[data-role="segment-group"]');
          if (!segGroup) return;
          segGroup.querySelectorAll('.mm-segment-btn').forEach(function (b) { b.classList.toggle('active', b === segBtn); });
          var segHidden = segGroup.nextElementSibling;
          if (segHidden && segHidden.matches('input[type="hidden"]')) segHidden.value = segBtn.getAttribute('data-segment-value');
          showGoalSaveError(null);
          // The skill target's valid range (AND its placeholder --
          // "Target level" vs. "Target experience") depends on which
          // metric is picked -- re-check/re-label it immediately
          // against whatever's already typed so switching metrics
          // updates both right away rather than waiting for the next
          // keystroke in the target field. Also carries whatever
          // number's already in there across the switch (5,750 xp
          // becomes level 22, and back again) via
          // xpForLevel/levelForXp, rather than leaving a now-wrong-unit
          // number sitting in the box for the player to redo by hand.
          if (segGroup.getAttribute('data-segment-field') === 'metric') {
            var fieldsWrapForMetric = segGroup.closest('[data-role="goal-fields"]');
            var targetForMetric = fieldsWrapForMetric && fieldsWrapForMetric.querySelector('[data-goal-field="target"]');
            if (targetForMetric) {
              var newMetric = segBtn.getAttribute('data-segment-value');
              var rawTargetForMetric = targetForMetric.value.trim();
              if (rawTargetForMetric !== '') {
                // The box is still showing the OLD metric's value here
                // (newMetric is what it's switching TO) -- it may have
                // a "150k"-style shorthand or thousands-separator
                // commas in it either way (see parseMoneySuffix and
                // filterNumericSuffixInput) that need resolving before
                // it can be converted to a level.
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
        // The gray-node manual-complete checkbox -- lives right on the
        // node itself now (see renderNodeLabelHtml), not behind a
        // popover, so it works on ANY gray node with text, whether or
        // not it's selected and whether or not Edit Mode is on (see
        // MM.editMode's own comment). Reads the CLICKED node (its own
        // ancestor .mm-node, not necessarily the selected one) fresh
        // off the mindmap's current data, so double-clicking it
        // quickly toggles back and forth correctly rather than sending
        // the same value twice.
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
        // The note-flip button (see renderCanvas) -- purely a local
        // view toggle (MM.flippedNodeIds), no request, same "works on
        // ANY node this way" reasoning as the manual-complete checkbox
        // just above, EXCEPT while Edit Mode is on: the button stays
        // visible there now (see .mm-node-note-toggle's own comment in
        // mindmaps.css for why it used to be hidden instead), but is
        // deliberately inert for that whole duration -- pointer-events:
        // none in that same CSS rule normally keeps a click from ever
        // reaching here at all, this MM.editMode check is just the
        // belt-and-suspenders backstop for a click that somehow still
        // lands on the button anyway. Reads the CLICKED node's id
        // straight off its ancestor .mm-node rather than assuming it's
        // the selected one, for the same double-click-doesn't-desync
        // reason that checkbox does. The actual squish-and-reveal
        // animation lives in flipNodeNote below.
        var noteToggleEl = e.target.closest('[data-role="note-toggle"]');
        if (noteToggleEl) {
          if (MM.editMode) return;
          var noteToggleNodeEl = noteToggleEl.closest('.mm-node');
          var noteToggleNodeId = noteToggleNodeEl && noteToggleNodeEl.getAttribute('data-node-id');
          if (noteToggleNodeId) flipNodeNote(noteToggleNodeId);
          return;
        }
        // A trackable goal's criteria form (kc/item/gp/skill/quest/
        // diary -- see renderGoalFieldsHtml) -- Edit Mode only, since
        // this is only ever rendered there in the first place, but the
        // save button existing at all already implies that. The Save
        // button itself now sits in the popover's own actions row,
        // alongside Delete, rather than inside .mm-goal-fields (see
        // renderNodePopoverHtml) -- so this looks the fields wrapper up
        // via the shared popover ancestor instead of e.target's own
        // closest ancestor.
        if (e.target.closest('[data-role="goal-save"]')) {
          var popoverForSave = e.target.closest('[data-role="popover"]');
          var fieldsWrap = popoverForSave && popoverForSave.querySelector('[data-role="goal-fields"]');
          if (!fieldsWrap) return;
          // The note field (see renderNoteFieldHtml) sits in the
          // popover but OUTSIDE .mm-goal-fields (it's the same box for
          // every node type, not one of a particular type's own
          // criteria), so it's read off popoverForSave directly rather
          // than fieldsWrap.
          var noteInputForSave = popoverForSave && popoverForSave.querySelector('[data-role="node-note-input"]');
          var noteValForSave = noteInputForSave ? noteInputForSave.value.trim() : '';
          // A gray (manual) node's Save button commits its NAME, not a
          // goal -- see renderGoalFieldsHtml's "manual" branch and
          // saveSelectedNodeText below. A manual node MUST have text to
          // be saved -- unlike every other type, it has no goal
          // criteria of its own to fall back on, so a blank one is
          // just an empty box with a checkbox next to it, not a real
          // goal -- so a blank attempt is refused outright (a plain
          // red border on the field, same site-wide standard as every
          // other required field -- see validateNodeText's own comment
          // for the live-typing side of this) rather than silently
          // doing anything with it. Unchanged from what's already
          // saved still just closes the popover without a request,
          // same "nothing worth sending" guard commitNodeTextFromLabel
          // used to apply for the old inline-editable version of this
          // same rename.
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
          // The kc goal's own sinceDate (see renderGoalFieldsHtml's kc
          // branch) is the only masked-text date field in this form --
          // same "typed digits, not a native picker" field the Loot
          // Tracker's custom range uses (see DATE_MASK et al above),
          // so it gets the same block-and-flag treatment
          // applyCustomRange gives THOSE fields on Apply: a value with
          // at least one digit typed that still isn't a real calendar
          // date refuses the save and turns the field's border red,
          // rather than letting a half-typed "2026-02-3_" reach the
          // server as-is. A still-blank field (nothing typed, or every
          // digit backspaced back out -- see applyDateMask's own
          // comment) isn't an error here, same as every other optional
          // field in this form -- it's just left out of `goal` by the
          // generic collection loop below like any other blank field.
          var sinceDateInput = fieldsWrap.querySelector('[data-goal-field="sinceDate"]');
          if (sinceDateInput) {
            var sinceDateVal = sinceDateInput.value.trim();
            if (sinceDateVal && !isValidIsoDate(sinceDateVal)) {
              sinceDateInput.classList.add('invalid');
              return;
            }
          }
          // Every other required/range rule this goal type's fields
          // need (see validateGoalFieldsForSave and the two tables
          // above it) -- checked client-side, on the spot, before ever
          // building a request, so an incomplete goal never round-trips
          // to the server just to bounce back as a showGoalSaveError
          // message (still there afterward as a fallback for anything
          // this doesn't catch).
          var typeForSave = GOAL_TYPE_BY_COLOR[nodeForSave.color];
          if (!validateGoalFieldsForSave(fieldsWrap, typeForSave)) return;
          var goal = {};
          fieldsWrap.querySelectorAll('[data-goal-field]').forEach(function (input) {
            var val = (input.value || '').trim();
            var field = input.getAttribute('data-goal-field');
            // Every plain numeric-target field -- kc's targetCount,
            // item's targetQty, gp's targetGp, and the skill target
            // (either metric -- see parseMoneySuffix's own comment for
            // why LVL doesn't need to be excluded) -- accepts the
            // K/M/B shorthand and comma separators (see
            // parseMoneySuffix); everything else is sent as typed.
            var isNumericTargetField = field === 'targetGp' || field === 'targetCount' || field === 'targetQty' || field === 'target';
            if (isNumericTargetField) val = parseMoneySuffix(val);
            if (val !== '') goal[field] = val;
          });
          // The Save button (unlike the manual-complete toggle, which
          // also funnels through saveSelectedNodeGoal) closes the
          // popover on a successful save -- see that function's own
          // comment. The note rides along on this same request (see
          // SetMindMapNodeGoalRequest's own docstring in
          // app/schemas.py) rather than a separate one, always -- goal
          // fields themselves aren't diffed against what's already
          // saved either (see the loop just above), so there's no
          // existing "only send what changed" behavior here for the
          // note to break by joining it.
          saveSelectedNodeGoal(goal, noteValForSave, true);
        }
      });

      // Committing an in-node text edit fires on focusout (bubbles,
      // unlike blur) rather than the pointerdown/click delegation
      // above, since it needs to run whenever the label loses focus
      // for ANY reason (Enter/Escape below, clicking elsewhere,
      // Tab...), not just on a click.
      document.getElementById('mmNodesLayer').addEventListener('focusout', function (e) {
        var label = e.target.closest('[data-role="label"]');
        if (label) commitNodeTextFromLabel(label);
        // A goal search field losing focus closes its suggestions --
        // delayed slightly rather than done immediately, since a click
        // on a suggestion itself (see getFloatingSuggestionsEl's own
        // click listener) blurs this same input first; the delay gives
        // that click time to read the floating box before this empties
        // it out from under it. Guarded by activeSearchInput still
        // being THIS input specifically -- the floating box is shared
        // across every search field now (see getFloatingSuggestionsEl's
        // own comment), so if the player blurred this one and focused a
        // different search field within the same 150ms, that other
        // field has already taken over the box by the time this timeout
        // runs, and hiding it here would wrongly yank its dropdown away
        // mid-search.
        var searchInput = e.target.closest('.mm-search-input');
        if (searchInput) {
          setTimeout(function () {
            if (activeSearchInput === searchInput) hideFloatingSuggestions();
          }, 150);
        }
      });
      // Debounced live search (goal search fields -- see
      // renderSearchFieldHtml) and live inline range validation (the
      // skill goal's target field -- see validateSkillTarget), both
      // driven off the same delegated 'input' listener since both are
      // "react to every keystroke, without a full render()" behaviors
      // that would otherwise wipe out whatever's mid-typing in every
      // other field of the same form. Keyed by a WeakMap rather than a
      // single shared timer, since a player could plausibly have more
      // than one search field in view (e.g. switching goal types
      // quickly) -- each input gets its own independent debounce.
      var searchDebounceTimers = new WeakMap();
      document.getElementById('mmNodesLayer').addEventListener('input', function (e) {
        // Any edit inside the goal-criteria form makes whatever
        // goal-save-error is currently showing stale -- same "clear it
        // the moment there's something worth trying again" treatment
        // validateNodeText already gives the manual node's own error,
        // just for the trackable-type one instead (see
        // showGoalSaveError/saveNodeGoal).
        if (e.target.closest('[data-role="goal-fields"]')) showGoalSaveError(null);
        // Site-wide standard: clear a field's own red border the
        // moment there's something worth trying again in it, on every
        // keystroke -- same idea as showGoalSaveError(null) just
        // above, just per-field instead of for the whole popover.
        // Covers every plain/search field (data-goal-field) and a
        // local-search field's own visible input (data-goal-field-
        // target, e.g. skill/area -- see renderLocalSearchFieldHtml)
        // in one place, since validateGoalFieldsForSave is what
        // actually adds .invalid to any of them.
        var goalFieldInput = e.target.closest('[data-goal-field], [data-goal-field-target]');
        if (goalFieldInput) goalFieldInput.classList.remove('invalid');
        var searchInput = e.target.closest('.mm-search-input');
        if (searchInput) {
          clearTimeout(searchDebounceTimers.get(searchInput));
          searchDebounceTimers.set(searchInput, setTimeout(function () { runGoalSearch(searchInput); }, 200));
          return;
        }
        // Every plain numeric-target field (see NUMERIC_SUFFIX_FIELDS_SELECTOR/
        // filterNumericSuffixInput) gets its typed value cleaned up
        // FIRST, before anything downstream (validateSkillTarget right
        // below, in particular) ever reads it -- so a disallowed
        // character never even flashes into the field for one frame
        // before being stripped back out.
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

      function fmtNum(n) { return Number(n).toLocaleString('en-US'); }

      // Lets any plain-numeric goal target (kc's targetCount, item's
      // targetQty, gp's targetGp, skill's target) be typed as a
      // shorthand -- "140k", "2.5m", "1b" -- and resolves it to the
      // plain integer the server actually stores (140000, 2500000,
      // 1000000000); the node itself always displays the resolved
      // number with commas (see goalDisplayText, unchanged), never the
      // shorthand the player typed. Commas are stripped unconditionally
      // first (filterNumericSuffixInput lets a player type them into
      // any of these fields as a thousands separator, purely for
      // readability while typing -- "2,500k" and "2500k" resolve
      // identically), so what's left is either a plain integer or a
      // number+suffix. Anything that isn't a number immediately
      // followed by k/m/b (case-insensitive) after that -- including a
      // plain "140000" -- passes through untouched, so typing the full
      // number still works exactly as before.
      function parseMoneySuffix(raw) {
        var s = (raw || '').trim().replace(/,/g, '');
        var m = /^([0-9]*\.?[0-9]+)\s*([kKmMbB])$/.exec(s);
        if (!m) return s;
        var mult = { k: 1e3, m: 1e6, b: 1e9 }[m[2].toLowerCase()];
        return String(Math.round(parseFloat(m[1]) * mult));
      }

      // Every field parseMoneySuffix ever resolves -- kc's
      // targetCount, item's targetQty, gp's targetGp, skill's target
      // (either metric) -- shares the one filterNumericSuffixInput
      // treatment below, keyed off this same selector.
      var NUMERIC_SUFFIX_FIELDS_SELECTOR =
        '[data-goal-field="targetCount"], [data-goal-field="targetQty"], ' +
        '[data-goal-field="targetGp"], [data-goal-field="target"]';

      // Restricts what actually lands in one of the fields above to
      // exactly the characters that could ever be valid in one: digits,
      // commas (a typing-time thousands separator -- parseMoneySuffix
      // strips them back out before saving/validating), a decimal
      // point (only meaningful together with a k/m/b suffix -- see
      // parseMoneySuffix -- but harmless on its own), and k/m/b
      // themselves (case-insensitive). Anything else typed, pasted, or
      // dropped in -- a letter, a symbol, an emoji -- is silently
      // dropped rather than shown and then complained about, same
      // "just doesn't work" feel a plain <input type="number"> already
      // gives a stray letter, just extended to cover the K/M/B
      // shorthand these fields ALSO need to accept, which a real
      // number input could never be made to allow (hence these being
      // type="text" inputmode="decimal" rather than type="number" --
      // see renderGoalFieldsHtml). Called from the shared delegated
      // 'input' listener below, so it runs on every keystroke (and on
      // a paste/drop, which fires 'input' too) before anything
      // downstream -- validateSkillTarget in particular -- ever reads
      // the field's value.
      var NUMERIC_SUFFIX_DISALLOWED_RE = /[^0-9,.kKmMbB]/g;

      function filterNumericSuffixInput(input) {
        var cleaned = input.value.replace(NUMERIC_SUFFIX_DISALLOWED_RE, '');
        if (cleaned === input.value) return;
        // Keeps the caret sitting after the same VALID characters it
        // was after before the strip, rather than letting the browser's
        // default post-assignment behavior jump it to the end -- counts
        // how many of the characters before the old cursor position
        // survive the same filter, and that count is exactly where the
        // cursor belongs in the cleaned-up value too.
        var cursor = input.selectionStart;
        var keptBeforeCursor = input.value.slice(0, cursor).replace(NUMERIC_SUFFIX_DISALLOWED_RE, '').length;
        input.value = cleaned;
        input.setSelectionRange(keptBeforeCursor, keptBeforeCursor);
      }

      // The kc goal's optional sinceDate field masks itself exactly
      // the way the Loot Tracker page's own "custom" range fields do
      // (see DATE_MASK/digitsOnly/applyDateMask/isValidIsoDate in
      // render_loot_tracker's own script -- ported here rather than
      // shared, since each page's script is its own self-contained
      // block with no shared module between them) -- a plain text
      // field the player types digits into, auto-dashed into
      // 'YYYY-MM-DD' as they go, rather than a native <input
      // type="date">'s own calendar popup. Kept as its own copy
      // instead of factored out because the two pages already don't
      // share any code today, and a real shared module is a bigger
      // change than this one field needs.
      var DATE_MASK = 'dddd-dd-dd';

      function digitsOnly(s) {
        return (s || '').replace(/\D/g, '').slice(0, 8);
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

      // Unlike the Loot Tracker's own version of this field (always
      // showing a "____-__-__" skeleton, since its start/end fields
      // are never optional), this one starts and can return to a
      // genuinely empty value whenever no digits are typed -- so a
      // player who never touches it, or clears it back out, ends up
      // with a plain blank field the shared [data-goal-field]
      // save-collection loop already treats as "nothing to save" like
      // any other empty field, no field-specific carve-out needed
      // there for it.
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
        var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || '');
        if (!m) return false;
        var year = parseInt(m[1], 10), month = parseInt(m[2], 10), day = parseInt(m[3], 10);
        if (month < 1 || month > 12) return false;
        var daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
        return day >= 1 && day <= daysInMonth;
      }

      // ---- Floating goal-search suggestions dropdown --------------------
      // The KC/ITEM/QUEST goal search fields' results dropdown used to be
      // rendered inline as a normal child of each field's own
      // .mm-search-wrap (see renderSearchFieldHtml's git history), which
      // put it inside .mm-world along with everything else on the canvas.
      // That's what caused the "blur while searching" bug several rounds
      // of this file's history tried to fix from the inside: a scrollable
      // overflow:auto region with real overflowing content -- exactly
      // what this dropdown is whenever a search returns enough results to
      // need its own scrollbar -- gets promoted to its own GPU
      // compositing layer by the browser just for being a scroller ready
      // to scroll smoothly, not only while actively being dragged in, and
      // that promotion forces .mm-world's shared layer to re-rasterize
      // around it. overscroll-behavior: contain (still applied below) was
      // never the problem; `contain: paint` was tried next and made
      // things WORSE, not better (see mindmaps.css's own comment on
      // .mm-suggestions and the git log for the full account) -- it
      // appears to have given the browser license to keep the region
      // composited permanently instead of only while scrolling, the same
      // raster-scale-mismatch failure will-change hit twice before,
      // elsewhere in this file's history.
      //
      // This drops that whole approach and moves the dropdown OUTSIDE
      // .mm-world's subtree entirely instead of trying to contain the
      // side effects of it living inside there: a single shared element
      // appended straight to <body>, `position: fixed`, repositioned via
      // getBoundingClientRect() on whichever search input is currently
      // focused. Its own layer promotion can no longer force a repaint of
      // an ancestor it no longer has. One shared element rather than one
      // per field, since only one popover -- and so only one search field
      // -- can ever be focused at a time; positionFloatingSuggestions is
      // called from applyTransform (every pan/zoom, the one choke point
      // all of those funnel through) so it tracks the canvas live instead
      // of drifting off the input the instant the view moves.
      var floatingSuggestionsEl = null;
      var activeSearchInput = null;
      function getFloatingSuggestionsEl() {
        if (!floatingSuggestionsEl) {
          floatingSuggestionsEl = document.createElement('div');
          floatingSuggestionsEl.className = 'mm-suggestions';
          floatingSuggestionsEl.setAttribute('data-role', 'mm-suggestions');
          document.body.appendChild(floatingSuggestionsEl);
          // A goal search field's suggestion -- fills the search box's
          // own input with the picked name and closes the dropdown, but
          // does NOT save on its own; the player still hits the
          // popover's Save button once every field (including a numeric
          // one alongside it) is filled in, same as typing a name in
          // directly. This box lives outside #mmNodesLayer now, so it
          // can't be picked up by that element's own click delegation
          // any more -- it gets this one listener of its own instead,
          // scoped to just this one shared box, kept alive for as long
          // as the page is (never torn down/recreated the way the rest
          // of the popover is on every render).
          floatingSuggestionsEl.addEventListener('click', function (e) {
            var suggestionEl = e.target.closest('.mm-suggestion');
            if (!suggestionEl || !activeSearchInput) return;
            var value = suggestionEl.getAttribute('data-value');
            var label = suggestionEl.getAttribute('data-label');
            // The KC/ITEM/QUEST fields' own persisted value IS the
            // typed/picked name (label === value for those -- see
            // normalizeSearchResults), so this covers them exactly as
            // before. The skill/diary fields (see
            // renderLocalSearchFieldHtml) differ: what's shown/typed
            // (a title-cased skill name, a diary's real in-game name)
            // isn't what's saved (a skill's lowercase key, a diary's
            // area slug) -- hiddenTargetFor finds their companion
            // hidden field and that's what actually gets the real
            // value; this visible input only ever shows the label.
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
      // Syncs the floating box's on-screen position/width to whatever
      // activeSearchInput's own getBoundingClientRect() reports right
      // now -- which already reflects .mm-world's current pan/zoom
      // transform (getBoundingClientRect always resolves to real,
      // post-transform viewport pixels), so this never needs to read
      // MM.pan/MM.zoom itself. A safe no-op whenever there's no open
      // dropdown to move, so every call site can call this
      // unconditionally rather than checking first.
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

      // The skill/diary search fields' visible input isn't itself the
      // saved field (see renderLocalSearchFieldHtml) -- this finds
      // their companion hidden [data-goal-field] input, off the
      // data-goal-field-target attribute the visible input carries.
      // null for the KC/ITEM/QUEST fields, which have no such
      // attribute (they ARE their own [data-goal-field] directly).
      function hiddenTargetFor(input) {
        var targetFieldName = input.getAttribute('data-goal-field-target');
        if (!targetFieldName) return null;
        var wrap = input.closest('.mm-search-wrap');
        return wrap && wrap.querySelector('[data-goal-field="' + targetFieldName + '"]');
      }

      // Runs a goal search field's query against whichever endpoint its
      // data-search-kind picks (see GOAL_SEARCH_ENDPOINTS), OR filters
      // LOCAL_SEARCH_POOLS[kind] client-side for the skill/diary fields
      // (nothing to look up server-side there -- see that constant's
      // own comment) -- renders either way into the shared floating
      // suggestions box, called debounced off the 'input' delegation
      // above.
      async function runGoalSearch(input) {
        var query = input.value.trim();
        var hidden = hiddenTargetFor(input);
        if (!query) {
          // An emptied search field means "nothing picked" for the
          // skill/diary fields too, same as it always has for the
          // KC/ITEM/QUEST ones (their own value -- typed directly into
          // the one input they have -- is just as empty).
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
          // Keeps the hidden field in sync with whatever the typed text
          // CURRENTLY resolves to exactly (or clears it otherwise) on
          // every keystroke -- not just on a suggestion click -- so
          // typing a full exact name and hitting Save without ever
          // clicking the dropdown still works, and, just as
          // importantly, so backspacing/editing away from a previously
          // clicked selection can't silently leave the stale old value
          // behind once the visible text no longer says that. An
          // unresolved partial ("Rune") clears it, same as it would if
          // the player had typed unmatched free text into a KC/ITEM/
          // QUEST field and hit Save -- clean_goal in app/mindmaps.py
          // rejects that the same way either way.
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
        // The popover (and this exact input) can be gone by the time
        // this resolves -- the node got deselected, recolored, or the
        // whole canvas re-rendered for some other reason while the
        // request was in flight. Bail rather than writing into a box
        // nobody can see any more. And now that every search field
        // shares ONE floating box instead of each carrying its own (see
        // getFloatingSuggestionsEl's own comment), a slower-to-resolve
        // request from a field the player has since tabbed/clicked away
        // from could otherwise clobber whatever's currently showing for
        // the field they're actually in -- the activeElement check
        // guards against that too.
        if (!document.body.contains(input) || document.activeElement !== input) return;
        activeSearchInput = input;
        renderGoalSuggestions(getFloatingSuggestionsEl(), kind, data ? data.results : []);
      }

      // Normalizes every search kind's raw result shape into one
      // uniform {value, label, icon} row for renderGoalSuggestions:
      // item results are {name, icon, ...} objects (/api/items/search);
      // NPC/quest results are plain name strings (/api/npcs/search,
      // /api/quests/search); skill/diary results are already
      // {value, label, icon} (LOCAL_SEARCH_POOLS). value === label for
      // every kind except skill/diary, where what's typed/shown isn't
      // what's saved (see renderLocalSearchFieldHtml).
      function normalizeSearchResults(kind, raw) {
        if (kind === 'skill' || kind === 'diary') return raw;
        if (kind === 'item') return raw.map(function (r) { return { value: r.name, label: r.name, icon: r.icon }; });
        return raw.map(function (name) { return { value: name, label: name, icon: null }; });
      }

      // Renders one search field's suggestion dropdown.
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
        // Only actually visible (display: block) once 'show' is added
        // just above, but positioning it before or after that makes no
        // difference -- inline left/top/width apply the same either way.
        positionFloatingSuggestions();
      }

      // Live, as-you-type range check for the skill goal's target
      // field -- mirrors MIN_SKILL_LEVEL/MAX_SKILL_LEVEL/MIN_SKILL_XP/
      // MAX_SKILL_XP exactly (the server re-validates against its own
      // copy of these regardless -- see clean_goal in app/mindmaps.py).
      //
      // Site-wide standard: invalid is a red border on the field
      // itself, nothing else. Same showEmptyAsInvalid split as Goal
      // Tracking's validateTargetField (goal-tracking.css's own copy
      // of this same idea) -- quiet while the field's simply not been
      // typed into yet (every live call below, and the metric-toggle
      // switch handler, both omit it), red the moment Save is clicked
      // on an empty one (validateGoalFieldsForSave passes true).
      // Returns whether the field is currently valid either way.
      function validateSkillTarget(input, showEmptyAsInvalid) {
        var fieldsWrap = input.closest('[data-role="goal-fields"]');
        var metricHidden = fieldsWrap && fieldsWrap.querySelector('[data-goal-field="metric"]');
        var metric = (metricHidden && metricHidden.value === 'xp') ? 'xp' : 'level';
        var raw = input.value.trim();
        if (raw === '') { input.classList.toggle('invalid', !!showEmptyAsInvalid); return false; }
        // Resolved through parseMoneySuffix either way -- both to
        // strip a thousands-separator comma (filterNumericSuffixInput
        // lets a player type one into this field regardless of metric)
        // and, in XP mode, to resolve the "140k"/"2.5m"/"1b" shorthand
        // before range-checking, so typing "150k" doesn't flash an
        // out-of-range error while the player's still typing it out in
        // full. LVL never has a REAL use for the k/m/b shorthand (a
        // level suffix makes no sense at OSRS's 1-126 scale), but
        // running it through the same resolver anyway costs nothing --
        // a stray "5k" there resolves to 5000, which the max check
        // below rejects exactly as an out-of-range level should be.
        var n = Number(parseMoneySuffix(raw));
        var min = metric === 'xp' ? MIN_SKILL_XP : MIN_SKILL_LEVEL;
        var max = metric === 'xp' ? MAX_SKILL_XP : MAX_SKILL_LEVEL;
        var ok = Number.isInteger(n) && n >= min && n <= max;
        input.classList.toggle('invalid', !ok);
        return ok;
      }

      // Live "clear the red border as you type" companion to the
      // goal-save click delegation's own blank-text check below --
      // THAT is what actually flags it, only once the player attempts
      // a Save with nothing typed (not the instant a fresh popover
      // opens empty -- nobody's tried to save anything wrong yet at
      // that point, so nothing to flag). This just clears it again the
      // moment there's something in the box worth saving, on every
      // keystroke, same trigger as validateSkillTarget above.
      function validateNodeText(input) {
        if (input.value.trim() !== '') input.classList.remove('invalid');
      }

      // Client-side mirror of clean_goal's own per-type required-field
      // list (app/mindmaps.py) -- metric/tier are deliberately absent
      // from every list below, since renderSegmentedToggleHtml always
      // defaults to its first option, so those two fields are
      // structurally never missing the way a text/search field can be.
      // activityType (kc) is likewise absent -- it's a hidden field
      // that's always "npc" now (see renderGoalFieldsHtml's kc
      // branch), never actually empty either.
      var REQUIRED_GOAL_FIELDS = {
        kc: ['sourceName'],
        item: ['itemName'],
        gp: [],
        skill: ['skill'],
        quest: ['questName'],
        diary: ['area'],
      };
      // Mirrors clean_goal's own numeric-target bounds (app/mindmaps.py)
      // for every goal type EXCEPT skill, whose target bounds depend on
      // the level/xp toggle and are already handled by
      // validateSkillTarget above.
      var NUMERIC_TARGET_FIELD = {
        kc: { field: 'targetCount', min: 1, max: MAX_KC_TARGET },
        item: { field: 'targetQty', min: 1, max: MAX_ITEM_QTY_TARGET },
        gp: { field: 'targetGp', min: 1, max: MAX_GP_TARGET },
      };

      // Finds the element a red border actually belongs on for a given
      // data-goal-field name -- the field itself for a plain or
      // search field, or its visible companion
      // (data-goal-field-target) for a local-search field like
      // skill/area, whose own [data-goal-field] element is a hidden
      // input the player never sees (see renderLocalSearchFieldHtml).
      function visibleGoalFieldEl(fieldsWrap, name) {
        return fieldsWrap.querySelector('[data-goal-field-target="' + name + '"]') ||
          fieldsWrap.querySelector('[data-goal-field="' + name + '"]');
      }

      // Client-side mirror of clean_goal's required+range checks (see
      // the two tables above), run right before the Save button's own
      // [data-goal-field] collection loop in the goal-save click
      // delegation -- catches a missing or out-of-range field with a
      // plain red border on the spot, rather than letting an
      // incomplete goal round-trip to the server just to bounce back
      // as a popover-level showGoalSaveError message (still there as a
      // fallback for anything this misses, e.g. a genuinely unexpected
      // server rejection). Toggles .invalid on each field's own
      // visible element along the way -- on for anything missing or
      // out of range, off for anything that's fine -- and returns
      // whether every field this goal type needs is currently valid.
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

      // Shows (or, with a falsy msg, clears) a trackable node's own
      // "you're missing something" error right in its popover -- see
      // saveNodeGoal for where this actually gets called (a rejected
      // save) and renderNodePopoverHtml for where the element itself
      // lives. Used to be the page's own top error banner (#mmError,
      // above the whole canvas -- see showError), same as any other
      // failed request; moved down here instead since it's a form
      // validation message about THIS popover specifically ("Set a
      // target count.", "Pick an item.", ...), not a page-level
      // failure, and the banner sits off past the top of the viewport
      // on a canvas that usually fills the whole screen -- easy to
      // miss entirely with the popover still open right in front of
      // the player. No popover currently open (or a popover with no
      // goal-save-error slot in it, e.g. the manual type, which never
      // hits this path -- see saveNodeGoal's own comment) is a no-op,
      // not an error.
      function showGoalSaveError(msg) {
        var errEl = document.querySelector('[data-role="popover"] [data-role="goal-save-error"]');
        if (!errEl) return;
        if (!msg) { errEl.textContent = ''; errEl.classList.remove('show'); return; }
        errEl.textContent = msg;
        errEl.classList.add('show');
      }

      // A trackable node's own text is no longer something the player
      // types -- it's derived straight from its goal criteria (see
      // clean_goal in app/mindmaps.py for the fields each type
      // stores), formatted per the exact shape asked for:
      //   kc:    "<count> <activity> kc"
      //   item:  "x<qty> <item>"
      //   gp:    "<amount> gp"
      //   skill: "<xp> <skill> xp"  or  "lvl <level> <skill>"
      //   quest: "<quest name>"
      //   diary: "<diary area> <tier>"
      // Only ever called for the 6 trackable colors -- gray (manual)
      // and white (the root) keep the player's own free-typed
      // node.text instead (see renderCanvas, which branches on this
      // before ever calling here). A goal that isn't fully filled in
      // yet (a freshly recolored node -- see default_goal in
      // app/mindmaps.py) has nothing to format, so it falls back to a
      // plain placeholder naming what still needs choosing.
      function goalDisplayText(node) {
        var type = GOAL_TYPE_BY_COLOR[node.color];
        var goal = node.goal || {};
        if (type === 'kc') {
          if (!goal.targetCount || !goal.sourceName) return 'Set KC goal';
          return fmtNum(goal.targetCount) + ' ' + goal.sourceName + ' kc';
        }
        if (type === 'item') {
          if (!goal.targetQty || !goal.itemName) return 'Set item goal';
          // The leading "x" here is intentionally lowercase in the
          // source string -- see renderNodeLabelHtml, which is what
          // actually keeps it lowercase on screen despite .mm-node's
          // own text-transform: uppercase (everything else in this
          // string still renders upper via that inherited rule).
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

      // .mm-node's own text-transform: uppercase (see that rule's own
      // comment in mindmaps.css) shouts an item goal's leading "x" into
      // "X" along with everything else in the label -- this wraps just
      // that character in a span forced back to lowercase (mirroring
      // the .mm-segment-btn/.mm-suggestion text-transform overrides
      // elsewhere in this file), leaving the rest of the label, and
      // every other goal type's label, uppercased exactly as before.
      function renderNodeLabelHtml(goalType, text) {
        if (goalType === 'item') {
          var m = /^x(\d.*)$/.exec(text);
          if (m) return '<span class="mm-node-x-lower">x</span>' + esc(m[1]);
        }
        return esc(text);
      }

      function renderCanvas(mm) {
        var layout = computeLayout(mm.nodes);
        MM.lastLayout = layout;

        var world = document.getElementById('mmWorld');
        // Width gets no extra padding -- a popover is only ever 250px
        // wide (.mm-node-popover-wide) against a 160px node, centered,
        // so it overhangs each side by 45px, comfortably inside
        // MARGIN's existing 60px already baked into worldWidth. Height
        // is the real problem: see POPOVER_HEIGHT_PAD's own comment.
        // This padding applies unconditionally, on every render, not
        // just while a popover happens to be open -- the moment that
        // actually needs it most is the CLOSING one, where the popover
        // has already been dropped from mm.nodes' own render pass by
        // the time this runs (MM.selectedNodeId is already null), so
        // there's no "a popover is open right now" flag left to key
        // off here. Keeping #mmWorld's own box permanently tall enough
        // sidesteps needing to track that at all: it just never gets
        // small enough for a popover, on ANY node, to paint outside it
        // in the first place, open OR just-closed.
        world.style.width = layout.worldWidth + 'px';
        world.style.height = (layout.worldHeight + POPOVER_HEIGHT_PAD) + 'px';

        var nodesLayer = document.getElementById('mmNodesLayer');
        // Nodes aren't clickable at all outside Edit Mode (see the
        // pointerdown delegation's own comment) -- this swaps the
        // whole layer's cursor from "pointer" to plain "default" to
        // match, so a node doesn't visually invite a click it won't
        // do anything with. See .mm-view-mode's own rule in
        // mindmaps.css.
        nodesLayer.classList.toggle('mm-view-mode', !MM.editMode);

        nodesLayer.innerHTML = mm.nodes.map(function (n) {
          var pos = layout.positions[n.id];
          // Every selected node (whether it's the only one, or one of
          // several shift-added to it) gets the exact same brighten
          // treatment -- there's no separate "multi-select" visual mode
          // otherwise. Selection itself still works the same outside
          // Edit Mode (a click still opens the popover -- e.g. the gray
          // "Mark complete" toggle -- so isSelected/isAnchor stay as
          // they are), but the visual highlight is Edit-Mode-only: a
          // node that just isn't editable right now shouldn't look
          // "pressed" the way an actual clickable control would.
          var isSelected = MM.multiSelectIds.has(n.id);
          var isAnchor = n.id === MM.selectedNodeId;
          var isRoot = n.parentId === null;
          var selectedCls = (isSelected && MM.editMode) ? ' selected' : '';
          // Filled solid once the goal's actually met (see
          // evaluate_completion in app/mindmaps.py -- computed fresh
          // server-side on every read, never something this script
          // derives itself), outlined otherwise -- see the
          // .mm-node-<color>.completed rules in mindmaps.css.
          var completedCls = n.completed ? ' completed' : '';
          // Only gray (manual) and white (the root) ever carry a
          // free-typed label anymore -- every trackable color's text
          // is derived from its own goal criteria instead (see
          // goalDisplayText), so there's nothing left for the player
          // to type into those.
          var goalType = GOAL_TYPE_BY_COLOR[n.color];
          var isFreeText = (goalType === 'manual' || !goalType);
          // But only the root (white, goalType null) is still edited
          // INLINE, directly on the canvas -- a gray node renames
          // through a text box in its own popover instead now (see
          // renderGoalFieldsHtml's "manual" branch and the goal-save
          // click delegation's own manual handling below), so a gray
          // label never becomes contenteditable, and never carries
          // data-role="label" either (nothing needs to find it there
          // any more -- see the post-render focus effect's fallback to
          // [data-role="node-text-input"] for how a brand new gray
          // node still gets typed into immediately). Combined with the
          // same "only the sole selected node, only in Edit Mode"
          // gating as before.
          var isInlineEditable = !goalType;
          var editableAttr = (MM.editMode && isInlineEditable && isSelected && MM.multiSelectIds.size === 1) ? ' contenteditable="true" spellcheck="false"' : '';
          var displayText = isFreeText ? n.text : goalDisplayText(n);
          // A gray node with actual text in it gets a manual-complete
          // checkbox where the icon sits for every other trackable
          // type (see the click delegation's own
          // [data-role="manual-toggle"] handler, which works on ANY
          // gray node this way -- selected or not, in or out of Edit
          // Mode). A brand new gray node with nothing typed into it
          // yet has nothing meaningful to mark complete, so it gets no
          // checkbox (or icon) at all, same as before.
          var showManualCheckbox = goalType === 'manual' && !!(n.text && n.text.trim());
          var manualChecked = !!(n.goal && n.goal.manualComplete);
          var iconSrc = GOAL_TYPE_ICON_BY_COLOR[n.color];
          var hasLeftSlot = !!iconSrc || showManualCheckbox;
          var labelCls = 'mm-node-label' + (hasLeftSlot ? ' mm-node-label-with-icon' : '');
          // data-role="label"/editableAttr move onto the INNER text
          // span (rather than sitting on the same element as the
          // checkbox/icon, like a trackable type's icon always could
          // safely be) only when there's a left slot to keep separate
          // -- a checkbox living INSIDE a contenteditable region would
          // otherwise get swept into "select all the label's text" on
          // focus (see selectNode's own comment) or be at risk of the
          // browser's own text-editing commands mangling it. The plain
          // case (no left slot at all) keeps them on the single outer
          // div exactly as before.
          var labelInner;
          if (hasLeftSlot) {
            var leftSlotHtml = showManualCheckbox
              ? '<input type="checkbox" class="mm-node-checkbox" data-role="manual-toggle" title="Mark complete"' + (manualChecked ? ' checked' : '') + '>'
              : '<img class="mm-node-icon" src="' + iconSrc + '" alt="">';
            // isInlineEditable is always false whenever hasLeftSlot is
            // true from a checkbox (a gray node only ever gets a left
            // slot once it HAS text -- see showManualCheckbox -- and
            // gray is never inline-editable any more), so this only
            // ever actually adds data-role="label"/editableAttr for a
            // tracked-type icon case... which in turn never happens
            // either, since isInlineEditable is root-only and root
            // never has a left slot (see hasLeftSlot's own comment
            // above). Kept as the general rule anyway -- computed the
            // same way as labelAttrs below -- rather than assuming
            // "left slot" and "inline editable" can never coincide by
            // construction.
            var innerLabelAttrs = isInlineEditable ? (' data-role="label"' + editableAttr) : '';
            labelInner = leftSlotHtml + '<span class="mm-node-label-text"' + innerLabelAttrs + '>' + renderNodeLabelHtml(goalType, displayText) + '</span>';
          } else {
            labelInner = esc(displayText);
          }
          // The root is the one node every mindmap always keeps, so it
          // can't get a parent (which would just bury it under a new,
          // equally permanent root) or a sibling (it has no parent to
          // share one under) -- only its "add child" edge button shows.
          // The backend enforces the same rule; this just keeps the
          // dead-end options from ever being offered in the first place.
          // Edge buttons only ever change the tree's structure, so
          // they're Edit-Mode-only too.
          var edgeButtonsHtml = !MM.editMode ? '' :
            (isRoot ? '' : '<button type="button" class="mm-edge-btn mm-edge-top" data-relation="parent" title="Add parent">+</button>') +
            '<button type="button" class="mm-edge-btn mm-edge-bottom" data-relation="child" title="Add child">+</button>' +
            (isRoot ? '' : '<button type="button" class="mm-edge-btn mm-edge-left" data-relation="sibling" data-before="1" title="Add sibling">+</button>') +
            (isRoot ? '' : '<button type="button" class="mm-edge-btn mm-edge-right" data-relation="sibling" data-before="0" title="Add sibling">+</button>');
          // The popover below the anchor node is the color swatches +
          // goal-criteria form + delete when it's the only thing
          // selected (see renderNodePopoverHtml -- also how the
          // outside-Edit-Mode gray "Mark complete" toggle shows up), or
          // the "add shared child" button once a second node's been
          // shift-added (Edit-Mode-only -- see the pointerdown
          // delegation above) -- see MM.selectedNodeId's own comment
          // for why it's always the anchor's popover, never every
          // selected node's own.
          var popoverHtml = '';
          if (isAnchor && MM.multiSelectIds.size === 1) popoverHtml = renderNodePopoverHtml(n);
          else if (isAnchor && MM.multiSelectIds.size >= 2) popoverHtml = renderSharedChildPopoverHtml();
          // data-role="label"/editableAttr already moved onto the inner
          // text span above when hasLeftSlot -- this outer div only
          // still carries them itself in the plain (no icon/checkbox)
          // case, same as before, and even then only for the root (see
          // isInlineEditable above) -- an empty, not-yet-typed-into
          // gray node has no left slot either (no checkbox until it
          // has text -- see showManualCheckbox), but isInlineEditable
          // is false for it too, so it renders with no data-role at
          // all, nothing on the canvas to click into.
          var labelAttrs = hasLeftSlot ? '' : (isInlineEditable ? (' data-role="label"' + editableAttr) : '');
          // The optional note flip (see renderNoteFieldHtml for where
          // it's written) -- a node with no note gets neither the
          // toggle button nor a back face at all, so it costs nothing
          // in the common case. hasNote also self-heals MM.flippedNodeIds
          // the moment a note's cleared out from under an already-
          // flipped node, rather than leaving a stale id that would
          // silently show the wrong face again if a note's ever typed
          // back in later.
          var hasNote = !!(n.note && n.note.trim());
          if (!hasNote) MM.flippedNodeIds.delete(n.id);
          var isFlipped = hasNote && MM.flippedNodeIds.has(n.id);
          var noteToggleHtml = !hasNote ? '' :
            '<button type="button" class="mm-node-note-toggle" data-role="note-toggle" title="' +
            (isFlipped ? 'Back to node' : 'View note') + '">' +
            (isFlipped ? NOTE_ICON_ARROW_SVG : NOTE_ICON_PAPER_SVG) + '</button>';
          // The front face is exactly what a non-flippable node has
          // always rendered (labelCls/labelAttrs/labelInner, untouched)
          // -- just wrapped in its own face div now instead of sitting
          // directly in .mm-node, so flipNodeNote has a single element
          // (.mm-node-flip-inner) to animate. Only EVER the currently-
          // visible face is in the DOM -- not both stacked and rotated
          // in 3D, which is how this first shipped -- flipNodeNote
          // swaps which one gets rendered here at the midpoint of its
          // own squish animation, so the swap itself lands while the
          // node's scaled down to a sliver and isn't visible either
          // way. A node with no note never gets a flip-inner at all --
          // there's nothing to flip TO -- so it renders its label
          // exactly as before, no extra wrapper markup for the common
          // case.
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
        // so it's the one that sticks. Always scheduled now, not just
        // when a focus was queued -- ensurePopoverVisible below needs
        // to check every fresh popover for overflow (a trackable
        // node's swatch/goal-form popover included, not just a free-
        // text one that also wants a focus), and needs the same
        // "after the DOM above has actually landed" timing this does.
        var focusIdForThisRender = MM.focusNodeId;
        MM.focusNodeId = null;
        setTimeout(function () {
          if (focusIdForThisRender) {
            var nodeEl = document.querySelector('.mm-node[data-node-id="' + focusIdForThisRender + '"]');
            if (nodeEl) {
              var label = nodeEl.querySelector('[data-role="label"]');
              if (label) {
                // preventScroll -- see ensurePopoverVisible's own
                // comment: the browser's native scroll-into-view would
                // otherwise fight the deliberate pan below (and, on
                // its own, is exactly what caused the toolbar-left-
                // behind bug that pan replaces).
                label.focus({ preventScroll: true });
                var range = document.createRange();
                range.selectNodeContents(label);
                var sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
              } else {
                // No inline-editable label -- this is a gray (manual)
                // node, whose equivalent "start typing immediately"
                // target is the text box in its own popover instead
                // (see renderGoalFieldsHtml's "manual" branch);
                // selectNode still queues focus the same way for both
                // cases (see its own comment), only the actual target
                // differs.
                var textInput = nodeEl.querySelector('[data-role="node-text-input"]');
                if (textInput) {
                  textInput.focus({ preventScroll: true });
                  textInput.select();
                }
              }
            }
          }
          ensurePopoverVisible();
          // Run after ensurePopoverVisible, not before -- it needs the
          // popover's FINAL post-pan position, and this scroll is a
          // separate, later concern from the preventScroll above (that
          // one is about not fighting the internal canvas pan; this one
          // is about the outer page never getting scrolled at all, since
          // preventScroll suppresses the browser's own native attempt).
          scrollCanvasPopoverIntoView();
        }, 0);

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

      // The selected node's color swatches + per-color goal-criteria
      // form + Save/Delete row, shown as a popover anchored right below
      // the node itself -- replaces the old toolbar's swatch row and
      // +Parent/+Child/+Sibling/Delete buttons (the add-relative ones
      // are now the edge buttons above; delete didn't have anywhere
      // else to go once the toolbar was removed, so it lives here
      // too). All Edit-Mode-only, EXCEPT the gray node's manual
      // "Mark complete" toggle (see renderGoalFieldsHtml), which is
      // also the only thing this popover ever shows OUTSIDE Edit Mode
      // -- see MM.editMode's own comment for why. Shares its outer
      // .mm-node-popover shell/position with renderSharedChildPopoverHtml
      // below -- only one of the two is ever shown for a given node
      // (see renderCanvas), depending on whether it's the sole selected
      // node or the anchor of several.
      //
      // The root node has NOTHING to show here at all, in either mode
      // -- it can't have a goal type (always white, structurally -- see
      // NODE_COLORS' own comment in app/mindmaps.py) and can't be
      // deleted (same rule the backend already enforces), so this
      // bails out before rendering any popover shell for it. Doing
      // that check first (rather than just leaving out the picker/
      // delete button and still wrapping an empty shell) is what keeps
      // selecting the root from showing a visible-but-empty popover box.
      function renderNodePopoverHtml(node) {
        // Nothing renders outside Edit Mode at all -- a node isn't
        // clickable there in the first place (see the pointerdown
        // delegation above), so there's never a selection for a
        // popover to attach to. Ticking a gray goal complete, the one
        // thing this used to still offer while just viewing, is now
        // the checkbox right on the node itself instead (see
        // renderNodeLabelHtml) -- it needs no popover and no
        // selection to work.
        if (node.parentId === null || !MM.editMode) return '';
        var goalType = GOAL_TYPE_BY_COLOR[node.color];
        // Every non-root type gets a Save button alongside Delete now,
        // including manual -- see renderGoalFieldsHtml's "manual"
        // branch, which gives it a name text box in place of a goal
        // form (ticking it COMPLETE is still the checkbox on the node
        // itself, not anything this popover saves -- only its NAME
        // saves here).
        var showSave = !!goalType;
        // Delete before Save (not after) -- same secondary-action-
        // first, primary-action-last ordering the Goal Tracking
        // wizard's own Back/Cancel/Save row uses, so Save reads as the
        // one gold "primary" action sitting rightmost regardless of
        // which page you're on.
        var actionsHtml = '<div class="mm-popover-actions" data-role="popover-actions">' +
          '<button type="button" class="btn-secondary mm-delete-btn mm-color-popover-delete" data-role="delete">Delete</button>' +
          (showSave ? '<button type="button" class="btn-secondary mm-goal-save-btn" data-role="goal-save">SAVE</button>' : '') +
          '</div>';
        // A trackable type's own "you're missing something" error
        // (server-validated -- see saveNodeGoal/showGoalSaveError and
        // clean_goal in app/mindmaps.py for the actual per-field
        // messages) lands here, right above Save/Delete -- the same
        // "in the popover, not the page's top banner" treatment the
        // manual node's own node-text-error already got, and it picks
        // up that same .mm-node ancestor's uppercase styling for free,
        // same as every other label in here.
        return '<div class="mm-node-popover mm-node-popover-wide" data-role="popover">' +
          renderGoalTypePickerHtml(node) +
          renderGoalFieldsHtml(node) +
          renderNoteFieldHtml(node) +
          '<div class="mm-field-error mm-goal-save-error" data-role="goal-save-error"></div>' +
          actionsHtml +
          '</div>';
      }

      // ---- Note two-line cap ---------------------------------------------
      // A node's own note used to allow up to 1000 characters with no line
      // cap, shown in a resizable, scrollable textarea in its popover and a
      // scrollable box on the node's own flipped-over back face
      // (.mm-node-note-text). Either one growing tall enough to need its
      // own scrollbar reintroduces the exact "scrollable region inside
      // .mm-world" mechanism behind the search-dropdown blur bug this
      // file's history spent several rounds chasing (see
      // getFloatingSuggestionsEl's own comment for the full account) --
      // and unlike that dropdown, there's no "move it outside .mm-world"
      // fix available for either of these: the textarea has to live in the
      // popover, right where the player is editing it, and the back face
      // literally IS the node. So instead of moving them out, this removes
      // the possibility of a scrollbar ever appearing on them AT ALL --
      // capping a note to 2 lines end to end, with overflow: hidden on
      // both as a backstop (see mindmaps.css), rather than trying to
      // contain a scrollbar's side effects the way earlier rounds did.
      //
      // RuneScapePlain11 (this whole page's font) is proportional, not
      // monospace, so a fixed character-count cap would either cut short a
      // note that's mostly narrow characters (i, l, .) or still overflow
      // one that's mostly wide ones (M, W, @) -- this measures the ACTUAL
      // rendered height of a candidate value against a hidden mirror
      // element instead of guessing a character budget. The mirror is
      // sized to match .mm-node-note-text/.mm-node-face exactly (font-
      // size 9.5px, line-height 1.35, NODE_WIDTH's own content width --
      // see mindmaps.css, keep the two in sync if either ever changes),
      // the NODE'S OWN BACK FACE, not the (larger, roomier) popover
      // textarea -- the back face is the tighter of the two contexts for
      // the same text, so a note that fits 2 lines there is guaranteed to
      // fit in 2 (or fewer) lines in the bigger textarea too. Clamping
      // against that one canonical fit point, live as the player types (or
      // pastes -- 'input' fires for both), keeps what they see while
      // editing and what the note actually looks like on the card in sync
      // -- there's no second, different truncation point a saved note
      // could still run into later.
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
      // Longest prefix of `value` that still renders at or under
      // NOTE_MAX_LINES lines tall in the mirror above. Binary-searches the
      // cut point rather than measuring one character at a time -- a
      // pasted note can be hundreds of characters, and this keeps that to
      // a handful of measurements instead of hundreds.
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
      // Called off the note textarea's own 'input' event (see the
      // delegated listener above) -- clamps in place and, only when a
      // character actually got cut, parks the caret at the end of what's
      // left. That's exactly right for the overwhelmingly common case
      // (typing/pasting at the end, which is the only place a caret can be
      // when a fresh keystroke is what tipped this over); a paste landing
      // mid-note that pushes the tail past 2 lines is the one case this
      // doesn't handle precisely (the caret ends up at the very end rather
      // than after the pasted text specifically) -- a small, rare
      // imprecision, not a broken one, and not worth the extra
      // bookkeeping this quick a fix calls for.
      function clampNoteInput(textarea) {
        var clamped = clampNoteToLines(textarea.value);
        if (clamped !== textarea.value) {
          textarea.value = clamped;
          textarea.setSelectionRange(clamped.length, clamped.length);
        }
      }

      // The one optional field every non-root node type gets, gray
      // (manual) included, right above the Save/Delete row -- "how I'd
      // like to achieve this," entirely separate from a trackable
      // node's own goal CRITERIA (renderGoalFieldsHtml, just above this
      // in the popover) or a manual node's own name. Saved by the same
      // Save button as everything else in the popover, riding along on
      // whichever request that node type's own fields already send
      // (see the goal-save click delegation, and
      // saveSelectedNodeText/saveSelectedNodeGoal below) rather than a
      // separate request of its own -- one Save click, one request,
      // one undo step, whether or not the note itself actually
      // changed. Shows the current note's text as its own value (not
      // placeholder) via a plain <textarea>, not one of the
      // data-goal-field inputs the generic goal-save loop reads
      // automatically -- it needs its own explicit handling either way
      // (manual saves through the node-PATCH endpoint, every other type
      // through the goal endpoint -- see SetMindMapNodeGoalRequest's own
      // docstring in app/schemas.py for why note rides along there
      // too), so there's nothing to gain from making it LOOK generic. No
      // longer resizable (see mindmaps.css) -- a note is hard-capped to 2
      // lines now (see clampNoteInput above), so there's nothing a resize
      // handle would let the player reach that typing itself doesn't
      // already allow. maxlength here is a generous backstop, not the
      // real cap -- clampNoteInput (wired up via the delegated 'input'
      // listener) is what actually enforces 2 lines, live, character by
      // character; this just matches MAX_NODE_NOTE_LENGTH server-side so
      // an already-long note from before this change can't paste back in
      // unbounded before that live clamp gets a chance to run.
      function renderNoteFieldHtml(node) {
        return '<div class="mm-note-wrap">' +
          '<textarea class="mm-goal-input mm-note-input" data-role="node-note-input" placeholder="Notes (optional)" maxlength="200" rows="2">' +
          esc(node.note || '') + '</textarea>' +
          '</div>';
      }

      // The goal-TYPE picker -- what used to be a row of plain color
      // swatches is now a grid of icon+label buttons, one per goal
      // type (see GOAL_TYPE_PICKER), since the color alone doesn't
      // say what a node actually tracks. Clicking one still just sets
      // the node's `color` (data-color, same click delegation as the
      // old swatches -- see the click handler above), which resets
      // its goal back to blank for the new type (see update_node in
      // app/mindmaps.py) the same way it always has; this is purely a
      // richer way to choose that same color. "White" is deliberately
      // NOT one of the options here -- it's reserved for the root
      // node alone (see NODE_COLORS' own comment in app/mindmaps.py)
      // and the backend silently refuses to apply it to anything
      // else, so there's no point ever offering it as a choice.
      function renderGoalTypePickerHtml(node) {
        var buttons = GOAL_TYPE_PICKER.map(function (opt) {
          var activeCls = (opt.color === node.color) ? ' active' : '';
          var inner = (opt.color === 'gray')
            // MANUAL has no clan-icon equivalent -- it's the "no
            // tracked goal" choice, so its own swatch box carries a
            // red diagonal slash instead of an icon, reading as
            // "reset/remove tracking" the same way a "no" sign would.
            ? '<span class="mm-type-btn-swatch mm-type-btn-swatch-manual"></span>'
            : '<img class="mm-type-btn-icon" src="' + opt.icon + '" alt="">';
          return '<button type="button" class="mm-type-btn' + activeCls + '" data-color="' + opt.color + '" title="' + opt.label + '">' +
            inner + '<span class="mm-type-btn-label">' + opt.label + '</span></button>';
        }).join('');
        return '<div class="mm-type-picker">' + buttons + '</div>';
      }

      // Renders a text input backed by a live search dropdown -- the
      // KC goal's NPC field, the ITEM goal's item field, and the QUEST
      // goal's quest/miniquest field all use this, differing only in
      // which snapshot they search (see GOAL_SEARCH_ENDPOINTS/
      // runGoalSearch). The input itself still just carries
      // `data-goal-field="<fieldName>"` like any other field -- typing
      // a name straight in (without picking a suggestion) is still a
      // perfectly valid save, same as before this search box existed;
      // clicking a suggestion (see getFloatingSuggestionsEl's own click
      // listener) just fills the same input's value in for you. No
      // .mm-suggestions div rendered inline here any more -- see
      // getFloatingSuggestionsEl for why (it's a single shared element
      // living outside the popover/canvas entirely, not one per field).
      function renderSearchFieldHtml(fieldName, searchKind, placeholder, currentValue) {
        return '<div class="mm-search-wrap">' +
          '<input class="mm-goal-input mm-search-input" type="text" autocomplete="off" ' +
          'data-goal-field="' + fieldName + '" data-search-kind="' + searchKind + '" ' +
          'placeholder="' + esc(placeholder) + '" maxlength="80" value="' + esc(currentValue || '') + '">' +
          '</div>';
      }

      // Same idea as renderSearchFieldHtml above, but backed by
      // LOCAL_SEARCH_POOLS (a fixed, already-in-memory list -- no
      // server round-trip) AND for a field whose saved value isn't the
      // same as what the player types/sees, unlike KC/ITEM/QUEST: a
      // skill's real value is its lowercase key ("runecraft"), not its
      // title-cased display name ("Runecraft"); a diary's real value is
      // its area slug ("kourend_kebos"), not its in-game name
      // ("Kourend & Kebos"). So the visible input here carries no
      // data-goal-field of its own -- it's pure display/search, tagged
      // data-goal-field-target instead, pointing at a companion hidden
      // input right beside it that DOES carry the real
      // data-goal-field="<fieldName>" (same hidden-input-carries-the-
      // real-value pattern renderSegmentedToggleHtml already uses for
      // the metric/tier toggles) -- see hiddenTargetFor/runGoalSearch/
      // the floating-suggestions click handler for how the two stay in
      // sync.
      function renderLocalSearchFieldHtml(fieldName, searchKind, placeholder, currentValue, labelFor) {
        var displayValue = currentValue ? labelFor(currentValue) : '';
        return '<div class="mm-search-wrap">' +
          '<input class="mm-goal-input mm-search-input" type="text" autocomplete="off" ' +
          'data-goal-field-target="' + fieldName + '" data-search-kind="' + searchKind + '" ' +
          'placeholder="' + esc(placeholder) + '" maxlength="80" value="' + esc(displayValue) + '">' +
          '<input type="hidden" data-goal-field="' + fieldName + '" value="' + esc(currentValue || '') + '">' +
          '</div>';
      }

      // Renders a segmented multi-choice button group backed by a
      // hidden `data-goal-field="<fieldName>"` input carrying whichever
      // option is currently active -- the skill goal's level/experience
      // choice and the diary goal's tier choice both use this in place
      // of a <select>. The goal-save click delegation reads every
      // `[data-goal-field]` element generically (including this hidden
      // one) exactly like a real <select>/<input>, so nothing else
      // needs to know this isn't one. Falls back to the FIRST option
      // when `currentValue` doesn't match any (a brand new goal with
      // nothing chosen yet) -- the same effective default a <select>
      // with no explicit `selected` option already had.
      function renderSegmentedToggleHtml(fieldName, options, currentValue) {
        var value = options.some(function (o) { return o[0] === currentValue; }) ? currentValue : options[0][0];
        var buttons = options.map(function (o) {
          var activeCls = (o[0] === value) ? ' active' : '';
          return '<button type="button" class="mm-segment-btn' + activeCls + '" data-segment-value="' + o[0] + '">' + esc(o[1]) + '</button>';
        }).join('');
        return '<div class="mm-segment-group" data-role="segment-group" data-segment-field="' + fieldName + '">' + buttons + '</div>' +
          '<input type="hidden" data-goal-field="' + fieldName + '" value="' + esc(value) + '">';
      }

      // The current color's goal-criteria fields, prefilled from the
      // node's own `goal` (see clean_goal/default_goal in
      // app/mindmaps.py for the exact shape each type stores) --
      // "white"/null (the root) never reaches this function at all any
      // more (see renderNodePopoverHtml's own early return), and every
      // OTHER color gets a small form whose fields are read fresh off
      // the DOM by the popover's own Save button (see the goal-save
      // click delegation above) -- nothing here is tracked in JS state,
      // so there's nothing to keep in sync with what the player's
      // actually typed. This whole function only ever runs in Edit Mode
      // now (see renderNodePopoverHtml's own early return), so there's
      // no separate view-mode branch to gate here either.
      //
      // "gray"/manual is the one type with no actual GOAL criteria (see
      // clean_goal in app/mindmaps.py -- its only field is
      // manualComplete, set by the checkbox right on the node itself,
      // see renderNodeLabelHtml, never by this popover) -- but it still
      // gets a field here now: a plain text box for the node's own
      // NAME, since a gray node no longer renames itself inline on the
      // canvas (see renderCanvas's isInlineEditable). Saving it goes
      // through the same Save button as every other type, but the
      // click delegation routes a manual node's save to the node's own
      // text (PATCH .../nodes/<id>) rather than its goal (PATCH
      // .../nodes/<id>/goal) -- see saveSelectedNodeText below.
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
          // No more activity-type dropdown -- the search field below
          // is scoped to killable NPCs specifically (see
          // app/npc_names.py), so activityType is always 'npc' now;
          // carried as a hidden field purely so the server's existing
          // clean_goal (which still requires it) sees a complete kc
          // goal without exposing a picklist the player never needs.
          fields =
            renderSearchFieldHtml('sourceName', 'npc', 'Search for an NPC', goal.sourceName) +
            '<input type="hidden" data-goal-field="activityType" value="npc">' +
            // type="text" (not "number"), same reasoning as the gp
            // goal's own target field below -- accepts the same
            // "140k"/"2.5m"/"1b" shorthand (see parseMoneySuffix and
            // filterNumericSuffixInput), which a real number input
            // would refuse to let the player type at all.
            '<input class="mm-goal-input" type="text" inputmode="decimal" data-goal-field="targetCount" placeholder="Target kc" value="' + esc(goal.targetCount != null ? goal.targetCount : '') + '">' +
            // Optional -- narrows targetCount to only count kc from this
            // date on, without ever showing on the node face itself (see
            // the kc summary text below and clean_goal's own comment in
            // app/mindmaps.py for why). Typed digits, auto-dashed into
            // 'YYYY-MM-DD' -- the exact same masked text field the Loot
            // Tracker's own "custom" range picker uses (see
            // DATE_MASK/applyDateMask/isValidIsoDate above, and the
            // save-click delegation's own invalid-date guard just
            // above it) -- rather than a native <input type="date">'s
            // own calendar popup, so the two date pickers on this site
            // now look and behave identically. The placeholder alone
            // only says the FORMAT (and disappears once typed), so this
            // field still gets its own hint line underneath -- same
            // reasoning as before switching to the masked input, just
            // no longer standing in for a missing placeholder, since
            // this one has a real one. Reads/writes/pre-fills through
            // the exact same generic [data-goal-field] mechanism as
            // every field above -- no other JS change needed for it
            // beyond the masking/validation wiring.
            '<div class="mm-goal-date-wrap">' +
              '<input class="mm-goal-input" type="text" data-goal-field="sinceDate" inputmode="numeric" autocomplete="off" spellcheck="false" placeholder="YYYY-MM-DD" value="' + esc(goal.sinceDate || '') + '">' +
              '<div class="mm-goal-hint">Only count kc from this date on (optional)</div>' +
            '</div>';
        } else if (type === 'item') {
          fields =
            renderSearchFieldHtml('itemName', 'item', 'Search for an item', goal.itemName) +
            // type="text" (not "number"), same reasoning as the gp
            // goal's own target field below -- accepts the same
            // "140k"/"2.5m"/"1b" shorthand (see parseMoneySuffix and
            // filterNumericSuffixInput), which a real number input
            // would refuse to let the player type at all.
            '<input class="mm-goal-input" type="text" inputmode="decimal" data-goal-field="targetQty" placeholder="Target quantity" value="' + esc(goal.targetQty != null ? goal.targetQty : '') + '">';
        } else if (type === 'gp') {
          // type="text" (not "number") because the shorthand this
          // accepts -- "140k", "2.5m", "1b" -- has letters in it, which
          // a real number input would just refuse to let the player
          // type at all; parseMoneySuffix resolves it to a plain
          // integer at save time (see the goal-save click delegation).
          fields =
            '<input class="mm-goal-input" type="text" inputmode="decimal" data-goal-field="targetGp" placeholder="Target gp (coins + tokens)" value="' + esc(goal.targetGp != null ? goal.targetGp : '') + '">';
        } else if (type === 'skill') {
          var metric = goal.metric === 'xp' ? 'xp' : 'level';
          var targetPlaceholder = metric === 'xp' ? 'Target experience' : 'Target level';
          // type="text" (not "number"), same reasoning as the gp
          // goal's own target field just above -- XP accepts the same
          // "140k"/"2.5m"/"1b" shorthand (see parseMoneySuffix,
          // resolved at save time by the goal-save click delegation,
          // live-validated by validateSkillTarget, and carried across
          // the LVL/XP toggle by the segmented-toggle click delegation
          // above), which a real number input would refuse to let the
          // player type at all. LVL never accepts the shorthand (a
          // level suffix makes no sense at OSRS's 1-126 scale) but
          // still uses the same text input -- restricting to digits
          // only ever happens in LVL mode is handled by validation, not
          // by swapping input types on every toggle click.
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
        // Every path below can tear down and rebuild #mmNodesLayer's
        // whole subtree (a different node selected, a goal saved, a
        // mindmap switched...), which would orphan the floating
        // suggestions box's activeSearchInput reference -- it lives
        // outside that subtree now (see getFloatingSuggestionsEl's own
        // comment) and wouldn't otherwise notice its anchor input is
        // gone until the next pan/zoom happened to call
        // positionFloatingSuggestions and catch the stale reference.
        // Closing it unconditionally here instead means it never
        // lingers on screen, visibly detached from whatever field it
        // used to belong to, in the gap between those two things.
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
            zoomToFit();
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
          zoomToFit();
        }
      }

      // ---- New/rename mindmap form ---------------------------------------

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
      // Site-wide standard: a required-field miss just gets a red border
      // on the field, no popup/inline text -- cleared as soon as the
      // person starts typing so it never lingers past the moment it's
      // fixed.
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
          if (data) { MM.data = data; render(); }
        }
      });

      // ---- Undo/redo --------------------------------------------------
      //
      // Every node-tree edit (add, delete, recolor, rename, add shared
      // child) records the tree's state from just BEFORE that edit
      // into MM.undoStack once the edit itself has actually succeeded,
      // so undo/redo is just "replace the whole node list with a past
      // (or future) snapshot" -- no per-action inverse logic to keep
      // in sync with add_node/delete_node/etc. This is also why
      // there's no more confirm-before-delete dialog: undo covers it
      // (any accidental delete, or any other edit) without
      // interrupting the player up front.
      var MAX_HISTORY = 50;

      function updateHistoryButtons() {
        var undoBtn = document.getElementById('mmUndoBtn');
        var redoBtn = document.getElementById('mmRedoBtn');
        if (undoBtn) undoBtn.disabled = !MM.undoStack.length;
        if (redoBtn) redoBtn.disabled = !MM.redoStack.length;
      }

      // Same disable-rather-than-hide treatment as updateHistoryButtons
      // just above (see its own comment, and .mm-zoom-controls
      // button:disabled in mindmaps.css, which both share), just keyed
      // off MM.zoom against MIN_ZOOM/MAX_ZOOM instead of the undo/redo
      // stacks -- called from every place MM.zoom can change (setZoom,
      // zoomToFit), so the +/- buttons are always dimmed exactly when
      // another click in that direction genuinely wouldn't do anything.
      function updateZoomButtons() {
        var zoomInBtn = document.getElementById('mmZoomIn');
        var zoomOutBtn = document.getElementById('mmZoomOut');
        if (zoomInBtn) zoomInBtn.disabled = MM.zoom >= MAX_ZOOM;
        if (zoomOutBtn) zoomOutBtn.disabled = MM.zoom <= MIN_ZOOM;
      }

      // The pencil toggle's own gold-when-on/gray-when-off state --
      // called alongside updateHistoryButtons (see render()) rather
      // than only from setEditMode, so a page load that restores
      // Edit Mode from storage (see loadStoredEditMode) still paints
      // the button correctly on its very first render.
      function updateEditModeButton() {
        var btn = document.getElementById('mmEditModeBtn');
        if (btn) btn.classList.toggle('active', MM.editMode);
      }

      // Pulses the Edit Mode button gold a couple of times -- called
      // when the player clicks a node's body while Edit Mode is off
      // (see the nodes-layer pointerdown delegation below), since a
      // node isn't clickable at all outside Edit Mode and this is the
      // one nudge toward the control that actually turns it on, rather
      // than the click just silently doing nothing. mm-glow is a plain
      // CSS animation (see mindmaps.css) with a fixed iteration count,
      // so all this does is (re)start it -- removing the class first
      // and forcing a reflow before re-adding it is what lets a second
      // click mid-glow restart the pulse from the beginning instead of
      // being ignored because the class was already present.
      function glowEditModeButton() {
        var btn = document.getElementById('mmEditModeBtn');
        if (!btn) return;
        btn.classList.remove('mm-glow');
        void btn.offsetWidth;
        btn.classList.add('mm-glow');
      }

      // Toggles a node between its front (label) and back (note) face
      // -- an immediate hard cut, no animation. This used to run a
      // squish-swap-unsquish transition (and, before that, a true 3D
      // rotateY), but a 3D-transform-based flip -- even the 2D
      // scaleX version this passed through on the way here -- is more
      // machinery than the hard cut the player actually wanted, so
      // this is now just the plain toggle + re-render every other
      // view-only action on a node already uses (see the
      // manual-complete checkbox's own handler just above).
      function flipNodeNote(nodeId) {
        if (MM.flippedNodeIds.has(nodeId)) MM.flippedNodeIds.delete(nodeId);
        else MM.flippedNodeIds.add(nodeId);
        render();
      }

      // Called by every mutating action below with `preNodes` --
      // activeMindmap().nodes as it stood right before that action's
      // API call -- but only AFTER that call has already come back
      // successful, so a failed request (network hiccup, validation error) never
      // records a snapshot for an edit that didn't actually happen.
      function recordUndoableEdit(preNodes) {
        MM.undoStack.push(preNodes);
        if (MM.undoStack.length > MAX_HISTORY) MM.undoStack.shift();
        // A fresh edit forks off a new future -- whatever was
        // previously redo-able no longer follows from where the tree
        // is now, same as any other undo/redo history (browsers,
        // editors, ...).
        MM.redoStack = [];
      }

      // True if the mindmap an in-flight edit was made against is
      // still the one on screen. Every mutating action below captures
      // its own mindmap's id before awaiting its request, then checks
      // this once the response comes back: switching to a different
      // mindmap resets ITS undo/redo history (see setActiveMindmapId),
      // and a slower, earlier edit's response landing after that
      // switch has nothing to do with the new mindmap's history --
      // without this check it would pop/push onto (or select a node
      // in) a history and tree that aren't its own.
      function isStillActiveMindmap(mmId) {
        return MM.activeMindmapId === mmId;
      }

      // The actual PUT that restores a snapshot -- shared by both
      // undo and redo below, which only differ in which stack they
      // read from/push onto, and (like every other mutating action)
      // only touch those stacks once this has actually succeeded.
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
        }
        render();
      }

      // ---- Selected-node actions ------------------------------------------

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
        if (isStillActiveMindmap(mmId)) recordUndoableEdit(preNodes);
        render();
      }

      // Replaces the selected node's goal criteria (see
      // set_node_goal/clean_goal in app/mindmaps.py) -- the trackable
      // types' "Save goal" button AND the gray manual-complete toggle
      // both funnel through here, same PATCH .../goal endpoint either
      // way, they just build a different `goal` object first. A 400
      // (an incomplete trackable submission -- clean_goal's
      // require_complete=True) surfaces the same way any other
      // rejected edit does, via apiCall's own showError -- nothing
      // needs undoing since the server never actually changed anything.
      // `closePopover` -- true only for the popover's own Save button
      // (see the goal-save click delegation above), never for the gray
      // manual-complete checkbox (see saveSelectedNodeGoal below), which
      // has no "popup" of its own to close -- deselects the node once
      // the save actually succeeds, which is what closes the popover
      // (it only ever shows for the selected node -- see
      // renderNodePopoverHtml). Left alone (not deselected) on a
      // failed save, so the player can fix whatever the error was
      // without having to reselect the node and start over. Takes an
      // explicit `nodeId` rather than always reading selectedNode()
      // because the manual-complete checkbox (see renderNodeLabelHtml)
      // now lives right on the node itself and works on ANY gray node,
      // selected or not, in or out of Edit Mode -- see its own click
      // handler above.
      //
      // `note` (see renderNoteFieldHtml/SetMindMapNodeGoalRequest's own
      // docstring in app/schemas.py) rides along on this same request,
      // applied server-side via the same update_node a plain node-PATCH
      // uses -- one request/one undo step for a trackable node's goal
      // AND its note together, rather than two. Left undefined by the
      // manual-complete checkbox call above (JSON.stringify drops an
      // undefined value's key entirely, same as the server's own
      // Optional[str] = None default), which is exactly right -- ticking
      // a goal complete should never touch its note.
      async function saveNodeGoal(nodeId, goal, note, closePopover) {
        var mm = activeMindmap();
        var node = mm && mm.nodes.find(function (n) { return n.id === nodeId; });
        if (!mm || !node) return;
        var mmId = mm.id;
        var preNodes = mm.nodes;
        // Not the shared apiCall helper here -- that always routes a
        // failed request to the page's top error banner (see
        // showError), which is exactly what showGoalSaveError's own
        // comment explains is the wrong place for a "you're missing a
        // field" validation message from clean_goal (app/mindmaps.py).
        // A 400 here IS specifically that (set_node_goal only ever
        // rejects with one -- see the /goal route in app/main.py), so
        // it goes to the popover instead; anything else (a dropped
        // connection, a genuine server error) still isn't about any
        // one field, so it keeps the old banner treatment.
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
        if (isStillActiveMindmap(mmId)) recordUndoableEdit(preNodes);
        if (closePopover) {
          MM.selectedNodeId = null;
          MM.multiSelectIds = new Set();
        }
        render();
      }
      // Thin wrapper over saveNodeGoal for the Edit-Mode popover's own
      // Save button, which only ever acts on whatever's currently
      // selected.
      function saveSelectedNodeGoal(goal, note, closePopover) {
        if (!MM.selectedNodeId) return;
        return saveNodeGoal(MM.selectedNodeId, goal, note, closePopover);
      }

      // A gray (manual) node's own Save button commits its NAME rather
      // than a goal -- see renderGoalFieldsHtml's "manual" branch and
      // the goal-save click delegation's own manual handling above.
      // Same shape as saveNodeGoal (PATCH, record undo, optionally
      // close the popover, `note` riding along the same way), just
      // against the plain node PATCH endpoint (see updateSelectedNode)
      // instead of .../goal, since a node's text and its goal criteria
      // are two separate fields server-side (see update_node vs.
      // set_node_goal in app/mindmaps.py) -- note lives with text here
      // (both go through update_node either way).
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
        if (isStillActiveMindmap(mmId)) recordUndoableEdit(preNodes);
        if (closePopover) {
          MM.selectedNodeId = null;
          MM.multiSelectIds = new Set();
        }
        render();
      }

      // Only the root is ever contenteditable now (see renderCanvas's
      // isInlineEditable -- a gray node renames through its popover's
      // text box instead, see saveSelectedNodeText above), so the
      // label losing focus always means the root's own text is what
      // changed -- no need to look up which node the label belonged to.
      function commitNodeTextFromLabel(label) {
        pendingLabelCommit = null;
        var node = selectedNode();
        if (!node) return;
        var val = (label.textContent || '').trim();
        if (!val || val === node.text) { label.textContent = node.text; return; }
        pendingLabelCommit = updateSelectedNode({ text: val });
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
        var mmId = mm.id;
        var preNodes = mm.nodes;
        // Empty, not a "New" placeholder -- selectNode below focuses +
        // selects the new node's label the instant it renders, so the
        // player just starts typing into a blank box (see
        // app/mindmaps.py's add_node, which now leaves an empty text
        // exactly as given instead of substituting its own default).
        var body = { relative_to: nodeId, relation: relation, text: '', color: 'gray' };
        if (relation === 'sibling') body.before = !!before;
        const data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        });
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) {
          recordUndoableEdit(preNodes);
          // selectNode both selects and (since it's a different id
          // than whatever was selected before) queues a focus for the
          // next render -- a brand new node is always gray, so that
          // resolves to the popover's own text box (see renderCanvas's
          // post-render focus effect), letting the player start typing
          // its name immediately without an extra click to open it.
          // Only done if the player's still looking at this mindmap --
          // otherwise the new node's id wouldn't belong to whatever
          // mindmap IS on screen now.
          selectNode(data.newNodeId || null);
        } else {
          render();
        }
      }

      // No confirm-before-delete dialog -- the undo button (see
      // "Undo/redo" above) covers an accidental delete the same way
      // it covers any other edit, without interrupting the player with
      // a prompt on every single delete.
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
        }
        render();
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
        var mmId = mm.id;
        var preNodes = mm.nodes;
        const data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/shared-child', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          // Empty for the same reason addNodeRelativeTo's own body is --
          // see that function's comment.
          body: JSON.stringify({ parent_ids: Array.from(MM.multiSelectIds), text: '', color: 'gray' }),
        });
        if (!data) return;
        MM.data = data;
        // selectNode below replaces MM.multiSelectIds with just the new
        // node on its own -- no separate .clear() needed first. Only
        // done if the player's still on this mindmap -- see
        // isStillActiveMindmap's comment.
        if (isStillActiveMindmap(mmId)) {
          recordUndoableEdit(preNodes);
          selectNode(data.newNodeId || null);
        } else {
          render();
        }
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
        zoomToFit();
      }

      loadState();
    })();
    """
    return extra_head, body, script


def render_mindmaps(player: PlayerView) -> str:
    """The Mindmaps page -- see _mindmaps_panel_markup above for the
    full markup/script; this is just that plus the _shell wrapper a
    real, logged-in-or-not page visit needs (see
    render_landing_mindmap_preview for the OTHER caller, which skips
    _shell entirely and embeds the same panel inline on the landing
    page instead)."""
    extra_head, body, script = _mindmaps_panel_markup()
    return _shell(
        title="Mindmaps — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )


# Storages Viewer's location-filter row groups the raw
# per-source storage keys (same key spelling as POSSESSION_STORAGE_KEYS
# in app/schemas.py/STORAGE_SOURCES in app/possessions.py) into six
# buttons rather than one per source -- with fourteen sources now, one
# button each stopped fitting on the same row as the search box.
# BANK folds Potion Storage in (both are things you visit a bank-like
# interface for); CHARACTER is what's actively worn/carried in the
# main inventory; PORTABLE is every other carried container item
# (Looting Bag, Rune Pouch, Tackle Box, Forestry Kit, Master Scroll
# Book, Seed Box, Huntsman's Kit); PoH is Player-Owned-House storage
# (today, just the Costume Room -- see PohItem's docstring in
# app/models.py); BOATS is every one of a player's (up to five)
# boats' cargo holds combined (see BoatCargoItem's own docstring for
# why they're still one button/key despite each boat's contents being
# genuinely separate underneath); SEED VAULT stays its own button
# since it's neither carried nor a bank.
# Each group is (label, [storage keys]) -- clicking a button toggles
# every key in its group together (see the click handler in the script
# below), so filtering is still exactly as granular as before under
# the hood: shownQuantity there still sums item.byLocation by the raw
# per-source key, untouched by this grouping.
_POSSESSION_LOCATION_GROUPS = [
    ("BANK", ["bank", "potion_storage"]),
    ("SEED VAULT", ["seed_vault"]),
    ("PoH", ["poh"]),
    ("BOATS", ["boat_cargo"]),
    ("PORTABLE", ["looting_bag", "rune_pouch", "tackle_box", "forestry_kit", "master_scroll_book", "seed_box", "huntsmans_kit"]),
    ("CHARACTER", ["equipment", "inventory"]),
]

#: Display label for every POSSESSION_STORAGE_KEYS entry -- backs the
#: settings-cog menu's checkboxes (see render_possessions below),
#: which list them alphabetically by this label rather than in
#: POSSESSION_STORAGE_KEYS' own fixed sync-status order. Same English
#: names the plugin's own side panel Status section shows (see
#: buildStatusStorageLabels in MyscapePanel.java) -- kept in sync by
#: hand since the two live in separate repos.
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
    """Builds Storages Viewer's (extra_head, body, script) triple --
    split out from render_possessions below (same reasoning, and the
    same split _purchase_goals_panel_markup/_loot_tracker_panel_markup/
    _mindmaps_panel_markup went through first) so the landing page's
    own interactive preview (render_landing_storages_preview) can reuse
    this exact markup/script inline, without render_possessions' own
    _shell wrapper (nav/footer/auth) around it.

    A single line-by-line table of everything the player currently owns
    across every synced storage (see get_owned_breakdown in
    app/possessions.py), fetched from GET /api/possessions/summary on
    load and re-polled every 5 seconds after that (same cadence as
    Purchase Goals' own PG.pollTimer in this file) so a change made
    in-game -- moving something out of the bank, say -- shows up here
    on its own shortly after, not only once the page is manually
    refreshed.

    One row per item: the ENTIRE row is one link (see wikiItemUrl/
    rowHtml in the script) out to that item's OSRS Wiki page, opened in
    a new tab -- hovering anywhere on the row highlights the whole
    thing and clicking anywhere on it (not just the icon/name) follows
    the link, same background-highlight-the-whole-clickable-box
    convention as Loot Tracker's own NPC/item boxes (see .loot-item-box
    in loot-tracker.css) rather than a link scoped to just the name --
    then QUANTITY (the full, unabbreviated
    count, with a lowercase "x" in front), GE VALUE and HA VALUE (each
    showing both the whole stack's value and one unit's value -- a
    glance at either number alone answers a different question,
    "what's this stack worth" vs. "what's one of these worth"), and a
    green/red TRADEABLE? badge -- tradeable meaning specifically
    tradeable on the Grand Exchange (resolve_item_display's own
    "tradeable" field in app/possessions.py is already exactly that:
    true only when the item is found in the live GE mapping, false for
    anything player-tradeable-but-not-GE-listed the same as for a
    genuinely untradeable item -- never a looser "can this be traded at
    all" definition). Every row is the same height regardless of
    whether its GE/HA cells actually have a per-unit line to show (see
    valueCell below, which always renders both lines -- the second one
    just empty when there's nothing to put there -- rather than only
    emitting it when needed).

    A poll only rebuilds a row's HTML (and so its <img> icon) when the
    visible set/order of items has actually changed; an unchanged poll
    -- by far the common case every 5 seconds -- just patches each
    existing row's quantity/value/tradeable text in place instead,
    leaving every icon untouched. When a rebuild IS needed, the new
    icons are preloaded before the HTML swap so they appear together
    with their rows instead of popping in a beat later (see
    preloadIcons/renderTable in the script -- same fix as Loot
    Tracker's own NPC/item boxes use, for the same reason: rebuilding
    live <img> elements on every poll, whether or not anything shown
    had actually changed, was what made these icons flicker).

    Search and the location filters share one row, at the same height
    -- the search box grows a CLEAR text button of its own at its far
    right edge the moment there's something typed into it (hidden
    again once the field's empty, whether that's from deleting the
    text, clicking CLEAR, or just never having typed anything -- see
    updateSearchClear). Locations are multi-select buttons (styled
    like Purchase Goals' own .sort-btn -- see that page's
    renderSortButtons in this file), toggled independently, all on by
    default, and purely reshape what QUANTITY -- and therefore GE/HA
    VALUE, which scale off it -- counts as owned (see shownQuantity
    below, which recomputes everything client-side from the one
    already-fetched summary payload's own per-location breakdown
    rather than re-polling the server on every toggle).

    The gear-icon button beside the location filters opens a menu of
    one checkbox per raw storage source, alphabetically labeled, all
    checked on by default -- unlike the location filter buttons
    (which just reshape a poll already in hand), unchecking one here
    is a real per-player setting (HiddenPossessionStorage, see
    app/models.py) that survives reloads and relogs, the same as a
    pin. A location filter button whose every underlying storage has
    been switched off this way disappears entirely (nothing left for
    it to filter) -- and the search box, already flex: 1 1 220px in
    possessions.css, grows into the space that frees up on its own,
    shrinking back the same way the moment a button reappears (see
    updateFilterButtonVisibility in the script).

    There's no separate sort control any more -- every header (ITEM,
    QUANTITY, GE VALUE, HA VALUE, TRADEABLE?) is a clickable
    .pm-sort-header button (see updateSortHeaders/visibleRows in the
    script) that sorts the table by that column, toggling ascending/
    descending on repeat clicks the way a spreadsheet's column headers
    do. Every header shares the same size and color, active or not --
    an arrow is the only thing marking which one is currently active.
    GE VALUE sorted highest-to-lowest is the default on load.

    Any row can be pinned -- a pushpin button, only visible on hover
    (always visible, filled gold, once pinned -- see .pm-pin-btn/
    .pinned in possessions.css), that floats it up into its own pinned
    group above a thin divider, separated from the rest of the list
    (see visibleRowGroups/setPinned in the script, and
    PinnedPossessionItem in app/models.py for where it's stored --
    server-side and per-player, so it's the same on every device, not
    a per-browser preference). A pinned row still sorts by whichever
    column is active and still respects search/location filtering,
    same as any other row -- pinning only changes which of the two
    groups it's sorted into, never whether it's shown at all.
    """
    extra_head = f'<link rel="stylesheet" href="/static/css/possessions.css?v={_POSSESSIONS_CSS_VERSION}" />'

    location_buttons = "".join(
        # PoH needs its literal mixed-case label preserved against
        # .pm-filter-btn's own text-transform: uppercase -- see the
        # pm-filter-btn-cased rule in possessions.css.
        f'<button type="button" class="pm-filter-btn{" pm-filter-btn-cased" if label == "PoH" else ""} active" '
        f'data-locations="{",".join(keys)}">{escape(label)}</button>'
        for label, keys in _POSSESSION_LOCATION_GROUPS
    )

    # Alphabetical by label (not POSSESSION_STORAGE_KEYS' own fixed
    # order) -- same pm-filter-btn-cased-style exception for PoH's
    # mixed-case label against .pm-settings-item's own uppercase
    # transform (see .pm-settings-item-cased in possessions.css). All
    # checked by default; JS reconciles each one against the
    # player's actual persisted setting once /api/possessions/summary
    # answers (see applyHiddenStorageKeys in the script below).
    settings_checkboxes = "".join(
        f'<label class="pm-settings-item{" pm-settings-item-cased" if key == "poh" else ""}">'
        f'<input type="checkbox" data-storage-key="{key}" checked /> {escape(label)}</label>'
        for key, label in sorted(_POSSESSION_STORAGE_LABELS.items(), key=lambda kv: kv[1].lower())
    )

    # The per-column filter trigger (see .pm-filter-icon-btn in
    # possessions.css, and wireFilterIcons in the script below) --
    # Feather Icons' own "filter" glyph (a funnel outline), same
    # stroke-icon family as PIN_GLYPH/the settings gear further down
    # -- one constant reused across all five header cells rather than
    # rebuilt per column, since it never varies.
    funnel_glyph = (
        '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon></svg>'
    )

    body = f"""
    <h2 class="page-title">Storages Viewer</h2>
    <div class="auth-error" id="pmError"></div>

    <section class="pm-section">
      <div class="pm-controls-row">
        <div class="pm-control-group pm-search-group">
          <input type="text" class="loot-search" id="pmSearch" placeholder="Search for an item" autocomplete="off" />
          <button type="button" class="pm-search-clear" id="pmSearchClear" style="display:none;">Clear</button>
        </div>
        <div class="pm-control-group pm-location-group">
          {location_buttons}
        </div>
        <div class="pm-control-group pm-settings-wrap">
          <button type="button" class="pm-settings-btn" id="pmSettingsBtn" title="Choose which storages to show">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.65 6.20 L9.54 2.82 L14.46 2.82 L15.35 6.20 L18.72 5.28 L21.18 9.54 L18.70 12.00 L21.18 14.46 L18.72 18.72 L15.35 17.80 L14.46 21.18 L9.54 21.18 L8.65 17.80 L5.28 18.72 L2.82 14.46 L5.30 12.00 L2.82 9.54 L5.28 5.28 Z"></path><circle cx="12" cy="12" r="3.1"></circle></svg>
          </button>
          <div class="pm-settings-menu" id="pmSettingsMenu" style="display:none;">
            {settings_checkboxes}
          </div>
        </div>
      </div>

      <p class="pg-empty" id="pmEmpty" style="display:none;">Nothing synced yet.</p>

      <div class="pm-views-row" id="pmViewsRow"></div>

      <div class="pm-table" id="pmTable" style="display:none;">
        <div class="pm-row pm-row-header">
          <div class="pm-col pm-col-image pm-header-cell">
            <button type="button" class="pm-sort-header" data-sort-key="alpha">Item<span class="pm-sort-arrow"></span></button>
            <button type="button" class="pm-filter-icon-btn" data-filter-col="alpha" title="Filter Item" aria-label="Filter Item">{funnel_glyph}</button>
          </div>
          <div class="pm-col pm-col-qty pm-header-cell">
            <button type="button" class="pm-sort-header" data-sort-key="qty">Quantity<span class="pm-sort-arrow"></span></button>
            <button type="button" class="pm-filter-icon-btn" data-filter-col="qty" title="Filter Quantity" aria-label="Filter Quantity">{funnel_glyph}</button>
          </div>
          <div class="pm-col pm-col-ge pm-header-cell">
            <button type="button" class="pm-sort-header" data-sort-key="ge">GE Value<span class="pm-sort-arrow"></span></button>
            <button type="button" class="pm-filter-icon-btn" data-filter-col="ge" title="Filter GE Value" aria-label="Filter GE Value">{funnel_glyph}</button>
          </div>
          <div class="pm-col pm-col-ha pm-header-cell">
            <button type="button" class="pm-sort-header" data-sort-key="ha">HA Value<span class="pm-sort-arrow"></span></button>
            <button type="button" class="pm-filter-icon-btn" data-filter-col="ha" title="Filter HA Value" aria-label="Filter HA Value">{funnel_glyph}</button>
          </div>
          <div class="pm-col pm-col-tradeable pm-header-cell">
            <button type="button" class="pm-sort-header" data-sort-key="tradeable">Tradeable?<span class="pm-sort-arrow"></span></button>
            <button type="button" class="pm-filter-icon-btn" data-filter-col="tradeable" title="Filter Tradeable?" aria-label="Filter Tradeable?">{funnel_glyph}</button>
          </div>
        </div>
        <div id="pmRows"></div>
      </div>
    </section>
    """

    script = """
    (function () {
      // The direction each column header starts in on its FIRST click --
      // numeric/boolean columns start high-to-low (most owned/valuable/
      // tradeable first, the more useful default), the name column
      // starts A-Z. A second click on the already-active header flips
      // that, same as a spreadsheet's own column-header sort.
      var SORT_DEFAULT_DIR = { alpha: 'asc', qty: 'desc', ge: 'desc', ha: 'desc', tradeable: 'desc' };

      // GE VALUE, highest stack first, is the default sort on load.
      //
      // locations/enabledStorages below MUST list every one of
      // POSSESSION_STORAGE_KEYS in app/schemas.py -- a key missing from
      // either object reads as `undefined` (falsy) forever, which looks
      // exactly like the storage being off: shownQuantity zeroes it out,
      // updateFilterButtonVisibility hides its whole filter button (if
      // every key in its group is missing/off), and every loadSummary
      // poll's applyHiddenStorageKeys call re-unchecks its settings
      // checkbox even after the player checks it back on (Object.keys
      // only walks the keys that exist here, but the checkbox-sync loop
      // right below still visits every checkbox in the DOM). Huntsman's
      // Kit and Boat Cargo shipped without being added here and hit
      // exactly this -- selecting them appeared to instantly revert.
      var state = {
        items: [],
        search: '',
        sortKey: 'ge',
        sortDir: 'desc',
        locations: { bank: true, potion_storage: true, seed_vault: true, poh: true, boat_cargo: true, equipment: true, inventory: true, looting_bag: true, rune_pouch: true, tackle_box: true, forestry_kit: true, master_scroll_book: true, seed_box: true, huntsmans_kit: true },
        // Persisted server-side (HiddenPossessionStorage, app/models.py)
        // -- separate from `locations` above, which is a purely
        // transient, resets-on-reload show/hide filter. This one
        // survives reloads/relogs, and is what actually zeroes an
        // item's contribution to shownQuantity regardless of the
        // filter buttons' own state -- see applyHiddenStorageKeys,
        // which syncs it (and every settings-menu checkbox) from
        // whatever loadSummary's own poll last saw.
        enabledStorages: { bank: true, potion_storage: true, seed_vault: true, poh: true, boat_cargo: true, equipment: true, inventory: true, looting_bag: true, rune_pouch: true, tackle_box: true, forestry_kit: true, master_scroll_book: true, seed_box: true, huntsmans_kit: true },
        // Per-column filters (see matchesFilters below) -- keyed by
        // column ('alpha'/'qty'/'ge'/'ha'/'tradeable'), each either
        // absent/null (no filter on that column) or one of the filter
        // shapes buildFilterFromPopover produces. Persisted server-side
        // only as part of a saved view's own config (PossessionView,
        // app/models.py) -- like `search` above, this itself resets on
        // reload unless a saved view is applied.
        filters: {},
        // Every saved view this player has (PossessionView,
        // app/models.py), in their own reorder-strip order -- see
        // loadViews/renderViewsRow. activeViewId is which one (if any)
        // currently matches state.sortKey/sortDir/filters -- cleared
        // the instant any of those three change by hand (see
        // clearActiveViewHighlight), so the highlighted chip never
        // lies about what's actually being shown.
        views: [],
        activeViewId: null,
      };

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

      // Full, unabbreviated numbers everywhere on this page -- comma
      // thousands separators for readability, never a compact "15k"/
      // "1.2M" form (see this function's callers: QUANTITY, and both
      // the stack and per-unit lines of GE VALUE/HA VALUE).
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

      // A drawing-pin/thumbtack glyph, not a map marker -- pinning an
      // item here is "stick this to the top of the list", not "here's
      // a location", so the icon should read as a physical pushpin
      // (flat head, tapered body, needle poking out below) rather than
      // the teardrop-plus-dot map-pin shape. Feather Icons has no
      // literal thumbtack, so this is hand-drawn to match its exact
      // stroke conventions (same line-outline-icon family every other
      // small control on this site draws from -- see, e.g., Mindmaps'
      // zoom-to-fit/undo/redo/edit-mode SVGs in this file), rather than
      // an emoji glyph. One markup shared by both pinned/unpinned states
      // -- see .pm-pin-btn/.pinned in possessions.css for how gray vs.
      // gold is told apart instead (color alone, currentColor picks it
      // up automatically, never a different icon).
      var PIN_GLYPH = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 4h8"></path><path d="M9 4v6l-2 4v2h10v-2l-2-4V4"></path><path d="M12 16v5"></path></svg>';

      // Same wiki-search-redirect link every item icon/name on this
      // page opens (see Loot Tracker's own wikiItemUrl in this file for
      // the identical approach, self-contained here per this project's
      // per-page-script convention rather than shared between them).
      function wikiItemUrl(name) {
        return 'https://oldschool.runescape.wiki/w/Special:Search?search=' + encodeURIComponent(name || '') + '&go=Go';
      }

      // Loads every one of these icon URLs in the background before
      // the caller swaps in HTML that references them, so a rebuilt
      // table paints already decoded instead of icons popping in a
      // beat after the rows themselves already changed -- see the
      // identical helper (and its own fuller comment) in Loot Tracker's
      // script in this file.
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

      // ---- Sort (click a column header -- see SORT_DEFAULT_DIR above) --

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

      // ---- Per-column filter popovers (funnel icon beside each header
      // -- a separate element from .pm-sort-header above, with its own
      // click target and its own stopPropagation everywhere, so
      // opening/using a filter never also re-sorts the column it's
      // attached to) --------------------------------------------------

      var FILTER_COLUMNS = { alpha: 'text', qty: 'numeric', ge: 'numeric', ha: 'numeric', tradeable: 'tradeable' };
      // Quantity/GE Value/HA Value all share the exact same numeric
      // filter shape (see numericMatch below) -- only the number
      // field's own placeholder differs, so a player always knows
      // which number a bare "150" in the box actually means. GE/HA
      // additionally get their own Stack/Single segmented control
      // (STACK_MODE_OPTIONS below) since those two columns' own
      // primary number is a stack total (price * quantity), and a
      // player may want to filter by the single/per-unit price
      // instead -- Quantity has no such distinction, so it never gets
      // that control.
      var NUMERIC_PLACEHOLDERS = { qty: 'Quantity', ge: 'Value', ha: 'Value' };

      // Every mode/operator choice in every popover below is a
      // segmented control -- every option shown at once, side by side,
      // with the current one picked out (same shape as Mindmaps' own
      // skill-goal LVL/XP switch, renderSegmentedToggleHtml in this
      // file -- .pm-segment-group/.pm-segment-btn in possessions.css
      // are this page's own copy of that same visual recipe, per this
      // project's per-page-CSS convention, not a shared class). Options
      // are [value, label] pairs; a numeric operator's label is
      // pre-escaped HTML for the same reason the old operator
      // <select>'s own option labels were -- a raw "<"/">" as element
      // TEXT content would otherwise be parsed as the start of a tag.
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
          // GE/HA only -- lets a player filter by either the stack
          // total (price * quantity, this column's own default/
          // displayed number) or the single per-unit price. Sits
          // beside the Value field rather than above it so it never
          // costs its own row, and stays visible even while Between
          // is selected and the Value field itself is hidden (it's a
          // flex sibling of that input, not nested inside it), since
          // Stack/Single still governs what the Min/Max fields below
          // are being compared against either way.
          var showStackToggle = (col === 'ge' || col === 'ha');
          var valueMode = showStackToggle ? ((current && current.valueMode) || 'stack') : null;
          var valueRow = (
            '<div class="pm-filter-value-row">' +
            (showStackToggle ? segmentGroupHtml('stackMode', STACK_MODE_OPTIONS, valueMode) : '') +
            '<input type="text" inputmode="decimal" class="pm-filter-input" data-role="value" placeholder="' + placeholder + '" value="' + value + '"' + (isBetween ? ' style="display:none;"' : '') + ' />' +
            '</div>'
          );
          return (
            segmentGroupHtml('op', NUMERIC_OP_OPTIONS, op) +
            valueRow +
            '<div class="pm-filter-input-pair" data-role="between-row"' + (isBetween ? '' : ' style="display:none;"') + '>' +
            '<input type="text" inputmode="decimal" class="pm-filter-input" data-role="min" placeholder="Min" value="' + min + '" />' +
            '<span class="pm-filter-input-pair-sep">&ndash;</span>' +
            '<input type="text" inputmode="decimal" class="pm-filter-input" data-role="max" placeholder="Max" value="' + max + '" />' +
            '</div>' +
            actions
          );
        }
        // tradeable
        var mode = (current && current.mode) || 'tradeable';
        return segmentGroupHtml('mode', TRADEABLE_MODE_OPTIONS, mode) + actions;
      }

      // Every numeric filter field (Quantity, GE/HA Value, and the
      // Between row's Min/Max) accepts k/m/b shorthand -- "1.5m",
      // "50k", "3b" -- and comma-grouped digits -- "2,500,000" --
      // alongside a plain number, so a player never has to count out
      // zeros by hand. These are plain type="text" inputs rather than
      // type="number" specifically because a number input rejects
      // letters and commas outright, which would make shorthand
      // impossible to even type. sanitizeAmountChars strips anything
      // outside digits/commas/periods/k/m/b as the player types (see
      // its 'input' listener in wirePopoverControls below); parseAmount
      // is the matching parser that turns whatever's left into an
      // actual number, used everywhere a numeric field used to just
      // get parseFloat'd.
      function sanitizeAmountChars(raw) {
        return (raw || '').replace(/[^0-9.,kmbKMB]/g, '');
      }

      function parseAmount(raw) {
        if (raw === null || raw === undefined) return null;
        var s = String(raw).trim();
        if (!s) return null;
        var match = /^([0-9]*\.?[0-9]+|[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*([kKmMbB])?$/.exec(s);
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

      // Reads whatever's currently selected/typed in an open popover
      // and turns it into the filter object matchesFilters expects --
      // null when there's nothing usable to apply (an empty text box,
      // an empty/non-numeric number field), which Apply treats as "no
      // filter on this column" rather than an error.
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
        // tradeable
        return { mode: segmentValue('mode', 'tradeable') };
      }

      function wirePopoverControls(col, popoverEl) {
        // Same click-delegation shape as Mindmaps' own segmented-toggle
        // handling -- clicking a segment marks IT active and clears
        // every sibling within its own group (never across groups;
        // the numeric popover's operator group is the only one with
        // more than one group in scope, but there's only ever one
        // group per popover in practice here).
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
        // Value/Min/Max accept k/m/b shorthand and comma grouping
        // (see parseAmount above) -- this is what actually enforces
        // "only digits, commas, periods, and k/m/b" as the player
        // types, stripping anything else on every keystroke (and on
        // paste, since 'input' fires for that too) rather than just
        // at Apply time.
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
        // Never let a click inside the popover (a segment, an input,
        // Apply/Clear) bubble up to the document-level "click outside
        // closes it" listener in wireFilterIcons below.
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

      // ---- Locations (multi-select groups, all on by default) ----------
      // Each button covers a GROUP of raw storage keys (data-locations is
      // comma-separated -- e.g. BANK is "bank,potion_storage"). A click is
      // a single master toggle for the whole group: if every key in the
      // group is currently on, the click turns them all off; otherwise it
      // turns them all on. state.locations itself stays keyed by the raw
      // per-source keys throughout, same as shownQuantity()/activeLocations
      // below expect.

      document.querySelectorAll('.pm-filter-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var keys = btn.getAttribute('data-locations').split(',');
          var allActive = keys.every(function (k) { return state.locations[k]; });
          var next = !allActive;
          keys.forEach(function (k) { state.locations[k] = next; });
          btn.classList.toggle('active', next);
          renderTable();
        });
      });

      // ---- Settings (per-storage on/off, persisted server-side) --------
      // The gear-icon menu next to the location filter buttons -- one
      // checkbox per raw storage key, alphabetically labeled (see
      // _POSSESSION_STORAGE_LABELS in app/pages.py), all checked by
      // default. Unlike the location filter buttons above, this is a
      // real per-player setting (HiddenPossessionStorage, app/models.py)
      // that survives reloads and relogs -- state.enabledStorages is
      // reconciled against the server's own hiddenStorageKeys on every
      // loadSummary poll (see applyHiddenStorageKeys), and every
      // checkbox toggle posts/deletes immediately rather than waiting
      // for the next poll, same "don't feel laggy" reasoning as
      // setPinned further down.

      var pmSettingsBtn = document.getElementById('pmSettingsBtn');
      var pmSettingsMenu = document.getElementById('pmSettingsMenu');

      // Gold border/icon while open -- same .active treatment as a
      // location filter button (.pm-filter-btn.active), applied here
      // to the trigger button itself rather than the menu, and kept in
      // sync on every path that can close the menu (the button's own
      // click, and the outside-click handler below), not just the one
      // that opened it.
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

      // A location filter button disappears entirely once every raw
      // key it covers has been switched off here -- there's nothing
      // left for it to filter -- and the search box (flex: 1 1 220px
      // in possessions.css) grows to fill the space that frees up on
      // its own, no extra layout code needed; it shrinks back the same
      // way the moment a button reappears.
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
          renderTable();
        });
      });

      // ---- Search + its CLEAR button (shown only once there's text to
      // clear, hidden again the moment the field goes back to empty --
      // whether that's from typing, deleting, or clicking CLEAR itself) --

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
        pmSearchInput.focus();
      });

      // ---- Table --------------------------------------------------------

      function shownQuantity(item) {
        var total = 0;
        for (var key in item.byLocation) {
          if (state.locations[key] && state.enabledStorages[key]) total += item.byLocation[key];
        }
        return total;
      }

      // ---- Per-column filters (funnel icon beside each header, see
      // wireFilterIcons) ---------------------------------------------

      // Quantity/GE Value/HA Value's shared filter -- an operator (>,
      // >=, <, <=, =, !=) against one typed number, or a between-two-
      // values range. Applied against QUANTITY as shown for the qty
      // column, and against the STACK total (price * qty) for GE/HA --
      // matching both what those two columns display as their primary
      // line and what sorting by them already ranks by (see
      // visibleRows' own sort below), never the per-unit price alone.
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

      // One combined check across every active column filter -- a row
      // has to pass ALL of them (not any), same "every active filter
      // narrows the list further" convention as the search box and
      // location buttons already sitting alongside these. A column
      // with no filter set (state.filters[col] is undefined/null) is
      // simply skipped, same as every other still-default column.
      function matchesFilters(item, qty) {
        var f = state.filters;
        if (f.alpha) {
          var needle = (f.alpha.text || '').toLowerCase();
          var hit = needle ? item.name.toLowerCase().indexOf(needle) !== -1 : true;
          if (f.alpha.mode === 'not_contains') hit = !hit;
          if (!hit) return false;
        }
        if (f.qty && !numericMatch(qty, f.qty)) return false;
        // GE/HA compare against either the stack total (default,
        // matches what the column itself displays/sorts by) or the
        // single per-unit price, per that filter's own Stack/Single
        // toggle -- valueMode is absent on any filter saved before
        // that toggle existed, which the "!== 'single'" check treats
        // the same as an explicit 'stack'.
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

      // Splits the same sorted/filtered rows visibleRows() already
      // produces into a pinned group and everything else, each still
      // in the exact sort order the columns headers chose -- pinning
      // only changes WHICH group a row lands in, never how a group's
      // own rows are ordered relative to each other. See renderTable,
      // which renders pinned first, then a divider, then the rest.
      function visibleRowGroups() {
        var rows = visibleRows();
        var pinned = [];
        var rest = [];
        for (var i = 0; i < rows.length; i++) {
          (rows[i].item.pinned ? pinned : rest).push(rows[i]);
        }
        return { pinned: pinned, rest: rest };
      }

      // One value column's two lines -- the whole stack's worth ("N gp",
      // primary) and, only when there's more than one to distinguish it
      // from, one unit's worth ("N ea", dim) -- or an em dash when this
      // item has no price on file at all (an untradeable item with no
      // linked value either, or a tradeable one the wiki just doesn't
      // have current data for -- see build_possessions_summary's own
      // comment in app/possessions.py for why those two cases can't be
      // told apart from gePrice/highAlch alone, and why that's fine
      // here). At qty 1 the stack value and the unit value are the same
      // number, so the "ea" line would just be a redundant repeat of
      // the line right above it -- left EMPTY rather than shown twice,
      // but the second .pm-value-each div is still always rendered
      // (never omitted) so every row comes out the same height whether
      // or not it actually has a per-unit line's worth of text in it.
      //
      // `derived` (GE column only, item.geDerived) marks a value that
      // isn't a direct Grand Exchange listing at all -- an untradeable
      // item's value computed from a linked item instead (see
      // derived_price_for in app/purchase_goals.py; TRADEABLE still
      // correctly reads NO for these) -- shown with a leading "~" so it
      // doesn't read as a real GE price. The tilde is wrapped in its
      // own span rather than sitting inline in the text -- the pixel
      // font (RuneScapePlain11) draws that glyph noticeably higher in
      // its own em-box than digits/letters are, which without this
      // dragged the whole "~N gp" line up a few px versus every other
      // row; pm-derived-mark (possessions.css) pins it back down to the
      // shared baseline.
      // The "each" line is only emitted when there's actually a per-unit
      // price to show (qty > 1). Earlier this always rendered an empty
      // <div class="pm-value-each"> as a spacer so every row matched
      // height -- but that reserved a blank second line under every
      // qty-1 (or unpriced) value, which left the visible number sitting
      // in the top half of that two-line space instead of centered in
      // the row like every other single-line column. Omitting the div
      // entirely lets .pm-row's own align-items: center do the
      // centering, same as it already does for the QTY/TRADEABLE cells.
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

      // The row itself is the link (an <a>, not a <div>) -- see
      // .pm-col-image and a.pm-row:hover in possessions.css -- rather
      // than just the icon/name, same "the whole box is one link" shape
      // as Loot Tracker's own .loot-item-box in this file. The pin
      // button is a SIBLING of that <a>, both wrapped in one plain,
      // non-interactive .pm-row-wrap, rather than nested inside the
      // <a> itself -- a <button> nested inside an <a> isn't valid HTML
      // (both are interactive content), and positioning it as a
      // sibling instead (see .pm-pin-btn in possessions.css) means
      // clicking it never touches the row's own link at all, no
      // preventDefault/stopPropagation gymnastics needed.
      function rowHtml(v) {
        var item = v.item;
        var tradeableCls = item.tradeable ? 'pm-badge-yes' : 'pm-badge-no';
        var tradeableText = item.tradeable ? 'YES' : 'NO';
        var pinCls = 'pm-pin-btn' + (item.pinned ? ' pinned' : '');
        var pinLabel = item.pinned ? 'Unpin' : 'Pin to top';
        return '<div class="pm-row-wrap">' +
          '<button type="button" class="' + pinCls + '" data-item-id="' + item.itemId + '" data-pinned="' + (item.pinned ? '1' : '0') + '" title="' + pinLabel + '" aria-label="' + pinLabel + '">' + PIN_GLYPH + '</button>' +
          '<a class="pm-row" href="' + wikiItemUrl(item.name) + '" target="_blank" rel="noopener" title="' + escapeHtml(item.name) + '">' +
            '<div class="pm-col pm-col-image">' + iconImg(item.icon) +
              '<span class="pm-row-name">' + escapeHtml(item.name) + '</span></div>' +
            '<div class="pm-col pm-col-qty">x' + fmtNum(v.qty) + '</div>' +
            '<div class="pm-col pm-col-ge">' + valueCell(item.gePrice, v.qty, item.geDerived) + '</div>' +
            '<div class="pm-col pm-col-ha">' + valueCell(item.highAlch, v.qty) + '</div>' +
            '<div class="pm-col pm-col-tradeable"><span class="pm-badge ' + tradeableCls + '">' + tradeableText + '</span></div>' +
          '</a>' +
        '</div>';
      }

      // Rebuilding every row's HTML (and so its <img> icon) on every
      // single 5-second poll -- even when nothing the table actually
      // shows had changed -- was what made these icons flicker
      // regularly. Same fix as Loot Tracker's NPC/item boxes: only
      // rebuild when the visible set/order of items has actually
      // changed (dedup key below), otherwise just patch each existing
      // row's qty/value/tradeable text in place and leave its icon
      // untouched; and when a rebuild IS needed, preload the new
      // icons before swapping the HTML in so they don't pop in a beat
      // after the rows already changed.
      //
      // lastPmRowRefs is a big part of why the patch path stays cheap
      // at large item counts: it's populated ONCE, right after a
      // rebuild, with each visible row's own child elements (queried
      // once via querySelector) -- every subsequent patch-in-place
      // poll (which can fire every 5 seconds for as long as the
      // visible set doesn't change) then writes straight to those
      // cached references instead of re-running 5 querySelector calls
      // PER ROW every single time. At a large item count with a wide
      // filter (hundreds to low thousands of visible rows), those
      // repeated querySelector calls were themselves a measurable,
      // recurring cost -- re-querying the same elements over and over
      // for numbers that usually haven't even changed.
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
        // pinnedKey is redundant with the id sequence below in every
        // case except a pin/unpin that happens not to change any row's
        // position (only possible with a single visible item) -- cheap
        // to include and guarantees a pin toggle always forces the
        // rebuild branch below, never the patch-in-place one, since
        // which group a row is in (and so whether the divider shows)
        // can only change there.
        var pinnedKey = groups.pinned.map(function (v) { return v.item.itemId; }).join(',');
        // filterKey -- same reasoning as pinnedKey above: a filter
        // change can narrow/widen the visible set without necessarily
        // changing the sorted id sequence of what's STILL visible
        // (e.g. tightening an already-active filter that removes
        // nothing currently shown), so it has to be part of the key
        // in its own right rather than relying on the id list alone.
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
            // Cache each visible row's own child elements once here,
            // right after the rebuild that just created them -- see
            // lastPmRowRefs' own comment above for why the
            // patch-in-place branch below leans on this instead of
            // re-querying every poll. Queried by .pm-row-wrap
            // specifically (not rowsEl.children) so the divider
            // between pinned and unpinned rows, when present, doesn't
            // shift the index-to-item mapping by one.
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

        // Same item set/order/pin-state as last render (key unchanged)
        // -- reuse the existing rows (and their <img> icons) but still
        // refresh the quantity/value/tradeable text in place, since a
        // later poll can change those numbers for an item still sorted
        // into the same slot.
        visible.forEach(function (v, i) {
          var refs = lastPmRowRefs[i];
          if (!refs) return;
          var item = v.item;
          if (refs.link) refs.link.title = item.name;
          if (refs.qtyEl) refs.qtyEl.textContent = 'x' + fmtNum(v.qty);
          if (refs.geEl) refs.geEl.innerHTML = valueCell(item.gePrice, v.qty, item.geDerived);
          if (refs.haEl) refs.haEl.innerHTML = valueCell(item.highAlch, v.qty);
          if (refs.badge) {
            refs.badge.className = 'pm-badge ' + (item.tradeable ? 'pm-badge-yes' : 'pm-badge-no');
            refs.badge.textContent = item.tradeable ? 'YES' : 'NO';
          }
        });
      }

      async function loadSummary() {
        var data = await apiCall('/api/possessions/summary');
        if (!data) return;
        state.items = data.items || [];
        applyHiddenStorageKeys(data.hiddenStorageKeys);
        renderTable();
      }

      // Pin/unpin -- POST or DELETE against the one item id, then
      // reconcile state.items against the server's own returned
      // pinnedItemIds (the source of truth) rather than just flipping
      // the clicked item's flag locally, so a stale/failed request
      // never leaves the UI showing something the server doesn't
      // actually have. Re-renders immediately rather than waiting for
      // the next 5-second poll, same reasoning as every other action
      // on this page that shouldn't feel laggy.
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

      // One delegated listener on the rows container rather than
      // binding a click handler to every pin button individually --
      // rows get replaced wholesale on a rebuild (see renderTable
      // above), so a per-button binding would just leak/vanish on
      // every rebuild instead of needing this at all.
      document.getElementById('pmRows').addEventListener('click', function (e) {
        var btn = e.target.closest('.pm-pin-btn');
        if (!btn) return;
        var itemId = Number(btn.getAttribute('data-item-id'));
        var currentlyPinned = btn.getAttribute('data-pinned') === '1';
        setPinned(itemId, !currentlyPinned);
      });

      // ---- Saved views (named, reorderable, server-persisted -- see
      // PossessionView in app/models.py) -- lets a player switch
      // between several different filter/sort setups without
      // re-building each one by hand every time. Unlike gear setups'
      // OWN icon row (Purchase Goals, wireSetupIconDrag), a view isn't
      // "active" just by existing -- state.activeViewId only reflects
      // one that was actually just applied (or saved), and is dropped
      // the moment the player changes sort/filters by hand (see
      // clearActiveViewHighlight, called from the sort header click
      // handler above and every filter Apply/Clear above).

      var viewDragSuppressClick = false;

      function currentConfigSnapshot() {
        return { sortKey: state.sortKey, sortDir: state.sortDir, filters: state.filters };
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
        state.activeViewId = view.id;
        updateSortHeaders();
        updateFilterIconStates();
        renderViewsRow();
        renderTable();
      }

      function openSaveViewPopover() {
        closeAllFilterPopovers();
        var row = document.getElementById('pmViewsRow');
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
          // A brand new view always lands past the end of the player's
          // existing ones (see next_possession_view_sort_order in
          // app/possessions.py), so the array's own last entry IS the
          // one just created -- no id round-tripped back explicitly.
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
            '<button type="button" class="pm-view-chip' + active + '" data-view-id="' + v.id + '" draggable="true" title="' + escapeHtml(v.name) + '">' +
            '<span class="pm-view-chip-name">' + escapeHtml(v.name) + '</span>' +
            '<span class="pm-view-delete" data-view-delete="' + v.id + '" title="Delete this view" aria-label="Delete this view">&times;</span>' +
            '</button>'
          );
        }).join('') + '<button type="button" class="pm-view-add-btn" id="pmViewAddBtn">+ Save View</button>';

        row.querySelectorAll('.pm-view-chip').forEach(function (chip) {
          chip.addEventListener('click', function (e) {
            if (e.target.closest('.pm-view-delete')) return;
            if (viewDragSuppressClick) { viewDragSuppressClick = false; return; }
            var id = chip.getAttribute('data-view-id');
            if (id === state.activeViewId) {
              // Clicking the already-active chip again deselects it --
              // back to the page's own plain defaults, same as a fresh
              // load with no view applied.
              state.sortKey = 'ge'; state.sortDir = 'desc'; state.filters = {}; state.activeViewId = null;
              updateSortHeaders(); updateFilterIconStates(); renderViewsRow(); renderTable();
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

      // Drag-and-drop reordering for the saved-views strip -- same
      // FLIP-preview/live-DOM-order/full-replacement shape as Purchase
      // Goals' own wireSetupIconDrag (app/pages.py), reused here over
      // data-view-id chips instead of data-setup-id ones. Unlike that
      // row, nothing else on this page polls/rebuilds #pmViewsRow out
      // from under an in-flight drag (loadSummary's own 5s poll only
      // ever touches state.items/#pmRows), so this doesn't need that
      // function's own PG.dragging guard flag.
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

      updateSortHeaders();
      updateFilterIconStates();
      loadSummary();
      loadViews();
      // Re-poll the same way Purchase Goals does (see PG.pollTimer
      // above in this file) -- a plugin sync (moving something from
      // the bank into inventory/equipment, say) should show up here on
      // its own within a few seconds, not only once the page is
      // manually refreshed.
      setInterval(loadSummary, 5000);
    })();
    """
    return extra_head, body, script


def render_landing_storages_preview() -> Optional[Tuple[str, str, str]]:
    """The landing page's own interactive Storages Viewer preview --
    same reuse-the-real-script pattern as the other three (reuses
    _possessions_panel_markup's body/script completely unmodified,
    layering demo-only behavior on top from the outside in a wrapper
    script), backed by one real, curated snapshot: app/data/
    landing_storages_demo.json is a one-time GET /api/possessions/
    summary pull of the account's own real current possessions --
    every item owned across every synced storage, exactly as the real
    page would show it -- with every PoH (Player-Owned-House, i.e.
    Costume Room) item stripped out first (see
    _get_landing_storages_demo_data's own comment for exactly how).
    Returns (extra_head, body, script) for render_landing to splice
    into its own markup, same as the other three, or None if the
    snapshot isn't there to read.

    Closer in spirit to Loot Tracker's preview than Purchase Goals' or
    Mindmaps': nothing here EDITS what's owned (there's no "add an
    item" on the real page either), but everything else genuinely
    works -- search, every column's sort/filter, pinning a row to the
    top, and saving/reordering/deleting named views -- all running
    against one frozen, PoH-free snapshot, in memory, never reaching
    the real API:

    1. A `fetch` shim, scoped to just this wrapper (a local `var
       fetch` inside its own IIFE, never touching window.fetch), that:
       - Answers GET /api/possessions/summary out of the frozen item
         list, with each item's own `pinned` flag freshly computed
         from whatever's currently in DEMO_PINNED_IDS (a plain Set) --
         not just replayed from the snapshot's own original pins --
         so a pin/unpin the player makes here survives the real page's
         own 5-second poll (loadSummary re-fetches and replaces
         state.items wholesale on every tick -- see
         _possessions_panel_markup's own docstring) instead of
         silently reverting a few seconds later. hiddenStorageKeys
         works the same way, off a plain in-memory Set the settings-
         menu checkboxes actually read and write below.
       - Implements POST/DELETE /api/possessions/pins/{itemId} for
         real against that same Set, returning {{pinnedItemIds: [...]}}
         exactly like the real endpoint.
       - Implements POST/DELETE /api/possessions/hidden-storages/
         {{key}} for real against DEMO_HIDDEN_KEYS, returning
         {{hiddenStorageKeys: [...]}}.
       - Implements the saved-views endpoints (GET/POST /api/
         possessions/views, DELETE /api/possessions/views/{{id}}, PUT
         /api/possessions/views/order) for real against an in-memory
         DEMO_VIEWS array, starting empty (a fresh account has none
         either) -- so "+ Save View" genuinely creates one, its × genu-
         inely deletes it, and dragging the strip genuinely reorders
         it, all without ever touching the real, session-authenticated
         API or this demo visitor's own (nonexistent) saved views.
       - Anything else gets a harmless failure response instead of
         ever reaching the real API.
    2. No localStorage shadowing needed here (unlike Mindmaps) -- this
       page's own script never reads or writes it.
    3. Same fixed-height container + always-on bottom-edge feather as
       the other three previews (.landing-storages-preview in
       possessions.css).

    Every item row is still a real, plain <a> out to the OSRS Wiki
    (wikiItemUrl in the reused script) -- a public, unauthenticated
    search URL with nothing account-specific in it, so unlike Purchase
    Goals' own gear icons those links needed no extra handling at all;
    they're left completely untouched here.

    The 5-second poll (setInterval(loadSummary, 5000), inside {script}
    itself) is left running rather than neutralized, same as Loot
    Tracker's own poll -- it just keeps re-fetching the same
    (pin/hidden-storage-aware) snapshot from the shim above, which is
    harmless and, unlike stopping it, means a pin made here would
    still be reflected if the player left the tab open for a while.
    """
    demo = _get_landing_storages_demo_data()
    if demo is None:
        return None
    extra_head, body, script = _possessions_panel_markup()

    # Landing-preview-only hero row, prepended in front of the reused
    # panel body -- character on the LEFT this time (per this
    # preview's own request), tagline's own wrap on the right -- same
    # flex row/bottom-align treatment as the other three previews' own
    # hero rows, just under this preview's own class names since its
    # markup/CSS are Storages Viewer's, not any other page's. See
    # .purchase-preview-hero in purchase-goals.css for the identical
    # character-first layout this mirrors. The reused body's own
    # "Storages Viewer" <h2> is hidden via CSS (.landing-storages-
    # preview .page-title), same as the other three.
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
      // The captured, PoH-free snapshot itself (see
      // _get_landing_storages_demo_data's own comment) -- a plain
      // array of items, each already shaped exactly like the real
      // GET /api/possessions/summary response's own `items` entries.
      var DEMO_ITEMS = {items_json};
      // Working, mutable copies -- NOT re-derived from DEMO_ITEMS on
      // every read, so a pin/unpin or a settings-menu toggle made here
      // survives this page's own 5-second re-poll (see this function's
      // own docstring, point 1).
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

      // ---- fetch shim -----------------------------------------------------
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
          // Any view missing from the given order (shouldn't happen --
          // the reused script always sends every chip's own id) stays
          // appended at the end rather than silently vanishing.
          DEMO_VIEWS.forEach(function (v) {{ if (order.indexOf(v.id) === -1) reordered.push(v); }});
          DEMO_VIEWS = reordered;
          return ok({{ views: DEMO_VIEWS }});
        }}
        if (url.indexOf('/api/possessions/views/') === 0 && method === 'DELETE') {{
          var delId = decodeURIComponent(url.slice('/api/possessions/views/'.length));
          DEMO_VIEWS = DEMO_VIEWS.filter(function (v) {{ return v.id !== delId; }});
          return ok({{ views: DEMO_VIEWS }});
        }}

        // A view rename (PATCH /api/possessions/views/{{id}}) -- not
        // wired up to any button in the reused script (see this
        // function's own docstring) -- and anything else this script
        // doesn't otherwise call. Graceful failure, never the real
        // network -- same discipline as the other three previews' own
        // catch-all.
        return fail('Not available in this preview.');
      }};

      {script}

      // Same fixed-height container + always-on bottom-edge feather as
      // the other three previews -- see .landing-storages-preview in
      // possessions.css, and render_landing_loot_preview's own wrapper
      // script for the fuller comment this mirrors. No JS needed here
      // any more either, for the same reason.
    }})();
    """
    return extra_head, body, wrapper_script


def render_possessions(player: PlayerView) -> str:
    """The Storages Viewer page -- see _possessions_panel_markup above
    for the full markup/script; this is just that plus the _shell
    wrapper a real, logged-in-or-not page visit needs (see
    render_landing_storages_preview for the OTHER caller, which skips
    _shell entirely and embeds the same panel inline on the landing
    page instead)."""
    extra_head, body, script = _possessions_panel_markup()
    return _shell(
        title="Storages Viewer — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )


def _goal_tracking_panel_markup() -> Tuple[str, str, str]:
    """Builds Goal Tracking's (extra_head, body, script) triple --
    split out from render_goal_tracking below (same reasoning, and the
    same split _purchase_goals_panel_markup/_loot_tracker_panel_markup/
    _mindmaps_panel_markup/_possessions_panel_markup already went
    through) so the landing page's own interactive preview
    (render_landing_goal_tracking_preview, just below) can reuse this
    exact body/script -- unmodified -- without also pulling in the
    is_linked gate render_goal_tracking itself needs (the demo's own
    frozen goal list stands in for a real linked account) or the
    _shell wrapper a real, logged-in-or-not page visit needs."""
    extra_head = f'<link rel="stylesheet" href="/static/css/goal-tracking.css?v={_GOAL_TRACKING_CSS_VERSION}" />'

    # A kc goal's own icon (see goalRowHtml in the script below) is its
    # real boss sprite, not the generic KC badge -- every HISCORE_BOSSES
    # entry has one (see the has_icon check in that module's own
    # docstring; there's no missing-icon fallback needed here the way
    # the old boss-table page once needed for its "no icon yet" case).
    # Built here rather than duplicated client-side since HISCORE_BOSSES
    # is this file's own source of truth for boss display names. Its
    # keys (already alphabetical -- see that module's own docstring)
    # double as the wizard's own boss search list client-side, so
    # there's no separate boss-names array to keep in sync with this.
    boss_slug_by_name_json = json.dumps({name: slug for slug, name, _has_icon in HISCORE_BOSSES})
    # SKILL_NAMES (app/mindmaps.py) is OSRS's own skills-tab order, not
    # alphabetical -- re-sorted here for the wizard's own skill search
    # list, same alphabetize-it convention this redesign already
    # applies to the dashboard's card order and the boss/skill icon
    # lookups above.
    skill_names_json = json.dumps(sorted(SKILL_NAMES))

    body = """
    <h2 class="page-title">Goal Tracking</h2>
    <div class="auth-error" id="gtError"></div>

    <div class="gt-wizard" id="gtWizard">
      <button type="button" class="gt-wizard-add-btn" id="gtWizardAddBtn">Add goal</button>
      <div class="gt-wizard-expanded" id="gtWizardExpanded" style="display:none;">
        <div id="gtWizardStage"></div>
      </div>
    </div>

    <div class="gt-card gt-list-card">
      <div class="gt-sort-tabs" id="gtSortTabs">
        <button type="button" class="gt-sort-tab" data-sort="progress_desc" title="Progress, closest to done first">Progress &darr;</button>
        <button type="button" class="gt-sort-tab" data-sort="progress_asc" title="Progress, furthest from done first">Progress &uarr;</button>
        <button type="button" class="gt-sort-tab" data-sort="type_desc" title="Type, Item to KC">Type &darr;</button>
        <button type="button" class="gt-sort-tab" data-sort="type_asc" title="Type, KC to Item">Type &uarr;</button>
        <button type="button" class="gt-sort-tab" data-sort="reverse_alphabetical" title="Z to A">A-Z &darr;</button>
        <button type="button" class="gt-sort-tab" data-sort="alphabetical" title="A to Z">A-Z &uarr;</button>
        <button type="button" class="gt-sort-tab" data-sort="recent" title="Newest created first">Recent &darr;</button>
        <button type="button" class="gt-sort-tab" data-sort="oldest" title="Oldest created first">Recent &uarr;</button>
        <button type="button" class="gt-sort-tab" data-sort="custom">Custom</button>
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
      // Generic per-TYPE badge -- still what the type-picker buttons
      // above show (they represent the category being picked, not a
      // specific goal), and item goals' own row icon too (there's no
      // single canonical sprite for "any item"). A kc/skill goal's own
      // row icon is its real boss/skill sprite instead -- see
      // goalRowHtml's iconSrc below, which only falls back to this for
      // item goals.
      var TYPE_ICON = {
        kc: '/static/img/icon-goal-kc.png',
        skill: '/static/img/icon-goal-skill.png',
        item: '/static/img/icon-goal-item.png',
      };
      // The "Type" sort tab's own grouping order -- same kc/skill/item
      // sequence TYPE_ICON above already uses, so a type-sorted list
      // reads in the same order the wizard's own stage-2 type picker
      // and every other type-keyed lookup on this page already agree
      // on, rather than introducing a second, different ordering.
      var GOAL_TYPE_SORT_ORDER = { kc: 0, skill: 1, item: 2 };
      // Bounds mirror app.mindmaps' own MIN/MAX_SKILL_LEVEL, just for
      // this field's own live validation (see validateTargetField
      // below) -- the server re-validates against its own copy of
      // these regardless. The skill xp floor is 1 here rather than
      // Mindmaps' own 0 -- this wizard has no "level 1 is always
      // already met" carve-out to accommodate, so a plain "at least
      // 1" reads more naturally for a fresh goal.
      var TARGET_BOUNDS = {
        kc: { min: 1, max: 2147483647 },
        item: { min: 1, max: 2147483647 },
        skill_level: { min: 1, max: 126 },
        skill_xp: { min: 1, max: 200000000 },
      };

      // ---- Target-field input masking + the skill lvl/xp table ----------
      //
      // Ported from Mindmaps' own copy of this exact same machinery
      // (parseMoneySuffix/filterNumericSuffixInput/SKILL_XP_TABLE/
      // xpForLevel/levelForXp -- see render_mindmaps' script, same
      // file) rather than shared, since each page here is its own
      // self-contained script with no module shared between them.

      // Lets the quantity/kc/xp-or-lvl target field be typed as a
      // shorthand -- "140k", "2.5m", "1b" -- and resolves it to the
      // plain integer actually sent to the server. Commas are always
      // stripped first (filterNumericSuffixInput lets a player type
      // them in purely for readability), so "2,500k" and "2500k"
      // resolve identically. Anything that isn't a number immediately
      // followed by k/m/b (case-insensitive) passes through untouched.
      function parseMoneySuffix(raw) {
        var s = (raw || '').trim().replace(/,/g, '');
        var m = /^([0-9]*\.?[0-9]+)\s*([kKmMbB])$/.exec(s);
        if (!m) return s;
        var mult = { k: 1e3, m: 1e6, b: 1e9 }[m[2].toLowerCase()];
        return String(Math.round(parseFloat(m[1]) * mult));
      }

      // Restricts what actually lands in the target field to exactly
      // the characters that could ever be valid there: digits, commas
      // (typing-time thousands separator), a decimal point (only
      // meaningful with a k/m/b suffix, harmless alone), and k/m/b
      // themselves. Anything else typed/pasted/dropped in is silently
      // dropped -- hence this being type="text" inputmode="decimal"
      // rather than type="number" (a real number input could never be
      // made to accept the K/M/B shorthand too).
      var NUMERIC_SUFFIX_DISALLOWED_RE = /[^0-9,.kKmMbB]/g;

      function filterNumericSuffixInput(input) {
        var cleaned = input.value.replace(NUMERIC_SUFFIX_DISALLOWED_RE, '');
        if (cleaned === input.value) return;
        var cursor = input.selectionStart;
        var keptBeforeCursor = input.value.slice(0, cursor).replace(NUMERIC_SUFFIX_DISALLOWED_RE, '').length;
        input.value = cleaned;
        input.setSelectionRange(keptBeforeCursor, keptBeforeCursor);
      }

      // The OSRS xp-per-level curve (levels 1-126, including the
      // "virtual" levels above the real level-99 cap) -- see
      // https://oldschool.runescape.wiki/w/Experience for the formula
      // this implements exactly: xp(L) = floor(1/4 * sum[l=1..L-1] of
      // floor(l + 300*2^(l/7))). Built once off TARGET_BOUNDS.skill_level.max
      // rather than hardcoded, so it can never drift from whatever the
      // level cap above says. SKILL_XP_TABLE[L] is the total xp needed
      // for level L; index 0 is unused (levels are 1-indexed) and
      // SKILL_XP_TABLE[1] is always 0.
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
      // The xp SKILL_XP_TABLE says a level needs, clamped into range --
      // used when the metric toggle switches from LVL to XP.
      function xpForLevel(level) {
        var b = TARGET_BOUNDS.skill_level;
        level = Math.max(b.min, Math.min(b.max, Math.round(level)));
        return SKILL_XP_TABLE[level];
      }
      // The level a given amount of xp has actually reached -- the
      // LARGEST level whose own requirement is at or below it (5,750
      // xp sits between level 22's 5,624 and level 23's 6,291, so this
      // reads as 22, same as the in-game skills tab would show) --
      // used when the metric toggle switches from XP to LVL.
      function levelForXp(xp) {
        var b = TARGET_BOUNDS.skill_level;
        for (var l = b.max; l >= b.min; l--) {
          if (xp >= SKILL_XP_TABLE[l]) return l;
        }
        return b.min;
      }

      var GT = {
        goals: [],
        // Which of #gtSortTabs' own buttons is active -- persisted
        // server-side now (GameAccount.goal_sort_mode), remembered
        // across refreshes/sessions the same way GoalReorderRequest's
        // own custom order is (see setGoalSortMode/applyGoalsResponse
        // below). This placeholder just covers the instant before the
        // very first /api/goals response actually arrives -- it's
        // overwritten from data.sort_mode on every load from then on,
        // never read on its own. 'alphabetical' matches this list's
        // own account-side default (see the migration that added
        // goal_sort_mode) -- the only order it ever had before sorting
        // existed. See sortGoals below for what each mode actually does.
        sortMode: 'alphabetical',
        // 0 = collapsed (just the + box), 1 = pick one-time/recurring,
        // 2 = pick a type, 3 = pick a target + value, 4 = pick a
        // recurring goal's own cadence (recurring only -- a one-time
        // goal saves straight from stage 3 instead of ever reaching
        // this one).
        wizardStage: 0,
        recurring: null, // null | 'one_time' | 'recurring' -- picked in stage 1
        type: null,
        skillMetric: 'level',
        itemId: null, // the chosen search result's real item id, if any -- see Goal.item_id's own docstring in app/models.py
        // A ONE-TIME kc or xp-metric skill goal's own GAIN/REACH choice
        // (#gtTargetModeToggle, stage 3 -- see targetModeApplies) --
        // 'gain' by default (a player thinking "get 50 more kc" is
        // likely more common than "reach a lifetime total of 50 kc" --
        // see Goal.baseline_value's own docstring in app/models.py for
        // what each one actually means server-side). Only ever READ
        // when targetModeApplies() is true (see wizardAddGoal). Left
        // untouched -- not force-reset -- switching away from kc/skill
        // entirely (an item goal, or leaving stage 3 altogether) hides
        // this toggle without resetting it, so a player's own pick
        // survives a Back-then-Forward the same way GT.type/
        // wizardTarget already do. A skill goal's own Lvl<->Xp toggle
        // is the one exception: switching LEVEL -> XP resets this to
        // 'gain' every time (see that toggle's own click handler),
        // since GAIN/REACH isn't a real choice yet on LEVEL -- there's
        // nothing there for a pick to "survive" from, only a stale
        // leftover value from some earlier visit to XP that GAIN's own
        // default is meant to replace.
        targetMode: 'gain',
        recurInterval: '', // stage 4's own text field, kept here so re-rendering that stage (e.g. after Back then forward again) doesn't lose it
        recurUnit: 'day', // stage 4's own segmented-control selection
        // sortMode + a JSON snapshot of whatever GT.goals last actually
        // got rendered with (see applyGoalsResponse/renderGoalList) --
        // null until the first render. Exists purely so
        // applyGoalsResponse can skip renderGoalList's own full
        // listEl.innerHTML rebuild when a poll comes back with nothing
        // actually different from what's already on screen, instead of
        // doing that rebuild unconditionally on every single 5-second
        // tick the way this used to.
        renderKey: null,
      };
      // Cached once rather than recomputed on every keystroke -- both
      // are small (71/24 entries) fixed lists, not endpoints, so the
      // wizard's own boss/skill search (see wireWizardStage below)
      // filters these client-side instead of round-tripping like the
      // item search does.
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

      // ---- Add-goal wizard ----------------------------------------------
      //
      // Collapsed by default -- just the + box right under the page
      // title. Clicking it expands the SAME box into a flow of up to 4
      // "pages": stage 1 picks one-time vs recurring, stage 2 picks a
      // goal type (item/kc/skill for one-time; recurring drops item --
      // see wizardStageTypeHtml, RECURRING_GOAL_TYPES' own reasoning in
      // app/goals.py), stage 3 picks the actual target (a search box
      // for all three types, not just item -- click a suggestion or
      // type free text, same tolerance app.goals.clean_new_goal already
      // gives an item goal's name) and its target value, then either
      // submits right away (one-time -- stage 3's button reads Save) or
      // moves on to stage 4 to pick the recurring cadence itself
      // (recurring -- stage 3's button reads Next instead). The x (or a
      // successful add) collapses back to stage 0, ready for the next
      // goal.

      var wizardExpanded = document.getElementById('gtWizardExpanded');
      var wizardStageEl = document.getElementById('gtWizardStage');
      // The stage-3 target actually picked so far this visit -- reset
      // every time stage 3 (re)renders (see wireWizardStage). name is
      // whatever's in the search box, whether from a clicked suggestion
      // or typed free text; itemId only ever gets set for an item goal,
      // from the id a clicked item-search suggestion carried; value is
      // the parsed target number, captured once stage 3's own Save/Next
      // button is clicked (see wireWizardStage) so wizardAddGoal can
      // still read it from here after stage 4 has replaced stage 3's
      // own #gtTargetValue field in the DOM.
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
        // A recurring skill goal only ever tracks xp -- see
        // wizardStageTargetHtml's own metricToggle suppression just
        // below, which is what removes the Lvl/Xp toggle for this
        // combination so there's no UI left to set it any other way.
        // Forced here (not just left at whatever it already was) so a
        // player who picked Lvl on an earlier one-time skill goal this
        // same visit, then backed out into a recurring one, doesn't
        // silently carry that stale choice forward.
        if (GT.recurring === 'recurring' && type === 'skill') { GT.skillMetric = 'xp'; }
        // This is the one place stage 3 is ever entered FRESH (either
        // the first time, or after backing out to stage 2 and picking
        // a type again -- possibly a different one, whose old target
        // wouldn't even make sense any more), so this is where
        // wizardTarget gets cleared -- see wireWizardStage's own
        // comment for why it deliberately does NOT clear this itself
        // any more.
        wizardTarget = { name: '', itemId: null, value: null };
        GT.wizardStage = 3;
        renderWizard();
      }

      // Stage-aware -- Back means something different depending on
      // which stage it's leaving, same as each stage's own forward
      // step resets exactly the state that stage owns (see
      // wizardPickRecurrence/wizardPickType above). Only resets what
      // the stage being left back INTO doesn't already own, so e.g.
      // backing out of stage 4 (cadence) straight to stage 3 keeps
      // GT.type/wizardTarget/GT.skillMetric/GT.targetMode intact --
      // there's nothing wrong with them, stage 3 just wants to be
      // exactly as the player left it.
      function wizardBack() {
        if (GT.wizardStage === 4) {
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
      // One listener for the whole page, not re-added per render (stage
      // 3's own suggestions box gets rebuilt every time it renders) --
      // looks the elements up fresh on each click instead, so this
      // harmlessly no-ops on any stage where they don't exist.
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
        }[GT.wizardStage];
        wizardStageEl.innerHTML = stageHtml();
        wireWizardStage();
      }

      // Gold, line-drawn (stroke, not fill -- same weight/style as the
      // goal list's own trash-can icon) so both read as UI marks
      // rather than art, and both fit the same 32px slot
      // .gt-wizard-type-btn img already sizes a type card's icon to
      // (see the svg sizing rule alongside that one in
      // goal-tracking.css). ONE_TIME is a plain "1x" mark; RECURRING
      // is a small calendar with a repeat-arrows loop inside it, same
      // idea as a typical "recurring event" glyph.
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

      // Stage 1: one-time vs recurring -- the wizard's very first
      // "page" now, reusing the exact same type-card/Cancel wrapper
      // stage 2's own type picker below uses (same fixed-size box,
      // same centered-as-a-group layout), just with 2 cards instead of
      // 3 and an SVG icon (gold, see ONE_TIME_ICON_SVG/
      // RECURRING_ICON_SVG above) in place of each card's usual <img>.
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

      // Stage 2: the type picker -- item/kc/skill for a one-time goal,
      // same 3 cards this stage always showed before recurrence
      // existed; kc/skill only for a recurring one (see
      // RECURRING_GOAL_TYPES' own reasoning in app/goals.py -- an item
      // goal's owned quantity isn't a monotonic lifetime total, so
      // "gained since the last period" wouldn't mean the same thing
      // for it). Shorter now that there's no top-right x to make room
      // for -- see goal-tracking.css -- with a small centered Back +
      // Cancel underneath, pinned to the bottom of the SAME
      // fixed-height box stage 3 uses via margin-top: auto, same
      // technique .gt-wizard-stage2's own actions row uses too. Back
      // exists here (stage 1 itself has none -- there's nothing
      // before it to go back to) because this is no longer the
      // wizard's first page now that stage 1 (one-time/recurring)
      // exists ahead of it.
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
          // A recurring skill goal has no Lvl/Xp choice -- it's XP-only
          // (see wizardStageTargetHtml's own comment on why) -- so this
          // card says just "Skill Xp" on that path instead of the
          // one-time flow's "Skill Lvl/Xp", which would otherwise
          // promise a level option this path never actually offers.
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

      // Whether GAIN/REACH actually means anything for whatever's
      // currently picked -- mirrors app.goals.target_mode_allows_gain
      // exactly (see its own comment for why a LEVEL-metric skill goal
      // and an "item" goal both stay REACH-only, and a recurring goal
      // doesn't need a second, independent baseline of its own). The
      // server re-validates against its own copy regardless
      // (clean_target_mode in app/goals.py) -- this is what decides
      // whether target_mode actually gets sent (see wizardAddGoal) and
      // which placeholder phrasing applies (wizardTargetPlaceholder),
      // NOT whether #gtTargetModeToggle is on the page at all -- see
      // targetModeVisible just below for that, which is a strictly
      // wider set (a one-time skill goal shows -- but disables -- this
      // toggle even on LEVEL, where this function returns false).
      function targetModeApplies() {
        if (GT.recurring === 'recurring') return false;
        if (GT.type === 'kc') return true;
        if (GT.type === 'skill') return GT.skillMetric === 'xp';
        return false;
      }

      // Whether #gtTargetModeToggle renders in the DOM at all, whether
      // or not it's actually usable right now -- a one-time skill goal
      // shows it on LEVEL too (disabled -- see wireTargetModeToggle),
      // rather than making it pop in and out purely from flipping
      // Lvl<->Xp, so a player can see GAIN/REACH exists for this goal
      // type without having to already be on Xp to discover it. Same
      // as targetModeApplies() everywhere else -- a recurring goal or
      // an item goal never shows this toggle at all, disabled or not.
      function targetModeVisible() {
        if (GT.recurring === 'recurring') return false;
        if (GT.type === 'kc') return true;
        if (GT.type === 'skill') return true;
        return false;
      }

      // The target field's placeholder -- doubles as this field's only
      // label now (see wizardStageTargetHtml/updateWizardTargetField
      // below, which is what keeps it current whenever the skill
      // goal's own Lvl/Xp toggle -- or now #gtTargetModeToggle itself
      // -- switches). A GAIN-mode kc/xp goal gets its own "___ to
      // gain" phrasing instead of "Target ___", so the field itself
      // keeps reinforcing which reading is active without needing a
      // separate label row to do it -- the exact ambiguity
      // #gtTargetModeToggle exists to resolve in the first place.
      function wizardTargetPlaceholder() {
        var gain = targetModeApplies() && GT.targetMode === 'gain';
        if (GT.type === 'kc') return gain ? 'Kc to gain' : 'Target kc';
        if (GT.type === 'skill') {
          if (GT.skillMetric === 'xp') return gain ? 'Experience to gain' : 'Target experience';
          return 'Target level';
        }
        return 'Target quantity';
      }

      // Stage 3 -- one box, same fixed size as every other stage (see
      // the .gt-wizard-expanded/#gtWizardStage height rules in
      // goal-tracking.css), now three rows deep instead of two: the
      // search field + target-value field share a row near the top,
      // this stage's own segmented controls (Lvl/Xp and/or GAIN/REACH,
      // see #gtWizardSegRow below) get a row of their own in the
      // middle, and Back/Cancel/Save-or-Next sit in their own row
      // pinned to the bottom (see .gt-wizard-stage2's own gap +
      // .gt-wizard-actions' margin-top: auto in goal-tracking.css).
      // Neither field carries its own <label> any more -- placeholder
      // text (WIZARD_SEARCH_PLACEHOLDER/wizardTargetPlaceholder) does
      // that job instead, so there's no label row above the inputs to
      // keep in sync any more either. The last button reads Next
      // instead of Save for a recurring goal -- there's one more page
      // (stage 4's own cadence picker) before this actually submits,
      // see wireWizardStage's own click handler for the
      // id="gtWizardSave" button below.
      //
      // #gtTargetModeField (GAIN/REACH, one-time kc/xp-skill goals only
      // -- see targetModeApplies) sits in #gtWizardSegRow beside the
      // Lvl/Xp toggle (or alone, for a kc goal, which has no Lvl/Xp
      // toggle at all) -- both are "how do I want this framed" choices
      // about the same target value, so they read as one segmented-
      // control row together rather than living inline with the text
      // fields above them. It's always rendered as this one always-
      // present empty wrapper regardless of whether it applies --
      // wireTargetModeToggle (called once from wireWizardStage, and
      // again from the Lvl/Xp toggle's own click handler) fills it in
      // or empties it back out in place, since switching Lvl<->Xp
      // doesn't re-render this whole stage; that same function also
      // calls updateWizardSegRowVisibility so the whole segmented-
      // control row disappears (rather than sitting there as an empty
      // gap) for an item goal, or a skill goal currently on Lvl, which
      // has neither toggle to show.
      function wizardStageTargetHtml() {
        // No Lvl/Xp choice at all for a recurring skill goal -- it only
        // ever tracks xp (see wizardPickType, which is what forces
        // GT.skillMetric to 'xp' the moment "skill" gets picked here),
        // so there's nothing for a toggle to switch between.
        var metricToggle = (GT.type !== 'skill' || GT.recurring === 'recurring') ? '' : (
          '<div class="gt-metric-toggle" id="gtMetricToggle">' +
          '  <button type="button" class="gt-metric-btn" data-metric="level">Lvl</button>' +
          '  <button type="button" class="gt-metric-btn" data-metric="xp">XP</button>' +
          '</div>'
        );
        var saveLabel = (GT.recurring === 'recurring') ? 'Next' : 'Save';
        // Next reads like a secondary action (same look as Back/Cancel)
        // rather than the page's one gold "primary" button -- there's
        // still a real Save ahead of it on stage 4, so Next shouldn't
        // read as the action that actually creates the goal.
        var saveBtnClass = 'gt-add-btn' + (GT.recurring === 'recurring' ? ' gt-wizard-btn-next' : '');
        // Three rows now, not two: the search/target fields on top,
        // this stage's own segmented controls (Lvl/Xp and/or GAIN/
        // REACH -- see #gtWizardSegRow below) on their own row in the
        // middle, and Back/Cancel/Save-or-Next pinned to the bottom --
        // see .gt-wizard-segrow's own comment in goal-tracking.css for
        // why these moved off the field row onto a row of their own.
        // #gtWizardSegRow always renders (even for an item goal, which
        // has neither toggle) -- updateWizardSegRowVisibility (called
        // from wireTargetModeToggle, which itself runs both on this
        // stage's initial wiring and again whenever Lvl/Xp flips) hides
        // the whole row via .gt-wizard-segrow--empty when it ends up
        // with nothing in it, same :empty-collapse idea
        // #gtTargetModeField already used on its own.
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

      // #gtTargetModeField's own contents -- see targetModeApplies/
      // wireTargetModeToggle for who calls this and when. Same
      // 2-button segmented look as #gtMetricToggle just beside it
      // (reused classes, not a near-duplicate set of rules -- see
      // .gt-target-mode-toggle's own comment in goal-tracking.css for
      // why this one gets its own class anyway despite the shared
      // look), GAIN first since that's this control's own default.
      function targetModeToggleHtml() {
        return '' +
          '<div class="gt-target-mode-toggle" id="gtTargetModeToggle">' +
          '  <button type="button" class="gt-target-mode-btn" data-mode="gain">Gain</button>' +
          '  <button type="button" class="gt-target-mode-btn" data-mode="reach">Reach</button>' +
          '</div>';
      }

      // Fills #gtTargetModeField in (or empties it back out) to match
      // targetModeVisible() right now, and wires its two buttons --
      // called once from wireWizardStage when stage 3 first renders,
      // and again from the Lvl/Xp metric toggle's own click handler
      // (updateWizardTargetField's neighbor, not that function itself)
      // since switching Lvl<->Xp changes targetModeApplies()'s own
      // answer without stage 3 ever re-rendering from scratch. Safe to
      // call repeatedly -- re-wiring an already-empty (or already-
      // filled, same content) field is a harmless no-op past the first
      // real change. Emptying it (rather than hiding it some other
      // way) is what lets #gtTargetModeField:empty in goal-tracking.css
      // collapse it out of the row's flex flow entirely when it isn't
      // visible at all (an item goal, or any recurring goal) -- see
      // that rule's own comment. Also refreshes #gtWizardSegRow's own
      // visibility every time (see updateWizardSegRowVisibility
      // below), since this is the one function that runs every time
      // this field's contents could have changed -- the row it's part
      // of needs to disappear right along with it once it (and any
      // Lvl/Xp toggle beside it) both go empty.
      //
      // When it's visible but doesn't currently apply (a one-time
      // skill goal on LEVEL) it still renders -- see targetModeVisible
      // vs. targetModeApplies' own comments for why -- just with
      // .gt-target-mode-toggle--disabled added (dims it via CSS and
      // turns off pointer-events, see goal-tracking.css) and no click
      // handler wired up at all, rather than one that would silently
      // no-op. Neither button gets .active while disabled either (see
      // the applies && below) -- GAIN/REACH isn't a real choice yet on
      // LEVEL, so nothing should read as chosen; both just show the
      // plain gray-bordered look .gt-target-mode-btn already has at
      // rest. GT.targetMode itself gets reset to 'gain' -- see the
      // metric toggle's own click handler above, right where LEVEL
      // switches to XP -- so GAIN is always what a player finds
      // selected the moment this toggle becomes usable again, rather
      // than whatever it happened to be left on before.
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
            // Reinforces the new choice right in the target field's own
            // placeholder ("Kc to gain" <-> "Target kc") -- same
            // in-place update the Lvl/Xp toggle's own click handler
            // already does for the same field, for the same reason.
            updateWizardTargetField();
          });
        });
        updateWizardSegRowVisibility();
      }

      // #gtWizardSegRow (stage 3's Lvl/Xp + GAIN/REACH row -- see
      // wizardStageTargetHtml) always renders, same always-present-
      // empty-wrapper idea #gtTargetModeField itself already uses, so
      // this is what actually collapses the whole row out of the
      // stage's flex flow (rather than leaving an empty gap where it
      // would have been) once neither toggle applies -- an item goal,
      // or a skill goal currently on Lvl. .gt-wizard-segrow:empty alone
      // can't do this the way #gtTargetModeField:empty does, since the
      // row still has #gtTargetModeField itself sitting inside it as a
      // child even when THAT'S empty -- checking for any real toggle
      // markup, rather than relying on the row having zero children, is
      // what a plain CSS :empty selector can't express here. Called
      // from wireTargetModeToggle every time it runs, since that's the
      // one place both this row's possible contents (the Lvl/Xp toggle
      // is fixed for the stage; GAIN/REACH is the only part that can
      // change without a full re-render) get touched.
      function updateWizardSegRowVisibility() {
        var segRow = document.getElementById('gtWizardSegRow');
        if (!segRow) return;
        var hasContent = !!segRow.querySelector('.gt-metric-toggle, .gt-target-mode-toggle');
        segRow.classList.toggle('gt-wizard-segrow--empty', !hasContent);
      }

      // Recurring only -- HOUR/DAY/WEEK/MONTH/YEAR, in the same order
      // app.goals.RECUR_UNITS lists them server-side (that's what
      // actually validates recur_unit; this is purely display order).
      var RECUR_UNIT_OPTIONS = [
        { unit: 'hour', label: 'Hour' },
        { unit: 'day', label: 'Day' },
        { unit: 'week', label: 'Week' },
        { unit: 'month', label: 'Month' },
        { unit: 'year', label: 'Year' },
      ];
      // Mirrors app.goals.MAX_RECUR_INTERVAL -- server re-validates
      // against its own copy regardless (see validateRecurField).
      var MAX_RECUR_INTERVAL = 999;

      // "Every x days", "Every x weeks", etc -- doubles as this field's
      // only label, same "placeholder text does the labeling" pattern
      // wizardTargetPlaceholder already uses on stage 3. Reads off
      // RECUR_UNIT_OPTIONS' own label (its singular, capitalized
      // display form) rather than a second lookup table, since a plain
      // lowercase + "s" is already exactly the word this needs.
      function recurIntervalPlaceholder() {
        var opt = RECUR_UNIT_OPTIONS.filter(function (o) { return o.unit === GT.recurUnit; })[0];
        var unitWord = opt ? opt.label.toLowerCase() : 'day';
        return 'Every x ' + unitWord + 's';
      }

      // Stage 4 -- recurring goals only, reached from stage 3's own
      // Next button. Same fixed-size box (.gt-wizard-stage2, reused
      // rather than a fourth near-identical class) as stages 2/3, and
      // now the same three-row shape stage 3 uses too: the interval
      // field alone up top, its own HOUR/DAY/WEEK/MONTH/YEAR toggle on
      // a row of its own underneath (reusing .gt-wizard-segrow -- see
      // that class's own comment in goal-tracking.css -- rather than a
      // page-4-only class, since it's the same "this stage's segmented
      // control(s) get a row of their own" idea stage 3's Lvl/Xp/GAIN-
      // REACH row already established), then Back/Cancel/Save pinned
      // to the bottom. Unlike stage 3's own segmented-control row, this
      // one's never empty -- a recurring goal always has a unit to
      // pick -- so there's no visibility toggling to wire up here.
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
          '    <button type="button" class="gt-add-btn" id="gtWizardSave">Save</button>' +
          '  </div>' +
          '</div>';
      }

      // A skill's search list is its lowercase key (SKILL_NAMES_LIST),
      // title-cased only for display/matching here -- a boss's search
      // list (BOSS_NAMES) is already the exact display name, so this is
      // a no-op for kc.
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

        // No longer resets wizardTarget here -- this stage's own DOM
        // gets fully torn down and rebuilt by renderWizard on EVERY
        // visit, including backing out of stage 4 straight back into
        // this one (see wizardBack), so resetting unconditionally
        // right here was wiping out whatever was already picked/typed
        // the moment a player backed out of the cadence stage to
        // change it -- the search box and target field came back
        // empty even though wizardTarget itself (per wizardBack's own
        // comment) was never meant to be touched by that trip.
        // wizardPickType is the one real "start fresh" moment now (see
        // its own comment), so this just restores whatever's already
        // in wizardTarget instead, which is a no-op the very first
        // time (it's still the empty object wizardPickType just set).
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

        // Delegated (rather than re-bound per suggestion row) since
        // suggestions.innerHTML gets replaced on every keystroke --
        // binding per-row would mean re-binding constantly for no gain.
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
                // Carries whatever number's already in the field across
                // the switch (5,750 xp becomes level 22, and back
                // again) via xpForLevel/levelForXp, rather than leaving
                // a now-wrong-unit number sitting in the box for the
                // player to redo by hand -- same behavior as Mindmaps'
                // own skill-goal metric toggle.
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
                // Switching onto XP is what makes GAIN/REACH go from
                // disabled to actually usable (see targetModeApplies) --
                // GAIN is this toggle's own default (see GT.targetMode's
                // declaration above for why), so resetting it here is
                // what guarantees GAIN is always what a player finds
                // selected the moment it becomes usable again, rather
                // than whatever REACH/GAIN choice happened to be sitting
                // there from a previous visit to XP. Only on the LEVEL
                // -> XP direction -- switching XP -> LEVEL disables the
                // toggle (see wireTargetModeToggle) without touching
                // GT.targetMode at all, since there's no "becomes usable"
                // moment on that side to reset for.
                if (newMetric === 'xp') GT.targetMode = 'gain';
                GT.skillMetric = newMetric;
              }
              document.querySelectorAll('.gt-metric-btn').forEach(function (b) {
                b.classList.toggle('active', b === btn);
              });
              // Lvl<->Xp is the one thing that can change
              // targetModeApplies()'s own answer without leaving stage
              // 3 -- xp offers GAIN/REACH, level doesn't -- so this is
              // what keeps #gtTargetModeField in sync with whichever
              // one's now active, same as updateWizardTargetField just
              // below keeps the target field's own placeholder in sync.
              wireTargetModeToggle();
              updateWizardTargetField();
              validateTargetField();
            });
          });
        }

        var targetInput = document.getElementById('gtTargetValue');
        // Restores whatever number was already captured into
        // wizardTarget.value the last time Next was pressed from this
        // same stage (see the Next/Save handler just below) -- null
        // the very first time a fresh wizardTarget reaches here (see
        // wizardPickType), same as searchInput.value's own restore
        // just above.
        if (wizardTarget.value != null) targetInput.value = String(wizardTarget.value);
        targetInput.addEventListener('input', function () {
          filterNumericSuffixInput(targetInput);
          validateTargetField();
        });

        wireTargetModeToggle();
        updateWizardTargetField();
        // One-time saves straight from here, same as this button
        // always has; recurring instead captures the name/value picked
        // on this stage into wizardTarget (stage 4 replaces this
        // stage's own DOM, including #gtTargetValue, so wizardAddGoal
        // can't re-read it live by the time IT runs) and moves on to
        // stage 4 to pick the cadence -- see wizardStageTargetHtml's
        // own Save/Next label switch just above.
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
          // Digits only -- there's no k/m/b shorthand or decimal point
          // to allow here the way the target-value field's own
          // filterNumericSuffixInput does, this is just a plain "how
          // many" count.
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
            // Updated in place rather than via a full renderWizard() --
            // that would also blow away whatever's already typed in
            // this same field (GT.recurInterval only gets read back
            // into the input's own value attribute on render, not
            // synced live), so this only ever touches the placeholder.
            intervalInput.placeholder = recurIntervalPlaceholder();
          });
        });

        document.getElementById('gtWizardSave').addEventListener('click', wizardAddGoal);
      }

      // Same shape as validateTargetField above, just against the
      // cadence field's own 1..MAX_RECUR_INTERVAL range instead of a
      // goal-type-dependent one, and the same showEmptyAsInvalid
      // quiet-while-typing/loud-at-save split.
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

      function currentTargetBounds() {
        if (GT.type === 'kc') return TARGET_BOUNDS.kc;
        if (GT.type === 'skill') return (GT.skillMetric === 'xp') ? TARGET_BOUNDS.skill_xp : TARGET_BOUNDS.skill_level;
        return TARGET_BOUNDS.item;
      }

      function updateWizardTargetField() {
        document.getElementById('gtTargetValue').placeholder = wizardTargetPlaceholder();
      }

      // Live, as-you-type range check for the target field -- mirrors
      // Mindmaps' own validateSkillTarget, generalized to all three
      // goal types via currentTargetBounds (the server re-validates
      // against its own copy of these bounds regardless). Resolves
      // through parseMoneySuffix first so a still-being-typed "150k"
      // doesn't flash an out-of-range error before it's finished.
      //
      // Site-wide standard: invalid just means a red border on the
      // field, no message anywhere. An empty field is a special case --
      // while the person is still typing (live 'input' calls, below)
      // it should stay neutral rather than flash red the instant the
      // box is cleared, but Save clicking through an empty field should
      // still show something's wrong. showEmptyAsInvalid (defaulted off
      // for the live-typing call sites) is what tells the two cases
      // apart; the Save handler below is the one call site that passes
      // true. Returns whether the field is currently valid either way,
      // so wizardAddGoal/the Save handler can reuse it as their own
      // save-time check rather than duplicating the range logic.
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

      // The name/target-value fields validated and captured back on
      // stage 3 (wizardTarget.name/value -- see that stage's own
      // Save/Next click handler in wireWizardStage) are already good
      // by the time this runs, whether it's called straight from
      // there (one-time) or from stage 4's own Save button afterward
      // (recurring) -- this only still needs to validate/collect the
      // cadence field for the recurring case.
      async function wizardAddGoal() {
        var payload = { goal_type: GT.type, target_name: wizardTarget.name, target_value: wizardTarget.value };
        if (GT.type === 'skill') { payload.metric = GT.skillMetric; }
        if (GT.type === 'item' && wizardTarget.itemId) { payload.item_id = wizardTarget.itemId; }
        if (GT.recurring === 'recurring') {
          if (!validateRecurField(true)) return;
          payload.is_recurring = true;
          payload.recur_interval = Number(document.getElementById('gtRecurInterval').value.trim());
          payload.recur_unit = GT.recurUnit;
        } else if (targetModeApplies()) {
          // Sent explicitly (both "gain" and "reach") whenever the
          // toggle's actually offered, rather than leaning on the
          // server's own omitted-field default -- see
          // GoalCreateRequest.target_mode's own docstring in
          // app/schemas.py for why that default exists at all (it's for
          // a raw API call that never knew to send this, not for this
          // wizard, which always knows).
          payload.target_mode = GT.targetMode;
        }

        var data = await apiCall('/api/goals', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
        if (!data) return;
        GT.goals.push(data);
        renderGoalList();
        closeWizard();
      }

      // ---- Goal list ----------------------------------------------------

      function goalName(g) {
        if (g.goal_type === 'skill') return g.target_name.charAt(0).toUpperCase() + g.target_name.slice(1);
        return g.target_name;
      }

      // Replaces the old static "Boss kill count"/"Level"/etc. subtitle
      // with the live current/target progress itself, in the goal's own
      // unit: "LVL" prefixed for a level goal, "XP"/"KC" suffixed for an
      // xp/kc goal, no unit at all for an item goal (its quantity speaks
      // for itself). This is also the only place that progress reads
      // now -- see goalRowHtml below, which no longer has its own
      // separate current/target column. A recurring goal's own cadence
      // (see recurCadenceLabel) tags along on the same line rather than
      // growing the row a whole new one -- g.current_value is already
      // this PERIOD's progress, not a lifetime total, for a recurring
      // goal (see app.goals.current_value), so the number above reads
      // correctly either way without this function needing to know or
      // care which kind of goal it's showing. goalInfoIconHtml tags
      // along too whenever it has something to show -- right after the
      // cadence text for a recurring goal (same as before), or straight
      // after the plain progress number for a one-time GAIN goal, which
      // has no cadence text of its own to follow.
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

      // "EVERY WEEK" for an interval of 1, "EVERY 2 WEEKS" otherwise --
      // RECUR_UNIT_OPTIONS' own labels pluralized rather than a second
      // lookup table, since they're already exactly the singular noun
      // this needs. Empty string (not shown) for a non-recurring goal.
      // Written already-uppercase to match every other unit suffix
      // goalProgressLabel builds (KC/XP/LVL), though .gt-goal-sub's own
      // text-transform: uppercase would render it that way regardless.
      var RECUR_UNIT_LABEL = { hour: 'HOUR', day: 'DAY', week: 'WEEK', month: 'MONTH', year: 'YEAR' };
      function recurCadenceLabel(g) {
        if (!g.is_recurring) return '';
        var unit = RECUR_UNIT_LABEL[g.recur_unit] || String(g.recur_unit || '').toUpperCase();
        if (g.recur_interval === 1) return 'EVERY ' + unit;
        return 'EVERY ' + fmtNum(g.recur_interval) + ' ' + unit + 'S';
      }

      // Mirrors app.goals._RECUR_UNIT_SECONDS exactly (see its own
      // comment in app/goals.py) -- same fixed-duration, non-calendar-
      // exact convention (a "month" is always 30 days, a "year" always
      // 365), so a recurring goal's own next-cycle countdown lands on
      // the same instant server and client agree the current period
      // actually ends.
      var RECUR_UNIT_SECONDS = { hour: 3600, day: 86400, week: 7 * 86400, month: 30 * 86400, year: 365 * 86400 };

      function pad2(n) { return String(n).padStart(2, '0'); }

      // "YYYY-MM-DD HH:MM" in the VIEWER's own local time (not UTC) --
      // g's own recur_period_start arrives as a plain ISO timestamp,
      // which `new Date(...)` already parses correctly either way, so
      // this only has to control how it's READ back out.
      function fmtIsoDateTimeLocal(iso) {
        var d = new Date(iso);
        return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) +
          ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
      }

      // Plain (not zero-padded) unit/letter pairs -- Year, Month, Week,
      // Day, Hour, Minute -- each just the remainder left after peeling
      // off every larger unit first (the same "greedy decomposition"
      // any digital-clock countdown uses), using RECUR_UNIT_SECONDS'
      // own fixed-duration units throughout so this never disagrees
      // with goalInfoIconHtml's own end-of-period math below. A unit
      // that's 0 is left out entirely (a goal with weeks left has no
      // use for "0Y 0M" in front of it), except when every single one
      // is -- an about-to-roll goal still gets a "0M" rather than an
      // empty string. Negative input (a period that's already
      // technically over -- the 5s poll just hasn't caught the
      // rollover yet) clamps to all-zeros (and so to that same "0M"
      // floor) rather than printing a negative countdown. No pad2 here
      // (unlike fmtIsoDateTimeLocal's own date/time digits) -- this
      // reads as a duration, not a fixed-width clock face, so "3H" is
      // correct and "03H" would just be a stray leading zero; a
      // two-digit value like 10H still prints in full either way,
      // since there's no padding to strip in the first place.
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

      // The little hoverable "i" that follows either a recurring goal's
      // own cadence tag (e.g. "EVERY 2 WEEKS") or a one-time GAIN-mode
      // goal's plain progress number -- native title="..." is this
      // whole codebase's only tooltip mechanism (see e.g. the "Hovering
      // a bar..." comment in loot-tracker.css; there's no custom
      // tooltip component anywhere to build one from), so this is a
      // plain title attribute, not a floating element of its own. Two
      // different tooltips depending on which kind of goal this is:
      //   recurring    -- "Set on [period start] · Next cycle in
      //     [countdown]" -- g.recur_period_start is the CURRENT
      //     period's own start (see GoalOut's own docstring in
      //     app/schemas.py), which is what both halves actually
      //     describe -- when this period began, and how much of it is
      //     left -- so recur_period_start plus recur_interval/
      //     recur_unit is all this branch needs.
      //   one-time GAIN -- just "Started at [baseline] [UNIT]" -- no
      //     "Set on [date]" half here (unlike the recurring branch
      //     above): a one-time goal has only the one baseline, ever,
      //     so pairing it with its own creation date added nothing a
      //     player couldn't already tell from the goal card itself,
      //     where "Started at" alone is what actually answers "why
      //     does progress not start at 0". g.baseline_value is
      //     captured once at creation and never re-baselined (there's
      //     no period to roll forward -- see Goal.baseline_value's own
      //     docstring in app/models.py) and is only ever non-null for
      //     a kc goal or an xp-metric skill goal (see
      //     app.goals.target_mode_allows_gain -- a level goal/item
      //     goal never get a baseline captured at all), so the unit
      //     branch below only needs to cover those two.
      // Neither branch fires (returns '') for a REACH-mode one-time
      // goal or an item goal -- both read as a plain lifetime total
      // already, nothing to add.
      function goalInfoIconHtml(g) {
        var tooltip = null;
        if (g.is_recurring && g.recur_period_start) {
          var unitSeconds = RECUR_UNIT_SECONDS[g.recur_unit];
          if (unitSeconds) {
            var periodStartMs = new Date(g.recur_period_start).getTime();
            var periodEndMs = periodStartMs + g.recur_interval * unitSeconds * 1000;
            var remainingSeconds = (periodEndMs - Date.now()) / 1000;
            tooltip = 'Set on ' + fmtIsoDateTimeLocal(g.recur_period_start) + ' · Next cycle in ' + fmtRecurCountdown(remainingSeconds);
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

      // A kc goal's icon is its real boss sprite (app/static/boss-icons,
      // same assets the old boss-table page used) and a skill goal's is
      // its real skill sprite (app/static/skill-icons, sourced from the
      // OSRS Wiki's own icon set) -- BOSS_SLUG_BY_NAME is injected above
      // from app.bosses.HISCORE_BOSSES, and a skill goal's target_name
      // is already the lowercase skill key the filename itself uses
      // (see SKILL_NAMES_LIST above). An item goal's icon is g.item_icon
      // (the real RuneLite-CDN icon for whichever search suggestion the
      // player picked -- see GoalOut.item_icon/Goal.item_id's own
      // docstring in app/models.py) when one was captured. Falls back to
      // the generic TYPE_ICON badge for a boss name somehow missing from
      // BOSS_SLUG_BY_NAME (shouldn't happen -- the wizard's own boss
      // search only ever offers names from that same list) and for any
      // item goal with no item_icon (free-typed text that never matched
      // a search result, or a goal predating this column) -- a
      // missing/broken <img> would look far worse than the plain badge
      // either fallback replaces.
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

      // The delete button starts as a plain trash icon; its first click
      // (wired via the delegated click listener on #gtGoalList below,
      // not here -- this only renders markup) just swaps it to an
      // "Are you sure?" confirm state via the gt-goal-delete--confirm
      // class rather than deleting anything, and only a second click
      // while in that state actually calls deleteGoal.
      //
      // customMode (only true when GT.sortMode === 'custom', see
      // renderGoalList) adds the same draggable/data-goal-id plumbing
      // Purchase Goals' own "still to purchase" rows carry in ITS
      // custom mode (see renderSummaryList/wireSummaryDrag) -- the
      // whole row becomes the drag surface, with draggable="false" on
      // the icon so starting a drag over it grabs the row underneath
      // instead of the browser's own native image drag.
      function goalRowHtml(g, customMode) {
        // g.progress_pct, not current_value/target_value divided here
        // -- for most goals that's the same ratio either way, but a
        // LEVEL-metric skill goal's current_value/target_value are
        // both plain level numbers, and OSRS's xp-per-level curve is
        // exponential (level 20 isn't "halfway" to level 40 in actual
        // playtime), so dividing those directly would fill the bar at
        // the wrong pace. progress_pct is already computed server-side
        // in xp for that case (see app.goals.progress_pct), and is
        // just the plain current/target ratio for every other goal
        // type, so this can read it the same way regardless of type.
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
          '  <button type="button" class="gt-goal-delete" data-goal-id="' + g.id + '" title="Delete goal" aria-label="Delete goal">' +
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

      // Powers #gtSortTabs (see the body's own markup and GT.sortMode).
      // Never mutates the list it's given -- same "always sort a copy"
      // convention Loot Tracker's own sortEntries already follows, so
      // GT.goals itself stays in whatever order loadGoals last received
      // it in. See GOAL_SORT_MODES in app/schemas.py for the
      // server-side twin of this same mode list.
      //   'progress_desc'/'progress_asc' -- closest/furthest from done
      //     (progress_pct, already computed server-side in xp for a
      //     level-metric skill goal -- see app.goals.progress_pct -- so
      //     this reads correctly for every goal type without needing to
      //     know which one it is).
      //   'type_asc'/'type_desc' -- kc/skill/item, grouped in
      //     GOAL_TYPE_SORT_ORDER's order (or reversed), alphabetical by
      //     name within each group either way.
      //   'alphabetical'/'reverse_alphabetical' -- A-Z / Z-A by name,
      //     case-insensitive. 'alphabetical' was this list's only order
      //     before sorting existed, and still is the account-side
      //     default for one that's never changed it.
      //   'recent'/'oldest' -- newest-created first / oldest-created
      //     first.
      //   'custom' -- the player's own drag-and-drop order
      //     (g.sort_order, see GoalOut's own docstring in
      //     app/schemas.py) -- a goal that's never been dragged has a
      //     null sort_order, which sorts after every goal that HAS one,
      //     tied among themselves by created_at (oldest first) so a
      //     freshly added goal lands at the end of a custom order
      //     instead of jumping in at some arbitrary spot.
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

      // Toggles which #gtSortTabs button looks active -- same pattern
      // Loot Tracker's own updateSortTabs already uses for its two
      // sort-tab rows, just the one container here.
      function updateSortTabs() {
        document.querySelectorAll('#gtSortTabs .gt-sort-tab').forEach(function (b) {
          b.classList.toggle('active', b.getAttribute('data-sort') === GT.sortMode);
        });
      }

      // Shared by loadGoals/setGoalSortMode/commitGoalOrder below --
      // all three hit an endpoint that returns the exact same
      // GoalsResponse shape (goals + the account's own persisted
      // sort_mode), so all three apply it to GT and re-render the same
      // way rather than each repeating the same four lines.
      function applyGoalsResponse(data) {
        GT.goals = data.goals || [];
        GT.sortMode = data.sort_mode || GT.sortMode;
        updateSortTabs();
        renderGoalList();
      }

      // Rows are only draggable in "custom" sort mode -- dragging one
      // in any other mode would just get computed right back out from
      // under you on the next poll, since every other mode is always
      // re-sorted by its own live field rather than remembered.
      //
      // Skips its own rebuild entirely when GT.sortMode + GT.goals are
      // byte-for-byte the same as what's already on screen (GT.
      // renderKey, set at the bottom of a real rebuild) -- loadGoals'
      // own 5-second poll (see below) calls applyGoalsResponse ->
      // renderGoalList on every single tick regardless of whether
      // anything actually changed, and listEl.innerHTML = ... always
      // used to tear down and recreate every row's <img> from scratch
      // even when it was about to render pixel-identical markup, which
      // is what was actually causing the reported flicker -- a
      // perfectly cached, same-URL <img> still repaints from nothing
      // for a frame when its element is destroyed and recreated,
      // whether or not the browser has to touch the network for it.
      // Same reasoning applies to the interactive landing preview,
      // which reuses this exact function unmodified (see
      // render_landing_goal_tracking_preview's own docstring in
      // app/pages.py) -- its own DEMO_GOALS answer GET /api/goals with
      // literally the same array every 5 seconds, so this was the
      // worst-case version of the same bug: 100% of its polls were
      // pure no-op rebuilds. A real, currently-changing goal (recurring
      // kc/xp ticking up from active hiscores) still renders normally
      // -- its own JSON differs tick to tick, so its renderKey misses
      // and the rebuild goes ahead exactly as before. The one thing
      // that goes stale while a poll's rebuild is skipped is the
      // recur-countdown tooltip text baked into goalInfoIconHtml's own
      // title attribute (computed from Date.now() at render time, not
      // from anything in the response) -- minute-granularity, hover-
      // only, and it catches back up the moment the underlying goal
      // data next actually changes, so this was judged not worth
      // keeping the flicker for.
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
        wireGoalDrag(customMode);
      }

      // Persists which #gtSortTabs button is active (GameAccount.
      // goal_sort_mode), remembered across refreshes/sessions -- same
      // "PUT it, then apply whatever the response says" shape
      // setStillToPurchaseSort already uses for Purchase Goals' own
      // sort tabs, rather than updating GT.sortMode optimistically
      // before the request resolves.
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
        var mode = btn.getAttribute('data-sort');
        if (mode === GT.sortMode) return;
        setGoalSortMode(mode);
      });
      updateSortTabs();

      // Delegated on the list container itself (not per-button, since
      // renderGoalList rebuilds the whole list's innerHTML every poll --
      // a container-level listener survives that; per-button ones
      // wouldn't need rewiring either way, but this is simpler and it's
      // the same delegation pattern already used elsewhere on this
      // page). First click on a delete button just arms it (shows "Are
      // you sure?"); a second click while armed actually deletes.
      // Clicking anywhere else disarms whatever button was armed, and
      // a click on a different delete button disarms the previous one
      // too, so only one row is ever mid-confirm at a time.
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
        renderGoalList();
      }

      // Nudges the CUSTOM sort tab, the same way Purchase Goals' own
      // glowCustomSortButton nudges its own Custom button when a
      // "still to purchase" row is clicked/dragged outside Custom mode
      // -- a goal row only accepts a drag at all in "custom" sort mode
      // (see wireGoalDrag below); in any other mode that gesture
      // currently does nothing on its own, so this points at the
      // control that would actually let it do something. Same
      // remove-class/reflow/add-class dance as its Purchase Goals
      // original, so a second attempt mid-glow restarts the pulse
      // instead of being ignored because the class was already there.
      function glowCustomSortTab() {
        var btn = document.querySelector('#gtSortTabs .gt-sort-tab[data-sort="custom"]');
        if (!btn) return;
        btn.classList.remove('glow');
        void btn.offsetWidth;
        btn.classList.add('glow');
      }

      // Drag-and-drop reordering for "custom" sort mode -- same
      // dragstart/dragover/drop/dragend shape (and the same FLIP-style
      // animateReorder live preview) as Purchase Goals' own
      // wireSummaryDrag for its "still to purchase" list, just keyed by
      // g.id (data-goal-id) instead of a {slotType, slot} pair.
      // draggedEl/dropped are scoped to this one call, which is fine
      // since renderGoalList rebuilds every row's markup (and rewires
      // this) from scratch every render.
      function wireGoalDrag(customMode) {
        var listEl = document.getElementById('gtGoalList');
        if (!customMode) {
          // Rows outside Custom mode carry no draggable attribute at
          // all (see goalRowHtml), so a native HTML5 drag can never
          // actually start on one -- the only gesture that can ever
          // reach a row here is a plain press. pointerdown (not click)
          // to match glowCustomSortTab's own trigger, and so this
          // fires the instant a drag is attempted too, not only on a
          // completed click.
          //
          // Bails out for a pointerdown that started on the row's own
          // .gt-goal-delete button -- both its plain trash-icon state
          // and its armed "Are you sure?" confirm state are the same
          // element (see .gt-goal-delete--confirm above), so this one
          // check covers pressing either. Without it, a press meant to
          // delete a goal was bubbling straight up to this listener
          // and glowing the CUSTOM tab right along with it, which
          // reads as "you can only delete goals in Custom mode" --
          // untrue and not what a delete press is even about. Only a
          // press on the row itself, outside that button, is what
          // should ever point someone at Custom mode.
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

        // The live preview above already leaves the DOM in exactly the
        // order a drop should save -- no separate source/target diffing
        // needed, just read the rows back out in their current order.
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
            // A drag that ends without a drop (dropped outside the
            // list, or cancelled with Escape) leaves the live-preview
            // DOM order sitting there with nothing saved server-side to
            // back it up -- a plain re-render from the untouched
            // GT.goals state snaps it straight back to the last real
            // order.
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

      // ---- Load + poll (same 5s cadence as PG.pollTimer/loadSummary,
      // render_purchase_goals/render_possessions) -- one endpoint
      // serves both the initial paint and every refresh after it. -----

      async function loadGoals() {
        var data = await apiCall('/api/goals');
        if (!data) return;
        applyGoalsResponse(data);
      }

      loadGoals();
      setInterval(loadGoals, 5000);
    })();
    """
    )
    return extra_head, body, script


def render_landing_goal_tracking_preview() -> Optional[Tuple[str, str, str]]:
    """The landing page's own interactive Goal Tracking preview -- same
    reuse-the-real-script pattern as the other four (reuses
    _goal_tracking_panel_markup's body/script completely unmodified,
    layering demo-only behavior on top from the outside in a wrapper
    script), backed by one real, curated snapshot: app/data/
    landing_goal_tracking_demo.json is a one-time GET /api/goals pull
    of the account's own real current goals -- every goal exactly as
    the real page would show it -- with two numbers nudged by hand
    afterward (see _get_landing_goal_tracking_demo_data's own comment
    for exactly which and why) so the demo has a goal that's neither
    empty nor already complete to show off a progress bar with.
    Returns (extra_head, body, script) for render_landing to splice
    into its own markup, same as the other four, or None if the
    snapshot isn't there to read.

    Sort tabs and custom-mode drag-reorder genuinely work here, the
    same as the real page. Two pieces of the reused markup are
    deliberately NOT offered, both disabled by this preview's own CSS
    rather than by touching the reused markup/script themselves:

    - The add-goal wizard -- #gtWizard (the "Add goal" button, and the
      wizard itself once expanded) is hidden outright
      (.landing-goal-tracking-preview #gtWizard in goal-tracking.css):
      a new goal's starting progress comes from the player's actual
      live boss/skill/item totals (see create_goal's own
      build_progress_context call in app/main.py), which this demo
      has no real account behind it to supply, so every path through
      that wizard was always going to end in Save silently going
      nowhere -- better to lead with what this demo actually delivers
      than dangle a button that can't. Hiding it (rather than
      stripping it from the markup) also closes up the gap its own
      margin used to leave, so the goal list sits flush under the
      hero row instead.
    - Each row's own delete button -- .gt-goal-delete is left fully
      visible and hoverable (still the same trash icon, same position,
      still lights up red on hover exactly like the real page -- see
      this preview's own capture-phase click interceptor further down,
      NOT pointer-events: none any more, which used to suppress that
      hover along with everything else) but made inert: unlike the
      wizard, delete actually WORKS against this demo's own in-memory
      snapshot (see the fetch shim below), so this isn't about
      papering over something broken -- it's simply not something a
      passerby idly clicking around a marketing page should be able to
      do to goals that read as "yours." A click on the icon itself
      never reaches the reused script's own delegated listener (see
      the capture-phase interceptor below), so it can never arm or
      confirm the delete; a click anywhere else on the row -- selecting
      it, starting a custom-mode drag (see wireGoalDrag's own
      pointerdown listener/glowCustomSortTab in
      _goal_tracking_panel_markup's script) -- is completely untouched.

    1. A `fetch` shim, scoped to just this wrapper, that:
       - Answers GET /api/goals out of DEMO_GOALS/DEMO_SORT_MODE --
         plain, directly-mutated in-memory state, not a frozen replay
         of the snapshot's own original values -- so a delete, a
         sort-tab change, or a custom-mode drag survives the real
         page's own 5-second poll (loadGoals re-fetches and replaces
         GT.goals wholesale on every tick -- see
         _goal_tracking_panel_markup's own docstring) instead of
         silently reverting a few seconds later.
       - Implements PUT /api/goals/sort-mode and PUT /api/goals/reorder
         against that same state, both returning the real endpoints'
         own {goals, sort_mode} shape (reorder also switches
         DEMO_SORT_MODE to "custom" itself, same as the real one does
         server-side -- see set_goal_order's own docstring in
         app/main.py).
       - Implements DELETE /api/goals/{id} against DEMO_GOALS for
         real -- unreachable in practice now that this preview's own
         capture-phase click interceptor (below the reused script)
         stops a click on .gt-goal-delete from ever reaching the
         row-level click delegation the reused script wires up
         (document.getElementById('gtGoalList')'s own listener), so it
         can never arm or confirm a delete to begin with. Left in
         rather than pulled out, same reasoning as the two below.
       - GET /api/items/search?q=... (off the same curated, 176-item
         pool Mindmaps' own preview already bundles -- see
         _get_landing_mindmap_search_pools_data) and POST /api/goals
         (the wizard's own Save, gracefully failing) are both now
         unreachable in practice with #gtWizard hidden -- kept here
         rather than pulled out, same as DEMO_ITEMS_POOL/
         localSearchItems below, since they're harmless dead code and
         this shim staying a complete, faithful stand-in for every
         request the reused script could ever issue is worth more than
         trimming a path CSS happens to make unreachable today.
       - Anything else (including that unreachable POST /api/goals)
         gets the same graceful "Not available in this preview"
         failure the reused script's own apiCall already shows through
         #gtError for any failed request -- were #gtWizard ever
         unhidden again, the wizard would stay open rather than losing
         whatever was typed, same as the other previews' own
         catch-alls.
    2. No localStorage shadowing needed here -- this page's own script
       never reads or writes it.
    3. Same bottom-edge feather as the other four previews.

    The 5-second poll (setInterval(loadGoals, 5000), inside the reused
    script itself) is left running rather than neutralized, same
    reasoning as the other previews' own polls.
    """
    demo = _get_landing_goal_tracking_demo_data()
    if demo is None:
        return None
    search_pools = _get_landing_mindmap_search_pools_data()
    items_pool = (search_pools or {}).get("items") or []
    extra_head, body, script = _goal_tracking_panel_markup()

    # Landing-preview-only hero row -- tagline's own wrap FIRST this
    # time, character SECOND (so he lands on the RIGHT, per this
    # preview's own explicit "put him on the right, with the text on
    # the left" request) -- same flex row/bottom-align treatment as
    # the other four previews' own hero rows, just under this
    # preview's own class names since its markup/CSS are Goal
    # Tracking's, not any other page's. This is the same left-to-right
    # order Loot Tracker's and Mindmaps' own hero rows already use
    # (see .loot-preview-hero/.mindmap-preview-hero's own markup) --
    # Purchase Goals and Storages Viewer are the two that put the
    # character first instead, per THEIR own explicit requests. The
    # reused body's own "Goal Tracking" <h2> is hidden via CSS
    # (.landing-goal-tracking-preview .page-title), same as the other
    # four.
    hero_markup = """
    <div class="gt-preview-hero">
      <div class="gt-preview-tagline-wrap">
        <p class="gt-preview-tagline">
          <span class="gt-preview-tagline-gold">GOAL TRACKING</span> <span class="gt-preview-tagline-white">for those days when you need some dopamine.</span>
        </p>
      </div>
      <picture class="gt-preview-char">
        <source srcset="/static/img/landing-goal-tracking-preview-char.webp" type="image/webp">
        <img src="/static/img/landing-goal-tracking-preview-char.png" alt="" />
      </picture>
    </div>
    """
    body = hero_markup + body

    goals_json = json.dumps(demo.get("goals") or [])
    sort_mode_json = json.dumps(demo.get("sort_mode") or "alphabetical")
    items_pool_json = json.dumps(items_pool)
    wrapper_script = f"""
    (function () {{
      // The captured, hand-nudged snapshot itself (see
      // _get_landing_goal_tracking_demo_data's own comment) -- a plain
      // array of goals, each already shaped exactly like the real GET
      // /api/goals response's own `goals` entries. Directly mutated
      // (not re-derived) by the delete/sort-mode/reorder handlers
      // below, so GET always answers with whatever this visitor has
      // actually done so far.
      var DEMO_GOALS = {goals_json};
      var DEMO_SORT_MODE = {sort_mode_json};
      // Same curated item pool Mindmaps' own preview bundles -- see
      // this function's own docstring.
      var DEMO_ITEMS_POOL = {items_pool_json};
      var ITEM_ICON_CDN_BASE = 'https://static.runelite.net/cache/item/icon/';

      // Same startswith-then-contains ranking localSearchItems already
      // uses inside Mindmaps' own preview wrapper, ported here rather
      // than shared -- each preview's wrapper is self-contained, same
      // as the rest of this pattern.
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

      // ---- fetch shim -----------------------------------------------------
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

        // The add-goal wizard's own Save (POST /api/goals) -- and
        // anything else this script doesn't otherwise call. Graceful
        // failure, never the real network -- see this function's own
        // docstring for why creating a goal specifically isn't
        // supported here.
        return fail('Not available in this preview.');
      }};

      {script}

      // Neutralizes each row's own delete button -- runs after the
      // reused script above has already wired its own delegated click
      // listener on #gtGoalList (see goalRowHtml/that listener in
      // _goal_tracking_panel_markup's script), so rather than stopping
      // .gt-goal-delete from being clicked at all (pointer-events:
      // none, this preview's first pass at this -- see this function's
      // own docstring), this instead lets it be clicked, hovered, AND
      // focused completely normally, right up until the delegated
      // listener would actually see it: a CAPTURING-phase listener on
      // the same #gtGoalList element fires on the way down, before the
      // event ever reaches the button and bubbles back up to that
      // reused bubble-phase listener, so calling stopPropagation here
      // halts the whole dispatch and the reused listener never runs at
      // all -- never arming the "Are you sure?" confirm state, never
      // calling deleteGoal. Scoped to just .gt-goal-delete (via
      // e.target.closest, same check the reused listener itself uses)
      // so a click anywhere else on the row -- selecting it, starting
      // a custom-mode drag -- passes through completely untouched.
      document.getElementById('gtGoalList').addEventListener('click', function (e) {{
        if (e.target.closest('.gt-goal-delete')) e.stopPropagation();
      }}, true);

      // Same fixed-height container + always-on bottom-edge feather as
      // the other four previews -- see .landing-goal-tracking-preview
      // in goal-tracking.css, and render_landing_loot_preview's own
      // wrapper script for the fuller comment this mirrors. No JS
      // needed here any more either, for the same reason.
    }})();
    """
    return extra_head, body, wrapper_script


def render_goal_tracking(player: PlayerView) -> str:
    """The Goal Tracking page -- a plain, player-built list of targets
    (a boss kill count, a skill level/xp, or an item quantity), each
    tracked toward completion with live progress that's always already
    current by the time this renders (no stale "as of my last visit"
    numbers). Superseded the old 71-boss reference table this page used
    to be (see git history) once app/goals.py's own CRUD endpoints
    existed to build a real goal-creation form against instead.

    Deliberately NOT server-rendered with the player's actual goal list
    -- PlayerView (this file's per-request "everything render_* needs"
    struct, built once in app/auth.py) has no goals field of its own,
    and adding one just for this page's first paint would mean a fresh
    query on every request whether or not Goal Tracking is even the
    page being loaded. Instead this follows the exact same shape
    Purchase Goals and Possessions already use (see render_purchase_goals/
    render_possessions): an empty shell on load, filled in by GET
    /api/goals the instant the page's own script runs, then kept
    current after that by polling the very same endpoint every 5
    seconds -- one endpoint serves both the initial paint and the live
    refresh, so a kill/xp drop/item pickup made mid-session shows up in
    a goal's progress bar within a few seconds, without a reload,
    exactly like every other page on this site that stays live.

    Not linked (player.account_hash is None) skips the add-goal form
    and goal list entirely and shows a one-line prompt to link instead
    -- GET/POST/DELETE /api/goals all require a verified, linked
    GameAccount (see get_current_verified_game_account_from_session in
    app/main.py), so there's nothing this page could usefully show or
    let an unlinked visitor do yet.
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

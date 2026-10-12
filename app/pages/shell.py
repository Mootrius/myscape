"""The shared page shell (head, header nav, link banner, footer) every page renders inside."""
import os
from html import escape
from typing import Optional

from app.pages.player import PlayerView

# Cache-busting `?v=` (file mtime) for the stylesheet link in _shell():
# StaticFiles sends no Cache-Control, so browsers can keep a stale CSS after a
# CSS-only deploy.
_STATIC_CSS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css", "myscape.css")

try:
    _CSS_VERSION = int(os.path.getmtime(_STATIC_CSS_PATH))
except OSError:
    _CSS_VERSION = 0


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

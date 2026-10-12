"""The shared page shell (head, header nav, link banner, footer) every page renders inside."""
import os
from html import escape
from typing import Optional

from app.pages.asset_loader import read_asset
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
    shared_script = read_asset("shell.js", indent=4)
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

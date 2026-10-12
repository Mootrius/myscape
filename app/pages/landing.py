"""The public landing page."""
from typing import Optional

from app.pages.character_overview import render_landing_character_overview_preview
from app.pages.goal_tracking import render_landing_goal_tracking_preview
from app.pages.help_support import (
    _HELP_SUPPORT_HEAD,
    _HELP_SUPPORT_SEARCH_MARKUP,
    _help_support_script,
)
from app.pages.loot_tracker import render_landing_loot_preview
from app.pages.mindmaps import render_landing_mindmap_preview
from app.pages.player import PlayerView
from app.pages.possessions import render_landing_storages_preview
from app.pages.purchase_goals import render_landing_purchase_preview
from app.pages.shell import _shell


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

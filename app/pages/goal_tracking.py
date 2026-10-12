"""Goal Tracking: the page, its shared view, and the landing preview."""
import json
import os
from html import escape
from typing import TYPE_CHECKING, Optional, Tuple

from app.bosses import HISCORE_BOSSES
from app.mindmaps import SKILL_NAMES
from app.pages.asset_loader import read_asset
from app.pages.mindmaps import _get_landing_mindmap_search_pools_data
from app.pages.player import PlayerView
from app.pages.shell import _shell

if TYPE_CHECKING:
    from app.models import GameAccount, SharedContent


# Snapshot for the landing Goal Tracking preview: real goals from GET
# /api/goals, with two current_value numbers adjusted by hand so the demo has an
# in-progress goal.
_LANDING_GOAL_TRACKING_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "landing_goal_tracking_demo.json"
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


_GOAL_TRACKING_CSS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css", "goal-tracking.css"
)

try:
    _GOAL_TRACKING_CSS_VERSION = int(os.path.getmtime(_GOAL_TRACKING_CSS_PATH))
except OSError:
    _GOAL_TRACKING_CSS_VERSION = 0


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
        + read_asset("goal_tracking.js", indent=4)
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

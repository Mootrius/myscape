"""Loot Tracker: the page, its shared view, and the landing preview."""
import json
import os
from datetime import datetime
from html import escape
from typing import TYPE_CHECKING, Optional, Tuple

from app.pages.asset_loader import read_asset
from app.pages.player import PlayerView
from app.pages.shell import _shell

if TYPE_CHECKING:
    from app.models import GameAccount, SharedContent


_LOOT_TRACKER_CSS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css", "loot-tracker.css"
)

try:
    _LOOT_TRACKER_CSS_VERSION = int(os.path.getmtime(_LOOT_TRACKER_CSS_PATH))
except OSError:
    _LOOT_TRACKER_CSS_VERSION = 0

# Curated snapshot behind the landing Loot Tracker preview (regenerate with
# scripts/gen_landing_loot_demo.py). Read lazily and memoized so a bad file
# fails only that page, not app startup.
_LANDING_LOOT_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "landing_loot_demo.json"
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
    script = read_asset("loot_tracker.js", indent=4)
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

"""Storages Viewer: the page, its shared view, and the landing preview."""
import json
import os
from html import escape
from typing import TYPE_CHECKING, Optional, Tuple

from app.pages.asset_loader import read_asset
from app.pages.player import PlayerView
from app.pages.shell import _shell

if TYPE_CHECKING:
    from app.models import GameAccount, SharedContent


# Snapshot for the landing Storages Viewer preview: real possessions from GET
# /api/possessions/summary with PoH (Costume Room) items stripped.
_LANDING_STORAGES_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "landing_storages_demo.json"
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


_POSSESSIONS_CSS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css", "possessions.css"
)

try:
    _POSSESSIONS_CSS_VERSION = int(os.path.getmtime(_POSSESSIONS_CSS_PATH))
except OSError:
    _POSSESSIONS_CSS_VERSION = 0

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

    script = read_asset("possessions.js", indent=4)
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

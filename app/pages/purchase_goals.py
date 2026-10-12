"""Purchase Goals: the page, its shared view, and the landing preview."""
import json
import os
from html import escape
from typing import TYPE_CHECKING, Optional, Tuple

from app.pages.asset_loader import read_asset
from app.pages.icons import _ICON_COINS
from app.pages.player import PlayerView
from app.pages.shell import _shell

if TYPE_CHECKING:
    from app.models import GameAccount, SharedContent


# Cache-busting `?v=` (file mtime) for the Purchase Goals stylesheet (separate
# from myscape.css since none of it applies elsewhere).
_PURCHASE_GOALS_CSS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css", "purchase-goals.css"
)

try:
    _PURCHASE_GOALS_CSS_VERSION = int(os.path.getmtime(_PURCHASE_GOALS_CSS_PATH))
except OSError:
    _PURCHASE_GOALS_CSS_VERSION = 0

# Snapshot for the landing Purchase Goals preview: a real "Tombs of Amascut"
# setup pulled once from GET /api/gear-setups.
_LANDING_PURCHASE_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "landing_purchase_demo.json"
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
    script = read_asset("purchase_goals.js", indent=4)
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

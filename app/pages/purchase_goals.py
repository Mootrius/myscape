"""Purchase Goals: the page, its shared view, and the landing preview."""
import json
import os
from html import escape
from typing import TYPE_CHECKING, Optional, Tuple

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
      // (_sort_tabs/updateSortTabs in app/pages/). SORT_METRIC_MODE maps
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
      // setSettingsMenuOpen (app/pages/) as setPgShareOpen. Null-guarded like
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

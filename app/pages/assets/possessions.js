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
    return '<img class="pm-row-icon" src="' + src + '" alt="" loading="lazy" onerror="this.style.display=\'none\'" />';
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
        arrow.textContent = state.sortDir === 'asc' ? ' \u2191' : ' \u2193';
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
    var key = state.sortKey + '\u0001' + state.sortDir + '\u0001' + state.search + '\u0001' + activeLocations + '\u0001' + pinnedKey + '\u0001' + filterKey + '\u0001' +
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

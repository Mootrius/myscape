(function () {
  var state = {
    // Ordered list, not a Set: selection order feeds the chart title
    // (renderBarChart). A plain click collapses to one entry (or empties
    // it); shift-click toggles one name; see the NPC row click handler.
    selectedNpcs: [], npcSort: 'gp-desc', npcSearch: '', itemSort: 'gp-desc', itemSearch: '',
    rangeKey: '24h', customStart: null, customEnd: null,
    // The clicked bar's {start, end, value, killCount, index}, or null.
    // Mutually exclusive with selectedNpcs (bar click scopes to a time
    // slice, NPC click to an identity). See currentNpcs/currentItems and
    // renderBarChart. `index` is the real identity: loadState overwrites the
    // other fields in place each poll with whichever bucket now sits at that
    // index, so a rolling preset's drift moves the selection along.
    selectedBucket: null,
    // Local UI state, never persisted: each panel's "show hidden" eye toggle
    // (.loot-hide-toggle). Off by default, so hidden NPCs/items are gone,
    // not dimmed (see visibleNpcEntries/visibleItemEntries).
    npcShowHidden: false, itemShowHidden: false,
  };
  var lastData = null;
  // Scoped payload for state.selectedBucket, separate from lastData (which
  // always covers the whole range for the chart): an extra GET
  // /api/players/me/loot for that bucket's [start, end) window
  // (bucketUrl/loadBucketData). Null when nothing is selected or the first
  // fetch is in flight.
  var bucketData = null;
  // Bumped by clearSelectedBucket and every loadBucketData call; guards
  // against a superseded slow fetch clobbering the panels (same as
  // npcRowRenderToken/itemListRenderToken).
  var bucketFetchToken = 0;

  // Feather eye/eye-off for the per-tile hide button in each NPC/item box
  // (renderNpcRow/renderItemList): open eye when clicking would hide,
  // crossed-out when it would unhide. The sort-row toggle (_EYE_GLYPH_SVG in
  // render_loot_tracker) is the open eye only.
  var EYE_GLYPH = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>';
  var EYE_OFF_GLYPH = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19M14.12 14.12a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>';

  // An NPC whose items are all individually hidden (item.hidden, set by
  // build_loot_state in app/loot.py) is treated as hidden for display
  // (filtered out, or dimmed with the toggle on). Its eye button still acts
  // only on the explicit n.hidden (see the #lootNpcRow click handler), so
  // unhiding one item doesn't require hiding the NPC.
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

  // Case-insensitive substring match on the given name field (sourceName for
  // NPCs, itemName for items).
  function filterByName(list, query, nameKey) {
    if (!query) return list;
    var q = query.toLowerCase();
    return list.filter(function (entry) {
      return (entry[nameKey] || '').toLowerCase().indexOf(q) !== -1;
    });
  }

  // Splits a "<metric>-<dir>" sort string (gp-desc, count-asc, ...) into its
  // parts; a bare metric defaults to 'desc'.
  function splitSort(sortStr) {
    var sep = sortStr.indexOf('-');
    return sep === -1
      ? { metric: sortStr, dir: 'desc' }
      : { metric: sortStr.slice(0, sep), dir: sortStr.slice(sep + 1) };
  }

  // Each metric's first-click direction: gp/count/time descending, alpha
  // ascending (cf. Storages Viewer's SORT_DEFAULT_DIR). Clicking the active
  // metric flips direction instead.
  var SORT_METRIC_DEFAULT_DIR = { gp: 'desc', count: 'desc', alpha: 'asc', time: 'desc' };

  // Shared by both panels' sort tabs. sortMode is "<metric>-<dir>": gp sorts
  // by valueKey, count by countKey (killCount for NPCs, quantity for items),
  // alpha by nameKey, time by recentKey (ISO timestamp: lastKillAt /
  // lastDroppedAt). desc is high-to-low / Z-to-A / newest-first. Never
  // mutates the input.
  function sortEntries(list, sortMode, nameKey, valueKey, recentKey, countKey) {
    var out = list.slice();
    var sort = splitSort(sortMode);
    if (sort.metric === 'count') {
      out.sort(function (a, b) { return sort.dir === 'asc' ? (a[countKey] || 0) - (b[countKey] || 0) : (b[countKey] || 0) - (a[countKey] || 0); });
    } else if (sort.metric === 'alpha') {
      out.sort(function (a, b) { return sort.dir === 'asc' ? (a[nameKey] || '').localeCompare(b[nameKey] || '') : (b[nameKey] || '').localeCompare(a[nameKey] || ''); });
    } else if (sort.metric === 'time') {
      out.sort(function (a, b) { var diff = new Date(b[recentKey] || 0) - new Date(a[recentKey] || 0); return sort.dir === 'asc' ? -diff : diff; });
    } else {
      out.sort(function (a, b) { return sort.dir === 'asc' ? (a[valueKey] || 0) - (b[valueKey] || 0) : (b[valueKey] || 0) - (a[valueKey] || 0); });
    }
    return out;
  }

  // Marks the active sort-tab button and draws its arrow, within one
  // .loot-sort-tabs container (shared markup, see _sort_tabs). activeSort is
  // the "<metric>-<dir>" string; same arrow convention as Storages Viewer's
  // updateSortHeaders.
  function updateSortTabs(containerId, activeSort) {
    var container = document.getElementById(containerId);
    var active = splitSort(activeSort);
    var btns = container.querySelectorAll('.loot-sort-tab');
    for (var i = 0; i < btns.length; i++) {
      var btn = btns[i];
      var isActive = btn.getAttribute('data-sort-metric') === active.metric;
      btn.classList.toggle('active', isActive);
      var arrow = btn.querySelector('.loot-sort-arrow');
      if (arrow) arrow.textContent = isActive ? (active.dir === 'asc' ? ' \u2191' : ' \u2193') : '';
    }
  }

  // Sums per-bucket gp across selected NPCs' npcBucketValues (see
  // build_loot_state in app/loot.py) into one array; null unless 2+ are
  // selected.
  function mergedNpcBucketValues(npcBucketValues, selectedNpcs, numBuckets) {
    var merged = new Array(numBuckets).fill(0);
    selectedNpcs.forEach(function (name) {
      var values = npcBucketValues[name];
      if (!values) return;
      for (var i = 0; i < numBuckets; i++) merged[i] += values[i] || 0;
    });
    return merged;
  }

  // Sums quantity/value per item (keyed like _add_item_totals server-side:
  // itemId, else itemName) across selected NPCs' npcItems. Keeps the latest
  // lastDroppedAt; icon and hidden flag are identical across occurrences.
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

  // The NPC row's source list: a clicked bar (state.selectedBucket) wins
  // over lastData.windowNpcs, as in currentItems. All NPC-row callers go
  // through this.
  function currentNpcs() {
    if (state.selectedBucket) return bucketData ? (bucketData.windowNpcs || []) : [];
    return (lastData && lastData.windowNpcs) || [];
  }

  // Item panel source: all NPCs' items when none selected, the one NPC's
  // items when one is, summed items (mergedNpcItems) for 2+ (see
  // windowItems/npcItems in build_loot_state, app/loot.py). A clicked bar
  // takes priority (mutually exclusive with selectedNpcs) and reads
  // bucketData, since only its scoped fetch has that bucket's items. Empty
  // while that fetch is in flight, to avoid flashing the too-broad range
  // items.
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

  // Compact axis label for a gp amount ("12.4k" / "3.1M") to fit the narrow
  // gutter.
  function fmtGpCompact(n) {
    var sign = n < 0 ? '-' : '';
    var abs = Math.abs(n || 0);
    if (abs >= 1e6) return sign + (abs / 1e6).toFixed(abs >= 1e7 ? 0 : 1).replace(/\.0$/, '') + 'M';
    if (abs >= 1e3) return sign + (abs / 1e3).toFixed(abs >= 1e4 ? 0 : 1).replace(/\.0$/, '') + 'k';
    return sign + Math.round(abs).toLocaleString('en-US');
  }

  // Rounds a chart max up to a "nice" number (step x power of ten) so
  // gridlines are clean. targetFrac scales the ceiling so the tallest bar
  // lands near that fraction of the axis; dividing by it before rounding,
  // with a finer step table, keeps the tallest bar in a tight band (about
  // 60-80% for a 0.8 target) instead of swinging 50-100%.
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

  // A bucket's x-axis tick, formatted by the range's granularity (see
  // _bucket_plan in app/loot.py): clock time hourly, short date
  // daily/weekly, month monthly.
  function fmtBucketLabel(granularity, isoString) {
    if (!isoString) return '';
    var d = new Date(isoString);
    if (granularity === 'hourly') return d.toLocaleTimeString('en-US', { hour: 'numeric' });
    if (granularity === 'monthly') return d.toLocaleDateString('en-US', { month: 'short' });
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  // Whether an ISO timestamp is close enough to now to label the last bar
  // "NOW"; a CUSTOM range ending earlier gets its real date/time.
  function isNowish(isoString) {
    if (!isoString) return false;
    return Math.abs(new Date(isoString).getTime() - Date.now()) < 5 * 60 * 1000;
  }

  // 'YYYY-MM-DD' (<input type="date"> value) to a short display date for the
  // range button's CUSTOM label.
  function fmtDateShort(isoDate) {
    if (!isoDate) return '';
    var d = new Date(isoDate + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  // Local-time zero-padded 'YYYY-MM-DD' for a Date, built by hand
  // (toLocaleDateString has no ISO-basic format).
  function fmtIsoDateLocal(d) {
    var month = String(d.getMonth() + 1);
    if (month.length < 2) month = '0' + month;
    var day = String(d.getDate());
    if (day.length < 2) day = '0' + day;
    return d.getFullYear() + '-' + month + '-' + day;
  }

  // A clicked bar's exact time range for the chart title (see
  // renderBarChart), using the bucket's real start/end (bucket boundaries
  // aren't calendar-aligned; see fmtBucketLabel). Dates use YYYY-MM-DD
  // (fmtIsoDateLocal). The end shown is 1s before the exclusive boundary (as
  // in bucketUrl), so 3:00-3:59 doesn't read as 3:00-4:00 and overlap the
  // next bar. The end date is shown only when it differs from the start's.
  function fmtBucketRangeLabel(startIso, endIso) {
    var start = new Date(startIso);
    var end = new Date(new Date(endIso).getTime() - 1000);
    var timeOpts = { hour: 'numeric', minute: '2-digit' };
    var startDateStr = fmtIsoDateLocal(start);
    var endDateStr = fmtIsoDateLocal(end);
    var startTimeStr = start.toLocaleTimeString('en-US', timeOpts);
    var endTimeStr = end.toLocaleTimeString('en-US', timeOpts);
    if (startDateStr === endDateStr) {
      return startDateStr + ', ' + startTimeStr + ' \u2013 ' + endTimeStr;
    }
    return startDateStr + ', ' + startTimeStr + ' \u2013 ' + endDateStr + ', ' + endTimeStr;
  }

  function rangeButtonLabel() {
    if (state.rangeKey === 'custom' && state.customStart && state.customEnd) {
      return fmtDateShort(state.customStart) + ' \u2013 ' + fmtDateShort(state.customEnd);
    }
    return RANGE_LABELS[state.rangeKey] || RANGE_LABELS['24h'];
  }

  // An item's OSRS Wiki article title is almost always its in-game name
  // (itemName), URL-encoded as for item_icon_url in app/purchase_goals.py;
  // MediaWiki treats %20 like an underscore. A mismatched name lands on
  // Special:Search, which redirects to an exact title match.
  function wikiItemUrl(name) {
    return 'https://oldschool.runescape.wiki/w/Special:Search?search=' + encodeURIComponent(name || '') + '&go=Go';
  }

  function iconImg(src, alt, cls) {
    if (!src) return '';
    // Hidden on a 404 (guessed wiki filename) rather than showing a
    // broken-image icon, like item icons elsewhere.
    return '<img class="' + cls + '" src="' + src + '" alt="" ' +
      'onerror="this.style.display=\'none\'" />';
  }

  // Preloads these icon URLs (skipping falsy ones) before the caller swaps
  // in the HTML, so new rows paint decoded instead of popping in. Capped at
  // ICON_PRELOAD_TIMEOUT_MS so a dead wiki image can't stall the swap;
  // iconImg's onerror still hides broken icons.
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

  // renderNpcRow/renderItemList rebuild their whole list when a hide/unhide
  // changes its entries (see each key comment). With no min-height reserved,
  // the height change shifts the page below. Re-pin the scroll position
  // around the swap, synchronously so no in-between frame paints.
  function swapListHtml(el, html) {
    var scrollY = window.scrollY;
    el.innerHTML = html;
    if (window.scrollY !== scrollY) window.scrollTo(0, scrollY);
  }

  // Used instead of swapListHtml when the set or order of boxes changes (new
  // kill/drop, re-sort, hide/unhide): new boxes are built aside and boxes
  // already on screen (matched by keyFn) are kept and moved, so their <img>
  // isn't re-created, which made icons flicker out. Only new boxes get a new
  // <img> (already fetched by preloadIcons); a kept box whose icon failed
  // gets a fresh <img> to retry.
  function reconcileBoxes(el, html, boxSel, keyFn) {
    var scrollY = window.scrollY;
    var tpl = document.createElement('template');
    tpl.innerHTML = html;
    var oldByKey = {};
    Array.prototype.forEach.call(el.children, function (w) {
      var k = keyFn(w);
      if (k != null) oldByKey[k] = w;
    });
    var frag = document.createDocumentFragment();
    Array.prototype.slice.call(tpl.content.children).forEach(function (nw) {
      var k = keyFn(nw);
      var ow = k != null ? oldByKey[k] : null;
      if (!ow) { frag.appendChild(nw); return; }
      delete oldByKey[k];
      ow.className = nw.className;
      var ob = ow.querySelector(boxSel), nb = nw.querySelector(boxSel);
      if (!ob || !nb) { frag.appendChild(nw); return; }
      Array.prototype.slice.call(ob.attributes).forEach(function (a) { ob.removeAttribute(a.name); });
      Array.prototype.slice.call(nb.attributes).forEach(function (a) { ob.setAttribute(a.name, a.value); });
      var oImg = ob.querySelector('img'), nImg = nb.querySelector('img');
      var kids = Array.prototype.slice.call(nb.childNodes);
      if (oImg && nImg && oImg.getAttribute('src') === nImg.getAttribute('src') &&
          oImg.className === nImg.className && oImg.style.display !== 'none') {
        kids[kids.indexOf(nImg)] = oImg;
      }
      ob.replaceChildren.apply(ob, kids);
      var oe = ow.querySelector('.loot-eye-btn'), ne = nw.querySelector('.loot-eye-btn');
      if (oe && ne) oe.replaceWith(ne);
      frag.appendChild(ow);
    });
    el.replaceChildren(frag);
    if (window.scrollY !== scrollY) window.scrollTo(0, scrollY);
  }

  // Bar chart over the selected range, bucketed by its span (see
  // _bucket_plan in app/loot.py), oldest on the left; ported from the
  // original tool's renderVorkathBarChart. With NPCs selected
  // (state.selectedNpcs), each bar shows a full-height outline at the bucket
  // total plus a solid fill for the selected NPCs' share
  // (mergedNpcBucketValues for 2+). maxValue comes from the totals so the
  // axis stays put. Reuses bar-col elements when the bucket count is
  // unchanged so the CSS height transition animates between polls; a range
  // change rebuilds.
  function renderBarChart(buckets, windowValue, windowKills, npcBucketValues, selectedNpcs, windowNpcs, granularity, rangeEnd, selectedBucket) {
    buckets = buckets || [];
    npcBucketValues = npcBucketValues || {};
    selectedNpcs = selectedNpcs || [];
    granularity = granularity || 'hourly';
    // Three mutually exclusive sources for the header gp/kc and the title,
    // in priority order: clicked bar (selectedBucket), NPC selection
    // (selectedNpcs), whole range. The click handlers clear the other
    // selection, but the priority still matters for the one render that
    // lands before the clearing.
    var headerValue, headerKills, titleText;
    if (selectedBucket) {
      // Reads selectedBucket directly; loadState keeps it fresh each poll
      // (see state's comment), so these are current numbers.
      headerValue = selectedBucket.value;
      headerKills = selectedBucket.killCount;
      titleText = fmtBucketRangeLabel(selectedBucket.start, selectedBucket.end);
    } else {
      // With NPCs selected, header gp/kc show just their totals (from
      // windowNpcs value/killCount) so they match the chart's partial fill.
      var selectedEntries = selectedNpcs.length && windowNpcs
        ? windowNpcs.filter(function (n) { return selectedNpcs.indexOf(n.sourceName) !== -1; })
        : [];
      headerValue = selectedEntries.length ? selectedEntries.reduce(function (sum, n) { return sum + n.value; }, 0) : windowValue;
      headerKills = selectedEntries.length ? selectedEntries.reduce(function (sum, n) { return sum + n.killCount; }, 0) : windowKills;
      // Selected NPC names are uppercased in JS, not via CSS text-transform
      // on .loot-chart-title, which would turn the "ALL NPCs" fallback into
      // "ALL NPCS". Multiple names are joined with a small dot (·) in
      // selection order.
      titleText = 'ALL NPCs';
      if (selectedNpcs.length === 1) {
        titleText = selectedNpcs[0].toUpperCase();
      } else if (selectedNpcs.length > 1) {
        titleText = selectedNpcs.map(function (n) { return n.toUpperCase(); }).join(' \u00b7 ');
      }
    }
    document.getElementById('lootChartTotal').textContent = fmtGp(headerValue) + ' gp';
    document.getElementById('lootChartKills').textContent = (headerKills || 0).toLocaleString('en-US') + ' kc';
    document.getElementById('lootChartTitle').textContent = titleText;

    // 0.8 target puts the tallest bar around 4/5 up the axis (see niceMax).
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

    // The outline always sits at the bucket's total height and never
    // animates. Only the solid fill (see fillPct) changes with selection:
    // with nothing selected the fill covers the outline completely, and
    // selecting an NPC shrinks the fill to reveal it.
    function outlinePct(b) {
      return maxValue > 0 ? Math.max(0, Math.min(100, (b.value / maxValue) * 100)) : 0;
    }
    // A bordered box paints its border even at height:0, so a zero-loot hour
    // would show a sliver. Only enable the border for buckets with something
    // to outline. Not tied to selection: the outline's visibility never
    // changes, only the fill's height.
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
    // With a selection, a bucket the selection had no part in keeps
    // outlineActive but gets fillPct 0, exposing the whole outline including
    // its bottom border, which reads as a baseline line. Suppress just the
    // bottom edge (loot-bar-outline.no-bottom-border); top/left/right still
    // show that loot existed.
    function outlineHideBottomBorder(b, i) {
      return selectedNpcs.length > 0 && fillPct(b, i) <= 0;
    }

    // Whether column i is the one state.selectedBucket points at. Matched by
    // index, not start/end, since rolling presets drift each poll (see
    // state's comment on selectedBucket).
    function isSelectedCol(i) {
      return !!(selectedBucket && i === selectedBucket.index);
    }

    var barsEl = document.getElementById('lootBarBars');
    var existingCols = barsEl.children;
    if (existingCols.length !== buckets.length) {
      barsEl.innerHTML = buckets.map(function (b, i) {
        return '<div class="loot-bar-col' + (isSelectedCol(i) ? ' selected' : '') + '" data-bucket-index="' + i + '">' +
          '<div class="loot-bar-outline' + (outlineActive(b) ? ' active' : '') + (outlineHideBottomBorder(b, i) ? ' no-bottom-border' : '') + '" style="height:' + outlinePct(b) + '%;"></div>' +
          '<div class="loot-bar-fill' + (fillPct(b, i) > 0 ? ' has-value' : '') + '" style="height:' + fillPct(b, i) + '%;"></div>' +
        '</div>';
      }).join('');
    } else {
      buckets.forEach(function (b, i) {
        var col = existingCols[i];
        col.setAttribute('data-bucket-index', i);
        col.classList.toggle('selected', isSelectedCol(i));
        var outline = col.querySelector('.loot-bar-outline');
        outline.style.height = outlinePct(b) + '%';
        outline.classList.toggle('active', outlineActive(b));
        outline.classList.toggle('no-bottom-border', outlineHideBottomBorder(b, i));
        var fill = col.querySelector('.loot-bar-fill');
        var fp = fillPct(b, i);
        fill.style.height = fp + '%';
        fill.classList.toggle('has-value', fp > 0);
      });
    }

    // Label roughly every 1/7th of the chart width (24 hourly buckets: every
    // 4th), scaling with bucket count. The last bucket gets "NOW" only when
    // the range end is near now (see isNowish).
    var labelStep = Math.max(1, Math.ceil(buckets.length / 7));
    var endIsNow = isNowish(rangeEnd);
    document.getElementById('lootBarXLabels').innerHTML = buckets.map(function (b, i) {
      if (i === buckets.length - 1 && endIsNow) return '<div class="loot-bar-x-label now">NOW</div>';
      var label = (i % labelStep === 0) ? fmtBucketLabel(granularity, b.start) : '';
      return '<div class="loot-bar-x-label">' + label + '</div>';
    }).join('');
  }

  // The clickable "By NPC" row, one box per NPC killed in the range. A plain
  // click selects just that NPC (clicking the sole selected one clears it);
  // shift-click toggles it in/out of the selection, folding in a single
  // plain-selected NPC on first use (see the click handler). Re-renders from
  // the last-polled data with no fetch. One selected NPC gets the gold
  // .active border; 2+ get the blue .multi-selected outline (cf.
  // .gear-slot.multi-selected in purchase-goals.css).
  // The row's HTML (and its <img> icons) is rebuilt only when the set/order
  // changes; otherwise active/title state is patched in place, since
  // rebuilding every poll made icons flicker. The list is filtered by
  // state.npcSearch and sorted by state.npcSort, so the dedup key must
  // include search/sort state too.
  var lastNpcKey = null;
  // Bumped on every rebuild; guards the preloadIcons().then() callback so a
  // superseded rebuild can't clobber the row with stale boxes.
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

    // Toggle off (default): hidden NPCs, explicit or effective
    // (npcEffectiveHidden), are filtered out. On: all show, hidden ones
    // dimmed (hidden-entry class). See .loot-hide-toggle in
    // loot-tracker.css.
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

            // Sources whose wiki art is a large "detail" render (reads
            // oversized in the shared 56px NPC icon box) get a dedicated
            // 70%-scale class (.loot-npc-box-icon-* in loot-tracker.css);
            // see _NPC_DISPLAY_OVERRIDES in app/loot.py. Reward caskets are
            // always "Reward casket (<tier>)" (npc_like_name in
            // build_loot_state), so this can't match a real NPC.
    function isCasketNpc(n) {
      return /^Reward casket \(/i.test(n.sourceName);
    }

    // Exact name; Guardians of the Rift's per-round reward.
    function isIntricatePouch(n) {
      return n.sourceName === 'Intricate pouch';
    }

    // Real NPCs whose bare wiki-name guess is right but reads large.
    // Exact-name matches, so similarly named NPCs ("Giant spider", "Goblin
    // (Dorgesh-Kaan)", see app/npc_names.py) are left alone.
    function isCrawlingHand(n) {
      return /^Crawling Hand$/i.test(n.sourceName);
    }

    function isSpider(n) {
      return /^Spider$/i.test(n.sourceName);
    }

    function isDeathSpawn(n) {
      return /^Death spawn$/i.test(n.sourceName);
    }

    function isGoblin(n) {
      return /^Goblin$/i.test(n.sourceName);
    }

    function isRockslug(n) {
      return /^Rockslug$/i.test(n.sourceName);
    }

    function isHellhound(n) {
      return /^Hellhound$/i.test(n.sourceName);
    }

    function isAraxyte(n) {
      return /^Araxyte$/i.test(n.sourceName);
    }

    function isScion(n) {
      return /^Scion$/i.test(n.sourceName);
    }

    function isJuvenileCustodianStalker(n) {
      return /^Juvenile custodian stalker$/i.test(n.sourceName);
    }

    function isTuroth(n) {
      return /^Turoth$/i.test(n.sourceName);
    }

    function isSpawn(n) {
      return /^Spawn$/i.test(n.sourceName);
    }

    function isImp(n) {
      return /^Imp$/i.test(n.sourceName);
    }

    function isRam(n) {
      return /^Ram$/i.test(n.sourceName);
    }

    function isCalf(n) {
      return /^(Cow )?Calf$/i.test(n.sourceName);
    }

    function isChicken(n) {
      return /^Chicken$/i.test(n.sourceName);
    }

    function isEntling(n) {
      return /^Entling$/i.test(n.sourceName);
    }

    // Yama's reward container (see _NPC_DISPLAY_OVERRIDES in app/loot.py).
    function isDossier(n) {
      return /^Dossier$/i.test(n.sourceName);
    }

    function isUnsired(n) {
      return /^Unsired$/i.test(n.sourceName);
    }

    function isForgottenLockbox(n) {
      return /^Forgotten lockbox$/i.test(n.sourceName);
    }

    // The nine Tarnished NPCs folded into one tile, shown under a bundled
    // battleaxe image.
    function isTarnishedItems(n) {
      return n.sourceName === 'Tarnished items';
    }

    // Every impling type. Matched by a "<word> impling" suffix so new types
    // are picked up automatically.
    function isImpling(n) {
      return /\bimpling$/i.test(n.sourceName);
    }

    // Seed pack / bird nest: event-type loot sources (see
    // _NPC_DISPLAY_OVERRIDES in app/loot.py), exact names. Only this panel
    // uses the detail render; renderItemList always shows the plain icon.
    function isSeedPackSource(n) {
      return n.sourceName === 'Seed pack';
    }
    function isBirdNestSource(n) {
      return n.sourceName === 'Bird nest';
    }

    // Sailing salvage tiers (8 of them, see _NPC_DISPLAY_OVERRIDES in
    // app/loot.py), matched by a "<word> salvage" suffix; no other source
    // name ends in " salvage".
    function isSalvageSource(n) {
      return /\bsalvage$/i.test(n.sourceName);
    }


    // hiddenFlags joins the key because hide/unhide can change which entries
    // are dimmed without changing membership or order (same as Storages
    // Viewer's pinnedKey in render_possessions).
    var hiddenFlags = sorted.map(function (n) { return npcEffectiveHidden(n) ? '1' : '0'; }).join('');
    var key = state.npcSearch + '\u0001' + state.npcSort + '\u0001' + (state.npcShowHidden ? '1' : '0') + '\u0001' +
      hiddenFlags + '\u0001' + sorted.map(function (n) { return n.sourceName; }).join('|');
    if (key !== lastNpcKey) {
      var html = sorted.map(function (n) {
        // A solo selection gets the gold .active border; 2+ get the blue
        // .multi-selected outline (see .loot-npc-box in loot-tracker.css).
        var isSelected = state.selectedNpcs.indexOf(n.sourceName) !== -1;
        var active = isSelected && state.selectedNpcs.length === 1;
        var multiSelected = isSelected && state.selectedNpcs.length > 1;
        var hidden = npcEffectiveHidden(n);
        var explicitHidden = !!n.hidden;
        var eyeTooltip = (explicitHidden ? 'Show ' : 'Hide ') + 'NPC';
        // A <button> can't nest in a <button> (see .loot-npc-box-wrap in
        // loot-tracker.css), so the eye toggle is a sibling of the box
        // inside a non-interactive div. That also means clicking it needs no
        // stopPropagation, as with Storages Viewer's pin button.
        return '<div class="loot-npc-box-wrap' + (hidden ? ' hidden-entry' : '') + '">' +
          '<button type="button" class="loot-npc-box' + (active ? ' active' : '') + (multiSelected ? ' multi-selected' : '') + '" data-npc="' +
            escapeHtml(n.sourceName) + '" data-tooltip="' + escapeHtml(n.sourceName) + '">' +
            iconImg(n.icon, n.sourceName, 'loot-npc-box-icon' + (isCasketNpc(n) ? ' loot-npc-box-icon-casket' : '') + (isIntricatePouch(n) ? ' loot-npc-box-icon-pouch' : '') + (isCrawlingHand(n) ? ' loot-npc-box-icon-crawling-hand' : '') + (isImpling(n) ? ' loot-npc-box-icon-impling' : '') + (isSeedPackSource(n) ? ' loot-npc-box-icon-seedpack' : '') + (isBirdNestSource(n) ? ' loot-npc-box-icon-birdnest' : '') + (isSalvageSource(n) ? ' loot-npc-box-icon-salvage' : '') + (isSpider(n) ? ' loot-npc-box-icon-spider' : '') + (isDeathSpawn(n) ? ' loot-npc-box-icon-death-spawn' : '') + (isGoblin(n) ? ' loot-npc-box-icon-goblin' : '') + (isRockslug(n) ? ' loot-npc-box-icon-rockslug' : '') + (isHellhound(n) ? ' loot-npc-box-icon-hellhound' : '') + (isAraxyte(n) ? ' loot-npc-box-icon-araxyte' : '') + (isScion(n) ? ' loot-npc-box-icon-scion' : '') + (isJuvenileCustodianStalker(n) ? ' loot-npc-box-icon-juvenile-custodian-stalker' : '') + (isTuroth(n) ? ' loot-npc-box-icon-turoth' : '') + (isSpawn(n) ? ' loot-npc-box-icon-spawn' : '') + (isImp(n) ? ' loot-npc-box-icon-imp' : '') + (isRam(n) ? ' loot-npc-box-icon-ram' : '') + (isCalf(n) ? ' loot-npc-box-icon-calf' : '') + (isChicken(n) ? ' loot-npc-box-icon-chicken' : '') + (isEntling(n) ? ' loot-npc-box-icon-entling' : '') + (isDossier(n) ? ' loot-npc-box-icon-dossier' : '') + (isUnsired(n) ? ' loot-npc-box-icon-unsired' : '') + (isForgottenLockbox(n) ? ' loot-npc-box-icon-forgotten-lockbox' : '') + (isTarnishedItems(n) ? ' loot-npc-box-icon-tarnished' : '')) +
            '<div class="loot-npc-box-kc">' + n.killCount + ' kc</div>' +
            '<div class="loot-npc-box-value">' + fmtGpCompact(n.value) + ' gp</div>' +
          '</button>' +
          '<button type="button" class="loot-eye-btn" data-hide-name="' + escapeHtml(n.sourceName) +
            '" data-hidden="' + (explicitHidden ? '1' : '0') + '" data-tooltip="' + escapeHtml(eyeTooltip) + '">' +
            (hidden ? EYE_OFF_GLYPH : EYE_GLYPH) +
          '</button>' +
        '</div>';
      }).join('');
      // Preload icons before swapping the HTML in so boxes and pictures
      // appear together.
      var token = ++npcRowRenderToken;
      preloadIcons(sorted.map(function (n) { return n.icon; })).then(function () {
        if (token !== npcRowRenderToken) return;
        lastNpcKey = key;
        reconcileBoxes(rowEl, html, '.loot-npc-box', function (w) {
          var b = w.querySelector('.loot-npc-box');
          return b ? b.getAttribute('data-npc') : null;
        });
      });
      return;
    }

    // Same set/order: keep the boxes and their <img>s, but refresh kc/value
    // text and title in place. Queried by .loot-npc-box-wrap, as in
    // render_possessions' patch branch.
    var wraps = rowEl.querySelectorAll('.loot-npc-box-wrap');
    sorted.forEach(function (n, i) {
      var wrap = wraps[i];
      if (!wrap) return;
      var box = wrap.querySelector('.loot-npc-box');
      var isSelected = state.selectedNpcs.indexOf(n.sourceName) !== -1;
      box.classList.toggle('active', isSelected && state.selectedNpcs.length === 1);
      box.classList.toggle('multi-selected', isSelected && state.selectedNpcs.length > 1);
      box.setAttribute('data-tooltip', n.sourceName);
      var kcEl = box.querySelector('.loot-npc-box-kc');
      if (kcEl) kcEl.textContent = n.killCount + ' kc';
      var valEl = box.querySelector('.loot-npc-box-value');
      if (valEl) valEl.textContent = fmtGpCompact(n.value) + ' gp';
    });
  }

  // Item panel: all NPCs' items, or the selected NPC's (see currentItems),
  // filtered by state.itemSearch and sorted by state.itemSort. Keyed on
  // itemId (falling back to itemName, like _add_item_totals server-side),
  // plus the selected NPC and search/sort state, so switching rebuilds but
  // an unchanged poll reuses the DOM.
  var lastItemKey = null;
  // See npcRowRenderToken.
  var itemListRenderToken = 0;

  // The item panel always uses the plain flat RuneLite-CDN pixel icon
  // (it.icon, from item_icon_url in app/loot.py), never the wiki's detail
  // render. The NPC/source panel is the only place detail renders appear.

  function renderItemList(items) {
    var emptyEl = document.getElementById('lootItemEmpty');
    var listEl = document.getElementById('lootItemList');
    // Same as renderNpcRow's visible filter; an item has no sub-items, so
    // it.hidden alone decides.
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

            // hiddenFlags in the key, as in renderNpcRow.
    var hiddenFlags = sorted.map(function (it) { return it.hidden ? '1' : '0'; }).join('');
    var key = state.selectedNpcs.join('\u0002') + '\u0001' + state.itemSearch + '\u0001' + state.itemSort + '\u0001' +
      (state.itemShowHidden ? '1' : '0') + '\u0001' + hiddenFlags + '\u0001' +
      sorted.map(function (it) { return it.itemId != null ? it.itemId : it.itemName; }).join('|');
    if (key !== lastItemKey) {
      var html = sorted.map(function (it) {
        var eyeTooltip = (it.hidden ? 'Show ' : 'Hide ') + 'item';
        // Sibling wrap as in renderNpcRow: an <a> can't contain a <button>
        // either.
        return '<div class="loot-item-box-wrap' + (it.hidden ? ' hidden-entry' : '') + '">' +
          '<a class="loot-item-box" href="' + wikiItemUrl(it.itemName) + '" target="_blank" rel="noopener" data-tooltip="' + escapeHtml(it.itemName) + '">' +
            iconImg(it.icon, it.itemName, 'loot-item-box-icon') +
            '<div class="loot-item-box-qty">' + '\u00d7' + fmtGpCompact(it.quantity) + '</div>' +
            '<div class="loot-item-box-value">' + fmtGpCompact(it.value) + ' gp</div>' +
          '</a>' +
          '<button type="button" class="loot-eye-btn" data-hide-item-id="' + (it.itemId != null ? it.itemId : '') +
            '" data-hide-name="' + escapeHtml(it.itemName) + '" data-hidden="' + (it.hidden ? '1' : '0') +
            '" data-tooltip="' + escapeHtml(eyeTooltip) + '">' +
            (it.hidden ? EYE_OFF_GLYPH : EYE_GLYPH) +
          '</button>' +
        '</div>';
      }).join('');
      // Preload before swap, as in renderNpcRow; this branch runs on every
      // NPC selection change, when icons are most likely new.
      var token = ++itemListRenderToken;
      preloadIcons(sorted.map(function (it) { return it.icon; })).then(function () {
        if (token !== itemListRenderToken) return;
        lastItemKey = key;
        reconcileBoxes(listEl, html, '.loot-item-box', function (w) {
          var e = w.querySelector('.loot-eye-btn');
          return e ? e.getAttribute('data-hide-item-id') + '|' + e.getAttribute('data-hide-name') : null;
        });
      });
      return;
    }

    // Same reuse branch as renderNpcRow: keep icons, refresh qty/value text
    // and title.
    var wraps = listEl.querySelectorAll('.loot-item-box-wrap');
    sorted.forEach(function (it, i) {
      var wrap = wraps[i];
      if (!wrap) return;
      var box = wrap.querySelector('.loot-item-box');
      box.setAttribute('data-tooltip', it.itemName);
      var qtyEl = box.querySelector('.loot-item-box-qty');
      if (qtyEl) qtyEl.textContent = '\u00d7' + fmtGpCompact(it.quantity);
      var valEl = box.querySelector('.loot-item-box-value');
      if (valEl) valEl.textContent = fmtGpCompact(it.value) + ' gp';
    });
  }

  // Hiding/unhiding an NPC or item: call the endpoint
  // (set_npc_hidden/set_item_hidden in app/loot.py), then re-poll with
  // loadState() rather than patching client state, since the server knows
  // how hiding reshapes every total (see build_loot_state).
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
    // The eye button is a sibling of .loot-npc-box, so it never matches
    // .closest('.loot-npc-box') below; checked first anyway to make the
    // priority explicit.
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
    // Selecting an NPC scopes by identity, so clear any bar selection first
    // (mirror of the #lootBarBars handler).
    clearSelectedBucket();
    if (e.shiftKey) {
      // Shift-click toggles this NPC in/out without touching the rest; a
      // single plain-selected NPC folds into the new group.
      var idx = state.selectedNpcs.indexOf(name);
      if (idx !== -1) state.selectedNpcs.splice(idx, 1);
      else state.selectedNpcs.push(name);
    } else {
      // A plain click replaces the whole selection with this NPC; clicking
      // the sole selected one clears it.
      var wasSoleSelection = state.selectedNpcs.length === 1 && state.selectedNpcs[0] === name;
      state.selectedNpcs = wasSoleSelection ? [] : [name];
    }
    rerenderChart(lastData);
    renderNpcRow(currentNpcs());
    renderItemList(currentItems());
  });

  document.getElementById('lootBarBars').addEventListener('click', function (e) {
    // Matched against the outline/fill themselves, not the whole
    // .loot-bar-col (full plot height), so only the rendered bar shape hits.
    // A zero-value bucket renders at 0% height and does nothing here; see
    // the outside-click handler below.
    var bar = e.target.closest('.loot-bar-outline, .loot-bar-fill');
    var col = bar && bar.closest('.loot-bar-col');
    if (!col || !lastData) return;
    var idx = parseInt(col.getAttribute('data-bucket-index'), 10);
    var b = (lastData.buckets || [])[idx];
    if (!b) return;
    // Toggle-off is keyed on index, not start/end, since polls drift those
    // (see selectedBucket in state).
    var alreadySelected = state.selectedBucket && state.selectedBucket.index === idx;
    if (alreadySelected) {
      // Clicking the selected bar clears back to the whole range, like
      // re-clicking the sole selected NPC.
      clearSelectedBucket();
    } else {
      // Scoping by time clears any NPC selection first (mirror of the
      // #lootNpcRow handler). value/killCount are captured too so the header
      // is correct before loadBucketData resolves; loadState keeps all four
      // current afterwards.
      state.selectedNpcs = [];
      state.selectedBucket = { start: b.start, end: b.end, value: b.value, killCount: b.killCount, index: idx };
      bucketData = null;
      loadBucketData();
    }
    rerenderChart(lastData);
    renderNpcRow(currentNpcs());
    renderItemList(currentItems());
  });
  // Any click that isn't on a bar clears a bucket selection. Skips clicks on
  // a bar itself, which its own handler owns (including toggle-off).
  document.addEventListener('click', function (e) {
    if (!state.selectedBucket) return;
    if (e.target.closest('.loot-bar-outline, .loot-bar-fill')) return;
    clearSelectedBucket();
    rerenderChart(lastData);
    renderNpcRow(currentNpcs());
    renderItemList(currentItems());
  });
  // Outside-click clear for NPC selections: anything that isn't a
  // .loot-npc-box clears it. Skips clicks on the box, which the #lootNpcRow
  // handler owns.
  document.addEventListener('click', function (e) {
    if (!state.selectedNpcs.length) return;
    if (e.target.closest('.loot-npc-box')) return;
    state.selectedNpcs = [];
    rerenderChart(lastData);
    renderNpcRow(currentNpcs());
    renderItemList(currentItems());
  });

  // CLEAR text button as in Storages Viewer's search box
  // (pmSearchClear/updateSearchClear in render_possessions): shown only
  // while the field has text. Shared styling in
  // .loot-search-group/.loot-search-clear (loot-tracker.css).
  var lootNpcSearchInput = document.getElementById('lootNpcSearch');
  var lootNpcSearchClear = document.getElementById('lootNpcSearchClear');
  function updateNpcSearchClear() {
    lootNpcSearchClear.style.display = lootNpcSearchInput.value ? '' : 'none';
  }
  lootNpcSearchInput.addEventListener('input', function (e) {
    state.npcSearch = e.target.value;
    updateNpcSearchClear();
    if (lastData) renderNpcRow(currentNpcs());
  });
  lootNpcSearchClear.addEventListener('click', function () {
    lootNpcSearchInput.value = '';
    state.npcSearch = '';
    updateNpcSearchClear();
    if (lastData) renderNpcRow(currentNpcs());
    // Keep focus on desktop to keep typing; on touch, blur so the on-screen
    // keyboard goes away.
    if (window.matchMedia('(hover: none)').matches) lootNpcSearchInput.blur();
    else lootNpcSearchInput.focus();
  });
  document.getElementById('lootNpcSortTabs').addEventListener('click', function (e) {
    var toggleBtn = e.target.closest('.loot-hide-toggle');
    if (toggleBtn) {
      state.npcShowHidden = !state.npcShowHidden;
      toggleBtn.classList.toggle('active', state.npcShowHidden);
      toggleBtn.setAttribute('data-tooltip', (state.npcShowHidden ? 'Hide hidden' : 'Show hidden') + ' NPCs');
      if (lastData) renderNpcRow(currentNpcs());
      return;
    }
    var btn = e.target.closest('.loot-sort-tab');
    if (!btn || !lastData) return;
    var metric = btn.getAttribute('data-sort-metric');
    var current = splitSort(state.npcSort);
    var dir = metric === current.metric ? (current.dir === 'asc' ? 'desc' : 'asc') : (SORT_METRIC_DEFAULT_DIR[metric] || 'desc');
    state.npcSort = metric + '-' + dir;
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
  // Same CLEAR button as the NPC search box.
  // On touch, taps on the date range picker, share icon and link button,
  // sort buttons and eye buttons (show-hidden toggles and per-tile) show no
  // tooltip; all others do. Read by the shared tooltip script in _shell.
  window.myscapeTouchTooltipFilter = function (el) {
    return !(el.closest && el.closest(
      '.loot-share-icon-btn, .loot-share-link-btn, .loot-sort-tab, .loot-hide-toggle, .loot-eye-btn, .loot-range-btn'
    ));
  };
  var lootItemSearchInput = document.getElementById('lootItemSearch');
  var lootItemSearchClear = document.getElementById('lootItemSearchClear');
  function updateItemSearchClear() {
    lootItemSearchClear.style.display = lootItemSearchInput.value ? '' : 'none';
  }
  lootItemSearchInput.addEventListener('input', function (e) {
    state.itemSearch = e.target.value;
    updateItemSearchClear();
    renderItemList(currentItems());
  });
  lootItemSearchClear.addEventListener('click', function () {
    lootItemSearchInput.value = '';
    state.itemSearch = '';
    updateItemSearchClear();
    renderItemList(currentItems());
    // Same as the NPC box's CLEAR.
    if (window.matchMedia('(hover: none)').matches) lootItemSearchInput.blur();
    else lootItemSearchInput.focus();
  });
  document.getElementById('lootItemSortTabs').addEventListener('click', function (e) {
    var toggleBtn = e.target.closest('.loot-hide-toggle');
    if (toggleBtn) {
      state.itemShowHidden = !state.itemShowHidden;
      toggleBtn.classList.toggle('active', state.itemShowHidden);
      toggleBtn.setAttribute('data-tooltip', (state.itemShowHidden ? 'Hide hidden' : 'Show hidden') + ' items');
      renderItemList(currentItems());
      return;
    }
    var btn = e.target.closest('.loot-sort-tab');
    if (!btn) return;
    var metric = btn.getAttribute('data-sort-metric');
    var current = splitSort(state.itemSort);
    var dir = metric === current.metric ? (current.dir === 'asc' ? 'desc' : 'asc') : (SORT_METRIC_DEFAULT_DIR[metric] || 'desc');
    state.itemSort = metric + '-' + dir;
    updateSortTabs('lootItemSortTabs', state.itemSort);
    renderItemList(currentItems());
  });
  updateSortTabs('lootNpcSortTabs', state.npcSort);
  updateSortTabs('lootItemSortTabs', state.itemSort);

  // Range button (presets + CUSTOM date pair)
  // Picking a preset applies and reloads immediately; CUSTOM reveals two
  // date inputs + Apply inline, and nothing changes until Apply with both
  // dates filled.

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
    // Gold-highlighted (.loot-range-btn.active) while its dropdown is open.
    // Every close path goes through closeRangeMenu, which un-highlights, so
    // only the open path sets it.
    this.classList.toggle('active', opening);
  });
  document.addEventListener('click', function (e) {
    var wrap = document.getElementById('lootChartRange');
    if (wrap && !wrap.contains(e.target)) closeRangeMenu();
  });
  // Typed 'YYYY-MM-DD' text fields rather than native date pickers. The 'd'
  // slots are masked live (digits only, fixed dashes, unfilled slots shown
  // as "_"), and isValidIsoDate rejects impossible dates like "2024-13-40".
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

  // Blank means no digits typed: an empty string or the all-underscores
  // skeleton (value="____-__-__" in the HTML).
  function isBlankMaskValue(s) {
    return digitsOnly(s).length === 0;
  }

  function applyDateMask(input) {
    var digits = digitsOnly(input.value);
    input.value = maskValueFromDigits(digits);
    // Cursor lands after the last filled digit, so typing/backspacing edits
    // from the end. Editing a digit mid-date isn't supported; clear and
    // retype.
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
    // A picked bar belongs to the range it was clicked in; switching ranges
    // invalidates it, like an NPC selection.
    clearSelectedBucket();
    // A link generated for the previous range would go stale; see
    // resetLootShareState.
    resetLootShareState();
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
    resetLootShareState();
    closeRangeMenu();
    updateRangeMenuActive();
    loadState();
  }
  document.getElementById('lootRangeApply').addEventListener('click', applyCustomRange);
  // Enter applies from either field.
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

  // A clicked bar's scoped request: same endpoint as lootUrl, with
  // range=custom and the bucket's exact start/end as full ISO timestamps
  // (parse_loot_range_bound in app/loot.py accepts these). bucket.end is the
  // next bucket's start (exclusive, see build_loot_state) but the endpoint's
  // end bound is inclusive, so back off 1ms to avoid double-counting a
  // boundary event.
  function bucketUrl(bucket) {
    var params = new URLSearchParams();
    params.set('range', 'custom');
    params.set('start', bucket.start);
    params.set('end', new Date(new Date(bucket.end).getTime() - 1).toISOString());
    return '/api/players/me/loot?' + params.toString();
  }

  // Fetches bucketData for the selected bucket: once after a bar click, then
  // on every loadState poll (a bucket including "now" can gain kills). Fails
  // quietly rather than showing lootError, since it refines a page that is
  // already showing something.
  async function loadBucketData() {
    if (!state.selectedBucket) return;
    var token = ++bucketFetchToken;
    try {
      var res = await fetch(bucketUrl(state.selectedBucket));
      if (!res.ok || token !== bucketFetchToken) return;
      var data = await res.json();
      // A newer click or a deselect may have landed meanwhile; discard
      // rather than clobber.
      if (token !== bucketFetchToken) return;
      bucketData = data;
      renderNpcRow(currentNpcs());
      renderItemList(currentItems());
    } catch (err) {
      // Quiet; see this function's doc comment.
    }
  }

  // Clears a bucket selection back to the whole range. Shared by the
  // #lootBarBars toggle-off and every scope change (new NPC, new
  // range/CUSTOM), which also reset state.selectedNpcs.
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

      // Drop any selected NPC that aged out of the range (a rolling preset
      // like 24 HOURS) or is now hidden with the NPC panel's toggle off (see
      // npcEffectiveHidden); its tile is gone, so it can't be clicked back.
      // Falls back to "all sources" only if every selected NPC did.
      var rangeNpcs = data.windowNpcs || [];
      state.selectedNpcs = state.selectedNpcs.filter(function (name) {
        var stillPresent = rangeNpcs.filter(function (n) { return n.sourceName === name; })[0];
        return stillPresent && (state.npcShowHidden || !npcEffectiveHidden(stillPresent));
      });

      // A selected bar stays pinned to its index: rolling presets' buckets
      // drift every 10s poll (width is span/count, not calendar-aligned; see
      // _bucket_plan in app/loot.py), so start/end/value/killCount are
      // re-read from whatever bucket now sits at that index. Clears the
      // selection if the index no longer exists (safety net; bucket-count
      // changes already clear it).
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
      // Keeps the selected bucket's panel data on the same 10s cadence;
      // quiet on failure (see loadBucketData).
      if (state.selectedBucket) loadBucketData();
    } catch (err) {
      errorEl.textContent = 'Something went wrong loading your loot.';
      errorEl.classList.add('show');
    }
  }

  // Share icon: floating popup under the button (.loot-share-wrap,
  // loot-tracker.css), closed by re-clicking or clicking elsewhere. Mirrors
  // the Storages Viewer's setSettingsMenuOpen (app/pages/) as
  // setLootShareOpen; nothing is fetched on open. Null-guarded because
  // render_loot_tracker_share strips the icon's <h2> from the body before
  // this script runs (a share visitor isn't the owner).
  var lootShareIconBtn = document.getElementById('lootShareIconBtn');
  var lootShareCard = document.getElementById('lootShareCard');
  if (lootShareIconBtn) {
    function setLootShareOpen(open) {
      lootShareCard.hidden = !open;
      lootShareIconBtn.classList.toggle('open', open);
    }
    lootShareIconBtn.addEventListener('click', function () {
      setLootShareOpen(lootShareCard.hidden);
    });
    document.addEventListener('click', function (e) {
      var wrap = document.querySelector('.loot-share-wrap');
      if (wrap && !wrap.contains(e.target)) setLootShareOpen(false);
    });
  }

  // Resets the share card (GENERATE SHAREABLE LINK shown, any generated link
  // hidden). Called from both range-change paths (preset click and CUSTOM
  // Apply) when state.rangeKey/customStart/customEnd actually change, so an
  // old link never looks current for a new range. Not called when merely
  // toggling the card, polling, or clicking a bucket: only a range change
  // invalidates a link. Regenerating for the same range is still one click
  // away.
  function resetLootShareState() {
    var genBtn = document.getElementById('lootShareGenerateBtn');
    var linkBtn = document.getElementById('lootShareLinkBtn');
    // Both null on the share page and the landing preview, whose wrapper
    // scripts strip .loot-share-wrap (see
    // render_loot_tracker_share/render_landing_loot_preview); this script
    // runs unmodified on both.
    if (!genBtn || !linkBtn) return;
    genBtn.hidden = false;
    genBtn.disabled = false;
    genBtn.classList.remove('action-failed');
    linkBtn.hidden = true;
    linkBtn.textContent = '';
    delete linkBtn.dataset.url;
  }

  // GENERATE SHAREABLE LINK: snapshots the current range
  // (state.rangeKey/customStart/customEnd, as lootUrl() reads). Only this
  // click generates; afterwards lootShareLinkBtn replaces the button until
  // resetLootShareState restores it on a range change. See
  // build_loot_share_snapshot in app/loot.py and SharedContent in
  // app/models.py. Null-guarded: on the share and landing-preview pages the
  // button is stripped, and an unguarded addEventListener would throw and
  // halt the IIFE, leaving loadState()/setInterval unrun and the page stuck
  // on "Loading...".
  var lootShareGenerateBtn = document.getElementById('lootShareGenerateBtn');
  if (lootShareGenerateBtn) {
    lootShareGenerateBtn.addEventListener('click', function () {
      var btn = this;
      btn.disabled = true;
      var body = { range: state.rangeKey };
      if (state.rangeKey === 'custom' && state.customStart && state.customEnd) {
        body.start = state.customStart;
        body.end = state.customEnd;
      }
      fetch('/api/players/me/loot/share', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
        .then(function (res) { return res.ok ? res.json() : Promise.reject(); })
        .then(function (data) {
          var linkBtn = document.getElementById('lootShareLinkBtn');
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

  // lootShareLinkBtn is the link once generated: click copies data-url
  // (textContent swaps to "COPIED" and back) and flashes "COPIED", like the
  // Account page's .shared-link-code-btn handler (app/pages/).
  // Null-guarded like lootShareGenerateBtn.
  var lootShareLinkBtn = document.getElementById('lootShareLinkBtn');
  if (lootShareLinkBtn) {
    lootShareLinkBtn.addEventListener('click', function () {
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

  loadState();
  setInterval(loadState, 10000);
})();

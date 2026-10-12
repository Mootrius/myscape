(function () {
  function formatInt(n) {
    return Math.round(n || 0).toLocaleString('en-US');
  }
  // Like formatInt but without thousands separators (combat/total level).
  function formatIntPlain(n) {
    return String(Math.round(n || 0));
  }
  function setStat(key, text) {
    var el = document.getElementById('co-' + key);
    if (el) el.textContent = text;
  }
  function setFraction(key, completed, total) {
    if (completed == null || total == null) return;
    setStat(key, formatInt(completed) + ' / ' + formatInt(total));
  }
  // (icon url, label) per GameAccount.account_type code, see
  // _ACCOUNT_TYPE_INFO in app/pages/. The accountType tile is the only one
  // whose icon is swapped; MAIN's coin icon is the pre-fetch default.
  var ACCOUNT_TYPE_INFO = __ACCOUNT_TYPE_INFO_JSON__;
  function setAccountType(code) {
    var info = code != null ? ACCOUNT_TYPE_INFO[code] : null;
    if (!info) return;
    var icon = document.getElementById('co-icon-accountType');
    if (icon) {
      icon.src = info[0];
      icon.alt = info[1];
      // data-tooltip is not swapped: it always reads the fixed "Account
      // type" label from the static markup (stat_tiles).
    }
    setStat('accountType', info[1]);
  }
  // OSRS xp-per-level curve for levels 1-126 (virtual levels past 99): xp(L)
  // = floor(1/4 * sum[l=1..L-1] of floor(l + 300*2^(l/7))), see
  // https://oldschool.runescape.wiki/w/Experience. Duplicated from
  // SKILL_XP_TABLE in Mindmaps' script. Index 0 is unused; SKILL_XP_TABLE[1]
  // is 0.
  var SKILL_XP_TABLE = (function () {
    var table = [0, 0];
    var cumulative = 0;
    for (var l = 1; l < 126; l++) {
      cumulative += Math.floor(l + 300 * Math.pow(2, l / 7));
      table[l + 1] = Math.floor(cumulative / 4);
    }
    return table;
  })();
  // Largest (virtual) level whose requirement is at or below xp, like
  // levelForXp in Mindmaps' script. Used instead of GameAccount.skills'
  // capped level so maxed skills read 126.
  function levelForXp(xp) {
    for (var l = 126; l >= 1; l--) {
      if (xp >= SKILL_XP_TABLE[l]) return l;
    }
    return 1;
  }
  function setSkillLevel(key, xp) {
    if (xp == null) return;
    var el = document.getElementById('skill-' + key);
    if (el) el.textContent = String(levelForXp(xp));
  }
  // Appends XP to the cell's data-tooltip (skill name from skill_cells in
  // app/pages/) with the usual middle-dot join.
  function setSkillTooltip(key, xp) {
    var el = document.getElementById('skill-cell-' + key);
    if (!el) return;
    var name = key.charAt(0).toUpperCase() + key.slice(1);
    el.setAttribute('data-tooltip', xp != null ? name + ' · ' + formatInt(xp) + ' xp' : name);
  }

  fetch('/api/character-overview/summary')
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) {
      if (!data) return;
      // The shuffled background is saved on the account (the shuffle button
      // POSTs it) so all devices agree; localStorage only covers first
      // paint. The pending value covers this response arriving before the
      // viewer's module script runs (__myscapePendingModelViewerBg).
      if (typeof data.modelViewerBackgroundIndex === 'number') {
        window.__myscapePendingModelViewerBg = data.modelViewerBackgroundIndex;
        if (typeof window.myscapeApplyModelViewerBackground === 'function') {
          window.myscapeApplyModelViewerBackground(data.modelViewerBackgroundIndex);
        }
      }
      setAccountType(data.accountType);
      if (data.combatLevel != null) setStat('combatLevel', formatIntPlain(data.combatLevel));
      if (data.totalLevel != null) setStat('totalLevel', formatIntPlain(data.totalLevel));
      if (data.totalXp != null) setStat('totalXp', formatInt(data.totalXp) + ' xp');
      setFraction('quests', data.questsCompleted, data.questsTotal);
      setFraction('achievements', data.achievementsCompleted, data.achievementsTotal);
      setFraction('combatTasks', data.combatTasksCompleted, data.combatTasksTotal);
      setFraction('collections', data.collectionsCompleted, data.collectionsTotal);
    })
    .catch(function () { /* leave this row's em dashes showing */ });

  // Same GameAccount.skills snapshot the Mindmaps/Goal Tracking skill picker
  // reads (/api/players/me/skills in app/main.py).
  fetch('/api/players/me/skills')
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) {
      if (!data || !data.skills) return;
      Object.keys(data.skills).forEach(function (key) {
        var entry = data.skills[key];
        if (!entry) return;
        setSkillLevel(key, entry.xp);
        setSkillTooltip(key, entry.xp);
      });
    })
    .catch(function () { /* leave this card's em dashes showing */ });

  // Collection Log (GET /api/players/me/collection-log)

  // Quests / Achievement Diaries / Combat Achievements: one GET
  // /api/character-overview/progress feeds all three .co-quad-row cards (see
  // its docstring in app/main.py).

  // Same convention as the Mindmaps goal editor's diary-area search
  // (render_mindmaps); duplicated since the page scripts are independent.
  var DIARY_AREA_LABELS = {
    ardougne: 'Ardougne', desert: 'Desert', falador: 'Falador',
    fremennik: 'Fremennik', kandarin: 'Kandarin', karamja: 'Karamja',
    kourend_kebos: 'Kourend & Kebos', lumbridge_draynor: 'Lumbridge & Draynor',
    morytania: 'Morytania', varrock: 'Varrock',
    western_provinces: 'Western Provinces', wilderness: 'Wilderness',
  };
  // Each area's "Main reward" icon per tier (easy/medium/hard/elite,
  // matching DIARY_TIER_ORDER); renderDiaries picks the highest completed
  // tier. URLs come from the Main Reward column of the wiki's
  // Achievement_Diary "List of diaries" table, which is the only place all
  // 48 icons are available.
  var DIARY_AREA_TIER_ICON = {
    ardougne: [
      'https://oldschool.runescape.wiki/images/Ardougne_cloak_1.png',
      'https://oldschool.runescape.wiki/images/Ardougne_cloak_2.png',
      'https://oldschool.runescape.wiki/images/Ardougne_cloak_3.png',
      'https://oldschool.runescape.wiki/images/Ardougne_cloak_4.png',
    ],
    desert: [
      'https://oldschool.runescape.wiki/images/Desert_amulet_1.png',
      'https://oldschool.runescape.wiki/images/Desert_amulet_2.png',
      'https://oldschool.runescape.wiki/images/Desert_amulet_3.png',
      'https://oldschool.runescape.wiki/images/Desert_amulet_4.png',
    ],
    falador: [
      'https://oldschool.runescape.wiki/images/Falador_shield_1.png',
      'https://oldschool.runescape.wiki/images/Falador_shield_2.png',
      'https://oldschool.runescape.wiki/images/Falador_shield_3.png',
      'https://oldschool.runescape.wiki/images/Falador_shield_4.png',
    ],
    fremennik: [
      'https://oldschool.runescape.wiki/images/Fremennik_sea_boots_1.png',
      'https://oldschool.runescape.wiki/images/Fremennik_sea_boots_2.png',
      'https://oldschool.runescape.wiki/images/Fremennik_sea_boots_3.png',
      'https://oldschool.runescape.wiki/images/Fremennik_sea_boots_4.png',
    ],
    kandarin: [
      'https://oldschool.runescape.wiki/images/Kandarin_headgear_1.png',
      'https://oldschool.runescape.wiki/images/Kandarin_headgear_2.png',
      'https://oldschool.runescape.wiki/images/Kandarin_headgear_3.png',
      'https://oldschool.runescape.wiki/images/Kandarin_headgear_4.png',
    ],
    karamja: [
      'https://oldschool.runescape.wiki/images/Karamja_gloves_1.png',
      'https://oldschool.runescape.wiki/images/Karamja_gloves_2.png',
      'https://oldschool.runescape.wiki/images/Karamja_gloves_3.png',
      'https://oldschool.runescape.wiki/images/Karamja_gloves_4.png',
    ],
    kourend_kebos: [
      "https://oldschool.runescape.wiki/images/Rada%27s_blessing_1.png",
      "https://oldschool.runescape.wiki/images/Rada%27s_blessing_2.png",
      "https://oldschool.runescape.wiki/images/Rada%27s_blessing_3.png",
      "https://oldschool.runescape.wiki/images/Rada%27s_blessing_4.png",
    ],
    lumbridge_draynor: [
      "https://oldschool.runescape.wiki/images/Explorer%27s_ring_1.png",
      "https://oldschool.runescape.wiki/images/Explorer%27s_ring_2.png",
      "https://oldschool.runescape.wiki/images/Explorer%27s_ring_3.png",
      "https://oldschool.runescape.wiki/images/Explorer%27s_ring_4.png",
    ],
    morytania: [
      'https://oldschool.runescape.wiki/images/Morytania_legs_1.png',
      'https://oldschool.runescape.wiki/images/Morytania_legs_2.png',
      'https://oldschool.runescape.wiki/images/Morytania_legs_3.png',
      'https://oldschool.runescape.wiki/images/Morytania_legs_4.png',
    ],
    varrock: [
      'https://oldschool.runescape.wiki/images/Varrock_armour_1.png',
      'https://oldschool.runescape.wiki/images/Varrock_armour_2.png',
      'https://oldschool.runescape.wiki/images/Varrock_armour_3.png',
      'https://oldschool.runescape.wiki/images/Varrock_armour_4.png',
    ],
    western_provinces: [
      'https://oldschool.runescape.wiki/images/Western_banner_1.png',
      'https://oldschool.runescape.wiki/images/Western_banner_2.png',
      'https://oldschool.runescape.wiki/images/Western_banner_3.png',
      'https://oldschool.runescape.wiki/images/Western_banner_4.png',
    ],
    wilderness: [
      'https://oldschool.runescape.wiki/images/Wilderness_sword_1.png',
      'https://oldschool.runescape.wiki/images/Wilderness_sword_2.png',
      'https://oldschool.runescape.wiki/images/Wilderness_sword_3.png',
      'https://oldschool.runescape.wiki/images/Wilderness_sword_4.png',
    ],
  };
  // Shown for an area with zero tiers completed; saved locally at
  // app/static/img/diary-not-started.png.
  var DIARY_AREA_NOT_STARTED_ICON = '/static/img/diary-not-started.png';
  // In-game area order (matches the journal's tabs), not the alphabetical
  // order DIARY_AREAS/get_diary_tier_totals iterate in.
  var DIARY_AREA_ORDER = [
    'ardougne', 'desert', 'falador', 'fremennik', 'kandarin', 'karamja',
    'kourend_kebos', 'lumbridge_draynor', 'morytania', 'varrock',
    'western_provinces', 'wilderness',
  ];
  var DIARY_TIER_ORDER = ['easy', 'medium', 'hard', 'elite'];
  var CA_TIER_ORDER = ['easy', 'medium', 'hard', 'elite', 'master', 'grandmaster'];
  function titleCase(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function questWikiUrl(name) {
    return 'https://oldschool.runescape.wiki/w/' + encodeURIComponent(String(name).replace(/ /g, '_'));
  }
  function renderQuests(quests) {
    var listEl = document.getElementById('questsList');
    var emptyEl = document.getElementById('questsEmpty');
    if (!listEl || !quests) return;
    var groups = [['Free Quests', quests.free], ["Members' Quests", quests.members], ['Miniquests', quests.miniquests]];
    var html = '';
    groups.forEach(function (group) {
      var label = group[0];
      var items = group[1] || [];
      if (!items.length) return;
      html += '<div class="quests-group-title">' + escapeHtml(label) + '</div>';
      items.forEach(function (q) {
        html += '<a class="quest-row quest-row--' + q.state + '" href="' + questWikiUrl(q.name) + '" target="_blank" rel="noopener">' + escapeHtml(q.name) + '</a>';
      });
    });
    listEl.innerHTML = html;
    if (emptyEl) emptyEl.hidden = html.length > 0;
  }

  // Same convention as questWikiUrl: spaces become underscores before
  // encodeURIComponent (so "&" in "Kourend & Kebos" comes out %26).
  function diaryWikiUrl(area) {
    var label = DIARY_AREA_LABELS[area] || titleCase(area);
    return 'https://oldschool.runescape.wiki/w/' + encodeURIComponent(label.replace(/ /g, '_')) + '_Diary';
  }

  function renderDiaries(diaries) {
    var listEl = document.getElementById('diariesList');
    if (!listEl || !Array.isArray(diaries)) return;
    var byArea = {};
    diaries.forEach(function (d) { byArea[d.area] = d; });
    var html = '';
    DIARY_AREA_ORDER.forEach(function (area) {
      var d = byArea[area];
      if (!d) return;
      // Highest completed tier picks the reward icon (DIARY_TIER_ORDER is
      // easy->elite, so the last match wins). -1 means no tiers completed.
      var highestCompletedIndex = -1;
      DIARY_TIER_ORDER.forEach(function (tier, i) {
        if (d.tiers && d.tiers[tier] === 'completed') highestCompletedIndex = i;
      });
      var icon = highestCompletedIndex >= 0
        ? (DIARY_AREA_TIER_ICON[area] || [])[highestCompletedIndex]
        : DIARY_AREA_NOT_STARTED_ICON;
      var label = DIARY_AREA_LABELS[area] || titleCase(area);
      html += '<a class="diary-row" href="' + diaryWikiUrl(area) + '" target="_blank" rel="noopener">'
        + '<div class="diary-row-header">'
        + '<img class="diary-row-icon" src="' + icon + '" alt="" />'
        + '<span class="diary-row-label">' + escapeHtml(label) + '</span>'
        + '<span class="diary-row-count">' + d.completed + '/' + d.total + '</span>'
        + '</div>'
        + '<div class="diary-row-bar">'
        + DIARY_TIER_ORDER.map(function (tier) {
            var state = (d.tiers && d.tiers[tier]) || 'not_completed';
            return '<div class="diary-tier-seg' + (state === 'completed' ? ' diary-tier-seg--completed' : '') + '"></div>';
          }).join('')
        + '</div>'
        + '</a>';
    });
    listEl.innerHTML = html;
  }

  function renderCombatAchievements(items) {
    var listEl = document.getElementById('caList');
    if (!listEl || !Array.isArray(items)) return;
    var byTier = {};
    items.forEach(function (item) { byTier[item.tier] = item; });
    var html = '';
    CA_TIER_ORDER.forEach(function (tier) {
      var item = byTier[tier];
      if (!item) return;
      var completed = item.completed;
      var total = item.total;
      var pct = (completed != null && total) ? Math.min(100, (completed / total) * 100) : 0;
      html += '<a class="ca-tile" href="https://oldschool.runescape.wiki/w/Combat_Achievements/' + titleCase(tier) + '" target="_blank" rel="noopener">'
        + '<span class="ca-tile-label">' + titleCase(tier) + '</span>'
        + '<img class="ca-tile-icon" src="/static/img/combat-achievement-tiers/' + tier + '.png" alt="" />'
        + '<span class="ca-tile-count">' + (completed != null ? completed : '—') + '/' + total + '</span>'
        + '<div class="ca-tile-bar"><div class="ca-tile-bar-fill" style="width: ' + pct + '%"></div></div>'
        + '</a>';
    });
    listEl.innerHTML = html;
  }

  fetch('/api/character-overview/progress')
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) {
      if (!data) return;
      renderQuests(data.quests);
      renderDiaries(data.diaries);
      renderCombatAchievements(data.combatAchievements);
    })
    .catch(function () { /* leave each card's own empty/em-dash state showing */ });

  // Collection Log (GET /api/players/me/collection-log): tabs -> pages ->
  // items from the static schema (get_collection_log_tabs in
  // app/collectionlog.py) plus the obtained-item map
  // (GameAccount.collection_log_items, {item id string: quantity}, captured
  // by CollectionLogItemCapture in the Mootrius/myscape-plugin repo).
  // Rendered client-side.
  var clogCard = document.getElementById('clogCard');
  var clogEmpty = document.getElementById('clogEmpty');
  var clogBody = document.getElementById('clogBody');
  var clogTabsEl = document.getElementById('clogTabs');
  var clogPagesEl = document.getElementById('clogPages');
  var clogItemsEl = document.getElementById('clogItems');
  var clogItemsHeaderEl = document.getElementById('clogItemsHeader');
  var clogSyncBtn = document.getElementById('clogSyncBtn');

  var clogTabs = [];
  var clogObtained = {};
  // page name -> array of kill/completion counts
  // (collection_log_page_kill_counts in app/bosses.py; see
  // read_collection_log in app/main.py). Only boss/raid/clue pages have
  // entries; absent means no count shown. Several elements mean a combo page
  // (twin bosses, normal/hard-mode raids), see renderClogItemsHeader.
  var clogKillCounts = {};
  var clogActiveTab = 0;
  var clogActivePage = 0;

  // Same RuneLite item-icon CDN as item_icon_url in app/purchase_goals.py;
  // built from the bare numeric id since get_collection_log_tabs returns
  // bare ids.
  function clogIconUrl(itemId) {
    return 'https://static.runelite.net/cache/item/icon/' + itemId + '.png';
  }

  // Item ids repeat across pages (~205 do, e.g. clue rewards on several
  // tiers), so totals must dedupe by id rather than sum list lengths. Used
  // for the grand total and each tab's count.
  function clogUniqueIds(items) {
    var seen = {};
    var ids = [];
    items.forEach(function (item) {
      if (!seen[item.id]) { seen[item.id] = true; ids.push(item.id); }
    });
    return ids;
  }

  function clogObtainedCount(ids) {
    var count = 0;
    ids.forEach(function (id) { if (clogObtained[String(id)] != null) count++; });
    return count;
  }

  // Phone width: the tab strip scrolls sideways, and these classes drive the
  // edge fade and arrow (.clog-tabs-wrap in character-overview.css). Never
  // set on desktop.
  var clogTabsWrapEl = document.getElementById('clogTabsWrap');
  function updateClogTabsFade() {
    if (!clogTabsWrapEl) return;
    var max = clogTabsEl.scrollWidth - clogTabsEl.clientWidth;
    clogTabsWrapEl.classList.toggle('can-scroll-left', clogTabsEl.scrollLeft > 2);
    clogTabsWrapEl.classList.toggle('can-scroll-right', clogTabsEl.scrollLeft < max - 2);
  }
  clogTabsEl.addEventListener('scroll', updateClogTabsFade, { passive: true });
  window.addEventListener('resize', updateClogTabsFade);

  function renderClogTabs() {
    // Emptying the strip collapses it and would reset the scroll to the
    // first tab, so the scroll position is kept across the rebuild.
    var keepScrollLeft = clogTabsEl.scrollLeft;
    clogTabsEl.innerHTML = '';
    clogTabs.forEach(function (tab, tabIndex) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'clog-tab' + (tabIndex === clogActiveTab ? ' active' : '');
      btn.textContent = tab.name;
      btn.addEventListener('click', function () {
        clogActiveTab = tabIndex;
        clogActivePage = 0;
        renderClogTabs();
        renderClogPages();
        renderClogItems();
        renderClogItemsHeader();
        // Switching tabs resets to the first page and scrolls both panes to
        // the top. Replacing innerHTML doesn't do this since scrollTop lives
        // on clogPagesEl/clogItemsEl, which persist.
        clogPagesEl.scrollTop = 0;
        clogItemsEl.scrollTop = 0;
      });
      clogTabsEl.appendChild(btn);
    });
    clogTabsEl.scrollLeft = keepScrollLeft;
    updateClogTabsFade();
  }

  function renderClogPages() {
    clogPagesEl.innerHTML = '';
    var tab = clogTabs[clogActiveTab];
    if (!tab) return;
    tab.pages.forEach(function (page, pageIndex) {
      var obtainedCount = clogObtainedCount(clogUniqueIds(page.items));
      // Red/yellow/green by progress; a 0/0 page reads as complete.
      var progressState = obtainedCount === page.items.length ? 'complete'
        : obtainedCount === 0 ? 'zero'
        : 'started';
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'clog-page-btn ' + progressState
        + (pageIndex === clogActivePage ? ' active' : '');
      var label = document.createElement('span');
      label.textContent = page.name;
      var count = document.createElement('span');
      count.className = 'clog-page-count';
      count.textContent = formatInt(obtainedCount) + '/' + formatInt(page.items.length);
      btn.appendChild(label);
      btn.appendChild(count);
      btn.addEventListener('click', function () {
        clogActivePage = pageIndex;
        renderClogPages();
        renderClogItems();
        renderClogItemsHeader();
        // Reset the items grid to the top for the new page. .clog-pages
        // keeps its scroll position (unlike a tab switch) since the page
        // list stays the same.
        clogItemsEl.scrollTop = 0;
      });
      clogPagesEl.appendChild(btn);
    });
  }

  // Same wiki-URL shape as itemWikiUrl (gear slots); each render_* script is
  // independent, so it is a local copy.
  function clogItemWikiUrl(itemName) {
    return 'https://oldschool.runescape.wiki/w/' + encodeURIComponent(String(itemName).replace(/ /g, '_'));
  }
  function renderClogItems() {
    clogItemsEl.innerHTML = '';
    var tab = clogTabs[clogActiveTab];
    var page = tab && tab.pages[clogActivePage];
    if (!page) return;
    page.items.forEach(function (item) {
      var qty = clogObtained[String(item.id)];
      var tile = document.createElement('a');
      tile.className = 'clog-item' + (qty != null ? ' obtained' : '');
      tile.href = clogItemWikiUrl(item.name);
      tile.target = '_blank';
      tile.rel = 'noopener';
      // Site-styled tooltip (.myscape-tooltip in myscape.css, driven by
      // _shell's shared_script) with just the item name.
      tile.setAttribute('data-tooltip', item.name);
      var img = document.createElement('img');
      img.className = 'clog-item-icon';
      img.src = clogIconUrl(item.id);
      img.alt = '';
      img.loading = 'lazy';
      img.onerror = function () { img.style.display = 'none'; };
      tile.appendChild(img);
      if (qty != null && qty > 1) {
        var badge = document.createElement('div');
        badge.className = 'clog-item-qty';
        badge.textContent = formatInt(qty);
        tile.appendChild(badge);
      }
      clogItemsEl.appendChild(tile);
    });
  }

  // Active page's name + kill/completion count above the item grid. The
  // count is omitted when clogKillCounts has no entry. Pages with several
  // counts show them joined by a middot rather than summed (e.g. Callisto
  // and Artio). No personal-best time since nothing tracks one.
  function renderClogItemsHeader() {
    clogItemsHeaderEl.innerHTML = '';
    var tab = clogTabs[clogActiveTab];
    var page = tab && tab.pages[clogActivePage];
    if (!page) return;
    var name = document.createElement('span');
    name.className = 'clog-items-header-name';
    name.textContent = page.name;
    clogItemsHeaderEl.appendChild(name);
    var killCounts = clogKillCounts[page.name];
    if (killCounts != null && killCounts.length) {
      var kc = document.createElement('span');
      kc.className = 'clog-items-header-kc';
      kc.textContent = killCounts.map(formatInt).join(' \u00b7 ');
      clogItemsHeaderEl.appendChild(kc);
    }
  }

  // Same empty-state swap as showEmpty in the model viewer's module script;
  // only called once there is nothing to show.
  function showClogEmpty() {
    clogBody.style.display = 'none';
    clogEmpty.style.display = 'block';
  }

  // Locks .clog-pages/.clog-items height to .model-viewer-card's rendered
  // height instead of a fixed px value in CSS. The .clog-tabs height depends
  // on the RuneScapePlain11 web font's line-height (font-display: optional
  // in myscape.css), which varies with network, environment and browser, so
  // it is computed from the real boxes.
  var modelViewerCard = document.getElementById('modelViewerCard');
  function syncClogHeight() {
    if (!modelViewerCard || !clogCard || !clogPagesEl || !clogItemsEl || !clogItemsHeaderEl) return;
    // Phone layout (700px breakpoint, as in character-overview.css): the log
    // stacks below the viewer, so drop inline heights and use the
    // stylesheet's.
    if (window.matchMedia('(max-width: 700px)').matches) {
      clogPagesEl.style.height = '';
      clogItemsEl.style.height = '';
      return;
    }
    var modelBoxHeight = modelViewerCard.getBoundingClientRect().height;
    if (!modelBoxHeight) return;
    var clogCS = getComputedStyle(clogCard);
    // Read .clog-toolbar, not .clog-tabs: the toolbar (wrapping .clog-tabs +
    // .clog-sync-btn) carries the row's margin-bottom, so using .clog-tabs
    // would under-subtract 8px.
    var toolbarEl = clogCard.querySelector('.clog-toolbar');
    var toolbarCS = toolbarEl ? getComputedStyle(toolbarEl) : null;
    var panesHeight = modelBoxHeight
      - parseFloat(clogCS.paddingTop)
      - parseFloat(clogCS.paddingBottom)
      - parseFloat(clogCS.borderTopWidth)
      - parseFloat(clogCS.borderBottomWidth)
      - (toolbarEl ? toolbarEl.getBoundingClientRect().height : 0)
      - (toolbarCS ? parseFloat(toolbarCS.marginBottom) : 0);
    if (panesHeight > 0) {
      // .clog-pages has no header, so it gets the whole budget;
      // .clog-items-header eats only into .clog-items' share (see
      // .clog-items-col in character-overview.css).
      clogPagesEl.style.height = panesHeight + 'px';
      var headerCS = getComputedStyle(clogItemsHeaderEl);
      var itemsHeight = panesHeight
        - clogItemsHeaderEl.getBoundingClientRect().height
        - parseFloat(headerCS.marginBottom);
      if (itemsHeight > 0) {
        clogItemsEl.style.height = itemsHeight + 'px';
      }
    }
  }
  if (modelViewerCard && window.ResizeObserver) {
    new ResizeObserver(syncClogHeight).observe(modelViewerCard);
  } else {
    window.addEventListener('resize', syncClogHeight);
  }
  syncClogHeight();
  // Re-run once the web font swaps in (see font-display: optional in
  // myscape.css); ResizeObserver on modelViewerCard won't catch it since the
  // card's height is width-driven.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(syncClogHeight);
  }

  // Touch screens only show a tap tooltip for these: summary-row icons, the
  // model viewer info button, the Collection Log refresh button and item
  // tiles, Skills cells, and the PRIVATE/PUBLIC buttons in the
  // public-profile popup. Read by the shared tooltip script in _shell.
  window.myscapeTouchTooltipFilter = function (el) {
    return !!(el.closest && el.closest(
      '.co-summary-row, #mvInfoBtn, #clogSyncBtn, .clog-item, .skill-cell, ' +
      '#publicProfileSegPrivate, #publicProfileSegPublic'
    ));
  };

  // Tapping the summary-row icons or the viewer's info button a second time
  // dismisses their tooltip (same shared tooltip script).
  window.myscapeTouchTooltipToggle = function (el) {
    return !!(el.closest && el.closest('.co-summary-row, #mvInfoBtn'));
  };

  // Drawn scrollbars for the four scrolling lists (Collection Log pages +
  // items, Quests, Achievement Diaries), shown only at phone width; see
  // "Scrollbars on the scrolling lists" in character-overview.css. Always
  // built, CSS decides display. The thumb is sized from scrollTop and
  // draggable.
  (function () {
    function attach(list) {
      if (!list || !list.parentElement) return;
      var track = document.createElement('div');
      track.className = 'co-sb';
      track.setAttribute('aria-hidden', 'true');
      var thumb = document.createElement('div');
      thumb.className = 'co-sb-thumb';
      track.appendChild(thumb);
      list.parentElement.appendChild(track);

      var thumbH = 0;
      function update() {
        var ch = list.clientHeight;
        var sh = list.scrollHeight;
        var scrollable = ch > 0 && sh > ch + 1;
        track.classList.toggle('co-sb--on', scrollable);
        if (!scrollable) return;
        track.style.top = list.offsetTop + 'px';
        track.style.height = list.offsetHeight + 'px';
        track.style.left = (list.offsetLeft + list.offsetWidth - 16) + 'px';
        thumbH = Math.max(28, Math.round(ch * ch / sh));
        thumb.style.height = thumbH + 'px';
        var maxTop = list.offsetHeight - thumbH;
        var y = maxTop * list.scrollTop / (sh - ch);
        thumb.style.transform = 'translateY(' + Math.max(0, Math.min(maxTop, Math.round(y))) + 'px)';
      }
      list.addEventListener('scroll', update, { passive: true });
      window.addEventListener('resize', update);
      if (window.ResizeObserver) new ResizeObserver(update).observe(list);
      if (window.MutationObserver) new MutationObserver(update).observe(list, { childList: true });

      var dragStartY = 0;
      var dragStartScroll = 0;
      thumb.addEventListener('pointerdown', function (e) {
        dragStartY = e.clientY;
        dragStartScroll = list.scrollTop;
        thumb.classList.add('dragging');
        thumb.setPointerCapture(e.pointerId);
        e.preventDefault();
      });
      thumb.addEventListener('pointermove', function (e) {
        if (!thumb.classList.contains('dragging')) return;
        var travel = list.offsetHeight - thumbH;
        if (travel <= 0) return;
        list.scrollTop = dragStartScroll + (e.clientY - dragStartY) * (list.scrollHeight - list.clientHeight) / travel;
      });
      function endDrag() { thumb.classList.remove('dragging'); }
      thumb.addEventListener('pointerup', endDrag);
      thumb.addEventListener('pointercancel', endDrag);
      update();
    }
    ['clogPages', 'clogItems', 'questsList', 'diariesList'].forEach(function (id) {
      attach(document.getElementById(id));
    });
  })();

  // Named so the manual sync button can re-run it after a resync.
  function loadCollectionLog() {
    return fetch('/api/players/me/collection-log')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.syncedAt || !Array.isArray(data.tabs) || !data.tabs.length) {
          showClogEmpty();
          return;
        }
        clogTabs = data.tabs;
        clogObtained = data.obtainedItems || {};
        clogKillCounts = data.killCounts || {};
        renderClogTabs();
        renderClogPages();
        renderClogItems();
        renderClogItemsHeader();
        // Re-sync heights now that .clog-tabs and .clog-items-header have
        // content (both are 0px tall until now).
        syncClogHeight();
      })
      .catch(function () { showClogEmpty(); });
  }
  if (clogCard) {
    loadCollectionLog();
  }

  // Manual hiscores refresh for the counts renderClogItemsHeader shows. POST
  // /api/players/me/hiscores/sync is otherwise only triggered at link time
  // (sync_hiscores in app/hiscores.py), so later-added stats (e.g.
  // COLLECTION_LOG_CLUE_PAGE_TIERS in app/bosses.py) would stay empty. Only
  // clogKillCounts can change, so loadCollectionLog() is re-run.
  if (clogSyncBtn) {
    clogSyncBtn.addEventListener('click', function () {
      if (clogSyncBtn.disabled) return;
      clogSyncBtn.classList.remove('sync-failed');
      clogSyncBtn.disabled = true;
      clogSyncBtn.classList.add('syncing');
      fetch('/api/players/me/hiscores/sync', { method: 'POST' })
        .then(function (r) { return r.ok ? loadCollectionLog() : Promise.reject(); })
        .catch(function () {
          clogSyncBtn.classList.add('sync-failed');
          setTimeout(function () { clogSyncBtn.classList.remove('sync-failed'); }, 2500);
        })
        .then(function () {
          clogSyncBtn.disabled = false;
          clogSyncBtn.classList.remove('syncing');
        });
    });
  }

  // Public-profile settings card (#publicProfileCard). Absent in
  // preview/public_code mode (see publicProfileSettingsBtn in
  // render_character_overview); this guard makes that a no-op.
  var publicProfileSettingsBtn = document.getElementById('publicProfileSettingsBtn');
  if (publicProfileSettingsBtn) {
    var publicProfileCard = document.getElementById('publicProfileCard');
    var publicProfileSegBtns = [document.getElementById('publicProfileSegPrivate'), document.getElementById('publicProfileSegPublic')];
    var publicProfileLinkBtn = document.getElementById('publicProfileLinkBtn');
    var publicProfileRegenerateBtn = document.getElementById('publicProfileRegenerateBtn');

    // Collapsed by default; the cog toggles a floating popup under the
    // button (.co-settings-wrap). Mirrors the Storages Viewer's
    // pmSettingsBtn/pmSettingsMenu (setSettingsMenuOpen in app/pages/),
    // including the .active class and outside-click close. No refetch on
    // open since the initial GET already ran.
    function setPublicProfileOpen(open) {
      publicProfileCard.hidden = !open;
      publicProfileSettingsBtn.classList.toggle('active', open);
    }
    publicProfileSettingsBtn.addEventListener('click', function () {
      setPublicProfileOpen(publicProfileCard.hidden);
    });
    document.addEventListener('click', function (e) {
      var wrap = document.querySelector('.co-settings-wrap');
      if (wrap && !wrap.contains(e.target)) setPublicProfileOpen(false);
    });

    function applyPublicProfileState(data) {
      if (!data) return;
      var activeValue = data.isPublic ? 'public' : 'private';
      publicProfileSegBtns.forEach(function (btn) {
        btn.classList.toggle('active', btn.getAttribute('data-segment-value') === activeValue);
      });
      publicProfileLinkBtn.dataset.url = data.url || '';
      publicProfileLinkBtn.textContent = data.url || '';
      // A private page has no link to copy: the real disabled attribute (not
      // just styling) stops the click handler, matching
      // .public-profile-link-btn:disabled.
      publicProfileLinkBtn.disabled = !data.isPublic;
      // The data-tooltip attribute is removed while private, since "Click to
      // copy" would describe an action the disabled button can't do.
      if (data.isPublic) {
        publicProfileLinkBtn.setAttribute('data-tooltip', 'Click to copy');
      } else {
        publicProfileLinkBtn.removeAttribute('data-tooltip');
      }
    }

    fetch('/api/players/me/public-profile')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(applyPublicProfileState)
      .catch(function () { /* leave the segmented control at its default (Private) */ });

    publicProfileSegBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (btn.classList.contains('active')) return;
        var wantPublic = btn.getAttribute('data-segment-value') === 'public';
        publicProfileSegBtns.forEach(function (b) { b.disabled = true; });
        fetch('/api/players/me/public-profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ is_public: wantPublic }),
        })
          .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
          .then(applyPublicProfileState)
          .catch(function () {})
          .then(function () { publicProfileSegBtns.forEach(function (b) { b.disabled = false; }); });
      });
    });

    // The link display is the copy button, as in Loot Tracker's
    // lootShareLinkBtn (app/pages/) and the Account page's Shared Links
    // table. The URL is held in data-url since textContent swaps to "COPIED"
    // briefly.
    publicProfileLinkBtn.addEventListener('click', function () {
      var url = publicProfileLinkBtn.dataset.url;
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
      publicProfileLinkBtn.textContent = 'COPIED';
      setTimeout(function () { publicProfileLinkBtn.textContent = url; }, 1200);
    });

    // Server-side limit is once per day (regenerate_public_profile_code in
    // app/main.py); a 429 flashes the button red like the collection log's
    // hiscores-sync failure.
    publicProfileRegenerateBtn.addEventListener('click', function () {
      publicProfileRegenerateBtn.disabled = true;
      fetch('/api/players/me/public-profile/regenerate-code', { method: 'POST' })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
        .then(applyPublicProfileState)
        .catch(function () {
          publicProfileRegenerateBtn.classList.add('action-failed');
          setTimeout(function () { publicProfileRegenerateBtn.classList.remove('action-failed'); }, 2500);
        })
        .then(function () { publicProfileRegenerateBtn.disabled = false; });
    });
  }
})();

"""Goal Tracking: the page, its shared view, and the landing preview."""
import json
import os
from html import escape
from typing import TYPE_CHECKING, Optional, Tuple

from app.bosses import HISCORE_BOSSES
from app.mindmaps import SKILL_NAMES
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
        + """
    (function () {
      // Generic per-TYPE badge: used by the type-picker buttons and by item
      // goals' row icons. kc/skill rows use their boss/skill sprite (goalRowHtml
      // iconSrc).
      var TYPE_ICON = {
        kc: '/static/img/icon-goal-kc.png',
        skill: '/static/img/icon-goal-skill.png',
        item: '/static/img/icon-goal-item.png',
      };
      // Grouping order for the "Type" sort tab; same kc/skill/item order as
      // TYPE_ICON.
      var GOAL_TYPE_SORT_ORDER = { kc: 0, skill: 1, item: 2 };
      var TARGET_BOUNDS = {
        kc: { min: 1, max: 2147483647 },
        item: { min: 1, max: 2147483647 },
        skill_level: { min: 1, max: 126 },
        skill_xp: { min: 1, max: 200000000 },
      };


      function parseMoneySuffix(raw) {
        var s = (raw || '').trim().replace(/,/g, '');
        var m = /^([0-9]*\\.?[0-9]+)\\s*([kKmMbB])$/.exec(s);
        if (!m) return s;
        var mult = { k: 1e3, m: 1e6, b: 1e9 }[m[2].toLowerCase()];
        return String(Math.round(parseFloat(m[1]) * mult));
      }

      // Keeps only valid target-field characters (digits, commas, a decimal
      // point, k/m/b). Hence type="text" inputmode="decimal": a number input
      // cannot accept K/M/B.
      var NUMERIC_SUFFIX_DISALLOWED_RE = /[^0-9,.kKmMbB]/g;

      function filterNumericSuffixInput(input) {
        var cleaned = input.value.replace(NUMERIC_SUFFIX_DISALLOWED_RE, '');
        if (cleaned === input.value) return;
        var cursor = input.selectionStart;
        var keptBeforeCursor = input.value.slice(0, cursor).replace(NUMERIC_SUFFIX_DISALLOWED_RE, '').length;
        input.value = cleaned;
        input.setSelectionRange(keptBeforeCursor, keptBeforeCursor);
      }

      // OSRS xp-per-level curve for levels 1-126 including virtual levels
      // (https://oldschool.runescape.wiki/w/Experience): xp(L) = floor(1/4 *
      // sum[l=1..L-1] of floor(l + 300*2^(l/7))). SKILL_XP_TABLE[L] is the total
      // xp for level L; index 0 is unused.
      var SKILL_XP_TABLE = (function () {
        var maxLevel = TARGET_BOUNDS.skill_level.max;
        var table = [0, 0];
        var cumulative = 0;
        for (var l = 1; l < maxLevel; l++) {
          cumulative += Math.floor(l + 300 * Math.pow(2, l / 7));
          table[l + 1] = Math.floor(cumulative / 4);
        }
        return table;
      })();
      // The xp a level needs, clamped into range; used when the metric toggle
      // goes LVL to XP.
      function xpForLevel(level) {
        var b = TARGET_BOUNDS.skill_level;
        level = Math.max(b.min, Math.min(b.max, Math.round(level)));
        return SKILL_XP_TABLE[level];
      }
      // The largest level whose xp requirement is at or below the given xp
      // (5,750 xp is level 22); used when the toggle goes XP to LVL.
      function levelForXp(xp) {
        var b = TARGET_BOUNDS.skill_level;
        for (var l = b.max; l >= b.min; l--) {
          if (xp >= SKILL_XP_TABLE[l]) return l;
        }
        return b.min;
      }

      var GT = {
        goals: [],
        sortMode: 'alphabetical',
        wizardStage: 0,
        recurring: null, // null | 'one_time' | 'recurring' -- picked in stage 1
        type: null,
        skillMetric: 'level',
        itemId: null, // the chosen search result's real item id, if any -- see Goal.item_id's own docstring in app/models.py
        // GAIN/REACH for a one-time kc or xp-skill goal (#gtTargetModeToggle,
        // see targetModeApplies); defaults to 'gain' (Goal.baseline_value in
        // app/models.py). Not reset when switching away, so Back/Forward keeps
        // it; LEVEL -> XP resets it to 'gain'.
        targetMode: 'gain',
        recurInterval: '', // stage 4's own text field, kept here so re-rendering that stage (e.g. after Back then forward again) doesn't lose it
        recurUnit: 'day', // stage 4's own segmented-control selection
        recurStart: 'now', // stage 5's own NOW/CUSTOM segmented-control selection -- NOW by default, same "the simple choice is the default" convention GT.targetMode/GT.recurUnit already follow
        recurStartAt: '', // stage 5's own masked "YYYY-MM-DD HH:MM" text field, kept here for the same Back-then-forward reason GT.recurInterval is; only ever read when recurStart === 'custom'
        // sortMode + JSON of the goals last rendered; null until the first
        // render. Lets applyGoalsResponse skip an unchanged rebuild.
        renderKey: null,
      };
      var BOSS_NAMES = Object.keys(BOSS_SLUG_BY_NAME);

      function showError(msg) {
        var el = document.getElementById('gtError');
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

      function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
          return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
      }

      function fmtNum(n) { return Math.round(n || 0).toLocaleString('en-US'); }

      function debounce(fn, wait) {
        var t = null;
        return function () {
          var args = arguments;
          clearTimeout(t);
          t = setTimeout(function () { fn.apply(null, args); }, wait);
        };
      }

      // Add-goal wizard
      // Stages: 1 one-time vs recurring, 2 goal type (recurring drops item;
      // RECURRING_GOAL_TYPES in app/goals.py), 3 target + value, 4 recurring
      // cadence, 5 recurring start. One-time goals save from stage 3.

      var wizardExpanded = document.getElementById('gtWizardExpanded');
      var wizardStageEl = document.getElementById('gtWizardStage');
      var wizardTarget = { name: '', itemId: null, value: null };

      function openWizard() {
        GT.wizardStage = 1;
        GT.recurring = null;
        GT.type = null;
        GT.skillMetric = 'level';
        GT.itemId = null;
        GT.targetMode = 'gain';
        GT.recurInterval = '';
        GT.recurUnit = 'day';
        GT.recurStart = 'now';
        GT.recurStartAt = '';
        renderWizard();
      }

      function closeWizard() {
        GT.wizardStage = 0;
        renderWizard();
      }

      function wizardPickRecurrence(recurring) {
        GT.recurring = recurring;
        GT.wizardStage = 2;
        renderWizard();
      }

      function wizardPickType(type) {
        GT.type = type;
        // A recurring skill goal is XP-only; forced here so a stale Lvl pick
        // from an earlier one-time goal is not carried over.
        if (GT.recurring === 'recurring' && type === 'skill') { GT.skillMetric = 'xp'; }
        // The one place stage 3 is entered fresh (first time, or after
        // re-picking a type), so wizardTarget is cleared here and not in
        // wireWizardStage.
        wizardTarget = { name: '', itemId: null, value: null };
        GT.wizardStage = 3;
        renderWizard();
      }

      function wizardBack() {
        if (GT.wizardStage === 5) {
          GT.wizardStage = 4;
        } else if (GT.wizardStage === 4) {
          GT.wizardStage = 3;
        } else if (GT.wizardStage === 3) {
          GT.wizardStage = 2;
          GT.type = null;
          GT.skillMetric = 'level';
          GT.itemId = null;
          GT.targetMode = 'gain';
        } else if (GT.wizardStage === 2) {
          GT.wizardStage = 1;
          GT.recurring = null;
        }
        renderWizard();
      }

      document.getElementById('gtWizardAddBtn').addEventListener('click', openWizard);
      // One page-wide listener (stage 3's suggestions box is rebuilt on every
      // render); looks elements up on each click, so it no-ops on other stages.
      document.addEventListener('click', function (e) {
        var suggestions = document.getElementById('gtWizardSuggestions');
        var searchInput = document.getElementById('gtWizardSearchInput');
        if (suggestions && !suggestions.contains(e.target) && e.target !== searchInput) {
          suggestions.classList.remove('show');
        }
      });

      function renderWizard() {
        var addBtn = document.getElementById('gtWizardAddBtn');
        if (GT.wizardStage === 0) {
          addBtn.style.display = '';
          wizardExpanded.style.display = 'none';
          return;
        }
        addBtn.style.display = 'none';
        wizardExpanded.style.display = '';
        var stageHtml = {
          1: wizardStageRecurrenceHtml,
          2: wizardStageTypeHtml,
          3: wizardStageTargetHtml,
          4: wizardStageCadenceHtml,
          5: wizardStageStartHtml,
        }[GT.wizardStage];
        wizardStageEl.innerHTML = stageHtml();
        wireWizardStage();
      }

      var ONE_TIME_ICON_SVG =
        '<svg class="gt-recur-icon" viewBox="0 0 24 24" width="32" height="32" fill="none" ' +
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<path d="M8.5 7L11.5 5V19"/>' +
        '<path d="M8 19H15"/>' +
        '<path d="M16.5 11.5L21 16"/>' +
        '<path d="M21 11.5L16.5 16"/>' +
        '</svg>';
      var RECURRING_ICON_SVG =
        '<svg class="gt-recur-icon" viewBox="0 0 24 24" width="32" height="32" fill="none" ' +
        'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<rect x="3.5" y="5.5" width="17" height="15" rx="2"/>' +
        '<path d="M8 3V7"/>' +
        '<path d="M16 3V7"/>' +
        '<path d="M9.8 13.5a2.6 2.6 0 0 1 4.7-1.6" stroke-width="1.4"/>' +
        '<path d="M14.9 10.8L15.1 12.5L13.4 12.4"/>' +
        '<path d="M14.2 14.9a2.6 2.6 0 0 1-4.7 1.6" stroke-width="1.4"/>' +
        '<path d="M9.1 17.6L8.9 15.9L10.6 16.0"/>' +
        '</svg>';

      // Stage 1: one-time vs recurring. Reuses stage 2's type-card/Cancel
      // wrapper with 2 cards and SVG icons
      // (ONE_TIME_ICON_SVG/RECURRING_ICON_SVG).
      function wizardStageRecurrenceHtml() {
        return '' +
          '<div class="gt-wizard-stage1-wrap">' +
          '  <div class="gt-wizard-stage1">' +
          '    <button type="button" class="gt-wizard-type-btn" data-recur="one_time">' +
                 ONE_TIME_ICON_SVG + '<span>One-Time</span></button>' +
          '    <button type="button" class="gt-wizard-type-btn" data-recur="recurring">' +
                 RECURRING_ICON_SVG + '<span>Recurring</span></button>' +
          '  </div>' +
          '  <div class="gt-wizard-stage1-actions">' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-cancel" id="gtWizardCancel">Cancel</button>' +
          '  </div>' +
          '</div>';
      }

      // Stage 2: type picker. Recurring goals offer kc/skill only (an item's
      // owned quantity is not a monotonic lifetime total; RECURRING_GOAL_TYPES
      // in app/goals.py).
      var GOAL_TYPE_OPTIONS = [
        { type: 'item', icon: '/static/img/icon-goal-item.png', label: 'Item Qty' },
        { type: 'kc', icon: '/static/img/icon-goal-kc.png', label: 'Boss KC' },
        { type: 'skill', icon: '/static/img/icon-goal-skill.png', label: 'Skill Lvl/Xp' },
      ];

      function wizardStageTypeHtml() {
        var options = (GT.recurring === 'recurring')
          ? GOAL_TYPE_OPTIONS.filter(function (o) { return o.type !== 'item'; })
          : GOAL_TYPE_OPTIONS;
        var cards = options.map(function (o) {
          // A recurring skill goal is XP-only, so its card says just "Skill Xp"
          // rather than promising a level option.
          var label = (o.type === 'skill' && GT.recurring === 'recurring') ? 'Skill Xp' : o.label;
          return '<button type="button" class="gt-wizard-type-btn" data-type="' + o.type + '">' +
            '<img src="' + o.icon + '" alt="" /><span>' + label + '</span></button>';
        }).join('');
        return '' +
          '<div class="gt-wizard-stage1-wrap">' +
          '  <div class="gt-wizard-stage1">' + cards + '</div>' +
          '  <div class="gt-wizard-stage1-actions">' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-back" id="gtWizardBack">Back</button>' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-cancel" id="gtWizardCancel">Cancel</button>' +
          '  </div>' +
          '</div>';
      }

      var WIZARD_SEARCH_PLACEHOLDER = { item: 'Search for an item', kc: 'Search for a boss', skill: 'Search for a skill' };

      // Whether GAIN/REACH applies to the current pick; mirrors
      // app.goals.target_mode_allows_gain (level-metric skill and item goals are
      // REACH-only).
      function targetModeApplies() {
        if (GT.recurring === 'recurring') return false;
        if (GT.type === 'kc') return true;
        if (GT.type === 'skill') return GT.skillMetric === 'xp';
        return false;
      }

      function targetModeVisible() {
        if (GT.recurring === 'recurring') return false;
        if (GT.type === 'kc') return true;
        if (GT.type === 'skill') return true;
        return false;
      }

      function wizardTargetPlaceholder() {
        var gain = targetModeApplies() && GT.targetMode === 'gain';
        if (GT.type === 'kc') return gain ? 'Kc to gain' : 'Target kc';
        if (GT.type === 'skill') {
          if (GT.skillMetric === 'xp') return gain ? 'Experience to gain' : 'Target experience';
          return 'Target level';
        }
        return 'Target quantity';
      }

      // Stage 3 in one fixed-size box (.gt-wizard-expanded in
      // goal-tracking.css): search + target fields, the segmented controls row
      // (#gtWizardSegRow), then Back/Cancel/Save-or-Next (Next for recurring
      // goals). #gtTargetModeField is an always-present wrapper that
      // wireTargetModeToggle fills or empties in place.
      function wizardStageTargetHtml() {
        // No Lvl/Xp choice for a recurring skill goal; wizardPickType forces
        // GT.skillMetric to 'xp'.
        var metricToggle = (GT.type !== 'skill' || GT.recurring === 'recurring') ? '' : (
          '<div class="gt-metric-toggle" id="gtMetricToggle">' +
          '  <button type="button" class="gt-metric-btn" data-metric="level">Lvl</button>' +
          '  <button type="button" class="gt-metric-btn" data-metric="xp">XP</button>' +
          '</div>'
        );
        var saveLabel = (GT.recurring === 'recurring') ? 'Next' : 'Save';
        // Next uses the secondary look (like Back/Cancel) since a real Save
        // still follows on stage 4.
        var saveBtnClass = 'gt-add-btn' + (GT.recurring === 'recurring' ? ' gt-wizard-btn-next' : '');
        return '' +
          '<div class="gt-wizard-stage2">' +
          '  <div class="gt-wizard-row">' +
          '    <div class="gt-field gt-field-target-search">' +
          '      <div class="gt-search-box">' +
          '        <input type="text" id="gtWizardSearchInput" placeholder="' + WIZARD_SEARCH_PLACEHOLDER[GT.type] + '" autocomplete="off" />' +
          '        <div class="gt-suggestions" id="gtWizardSuggestions"></div>' +
          '      </div>' +
          '    </div>' +
          '    <div class="gt-field gt-field-target">' +
          '      <input type="text" inputmode="decimal" id="gtTargetValue" placeholder="' + wizardTargetPlaceholder() + '" autocomplete="off" />' +
          '    </div>' +
          '  </div>' +
          '  <div class="gt-wizard-segrow" id="gtWizardSegRow">' +
          metricToggle +
          '    <div id="gtTargetModeField"></div>' +
          '  </div>' +
          '  <div class="gt-wizard-actions">' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-back" id="gtWizardBack">Back</button>' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-cancel" id="gtWizardCancel">Cancel</button>' +
          '    <button type="button" class="' + saveBtnClass + '" id="gtWizardSave">' + saveLabel + '</button>' +
          '  </div>' +
          '</div>';
      }

      function targetModeToggleHtml() {
        return '' +
          '<div class="gt-target-mode-toggle" id="gtTargetModeToggle">' +
          '  <button type="button" class="gt-target-mode-btn" data-mode="gain">Gain</button>' +
          '  <button type="button" class="gt-target-mode-btn" data-mode="reach">Reach</button>' +
          '</div>';
      }

      // Fills #gtTargetModeField (or empties it) to match targetModeVisible()
      // and wires its buttons; called when stage 3 renders and from the Lvl/Xp
      // handler. When visible but not applicable (skill goal on LEVEL) it is
      // .gt-target-mode-toggle--disabled with no handler or .active button.
      function wireTargetModeToggle() {
        var field = document.getElementById('gtTargetModeField');
        if (!field) return;
        if (!targetModeVisible()) {
          field.innerHTML = '';
          updateWizardSegRowVisibility();
          return;
        }
        var applies = targetModeApplies();
        field.innerHTML = targetModeToggleHtml();
        var toggleEl = document.getElementById('gtTargetModeToggle');
        toggleEl.classList.toggle('gt-target-mode-toggle--disabled', !applies);
        document.querySelectorAll('#gtTargetModeToggle .gt-target-mode-btn').forEach(function (btn) {
          btn.classList.toggle('active', applies && btn.getAttribute('data-mode') === GT.targetMode);
          if (!applies) return;
          btn.addEventListener('click', function () {
            var newMode = btn.getAttribute('data-mode');
            if (newMode === GT.targetMode) return;
            GT.targetMode = newMode;
            document.querySelectorAll('#gtTargetModeToggle .gt-target-mode-btn').forEach(function (b) {
              b.classList.toggle('active', b === btn);
            });
            // Update the target placeholder in place ("Kc to gain" <-> "Target
            // kc"), like the Lvl/Xp toggle handler.
            updateWizardTargetField();
          });
        });
        updateWizardSegRowVisibility();
      }

      // Collapses #gtWizardSegRow when no toggle applies (item goal, or skill
      // goal on Lvl). CSS :empty cannot do this since #gtTargetModeField is
      // always a child. Called from wireTargetModeToggle, the one place the
      // row's contents can change.
      function updateWizardSegRowVisibility() {
        var segRow = document.getElementById('gtWizardSegRow');
        if (!segRow) return;
        var hasContent = !!segRow.querySelector('.gt-metric-toggle, .gt-target-mode-toggle');
        segRow.classList.toggle('gt-wizard-segrow--empty', !hasContent);
      }

      // Recurring units in the order of app.goals.RECUR_UNITS (display order
      // only; the server validates recur_unit).
      var RECUR_UNIT_OPTIONS = [
        { unit: 'hour', label: 'Hour' },
        { unit: 'day', label: 'Day' },
        { unit: 'week', label: 'Week' },
        { unit: 'month', label: 'Month' },
        { unit: 'year', label: 'Year' },
      ];
      // Mirrors app.goals.MAX_RECUR_INTERVAL; the server re-validates
      // (validateRecurField).
      var MAX_RECUR_INTERVAL = 999;

      // "Every x days" etc.; doubles as the field's label. Derived from
      // RECUR_UNIT_OPTIONS' label (lowercase + "s").
      function recurIntervalPlaceholder() {
        var opt = RECUR_UNIT_OPTIONS.filter(function (o) { return o.unit === GT.recurUnit; })[0];
        var unitWord = opt ? opt.label.toLowerCase() : 'day';
        return 'Every x ' + unitWord + 's';
      }

      function wizardStageCadenceHtml() {
        var unitButtons = RECUR_UNIT_OPTIONS.map(function (o) {
          return '<button type="button" class="gt-recur-unit-btn' + (o.unit === GT.recurUnit ? ' active' : '') + '" data-unit="' + o.unit + '">' + o.label + '</button>';
        }).join('');
        return '' +
          '<div class="gt-wizard-stage2">' +
          '  <div class="gt-wizard-recur-fields">' +
          '    <input type="text" inputmode="numeric" class="gt-recur-interval-input" id="gtRecurInterval" placeholder="' + recurIntervalPlaceholder() + '" autocomplete="off" maxlength="4" value="' + escapeHtml(GT.recurInterval || '') + '" />' +
          '  </div>' +
          '  <div class="gt-wizard-segrow">' +
          '    <div class="gt-recur-unit-toggle" id="gtRecurUnitToggle">' + unitButtons + '</div>' +
          '  </div>' +
          '  <div class="gt-wizard-actions">' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-back" id="gtWizardBack">Back</button>' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-cancel" id="gtWizardCancel">Cancel</button>' +
          '    <button type="button" class="gt-add-btn gt-wizard-btn-next" id="gtWizardSave">Next</button>' +
          '  </div>' +
          '</div>';
      }

      // Stage 5 (recurring only, last page): when the cadence starts. The
      // date/time field always renders (disabled while NOW, wireStartStage) so
      // the row order is fixed. RECUR_START_MASK is a longer copy of Loot
      // Tracker's DATE_MASK (pages share no script module).
      function wizardStageStartHtml() {
        var startPlaceholder = (GT.recurStart === 'custom') ? 'YYYY-MM-DD HH:MM' : 'Start now';
        var startValue = (GT.recurStart === 'custom') ? (GT.recurStartAt || RECUR_START_BLANK) : '';
        return '' +
          '<div class="gt-wizard-stage2">' +
          '  <div class="gt-wizard-recur-fields">' +
          '    <input type="text" inputmode="numeric" class="gt-recur-start-input" id="gtRecurStartInput" placeholder="' + escapeHtml(startPlaceholder) + '" autocomplete="off" spellcheck="false" ' +
                 (GT.recurStart === 'custom' ? '' : 'disabled ') + 'value="' + escapeHtml(startValue) + '" />' +
          '  </div>' +
          '  <div class="gt-wizard-segrow">' +
          '    <div class="gt-recur-start-toggle" id="gtRecurStartToggle">' +
          '      <button type="button" class="gt-recur-start-btn' + (GT.recurStart === 'now' ? ' active' : '') + '" data-start="now">Now</button>' +
          '      <button type="button" class="gt-recur-start-btn' + (GT.recurStart === 'custom' ? ' active' : '') + '" data-start="custom">Custom</button>' +
          '    </div>' +
          '  </div>' +
          '  <div class="gt-wizard-actions">' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-back" id="gtWizardBack">Back</button>' +
          '    <button type="button" class="gt-wizard-btn gt-wizard-btn-cancel" id="gtWizardCancel">Cancel</button>' +
          '    <button type="button" class="gt-add-btn" id="gtWizardSave">Save</button>' +
          '  </div>' +
          '</div>';
      }

      function wizardOptionLabel(raw) {
        return (GT.type === 'skill') ? (raw.charAt(0).toUpperCase() + raw.slice(1)) : raw;
      }

      function wireWizardStage() {
        if (GT.wizardStage === 1) {
          document.querySelectorAll('.gt-wizard-type-btn').forEach(function (btn) {
            btn.addEventListener('click', function () { wizardPickRecurrence(btn.getAttribute('data-recur')); });
          });
          document.getElementById('gtWizardCancel').addEventListener('click', closeWizard);
          return;
        }

        if (GT.wizardStage === 2) {
          document.querySelectorAll('.gt-wizard-type-btn').forEach(function (btn) {
            btn.addEventListener('click', function () { wizardPickType(btn.getAttribute('data-type')); });
          });
          document.getElementById('gtWizardBack').addEventListener('click', wizardBack);
          document.getElementById('gtWizardCancel').addEventListener('click', closeWizard);
          return;
        }

        if (GT.wizardStage === 4) {
          wireCadenceStage();
          return;
        }

        if (GT.wizardStage === 5) {
          wireStartStage();
          return;
        }

        // Does not reset wizardTarget: renderWizard rebuilds this stage on every
        // visit, including Back from stage 4, and a reset would blank the picks.
        // wizardPickType is the fresh start.
        document.getElementById('gtWizardBack').addEventListener('click', wizardBack);
        document.getElementById('gtWizardCancel').addEventListener('click', closeWizard);

        var searchInput = document.getElementById('gtWizardSearchInput');
        var suggestions = document.getElementById('gtWizardSuggestions');
        searchInput.value = wizardTarget.name || '';

        function showSuggestions(names, iconFor) {
          if (!names.length) { suggestions.classList.remove('show'); suggestions.innerHTML = ''; return; }
          suggestions.innerHTML = names.map(function (raw) {
            var label = wizardOptionLabel(raw);
            var icon = iconFor ? iconFor(raw) : null;
            return '<div class="gt-suggestion" data-raw="' + escapeHtml(raw) + '" data-label="' + escapeHtml(label) + '">' +
              (icon ? '<img src="' + escapeHtml(icon) + '" alt="" />' : '') +
              '<span>' + escapeHtml(label) + '</span></div>';
          }).join('');
          suggestions.classList.add('show');
        }

        function showItemSuggestions(results) {
          if (!results.length) { suggestions.classList.remove('show'); suggestions.innerHTML = ''; return; }
          suggestions.innerHTML = results.map(function (r) {
            return '<div class="gt-suggestion" data-raw="' + escapeHtml(r.name) + '" data-label="' + escapeHtml(r.name) +
              '" data-item-id="' + (r.id || '') + '">' +
              (r.icon ? '<img src="' + escapeHtml(r.icon) + '" alt="" />' : '') +
              '<span>' + escapeHtml(r.name) + '</span></div>';
          }).join('');
          suggestions.classList.add('show');
        }

        suggestions.addEventListener('click', function (e) {
          var row = e.target.closest('.gt-suggestion');
          if (!row) return;
          var label = row.getAttribute('data-label');
          searchInput.value = label;
          searchInput.classList.remove('invalid');
          wizardTarget.name = row.getAttribute('data-raw');
          var itemId = row.getAttribute('data-item-id');
          wizardTarget.itemId = (GT.type === 'item' && itemId) ? parseInt(itemId, 10) : null;
          suggestions.classList.remove('show');
          suggestions.innerHTML = '';
        });

        if (GT.type === 'item') {
          searchInput.addEventListener('input', debounce(async function () {
            searchInput.classList.remove('invalid');
            wizardTarget.name = searchInput.value.trim();
            wizardTarget.itemId = null;
            var q = wizardTarget.name;
            if (!q) { showItemSuggestions([]); return; }
            var data = await apiCall('/api/items/search?q=' + encodeURIComponent(q));
            showItemSuggestions(data ? data.results : []);
          }, 200));
        } else {
          var pool = (GT.type === 'kc') ? BOSS_NAMES : SKILL_NAMES_LIST;
          var iconFor = (GT.type === 'kc')
            ? function (raw) { return '/static/boss-icons/' + BOSS_SLUG_BY_NAME[raw] + '.png'; }
            : function (raw) { return '/static/skill-icons/' + raw + '.png'; };
          searchInput.addEventListener('input', debounce(function () {
            searchInput.classList.remove('invalid');
            wizardTarget.name = searchInput.value.trim();
            var q = wizardTarget.name.toLowerCase();
            var matches = !q ? [] : pool.filter(function (raw) {
              return wizardOptionLabel(raw).toLowerCase().indexOf(q) !== -1;
            }).slice(0, 20);
            showSuggestions(matches, iconFor);
          }, 120));
        }

        if (GT.type === 'skill' && GT.recurring !== 'recurring') {
          document.querySelectorAll('.gt-metric-btn').forEach(function (btn) {
            btn.classList.toggle('active', btn.getAttribute('data-metric') === GT.skillMetric);
            btn.addEventListener('click', function () {
              var newMetric = btn.getAttribute('data-metric');
              if (newMetric !== GT.skillMetric) {
                // Carries the field's number across the switch (5,750 xp <->
                // level 22) via xpForLevel/levelForXp, like Mindmaps' skill-goal
                // metric toggle.
                var targetInputForSwitch = document.getElementById('gtTargetValue');
                var rawForSwitch = targetInputForSwitch.value.trim();
                if (rawForSwitch !== '') {
                  var nForSwitch = Number(parseMoneySuffix(rawForSwitch));
                  if (Number.isInteger(nForSwitch)) {
                    targetInputForSwitch.value = String(
                      newMetric === 'xp' ? xpForLevel(nForSwitch) : levelForXp(nForSwitch)
                    );
                  }
                }
                // LEVEL -> XP makes GAIN/REACH usable, so GT.targetMode resets
                // to 'gain'. XP -> LEVEL only disables the toggle.
                if (newMetric === 'xp') GT.targetMode = 'gain';
                GT.skillMetric = newMetric;
              }
              document.querySelectorAll('.gt-metric-btn').forEach(function (b) {
                b.classList.toggle('active', b === btn);
              });
              wireTargetModeToggle();
              updateWizardTargetField();
              validateTargetField();
            });
          });
        }

        var targetInput = document.getElementById('gtTargetValue');
        // Restores wizardTarget.value captured the last time Next was pressed
        // here (null on the first visit).
        if (wizardTarget.value != null) targetInput.value = String(wizardTarget.value);
        targetInput.addEventListener('input', function () {
          filterNumericSuffixInput(targetInput);
          validateTargetField();
        });

        wireTargetModeToggle();
        updateWizardTargetField();
        document.getElementById('gtWizardSave').addEventListener('click', function () {
          var targetName = wizardTarget.name.trim();
          searchInput.classList.toggle('invalid', !targetName);
          var valueOk = validateTargetField(true);
          if (!targetName || !valueOk) return;
          wizardTarget.value = Number(parseMoneySuffix(document.getElementById('gtTargetValue').value.trim()));
          if (GT.recurring === 'recurring') {
            GT.wizardStage = 4;
            renderWizard();
          } else {
            wizardAddGoal();
          }
        });
      }

      function wireCadenceStage() {
        document.getElementById('gtWizardBack').addEventListener('click', wizardBack);
        document.getElementById('gtWizardCancel').addEventListener('click', closeWizard);

        var intervalInput = document.getElementById('gtRecurInterval');
        intervalInput.addEventListener('input', function () {
          // Digits only: a plain count, no k/m/b shorthand or decimal point.
          var cursor = intervalInput.selectionStart;
          var cleaned = intervalInput.value.replace(/[^0-9]/g, '');
          if (cleaned !== intervalInput.value) {
            var keptBeforeCursor = intervalInput.value.slice(0, cursor).replace(/[^0-9]/g, '').length;
            intervalInput.value = cleaned;
            intervalInput.setSelectionRange(keptBeforeCursor, keptBeforeCursor);
          }
          GT.recurInterval = intervalInput.value;
          validateRecurField();
        });

        document.querySelectorAll('.gt-recur-unit-btn').forEach(function (btn) {
          btn.addEventListener('click', function () {
            GT.recurUnit = btn.getAttribute('data-unit');
            document.querySelectorAll('.gt-recur-unit-btn').forEach(function (b) {
              b.classList.toggle('active', b === btn);
            });
            // Updates only the placeholder: a full renderWizard() would wipe
            // what is typed in the field (GT.recurInterval is read back only on
            // render).
            intervalInput.placeholder = recurIntervalPlaceholder();
          });
        });

        // Validates and advances to stage 5 (never saves). GT.recurInterval is
        // already kept current by the keystroke handler above.
        document.getElementById('gtWizardSave').addEventListener('click', function () {
          if (!validateRecurField(true)) return;
          GT.wizardStage = 5;
          renderWizard();
        });
      }

      // Like validateTargetField, against 1..MAX_RECUR_INTERVAL, with the same
      // showEmptyAsInvalid quiet-while-typing/loud-at-save split.
      function validateRecurField(showEmptyAsInvalid) {
        var input = document.getElementById('gtRecurInterval');
        if (!input) return false;
        var raw = input.value.trim();
        if (raw === '') { input.classList.toggle('invalid', !!showEmptyAsInvalid); return false; }
        var n = Number(raw);
        var ok = Number.isInteger(n) && n >= 1 && n <= MAX_RECUR_INTERVAL;
        input.classList.toggle('invalid', !ok);
        return ok;
      }

      var RECUR_START_MASK = 'dddd-dd-dd dd:dd';
      // All-underscores skeleton the field starts at and falls back to when
      // emptied; built from RECUR_START_MASK's length.
      var RECUR_START_BLANK = RECUR_START_MASK.replace(/d/g, '_');
      // Count of 'd' slots in the mask (12), computed once for
      // recurStartDigitsOnly and validateRecurStartField (partial vs. fully
      // filled).
      var RECUR_START_DIGIT_COUNT = (RECUR_START_MASK.match(/d/g) || []).length;

      function recurStartDigitsOnly(s) {
        return (s || '').replace(/\\D/g, '').slice(0, RECUR_START_DIGIT_COUNT);
      }

      function recurStartMaskFromDigits(digits) {
        var out = '', di = 0;
        for (var i = 0; i < RECUR_START_MASK.length; i++) {
          if (RECUR_START_MASK[i] === 'd') {
            out += di < digits.length ? digits[di] : '_';
            di++;
          } else {
            out += RECUR_START_MASK[i];
          }
        }
        return out;
      }

      function applyRecurStartMask(input) {
        var digits = recurStartDigitsOnly(input.value);
        input.value = recurStartMaskFromDigits(digits);
        // Cursor lands after the last filled digit, as in Loot Tracker's
        // applyDateMask.
        var pos = 0, di = 0;
        for (var i = 0; i < RECUR_START_MASK.length; i++) {
          if (RECUR_START_MASK[i] === 'd' && di < digits.length) { pos = i + 1; di++; }
        }
        input.setSelectionRange(pos, pos);
        input.classList.remove('invalid');
      }

      // Requires a real calendar date and clock time (rejects "2024-13-40
      // 25:99"); like Loot Tracker's isValidIsoDate plus an hour/minute check.
      function isValidRecurStartDateTime(s) {
        var m = /^(\\d{4})-(\\d{2})-(\\d{2}) (\\d{2}):(\\d{2})$/.exec(s || '');
        if (!m) return false;
        var year = parseInt(m[1], 10), month = parseInt(m[2], 10), day = parseInt(m[3], 10);
        var hour = parseInt(m[4], 10), minute = parseInt(m[5], 10);
        if (month < 1 || month > 12) return false;
        var daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
        if (day < 1 || day > daysInMonth) return false;
        return hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59;
      }

      // Like validateRecurField for the masked field; always valid while NOW is
      // picked. An incomplete value is quiet (gated by showEmptyAsInvalid),
      // since red on every keystroke reads as broken. Only Save passes true.
      function validateRecurStartField(showIncompleteAsInvalid) {
        if (GT.recurStart !== 'custom') return true;
        var input = document.getElementById('gtRecurStartInput');
        if (!input) return false;
        if (recurStartDigitsOnly(input.value).length < RECUR_START_DIGIT_COUNT) {
          input.classList.toggle('invalid', !!showIncompleteAsInvalid);
          return false;
        }
        var ok = isValidRecurStartDateTime(input.value.trim());
        input.classList.toggle('invalid', !ok);
        return ok;
      }

      // Converts the masked local "YYYY-MM-DD HH:MM" to the ISO UTC string
      // payload.recur_start_at expects (GoalCreateRequest in app/schemas.py):
      // new Date(y, m-1, d, h, min) reads local time, toISOString() gives UTC.
      // Call after isValidRecurStartDateTime passes.
      function recurStartIsoFromMasked(s) {
        var m = /^(\\d{4})-(\\d{2})-(\\d{2}) (\\d{2}):(\\d{2})$/.exec(s || '');
        if (!m) return null;
        var d = new Date(
          parseInt(m[1], 10), parseInt(m[2], 10) - 1, parseInt(m[3], 10),
          parseInt(m[4], 10), parseInt(m[5], 10)
        );
        return d.toISOString();
      }

      function nowRecurStartMasked() {
        var d = new Date();
        function pad2(n) { return (n < 10 ? '0' : '') + n; }
        return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) +
          ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
      }

      function wireStartStage() {
        document.getElementById('gtWizardBack').addEventListener('click', wizardBack);
        document.getElementById('gtWizardCancel').addEventListener('click', closeWizard);

        var input = document.getElementById('gtRecurStartInput');
        input.addEventListener('input', function () {
          applyRecurStartMask(input);
          GT.recurStartAt = input.value;
          validateRecurStartField();
        });

        document.querySelectorAll('.gt-recur-start-btn').forEach(function (btn) {
          btn.addEventListener('click', function () {
            var newStart = btn.getAttribute('data-start');
            if (newStart === GT.recurStart) return;
            GT.recurStart = newStart;
            document.querySelectorAll('.gt-recur-start-btn').forEach(function (b) {
              b.classList.toggle('active', b === btn);
            });
            input.disabled = (newStart !== 'custom');
            input.placeholder = (newStart === 'custom') ? 'YYYY-MM-DD HH:MM' : 'Start now';
            input.classList.remove('invalid');
            if (newStart === 'custom') {
              // Prefill with the current time only the first time CUSTOM is
              // picked (GT.recurStartAt empty); see nowRecurStartMasked.
              if (!GT.recurStartAt) {
                input.value = nowRecurStartMasked();
                GT.recurStartAt = input.value;
              } else {
                input.value = GT.recurStartAt;
              }
              input.focus();
            } else {
              input.value = '';
            }
          });
        });

        document.getElementById('gtWizardSave').addEventListener('click', wizardAddGoal);
      }

      function currentTargetBounds() {
        if (GT.type === 'kc') return TARGET_BOUNDS.kc;
        if (GT.type === 'skill') return (GT.skillMetric === 'xp') ? TARGET_BOUNDS.skill_xp : TARGET_BOUNDS.skill_level;
        return TARGET_BOUNDS.item;
      }

      function updateWizardTargetField() {
        document.getElementById('gtTargetValue').placeholder = wizardTargetPlaceholder();
      }

      // Live range check for the target field (mirrors Mindmaps'
      // validateSkillTarget; server re-validates). Goes through parseMoneySuffix
      // so "150k" does not flash. Invalid is a red border only; empty is neutral
      // while typing but invalid on Save (showEmptyAsInvalid).
      function validateTargetField(showEmptyAsInvalid) {
        var input = document.getElementById('gtTargetValue');
        if (!input) return false;
        var raw = input.value.trim();
        if (raw === '') { input.classList.toggle('invalid', !!showEmptyAsInvalid); return false; }
        var n = Number(parseMoneySuffix(raw));
        var bounds = currentTargetBounds();
        var ok = Number.isInteger(n) && n >= bounds.min && n <= bounds.max;
        input.classList.toggle('invalid', !ok);
        return ok;
      }

      // The stage-3 name/value (wizardTarget) and the cadence were validated on
      // earlier stages and their DOM is gone; only the CUSTOM start field is
      // validated here.
      async function wizardAddGoal() {
        var payload = { goal_type: GT.type, target_name: wizardTarget.name, target_value: wizardTarget.value };
        if (GT.type === 'skill') { payload.metric = GT.skillMetric; }
        if (GT.type === 'item' && wizardTarget.itemId) { payload.item_id = wizardTarget.itemId; }
        if (GT.recurring === 'recurring') {
          if (!validateRecurStartField(true)) return;
          payload.is_recurring = true;
          payload.recur_interval = Number(GT.recurInterval);
          payload.recur_unit = GT.recurUnit;
          if (GT.recurStart === 'custom') {
            payload.recur_start_at = recurStartIsoFromMasked(document.getElementById('gtRecurStartInput').value.trim());
          }
        } else if (targetModeApplies()) {
          payload.target_mode = GT.targetMode;
        }

        var data = await apiCall('/api/goals', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
        if (!data) return;
        GT.goals.push(data);
        // A new goal changes the list; see resetGoalTrackingShareState.
        resetGoalTrackingShareState();
        renderGoalList();
        closeWizard();
      }

      // Goal list

      function goalName(g) {
        if (g.goal_type === 'skill') return g.target_name.charAt(0).toUpperCase() + g.target_name.slice(1);
        return g.target_name;
      }

      // Live current/target progress in the goal's unit ("LVL" prefix, "XP"/"KC"
      // suffix, none for items), followed by a recurring goal's cadence;
      // g.current_value is already this period's progress.
      function goalProgressLabel(g) {
        var cur = fmtNum(g.current_value);
        var tgt = fmtNum(g.target_value);
        var base;
        if (g.goal_type === 'kc') base = cur + ' / ' + tgt + ' KC';
        else if (g.goal_type === 'skill') base = (g.metric === 'xp') ? (cur + ' / ' + tgt + ' XP') : ('LVL ' + cur + ' / ' + tgt);
        else base = cur + ' / ' + tgt;
        var cadence = recurCadenceLabel(g);
        var info = goalInfoIconHtml(g);
        return cadence ? (base + ' · ' + cadence + info) : (base + info);
      }

      var RECUR_UNIT_LABEL = { hour: 'HOUR', day: 'DAY', week: 'WEEK', month: 'MONTH', year: 'YEAR' };
      function recurCadenceLabel(g) {
        if (!g.is_recurring) return '';
        var unit = RECUR_UNIT_LABEL[g.recur_unit] || String(g.recur_unit || '').toUpperCase();
        if (g.recur_interval === 1) return 'EVERY ' + unit;
        return 'EVERY ' + fmtNum(g.recur_interval) + ' ' + unit + 'S';
      }

      var RECUR_UNIT_SECONDS = { hour: 3600, day: 86400, week: 7 * 86400, month: 30 * 86400, year: 365 * 86400 };

      // Unit/letter pairs (Y, M, W, D, H, M) by greedy decomposition with
      // RECUR_UNIT_SECONDS, matching goalInfoIconHtml. Zero units are omitted
      // unless all are zero ("0M"); negative input clamps to zero. Not
      // zero-padded.
      function fmtRecurCountdown(totalSeconds) {
        var sec = Math.max(0, Math.round(totalSeconds));
        var y = Math.floor(sec / RECUR_UNIT_SECONDS.year); sec -= y * RECUR_UNIT_SECONDS.year;
        var mo = Math.floor(sec / RECUR_UNIT_SECONDS.month); sec -= mo * RECUR_UNIT_SECONDS.month;
        var w = Math.floor(sec / RECUR_UNIT_SECONDS.week); sec -= w * RECUR_UNIT_SECONDS.week;
        var d = Math.floor(sec / RECUR_UNIT_SECONDS.day); sec -= d * RECUR_UNIT_SECONDS.day;
        var h = Math.floor(sec / 3600); sec -= h * 3600;
        var mi = Math.floor(sec / 60);
        var units = [[y, 'Y'], [mo, 'M'], [w, 'W'], [d, 'D'], [h, 'H'], [mi, 'M']];
        var shown = units.filter(function (u) { return u[0] !== 0; });
        if (!shown.length) shown = [units[units.length - 1]];
        return shown.map(function (u) { return u[0] + u[1]; }).join(' ');
      }

      // The hoverable "i" (a title attribute): recurring goals show "Resets in
      // [countdown]", one-time GAIN goals show "Started at [baseline] [UNIT]"
      // (g.baseline_value, kc and xp-skill only). Returns '' otherwise.
      function goalInfoIconHtml(g) {
        var tooltip = null;
        if (g.is_recurring && g.recur_period_start) {
          var unitSeconds = RECUR_UNIT_SECONDS[g.recur_unit];
          if (unitSeconds) {
            var periodStartMs = new Date(g.recur_period_start).getTime();
            var periodEndMs = periodStartMs + g.recur_interval * unitSeconds * 1000;
            var remainingSeconds = (periodEndMs - Date.now()) / 1000;
            tooltip = 'Resets in ' + fmtRecurCountdown(remainingSeconds);
          }
        } else if (!g.is_recurring && g.baseline_value != null) {
          var unit = (g.goal_type === 'kc') ? ' KC' : (g.goal_type === 'skill' && g.metric === 'xp') ? ' XP' : '';
          tooltip = 'Started at ' + fmtNum(g.baseline_value) + unit;
        }
        if (!tooltip) return '';
        return '<span class="gt-goal-info-icon" title="' + escapeHtml(tooltip) + '">' +
          '<svg width="11" height="11" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
          '<circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.3"/>' +
          '<path d="M8 7.3V11.4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>' +
          '<circle cx="8" cy="4.9" r="0.9" fill="currentColor"/>' +
          '</svg>' +
          '</span>';
      }

      function goalIconSrc(g) {
        if (g.goal_type === 'kc') {
          var slug = BOSS_SLUG_BY_NAME[g.target_name];
          if (slug) return '/static/boss-icons/' + slug + '.png';
        } else if (g.goal_type === 'skill') {
          return '/static/skill-icons/' + g.target_name + '.png';
        } else if (g.goal_type === 'item' && g.item_icon) {
          return g.item_icon;
        }
        return TYPE_ICON[g.goal_type];
      }

      // Delete button: the first click (delegated on #gtGoalList) arms
      // gt-goal-delete--confirm, a second calls deleteGoal. customMode adds
      // draggable/data-goal-id; the icon has draggable="false" so a drag grabs
      // the row.
      function goalRowHtml(g, customMode) {
        // Uses g.progress_pct (computed in xp server-side,
        // app.goals.progress_pct) rather than current/target, since a
        // LEVEL-metric goal's levels are not linear in effort.
        var pct = g.progress_pct;
        var done = g.current_value >= g.target_value;
        var rowCls = 'gt-goal-row' + (done ? ' gt-goal-done' : '') + (customMode ? ' draggable' : '');
        var draggableAttr = customMode ? ' draggable="true"' : '';
        return '' +
          '<div class="' + rowCls + '" data-goal-id="' + g.id + '"' + draggableAttr + '>' +
          '  <img class="gt-goal-icon" src="' + goalIconSrc(g) + '" alt="" draggable="false" />' +
          '  <div class="gt-goal-info">' +
          '    <div class="gt-goal-headline">' +
          '      <span class="gt-goal-name">' + escapeHtml(goalName(g)) + '</span>' +
          '      <span class="gt-goal-sub">' + goalProgressLabel(g) + '</span>' +
          '    </div>' +
          '    <div class="gt-goal-bar"><div class="gt-goal-bar-fill" style="width:' + pct + '%"></div></div>' +
          '  </div>' +
          '  <button type="button" class="gt-goal-delete" data-goal-id="' + g.id + '" data-tooltip="Delete goal" aria-label="Delete goal">' +
          '    <svg class="gt-goal-delete-icon" width="15" height="15" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
          '      <path d="M2 4H14" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>' +
          '      <path d="M6 4V2.5C6 2.22386 6.22386 2 6.5 2H9.5C9.77614 2 10 2.22386 10 2.5V4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>' +
          '      <path d="M3.5 4L4.1 13.2C4.13 13.66 4.51 14 4.97 14H11.03C11.49 14 11.87 13.66 11.9 13.2L12.5 4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>' +
          '      <path d="M6.5 6.5V11.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>' +
          '      <path d="M9.5 6.5V11.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>' +
          '    </svg>' +
          '    <span class="gt-goal-delete-confirm">Are you sure?</span>' +
          '  </button>' +
          '</div>';
      }

      // Powers #gtSortTabs (GT.sortMode); sorts a copy. Server twin:
      // GOAL_SORT_MODES in app/schemas.py. 'custom' uses g.sort_order;
      // never-dragged goals sort last, oldest first.
      function sortGoals(list, sortMode) {
        var out = list.slice();
        function byNameAsc(a, b) { return goalName(a).toLowerCase().localeCompare(goalName(b).toLowerCase()); }
        function byType(a, b) {
          var byT = GOAL_TYPE_SORT_ORDER[a.goal_type] - GOAL_TYPE_SORT_ORDER[b.goal_type];
          return byT !== 0 ? byT : byNameAsc(a, b);
        }
        if (sortMode === 'progress_desc') {
          out.sort(function (a, b) { return b.progress_pct - a.progress_pct; });
        } else if (sortMode === 'progress_asc') {
          out.sort(function (a, b) { return a.progress_pct - b.progress_pct; });
        } else if (sortMode === 'type_asc') {
          out.sort(byType);
        } else if (sortMode === 'type_desc') {
          out.sort(function (a, b) { return -byType(a, b); });
        } else if (sortMode === 'reverse_alphabetical') {
          out.sort(function (a, b) { return -byNameAsc(a, b); });
        } else if (sortMode === 'recent') {
          out.sort(function (a, b) { return new Date(b.created_at) - new Date(a.created_at); });
        } else if (sortMode === 'oldest') {
          out.sort(function (a, b) { return new Date(a.created_at) - new Date(b.created_at); });
        } else if (sortMode === 'custom') {
          out.sort(function (a, b) {
            if (a.sort_order == null && b.sort_order == null) return new Date(a.created_at) - new Date(b.created_at);
            if (a.sort_order == null) return 1;
            if (b.sort_order == null) return -1;
            return a.sort_order - b.sort_order;
          });
        } else {
          out.sort(byNameAsc);
        }
        return out;
      }

      // Maps the 9 persisted sort_mode strings to and from {metric, dir} pairs
      // for the 5-button row. Keyed by full mode string since they do not all
      // follow "metric-dir" ("reverse_alphabetical"); custom has no direction.
      var SORT_MODE_METRIC = {
        progress_desc: { metric: 'progress', dir: 'desc' },
        progress_asc: { metric: 'progress', dir: 'asc' },
        type_desc: { metric: 'type', dir: 'desc' },
        type_asc: { metric: 'type', dir: 'asc' },
        alphabetical: { metric: 'alpha', dir: 'asc' },
        reverse_alphabetical: { metric: 'alpha', dir: 'desc' },
        recent: { metric: 'time', dir: 'desc' },
        oldest: { metric: 'time', dir: 'asc' },
      };
      var SORT_METRIC_MODE = {
        progress: { asc: 'progress_asc', desc: 'progress_desc' },
        type: { asc: 'type_asc', desc: 'type_desc' },
        alpha: { asc: 'alphabetical', desc: 'reverse_alphabetical' },
        time: { asc: 'oldest', desc: 'recent' },
      };
      // Direction a metric starts at on a fresh click: alpha ascending, every
      // other metric descending (as in Loot Tracker's SORT_METRIC_DEFAULT_DIR).
      var SORT_METRIC_DEFAULT_DIR = { progress: 'desc', type: 'desc', alpha: 'asc', time: 'desc' };

      function updateSortTabs() {
        var active = SORT_MODE_METRIC[GT.sortMode];
        document.querySelectorAll('#gtSortTabs .gt-sort-tab').forEach(function (b) {
          var metric = b.getAttribute('data-sort-metric');
          // !!(...) is required: active is undefined for 'custom', and
          // classList.toggle('active', undefined) flips the class instead of
          // forcing it off, leaving a metric button stuck active after Custom is
          // picked.
          var isActive = !!(metric ? (active && active.metric === metric) : (b.getAttribute('data-sort') === GT.sortMode));
          b.classList.toggle('active', isActive);
          var arrow = b.querySelector('.gt-sort-arrow');
          if (arrow) arrow.textContent = isActive && active ? (active.dir === 'asc' ? ' ↑' : ' ↓') : '';
        });
      }

      function applyGoalsResponse(data) {
        GT.goals = data.goals || [];
        GT.sortMode = data.sort_mode || GT.sortMode;
        updateSortTabs();
        renderGoalList();
      }

      // Rows are draggable only in "custom" sort mode. Skips the rebuild when
      // GT.sortMode + GT.goals match what is on screen (GT.renderKey): the
      // 5-second poll calls this every tick, and recreating each row's <img>
      // flickers. The recur-countdown tooltip can go stale meanwhile
      // (hover-only).
      function renderGoalList() {
        var listEl = document.getElementById('gtGoalList');
        var emptyEl = document.getElementById('gtEmpty');
        var sortTabsEl = document.getElementById('gtSortTabs');
        if (!GT.goals.length) {
          GT.renderKey = GT.sortMode + '|[]';
          listEl.innerHTML = '';
          emptyEl.style.display = '';
          sortTabsEl.style.display = 'none';
          return;
        }
        var renderKey = GT.sortMode + '|' + JSON.stringify(GT.goals);
        if (renderKey === GT.renderKey) return;
        GT.renderKey = renderKey;
        emptyEl.style.display = 'none';
        sortTabsEl.style.display = '';
        var customMode = GT.sortMode === 'custom';
        var sorted = sortGoals(GT.goals, GT.sortMode);
        listEl.innerHTML = sorted.map(function (g) { return goalRowHtml(g, customMode); }).join('');
        fixGoalNameMinWidths(listEl);
        wireGoalDrag(customMode);
        // Touch screens never show a native title tooltip, so the info icon's
        // text goes in data-tooltip for the shared tap-tooltip script.
        if (GT_TOUCH) {
          listEl.querySelectorAll('.gt-goal-info-icon[title]').forEach(function (ic) {
            ic.setAttribute('data-tooltip', ic.getAttribute('title'));
            ic.removeAttribute('title');
          });
        }
      }

      // Keeps the gap between a goal's title and progress readout constant:
      // .gt-goal-name has min-width: 48px (goal-tracking.css), which pads short
      // titles. The floor is lowered per row to the measured title width (reused
      // canvas 2D context; character counts are unreliable in this bitmap font).
      // Runs after each rebuild.
      var goalNameMeasureCtx = document.createElement('canvas').getContext('2d');
      var ON_LANDING = document.body.classList.contains('landing');
      var GT_TOUCH = !!(window.matchMedia && window.matchMedia('(hover: none)').matches);
      var GT_GOAL_NAME_MIN_WIDTH = 48; // matches .gt-goal-name's own min-width in goal-tracking.css
      function fixGoalNameMinWidths(listEl) {
        listEl.querySelectorAll('.gt-goal-name').forEach(function (el) {
          var cs = getComputedStyle(el);
          goalNameMeasureCtx.font = cs.fontStyle + ' ' + cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
          var natural = goalNameMeasureCtx.measureText(el.textContent).width;
          el.style.minWidth = Math.min(GT_GOAL_NAME_MIN_WIDTH, natural) + 'px';
        });
      }

      // Persists the active sort tab (GameAccount.goal_sort_mode): PUT, then
      // apply the response (as setStillToPurchaseSort does), not optimistically.
      async function setGoalSortMode(mode) {
        var data = await apiCall('/api/goals/sort-mode', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sort_mode: mode }),
        });
        if (data) applyGoalsResponse(data);
      }

      document.getElementById('gtSortTabs').addEventListener('click', function (e) {
        var btn = e.target.closest('.gt-sort-tab');
        if (!btn) return;
        var metric = btn.getAttribute('data-sort-metric');
        var mode;
        if (!metric) {
          // Custom has no direction, just its literal mode string.
          mode = btn.getAttribute('data-sort');
        } else {
          var current = SORT_MODE_METRIC[GT.sortMode];
          var dir = (current && current.metric === metric)
            ? (current.dir === 'asc' ? 'desc' : 'asc')
            : SORT_METRIC_DEFAULT_DIR[metric];
          mode = SORT_METRIC_MODE[metric][dir];
        }
        if (mode === GT.sortMode) return;
        setGoalSortMode(mode);
      });
      updateSortTabs();

      // Delegated on the list container (survives the per-poll rebuild). First
      // click arms a delete button ("Are you sure?"), a second deletes; clicking
      // elsewhere disarms, so one row is mid-confirm at a time.
      document.getElementById('gtGoalList').addEventListener('click', function (e) {
        var btn = e.target.closest('.gt-goal-delete');
        if (!btn) return;
        if (btn.classList.contains('gt-goal-delete--confirm')) {
          deleteGoal(btn.getAttribute('data-goal-id'));
          return;
        }
        document.querySelectorAll('.gt-goal-delete--confirm').forEach(function (b) {
          b.classList.remove('gt-goal-delete--confirm');
        });
        btn.classList.add('gt-goal-delete--confirm');
      });

      document.addEventListener('click', function (e) {
        if (e.target.closest('.gt-goal-delete')) return;
        document.querySelectorAll('.gt-goal-delete--confirm').forEach(function (b) {
          b.classList.remove('gt-goal-delete--confirm');
        });
      });

      async function deleteGoal(goalId) {
        var data = await apiCall('/api/goals/' + encodeURIComponent(goalId), { method: 'DELETE' });
        if (data === null) return;
        GT.goals = GT.goals.filter(function (g) { return g.id !== goalId; });
        resetGoalTrackingShareState();
        renderGoalList();
      }

      // Nudges the CUSTOM sort tab (like glowCustomSortButton in Purchase Goals)
      // when a row is pressed outside Custom mode, where drag does nothing.
      // Removes the class, forces a reflow and re-adds it so the pulse restarts.
      function glowCustomSortTab() {
        var btn = document.querySelector('#gtSortTabs .gt-sort-tab[data-sort="custom"]');
        if (!btn) return;
        btn.classList.remove('glow');
        void btn.offsetWidth;
        btn.classList.add('glow');
      }

      function wireGoalDrag(customMode) {
        var listEl = document.getElementById('gtGoalList');
        if (!customMode) {
          // Rows outside Custom have no draggable attribute, so only a plain
          // press reaches here. Ignores presses on .gt-goal-delete, which should
          // not glow the CUSTOM tab.
          if (GT_TOUCH) return;
          listEl.querySelectorAll('.gt-goal-row').forEach(function (el) {
            el.addEventListener('pointerdown', function (e) {
              if (e.target.closest('.gt-goal-delete')) return;
              glowCustomSortTab();
            });
          });
          return;
        }
        var draggedEl = null;
        var dropped = false;

        function rowKey(row) { return row.getAttribute('data-goal-id'); }

        function animateReorder(mutate) {
          var rows = Array.prototype.slice.call(listEl.querySelectorAll('.gt-goal-row'));
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
            row.getBoundingClientRect();
            row.style.transition = 'transform 150ms ease';
            row.style.transform = '';
            row.addEventListener('transitionend', function handler() {
              row.style.transition = '';
              row.removeEventListener('transitionend', handler);
            });
          });
        }

        // The live preview already leaves the DOM in the order to save; just
        // read the rows back.
        async function commitDomOrder() {
          var order = Array.prototype.slice.call(listEl.querySelectorAll('.gt-goal-row')).map(rowKey);
          var data = await apiCall('/api/goals/reorder', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order: order }),
          });
          if (data) applyGoalsResponse(data);
        }

        listEl.querySelectorAll('.gt-goal-row').forEach(function (el) {
          el.addEventListener('dragstart', function (e) {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', el.getAttribute('data-goal-id'));
            draggedEl = el;
            dropped = false;
            el.classList.add('dragging');
          });
          el.addEventListener('dragend', function () {
            el.classList.remove('dragging');
            draggedEl = null;
            // A drag that ends without a drop (outside the list, or Escape)
            // leaves the preview DOM order unsaved; re-rendering from GT.goals
            // snaps it back.
            if (!dropped) renderGoalList();
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

      var gtShareIconBtn = document.getElementById('gtShareIconBtn');
      var gtShareCard = document.getElementById('gtShareCard');
      if (gtShareIconBtn) {
        function setGtShareOpen(open) {
          gtShareCard.hidden = !open;
          gtShareIconBtn.classList.toggle('open', open);
        }
        gtShareIconBtn.addEventListener('click', function () {
          setGtShareOpen(gtShareCard.hidden);
        });
        document.addEventListener('click', function (e) {
          var wrap = document.querySelector('.gt-share-wrap');
          if (wrap && !wrap.contains(e.target)) setGtShareOpen(false);
        });
      }

      function resetGoalTrackingShareState() {
        var genBtn = document.getElementById('gtShareGenerateBtn');
        var linkBtn = document.getElementById('gtShareLinkBtn');
        if (!genBtn || !linkBtn) return;
        genBtn.hidden = false;
        genBtn.disabled = false;
        genBtn.classList.remove('action-failed');
        linkBtn.hidden = true;
        linkBtn.textContent = '';
        delete linkBtn.dataset.url;
      }

      // GENERATE SHAREABLE LINK: freezes the whole goal list into a
      // SharedContent row (POST /api/goals/share, app/main.py); no id to pick.
      // Null-guarded like gtShareIconBtn (see mmShareGenerateBtn).
      var gtShareGenerateBtn = document.getElementById('gtShareGenerateBtn');
      if (gtShareGenerateBtn) {
        gtShareGenerateBtn.addEventListener('click', function () {
          var btn = this;
          btn.disabled = true;
          fetch('/api/goals/share', { method: 'POST' })
            .then(function (res) { return res.ok ? res.json() : Promise.reject(); })
            .then(function (data) {
              var linkBtn = document.getElementById('gtShareLinkBtn');
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

      var gtShareLinkBtn = document.getElementById('gtShareLinkBtn');
      if (gtShareLinkBtn) {
        gtShareLinkBtn.addEventListener('click', function () {
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

      // Load + poll (5s like PG.pollTimer/loadSummary); one endpoint serves the
      // initial paint and refreshes.

      async function loadGoals() {
        if (GT.dragging) return; // a touch long-press drag is in flight
        var data = await apiCall('/api/goals');
        if (!data || GT.dragging) return;
        applyGoalsResponse(data);
      }


      // Touch only (real page and homepage preview)
      if (GT_TOUCH) {
        // Tap tooltips: only the info icon has content. On the homepage this
        // filter is shared with the other previews, whose tooltips stay.
        window.myscapeTouchTooltipFilter = function (el) {
          if (ON_LANDING && !(el.closest && el.closest('.landing-goal-tracking-preview'))) return true;
          return !(el.closest && el.closest('.gt-sort-tab, .gt-share-icon-btn, .gt-share-link-btn, .gt-goal-delete'));
        };

        // Keyboard: keep a focused text field (and some of its suggestion list)
        // above the on-screen keyboard.
        (function () {
          var vv = window.visualViewport;
          var pending = null;
          function isTextField(el) {
            return !!el && el.tagName === 'INPUT' && /^(text|search|number|tel|)$/.test(el.type || '');
          }
          function reveal() {
            var el = document.activeElement;
            if (!isTextField(el)) return;
            var viewTop = vv ? vv.offsetTop : 0;
            var viewBottom = viewTop + (vv ? vv.height : window.innerHeight);
            var r = el.getBoundingClientRect();
            var need = r.bottom + 16;
            var sug = document.querySelector('.gt-suggestions.show');
            if (sug) need = Math.min(sug.getBoundingClientRect().bottom, r.bottom + 170) + 8;
            var dy = need - viewBottom;
            if (dy > 0) {
              dy = Math.min(dy, Math.max(0, r.top - viewTop - 8));
              if (dy > 0) window.scrollBy({ top: dy, left: 0, behavior: 'smooth' });
            } else if (r.top < viewTop + 8) {
              window.scrollBy({ top: r.top - viewTop - 8, left: 0, behavior: 'smooth' });
            }
          }
          function schedule(delay) { clearTimeout(pending); pending = setTimeout(reveal, delay); }
          document.addEventListener('focusin', function (e) {
            if (!isTextField(e.target)) return;
            schedule(150); setTimeout(reveal, 450); setTimeout(reveal, 800);
          });
          document.addEventListener('input', function (e) {
            if (isTextField(e.target)) schedule(450);
          });
          if (vv) vv.addEventListener('resize', function () {
            if (isTextField(document.activeElement)) schedule(60);
          });
        })();

        // Long-press drag (Custom sort): a ~0.35s hold fires the same drag
        // events at the same handlers (stand-in dataTransfer) with a ghost copy,
        // since HTML5 drag is unreliable from a finger.
        (function () {
          var HOLD_MS = 350, MOVE_TOL = 10, EDGE = 90;
          var st = null;
          var SOURCE_SEL = '#gtGoalList .gt-goal-row[draggable="true"]';
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
            return target.dispatchEvent(ev);
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
            // Not on the homepage: its page is snap-scrolled screens and the
            // preview is one screen.
            if (ON_LANDING) { /* no edge auto-scroll */ }
            else if (st.y < EDGE) dy = -Math.ceil((EDGE - st.y) / 6);
            else if (st.y > window.innerHeight - EDGE) dy = Math.ceil((st.y - (window.innerHeight - EDGE)) / 6);
            if (dy) { window.scrollBy(0, dy); moveGhost(); hover(); }
            st.raf = requestAnimationFrame(scrollLoop);
          }
          function release(s) {
            if (s.src && s.wasDraggable != null) s.src.setAttribute('draggable', s.wasDraggable);
            GT.dragging = false;
          }
          function begin() {
            if (!st || st.active) return;
            if (!document.contains(st.src)) { st = null; GT.dragging = false; return; }
            st.active = true;
            fire('dragstart', st.src, st.x, st.y, st.dt);
            var r = st.src.getBoundingClientRect();
            var g = st.src.cloneNode(true);
            g.classList.remove('dragging');
            g.style.cssText = 'position:fixed;margin:0;pointer-events:none;z-index:9999;' +
              'width:' + r.width + 'px;height:' + r.height + 'px;transform:scale(1.03);box-sizing:border-box;' +
              'background:var(--panel);border:1px solid var(--gold-dim);opacity:1;' +
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
            GT.dragging = false;
            if (s.ghost && s.ghost.parentNode) s.ghost.parentNode.removeChild(s.ghost);
          }
          document.addEventListener('touchstart', function (e) {
            if (st || e.touches.length !== 1) return;
            var src = e.target.closest && e.target.closest(SOURCE_SEL);
            if (!src || e.target.closest('.gt-goal-delete')) return;
            var t = e.touches[0];
            st = { src: src, x0: t.clientX, y0: t.clientY, x: t.clientX, y: t.clientY,
                   active: false, dt: makeDT(), over: null, ghost: null, raf: 0,
                   timer: setTimeout(begin, HOLD_MS) };
            GT.dragging = true; // hold off the 5s refresh for the whole gesture
            // Chrome on Android starts a native drag after ~0.5s, cancelling the
            // touch; switch it off for this touch.
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
            if (st && st.active && e.cancelable) e.preventDefault();
            finish(true);
          }, { passive: false });
          document.addEventListener('touchcancel', function () { finish(false); });
          document.addEventListener('contextmenu', function (e) {
            if (st || (e.target.closest && e.target.closest(SOURCE_SEL))) e.preventDefault();
          });
          document.addEventListener('dragstart', function (e) {
            if (e.isTrusted && e.target.closest && e.target.closest(SOURCE_SEL)) e.preventDefault();
          }, true);
        })();
      }

      loadGoals();
      setInterval(loadGoals, 5000);
    })();
    """
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

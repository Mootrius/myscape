"""Mindmaps: the page, its shared view, and the landing preview."""
import json
import os
from html import escape
from typing import TYPE_CHECKING, Optional, Tuple

from app.pages.player import PlayerView
from app.pages.shell import _shell

if TYPE_CHECKING:
    from app.models import GameAccount, SharedContent


# Snapshot for the landing Mindmaps preview: one real mindmap pulled once from
# GET /api/mindmaps. Visitors edit it in memory only.
_LANDING_MINDMAP_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "landing_mindmap_demo.json"
)

_landing_mindmap_demo_data = None


def _get_landing_mindmap_demo_data() -> Optional[dict]:
    global _landing_mindmap_demo_data
    if _landing_mindmap_demo_data is None:
        try:
            with open(_LANDING_MINDMAP_DEMO_PATH, "r") as f:
                _landing_mindmap_demo_data = json.load(f)
        except (OSError, ValueError):
            return None
    return _landing_mindmap_demo_data


# Local snapshot for the Mindmaps preview's goal-criteria search
# (KC/item/quest), run client-side so visitors' cookies never reach the real
# endpoints. Full NPC and quest lists (app/npc_names.py, app/quest_names.py) but
# only a ~175-item subset of items (the full snapshot is ~1MB).
_LANDING_MINDMAP_SEARCH_POOLS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "landing_mindmap_search_pools.json"
)

_landing_mindmap_search_pools_data = None


def _get_landing_mindmap_search_pools_data() -> Optional[dict]:
    global _landing_mindmap_search_pools_data
    if _landing_mindmap_search_pools_data is None:
        try:
            with open(_LANDING_MINDMAP_SEARCH_POOLS_PATH, "r") as f:
                _landing_mindmap_search_pools_data = json.load(f)
        except (OSError, ValueError):
            return None
    return _landing_mindmap_search_pools_data


_MINDMAPS_CSS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css", "mindmaps.css"
)

try:
    _MINDMAPS_CSS_VERSION = int(os.path.getmtime(_MINDMAPS_CSS_PATH))
except OSError:
    _MINDMAPS_CSS_VERSION = 0


def render_landing_mindmap_preview() -> Optional[Tuple[str, str, str]]:
    """Interactive Mindmaps preview for the landing page, like
    render_landing_loot_preview/render_landing_purchase_preview: reuses
    _mindmaps_panel_markup unmodified with a wrapper script. The data is
    app/data/landing_mindmap_demo.json, a frozen GET /api/mindmaps pull of the
    real "Example" mindmap. Returns (extra_head, body, script), or None if the
    snapshot or its search-pools sidecar
    (_get_landing_mindmap_search_pools_data) can't be read.
    
    Unlike the other previews this one is fully editable, in memory only. Tree
    mutations in app/mindmaps.py never touch account state, so they are ported
    to JS. A node's `completed` flag (evaluate_completion) depends on live
    account state and is frozen per node id, except the gray manual toggle
    (setNodeGoal) and the root's flag (withRecomputedRoot).
    
    1. A `fetch` shim (local `var fetch`) that serves GET /api/mindmaps from
    DEMO_MINDMAP, applies the node-mutation endpoints to it in memory
    (validation failures reject as {{detail: "..."}} like the real 400),
    answers /api/npcs|items|quests/search from the bundled SEARCH_POOLS, and
    fails anything else so no call carries a visitor's session cookie.
    2. `localStorage` is shadowed by an in-memory object: the reused script
    persists myscape:mindmaps:editMode and :activeMindmapId, and the landing
    page shares an origin with the real Mindmaps page, so the preview would
    otherwise inherit and overwrite the visitor's real preferences.
    3. #mmSwitchBtn is wired once, so it gets the cloneNode+replaceWith strip.
    4. Wheel-zoom is disabled and touch pan/pinch only works in fullscreen, so
    the page keeps scrolling (see the comments in the wrapper script). No
    setInterval: the real page doesn't poll either.
    """
    demo = _get_landing_mindmap_demo_data()
    search_pools = _get_landing_mindmap_search_pools_data()
    if demo is None or search_pools is None:
        return None
    extra_head, body, script = _mindmaps_panel_markup()

    # Hero row (tagline left, image right; .mindmap-preview-hero in
    # mindmaps.css). The "Mindmaps" <h2> is hidden via CSS.
    hero_markup = """
    <div class="mindmap-preview-hero">
      <div class="mindmap-preview-tagline-wrap">
        <p class="mindmap-preview-tagline">
          <span class="mindmap-preview-tagline-gold">MINDMAPS</span> <span class="mindmap-preview-tagline-white">to plan every step of your grind.</span>
        </p>
      </div>
      <picture class="mindmap-preview-char">
        <source srcset="/static/img/landing-mindmap-preview-char.webp" type="image/webp">
        <img src="/static/img/landing-mindmap-preview-char.png" alt="" />
      </picture>
    </div>
    """
    body = hero_markup + body

    demo_json = json.dumps(demo)
    search_pools_json = json.dumps(search_pools)
    wrapper_script = f"""
    (function () {{
      var DEMO_STATE = {demo_json};
      var DEMO_MINDMAP = DEMO_STATE.mindmaps[0];
      var SEARCH_POOLS = {search_pools_json};
      var ITEM_ICON_CDN_BASE = 'https://static.runelite.net/cache/item/icon/';

      var localStorage = (function () {{
        var store = {{}};
        return {{
          getItem: function (k) {{ return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; }},
          setItem: function (k, v) {{ store[k] = String(v); }},
          removeItem: function (k) {{ delete store[k]; }},
        }};
      }})();

      // Mutation logic ported from app/mindmaps.py. Each function mirrors its
      // Python counterpart (validation, defaults, a new node array, never
      // mutated in place) so the fetch shim returns the real response shape;
      // withRecomputedRoot handles the one field never carried over.
      var NODE_COLORS = ['gray', 'red', 'orange', 'yellow', 'green', 'blue', 'purple', 'white'];
      var DEFAULT_COLOR = 'gray';
      var DEFAULT_TEXT = 'New';
      var MAX_NODE_TEXT_LENGTH = 120;
      var MAX_NODE_NOTE_LENGTH = 200;
      var GOAL_TYPE_BY_COLOR = {{ gray: 'manual', red: 'kc', orange: 'item', yellow: 'gp', green: 'skill', blue: 'quest', purple: 'diary', white: null }};
      var KC_ACTIVITY_TYPES = ['npc', 'pickpocket', 'event'];
      var SKILL_NAMES = {{}};
      ['attack', 'defence', 'strength', 'hitpoints', 'ranged', 'prayer', 'magic', 'cooking', 'woodcutting', 'fletching',
       'fishing', 'firemaking', 'crafting', 'smithing', 'mining', 'herblore', 'agility', 'thieving', 'slayer', 'farming',
       'runecraft', 'hunter', 'construction', 'sailing'].forEach(function (s) {{ SKILL_NAMES[s] = true; }});
      var DIARY_AREAS = {{}};
      ['ardougne', 'desert', 'falador', 'fremennik', 'kandarin', 'karamja', 'kourend_kebos', 'lumbridge_draynor',
       'morytania', 'varrock', 'western_provinces', 'wilderness'].forEach(function (a) {{ DIARY_AREAS[a] = true; }});
      var DIARY_TIERS = ['easy', 'medium', 'hard', 'elite'];
      var MAX_GOAL_NAME_LENGTH = 80;
      var MAX_KC_TARGET = 1000000, MAX_ITEM_QTY_TARGET = 2000000000, MAX_GP_TARGET = 100000000000;
      var MIN_SKILL_LEVEL = 1, MAX_SKILL_LEVEL = 126, MIN_SKILL_XP = 0, MAX_SKILL_XP = 200000000;

      function newNodeId() {{
        if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {{
          var r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
          return v.toString(16);
        }});
      }}
      function cleanText(text, allowEmpty) {{
        text = String(text == null ? '' : text).trim().slice(0, MAX_NODE_TEXT_LENGTH).trim();
        if (allowEmpty) return text;
        return text || DEFAULT_TEXT;
      }}
      function cleanNote(note) {{
        var cleaned = String(note == null ? '' : note).trim();
        var lines = cleaned.split('\\n');
        if (lines.length > 2) cleaned = lines.slice(0, 2).join('\\n');
        return cleaned.slice(0, MAX_NODE_NOTE_LENGTH);
      }}
      function cleanColor(color, isRoot) {{
        if (isRoot) return 'white';
        var cleaned = NODE_COLORS.indexOf(color) !== -1 ? color : DEFAULT_COLOR;
        return cleaned === 'white' ? DEFAULT_COLOR : cleaned;
      }}
      function cleanGoalText(value, fieldName) {{
        var text = String(value == null ? '' : value).trim().slice(0, MAX_GOAL_NAME_LENGTH);
        if (!text) throw new Error(fieldName + " can't be empty.");
        return text;
      }}
      function cleanIntInRange(value, fieldName, minimum, maximum) {{
        var n = Number(value);
        if (!isFinite(n)) throw new Error(fieldName + ' must be a whole number.');
        n = Math.trunc(n);
        if (n < minimum || n > maximum) throw new Error(fieldName + ' must be between ' + minimum + ' and ' + maximum + '.');
        return n;
      }}
      function cleanGoalDate(value, fieldName) {{
        var text = String(value == null ? '' : value).trim();
        if (!/^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(text)) throw new Error(fieldName + ' must be a YYYY-MM-DD date.');
        return text;
      }}
      function defaultGoal(color) {{
        var t = GOAL_TYPE_BY_COLOR[color];
        if (t === 'manual') return {{ manualComplete: false }};
        if (t == null) return null;
        return {{}};
      }}
      function cleanGoal(color, goal, requireComplete) {{
        var t = GOAL_TYPE_BY_COLOR[color];
        goal = (goal && typeof goal === 'object') ? goal : {{}};
        if (t === 'manual') return {{ manualComplete: !!goal.manualComplete }};
        if (t == null) return null;
        var cleaned = {{}};
        function field(name, cleanFn, missingMsg) {{
          var value = goal[name];
          if (value == null || value === '') {{
            if (requireComplete) throw new Error(missingMsg);
            return;
          }}
          cleaned[name] = cleanFn(value);
        }}
        if (t === 'kc') {{
          field('activityType', function (v) {{
            if (KC_ACTIVITY_TYPES.indexOf(v) === -1) throw new Error('activityType must be one of ' + KC_ACTIVITY_TYPES.join(', ') + '.');
            return v;
          }}, 'Pick what kind of activity this goal tracks.');
          field('sourceName', function (v) {{ return cleanGoalText(v, 'sourceName'); }}, 'Pick an NPC.');
          field('targetCount', function (v) {{ return cleanIntInRange(v, 'targetCount', 1, MAX_KC_TARGET); }}, 'Set a target kc.');
          if (goal.sinceDate) cleaned.sinceDate = cleanGoalDate(goal.sinceDate, 'sinceDate');
          return cleaned;
        }}
        if (t === 'item') {{
          field('itemName', function (v) {{ return cleanGoalText(v, 'itemName'); }}, 'Pick an item.');
          field('targetQty', function (v) {{ return cleanIntInRange(v, 'targetQty', 1, MAX_ITEM_QTY_TARGET); }}, 'Set a target quantity.');
          return cleaned;
        }}
        if (t === 'gp') {{
          field('targetGp', function (v) {{ return cleanIntInRange(v, 'targetGp', 1, MAX_GP_TARGET); }}, 'Set a gp target.');
          return cleaned;
        }}
        if (t === 'skill') {{
          field('skill', function (v) {{
            v = String(v).trim().toLowerCase();
            if (!SKILL_NAMES[v]) throw new Error('skill must be a real OSRS skill.');
            return v;
          }}, 'Pick a skill.');
          field('metric', function (v) {{
            if (v !== 'level' && v !== 'xp') throw new Error("metric must be 'level' or 'xp'.");
            return v;
          }}, 'Pick level or experience.');
          if (cleaned.metric === 'xp') {{
            field('target', function (v) {{ return cleanIntInRange(v, 'target', MIN_SKILL_XP, MAX_SKILL_XP); }}, 'Set an experience target.');
          }} else {{
            field('target', function (v) {{ return cleanIntInRange(v, 'target', MIN_SKILL_LEVEL, MAX_SKILL_LEVEL); }}, 'Set a level target.');
          }}
          return cleaned;
        }}
        if (t === 'quest') {{
          field('questName', function (v) {{ return cleanGoalText(v, 'questName'); }}, 'Pick a quest.');
          return cleaned;
        }}
        if (t === 'diary') {{
          field('area', function (v) {{
            v = String(v).trim().toLowerCase();
            if (!DIARY_AREAS[v]) throw new Error('area must be a real diary area.');
            return v;
          }}, 'Pick a diary area.');
          field('tier', function (v) {{
            v = String(v).trim().toLowerCase();
            if (DIARY_TIERS.indexOf(v) === -1) throw new Error('tier must be one of ' + DIARY_TIERS.join(', ') + '.');
            return v;
          }}, 'Pick a tier.');
          return cleaned;
        }}
        return cleaned;
      }}
      function findNode(nodes, id) {{
        for (var i = 0; i < nodes.length; i++) {{ if (nodes[i].id === id) return nodes[i]; }}
        return null;
      }}
      function childrenOf(nodes, parentId) {{
        return nodes.filter(function (n) {{ return n.parentId === parentId; }}).sort(function (a, b) {{ return a.order - b.order; }});
      }}
      function depthOf(nodes, id) {{
        var depth = 0, node = findNode(nodes, id);
        while (node && node.parentId != null) {{ node = findNode(nodes, node.parentId); depth++; }}
        return depth;
      }}
      function nextChildOrder(nodes, parentId) {{
        var kids = childrenOf(nodes, parentId);
        return kids.length ? kids[kids.length - 1].order + 1.0 : 0.0;
      }}
      function orderAfter(nodes, node) {{
        var sibs = childrenOf(nodes, node.parentId);
        var idx = sibs.findIndex(function (n) {{ return n.id === node.id; }});
        if (idx + 1 < sibs.length) return (node.order + sibs[idx + 1].order) / 2.0;
        return node.order + 1.0;
      }}
      function orderBefore(nodes, node) {{
        var sibs = childrenOf(nodes, node.parentId);
        var idx = sibs.findIndex(function (n) {{ return n.id === node.id; }});
        if (idx > 0) return (sibs[idx - 1].order + node.order) / 2.0;
        return node.order - 1.0;
      }}
      // Mirrors add_node in app/mindmaps.py; returns {{nodes, newId}}.
      function addNode(nodes, relativeId, relation, text, color, before) {{
        var relative = findNode(nodes, relativeId);
        if (!relative) throw new Error('That node no longer exists.');
        var newColor = cleanColor(color, false);
        var newNode = {{ id: newNodeId(), text: cleanText(text, true), color: newColor, goal: defaultGoal(newColor), completed: false }};
        if (relation === 'child') {{
          newNode.parentId = relativeId;
          newNode.order = nextChildOrder(nodes, relativeId);
          return {{ nodes: nodes.concat([newNode]), newId: newNode.id }};
        }}
        if (relation === 'sibling') {{
          if (relative.parentId == null) throw new Error("The root node can't have a sibling -- try adding a parent or child instead.");
          newNode.parentId = relative.parentId;
          newNode.order = before ? orderBefore(nodes, relative) : orderAfter(nodes, relative);
          return {{ nodes: nodes.concat([newNode]), newId: newNode.id }};
        }}
        if (relation === 'parent') {{
          if (relative.parentId == null) throw new Error("The root node can't have a parent added -- it's the one node every mindmap keeps.");
          newNode.parentId = relative.parentId;
          newNode.order = relative.order;
          var updated = nodes.map(function (n) {{
            if (n.id === relativeId) {{ n = Object.assign({{}}, n, {{ parentId: newNode.id, order: 0.0 }}); }}
            return n;
          }});
          return {{ nodes: updated.concat([newNode]), newId: newNode.id }};
        }}
        throw new Error("relation must be 'parent', 'child', or 'sibling'.");
      }}
      // Mirrors add_shared_child in app/mindmaps.py.
      function addSharedChild(nodes, parentIds, text, color) {{
        if (parentIds.length < 2) throw new Error('Select at least two nodes to add a shared child below them.');
        parentIds.forEach(function (pid) {{ if (!findNode(nodes, pid)) throw new Error('That node no longer exists.'); }});
        var depths = {{}};
        parentIds.forEach(function (pid) {{ depths[depthOf(nodes, pid)] = true; }});
        if (Object.keys(depths).length > 1) throw new Error('Selected nodes must all be at the same level to add a shared child below them.');
        var primaryParentId = parentIds[0];
        var newColor = cleanColor(color, false);
        var newNode = {{
          id: newNodeId(), text: cleanText(text, true), color: newColor, goal: defaultGoal(newColor), completed: false,
          parentId: primaryParentId, order: nextChildOrder(nodes, primaryParentId), extraParentIds: parentIds.slice(1),
        }};
        return {{ nodes: nodes.concat([newNode]), newId: newNode.id }};
      }}
      // Mirrors update_node in app/mindmaps.py: a color change resets `goal` to
      // a blank default and `completed` to false (the old criteria's frozen
      // value means nothing).
      function updateNode(nodes, nodeId, text, color, note) {{
        var node = findNode(nodes, nodeId);
        if (!node) throw new Error('That node no longer exists.');
        var isRoot = node.parentId == null;
        return nodes.map(function (n) {{
          if (n.id !== nodeId) return n;
          n = Object.assign({{}}, n);
          if (text != null) n.text = cleanText(text, false);
          if (color != null) {{
            var newColor = cleanColor(color, isRoot);
            if (newColor !== n.color) {{ n.goal = defaultGoal(newColor); n.completed = false; }}
            n.color = newColor;
          }}
          if (note != null) n.note = cleanNote(note);
          return n;
        }});
      }}
      function deleteNode(nodes, nodeId) {{
        var target = findNode(nodes, nodeId);
        if (!target) throw new Error('That node no longer exists.');
        if (target.parentId == null) throw new Error("The root node can't be deleted on its own -- delete the whole mindmap instead.");
        var toRemove = {{}};
        toRemove[nodeId] = true;
        var changed = true;
        while (changed) {{
          changed = false;
          nodes.forEach(function (n) {{
            if (!toRemove[n.id] && n.parentId != null && toRemove[n.parentId]) {{ toRemove[n.id] = true; changed = true; }}
          }});
        }}
        var kept = [];
        nodes.forEach(function (n) {{
          if (toRemove[n.id]) return;
          if (n.extraParentIds && n.extraParentIds.length) {{
            var pruned = n.extraParentIds.filter(function (pid) {{ return !toRemove[pid]; }});
            if (pruned.length !== n.extraParentIds.length) n = Object.assign({{}}, n, {{ extraParentIds: pruned }});
          }}
          kept.push(n);
        }});
        return kept;
      }}
      // Mirrors replace_nodes in app/mindmaps.py (what Undo/Redo restore
      // against). `completed` carries over from the restored snapshot rather
      // than being reset.
      function replaceNodes(nodes) {{
        if (!nodes || !nodes.length) throw new Error('A mindmap needs at least one node.');
        var ids = nodes.map(function (n) {{ return n.id; }});
        var idSet = {{}};
        var dup = false;
        ids.forEach(function (id) {{ if (id == null || idSet[id]) dup = true; idSet[id] = true; }});
        if (dup || Object.keys(idSet).length !== ids.length) throw new Error('Every node needs its own unique id.');
        var byId = {{}};
        nodes.forEach(function (n) {{ byId[n.id] = n; }});
        var roots = nodes.filter(function (n) {{ return n.parentId == null; }});
        if (roots.length !== 1) throw new Error('A mindmap needs exactly one root node.');
        nodes.forEach(function (n) {{ if (n.parentId != null && !idSet[n.parentId]) throw new Error("A node's parent must exist in the same tree."); }});
        nodes.forEach(function (n) {{
          var cur = n, hops = 0;
          while (cur && cur.parentId != null) {{
            hops++;
            if (hops > nodes.length) throw new Error('The submitted tree contains a cycle.');
            cur = byId[cur.parentId];
          }}
        }});
        return nodes.map(function (n) {{
          var isRoot = n.parentId == null;
          var newColor = cleanColor(n.color, isRoot);
          var newNode = {{
            id: n.id, parentId: n.parentId != null ? n.parentId : null,
            text: cleanText(n.text, true), color: newColor,
            goal: cleanGoal(newColor, n.goal, false),
            order: (typeof n.order === 'number') ? n.order : 0.0,
            completed: !!n.completed,
          }};
          if (n.note) newNode.note = cleanNote(n.note);
          if (n.extraParentIds && n.extraParentIds.length) {{
            var pruned = n.extraParentIds.filter(function (pid) {{ return idSet[pid] && pid !== n.id; }});
            if (pruned.length) newNode.extraParentIds = pruned;
          }}
          return newNode;
        }});
      }}
      // Mirrors set_node_goal in app/mindmaps.py. For a gray node `completed` IS
      // the cleaned manualComplete flag, the one completion check the demo can
      // keep live; other colors' `completed` stays as it was (criteria can't be
      // evaluated without account context).
      function setNodeGoal(nodes, nodeId, goal) {{
        var node = findNode(nodes, nodeId);
        if (!node) throw new Error('That node no longer exists.');
        var color = node.color || DEFAULT_COLOR;
        var cleaned = cleanGoal(color, goal, true);
        return nodes.map(function (n) {{
          if (n.id !== nodeId) return n;
          var out = Object.assign({{}}, n, {{ goal: cleaned }});
          if (color === 'gray') out.completed = !!(cleaned && cleaned.manualComplete);
          return out;
        }});
      }}
      // The root's `completed` is recomputed (evaluate_completion in
      // app/mindmaps.py): true iff there is at least one other node and every
      // one is complete. Other nodes' values are already known (frozen, or
      // toggled by setNodeGoal), so this is a pure aggregation.
      function findRootId(nodes) {{
        var r = nodes.find(function (n) {{ return n.parentId == null; }});
        return r ? r.id : null;
      }}
      function withRecomputedRoot(nodes) {{
        var rootId = findRootId(nodes);
        if (rootId == null) return nodes;
        var nonRoot = nodes.filter(function (n) {{ return n.id !== rootId; }});
        var rootComplete = nonRoot.length > 0 && nonRoot.every(function (n) {{ return !!n.completed; }});
        return nodes.map(function (n) {{ return n.id === rootId ? Object.assign({{}}, n, {{ completed: rootComplete }}) : n; }});
      }}
      function currentState() {{
        return {{ mindmaps: [Object.assign({{}}, DEMO_MINDMAP, {{ nodes: withRecomputedRoot(DEMO_MINDMAP.nodes) }})] }};
      }}

      // Local goal-criteria search (answered locally instead of reaching
      // /api/npcs|items|quests/search). Ranking is startswith then contains,
      // shortest first, as in search_npc_names/search_quest_names/search_items.
      function localSearchNames(list, query) {{
        var q = String(query || '').trim().toLowerCase();
        if (!q) return [];
        var starts = [], contains = [];
        list.forEach(function (name) {{
          var lname = name.toLowerCase();
          if (lname.indexOf(q) === 0) starts.push(name);
          else if (lname.indexOf(q) !== -1) contains.push(name);
        }});
        starts.sort(function (a, b) {{ return a.length - b.length; }});
        contains.sort(function (a, b) {{ return a.length - b.length; }});
        return starts.concat(contains).slice(0, 20);
      }}
      function localSearchItems(list, query) {{
        var q = String(query || '').trim().toLowerCase();
        if (!q) return [];
        var starts = [], contains = [];
        list.forEach(function (item) {{
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

        if (path === '/api/mindmaps' && method === 'GET') {{
          return ok(currentState());
        }}
        if (path === '/api/npcs/search' && method === 'GET') {{
          return ok({{ results: localSearchNames(SEARCH_POOLS.npcs, params.get('q')) }});
        }}
        if (path === '/api/quests/search' && method === 'GET') {{
          return ok({{ results: localSearchNames(SEARCH_POOLS.quests, params.get('q')) }});
        }}
        if (path === '/api/items/search' && method === 'GET') {{
          return ok({{ results: localSearchItems(SEARCH_POOLS.items, params.get('q')) }});
        }}

        var mmPrefix = '/api/mindmaps/' + encodeURIComponent(DEMO_MINDMAP.id);
        var body = {{}};
        try {{ body = opts.body ? JSON.parse(opts.body) : {{}}; }} catch (e) {{ body = {{}}; }}

        if (path === mmPrefix + '/nodes' && method === 'POST') {{
          try {{
            var res = addNode(DEMO_MINDMAP.nodes, body.relative_to, body.relation, body.text, body.color, !!body.before);
            DEMO_MINDMAP.nodes = res.nodes;
            var state = currentState();
            state.newNodeId = res.newId;
            return ok(state);
          }} catch (e) {{ return fail(e.message); }}
        }}
        if (path === mmPrefix + '/nodes/shared-child' && method === 'POST') {{
          try {{
            var res2 = addSharedChild(DEMO_MINDMAP.nodes, body.parent_ids || [], body.text, body.color);
            DEMO_MINDMAP.nodes = res2.nodes;
            var state2 = currentState();
            state2.newNodeId = res2.newId;
            return ok(state2);
          }} catch (e) {{ return fail(e.message); }}
        }}
        if (path === mmPrefix + '/nodes' && method === 'PUT') {{
          try {{
            DEMO_MINDMAP.nodes = replaceNodes(body.nodes || []);
            return ok(currentState());
          }} catch (e) {{ return fail(e.message); }}
        }}
        if (path.indexOf(mmPrefix + '/nodes/') === 0) {{
          var rest = path.slice((mmPrefix + '/nodes/').length);
          var isGoal = rest.slice(-5) === '/goal';
          var nodeId = decodeURIComponent(isGoal ? rest.slice(0, -5) : rest);
          if (method === 'PATCH' && isGoal) {{
            try {{
              DEMO_MINDMAP.nodes = setNodeGoal(DEMO_MINDMAP.nodes, nodeId, body.goal || {{}});
              if (body.note != null) DEMO_MINDMAP.nodes = updateNode(DEMO_MINDMAP.nodes, nodeId, null, null, body.note);
              return ok(currentState());
            }} catch (e) {{ return fail(e.message); }}
          }}
          if (method === 'PATCH') {{
            try {{
              DEMO_MINDMAP.nodes = updateNode(DEMO_MINDMAP.nodes, nodeId, body.text, body.color, body.note);
              return ok(currentState());
            }} catch (e) {{ return fail(e.message); }}
          }}
          if (method === 'DELETE') {{
            try {{
              DEMO_MINDMAP.nodes = deleteNode(DEMO_MINDMAP.nodes, nodeId);
              return ok(currentState());
            }} catch (e) {{ return fail(e.message); }}
          }}
        }}
        return fail('Not available in this preview.');
      }};

      // Disable wheel-zoom on the landing preview: only the toolbar buttons
      // zoom, unlike the real page. A capturing listener with stopPropagation
      // would also starve the landing page's window-level 'wheel' listener,
      // which drives its JS section-snapping scroll. Instead addEventListener is
      // shadowed on #mmCanvas itself (this instance, not the prototype) and the
      // reused script's one 'wheel' listener is wrapped: a plain wheel over the
      // canvas skips it and bubbles on to scroll-snap the page, while wheels
      // over the note textarea or goal-search popover still reach its bail-out
      // logic. Other event types pass through. In fullscreen the canvas covers
      // the page, so scroll-to-zoom is let through; this is checked on every
      // wheel event, since a session can enter and exit fullscreen.
      var mmCanvasForWheelPatch = document.getElementById('mmCanvas');
      if (mmCanvasForWheelPatch) {{
        var mmRealAddEventListener = mmCanvasForWheelPatch.addEventListener.bind(mmCanvasForWheelPatch);
        mmCanvasForWheelPatch.addEventListener = function (type, listener, opts) {{
          // Same for touch: on the homepage a finger swipe on the non-fullscreen
          // preview scrolls the page, not the map. The first finger still
          // reaches pointerdown/up (a tap deselects) but its moves are skipped
          // (no pan) and a second finger is dropped (no pinch).
          if (type === 'pointerdown' || type === 'pointermove') {{
            return mmRealAddEventListener(type, function (e) {{
              if (e.pointerType === 'touch' && !mmCanvasForWheelPatch.classList.contains('mm-fullscreen')) {{
                if (type === 'pointermove' || !e.isPrimary) return;
              }}
              return listener.call(this, e);
            }}, opts);
          }}
          if (type !== 'wheel') return mmRealAddEventListener(type, listener, opts);
          return mmRealAddEventListener('wheel', function (e) {{
            if (mmCanvasForWheelPatch.classList.contains('mm-fullscreen')) return listener(e);
            if (e.target.closest('[data-role="node-note-input"], .mm-node-note-text')) return listener(e);
            if (e.target.closest('[data-role="popover"]')) return listener(e);
          }}, opts);
        }};
      }}

      {script}

      // Neutralize the mindmap-switcher trigger: wired once on load, so the
      // one-time cloneNode+replaceWith strip works. Its menu never opens (only
      // one mindmap here).
      var switchBtn = document.getElementById('mmSwitchBtn');
      if (switchBtn) {{
        switchBtn.replaceWith(switchBtn.cloneNode(true));
        document.getElementById('mmSwitchBtn').style.cursor = 'default';
      }}

      // Remove the export icon and its popup (both in .mm-share-wrap): nothing
      // to share from an anonymous demo, and the reused script never looks them
      // up again.
      var shareWrap = document.querySelector('.mm-share-wrap');
      if (shareWrap) shareWrap.remove();

    }})();
    """
    return extra_head, body, wrapper_script


def _mindmaps_panel_markup() -> Tuple[str, str, str]:
    """Builds Mindmaps' (extra_head, body, script) triple, split out of
    render_mindmaps so render_landing_mindmap_preview can embed the same
    panel. Everything is rendered client-side from one JSON payload (GET
    /api/mindmaps, build_mindmaps_state in app/mindmaps.py); mutations return
    the recomputed state for render() to redraw. No polling, since nothing
    external changes a mindmap. The canvas is positioned <div>s plus one <svg>
    overlay laid out by computeLayout; node width/height match mindmaps.css so
    layout needs no DOM measurement.
    """
    extra_head = f'<link rel="stylesheet" href="/static/css/mindmaps.css?v={_MINDMAPS_CSS_VERSION}" />'
    body = """
    <h2 class="page-title">Mindmaps</h2>
    <div class="auth-error" id="mmError"></div>
    <div class="mm-name-form" id="mmNameForm" style="display:none;">
      <input type="text" id="mmNameInput" placeholder="Mindmap name" maxlength="60" />
      <button class="primary mm-name-form-save" id="mmNameSave" type="button">Save</button>
      <button class="btn-secondary" id="mmNameCancel" type="button">Cancel</button>
    </div>
    <div class="mm-empty-wrap" id="mmEmptyWrap">
      <p class="mm-empty" id="mmEmptyMsg">Loading&hellip;</p>
      <button class="primary" id="mmCreateFirstBtn" type="button" style="display:none;">Create your first mindmap</button>
    </div>
    <div id="mmBody" style="display:none;">
      <div class="mm-header">
        <div class="mm-menu-wrap">
          <button class="mm-switch-btn" id="mmSwitchBtn" type="button" data-tooltip="Mindmap options">
            <span class="mm-switch-name" id="mmSwitchName"></span>
            <span class="mm-switch-caret">&#9662;</span>
          </button>
          <div class="mm-menu" id="mmMenu" style="display:none;"></div>
        </div>
      </div>
      <div class="mm-canvas" id="mmCanvas">
        <div class="mm-zoom-controls">
          <button type="button" id="mmUndoBtn" data-tooltip="Undo" disabled>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>
          </button>
          <button type="button" id="mmRedoBtn" data-tooltip="Redo" disabled>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
          </button>
          <div class="mm-zoom-divider"></div>
          <button type="button" id="mmZoomIn" data-tooltip="Zoom in">+</button>
          <button type="button" id="mmZoomOut" data-tooltip="Zoom out">&minus;</button>
          <button type="button" id="mmZoomFit" data-tooltip="Fit to zoom">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="10.5" cy="10.5" r="6.5"></circle><line x1="20" y1="20" x2="15.5" y2="15.5"></line></svg>
          </button>
          <button type="button" id="mmFullscreenBtn" data-tooltip="Enter fullscreen">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>
          </button>
          <div class="mm-zoom-divider"></div>
          <button type="button" id="mmEditModeBtn" data-tooltip="Enter edit mode">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.83 2.83 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5Z"></path><path d="M15 5l4 4"></path></svg>
          </button>
        </div>
        <div class="mm-world" id="mmWorld">
          <svg class="mm-lines" id="mmLines"></svg>
          <div id="mmNodesLayer"></div>
        </div>
      </div>
    </div>
    """
    # Export icon next to the title, a popover like
    # loot-share-wrap/pm-share-wrap (duplicated with an mm- prefix) holding the
    # GENERATE SHAREABLE LINK flow (build_mindmap_share_snapshot in
    # app/mindmaps.py). Inserted via str.replace because body/script are plain
    # strings full of literal { }.
    mm_share_icon_btn = (
        ' <span class="mm-share-wrap">'
        '<button type="button" class="mm-share-icon-btn" id="mmShareIconBtn" aria-label="Share the currently selected mindmap" data-tooltip="Share the currently selected mindmap">'
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
        '<polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line>'
        '</svg></button>'
        '<div class="mm-share-card" id="mmShareCard" hidden>'
        '<button type="button" class="mm-share-generate-btn" id="mmShareGenerateBtn">GENERATE SHAREABLE LINK</button>'
        '<button type="button" class="mm-share-link-btn" id="mmShareLinkBtn" data-tooltip="Click to copy" hidden></button>'
        '<p class="mm-share-popup-hint">Links are active for 30 days, but can be<br>deleted sooner on your Account page.</p>'
        '</div>'
        '</span>'
    )
    body = body.replace(
        '<h2 class="page-title">Mindmaps</h2>',
        f'<h2 class="page-title">Mindmaps{mm_share_icon_btn}</h2>',
    )
    script = """
    (function () {
      // Must match mindmaps.css .mm-node width/height; layout is arithmetic on
      // these.
      var NODE_WIDTH = 160;
      var NODE_HEIGHT = 46;
      if (!document.body.classList.contains('landing')) {
        window.myscapeTouchTooltipFilter = function () { return false; };
      }
      var COL_WIDTH = 190;   // horizontal spacing between sibling leaf columns
      var ROW_HEIGHT = 110;  // vertical spacing between depth levels
      var MARGIN = 60;       // breathing room around the whole tree inside the world
      // Extra room below the last row for popovers that hang past their node
      // (POPOVER_HEIGHT_PAD); the tallest is about 260px.
      var POPOVER_HEIGHT_PAD = 420;

      // Mirrors NODE_COLORS in app/mindmaps.py (white is root-only); every
      // .mm-node-<color> CSS class assumes this set.
      var NODE_COLORS = ['gray', 'red', 'orange', 'yellow', 'green', 'blue', 'purple', 'white'];

      // Mirrors the goal-type constants in app/mindmaps.py (GOAL_TYPE_BY_COLOR,
      // SKILL_NAMES, DIARY_AREAS, DIARY_TIERS); the server re-validates via
      // clean_goal. Keep in sync.
      var GOAL_TYPE_BY_COLOR = {
        gray: 'manual', red: 'kc', orange: 'item', yellow: 'gp',
        green: 'skill', blue: 'quest', purple: 'diary', white: null,
      };
      // Goal-type picker options: every NODE_COLORS entry except "white", with
      // local clan rank icons (app/static/img/). Array order is the 3-column
      // grid order.
      var GOAL_TYPE_PICKER = [
        { color: 'red', label: 'KC', icon: '/static/img/icon-goal-kc.png' },
        { color: 'orange', label: 'ITEM', icon: '/static/img/icon-goal-item.png' },
        { color: 'yellow', label: 'GP', icon: '/static/img/icon-goal-gp.png' },
        { color: 'green', label: 'SKILL', icon: '/static/img/icon-goal-skill.png' },
        { color: 'blue', label: 'QUEST', icon: '/static/img/icon-goal-quest.png' },
        { color: 'purple', label: 'DIARY', icon: '/static/img/icon-goal-diary.png' },
        { color: 'gray', label: 'MANUAL' },
      ];
      var GOAL_TYPE_ICON_BY_COLOR = {};
      GOAL_TYPE_PICKER.forEach(function (opt) { if (opt.icon) GOAL_TYPE_ICON_BY_COLOR[opt.color] = opt.icon; });
      var NOTE_ICON_PAPER_SVG = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>';
      var NOTE_ICON_ARROW_SVG = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">' +
        '<line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>';
      var SKILL_NAMES = [
        'attack', 'defence', 'strength', 'hitpoints', 'ranged', 'prayer', 'magic',
        'cooking', 'woodcutting', 'fletching', 'fishing', 'firemaking', 'crafting',
        'smithing', 'mining', 'herblore', 'agility', 'thieving', 'slayer', 'farming',
        'runecraft', 'hunter', 'construction', 'sailing',
      ];
      // Mirrors MIN/MAX_SKILL_LEVEL and MIN/MAX_SKILL_XP in app/mindmaps.py for
      // validateSkillTarget. Levels run 1-126 (virtual levels); level 1 / 0 xp
      // are valid so the LVL/XP toggle never lands out of range.
      var MIN_SKILL_LEVEL = 1, MAX_SKILL_LEVEL = 126;
      var MIN_SKILL_XP = 0, MAX_SKILL_XP = 200000000;
      var MAX_KC_TARGET = 1000000;
      var MAX_ITEM_QTY_TARGET = 2000000000;
      var MAX_GP_TARGET = 100000000000;
      // OSRS xp-per-level curve for levels 1-126
      // (https://oldschool.runescape.wiki/w/Experience). SKILL_XP_TABLE[L] is
      // the xp for level L (index 0 unused).
      var SKILL_XP_TABLE = (function () {
        var table = [0, 0];
        var cumulative = 0;
        for (var l = 1; l < MAX_SKILL_LEVEL; l++) {
          cumulative += Math.floor(l + 300 * Math.pow(2, l / 7));
          table[l + 1] = Math.floor(cumulative / 4);
        }
        return table;
      })();
      function xpForLevel(level) {
        level = Math.max(MIN_SKILL_LEVEL, Math.min(MAX_SKILL_LEVEL, Math.round(level)));
        return SKILL_XP_TABLE[level];
      }
      function levelForXp(xp) {
        for (var l = MAX_SKILL_LEVEL; l >= MIN_SKILL_LEVEL; l--) {
          if (xp >= SKILL_XP_TABLE[l]) return l;
        }
        return MIN_SKILL_LEVEL;
      }
      var GOAL_SEARCH_ENDPOINTS = {
        npc: '/api/npcs/search',
        item: '/api/items/search',
        quest: '/api/quests/search',
      };
      var DIARY_AREAS = [
        'ardougne', 'desert', 'falador', 'fremennik', 'kandarin', 'karamja',
        'kourend_kebos', 'lumbridge_draynor', 'morytania', 'varrock',
        'western_provinces', 'wilderness',
      ];
      // Some diary names need explicit labels ("Kourend & Kebos", "Lumbridge &
      // Draynor").
      var DIARY_AREA_LABELS = {
        ardougne: 'Ardougne', desert: 'Desert', falador: 'Falador',
        fremennik: 'Fremennik', kandarin: 'Kandarin', karamja: 'Karamja',
        kourend_kebos: 'Kourend & Kebos', lumbridge_draynor: 'Lumbridge & Draynor',
        morytania: 'Morytania', varrock: 'Varrock',
        western_provinces: 'Western Provinces', wilderness: 'Wilderness',
      };
      var DIARY_TIERS = ['easy', 'medium', 'hard', 'elite'];
      function titleCase(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
      // Each diary's icon is its elite-tier reward item
      // (https://oldschool.runescape.wiki/w/Achievement_Diary), via RuneLite CDN
      // URLs like item_icon_url in app/purchase_goals.py.
      var DIARY_AREA_ICON = {
        ardougne: 'https://static.runelite.net/cache/item/icon/13124.png',
        desert: 'https://static.runelite.net/cache/item/icon/13136.png',
        falador: 'https://static.runelite.net/cache/item/icon/13120.png',
        fremennik: 'https://static.runelite.net/cache/item/icon/13132.png',
        kandarin: 'https://static.runelite.net/cache/item/icon/13140.png',
        karamja: 'https://static.runelite.net/cache/item/icon/13103.png',
        kourend_kebos: 'https://static.runelite.net/cache/item/icon/22947.png',
        lumbridge_draynor: 'https://static.runelite.net/cache/item/icon/13128.png',
        morytania: 'https://static.runelite.net/cache/item/icon/13115.png',
        varrock: 'https://static.runelite.net/cache/item/icon/13107.png',
        western_provinces: 'https://static.runelite.net/cache/item/icon/13144.png',
        wilderness: 'https://static.runelite.net/cache/item/icon/13111.png',
      };
      var LOCAL_SEARCH_POOLS = {
        skill: SKILL_NAMES.map(function (key) {
          return { value: key, label: titleCase(key), icon: '/static/skill-icons/' + key + '.png' };
        }).sort(function (a, b) { return a.label.localeCompare(b.label); }),
        diary: DIARY_AREAS.map(function (area) {
          return { value: area, label: DIARY_AREA_LABELS[area], icon: DIARY_AREA_ICON[area] };
        }).sort(function (a, b) { return a.label.localeCompare(b.label); }),
      };

      var MM = {
        data: null,
        activeMindmapId: null,
        selectedNodeId: null,
        focusNodeId: null, // one-shot: focus + select this node's text on the next render
        multiSelectIds: new Set(),
        flippedNodeIds: new Set(),
        nameFormMode: null, // 'new' | 'rename' | null
        pan: { x: 0, y: 0 },
        zoom: 1,
        lastLayout: null, // set by renderCanvas, read by zoomToFit
        undoStack: [],
        redoStack: [],
        editMode: false,
        fullscreen: false,
      };
      MM.editMode = loadStoredEditMode();

      var ACTIVE_MINDMAP_STORAGE_KEY = 'myscape:mindmaps:activeMindmapId';
      function loadStoredActiveMindmapId() {
        try { return localStorage.getItem(ACTIVE_MINDMAP_STORAGE_KEY); } catch (e) { return null; }
      }
      function setActiveMindmapId(id) {
        resetMindmapShareState();
        MM.activeMindmapId = id;
        MM.undoStack = [];
        MM.redoStack = [];
        try {
          if (id) localStorage.setItem(ACTIVE_MINDMAP_STORAGE_KEY, id);
          else localStorage.removeItem(ACTIVE_MINDMAP_STORAGE_KEY);
        } catch (e) { /* ignore -- see comment above */ }
      }

      // Edit Mode (pencil toggle, #mmEditModeBtn/updateEditModeButton),
      // persisted per browser like ACTIVE_MINDMAP_STORAGE_KEY.
      // - OFF (default): pan/zoom/select, plus the GRAY node's "Mark complete"
      // toggle.
      // - ON: the full editor (labels, edge "+" buttons, swatches, delete, goal
      // forms, multi-select/shared-child).
      var EDIT_MODE_STORAGE_KEY = 'myscape:mindmaps:editMode';
      function loadStoredEditMode() {
        try { return localStorage.getItem(EDIT_MODE_STORAGE_KEY) === '1'; } catch (e) { return false; }
      }
      function setEditMode(on) {
        if (on === MM.editMode) return;
        commitActiveLabelIfEditing();
        MM.editMode = on;
        try {
          if (on) localStorage.setItem(EDIT_MODE_STORAGE_KEY, '1');
          else localStorage.removeItem(EDIT_MODE_STORAGE_KEY);
        } catch (e) { /* ignore -- see ACTIVE_MINDMAP_STORAGE_KEY's own comment */ }
        if (!on && MM.multiSelectIds.size > 1) {
          MM.multiSelectIds = MM.selectedNodeId ? new Set([MM.selectedNodeId]) : new Set();
        }
        // Entering edit mode flips nodes back to their front face: the
        // note-toggle icon is hidden in edit mode (.mm-view-mode), so a flipped
        // note couldn't be flipped back.
        if (on) MM.flippedNodeIds.clear();
        render();
      }

      function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
          return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
      }

      function showError(msg) {
        var el = document.getElementById('mmError');
        if (!msg) { el.classList.remove('show'); el.textContent = ''; return; }
        el.textContent = msg;
        el.classList.add('show');
      }

      async function apiCall(url, options) {
        try {
          const res = await fetch(url, options);
          const data = await res.json().catch(function () { return {}; });
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

      function activeMindmap() {
        if (!MM.data || !MM.activeMindmapId) return null;
        return MM.data.mindmaps.find(function (m) { return m.id === MM.activeMindmapId; }) || null;
      }

      function selectedNode() {
        var mm = activeMindmap();
        if (!mm || !MM.selectedNodeId) return null;
        return mm.nodes.find(function (n) { return n.id === MM.selectedNodeId; }) || null;
      }

      // Tree layout: top-down, no library. Each leaf gets its own column so
      // subtrees can't overlap; each parent centers over its first and last
      // child.
      function computeLayout(nodes) {
        var childrenMap = new Map();
        nodes.forEach(function (n) {
          if (!childrenMap.has(n.parentId)) childrenMap.set(n.parentId, []);
          childrenMap.get(n.parentId).push(n);
        });
        childrenMap.forEach(function (list) { list.sort(function (a, b) { return a.order - b.order; }); });

        var root = nodes.find(function (n) { return n.parentId === null; });
        var positions = {};
        var leafCounter = { value: 0 };
        var maxDepth = 0;

        function walk(node, depth) {
          maxDepth = Math.max(maxDepth, depth);
          var kids = childrenMap.get(node.id) || [];
          var unitX;
          if (kids.length === 0) {
            unitX = leafCounter.value;
            leafCounter.value += 1;
          } else {
            var childXs = kids.map(function (c) { return walk(c, depth + 1); });
            unitX = (childXs[0] + childXs[childXs.length - 1]) / 2;
          }
          positions[node.id] = { x: unitX * COL_WIDTH + MARGIN, y: depth * ROW_HEIGHT + MARGIN, depth: depth };
          return unitX;
        }
        if (root) walk(root, 0);

        // A shared child (extraParentIds) is centered under all its linked
        // parents, clamped against same-depth nodes to keep one column of
        // spacing (keeps its own column if packed).
        nodes.forEach(function (n) {
          if (!n.extraParentIds || !n.extraParentIds.length) return;
          var linkedIds = [n.parentId].concat(n.extraParentIds);
          var centers = [];
          linkedIds.forEach(function (pid) {
            var p = positions[pid];
            if (p) centers.push(p.x + NODE_WIDTH / 2);
          });
          if (!centers.length) return;
          var avgCenter = centers.reduce(function (a, b) { return a + b; }, 0) / centers.length;

          var ownDepth = positions[n.id].depth;
          var minAllowed = -Infinity, maxAllowed = Infinity;
          Object.keys(positions).forEach(function (otherId) {
            if (otherId === n.id) return;
            var otherPos = positions[otherId];
            if (otherPos.depth !== ownDepth) return;
            var otherCenter = otherPos.x + NODE_WIDTH / 2;
            if (otherCenter <= avgCenter) {
              minAllowed = Math.max(minAllowed, otherCenter + COL_WIDTH);
            } else {
              maxAllowed = Math.min(maxAllowed, otherCenter - COL_WIDTH);
            }
          });

          var clampedCenter = avgCenter;
          if (minAllowed > maxAllowed) {
            clampedCenter = positions[n.id].x + NODE_WIDTH / 2;
          } else {
            if (clampedCenter < minAllowed) clampedCenter = minAllowed;
            if (clampedCenter > maxAllowed) clampedCenter = maxAllowed;
          }

          var oldCenter = positions[n.id].x + NODE_WIDTH / 2;
          var delta = clampedCenter - oldCenter;
          positions[n.id].x = clampedCenter - NODE_WIDTH / 2;
          if (delta !== 0) {
            (function shiftSubtree(nodeId) {
              (childrenMap.get(nodeId) || []).forEach(function (kid) {
                if (positions[kid.id]) {
                  positions[kid.id].x += delta;
                  shiftSubtree(kid.id);
                }
              });
            })(n.id);
          }
        });

        return {
          positions: positions,
          childrenMap: childrenMap,
          root: root,
          worldWidth: Math.max(1, leafCounter.value) * COL_WIDTH + MARGIN * 2,
          worldHeight: (maxDepth + 1) * ROW_HEIGHT + MARGIN * 2,
        };
      }

      // Pan/zoom

      var mmWorldEl = document.getElementById('mmWorld');
      function applyTransform() {
        mmWorldEl.style.transform =
          'translate(' + MM.pan.x + 'px, ' + MM.pan.y + 'px) scale(' + MM.zoom + ')';
        positionFloatingSuggestions();
      }

      var MIN_ZOOM = 0.2;
      var MAX_ZOOM = 2;

      // Zooms around (originX, originY) in viewport pixels (default: center) by
      // re-solving pan so the world point under the origin stays put.
      function setZoom(z, originX, originY) {
        var canvas = document.getElementById('mmCanvas');
        if (originX == null) originX = canvas.clientWidth / 2;
        if (originY == null) originY = canvas.clientHeight / 2;
        var newZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, z));
        if (newZoom !== MM.zoom) {
          var worldX = (originX - MM.pan.x) / MM.zoom;
          var worldY = (originY - MM.pan.y) / MM.zoom;
          MM.zoom = newZoom;
          MM.pan.x = originX - worldX * MM.zoom;
          MM.pan.y = originY - worldY * MM.zoom;
          applyTransform();
        }
        updateZoomButtons();
      }

      // Nudges the pan (never the zoom) so an open popover's edges clear
      // .mm-canvas when its node is near the bottom (POPOVER_HEIGHT_PAD) or off
      // to a side. Called after every render, since popover size varies by goal
      // type. Uses MM.pan/applyTransform instead of native scroll-into-view,
      // which scrolls .mm-canvas and drags the zoom controls out of the box.
      // Overflow is measured against the current MM.pan, never a remembered
      // baseline, which would snap the view back when switching from a tall goal
      // type to a short one that fits.
      function ensurePopoverVisible() {
        var popover = document.querySelector('#mmNodesLayer [data-role="popover"]');
        if (!popover) return;
        var layout = MM.lastLayout;
        var pos = layout && MM.selectedNodeId ? layout.positions[MM.selectedNodeId] : null;
        if (!pos) return;
        var canvas = document.getElementById('mmCanvas');
        var canvasRect = canvas.getBoundingClientRect();
        // Computed analytically, not via getBoundingClientRect(): .mm-world has
        // a 0.18s transform transition, so a rapid popover change would measure
        // it mid-glide. screen = pan + zoom * local (transform-origin 0 0) using
        // the authoritative MM.pan/MM.zoom; the popover's local box comes from
        // its CSS (.mm-node-popover: top calc(100% + 22px), left
        // 50%/translateX(-50%)) plus offsetWidth/offsetHeight.
        var localTop = pos.y + NODE_HEIGHT + 22;
        var localBottom = localTop + popover.offsetHeight;
        var localCenterX = pos.x + NODE_WIDTH / 2;
        var localLeft = localCenterX - popover.offsetWidth / 2;
        var localRight = localCenterX + popover.offsetWidth / 2;
        var MARGIN = 16;

        var targetPanY = MM.pan.y;
        var screenTop = canvasRect.top + targetPanY + MM.zoom * localTop;
        var screenBottom = canvasRect.top + targetPanY + MM.zoom * localBottom;
        var overflowBelow = screenBottom - (canvasRect.bottom - MARGIN);
        var overflowAbove = (canvasRect.top + MARGIN) - screenTop;
        if (overflowBelow > 0) {
          targetPanY -= overflowBelow;
        } else if (overflowAbove > 0) {
          targetPanY += overflowAbove;
        }
        if (targetPanY !== MM.pan.y) {
          MM.pan.y = targetPanY;
          applyTransform();
        }

        var targetPanX = MM.pan.x;
        var screenLeft = canvasRect.left + targetPanX + MM.zoom * localLeft;
        var screenRight = canvasRect.left + targetPanX + MM.zoom * localRight;
        var overflowRight = screenRight - (canvasRect.right - MARGIN);
        var overflowLeft = (canvasRect.left + MARGIN) - screenLeft;
        if (overflowRight > 0) {
          targetPanX -= overflowRight;
        } else if (overflowLeft > 0) {
          targetPanX += overflowLeft;
        }
        if (targetPanX !== MM.pan.x) {
          MM.pan.x = targetPanX;
          applyTransform();
        }
      }

      // Deliberate no-op: scrolling the outer page for a popover made it jerk on
      // ordinary clicks. Kept so its call sites stay unchanged.
      function scrollCanvasPopoverIntoView() {
        if (MM.fullscreen) return;
      }

      // Fits the tree's bounding box in the viewport (clamped to
      // MIN_ZOOM-MAX_ZOOM) and centers it, using the tight box of node positions
      // rather than layout.worldWidth/worldHeight. Also frames every
      // load/switch/create/delete.
      function zoomToFit() {
        var layout = MM.lastLayout;
        if (!layout) return;
        var ids = Object.keys(layout.positions);
        if (!ids.length) return;
        var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        ids.forEach(function (id) {
          var pos = layout.positions[id];
          minX = Math.min(minX, pos.x);
          minY = Math.min(minY, pos.y);
          maxX = Math.max(maxX, pos.x + NODE_WIDTH);
          maxY = Math.max(maxY, pos.y + NODE_HEIGHT);
        });
        var boxW = maxX - minX, boxH = maxY - minY;
        var canvas = document.getElementById('mmCanvas');
        var viewW = canvas.clientWidth, viewH = canvas.clientHeight;
        var pad = (window.matchMedia && window.matchMedia('(max-width: 700px)').matches) ? 16 : 40; // breathing room inside the viewport edges
        var availW = Math.max(1, viewW - pad * 2), availH = Math.max(1, viewH - pad * 2);
        var z = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Math.min(availW / boxW, availH / boxH)));
        MM.zoom = z;
        var boxCenterX = minX + boxW / 2, boxCenterY = minY + boxH / 2;
        MM.pan.x = viewW / 2 - boxCenterX * z;
        MM.pan.y = viewH / 2 - boxCenterY * z;
        applyTransform();
        updateZoomButtons();
      }

      function commitActiveLabelIfEditing() {
        var el = document.activeElement;
        if (el && el.isContentEditable && el.getAttribute && el.getAttribute('data-role') === 'label') el.blur();
      }

      var MM_FULLSCREEN_ENTER_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>';
      var MM_FULLSCREEN_EXIT_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline><line x1="14" y1="10" x2="21" y2="3"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>';

      // Fullscreen fills the window via a CSS class (.mm-canvas.mm-fullscreen),
      // not the Fullscreen API: no permission prompt, and Escape closes it.
      // Document scroll is locked because the canvas's slot collapses once
      // position: fixed.
      function setFullscreen(on) {
        if (on === MM.fullscreen) return;
        commitActiveLabelIfEditing();
        MM.fullscreen = on;
        document.getElementById('mmCanvas').classList.toggle('mm-fullscreen', on);
        document.documentElement.style.overflow = on ? 'hidden' : '';
        var btn = document.getElementById('mmFullscreenBtn');
        btn.classList.toggle('active', on);
        btn.setAttribute('data-tooltip', on ? 'Exit fullscreen' : 'Enter fullscreen');
        btn.innerHTML = on ? MM_FULLSCREEN_EXIT_ICON : MM_FULLSCREEN_ENTER_ICON;
        zoomToFit();
        // zoomToFit doesn't know a popover may be open, and fullscreen toggling
        // skips render()'s popover-visibility effect, so an open popover would
        // be left off-screen.
        if (MM.selectedNodeId) {
          // zoomToFit's applyTransform() just started the 0.18s transition, so
          // measuring the popover now would be mid-flight; land this step
          // instantly.
          mmWorldEl.style.transitionDuration = '0s';
          ensurePopoverVisible();
          scrollCanvasPopoverIntoView();
          mmWorldEl.style.transitionDuration = '';
        }
      }

      // Blurring a still-editing label fires its text-commit PATCH. A click on
      // the same node would race a second request and flash a stray caret, so
      // the click delegation awaits this first.
      var pendingLabelCommit = null;

      var canvasEl = document.getElementById('mmCanvas');
      var panState = { active: false, startX: 0, startY: 0, startPanX: 0, startPanY: 0, moved: false };
      canvasEl.addEventListener('pointerdown', function (e) {
        commitActiveLabelIfEditing();
        if (e.pointerType === 'touch') return;
        if (e.target.closest('.mm-node') || e.target.closest('.mm-zoom-controls')) return;
        panState.active = true;
        panState.moved = false;
        panState.startX = e.clientX;
        panState.startY = e.clientY;
        panState.startPanX = MM.pan.x;
        panState.startPanY = MM.pan.y;
        canvasEl.setPointerCapture(e.pointerId);
        canvasEl.classList.add('panning');
        mmWorldEl.style.transitionDuration = '0s'; // dragging must track the cursor 1:1, never smoothed
      });
      canvasEl.addEventListener('pointermove', function (e) {
        if (!panState.active) return;
        var dx = e.clientX - panState.startX, dy = e.clientY - panState.startY;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) panState.moved = true;
        MM.pan.x = panState.startPanX + dx;
        MM.pan.y = panState.startPanY + dy;
        applyTransform();
      });
      function endPan() {
        if (!panState.active) return;
        panState.active = false;
        canvasEl.classList.remove('panning');
        mmWorldEl.style.transitionDuration = ''; // hand back to .mm-world's own smooth-zoom transition
        if (!panState.moved) selectNode(null); // a plain click on empty canvas deselects
      }
      canvasEl.addEventListener('pointerup', endPan);
      canvasEl.addEventListener('pointercancel', endPan);

      // Touch: pinch-to-zoom, two-finger pan, one-finger pan. .mm-canvas is
      // touch-action: none, so fingers arrive as pointer events (up to two
      // tracked). One finger pans past a small slop (so a tap on a node still
      // selects); two fingers pinch around the starting midpoint. Transitions
      // are off during the gesture and taps ending it are swallowed.
      var touchPtrs = {};
      var touchPan = null;
      var pinch = null;
      var touchClickBlockUntil = 0;
      var TOUCH_SLOP = 8;
      function touchIds() { return Object.keys(touchPtrs); }
      function touchIgnored(t) {
        return !!(t.closest && t.closest('.mm-zoom-controls, [data-role="popover"], .mm-suggestions, input, textarea, select, [contenteditable="true"], .mm-edge-btn, [data-role="manual-toggle"], [data-role="note-toggle"]'));
      }
      function touchFinish() {
        canvasEl.classList.remove('panning');
        mmWorldEl.style.transitionDuration = '';
      }
      function touchHoldPointer(id) {
        try { canvasEl.setPointerCapture(id); } catch (_) {}
      }
      function startPinch() {
        var ids = touchIds();
        var a = touchPtrs[ids[0]], b = touchPtrs[ids[1]];
        var rect = canvasEl.getBoundingClientRect();
        var mx = (a.x + b.x) / 2 - rect.left, my = (a.y + b.y) / 2 - rect.top;
        pinch = {
          dist: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)),
          zoom: MM.zoom,
          wx: (mx - MM.pan.x) / MM.zoom,
          wy: (my - MM.pan.y) / MM.zoom
        };
        touchPan = null;
        mmWorldEl.style.transitionDuration = '0s';
        canvasEl.classList.add('panning');
        touchClickBlockUntil = Date.now() + 600;
        ids.forEach(function (id) { touchHoldPointer(+id); });
      }
      function updatePinch() {
        var ids = touchIds();
        var a = touchPtrs[ids[0]], b = touchPtrs[ids[1]];
        if (!a || !b) return;
        var rect = canvasEl.getBoundingClientRect();
        var mx = (a.x + b.x) / 2 - rect.left, my = (a.y + b.y) / 2 - rect.top;
        var dist = Math.max(1, Math.hypot(a.x - b.x, a.y - b.y));
        var z = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, pinch.zoom * dist / pinch.dist));
        MM.zoom = z;
        MM.pan.x = mx - pinch.wx * z;
        MM.pan.y = my - pinch.wy * z;
        applyTransform();
        updateZoomButtons();
      }
      canvasEl.addEventListener('pointerdown', function (e) {
        if (e.pointerType !== 'touch' || touchIgnored(e.target)) return;
        if (touchIds().length >= 2) return; // a third finger is ignored
        touchPtrs[e.pointerId] = { x: e.clientX, y: e.clientY };
        if (touchIds().length === 1) {
          touchPan = {
            id: e.pointerId, sx: e.clientX, sy: e.clientY,
            px: MM.pan.x, py: MM.pan.y, moved: false,
            empty: !e.target.closest('.mm-node')
          };
        } else {
          startPinch();
        }
      }, true);
      canvasEl.addEventListener('pointermove', function (e) {
        if (e.pointerType !== 'touch') return;
        var p = touchPtrs[e.pointerId];
        if (!p) return;
        p.x = e.clientX; p.y = e.clientY;
        if (pinch) { updatePinch(); return; }
        if (!touchPan || touchPan.id !== e.pointerId) return;
        var dx = e.clientX - touchPan.sx, dy = e.clientY - touchPan.sy;
        if (!touchPan.moved) {
          if (Math.hypot(dx, dy) < TOUCH_SLOP) return;
          touchPan.moved = true;
          // Re-base so the view doesn't jump by the slop distance.
          touchPan.sx = e.clientX; touchPan.sy = e.clientY;
          touchPan.px = MM.pan.x; touchPan.py = MM.pan.y;
          dx = 0; dy = 0;
          touchHoldPointer(e.pointerId);
          canvasEl.classList.add('panning');
          mmWorldEl.style.transitionDuration = '0s';
        }
        MM.pan.x = touchPan.px + dx;
        MM.pan.y = touchPan.py + dy;
        applyTransform();
      });
      function touchEnd(e) {
        if (e.pointerType !== 'touch' || !touchPtrs[e.pointerId]) return;
        delete touchPtrs[e.pointerId];
        var left = touchIds();
        if (pinch) {
          pinch = null;
          touchClickBlockUntil = Date.now() + 600;
          if (left.length === 1) {
            // One finger still down: carry on as a one-finger pan.
            var rest = touchPtrs[left[0]];
            touchPan = { id: +left[0], sx: rest.x, sy: rest.y, px: MM.pan.x, py: MM.pan.y, moved: true, empty: false };
          } else {
            touchFinish();
          }
          return;
        }
        if (touchPan && touchPan.id === e.pointerId) {
          var tp = touchPan;
          touchPan = null;
          if (tp.moved) {
            touchClickBlockUntil = Date.now() + 400;
            touchFinish();
          } else if (tp.empty && e.type === 'pointerup') {
            selectNode(null); // a plain tap on empty canvas deselects
          }
        }
      }
      canvasEl.addEventListener('pointerup', touchEnd);
      canvasEl.addEventListener('pointercancel', touchEnd);
      canvasEl.addEventListener('click', function (e) {
        if (Date.now() < touchClickBlockUntil && !e.target.closest('.mm-zoom-controls')) {
          e.stopPropagation();
          e.preventDefault();
        }
      }, true);
      // Wheel-zoom. Transitions stay off while wheel events keep arriving and
      // return after wheelSettleMs without one; otherwise each tick restarts the
      // 0.18s transition and a constantly re-transitioning layer blurs the
      // canvas. Tick size scales exponentially with deltaY since trackpad ticks
      // vary. Ticks apply instantly rather than eased via requestAnimationFrame:
      // a sustained per-frame ramp makes Chrome's compositor trade raster
      // fidelity for it, so the canvas goes soft while moving.
      var wheelZoomSensitivity = 0.0013;
      var wheelSettleTimer = null;
      var wheelSettleMs = 200;
      canvasEl.addEventListener('wheel', function (e) {
        // A wheel event over a popover (e.g. a long .mm-suggestions list) must
        // not zoom the canvas: bail without preventDefault so the browser
        // scrolls it. The note textarea and back face are overflow: hidden, so
        // swallow the event there or it leaks to the page scroll.
        if (e.target.closest('[data-role="node-note-input"], .mm-node-note-text')) {
          e.preventDefault();
          return;
        }
        if (e.target.closest('[data-role="popover"]')) return;
        e.preventDefault();
        mmWorldEl.style.transitionDuration = '0s';
        setZoom(MM.zoom * Math.exp(-e.deltaY * wheelZoomSensitivity));
        clearTimeout(wheelSettleTimer);
        wheelSettleTimer = setTimeout(function () {
          mmWorldEl.style.transitionDuration = ''; // hand back to .mm-world's own smooth-zoom transition
        }, wheelSettleMs);
      }, { passive: false });

      document.getElementById('mmZoomIn').addEventListener('click', function () { setZoom(MM.zoom + 0.15); });
      document.getElementById('mmZoomOut').addEventListener('click', function () { setZoom(MM.zoom - 0.15); });
      document.getElementById('mmZoomFit').addEventListener('click', zoomToFit);
      document.getElementById('mmUndoBtn').addEventListener('click', undo);
      document.getElementById('mmRedoBtn').addEventListener('click', redo);
      document.getElementById('mmFullscreenBtn').addEventListener('click', function () { setFullscreen(!MM.fullscreen); });
      document.getElementById('mmEditModeBtn').addEventListener('click', function () { setEditMode(!MM.editMode); });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && MM.fullscreen) setFullscreen(false);
      });

      // Node selection + click delegation

      // A plain click REPLACES the selection (null clears it). Re-selecting the
      // same node is a no-op: a re-render would lose the caret in an editable
      // label.
      function selectNode(id) {
        var alreadyJustThis = id === MM.selectedNodeId && (
          (id === null && MM.multiSelectIds.size === 0) ||
          (id !== null && MM.multiSelectIds.size === 1 && MM.multiSelectIds.has(id))
        );
        if (alreadyJustThis) return;
        MM.selectedNodeId = id;
        MM.multiSelectIds = new Set(id ? [id] : []);
        var mmForFocus = activeMindmap();
        var nodeForFocus = mmForFocus && id ? mmForFocus.nodes.find(function (n) { return n.id === id; }) : null;
        var focusGoalType = nodeForFocus ? GOAL_TYPE_BY_COLOR[nodeForFocus.color] : null;
        var focusIsFreeText = (focusGoalType === 'manual' || !focusGoalType);
        MM.focusNodeId = (MM.editMode && id && focusIsFreeText) ? id : null;
        render();
      }

      // Shift-click toggles the node in the selection; the latest becomes the
      // anchor. A shared child only joins nodes at the same depth
      // (add_shared_child in app/mindmaps.py), so a mismatched node is silently
      // refused.
      function extendMultiSelect(id) {
        if (MM.multiSelectIds.has(id)) {
          MM.multiSelectIds.delete(id);
          if (MM.selectedNodeId === id) {
            var remaining = Array.from(MM.multiSelectIds);
            MM.selectedNodeId = remaining.length ? remaining[remaining.length - 1] : null;
          }
          MM.focusNodeId = null;
          render();
          return;
        }
        var layout = MM.lastLayout;
        if (layout && MM.selectedNodeId) {
          var anchorPos = layout.positions[MM.selectedNodeId];
          var newPos = layout.positions[id];
          if (anchorPos && newPos && anchorPos.depth !== newPos.depth) {
            return;
          }
        }
        MM.multiSelectIds.add(id);
        MM.selectedNodeId = id;
        MM.focusNodeId = null;
        render();
      }

      document.getElementById('mmNodesLayer').addEventListener('pointerdown', function (e) {
        var el = e.target.closest('.mm-node');
        if (!el) return;
        commitActiveLabelIfEditing();
        e.stopPropagation();
        // Edge buttons, the popover, the manual-complete checkbox and the
        // note-flip toggle work with or without Edit Mode; only a click on the
        // node body is gated on it.
        if (e.target.closest('.mm-edge-btn') || e.target.closest('[data-role="popover"]') || e.target.closest('[data-role="manual-toggle"]') || e.target.closest('[data-role="note-toggle"]')) return;
        if (!MM.editMode) { glowEditModeButton(); return; }
        if (e.shiftKey) { extendMultiSelect(el.getAttribute('data-node-id')); return; }
        selectNode(el.getAttribute('data-node-id'));
      });

      document.getElementById('mmNodesLayer').addEventListener('click', async function (e) {
        if (pendingLabelCommit) {
          await pendingLabelCommit;
          pendingLabelCommit = null;
        }
        var edgeBtn = e.target.closest('.mm-edge-btn');
        if (edgeBtn) {
          var nodeEl = edgeBtn.closest('.mm-node');
          addNodeRelativeTo(
            nodeEl.getAttribute('data-node-id'),
            edgeBtn.getAttribute('data-relation'),
            edgeBtn.getAttribute('data-before') === '1'
          );
          return;
        }
        var typeBtn = e.target.closest('.mm-type-btn');
        if (typeBtn) { updateSelectedNode({ color: typeBtn.getAttribute('data-color') }); return; }
        var segBtn = e.target.closest('.mm-segment-btn');
        if (segBtn) {
          var segGroup = segBtn.closest('[data-role="segment-group"]');
          if (!segGroup) return;
          segGroup.querySelectorAll('.mm-segment-btn').forEach(function (b) { b.classList.toggle('active', b === segBtn); });
          var segHidden = segGroup.nextElementSibling;
          if (segHidden && segHidden.matches('input[type="hidden"]')) segHidden.value = segBtn.getAttribute('data-segment-value');
          showGoalSaveError(null);
          if (segGroup.getAttribute('data-segment-field') === 'metric') {
            var fieldsWrapForMetric = segGroup.closest('[data-role="goal-fields"]');
            var targetForMetric = fieldsWrapForMetric && fieldsWrapForMetric.querySelector('[data-goal-field="target"]');
            if (targetForMetric) {
              var newMetric = segBtn.getAttribute('data-segment-value');
              var rawTargetForMetric = targetForMetric.value.trim();
              if (rawTargetForMetric !== '') {
                var nTargetForMetric = Number(parseMoneySuffix(rawTargetForMetric));
                if (Number.isInteger(nTargetForMetric)) {
                  targetForMetric.value = newMetric === 'xp'
                    ? xpForLevel(nTargetForMetric)
                    : levelForXp(nTargetForMetric);
                }
              }
              targetForMetric.placeholder = (newMetric === 'xp') ? 'Target experience' : 'Target level';
              validateSkillTarget(targetForMetric);
            }
          }
          return;
        }
        if (e.target.closest('[data-role="delete"]')) { deleteSelectedNode(); return; }
        if (e.target.closest('[data-role="add-shared-child"]')) { addSharedChildSelected(); return; }
        // Manual-complete checkbox on gray nodes: works in or out of Edit Mode;
        // reads the clicked node fresh so a quick double-click toggles
        // correctly.
        var toggleEl = e.target.closest('[data-role="manual-toggle"]');
        if (toggleEl) {
          var toggleNodeEl = toggleEl.closest('.mm-node');
          var toggleNodeId = toggleNodeEl && toggleNodeEl.getAttribute('data-node-id');
          var mmForToggle = activeMindmap();
          var toggleNode = mmForToggle && toggleNodeId
            ? mmForToggle.nodes.find(function (n) { return n.id === toggleNodeId; })
            : null;
          if (toggleNode) saveNodeGoal(toggleNodeId, { manualComplete: !(toggleNode.goal && toggleNode.goal.manualComplete) });
          return;
        }
        // Note-flip button: a local view toggle (MM.flippedNodeIds), no request.
        // Inert in Edit Mode (pointer-events: none in .mm-node-note-toggle);
        // this check is a backstop.
        var noteToggleEl = e.target.closest('[data-role="note-toggle"]');
        if (noteToggleEl) {
          if (MM.editMode) return;
          var noteToggleNodeEl = noteToggleEl.closest('.mm-node');
          var noteToggleNodeId = noteToggleNodeEl && noteToggleNodeEl.getAttribute('data-node-id');
          if (noteToggleNodeId) flipNodeNote(noteToggleNodeId);
          return;
        }
        if (e.target.closest('[data-role="goal-save"]')) {
          var popoverForSave = e.target.closest('[data-role="popover"]');
          var fieldsWrap = popoverForSave && popoverForSave.querySelector('[data-role="goal-fields"]');
          if (!fieldsWrap) return;
          var noteInputForSave = popoverForSave && popoverForSave.querySelector('[data-role="node-note-input"]');
          var noteValForSave = noteInputForSave ? noteInputForSave.value.trim() : '';
          var nodeForSave = selectedNode();
          if (nodeForSave && GOAL_TYPE_BY_COLOR[nodeForSave.color] === 'manual') {
            var textInput = fieldsWrap.querySelector('[data-role="node-text-input"]');
            var textVal = textInput ? textInput.value.trim() : '';
            if (!textVal) {
              if (textInput) textInput.classList.add('invalid');
              return;
            }
            var noteChangedForManual = noteValForSave !== (nodeForSave.note || '');
            if (textVal !== nodeForSave.text || noteChangedForManual) {
              saveSelectedNodeText(textVal, noteValForSave, true);
            } else {
              MM.selectedNodeId = null;
              MM.multiSelectIds = new Set();
              render();
            }
            return;
          }
          // sinceDate is the only masked date field here (like the Loot Tracker
          // custom range): as in applyCustomRange, refuse the save and flag it
          // red if digits are typed but not a real date; blank is fine.
          var sinceDateInput = fieldsWrap.querySelector('[data-goal-field="sinceDate"]');
          if (sinceDateInput) {
            var sinceDateVal = sinceDateInput.value.trim();
            if (sinceDateVal && !isValidIsoDate(sinceDateVal)) {
              sinceDateInput.classList.add('invalid');
              return;
            }
          }
          var typeForSave = GOAL_TYPE_BY_COLOR[nodeForSave.color];
          if (!validateGoalFieldsForSave(fieldsWrap, typeForSave)) return;
          var goal = {};
          fieldsWrap.querySelectorAll('[data-goal-field]').forEach(function (input) {
            var val = (input.value || '').trim();
            var field = input.getAttribute('data-goal-field');
            var isNumericTargetField = field === 'targetGp' || field === 'targetCount' || field === 'targetQty' || field === 'target';
            if (isNumericTargetField) val = parseMoneySuffix(val);
            if (val !== '') goal[field] = val;
          });
          saveSelectedNodeGoal(goal, noteValForSave, true);
        }
      });

      document.getElementById('mmNodesLayer').addEventListener('focusout', function (e) {
        var label = e.target.closest('[data-role="label"]');
        if (label) commitNodeTextFromLabel(label);
        // Close suggestions on blur after 150ms so a click on a suggestion can
        // read the box first, unless another field has since taken over the
        // shared box (activeSearchInput).
        var searchInput = e.target.closest('.mm-search-input');
        if (searchInput) {
          setTimeout(function () {
            if (activeSearchInput === searchInput) hideFloatingSuggestions();
          }, 150);
        }
      });
      // Debounced live search and live skill-target validation share one
      // delegated 'input' listener (a full render() would wipe other fields'
      // typing); timers are per input in a WeakMap.
      var searchDebounceTimers = new WeakMap();
      document.getElementById('mmNodesLayer').addEventListener('input', function (e) {
        if (e.target.closest('[data-role="goal-fields"]')) showGoalSaveError(null);
        var goalFieldInput = e.target.closest('[data-goal-field], [data-goal-field-target]');
        if (goalFieldInput) goalFieldInput.classList.remove('invalid');
        var searchInput = e.target.closest('.mm-search-input');
        if (searchInput) {
          clearTimeout(searchDebounceTimers.get(searchInput));
          searchDebounceTimers.set(searchInput, setTimeout(function () { runGoalSearch(searchInput); }, 200));
          return;
        }
        var numericField = e.target.closest(NUMERIC_SUFFIX_FIELDS_SELECTOR);
        if (numericField) filterNumericSuffixInput(numericField);
        var targetInput = e.target.closest('[data-goal-field="target"]');
        if (targetInput && targetInput.closest('.mm-goal-fields')) validateSkillTarget(targetInput);
        var sinceDateInput = e.target.closest('[data-goal-field="sinceDate"]');
        if (sinceDateInput) applyDateMask(sinceDateInput);
        var nodeTextInput = e.target.closest('[data-role="node-text-input"]');
        if (nodeTextInput) validateNodeText(nodeTextInput);
        var noteInput = e.target.closest('[data-role="node-note-input"]');
        if (noteInput) clampNoteInput(noteInput);
      });
      document.getElementById('mmNodesLayer').addEventListener('keydown', function (e) {
        var label = e.target.closest('[data-role="label"]');
        if (!label) return;
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); label.blur(); }
        else if (e.key === 'Escape') { e.preventDefault(); label.blur(); }
      });
      document.getElementById('mmNodesLayer').addEventListener('paste', function (e) {
        var label = e.target.closest('[data-role="label"]');
        if (!label) return;
        e.preventDefault();
        var text = (e.clipboardData || window.clipboardData).getData('text/plain');
        document.execCommand('insertText', false, text);
      });

      // Rendering

      function fmtNum(n) { return Number(n).toLocaleString('en-US'); }

      // Resolves K/M/B shorthand ("140k", "2.5m") in numeric goal targets to the
      // integer the server stores; commas are stripped first, anything else
      // passes through.
      function parseMoneySuffix(raw) {
        var s = (raw || '').trim().replace(/,/g, '');
        var m = /^([0-9]*\\.?[0-9]+)\\s*([kKmMbB])$/.exec(s);
        if (!m) return s;
        var mult = { k: 1e3, m: 1e6, b: 1e9 }[m[2].toLowerCase()];
        return String(Math.round(parseFloat(m[1]) * mult));
      }

      var NUMERIC_SUFFIX_FIELDS_SELECTOR =
        '[data-goal-field="targetCount"], [data-goal-field="targetQty"], ' +
        '[data-goal-field="targetGp"], [data-goal-field="target"]';

      // Restricts numeric-target fields to digits, commas, a decimal point and
      // k/m/b. They're type="text" inputmode="decimal" because a number input
      // can't take the shorthand.
      var NUMERIC_SUFFIX_DISALLOWED_RE = /[^0-9,.kKmMbB]/g;

      function filterNumericSuffixInput(input) {
        var cleaned = input.value.replace(NUMERIC_SUFFIX_DISALLOWED_RE, '');
        if (cleaned === input.value) return;
        var cursor = input.selectionStart;
        var keptBeforeCursor = input.value.slice(0, cursor).replace(NUMERIC_SUFFIX_DISALLOWED_RE, '').length;
        input.value = cleaned;
        input.setSelectionRange(keptBeforeCursor, keptBeforeCursor);
      }

      // sinceDate masks like the Loot Tracker custom range
      // (DATE_MASK/applyDateMask/isValidIsoDate in render_loot_tracker's script,
      // ported since page scripts are self-contained).
      var DATE_MASK = 'dddd-dd-dd';

      function digitsOnly(s) {
        return (s || '').replace(/\\D/g, '').slice(0, 8);
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

      function applyDateMask(input) {
        var digits = digitsOnly(input.value);
        input.value = digits.length ? maskValueFromDigits(digits) : '';
        var pos = 0, di = 0;
        for (var i = 0; i < DATE_MASK.length; i++) {
          if (DATE_MASK[i] === 'd' && di < digits.length) { pos = i + 1; di++; }
        }
        input.setSelectionRange(pos, pos);
        input.classList.remove('invalid');
      }

      function isValidIsoDate(s) {
        var m = /^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(s || '');
        if (!m) return false;
        var year = parseInt(m[1], 10), month = parseInt(m[2], 10), day = parseInt(m[3], 10);
        if (month < 1 || month > 12) return false;
        var daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
        return day >= 1 && day <= daysInMonth;
      }

      // Floating goal-search suggestions dropdown. A scrollable overflow:auto
      // region inside .mm-world gets its own GPU layer, which re-rasterizes
      // .mm-world and blurs the canvas while searching (`contain: paint` and
      // will-change did not help). So it is one shared `position: fixed` element
      // on <body>, placed from the focused input's getBoundingClientRect() and
      // re-synced from applyTransform.
      var floatingSuggestionsEl = null;
      var activeSearchInput = null;
      function getFloatingSuggestionsEl() {
        if (!floatingSuggestionsEl) {
          floatingSuggestionsEl = document.createElement('div');
          floatingSuggestionsEl.className = 'mm-suggestions';
          floatingSuggestionsEl.setAttribute('data-role', 'mm-suggestions');
          document.body.appendChild(floatingSuggestionsEl);
          floatingSuggestionsEl.addEventListener('click', function (e) {
            var suggestionEl = e.target.closest('.mm-suggestion');
            if (!suggestionEl || !activeSearchInput) return;
            var value = suggestionEl.getAttribute('data-value');
            var label = suggestionEl.getAttribute('data-label');
            activeSearchInput.value = (label != null) ? label : value;
            activeSearchInput.classList.remove('invalid');
            var hidden = hiddenTargetFor(activeSearchInput);
            if (hidden) hidden.value = value;
            hideFloatingSuggestions();
            showGoalSaveError(null);
          });
        }
        return floatingSuggestionsEl;
      }
      function positionFloatingSuggestions() {
        if (!activeSearchInput || !floatingSuggestionsEl || !floatingSuggestionsEl.classList.contains('show')) return;
        if (!document.body.contains(activeSearchInput)) { hideFloatingSuggestions(); return; }
        var rect = activeSearchInput.getBoundingClientRect();
        floatingSuggestionsEl.style.left = rect.left + 'px';
        floatingSuggestionsEl.style.top = (rect.bottom + 2) + 'px';
        floatingSuggestionsEl.style.width = rect.width + 'px';
      }
      function hideFloatingSuggestions() {
        if (!floatingSuggestionsEl) return;
        floatingSuggestionsEl.classList.remove('show');
        floatingSuggestionsEl.innerHTML = '';
        activeSearchInput = null;
      }

      function hiddenTargetFor(input) {
        var targetFieldName = input.getAttribute('data-goal-field-target');
        if (!targetFieldName) return null;
        var wrap = input.closest('.mm-search-wrap');
        return wrap && wrap.querySelector('[data-goal-field="' + targetFieldName + '"]');
      }

      async function runGoalSearch(input) {
        var query = input.value.trim();
        var hidden = hiddenTargetFor(input);
        if (!query) {
          if (hidden) hidden.value = '';
          if (activeSearchInput === input) hideFloatingSuggestions();
          return;
        }
        var kind = input.getAttribute('data-search-kind');
        var localPool = LOCAL_SEARCH_POOLS[kind];
        if (localPool) {
          if (!document.body.contains(input) || document.activeElement !== input) return;
          activeSearchInput = input;
          var q = query.toLowerCase();
          // Keep the hidden field in sync on every keystroke with what the text
          // resolves to exactly (or clear it), so a typed full name saves
          // without clicking a suggestion.
          if (hidden) {
            var exact = localPool.filter(function (item) { return item.label.toLowerCase() === q; })[0];
            hidden.value = exact ? exact.value : '';
          }
          var matches = localPool.filter(function (item) { return item.label.toLowerCase().indexOf(q) !== -1; });
          renderGoalSuggestions(getFloatingSuggestionsEl(), kind, matches);
          return;
        }
        var endpoint = GOAL_SEARCH_ENDPOINTS[kind];
        if (!endpoint) return;
        var data = await apiCall(endpoint + '?q=' + encodeURIComponent(query));
        // Bail if the popover or input is gone when the request resolves; the
        // activeElement check also stops a slow response clobbering the shared
        // box.
        if (!document.body.contains(input) || document.activeElement !== input) return;
        activeSearchInput = input;
        renderGoalSuggestions(getFloatingSuggestionsEl(), kind, data ? data.results : []);
      }

      function normalizeSearchResults(kind, raw) {
        if (kind === 'skill' || kind === 'diary') return raw;
        if (kind === 'item') return raw.map(function (r) { return { value: r.name, label: r.name, icon: r.icon }; });
        return raw.map(function (name) { return { value: name, label: name, icon: null }; });
      }

      // Render one search field's suggestion dropdown.
      function renderGoalSuggestions(box, kind, rawResults) {
        var results = normalizeSearchResults(kind, rawResults);
        if (!results.length) {
          var emptyLabel = kind === 'npc' ? 'No NPCs found' : kind === 'quest' ? 'No quests found' :
            kind === 'skill' ? 'No skills found' : kind === 'diary' ? 'No diaries found' : 'No items found';
          box.innerHTML = '<div class="mm-suggestion-empty">' + esc(emptyLabel) + '</div>';
        } else {
          box.innerHTML = results.map(function (r) {
            return '<div class="mm-suggestion" data-kind="' + esc(kind) + '" data-value="' + esc(r.value) + '" data-label="' + esc(r.label) + '">' +
              (r.icon ? '<img src="' + esc(r.icon) + '" alt="">' : '') +
              '<span>' + esc(r.label) + '</span></div>';
          }).join('');
        }
        box.classList.add('show');
        positionFloatingSuggestions();
      }

      // Live range check for the skill target, mirroring MIN/MAX_SKILL_LEVEL/XP
      // (the server re-validates). Invalid is a red border only;
      // showEmptyAsInvalid is off for live calls and on from
      // validateGoalFieldsForSave. Returns validity.
      function validateSkillTarget(input, showEmptyAsInvalid) {
        var fieldsWrap = input.closest('[data-role="goal-fields"]');
        var metricHidden = fieldsWrap && fieldsWrap.querySelector('[data-goal-field="metric"]');
        var metric = (metricHidden && metricHidden.value === 'xp') ? 'xp' : 'level';
        var raw = input.value.trim();
        if (raw === '') { input.classList.toggle('invalid', !!showEmptyAsInvalid); return false; }
        var n = Number(parseMoneySuffix(raw));
        var min = metric === 'xp' ? MIN_SKILL_XP : MIN_SKILL_LEVEL;
        var max = metric === 'xp' ? MAX_SKILL_XP : MAX_SKILL_LEVEL;
        var ok = Number.isInteger(n) && n >= min && n <= max;
        input.classList.toggle('invalid', !ok);
        return ok;
      }

      function validateNodeText(input) {
        if (input.value.trim() !== '') input.classList.remove('invalid');
      }

      var REQUIRED_GOAL_FIELDS = {
        kc: ['sourceName'],
        item: ['itemName'],
        gp: [],
        skill: ['skill'],
        quest: ['questName'],
        diary: ['area'],
      };
      var NUMERIC_TARGET_FIELD = {
        kc: { field: 'targetCount', min: 1, max: MAX_KC_TARGET },
        item: { field: 'targetQty', min: 1, max: MAX_ITEM_QTY_TARGET },
        gp: { field: 'targetGp', min: 1, max: MAX_GP_TARGET },
      };

      function visibleGoalFieldEl(fieldsWrap, name) {
        return fieldsWrap.querySelector('[data-goal-field-target="' + name + '"]') ||
          fieldsWrap.querySelector('[data-goal-field="' + name + '"]');
      }

      // Mirror of clean_goal's required+range checks, run before Save collects
      // fields: toggles .invalid per field instead of a server round trip;
      // showGoalSaveError is the fallback.
      function validateGoalFieldsForSave(fieldsWrap, type) {
        var ok = true;
        (REQUIRED_GOAL_FIELDS[type] || []).forEach(function (name) {
          var visible = visibleGoalFieldEl(fieldsWrap, name);
          var real = fieldsWrap.querySelector('[data-goal-field="' + name + '"]');
          var filled = real && real.value.trim() !== '';
          if (visible) visible.classList.toggle('invalid', !filled);
          if (!filled) ok = false;
        });
        var numericSpec = NUMERIC_TARGET_FIELD[type];
        if (numericSpec) {
          var input = fieldsWrap.querySelector('[data-goal-field="' + numericSpec.field + '"]');
          if (input) {
            var raw = input.value.trim();
            var n = Number(parseMoneySuffix(raw));
            var fieldOk = raw !== '' && Number.isInteger(n) && n >= numericSpec.min && n <= numericSpec.max;
            input.classList.toggle('invalid', !fieldOk);
            if (!fieldOk) ok = false;
          }
        }
        if (type === 'skill') {
          var targetInput = fieldsWrap.querySelector('[data-goal-field="target"]');
          if (targetInput && !validateSkillTarget(targetInput, true)) ok = false;
        }
        return ok;
      }

      // Shows (or with a falsy msg clears) a trackable node's error in its
      // popover, since the #mmError banner can be off-screen on a full-screen
      // canvas. No-op without a goal-save-error slot (manual).
      function showGoalSaveError(msg) {
        var errEl = document.querySelector('[data-role="popover"] [data-role="goal-save-error"]');
        if (!errEl) return;
        if (!msg) { errEl.textContent = ''; errEl.classList.remove('show'); return; }
        errEl.textContent = msg;
        errEl.classList.add('show');
      }

      // A trackable node's text is derived from its goal (clean_goal in
      // app/mindmaps.py): kc "<count> <activity> kc", item "x<qty> <item>", gp
      // "<amount> gp", skill "<xp> <skill> xp" or "lvl <level> <skill>", quest
      // "<quest name>", diary "<diary area> <tier>". Gray and white use
      // free-typed node.text.
      function goalDisplayText(node) {
        var type = GOAL_TYPE_BY_COLOR[node.color];
        var goal = node.goal || {};
        if (type === 'kc') {
          if (!goal.targetCount || !goal.sourceName) return 'Set KC goal';
          return fmtNum(goal.targetCount) + ' ' + goal.sourceName + ' kc';
        }
        if (type === 'item') {
          if (!goal.targetQty || !goal.itemName) return 'Set item goal';
          return 'x' + fmtNum(goal.targetQty) + ' ' + goal.itemName;
        }
        if (type === 'gp') {
          if (!goal.targetGp) return 'Set GP goal';
          return fmtNum(goal.targetGp) + ' gp';
        }
        if (type === 'skill') {
          if (!goal.skill || !goal.metric || !goal.target) return 'Set skill goal';
          var skillLabel = titleCase(goal.skill);
          return goal.metric === 'xp'
            ? fmtNum(goal.target) + ' ' + skillLabel + ' xp'
            : 'Lvl ' + goal.target + ' ' + skillLabel;
        }
        if (type === 'quest') {
          return goal.questName || 'Set quest goal';
        }
        if (type === 'diary') {
          if (!goal.area || !goal.tier) return 'Set diary goal';
          return DIARY_AREA_LABELS[goal.area] + ' ' + titleCase(goal.tier);
        }
        return node.text;
      }

      // Wraps an item goal's leading "x" in a span forced to lowercase (.mm-node
      // uppercases everything else).
      function renderNodeLabelHtml(goalType, text) {
        if (goalType === 'item') {
          var m = /^x(\\d.*)$/.exec(text);
          if (m) return '<span class="mm-node-x-lower">x</span>' + esc(m[1]);
        }
        return esc(text);
      }

      function renderCanvas(mm) {
        var layout = computeLayout(mm.nodes);
        MM.lastLayout = layout;

        var world = document.getElementById('mmWorld');
        // No width padding (a 250px popover overhangs a 160px node by 45px per
        // side, inside MARGIN's 60px). Height padding applies on every render,
        // since the closing render has already dropped the popover.
        world.style.width = layout.worldWidth + 'px';
        world.style.height = (layout.worldHeight + POPOVER_HEIGHT_PAD) + 'px';

        var nodesLayer = document.getElementById('mmNodesLayer');
        nodesLayer.classList.toggle('mm-view-mode', !MM.editMode);

        nodesLayer.innerHTML = mm.nodes.map(function (n) {
          var pos = layout.positions[n.id];
          // Selected nodes get the same brighten treatment, in Edit Mode only,
          // so non-editable nodes don't look pressed.
          var isSelected = MM.multiSelectIds.has(n.id);
          var isAnchor = n.id === MM.selectedNodeId;
          var isRoot = n.parentId === null;
          var selectedCls = (isSelected && MM.editMode) ? ' selected' : '';
          var completedCls = n.completed ? ' completed' : '';
          var goalType = GOAL_TYPE_BY_COLOR[n.color];
          var isFreeText = (goalType === 'manual' || !goalType);
          // Only the root (white, goalType null) is edited inline. A gray node
          // renames via a textbox in its popover (renderGoalFieldsHtml's
          // "manual" branch), so its label is never contenteditable and has no
          // data-role="label"; the post-render focus effect falls back to
          // [data-role="node-text-input"].
          var isInlineEditable = !goalType;
          var editableAttr = (MM.editMode && isInlineEditable && isSelected && MM.multiSelectIds.size === 1) ? ' contenteditable="true" spellcheck="false"' : '';
          var displayText = isFreeText ? n.text : goalDisplayText(n);
          var showManualCheckbox = goalType === 'manual' && !!(n.text && n.text.trim());
          var manualChecked = !!(n.goal && n.goal.manualComplete);
          var iconSrc = GOAL_TYPE_ICON_BY_COLOR[n.color];
          var hasLeftSlot = !!iconSrc || showManualCheckbox;
          var labelCls = 'mm-node-label' + (hasLeftSlot ? ' mm-node-label-with-icon' : '');
          // With a left slot, data-role="label"/editableAttr go on the inner
          // span, since a checkbox inside a contenteditable region would be
          // swept into select-all or mangled by editing.
          var labelInner;
          if (hasLeftSlot) {
            var leftSlotHtml = showManualCheckbox
              ? '<input type="checkbox" class="mm-node-checkbox" data-role="manual-toggle" title="Mark complete"' + (manualChecked ? ' checked' : '') + '>'
              : '<img class="mm-node-icon" src="' + iconSrc + '" alt="">';
            var innerLabelAttrs = isInlineEditable ? (' data-role="label"' + editableAttr) : '';
            labelInner = leftSlotHtml + '<span class="mm-node-label-text"' + innerLabelAttrs + '>' + renderNodeLabelHtml(goalType, displayText) + '</span>';
          } else {
            labelInner = esc(displayText);
          }
          // The root can't get a parent or sibling (the backend enforces it), so
          // only its "add child" edge button shows. Edge buttons are
          // Edit-Mode-only.
          var edgeButtonsHtml = !MM.editMode ? '' :
            (isRoot ? '' : '<button type="button" class="mm-edge-btn mm-edge-top" data-relation="parent">+</button>') +
            '<button type="button" class="mm-edge-btn mm-edge-bottom" data-relation="child">+</button>' +
            (isRoot ? '' : '<button type="button" class="mm-edge-btn mm-edge-left" data-relation="sibling" data-before="1">+</button>') +
            (isRoot ? '' : '<button type="button" class="mm-edge-btn mm-edge-right" data-relation="sibling" data-before="0">+</button>');
          // The anchor node's popover: the full editor for a sole selection
          // (renderNodePopoverHtml), or the "add shared child" button once a
          // second node is shift-added.
          var popoverHtml = '';
          if (isAnchor && MM.multiSelectIds.size === 1) popoverHtml = renderNodePopoverHtml(n);
          else if (isAnchor && MM.multiSelectIds.size >= 2) popoverHtml = renderSharedChildPopoverHtml();
          var labelAttrs = hasLeftSlot ? '' : (isInlineEditable ? (' data-role="label"' + editableAttr) : '');
          // Optional note flip (renderNoteFieldHtml): no note means no toggle or
          // back face. hasNote drops a stale MM.flippedNodeIds entry when a note
          // is cleared.
          var hasNote = !!(n.note && n.note.trim());
          if (!hasNote) MM.flippedNodeIds.delete(n.id);
          var isFlipped = hasNote && MM.flippedNodeIds.has(n.id);
          var noteToggleHtml = !hasNote ? '' :
            '<button type="button" class="mm-node-note-toggle" data-role="note-toggle">' +
            (isFlipped ? NOTE_ICON_ARROW_SVG : NOTE_ICON_PAPER_SVG) + '</button>';
          // The front face is wrapped in a face div so flipNodeNote has one
          // element (.mm-node-flip-inner) to animate; nodes without a note get
          // no wrapper.
          var faceHtml = hasNote
            ? '<div class="mm-node-flip-inner">' +
              (isFlipped
                ? '<div class="mm-node-face mm-node-face-back"><div class="mm-node-note-text">' + esc(n.note) + '</div></div>'
                : '<div class="mm-node-face mm-node-face-front"><div class="' + labelCls + '"' + labelAttrs + '>' + labelInner + '</div></div>') +
              '</div>'
            : '<div class="' + labelCls + '"' + labelAttrs + '>' + labelInner + '</div>';
          return '<div class="mm-node mm-node-' + esc(n.color) + selectedCls + completedCls + '" data-node-id="' + esc(n.id) + '" ' +
            'style="left:' + pos.x + 'px; top:' + pos.y + 'px;">' +
            faceHtml +
            noteToggleHtml +
            edgeButtonsHtml +
            popoverHtml +
            '</div>';
        }).join('');

        // A newly selected node (selectNode) is focused with its text selected
        // once the DOM lands. Deferred with setTimeout(..., 0) because render()
        // runs inside the pointerdown handler, and the browser's default focus
        // resolution afterwards would blur a not-yet-focusable node. Always
        // scheduled so ensurePopoverVisible checks every fresh popover.
        var focusIdForThisRender = MM.focusNodeId;
        MM.focusNodeId = null;
        setTimeout(function () {
          if (focusIdForThisRender) {
            var nodeEl = document.querySelector('.mm-node[data-node-id="' + focusIdForThisRender + '"]');
            if (nodeEl) {
              var label = nodeEl.querySelector('[data-role="label"]');
              if (label) {
                label.focus({ preventScroll: true });
                var range = document.createRange();
                range.selectNodeContents(label);
                var sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
              } else {
                var textInput = nodeEl.querySelector('[data-role="node-text-input"]');
                if (textInput) {
                  textInput.focus({ preventScroll: true });
                  textInput.select();
                }
              }
            }
          }
          ensurePopoverVisible();
          scrollCanvasPopoverIntoView();
        }, 0);

        var svg = document.getElementById('mmLines');
        svg.setAttribute('width', layout.worldWidth);
        svg.setAttribute('height', layout.worldHeight);
        var pathsHtml = '';
        layout.childrenMap.forEach(function (kids, parentId) {
          if (parentId === null || !kids.length) return; // the null bucket just holds the root itself, not a real edge
          var fanOutKids = kids.filter(function (k) { return !k.extraParentIds || !k.extraParentIds.length; });
          if (!fanOutKids.length) return;
          var parentPos = layout.positions[parentId];
          if (!parentPos) return;
          var parentCenterX = parentPos.x + NODE_WIDTH / 2;
          var parentBottomY = parentPos.y + NODE_HEIGHT;
          var childTopY = parentPos.y + ROW_HEIGHT;
          var busY = parentBottomY + (childTopY - parentBottomY) / 2;
          var childXs = fanOutKids.map(function (k) { return layout.positions[k.id].x + NODE_WIDTH / 2; });
          var minX = Math.min.apply(null, childXs), maxX = Math.max.apply(null, childXs);
          var d = 'M ' + parentCenterX + ' ' + parentBottomY + ' L ' + parentCenterX + ' ' + busY + ' ';
          if (fanOutKids.length > 1) d += 'M ' + minX + ' ' + busY + ' L ' + maxX + ' ' + busY + ' ';
          childXs.forEach(function (cx) { d += 'M ' + cx + ' ' + busY + ' L ' + cx + ' ' + childTopY + ' '; });
          pathsHtml += '<path d="' + d + '"></path>';
        });

        // Fan-in connectors for shared-child nodes (several parents converging
        // on one child); a separate pass since they have no single parentId.
        mm.nodes.forEach(function (n) {
          if (!n.extraParentIds || !n.extraParentIds.length) return;
          var childPos = layout.positions[n.id];
          if (!childPos) return;
          var linkedIds = [n.parentId].concat(n.extraParentIds).filter(function (pid) {
            return !!layout.positions[pid];
          });
          if (linkedIds.length < 2) return; // a linked parent got deleted and pruned down to <2 -- nothing shared to draw
          var childTopY = childPos.y;
          var childCenterX = childPos.x + NODE_WIDTH / 2;
          var parentBottomYs = linkedIds.map(function (pid) { return layout.positions[pid].y + NODE_HEIGHT; });
          var parentCenterXs = linkedIds.map(function (pid) { return layout.positions[pid].x + NODE_WIDTH / 2; });
          var maxParentBottomY = Math.max.apply(null, parentBottomYs);
          var busY = maxParentBottomY + (childTopY - maxParentBottomY) / 2;
          var minX = Math.min.apply(null, parentCenterXs), maxX = Math.max.apply(null, parentCenterXs);
          var d = '';
          parentCenterXs.forEach(function (px, i) { d += 'M ' + px + ' ' + parentBottomYs[i] + ' L ' + px + ' ' + busY + ' '; });
          d += 'M ' + minX + ' ' + busY + ' L ' + maxX + ' ' + busY + ' ';
          d += 'M ' + childCenterX + ' ' + busY + ' L ' + childCenterX + ' ' + childTopY + ' ';
          pathsHtml += '<path d="' + d + '"></path>';
        });

        svg.innerHTML = pathsHtml;
      }

      function renderMenu() {
        var rows = MM.data.mindmaps.map(function (m) {
          var activeCls = (m.id === MM.activeMindmapId) ? ' active' : '';
          return '<button type="button" class="mm-menu-item mm-menu-switch' + activeCls + '" data-mindmap-id="' +
            esc(m.id) + '">' + esc(m.name) + '</button>';
        }).join('');
        document.getElementById('mmMenu').innerHTML = rows +
          '<div class="mm-menu-divider"></div>' +
          '<button type="button" class="mm-menu-item" id="mmMenuNew">New mindmap</button>' +
          '<button type="button" class="mm-menu-item" id="mmMenuDuplicate">Duplicate mindmap</button>' +
          '<button type="button" class="mm-menu-item" id="mmMenuRename">Rename mindmap</button>' +
          '<button type="button" class="mm-menu-item danger" id="mmMenuDelete">Delete mindmap</button>';
      }

      // The selected node's popover: swatches, goal form and Save/Delete (Edit
      // Mode only). Shares its shell with renderSharedChildPopoverHtml;
      // renderCanvas shows one of the two. The root has nothing to show (always
      // white, can't be deleted), so bail before rendering an empty shell.
      function renderNodePopoverHtml(node) {
        if (node.parentId === null || !MM.editMode) return '';
        var goalType = GOAL_TYPE_BY_COLOR[node.color];
        var showSave = !!goalType;
        var actionsHtml = '<div class="mm-popover-actions" data-role="popover-actions">' +
          '<button type="button" class="btn-secondary mm-delete-btn mm-color-popover-delete" data-role="delete">Delete</button>' +
          (showSave ? '<button type="button" class="btn-secondary mm-goal-save-btn" data-role="goal-save">SAVE</button>' : '') +
          '</div>';
        // A trackable type's server-validated error
        // (saveNodeGoal/showGoalSaveError) lands here above Save/Delete, not in
        // the page banner.
        return '<div class="mm-node-popover mm-node-popover-wide" data-role="popover">' +
          renderGoalTypePickerHtml(node) +
          renderGoalFieldsHtml(node) +
          renderNoteFieldHtml(node) +
          '<div class="mm-field-error mm-goal-save-error" data-role="goal-save-error"></div>' +
          actionsHtml +
          '</div>';
      }

      // Note two-line cap. A scrollbar inside .mm-world re-triggers the
      // compositing blur (see getFloatingSuggestionsEl) and the textarea and
      // node back face can't move outside it, so notes are capped to 2 lines
      // (overflow: hidden as a backstop). The font is proportional, so the cap
      // measures a candidate value's rendered height in a hidden mirror matching
      // the back face (.mm-node-note-text: 9.5px, line-height 1.35, NODE_WIDTH
      // content width; keep in sync with mindmaps.css).
      var noteMeasureEl = null;
      function getNoteMeasureEl() {
        if (!noteMeasureEl) {
          noteMeasureEl = document.createElement('div');
          noteMeasureEl.style.position = 'fixed';
          noteMeasureEl.style.visibility = 'hidden';
          noteMeasureEl.style.pointerEvents = 'none';
          noteMeasureEl.style.top = '-9999px';
          noteMeasureEl.style.left = '-9999px';
          noteMeasureEl.style.boxSizing = 'border-box';
          noteMeasureEl.style.width = (NODE_WIDTH - 20) + 'px'; // NODE_WIDTH minus .mm-node-face's 10px+10px padding
          noteMeasureEl.style.fontFamily = 'RuneScapePlain11';
          noteMeasureEl.style.fontSize = '9.5px';
          noteMeasureEl.style.lineHeight = '1.35';
          noteMeasureEl.style.whiteSpace = 'pre-wrap';
          noteMeasureEl.style.wordBreak = 'break-word';
          document.body.appendChild(noteMeasureEl);
        }
        return noteMeasureEl;
      }
      var NOTE_MAX_LINES = 2;
      function clampNoteToLines(value) {
        if (!value) return value;
        var mirror = getNoteMeasureEl();
        mirror.textContent = 'M';
        var oneLine = mirror.getBoundingClientRect().height;
        var maxHeight = oneLine * NOTE_MAX_LINES + 1; // +1px slack for sub-pixel rounding
        mirror.textContent = value;
        if (mirror.getBoundingClientRect().height <= maxHeight) return value;
        var lo = 0, hi = value.length;
        while (lo < hi) {
          var mid = (lo + hi + 1) >> 1;
          mirror.textContent = value.slice(0, mid);
          if (mirror.getBoundingClientRect().height <= maxHeight) lo = mid; else hi = mid - 1;
        }
        return value.slice(0, lo);
      }
      // Called from the note textarea's 'input': clamps in place and, if a
      // character was cut, parks the caret at the end (imprecise for a mid-note
      // paste, accepted).
      function clampNoteInput(textarea) {
        var clamped = clampNoteToLines(textarea.value);
        if (clamped !== textarea.value) {
          textarea.value = clamped;
          textarea.setSelectionRange(clamped.length, clamped.length);
        }
      }

      // The optional note every non-root type gets, above Save/Delete. It is
      // saved by the same Save click on the request the node type already sends
      // (one undo step). A plain <textarea>, not resizable (2-line cap,
      // clampNoteInput); maxlength is a backstop matching MAX_NODE_NOTE_LENGTH.
      function renderNoteFieldHtml(node) {
        return '<div class="mm-note-wrap">' +
          '<textarea class="mm-goal-input mm-note-input" data-role="node-note-input" placeholder="Notes (optional)" maxlength="200" rows="2">' +
          esc(node.note || '') + '</textarea>' +
          '</div>';
      }

      // Goal-type picker (GOAL_TYPE_PICKER). Clicking one sets the node's
      // `color` (data-color), which resets its goal (update_node in
      // app/mindmaps.py). "White" is omitted: it is root-only (NODE_COLORS).
      function renderGoalTypePickerHtml(node) {
        var buttons = GOAL_TYPE_PICKER.map(function (opt) {
          var activeCls = (opt.color === node.color) ? ' active' : '';
          var inner = (opt.color === 'gray')
            ? '<span class="mm-type-btn-swatch mm-type-btn-swatch-manual"></span>'
            : '<img class="mm-type-btn-icon" src="' + opt.icon + '" alt="">';
          return '<button type="button" class="mm-type-btn' + activeCls + '" data-color="' + opt.color + '">' +
            inner + '<span class="mm-type-btn-label">' + opt.label + '</span></button>';
        }).join('');
        return '<div class="mm-type-picker">' + buttons + '</div>';
      }

      // A text input with a live search dropdown (KC NPC, ITEM, QUEST;
      // GOAL_SEARCH_ENDPOINTS/runGoalSearch). Typing a name without picking a
      // suggestion still saves.
      function renderSearchFieldHtml(fieldName, searchKind, placeholder, currentValue) {
        return '<div class="mm-search-wrap">' +
          '<input class="mm-goal-input mm-search-input" type="text" autocomplete="off" ' +
          'data-goal-field="' + fieldName + '" data-search-kind="' + searchKind + '" ' +
          'placeholder="' + esc(placeholder) + '" maxlength="80" value="' + esc(currentValue || '') + '">' +
          '</div>';
      }

      // Like renderSearchFieldHtml but backed by LOCAL_SEARCH_POOLS, for fields
      // whose saved value differs from the displayed one (skill key vs name,
      // diary slug vs "Kourend & Kebos"). The visible input's
      // data-goal-field-target points at a hidden companion holding the real
      // data-goal-field.
      function renderLocalSearchFieldHtml(fieldName, searchKind, placeholder, currentValue, labelFor) {
        var displayValue = currentValue ? labelFor(currentValue) : '';
        return '<div class="mm-search-wrap">' +
          '<input class="mm-goal-input mm-search-input" type="text" autocomplete="off" ' +
          'data-goal-field-target="' + fieldName + '" data-search-kind="' + searchKind + '" ' +
          'placeholder="' + esc(placeholder) + '" maxlength="80" value="' + esc(displayValue) + '">' +
          '<input type="hidden" data-goal-field="' + fieldName + '" value="' + esc(currentValue || '') + '">' +
          '</div>';
      }

      function renderSegmentedToggleHtml(fieldName, options, currentValue) {
        var value = options.some(function (o) { return o[0] === currentValue; }) ? currentValue : options[0][0];
        var buttons = options.map(function (o) {
          var activeCls = (o[0] === value) ? ' active' : '';
          return '<button type="button" class="mm-segment-btn' + activeCls + '" data-segment-value="' + o[0] + '">' + esc(o[1]) + '</button>';
        }).join('');
        return '<div class="mm-segment-group" data-role="segment-group" data-segment-field="' + fieldName + '">' + buttons + '</div>' +
          '<input type="hidden" data-goal-field="' + fieldName + '" value="' + esc(value) + '">';
      }

      // The current color's goal fields, prefilled from the node's `goal`
      // (clean_goal/ default_goal in app/mindmaps.py). Only runs in Edit Mode,
      // never for the root; Save reads fields fresh off the DOM. "gray"/manual
      // has no goal criteria but gets a textbox for the node's NAME, saved via
      // PATCH .../nodes/<id> rather than .../goal (saveSelectedNodeText).
      function renderGoalFieldsHtml(node) {
        var goal = node.goal || {};
        var type = GOAL_TYPE_BY_COLOR[node.color];
        if (!type) return '';
        if (type === 'manual') {
          return '<div class="mm-goal-fields" data-role="goal-fields">' +
            '<div class="mm-goal-target-wrap">' +
              '<input class="mm-goal-input" type="text" data-role="node-text-input" placeholder="Type something" maxlength="120" value="' + esc(node.text || '') + '">' +
            '</div>' +
            '</div>';
        }
        var fields = '';
        if (type === 'kc') {
          fields =
            renderSearchFieldHtml('sourceName', 'npc', 'Search for an NPC', goal.sourceName) +
            '<input type="hidden" data-goal-field="activityType" value="npc">' +
            '<input class="mm-goal-input" type="text" inputmode="decimal" data-goal-field="targetCount" placeholder="Target kc" value="' + esc(goal.targetCount != null ? goal.targetCount : '') + '">' +
            // Optional: counts kc only from this date on; not shown on the node
            // face (see clean_goal). A masked YYYY-MM-DD field like the Loot
            // Tracker custom range, with a hint line since the placeholder
            // vanishes once typed.
            '<div class="mm-goal-date-wrap">' +
              '<input class="mm-goal-input" type="text" data-goal-field="sinceDate" inputmode="numeric" autocomplete="off" spellcheck="false" placeholder="YYYY-MM-DD" value="' + esc(goal.sinceDate || '') + '">' +
              '<div class="mm-goal-hint">Only count kc from this date on (optional)</div>' +
            '</div>';
        } else if (type === 'item') {
          fields =
            renderSearchFieldHtml('itemName', 'item', 'Search for an item', goal.itemName) +
            '<input class="mm-goal-input" type="text" inputmode="decimal" data-goal-field="targetQty" placeholder="Target quantity" value="' + esc(goal.targetQty != null ? goal.targetQty : '') + '">';
        } else if (type === 'gp') {
          fields =
            '<input class="mm-goal-input" type="text" inputmode="decimal" data-goal-field="targetGp" placeholder="Target gp (coins + tokens)" value="' + esc(goal.targetGp != null ? goal.targetGp : '') + '">';
        } else if (type === 'skill') {
          var metric = goal.metric === 'xp' ? 'xp' : 'level';
          var targetPlaceholder = metric === 'xp' ? 'Target experience' : 'Target level';
          fields =
            '<div class="mm-goal-skill-row">' +
              renderLocalSearchFieldHtml('skill', 'skill', 'Search for a skill', goal.skill, titleCase) +
              renderSegmentedToggleHtml('metric', [['level', 'LVL'], ['xp', 'XP']], goal.metric) +
            '</div>' +
            '<div class="mm-goal-target-wrap">' +
              '<input class="mm-goal-input" type="text" inputmode="decimal" data-goal-field="target" placeholder="' + esc(targetPlaceholder) + '" value="' + esc(goal.target != null ? goal.target : '') + '">' +
            '</div>';
        } else if (type === 'quest') {
          fields = renderSearchFieldHtml('questName', 'quest', 'Search for a quest or miniquest', goal.questName);
        } else if (type === 'diary') {
          fields =
            renderLocalSearchFieldHtml('area', 'diary', 'Search for a diary', goal.area, function (a) { return DIARY_AREA_LABELS[a] || a; }) +
            renderSegmentedToggleHtml('tier', DIARY_TIERS.map(function (t) { return [t, titleCase(t)]; }), goal.tier);
        }
        return '<div class="mm-goal-fields" data-role="goal-fields">' + fields + '</div>';
      }

      function renderSharedChildPopoverHtml() {
        return '<div class="mm-node-popover" data-role="popover">' +
          '<button type="button" class="btn-secondary mm-add-shared-child-btn" data-role="add-shared-child">Add shared child</button>' +
          '</div>';
      }

      function render() {
        hideFloatingSuggestions();
        updateHistoryButtons();
        updateEditModeButton();
        var wrapEl = document.getElementById('mmEmptyWrap');
        var msgEl = document.getElementById('mmEmptyMsg');
        var createBtn = document.getElementById('mmCreateFirstBtn');
        var bodyEl = document.getElementById('mmBody');

        if (!MM.data) {
          wrapEl.style.display = '';
          msgEl.textContent = 'Loading…';
          createBtn.style.display = 'none';
          bodyEl.style.display = 'none';
          return;
        }
        if (!MM.data.mindmaps.length) {
          wrapEl.style.display = '';
          msgEl.textContent = '';
          createBtn.style.display = '';
          bodyEl.style.display = 'none';
          return;
        }
        wrapEl.style.display = 'none';
        bodyEl.style.display = '';

        var mm = activeMindmap();
        document.getElementById('mmSwitchName').textContent = mm ? mm.name : '';
        renderMenu();
        pruneMultiSelect(mm);
        if (mm) renderCanvas(mm);
      }

      function pruneMultiSelect(mm) {
        if (!mm) { MM.multiSelectIds.clear(); MM.selectedNodeId = null; return; }
        var validIds = new Set(mm.nodes.map(function (n) { return n.id; }));
        MM.multiSelectIds.forEach(function (id) {
          if (!validIds.has(id)) MM.multiSelectIds.delete(id);
        });
        if (MM.selectedNodeId && !MM.multiSelectIds.has(MM.selectedNodeId)) {
          var remaining = Array.from(MM.multiSelectIds);
          MM.selectedNodeId = remaining.length ? remaining[remaining.length - 1] : null;
        }
      }

      // Mindmap switcher menu

      function closeMenu() {
        document.getElementById('mmMenu').style.display = 'none';
        var deleteBtn = document.getElementById('mmMenuDelete');
        if (deleteBtn) {
          deleteBtn.classList.remove('mm-menu-item--confirm');
          deleteBtn.textContent = 'Delete mindmap';
        }
      }
      document.getElementById('mmSwitchBtn').addEventListener('click', function () {
        commitActiveLabelIfEditing();
        var menu = document.getElementById('mmMenu');
        if (menu.style.display === 'none') { menu.style.display = 'flex'; } else { closeMenu(); }
      });
      document.addEventListener('click', function (e) {
        var wrap = document.querySelector('.mm-menu-wrap');
        if (wrap && !wrap.contains(e.target)) closeMenu();
      });

      document.getElementById('mmMenu').addEventListener('click', function (e) {
        commitActiveLabelIfEditing();
        var switchBtn = e.target.closest('.mm-menu-switch');
        if (switchBtn) {
          closeMenu();
          var id = switchBtn.getAttribute('data-mindmap-id');
          if (id !== MM.activeMindmapId) {
            setActiveMindmapId(id);
            MM.selectedNodeId = null;
            render();
            zoomToFit();
          }
          return;
        }
        if (e.target.id === 'mmMenuNew') { closeMenu(); openNameForm('new', ''); return; }
        if (e.target.id === 'mmMenuDuplicate') {
          closeMenu();
          duplicateActiveMindmap();
          return;
        }
        if (e.target.id === 'mmMenuRename') {
          closeMenu();
          var mm = activeMindmap();
          if (mm) openNameForm('rename', mm.name);
          return;
        }
        if (e.target.id === 'mmMenuDelete') {
          if (e.target.classList.contains('mm-menu-item--confirm')) {
            closeMenu();
            deleteActiveMindmap();
            return;
          }
          e.target.classList.add('mm-menu-item--confirm');
          e.target.textContent = 'Are you sure?';
          return;
        }
      });

      async function duplicateActiveMindmap() {
        var mm = activeMindmap();
        if (!mm) return;
        const data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id) + '/duplicate', { method: 'POST' });
        if (data) {
          MM.data = data;
          if (data.newMindmapId) {
            setActiveMindmapId(data.newMindmapId);
            MM.selectedNodeId = null;
          }
          render();
          zoomToFit();
        }
      }

      async function deleteActiveMindmap() {
        var mm = activeMindmap();
        if (!mm) return;
        const data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id), { method: 'DELETE' });
        if (data) {
          MM.data = data;
          MM.selectedNodeId = null;
          setActiveMindmapId(data.mindmaps.length ? data.mindmaps[0].id : null);
          render();
          zoomToFit();
        }
      }

      // New/rename mindmap form

      function openNameForm(mode, initialValue) {
        MM.nameFormMode = mode;
        var form = document.getElementById('mmNameForm');
        var input = document.getElementById('mmNameInput');
        form.style.display = 'flex';
        input.value = initialValue || '';
        input.classList.remove('invalid');
        input.focus();
      }
      document.getElementById('mmCreateFirstBtn').addEventListener('click', function () { openNameForm('new', ''); });
      document.getElementById('mmNameInput').addEventListener('input', function () {
        this.classList.remove('invalid');
      });
      document.getElementById('mmNameCancel').addEventListener('click', function () {
        document.getElementById('mmNameForm').style.display = 'none';
        document.getElementById('mmNameInput').classList.remove('invalid');
        MM.nameFormMode = null;
      });
      document.getElementById('mmNameSave').addEventListener('click', async function () {
        var nameInput = document.getElementById('mmNameInput');
        var name = (nameInput.value || '').trim();
        if (!name) { nameInput.classList.add('invalid'); return; }
        nameInput.classList.remove('invalid');
        var mode = MM.nameFormMode;
        document.getElementById('mmNameForm').style.display = 'none';
        MM.nameFormMode = null;
        var data;
        if (mode === 'new') {
          data = await apiCall('/api/mindmaps', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name }),
          });
          if (data) {
            MM.data = data;
            var created = data.mindmaps.find(function (m) { return m.name === name; }) || data.mindmaps[data.mindmaps.length - 1];
            if (created) {
              setActiveMindmapId(created.id);
              MM.selectedNodeId = null;
              render();
              zoomToFit();
            }
          }
        } else if (mode === 'rename') {
          var mm = activeMindmap();
          if (!mm) return;
          data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id), {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name }),
          });
          // Renamed the active mindmap; see resetMindmapShareState.
          if (data) { MM.data = data; resetMindmapShareState(); render(); }
        }
      });

      // Undo/redo. Each node-tree edit records the tree from just before it into
      // MM.undoStack once it succeeds, so undo swaps in a whole snapshot with no
      // per-action inverse (and deletes need no confirm).
      var MAX_HISTORY = 50;

      function updateHistoryButtons() {
        var undoBtn = document.getElementById('mmUndoBtn');
        var redoBtn = document.getElementById('mmRedoBtn');
        if (undoBtn) undoBtn.disabled = !MM.undoStack.length;
        if (redoBtn) redoBtn.disabled = !MM.redoStack.length;
      }

      function updateZoomButtons() {
        var zoomInBtn = document.getElementById('mmZoomIn');
        var zoomOutBtn = document.getElementById('mmZoomOut');
        if (zoomInBtn) zoomInBtn.disabled = MM.zoom >= MAX_ZOOM;
        if (zoomOutBtn) zoomOutBtn.disabled = MM.zoom <= MIN_ZOOM;
      }

      function updateEditModeButton() {
        var btn = document.getElementById('mmEditModeBtn');
        if (!btn) return;
        btn.classList.toggle('active', MM.editMode);
        btn.setAttribute('data-tooltip', MM.editMode ? 'Exit edit mode' : 'Enter edit mode');
      }

      // Pulses the Edit Mode button when a node body is clicked outside Edit
      // Mode. mm-glow is a fixed-iteration CSS animation; removing the class and
      // forcing a reflow restarts it.
      function glowEditModeButton() {
        var btn = document.getElementById('mmEditModeBtn');
        if (!btn) return;
        btn.classList.remove('mm-glow');
        void btn.offsetWidth;
        btn.classList.add('mm-glow');
      }

      function flipNodeNote(nodeId) {
        if (MM.flippedNodeIds.has(nodeId)) MM.flippedNodeIds.delete(nodeId);
        else MM.flippedNodeIds.add(nodeId);
        render();
      }

      function recordUndoableEdit(preNodes) {
        MM.undoStack.push(preNodes);
        if (MM.undoStack.length > MAX_HISTORY) MM.undoStack.shift();
        // A fresh edit discards the redo stack, like any undo history.
        MM.redoStack = [];
      }

      // True if the mindmap an in-flight edit was made against is still on
      // screen, so a slow response never touches another mindmap's history or
      // tree.
      function isStillActiveMindmap(mmId) {
        return MM.activeMindmapId === mmId;
      }

      async function restoreNodesSnapshot(nodes) {
        var mm = activeMindmap();
        if (!mm) return null;
        return apiCall('/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nodes: nodes }),
        });
      }

      async function undo() {
        var mm = activeMindmap();
        if (!MM.undoStack.length || !mm) return;
        var mmId = mm.id;
        var prev = MM.undoStack[MM.undoStack.length - 1];
        var preUndoNodes = mm.nodes;
        const data = await restoreNodesSnapshot(prev);
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) {
          MM.undoStack.pop();
          MM.redoStack.push(preUndoNodes);
          MM.selectedNodeId = null;
          resetMindmapShareState();
        }
        render();
      }

      async function redo() {
        var mm = activeMindmap();
        if (!MM.redoStack.length || !mm) return;
        var mmId = mm.id;
        var next = MM.redoStack[MM.redoStack.length - 1];
        var preRedoNodes = mm.nodes;
        const data = await restoreNodesSnapshot(next);
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) {
          MM.redoStack.pop();
          MM.undoStack.push(preRedoNodes);
          MM.selectedNodeId = null;
          resetMindmapShareState();
        }
        render();
      }

      // Selected-node actions

      async function updateSelectedNode(patch) {
        var mm = activeMindmap();
        var node = selectedNode();
        if (!mm || !node) return;
        var mmId = mm.id;
        var preNodes = mm.nodes;
        const data = await apiCall(
          '/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/' + encodeURIComponent(node.id),
          { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) }
        );
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) { recordUndoableEdit(preNodes); resetMindmapShareState(); }
        render();
      }

      // Replaces the selected node's goal (set_node_goal in app/mindmaps.py) via
      // PATCH .../goal, for the trackable Save button and the gray
      // manual-complete toggle. `closePopover` (Save only) deselects the node on
      // success. Takes an explicit `nodeId` because the checkbox works on any
      // gray node. `note` rides on the same request for one undo step; the
      // checkbox leaves it undefined (JSON.stringify drops the key), so ticking
      // never touches the note.
      async function saveNodeGoal(nodeId, goal, note, closePopover) {
        var mm = activeMindmap();
        var node = mm && mm.nodes.find(function (n) { return n.id === nodeId; });
        if (!mm || !node) return;
        var mmId = mm.id;
        var preNodes = mm.nodes;
        // Not the shared apiCall helper, which sends failures to the top banner.
        // A 400 here is clean_goal's "missing field" message, which belongs in
        // the popover; other failures keep the banner.
        var res, data;
        try {
          res = await fetch(
            '/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/' + encodeURIComponent(node.id) + '/goal',
            { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ goal: goal, note: note }) }
          );
          data = await res.json().catch(function () { return {}; });
        } catch (err) {
          showError('Something went wrong. Please try again.');
          return;
        }
        if (!res.ok) {
          showGoalSaveError(describeError(data, 'Something went wrong. Please try again.'));
          return;
        }
        showGoalSaveError(null);
        showError(null);
        MM.data = data;
        if (isStillActiveMindmap(mmId)) { recordUndoableEdit(preNodes); resetMindmapShareState(); }
        if (closePopover) {
          MM.selectedNodeId = null;
          MM.multiSelectIds = new Set();
        }
        render();
      }
      function saveSelectedNodeGoal(goal, note, closePopover) {
        if (!MM.selectedNodeId) return;
        return saveNodeGoal(MM.selectedNodeId, goal, note, closePopover);
      }

      // A gray (manual) node's Save commits its NAME via the plain node PATCH
      // (updateSelectedNode), not .../goal (update_node vs set_node_goal);
      // `note` goes with the text.
      async function saveSelectedNodeText(text, note, closePopover) {
        var mm = activeMindmap();
        var node = selectedNode();
        if (!mm || !node) return;
        var mmId = mm.id;
        var preNodes = mm.nodes;
        const data = await apiCall(
          '/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/' + encodeURIComponent(node.id),
          { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text, note: note }) }
        );
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) { recordUndoableEdit(preNodes); resetMindmapShareState(); }
        if (closePopover) {
          MM.selectedNodeId = null;
          MM.multiSelectIds = new Set();
        }
        render();
      }

      function commitNodeTextFromLabel(label) {
        pendingLabelCommit = null;
        var node = selectedNode();
        if (!node) return;
        var val = (label.textContent || '').trim();
        if (!val || val === node.text) { label.textContent = node.text; return; }
        pendingLabelCommit = updateSelectedNode({ text: val });
      }

      // Adds a node relative to `nodeId`, which need not be the selected one
      // (edge-hover "+" buttons). `before` only matters for "sibling"
      // (_order_before/_order_after in app/mindmaps.py).
      async function addNodeRelativeTo(nodeId, relation, before) {
        var mm = activeMindmap();
        if (!mm) return;
        var mmId = mm.id;
        var preNodes = mm.nodes;
        var body = { relative_to: nodeId, relation: relation, text: '', color: 'gray' };
        if (relation === 'sibling') body.before = !!before;
        const data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        });
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) {
          recordUndoableEdit(preNodes);
          resetMindmapShareState();
          selectNode(data.newNodeId || null);
        } else {
          render();
        }
      }

      async function deleteSelectedNode() {
        var mm = activeMindmap();
        var node = selectedNode();
        if (!mm || !node || node.parentId === null) return;
        var mmId = mm.id;
        var preNodes = mm.nodes;
        const data = await apiCall(
          '/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/' + encodeURIComponent(node.id),
          { method: 'DELETE' }
        );
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) {
          recordUndoableEdit(preNodes);
          MM.selectedNodeId = null;
          resetMindmapShareState();
        }
        render();
      }

      // Multi-select: add a shared child below several nodes

      // Adds one node as a shared CHILD of every node in MM.multiSelectIds, e.g.
      // several "blocklist" nodes feeding one "setup" node. The nodes needn't
      // share a parent or depth (add_shared_child in app/mindmaps.py); the
      // button only shows with 2+ selected.
      async function addSharedChildSelected() {
        var mm = activeMindmap();
        if (!mm || MM.multiSelectIds.size < 2) return;
        var mmId = mm.id;
        var preNodes = mm.nodes;
        const data = await apiCall('/api/mindmaps/' + encodeURIComponent(mm.id) + '/nodes/shared-child', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          // Empty text, as in addNodeRelativeTo.
          body: JSON.stringify({ parent_ids: Array.from(MM.multiSelectIds), text: '', color: 'gray' }),
        });
        if (!data) return;
        MM.data = data;
        if (isStillActiveMindmap(mmId)) {
          recordUndoableEdit(preNodes);
          resetMindmapShareState();
          selectNode(data.newNodeId || null);
        } else {
          render();
        }
      }

      // Share (export a frozen myscape.io/s/<code> link)

      // Export icon next to the title: a popup under the button
      // (.mm-share-wrap). Nothing is generated until GENERATE SHAREABLE LINK is
      // clicked. Null-guarded because render_mindmap_share strips this icon's
      // <h2>.
      var mmShareIconBtn = document.getElementById('mmShareIconBtn');
      var mmShareCard = document.getElementById('mmShareCard');
      if (mmShareIconBtn) {
        function setMmShareOpen(open) {
          mmShareCard.hidden = !open;
          mmShareIconBtn.classList.toggle('open', open);
        }
        mmShareIconBtn.addEventListener('click', function () {
          setMmShareOpen(mmShareCard.hidden);
        });
        document.addEventListener('click', function (e) {
          var wrap = document.querySelector('.mm-share-wrap');
          if (wrap && !wrap.contains(e.target)) setMmShareOpen(false);
        });
      }

      // Resets the share card when the active mindmap changes and after every
      // edit to it: build_mindmap_share_snapshot (app/mindmaps.py) freezes the
      // whole mindmap, so an edit makes an old link stale.
      function resetMindmapShareState() {
        var genBtn = document.getElementById('mmShareGenerateBtn');
        var linkBtn = document.getElementById('mmShareLinkBtn');
        if (!genBtn || !linkBtn) return;
        genBtn.hidden = false;
        genBtn.disabled = false;
        genBtn.classList.remove('action-failed');
        linkBtn.hidden = true;
        linkBtn.textContent = '';
        delete linkBtn.dataset.url;
      }

      // GENERATE SHAREABLE LINK: freezes the active mindmap into a new
      // SharedContent row, then shows mmShareLinkBtn with the link.
      // Null-guarded: an unguarded addEventListener would throw and halt this
      // IIFE before loadState(), leaving the share page on "Loading...".
      var mmShareGenerateBtn = document.getElementById('mmShareGenerateBtn');
      if (mmShareGenerateBtn) {
        mmShareGenerateBtn.addEventListener('click', function () {
          var btn = this;
          if (!MM.activeMindmapId) return;
          btn.disabled = true;
          fetch('/api/mindmaps/' + encodeURIComponent(MM.activeMindmapId) + '/share', { method: 'POST' })
            .then(function (res) { return res.ok ? res.json() : Promise.reject(); })
            .then(function (data) {
              var linkBtn = document.getElementById('mmShareLinkBtn');
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

      var mmShareLinkBtn = document.getElementById('mmShareLinkBtn');
      if (mmShareLinkBtn) {
        mmShareLinkBtn.addEventListener('click', function () {
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

      // Boot

      async function loadState() {
        const data = await apiCall('/api/mindmaps');
        if (!data) return;
        MM.data = data;
        if (!MM.activeMindmapId || !data.mindmaps.some(function (m) { return m.id === MM.activeMindmapId; })) {
          var stored = loadStoredActiveMindmapId();
          var resolved = (stored && data.mindmaps.some(function (m) { return m.id === stored; }))
            ? stored
            : (data.mindmaps.length ? data.mindmaps[0].id : null);
          setActiveMindmapId(resolved);
        }
        render();
        zoomToFit();
      }

      loadState();
    })();
    """
    return extra_head, body, script


def render_mindmaps(player: PlayerView) -> str:
    """The Mindmaps page: _mindmaps_panel_markup's markup/script inside the
    _shell wrapper. render_landing_mindmap_preview embeds the same panel
    without _shell.
    """
    extra_head, body, script = _mindmaps_panel_markup()
    return _shell(
        title="Mindmaps — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )


def render_mindmap_share(share: "SharedContent", game_account: Optional["GameAccount"], viewer: Optional[PlayerView]) -> str:
    """GET /s/<code> for a Mindmap share: a read-only, frozen snapshot of the
    mindmap the owner picked (build_mindmap_share_snapshot in
    app/mindmaps.py).
    
    Reuses _mindmaps_panel_markup's body/script unmodified, with a fetch shim
    answering GET /api/mindmaps from PAYLOAD and localStorage shadowed
    (/s/<code> shares an origin with the real page). The switcher, Undo/Redo
    and Edit Mode toggle are hidden via CSS (.mindmap-share in mindmaps.css),
    not stripped, so no null guards are needed.
    
    The reused "Mindmaps" <h2> is stripped; banner_markup adds the mindmap
    name and "Shared by <name>" with an import icon. game_account may be None;
    falls back to "A player".
    """
    extra_head, body, script = _mindmaps_panel_markup()
    # Strip the reused body's "Mindmaps" <h2 class="page-title"> and its export
    # button by keeping only what follows the first "</h2>".
    _, _, body = body.partition("</h2>")

    owner_name = (game_account.runescape_name if game_account else None) or "A player"
    mindmap_name = share.payload["mindmap"]["name"]

    # Import icon next to "Shared by <name>"; same signed-in/signed-out split as
    # import_icon_btn in render_purchase_goals_share.
    import_icon_svg = (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
        '<polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line>'
        '</svg>'
    )
    if viewer is not None:
        import_icon_btn = (
            ' <span class="mm-import-wrap">'
            '<button type="button" class="mm-import-icon-btn" id="mmImportBtn" aria-label="Save to your account" title="Save to your account">'
            f'{import_icon_svg}</button>'
            '<div class="mm-import-card" id="mmImportCard" hidden>'
            '<button type="button" class="mm-import-save-btn" id="mmImportSaveBtn">SAVE TO MY MYSCAPE</button>'
            '<p class="mm-import-popup-hint">Clicking the button above will save a copy<br>of this mindmap to your Mindmaps app.</p>'
            '</div>'
            '</span>'
        )
    else:
        import_icon_btn = (
            ' <a class="mm-import-icon-btn" href="/signup" aria-label="Sign up to save this" title="Sign up to save this">'
            f'{import_icon_svg}</a>'
        )

    banner_markup = f"""
    <p class="subtitle mm-share-label">{escape(mindmap_name)}</p>
    <h2 class="page-title">Shared by {escape(owner_name)}{import_icon_btn}</h2>
    """
    body = banner_markup + body
    body = f'<div class="mindmap-share">{body}</div>'

    payload_json = json.dumps(share.payload)
    wrapper_script = f"""
    (function () {{
      var PAYLOAD = {payload_json};

      // Same-origin localStorage shadow (see the doc comment above); the
      // visitor's own preferences must not be read or overwritten.
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

        if (path === '/api/mindmaps' && method === 'GET') {{
          return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve({{ mindmaps: [PAYLOAD.mindmap] }}); }} }});
        }}
        // Every node- and mindmap-mutation endpoint gets a graceful ok:false
        // instead of reaching the real API with the visitor's session cookie.
        // ok:false (not an empty-object success, as in Loot Tracker) is the only
        // safe catch-all here: the reused script assigns MM.data from any
        // successful response and then reads its 'mindmaps' array, so an empty
        // object would crash. Nothing should reach this in practice (Edit Mode
        // never turns on; the gray-node checkbox is locked via pointer-events:
        // none in mindmaps.css).
        return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{ detail: 'Not available on a shared link.' }}); }} }});
      }};

      {script}

      // The switcher, Undo, Redo and Edit Mode are hidden via CSS only
      // (.mindmap-share in mindmaps.css), so nothing here needs to strip them.

      // Import icon: a real <button> only when the viewer was signed in at
      // render time (null-guarded otherwise; signed out it is a plain link to
      // /signup). Toggles mmImportCard like mmShareIconBtn/mmShareCard; nothing
      // imports until mmImportSaveBtn is clicked.
      var mmImportBtn = document.getElementById('mmImportBtn');
      var mmImportCard = document.getElementById('mmImportCard');
      if (mmImportBtn) {{
        function setMmImportOpen(open) {{
          mmImportCard.hidden = !open;
          mmImportBtn.classList.toggle('open', open);
        }}
        mmImportBtn.addEventListener('click', function () {{
          setMmImportOpen(mmImportCard.hidden);
        }});
        document.addEventListener('click', function (e) {{
          var wrap = document.querySelector('.mm-import-wrap');
          if (wrap && !wrap.contains(e.target)) setMmImportOpen(false);
        }});
      }}

      // SAVE TO MY MYSCAPE -- imports THIS share's own frozen mindmap
      // into the signed-in visitor's own Mindmaps list (POST /api/
      // mindmaps/shares/{share.code}/import in app/main.py), then --
      // only once that succeeds -- navigates there so they land right
      // on it, appended at the end of their own mindmap list AND
      // already selected (see below). A failed import (expired link,
      // or this specific race: the code was still valid when the page
      // loaded but lapses before the click) leaves this card open
      // exactly as-is and flashes this button red for 2.5s, same
      // pattern as mmShareGenerateBtn's own .action-failed handling
      // above.
      //
      // IMPORTANT: this calls window.fetch/window.localStorage
      // explicitly, not the bare fetch(...)/localStorage every other
      // handler in this wrapper script uses -- the plain identifiers
      // would resolve to THIS SAME IIFE's own local shim/shadow above
      // (harmless by design against the reused panel script, see this
      // function's own doc comment), which would mean this handler's
      // own fetch call never actually reaches the real server at all,
      // and writing the newly imported mindmap's id to the SHADOWED
      // localStorage would set a key nothing outside this one page
      // load ever reads -- same bug/fix Purchase Goals' own
      // pgImportSaveBtn handler already documents for its identical
      // choice.
      var mmImportSaveBtn = document.getElementById('mmImportSaveBtn');
      if (mmImportSaveBtn) {{
        mmImportSaveBtn.addEventListener('click', function () {{
          var btn = this;
          btn.disabled = true;
          window.fetch('/api/mindmaps/shares/{share.code}/import', {{ method: 'POST' }})
            .then(function (res) {{ return res.ok ? res.json() : Promise.reject(); }})
            .then(function (data) {{
              try {{
                if (data && data.importedMindmapId) {{
                  window.localStorage.setItem('myscape:mindmaps:activeMindmapId', data.importedMindmapId);
                }}
              }} catch (e) {{ /* same best-effort posture setActiveMindmapId's own try/catch takes above -- losing the auto-select is fine, the import itself already succeeded */ }}
              window.location.href = '/dashboard/mindmaps';
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
        title=f"{owner_name}'s shared Mindmap — myscape",
        player=viewer,
        body=body,
        extra_head=extra_head,
        extra_script=wrapper_script,
        meta_description=f'{owner_name} shared their "{mindmap_name}" Mindmap on myscape.',
    )

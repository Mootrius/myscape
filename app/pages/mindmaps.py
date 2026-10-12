"""Mindmaps: the page, its shared view, and the landing preview."""
import json
import os
from html import escape
from typing import TYPE_CHECKING, Optional, Tuple

from app.pages.asset_loader import read_asset
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
    script = read_asset("mindmaps.js", indent=4)
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

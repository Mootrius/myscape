"""Mindmaps: a player's named goal/idea trees. Holds the tree operations (insert
a node as parent/child/sibling, delete a subtree), goal completion evaluation,
and conversion of a MindMap row to client JSON.
`nodes` (see MindMap in app/models.py) is a flat list of dicts: each node has
a parentId (None for the one root) and an `order` float among its siblings.
Mutating functions return a new list rather than mutating, since SQLAlchemy
only detects a new object assigned to a JSONB column (see GearSetup in
app/models.py). ORM work stays in main.py.
"""
import math
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.item_ids import find_item_ids
from app.models import MindMap, GameAccount

# Node colors: a small named set (not free-form hex) so the client styles each
# with a CSS class (mindmaps.css). "gray" is the default. Every color but
# "white" picks a goal type (GOAL_TYPE_BY_COLOR) whose criteria live in the
# node's `goal` dict (see clean_goal). "white" is reserved for the root, done
# once every other node is (see evaluate_completion).
NODE_COLORS = ["gray", "red", "orange", "yellow", "green", "blue", "purple", "white"]
DEFAULT_COLOR = "gray"
DEFAULT_TEXT = "New"
MAX_NODE_TEXT_LENGTH = 120
MAX_MINDMAP_NAME_LENGTH = 60
# Max note length: only a backstop for direct API calls. The real 2-line cap is
# client-side (clampNoteInput in app/pages.py; the font is proportional),
# because a scrolling note reintroduces the blur described at .mm-suggestions in
# mindmaps.css. See _clean_note.
MAX_NODE_NOTE_LENGTH = 200

# Goal type per color (see clean_goal/evaluate_completion). "manual" (gray) is
# checked off by the player, even outside Edit Mode. None (white) is root-only.
GOAL_TYPE_BY_COLOR = {
    "gray": "manual",
    "red": "kc",
    "orange": "item",
    "yellow": "gp",
    "green": "skill",
    "blue": "quest",
    "purple": "diary",
    "white": None,
}

# Allowed `activity` values for a red (kc) goal: anything the plugin logs a
# LootEvent for (app/loot.py). Clue tiers cannot be told apart: RuneLite reports
# all non-NPC, non-pickpocket rewards as source_type "event".
KC_ACTIVITY_TYPES = ["npc", "pickpocket", "event"]

# The 24 OSRS skills, lowercase; a green (skill) goal's `skill` must be one.
SKILL_NAMES = {
    "attack", "defence", "strength", "hitpoints", "ranged", "prayer", "magic",
    "cooking", "woodcutting", "fletching", "fishing", "firemaking", "crafting",
    "smithing", "mining", "herblore", "agility", "thieving", "slayer", "farming",
    "runecraft", "hunter", "construction", "sailing",
}

# The 12 achievement diary areas, lowercase/slugified; a purple (diary) goal's
# `area` must be one.
DIARY_AREAS = {
    "ardougne", "desert", "falador", "fremennik", "kandarin", "karamja",
    "kourend_kebos", "lumbridge_draynor", "morytania", "varrock",
    "western_provinces", "wilderness",
}

# Ordered low to high: a goal for "hard" is also satisfied by "elite" (see
# evaluate_completion), since only the highest tier per area is stored.
DIARY_TIERS = ["easy", "medium", "hard", "elite"]

MAX_GOAL_NAME_LENGTH = 80
# Defensive ceilings, not OSRS limits; only a malformed client would hit them
# (compare MAX_BANK_ITEMS in app/main.py).
MAX_KC_TARGET = 1_000_000
MAX_ITEM_QTY_TARGET = 2_000_000_000
MAX_GP_TARGET = 100_000_000_000
# Goal bounds: skill LEVEL 1-126 (126 is the virtual-level cap), XP
# 0-200,000,000 (OSRS max).
MIN_SKILL_LEVEL, MAX_SKILL_LEVEL = 1, 126
MIN_SKILL_XP, MAX_SKILL_XP = 0, 200_000_000


def _build_skill_xp_table() -> List[int]:
    """OSRS xp-per-level curve for levels 1-126 (including virtual levels).
    Mirrors SKILL_XP_TABLE in app/pages.py. Index 0 is unused; index 1 is 0.
    """
    table = [0, 0]
    cumulative = 0
    for level in range(1, MAX_SKILL_LEVEL):
        cumulative += math.floor(level + 300 * (2 ** (level / 7)))
        table.append(math.floor(cumulative / 4))
    return table


SKILL_XP_TABLE = _build_skill_xp_table()


def _xp_for_level(level: int) -> int:
    """The xp needed for `level`, clamped into range. Level goals are checked
    against xp because the client's level is 99-capped.
    """
    level = max(MIN_SKILL_LEVEL, min(MAX_SKILL_LEVEL, level))
    return SKILL_XP_TABLE[level]


def _clean_text(text: Optional[str], allow_empty: bool = False) -> str:
    """Trims/truncates node text. `allow_empty` lets a new node start blank (the
    canvas focuses its editor at once). Otherwise blank text falls back to
    DEFAULT_TEXT, a guard for direct API calls.
    """
    text = (text or "").strip()[:MAX_NODE_TEXT_LENGTH].strip()
    if allow_empty:
        return text
    return text or DEFAULT_TEXT


def _clean_note(note: Optional[str]) -> str:
    """Trims/truncates a node's optional note; may be blank, with no placeholder.
    Backstop only (see MAX_NODE_NOTE_LENGTH): collapses anything past 2
    explicit lines, then applies the character cap.
    """
    cleaned = (note or "").strip()
    lines = cleaned.split("\n")
    if len(lines) > 2:
        cleaned = "\n".join(lines[:2])
    return cleaned[:MAX_NODE_NOTE_LENGTH]


def _clean_color(color: Optional[str], is_root: bool = False) -> str:
    """The root is always "white" and a non-root node never is; an invalid color
    silently falls back to DEFAULT_COLOR rather than rejecting the write.
    """
    if is_root:
        return "white"
    cleaned = color if color in NODE_COLORS else DEFAULT_COLOR
    return DEFAULT_COLOR if cleaned == "white" else cleaned


def _clean_goal_text(value, field_name: str) -> str:
    text = (str(value) if value is not None else "").strip()[:MAX_GOAL_NAME_LENGTH]
    if not text:
        raise ValueError(f"{field_name} can't be empty.")
    return text


def _clean_int_in_range(value, field_name: str, minimum: int, maximum: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a whole number.")
    if n < minimum or n > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}.")
    return n


def _clean_goal_date(value, field_name: str) -> str:
    """Validates a "YYYY-MM-DD" date string (native <input type="date"> format).
    Stored as that string; only evaluate_completion parses it.
    """
    text = (str(value) if value is not None else "").strip()
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"{field_name} must be a YYYY-MM-DD date.")
    return text


def default_goal(color: str) -> Optional[Dict]:
    """The blank goal a node gets when its color changes to `color` (see
    update_node); old fields are not carried over. None for "white".
    """
    goal_type = GOAL_TYPE_BY_COLOR.get(color)
    if goal_type == "manual":
        return {"manualComplete": False}
    if goal_type is None:
        return None
    return {}


def clean_goal(color: str, goal, require_complete: bool = True) -> Optional[Dict]:
    """Validates a goal payload against the shape `color`'s goal type requires.
    Present fields are always validated; `require_complete` controls whether
    missing ones are rejected (False only in replace_nodes, so undo/redo
    restores partly filled goals). Raises ValueError (safe to show the
    player). Returns None for "white".
    """
    goal_type = GOAL_TYPE_BY_COLOR.get(color)
    goal = goal if isinstance(goal, dict) else {}

    if goal_type == "manual":
        return {"manualComplete": bool(goal.get("manualComplete"))}
    if goal_type is None:
        return None

    cleaned: Dict = {}

    def field(name, clean_value, missing_msg):
        value = goal.get(name)
        if value is None or value == "":
            if require_complete:
                raise ValueError(missing_msg)
            return
        cleaned[name] = clean_value(value)

    if goal_type == "kc":
        def _activity(v):
            if v not in KC_ACTIVITY_TYPES:
                raise ValueError(f"activityType must be one of {KC_ACTIVITY_TYPES}.")
            return v
        field("activityType", _activity, "Pick what kind of activity this goal tracks.")
        field("sourceName", lambda v: _clean_goal_text(v, "sourceName"), "Pick an NPC.")
        field("targetCount", lambda v: _clean_int_in_range(v, "targetCount", 1, MAX_KC_TARGET), "Set a target kc.")
        # sinceDate is optional even when require_complete is True: a kc goal
        # without it counts kc all-time. Blank or missing values are left out.
        since_date = goal.get("sinceDate")
        if since_date:
            cleaned["sinceDate"] = _clean_goal_date(since_date, "sinceDate")
        return cleaned

    if goal_type == "item":
        field("itemName", lambda v: _clean_goal_text(v, "itemName"), "Pick an item.")
        field("targetQty", lambda v: _clean_int_in_range(v, "targetQty", 1, MAX_ITEM_QTY_TARGET), "Set a target quantity.")
        return cleaned

    if goal_type == "gp":
        field("targetGp", lambda v: _clean_int_in_range(v, "targetGp", 1, MAX_GP_TARGET), "Set a gp target.")
        return cleaned

    if goal_type == "skill":
        def _skill(v):
            v = str(v).strip().lower()
            if v not in SKILL_NAMES:
                raise ValueError(f"skill must be one of {sorted(SKILL_NAMES)}.")
            return v
        def _metric(v):
            if v not in ("level", "xp"):
                raise ValueError("metric must be 'level' or 'xp'.")
            return v
        field("skill", _skill, "Pick a skill.")
        field("metric", _metric, "Pick level or experience.")
        metric = cleaned.get("metric")
        if metric == "xp":
            field("target", lambda v: _clean_int_in_range(v, "target", MIN_SKILL_XP, MAX_SKILL_XP), "Set an experience target.")
        else:
            field("target", lambda v: _clean_int_in_range(v, "target", MIN_SKILL_LEVEL, MAX_SKILL_LEVEL), "Set a level target.")
        return cleaned

    if goal_type == "quest":
        field("questName", lambda v: _clean_goal_text(v, "questName"), "Pick a quest.")
        return cleaned

    if goal_type == "diary":
        def _area(v):
            v = str(v).strip().lower()
            if v not in DIARY_AREAS:
                raise ValueError(f"area must be one of {sorted(DIARY_AREAS)}.")
            return v
        def _tier(v):
            v = str(v).strip().lower()
            if v not in DIARY_TIERS:
                raise ValueError(f"tier must be one of {DIARY_TIERS}.")
            return v
        field("area", _area, "Pick a diary area.")
        field("tier", _tier, "Pick a tier.")
        return cleaned

    return cleaned


def set_node_goal(nodes: List[Dict], node_id: str, goal: Dict) -> List[Dict]:
    """Returns a new node list with the node's goal replaced, fully validated
    against its current color (see clean_goal). Also how a gray node's manual
    "Complete" works, the one mutation allowed outside Edit Mode. Raises
    ValueError if the node does not exist or `goal` does not fit.
    """
    node = _find(nodes, node_id)
    if node is None:
        raise ValueError("That node no longer exists.")
    cleaned = clean_goal(node.get("color", DEFAULT_COLOR), goal, require_complete=True)
    return [dict(n, goal=cleaned) if n["id"] == node_id else n for n in nodes]


def new_root_node(text: Optional[str] = None) -> Dict:
    """The starting node of a new mindmap: always "white" (see NODE_COLORS),
    never gray.
    """
    return {
        "id": str(uuid.uuid4()),
        "parentId": None,
        "text": _clean_text(text),
        "color": "white",
        "order": 0.0,
        "goal": None,
    }


def _find(nodes: List[Dict], node_id: str) -> Optional[Dict]:
    return next((n for n in nodes if n["id"] == node_id), None)


def _children(nodes: List[Dict], parent_id: Optional[str]) -> List[Dict]:
    return sorted((n for n in nodes if n["parentId"] == parent_id), key=lambda n: n["order"])


def _depth(nodes: List[Dict], node_id: str) -> int:
    """Parent hops from `node_id` to the root (root is 0); structural parentId
    only, not extraParentIds.
    """
    depth = 0
    node = _find(nodes, node_id)
    while node is not None and node["parentId"] is not None:
        node = _find(nodes, node["parentId"])
        depth += 1
    return depth


def _next_child_order(nodes: List[Dict], parent_id: str) -> float:
    kids = _children(nodes, parent_id)
    return (kids[-1]["order"] + 1.0) if kids else 0.0


def _order_after(nodes: List[Dict], node: Dict) -> float:
    """An order value sorting right after `node` among its siblings: the midpoint
    to the next sibling, or order + 1 if last.
    """
    siblings = _children(nodes, node["parentId"])
    idx = next(i for i, n in enumerate(siblings) if n["id"] == node["id"])
    if idx + 1 < len(siblings):
        return (node["order"] + siblings[idx + 1]["order"]) / 2.0
    return node["order"] + 1.0


def _order_before(nodes: List[Dict], node: Dict) -> float:
    """Mirror of _order_after: sorts right before `node`."""
    siblings = _children(nodes, node["parentId"])
    idx = next(i for i, n in enumerate(siblings) if n["id"] == node["id"])
    if idx > 0:
        return (siblings[idx - 1]["order"] + node["order"]) / 2.0
    return node["order"] - 1.0


def add_node(
    nodes: List[Dict],
    relative_id: str,
    relation: str,
    text: Optional[str] = None,
    color: Optional[str] = None,
    before: bool = False,
) -> "tuple[List[Dict], str]":
    """Returns (new_nodes, new_node_id) with a node inserted relative to
    `relative_id`, per `relation`: "child" (appended after existing children),
    "sibling" (after the relative node, before it if `before`), or "parent"
    (takes the relative node's slot, which becomes its only child). Sibling
    and parent are not allowed for the root, which must stay the one
    undeletable node (see delete_node). Raises ValueError (safe to show)
    otherwise.
    """
    relative = _find(nodes, relative_id)
    if relative is None:
        raise ValueError("That node no longer exists.")

    new_color = _clean_color(color)
    new_node = {
        "id": str(uuid.uuid4()),
        "text": _clean_text(text, allow_empty=True),
        "color": new_color,
        "goal": default_goal(new_color),
    }

    if relation == "child":
        new_node["parentId"] = relative_id
        new_node["order"] = _next_child_order(nodes, relative_id)
        return nodes + [new_node], new_node["id"]

    if relation == "sibling":
        if relative["parentId"] is None:
            raise ValueError("The root node can't have a sibling -- try adding a parent or child instead.")
        new_node["parentId"] = relative["parentId"]
        new_node["order"] = _order_before(nodes, relative) if before else _order_after(nodes, relative)
        return nodes + [new_node], new_node["id"]

    if relation == "parent":
        if relative["parentId"] is None:
            raise ValueError("The root node can't have a parent added -- it's the one node every mindmap keeps.")
        new_node["parentId"] = relative["parentId"]
        new_node["order"] = relative["order"]
        updated = []
        for n in nodes:
            if n["id"] == relative_id:
                n = dict(n)
                n["parentId"] = new_node["id"]
                n["order"] = 0.0
            updated.append(n)
        return updated + [new_node], new_node["id"]

    raise ValueError("relation must be 'parent', 'child', or 'sibling'.")


def add_shared_child(
    nodes: List[Dict], parent_ids: List[str], text: Optional[str] = None, color: Optional[str] = None
) -> "tuple[List[Dict], str]":
    """Returns a new node list with a node added as a shared child of two or more
    nodes (the canvas's shift-click multi-select). Structurally it is a child
    of parent_ids[0]; the other ids go in the display-only `extraParentIds`
    (extra connectors, centering). Raises ValueError if fewer than two ids, an
    unknown id, or the nodes are not all at the same depth (see _depth).
    """
    if len(parent_ids) < 2:
        raise ValueError("Select at least two nodes to add a shared child below them.")
    parents = []
    for parent_id in parent_ids:
        parent = _find(nodes, parent_id)
        if parent is None:
            raise ValueError("That node no longer exists.")
        parents.append(parent)

    depths = {_depth(nodes, parent_id) for parent_id in parent_ids}
    if len(depths) > 1:
        raise ValueError("Selected nodes must all be at the same level to add a shared child below them.")

    primary_parent_id = parent_ids[0]
    new_color = _clean_color(color)
    new_node = {
        "id": str(uuid.uuid4()),
        "text": _clean_text(text, allow_empty=True),
        "color": new_color,
        "goal": default_goal(new_color),
        "parentId": primary_parent_id,
        "order": _next_child_order(nodes, primary_parent_id),
        "extraParentIds": parent_ids[1:],
    }
    return nodes + [new_node], new_node["id"]


def update_node(
    nodes: List[Dict],
    node_id: str,
    text: Optional[str] = None,
    color: Optional[str] = None,
    note: Optional[str] = None,
) -> List[Dict]:
    """Returns a new node list with the node's text, color, and/or note replaced
    (whichever is not None). A color change resets `goal` (see default_goal)
    but keeps `note`. Raises ValueError if the node does not exist.
    """
    node = _find(nodes, node_id)
    if node is None:
        raise ValueError("That node no longer exists.")
    is_root = node.get("parentId") is None
    updated = []
    for n in nodes:
        if n["id"] == node_id:
            n = dict(n)
            if text is not None:
                n["text"] = _clean_text(text)
            if color is not None:
                new_color = _clean_color(color, is_root=is_root)
                if new_color != n.get("color"):
                    n["goal"] = default_goal(new_color)
                n["color"] = new_color
            if note is not None:
                n["note"] = _clean_note(note)
        updated.append(n)
    return updated


def delete_node(nodes: List[Dict], node_id: str) -> List[Dict]:
    """Returns a new node list without the node and its subtree. Raises
    ValueError if the node does not exist or is the root. The node is also
    stripped from every extraParentIds, so a shared child keeps no dangling
    reference.
    """
    target = _find(nodes, node_id)
    if target is None:
        raise ValueError("That node no longer exists.")
    if target["parentId"] is None:
        raise ValueError("The root node can't be deleted on its own -- delete the whole mindmap instead.")

    to_remove = {node_id}
    # Sweep until no node has a removed parent; terminates even on a cyclic
    # list.
    changed = True
    while changed:
        changed = False
        for n in nodes:
            if n["id"] not in to_remove and n["parentId"] in to_remove:
                to_remove.add(n["id"])
                changed = True

    kept = []
    for n in nodes:
        if n["id"] in to_remove:
            continue
        extra_parent_ids = n.get("extraParentIds")
        if extra_parent_ids:
            pruned = [pid for pid in extra_parent_ids if pid not in to_remove]
            if len(pruned) != len(extra_parent_ids):
                n = dict(n)
                n["extraParentIds"] = pruned
        kept.append(n)
    return kept


def replace_nodes(nodes: List[Dict]) -> List[Dict]:
    """Returns a new node list from a full snapshot `nodes` (undo/redo PUTs back
    past server responses; see MM.undoStack in app/pages.py). The payload is
    untrusted, so everything is re-cleaned; goals use require_complete=False.
    Raises ValueError unless it is a well-formed tree (one root, unique ids,
    no dangling references, no cycles).
    """
    if not nodes:
        raise ValueError("A mindmap needs at least one node.")

    ids = [n.get("id") for n in nodes]
    if len(set(ids)) != len(ids) or any(i is None for i in ids):
        raise ValueError("Every node needs its own unique id.")
    id_set = set(ids)
    by_id = {n["id"]: n for n in nodes}

    roots = [n for n in nodes if n.get("parentId") is None]
    if len(roots) != 1:
        raise ValueError("A mindmap needs exactly one root node.")

    for n in nodes:
        parent_id = n.get("parentId")
        if parent_id is not None and parent_id not in id_set:
            raise ValueError("A node's parent must exist in the same tree.")

    # Cycle guard: _depth and others walk this chain assuming it ends at the
    # root. Bounded by the tree's size.
    for n in nodes:
        cur = n
        hops = 0
        while cur.get("parentId") is not None:
            hops += 1
            if hops > len(nodes):
                raise ValueError("The submitted tree contains a cycle.")
            cur = by_id.get(cur["parentId"])
            if cur is None:
                break

    cleaned = []
    for n in nodes:
        is_root = n.get("parentId") is None
        new_color = _clean_color(n.get("color"), is_root=is_root)
        new_node = {
            "id": n["id"],
            "parentId": n.get("parentId"),
            # allow_empty=True so a not-yet-named node restores exactly.
            "text": _clean_text(n.get("text"), allow_empty=True),
            "color": new_color,
            "goal": clean_goal(new_color, n.get("goal"), require_complete=False),
            "order": float(n.get("order") or 0.0),
        }
        # Only carried across if present, so notes-less nodes gain no empty key.
        if n.get("note"):
            new_node["note"] = _clean_note(n.get("note"))
        extra_parent_ids = n.get("extraParentIds")
        if extra_parent_ids:
            pruned = [pid for pid in extra_parent_ids if pid in id_set and pid != n["id"]]
            if pruned:
                new_node["extraParentIds"] = pruned
        cleaned.append(new_node)
    return cleaned


# Goal completion evaluation

def _normalize_lookup_name(name: Optional[str]) -> str:
    return (name or "").strip().lower()


_OFFHAND_SUFFIX = " (off-hand)"


def _offhand_pair_name(item_name: Optional[str]) -> Optional[str]:
    """Returns the other name in an "item" goal's off-hand pair, if any. Some
    tools (Imcando hammer, Amy's saw, Bruma torch; see app/data/item_ids.json)
    have an "(off-hand)" variant that is equivalent, so owning either
    satisfies the goal. Naming transform only; find_item_ids confirms the item
    exists.
    """
    name = (item_name or "").strip()
    if not name:
        return None
    if name.lower().endswith(_OFFHAND_SUFFIX):
        return name[: -len(_OFFHAND_SUFFIX)].strip() or None
    return name + _OFFHAND_SUFFIX


def evaluate_completion(nodes: List[Dict], context: Dict) -> Dict[str, bool]:
    """Returns {node_id: bool}: whether each node's goal is currently satisfied
    (computed per read, never stored). `context` comes from
    _build_goal_context in app/main.py:
    - owned_pool_by_id / owned_pool_by_name: Purchase Goals' owned pools
    (build_owned_pools), for "item" goals.
    - gp_total: coins plus platinum tokens (1k gp each), for "gp" goals.
    - skills: {<skill>: {"level", "xp"}}; completed_quests: lowercased names.
    - diary_tiers: {<area>: <highest tier>}; a higher tier satisfies a lower
    one.
    - kc_counts: {(activityType, <lowercased source>): [occurred_at, ...]}
    from LootEvent rows.
    The root is evaluated last: complete iff it has other nodes and all are
    complete.
    """
    completed: Dict[str, bool] = {}
    owned_pool_by_id = context.get("owned_pool_by_id", {})
    owned_pool_by_name = context.get("owned_pool_by_name", {})
    gp_total = context.get("gp_total", 0)
    skills = context.get("skills", {})
    completed_quests = context.get("completed_quests", set())
    diary_tiers = context.get("diary_tiers", {})
    kc_counts = context.get("kc_counts", {})

    non_root_ids = []
    for n in nodes:
        if n.get("parentId") is None:
            continue
        non_root_ids.append(n["id"])
        color = n.get("color", DEFAULT_COLOR)
        goal_type = GOAL_TYPE_BY_COLOR.get(color)
        goal = n.get("goal") or {}
        done = False

        if goal_type == "manual":
            done = bool(goal.get("manualComplete"))
        elif goal_type == "kc":
            activity_type, source_name, target = goal.get("activityType"), goal.get("sourceName"), goal.get("targetCount")
            if activity_type and source_name and target:
                key = (activity_type, _normalize_lookup_name(source_name))
                occurrences = kc_counts.get(key, [])
                since_date = goal.get("sinceDate")
                if since_date:
                    # sinceDate was validated at save time (_clean_goal_date);
                    # only occurrences on or after midnight UTC of that date
                    # count.
                    since_dt = datetime.strptime(since_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    count = sum(1 for ts in occurrences if ts and ts >= since_dt)
                else:
                    count = len(occurrences)
                done = count >= target
        elif goal_type == "item":
            item_name, target = goal.get("itemName"), goal.get("targetQty")
            if item_name and target:
                # Either name in an off-hand pair satisfies the other, so ids
                # from both are pooled, deduped against item_name.
                names = [item_name]
                pair_name = _offhand_pair_name(item_name)
                if pair_name and pair_name.lower() != item_name.strip().lower():
                    names.append(pair_name)
                ids = [i for n in names for i in (find_item_ids(n) or [])]
                if ids:
                    owned = sum(owned_pool_by_id.get(i, 0) for i in ids)
                else:
                    owned = sum(owned_pool_by_name.get(_normalize_lookup_name(n), 0) for n in names)
                done = owned >= target
        elif goal_type == "gp":
            target = goal.get("targetGp")
            done = bool(target) and gp_total >= target
        elif goal_type == "skill":
            skill, metric, target = goal.get("skill"), goal.get("metric"), goal.get("target")
            if skill and metric and target:
                # LVL and XP goals are both checked against xp, since the
                # plugin's `level` is 99-capped and cannot reach a virtual-level
                # target.
                have_xp = (skills.get(skill) or {}).get("xp", 0)
                need_xp = target if metric == "xp" else _xp_for_level(target)
                done = have_xp >= need_xp
        elif goal_type == "quest":
            quest_name = goal.get("questName")
            done = bool(quest_name) and _normalize_lookup_name(quest_name) in completed_quests
        elif goal_type == "diary":
            area, tier = goal.get("area"), goal.get("tier")
            if area and tier and tier in DIARY_TIERS:
                have_tier = diary_tiers.get(area)
                done = have_tier in DIARY_TIERS and DIARY_TIERS.index(have_tier) >= DIARY_TIERS.index(tier)

        completed[n["id"]] = done

    for n in nodes:
        if n.get("parentId") is None:
            completed[n["id"]] = bool(non_root_ids) and all(completed[nid] for nid in non_root_ids)

    return completed


def serialize_mindmap(mindmap: MindMap, context: Optional[Dict] = None) -> Dict:
    nodes = mindmap.nodes
    completed = evaluate_completion(nodes, context) if context is not None else {}
    return {
        "id": str(mindmap.id),
        "name": mindmap.name,
        "createdAt": mindmap.created_at.isoformat() if mindmap.created_at else None,
        "nodes": [dict(n, completed=completed.get(n["id"], False)) for n in nodes],
    }


def build_mindmap_share_snapshot(mindmap: MindMap, context: Dict) -> dict:
    """Freezes one of game_account's mindmaps (resolved and ownership-checked by
    the caller) into the payload for a SharedContent row (see POST
    /api/mindmaps/<id>/share, render_mindmap_share in app/pages.py). This is
    serialize_mindmap verbatim, with each node's `completed` flag baked in as
    evaluated against `context` at share time.
    """
    return {"mindmap": serialize_mindmap(mindmap, context)}


def import_mindmap_from_share_payload(db: Session, game_account: GameAccount, payload: dict) -> MindMap:
    """The reverse of build_mindmap_share_snapshot: creates a new, editable
    MindMap for game_account from a share payload (POST
    /api/mindmaps/shares/{code}/import in app/main.py). Strips the serialized
    `completed` key and keeps the sharer's name and node ids. The caller
    commits.
    """
    mindmap_payload = payload["mindmap"]
    nodes = [
        {k: v for k, v in node.items() if k != "completed"}
        for node in (mindmap_payload.get("nodes") or [])
    ]
    mindmap = MindMap(
        # Explicit id rather than the column default, which is not applied until
        # flush; the caller reads mindmap.id right away.
        id=uuid.uuid4(),
        game_account_id=game_account.id,
        name=mindmap_payload.get("name") or "New Mindmap",
        nodes=nodes,
    )
    db.add(mindmap)
    return mindmap


def build_mindmaps_state(db: Session, game_account: GameAccount, context: Optional[Dict] = None) -> Dict:
    """The state the Mindmaps page loads (render_mindmaps in app/pages.py): every
    mindmap with its nodes, oldest first. `context` is optional for
    scripts/tests; real callers always pass one so `completed` flags are real.
    """
    mindmaps = (
        db.query(MindMap)
        .filter(MindMap.game_account_id == game_account.id)
        .order_by(MindMap.created_at.asc())
        .all()
    )
    return {"mindmaps": [serialize_mindmap(m, context) for m in mindmaps]}

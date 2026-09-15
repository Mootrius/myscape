"""Mindmaps -- a player's named goal/idea trees. Brand new feature (no
Maintrius equivalent to port, unlike Purchase Goals/Loot Tracker), so
this module is the whole of its own server-side logic: the tree-shape
operations (insert a node as a parent/child/sibling of an existing one,
delete a node and its whole subtree) plus turning a MindMap row into
the JSON the client renders from.

A mindmap's `nodes` column (see MindMap's docstring in app/models.py)
is a flat list of plain dicts, never a nested/recursive structure --
each node just points at its own parent by id (None for the tree's one
root), and an `order` float ranks it among that parent's other
children. Every function below that changes the tree takes the current
list and returns a brand new one rather than mutating it in place --
required for the write to actually persist (see GearSetup's docstring
in app/models.py for why: SQLAlchemy only notices a *new* object
assigned to a JSONB column, not an existing one mutated after the
fact), and it also means every mutation is a plain, easily-tested
list-in-list-out function with no ORM/session concerns of its own --
those stay in main.py's route handlers, same split as
app/purchase_goals.py.
"""
import math
import uuid
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.item_ids import find_item_ids
from app.models import MindMap, Player

# The fixed palette a node's `color` can be -- deliberately a small,
# named set (not a free-form hex value) so the client can style each
# one with a real CSS class instead of trusting arbitrary color input,
# the same reasoning GearSetup's owned/not-owned/affordable border
# colors already follow. "gray" (panel-2, the site's own default box
# shade) is what every new node starts as; see mindmaps.css for what
# each name actually renders as.
#
# Every color but "white" also picks a goal TYPE (see GOAL_TYPE_BY_COLOR
# below) -- this is what turns a mindmap from a plain idea tree into a
# self-checking goal tree: a node's color says what kind of thing has
# to happen for it to be considered done, and its `goal` dict (see
# clean_goal) holds the specific criteria. "white" is the one color a
# player never picks for themselves -- it's reserved for a mindmap's
# one root node, the "final" goal/unlock that isn't trackable on its
# own at all, just marked done once every other node is (see
# evaluate_completion).
NODE_COLORS = ["gray", "red", "orange", "yellow", "green", "blue", "purple", "white"]
DEFAULT_COLOR = "gray"
DEFAULT_TEXT = "New"
MAX_NODE_TEXT_LENGTH = 120
MAX_MINDMAP_NAME_LENGTH = 60
# A node's own optional note (see update_node/_clean_note below) --
# free-form "how I'd like to achieve this" text, not a display label,
# so it gets much more room than MAX_NODE_TEXT_LENGTH.
MAX_NODE_NOTE_LENGTH = 1000

# Which goal TYPE each color picks -- see clean_goal/evaluate_completion
# below for what each type actually checks. "manual" (gray) is the one
# type with no auto-detection at all: the player just clicks a
# "Complete" button themselves once they've done whatever the node
# says, available even outside the canvas's Edit Mode (see
# render_mindmaps in app/pages.py) since checking it off isn't
# "editing" the node the way changing its criteria is. None (white) has
# no goal type -- it's never player-set; see NODE_COLORS' own comment.
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

# What a red (kc) goal's "activity" field can be -- KC-based goals cover
# anything "trackable"/"lootable" this app's plugin already logs one
# LootEvent per occurrence of (see LootEvent's docstring in
# app/models.py and app/loot.py): an NPC/boss kill, a pickpocket, or a
# clue casket/minigame reward (RuneLite's own LootReceived event lumps
# every non-NPC, non-pickpocket reward into source_type "event" -- see
# LootEvent's docstring for why a clue's TIER specifically can't be
# told apart from this, a real limitation of the event this reads, not
# something worked around here).
KC_ACTIVITY_TYPES = ["npc", "pickpocket", "event"]

# The 24 real OSRS skills, lowercase -- what a green (skill) goal's
# `skill` field must be one of.
SKILL_NAMES = {
    "attack", "defence", "strength", "hitpoints", "ranged", "prayer", "magic",
    "cooking", "woodcutting", "fletching", "fishing", "firemaking", "crafting",
    "smithing", "mining", "herblore", "agility", "thieving", "slayer", "farming",
    "runecraft", "hunter", "construction", "sailing",
}

# The 12 real OSRS achievement diary areas, lowercase/slugified -- what
# a purple (diary) goal's `area` field must be one of.
DIARY_AREAS = {
    "ardougne", "desert", "falador", "fremennik", "kandarin", "karamja",
    "kourend_kebos", "lumbridge_draynor", "morytania", "varrock",
    "western_provinces", "wilderness",
}

# Ordered low-to-high -- a diary goal asking for "hard" is also
# satisfied by a player who's actually finished "elite" for that area
# (see evaluate_completion), the same way the real in-game diary
# journal only ever shows one current (highest) tier per area, not
# each one separately.
DIARY_TIERS = ["easy", "medium", "hard", "elite"]

MAX_GOAL_NAME_LENGTH = 80
# Defensive ceilings, not real OSRS limits -- generous enough that no
# legitimate goal could ever hit them, so the only way a request would
# is a malformed/buggy client, same spirit as MAX_BANK_ITEMS etc. in
# app/main.py.
MAX_KC_TARGET = 1_000_000
MAX_ITEM_QTY_TARGET = 2_000_000_000
MAX_GP_TARGET = 100_000_000_000
# The player's own bounds, given verbatim: a skill LEVEL goal is
# 1-126 (level 1 through OSRS's "virtual level" cap above the real
# level-99 one -- both ends allowed even though "reach level 1" is
# always already true, by request), an XP goal is 0-200,000,000
# (0 is level 1's own xp requirement -- see app/pages.py's
# SKILL_XP_TABLE, which mirrors this same level-1-through-126 range
# -- and 200,000,000 is OSRS's own max skill xp).
MIN_SKILL_LEVEL, MAX_SKILL_LEVEL = 1, 126
MIN_SKILL_XP, MAX_SKILL_XP = 0, 200_000_000


def _build_skill_xp_table() -> List[int]:
    """The OSRS xp-per-level curve (levels 1-126, including the
    "virtual" levels above the real level-99 cap) -- mirrors
    app/pages.py's own SKILL_XP_TABLE exactly (same formula, see its
    comment for the source), built once at import off MAX_SKILL_LEVEL
    rather than hardcoded so the two can never drift apart. Index 0 is
    unused (levels are 1-indexed); index 1 is always 0.
    """
    table = [0, 0]
    cumulative = 0
    for level in range(1, MAX_SKILL_LEVEL):
        cumulative += math.floor(level + 300 * (2 ** (level / 7)))
        table.append(math.floor(cumulative / 4))
    return table


SKILL_XP_TABLE = _build_skill_xp_table()


def _xp_for_level(level: int) -> int:
    """The xp SKILL_XP_TABLE says `level` needs, clamped into range --
    used by evaluate_completion below to check a LVL-metric skill goal
    (including a virtual one above 99) against the player's own xp
    rather than their reported level, which the client only ever sends
    real/99-capped (see evaluate_completion's own comment)."""
    level = max(MIN_SKILL_LEVEL, min(MAX_SKILL_LEVEL, level))
    return SKILL_XP_TABLE[level]


def _clean_text(text: Optional[str], allow_empty: bool = False) -> str:
    """Trims/truncates whatever text a node is given. `allow_empty`
    lets a brand new node (see add_node/add_shared_child below) actually
    start with nothing in it -- the canvas immediately queues a focus
    for a fresh node (see selectNode's own comment in the page script),
    landing either in the root's own inline-editable label or, for
    every other new node (always gray), a text box in its popover (see
    renderGoalFieldsHtml's "manual" branch) -- either way there's no
    "New" placeholder for the player to notice or have to clear first.
    Everywhere else (an existing node's text being CHANGED, and a
    mindmap's own root, whose text comes from the mindmap's own
    required name) keeps falling back to DEFAULT_TEXT -- update_node's
    callers already refuse to ever submit an empty edit in the first
    place (see commitActiveLabelIfEditing for the root's inline rename,
    and the goal-save click delegation's own manual handling for a gray
    node's popover rename), so this is purely a defensive floor against
    a stray/direct API call blanking an existing node out, not
    something the normal UI can trigger."""
    text = (text or "").strip()[:MAX_NODE_TEXT_LENGTH].strip()
    if allow_empty:
        return text
    return text or DEFAULT_TEXT


def _clean_note(note: Optional[str]) -> str:
    """Trims/truncates a node's own optional note (see update_node) --
    unlike _clean_text, always allowed to come out blank and never
    falls back to a placeholder: a note is optional by design (see
    app/pages.py's node-popover note field), so "no note" is a normal,
    common state to end up in, not something to guard against the way
    a blank node NAME is."""
    return (note or "").strip()[:MAX_NODE_NOTE_LENGTH]


def _clean_color(color: Optional[str], is_root: bool = False) -> str:
    """A root node is always "white", structurally -- never a player's
    choice (see NODE_COLORS' own comment) -- and, symmetrically, a
    NON-root node can never actually become white (silently falls back
    to DEFAULT_COLOR instead of erroring, same spirit as an unrecognized
    color already falling back rather than rejecting the whole write --
    the real client never offers "white" as a pickable swatch in the
    first place, so this only ever matters against a malformed/direct
    API call, not a normal edit)."""
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


def default_goal(color: str) -> Optional[Dict]:
    """The blank goal a node gets the instant its color changes to
    `color` (see update_node) -- a goal shaped for one color's criteria
    rarely means anything for another, so switching colors always
    starts the new one from scratch rather than trying to carry old
    fields across. Returns None for "white" (never player-editable --
    see GOAL_TYPE_BY_COLOR)."""
    goal_type = GOAL_TYPE_BY_COLOR.get(color)
    if goal_type == "manual":
        return {"manualComplete": False}
    if goal_type is None:
        return None
    return {}


def clean_goal(color: str, goal, require_complete: bool = True) -> Optional[Dict]:
    """Validates+cleans a goal payload against whatever shape `color`'s
    goal type requires. Every field that's PRESENT is validated the
    same way regardless of `require_complete` -- an out-of-range value
    or an unrecognized choice is always rejected. What
    `require_complete` controls is whether a MISSING field is also
    rejected:

    - True (the default, used by set_node_goal below -- the node
      canvas's goal-edit form save): every field that color's goal type
      needs must be present, same as every other write path in this
      module validating a whole object rather than accepting a partial
      patch.
    - False (used only by replace_nodes, restoring an undo/redo
      snapshot): a missing field is just left out rather than rejected,
      since the snapshot being restored might have been captured while
      the player had only partly filled the goal in -- undo/redo needs
      to be able to restore that same partial state, not force it
      complete.

    Raises ValueError (safe to show the player as-is) naming whatever's
    missing or invalid. Returns None for "white" (see GOAL_TYPE_BY_COLOR)."""
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
    """Returns a NEW node list with the given node's goal criteria
    replaced -- validated fully (require_complete=True) against its
    CURRENT color, see clean_goal. This is the only way a goal's
    criteria change after a node's color first picked its type;
    changing color itself resets the goal back to blank (see
    update_node) rather than trying to carry old, now-meaningless
    fields across, so this never needs to know a node's previous goal
    shape.

    Also how a gray node's manual "Complete" button works (see
    clean_goal's "manual" branch) -- and the only mutation in this
    module a player can trigger without the canvas's Edit Mode toggled
    on (see app/pages.py), since ticking off a manual goal isn't
    "editing" the node the way changing its criteria is.

    Raises ValueError if the node doesn't exist or `goal` doesn't fit
    its color's shape."""
    node = _find(nodes, node_id)
    if node is None:
        raise ValueError("That node no longer exists.")
    cleaned = clean_goal(node.get("color", DEFAULT_COLOR), goal, require_complete=True)
    return [dict(n, goal=cleaned) if n["id"] == node_id else n for n in nodes]


def new_root_node(text: Optional[str] = None) -> Dict:
    """The single starting node a brand new mindmap is created with --
    always "white" (see NODE_COLORS' own comment), never gray like
    every other node: the root is the tree's one non-trackable "final"
    node from the moment it exists, not something that starts
    undecided."""
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
    """How many parentId hops separate `node_id` from the tree's root
    (root itself is depth 0) -- used by add_shared_child to enforce
    "same vertical level." Walks the real structural parentId chain
    only, never a shared child's extraParentIds (those are display-only
    and don't participate in the tree's actual shape -- see
    add_shared_child's own docstring)."""
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
    """An order value that sorts immediately after `node` among its own
    siblings -- the midpoint to the next sibling if there is one (so
    inserting between two existing siblings never needs to renumber
    anything else), or node's own order + 1 if it's currently last."""
    siblings = _children(nodes, node["parentId"])
    idx = next(i for i, n in enumerate(siblings) if n["id"] == node["id"])
    if idx + 1 < len(siblings):
        return (node["order"] + siblings[idx + 1]["order"]) / 2.0
    return node["order"] + 1.0


def _order_before(nodes: List[Dict], node: Dict) -> float:
    """The mirror image of _order_after -- an order value that sorts
    immediately BEFORE `node` among its own siblings, used for the
    node canvas's left-edge "add sibling" control (right-edge uses
    _order_after instead). Same midpoint-or-plus/minus-one shape, just
    walking to the previous sibling instead of the next."""
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
    """Returns a NEW node list with one extra node inserted relative to
    an existing one (`relative_id`), per `relation`:

      - "child": a new child of the relative node, after its existing
        children (if any).
      - "sibling": a new node sharing the relative node's own parent,
        placed immediately after it (or before it, when `before` is
        true -- the node canvas's right-edge vs. left-edge "add
        sibling" hover controls). The relative node can't be the
        tree's root (a root has no parent to share a sibling under --
        see the single-root shape MindMap.nodes assumes throughout).
      - "parent": a new node takes over the relative node's exact spot
        (same parentId and order) among its current siblings, and the
        relative node becomes that new node's only child. The relative
        node can't be the tree's root -- unlike a sibling, this would
        otherwise actually succeed (the new node just becomes the new
        root), but it's disallowed anyway: every mindmap needs exactly
        one node nobody can delete (see delete_node), and letting a
        parent be added to the root would just create a fresh one of
        those every time, each burying the last "original" node one
        level deeper for no real benefit.

    Returns (new_nodes, new_node_id) -- the caller (see
    add_mindmap_node in app/main.py) hands the id straight back to the
    client so it can select the just-created node without having to
    diff the old and new node lists itself.

    Raises ValueError (its message is safe to show the player as-is)
    on an unknown relation, a missing relative node, a sibling
    requested for the root, or a parent requested for the root."""
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
    """Returns a NEW node list with one extra node added as a shared
    child of two or more existing nodes -- the node canvas's shift-click
    multi-select ("hold shift and select multiple nodes, then add a
    child that connects to all of them"), e.g. four separate "blocklist"
    nodes all feeding into one shared "setup" node below them.

    The single-parent-per-node shape every other function in this file
    assumes (see the module docstring) still holds for STRUCTURAL
    purposes: the new node's real `parentId` is `parent_ids[0]` (the
    first node selected), exactly like any other child, so column
    layout and delete_node's subtree cascade both treat it as an
    ordinary child of that one node. The rest of `parent_ids` are
    recorded as `extraParentIds` -- a purely additional, display-only
    list the client uses to draw the extra connector lines up to those
    other nodes and to nudge the shared child's on-screen position to
    sit centered under the whole group, but which delete_node otherwise
    leaves alone (deleting one of THOSE nodes just prunes it from this
    list -- see delete_node -- while deleting the primary parent still
    cascades away the shared child like any other child of that node).

    Raises ValueError if fewer than two ids are given, any id doesn't
    exist, or the given nodes aren't all at the same vertical level
    (the same number of parentId hops from the root -- see _depth).
    Unlike the old sibling-insertion version this replaced, they don't
    need to share a parent, just a depth -- a shared child can connect
    several different branches together as long as they're all the
    same number of rows down, matching how the canvas actually draws
    them (one shared child, one row below the whole selected group)."""
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
    """Returns a NEW node list with the given node's text, color, and/or
    note replaced -- whichever of the three is not None. Changing color
    always resets that node's `goal` back to a blank default for the new
    color (see default_goal) -- criteria shaped for one goal type rarely
    mean anything for another, so there's nothing worth trying to carry
    across; use set_node_goal afterward to fill the new goal in. `note`
    is deliberately left alone by a color change, unlike `goal` -- it's
    the player's own free-form "how I'd like to achieve this" text (see
    app/pages.py's node-popover note field), which doesn't stop applying
    just because the node's tracked-goal TYPE changed underneath it, the
    way goal criteria shaped for the old type would. Raises ValueError
    if the node doesn't exist."""
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
    """Returns a NEW node list with the given node and its entire
    subtree removed. Raises ValueError if the node doesn't exist, or if
    it's the tree's root -- a mindmap always needs exactly one root, so
    removing it is done by deleting the whole mindmap instead (see
    delete_mindmap in app/main.py), not by deleting just this node.

    A node can also be referenced as an EXTRA (non-structural) parent
    of some shared child via that child's `extraParentIds` -- see
    add_shared_child. Removing a node here strips it out of every
    remaining node's extraParentIds too, so a shared child never keeps
    a dangling reference to a parent that no longer exists; it just
    loses that one extra connector line and stays alive through its
    real (structural) parentId, unless that's ALSO in this subtree, in
    which case it's swept away like any other descendant."""
    target = _find(nodes, node_id)
    if target is None:
        raise ValueError("That node no longer exists.")
    if target["parentId"] is None:
        raise ValueError("The root node can't be deleted on its own -- delete the whole mindmap instead.")

    to_remove = {node_id}
    # Repeatedly sweep for any node whose parent is already marked for
    # removal, until a pass finds nothing new -- a plain flat-list
    # equivalent of a recursive subtree walk, with no risk of infinite
    # recursion even in a maliciously/accidentally cyclic list (there
    # shouldn't be one, but nothing here relies on that being true).
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
    """Returns a NEW node list built from `nodes` -- a full snapshot
    the client is restoring. This is what the node canvas's undo/redo
    buttons use in place of a confirm-before-delete dialog: rather than
    asking "are you sure?" before every destructive edit, the client
    keeps its own stack of this same mindmap's past server-returned
    node lists (see MM.undoStack/MM.redoStack in the Mindmaps script,
    app/pages.py) and PUTs one straight back to step backward/forward
    through it -- so a delete (or any other edit) can always just be
    undone afterward instead of confirmed beforehand.

    Every node's text/color/goal is re-cleaned exactly like any other
    write path (see _clean_text/_clean_color/clean_goal) even though
    the snapshot was already valid once, since it's still untrusted
    input off the wire, not something this function can assume came
    from a real previous server response just because the client
    claims it did. A goal is cleaned leniently (require_complete=False)
    rather than the way set_node_goal cleans a fresh save -- the
    snapshot being restored might have been captured while the player
    had only partly filled a goal in, and undo/redo needs to be able to
    restore that same partial state, not force it complete.

    Raises ValueError if the snapshot isn't a well-formed tree: empty,
    no root (exactly one node with parentId None), a duplicate id, a
    parentId/extraParentIds entry that doesn't point at another node
    in the same snapshot, or a parentId chain that cycles back on
    itself. None of this should ever actually trip for a legitimate
    undo/redo step -- it only ever replays a snapshot this same server
    handed out -- it's a defensive floor against a corrupted or
    tampered payload, same spirit as add_node/add_shared_child raising
    on a shape they don't recognize."""
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

    # Cycle guard for the parentId chain -- _depth and other callers
    # walk this chain assuming it always terminates at the root; a
    # tampered payload with e.g. A's parent set to its own descendant
    # would otherwise hang the server the next time something walks
    # it. Bounded by the tree's own size, so this can't itself loop
    # forever even against a maximally adversarial payload.
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
            # allow_empty=True for the same reason clean_goal above is
            # leniently require_complete=False -- a snapshot being
            # restored might capture a freshly-created node the player
            # hadn't typed a name into yet (see add_node/add_shared_child),
            # and undo/redo needs to restore that exact state rather than
            # silently "fixing" it back to DEFAULT_TEXT.
            "text": _clean_text(n.get("text"), allow_empty=True),
            "color": new_color,
            "goal": clean_goal(new_color, n.get("goal"), require_complete=False),
            "order": float(n.get("order") or 0.0),
        }
        # Only carried across if actually present -- an older snapshot
        # (from before notes existed) or a node that never had one
        # shouldn't gain an empty "note" key it didn't have before, same
        # spirit as extraParentIds right below only being set when
        # there's something to set.
        if n.get("note"):
            new_node["note"] = _clean_note(n.get("note"))
        extra_parent_ids = n.get("extraParentIds")
        if extra_parent_ids:
            pruned = [pid for pid in extra_parent_ids if pid in id_set and pid != n["id"]]
            if pruned:
                new_node["extraParentIds"] = pruned
        cleaned.append(new_node)
    return cleaned


# ---- Goal completion evaluation ----------------------------------------
#
# Everything below is read-only against the tree (no "returns a NEW node
# list" here -- completion is never stored on the node itself, it's
# computed fresh every time a mindmap is read, same "compute fresh on
# every read" philosophy app/purchase_goals.py already follows for
# affordability/ownership). A GoalContext bundles the player's actual
# synced game state that every node's goal gets checked against -- built
# once per request in app/main.py (which is also the only place that can
# freely import both this module and app/purchase_goals.py -- see that
# context-building code's own comment for why it isn't built here).

def _normalize_lookup_name(name: Optional[str]) -> str:
    return (name or "").strip().lower()


def evaluate_completion(nodes: List[Dict], context: Dict) -> Dict[str, bool]:
    """Returns {node_id: bool} for every node in `nodes` -- whether that
    node's goal is currently satisfied. `context` is a plain dict built
    by app/main.py's _build_goal_context, holding everything a goal
    might need to check itself against:

      - owned_pool_by_id / owned_pool_by_name: the same bank+inventory+
        equipment+potion storage+rune pouch+seed vault pools Purchase
        Goals checks a gear slot against (see build_owned_pools in
        app/purchase_goals.py) -- what an "item" goal checks its
        targetQty against.
      - gp_total: coins plus platinum tokens (at 1k gp each) across
        that same pool -- what a "gp" goal checks its targetGp against.
      - skills: {<skill>: {"level": int, "xp": int}} -- what a "skill"
        goal checks its target against (whichever of level/xp it asked
        for).
      - completed_quests: a lowercased set of quest/miniquest names --
        what a "quest" goal's questName is checked for membership in.
      - diary_tiers: {<area>: <highest tier>} -- what a "diary" goal's
        area+tier is checked against (see DIARY_TIERS -- a higher
        completed tier also satisfies a lower-tier goal).
      - kc_counts: {(activityType, <lowercased source name>): count} --
        what a "kc" goal's activityType+sourceName+targetCount is
        checked against, built from this player's synced LootEvent rows
        (see app/loot.py).

    A goal that isn't fully filled in yet (a trackable node the player
    added but hasn't finished configuring -- see default_goal) is
    always just "not completed" rather than an error. The tree's root
    node is handled last, once every other node's own status is known:
    it's complete iff the tree has at least one other node and every
    one of them is (see GOAL_TYPE_BY_COLOR's "white" entry) -- an empty
    mindmap (just the root, nothing under it yet) is never itself
    "done"."""
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
                done = kc_counts.get(key, 0) >= target
        elif goal_type == "item":
            item_name, target = goal.get("itemName"), goal.get("targetQty")
            if item_name and target:
                ids = find_item_ids(item_name) or []
                owned = sum(owned_pool_by_id.get(i, 0) for i in ids)
                if not ids:
                    owned = owned_pool_by_name.get(_normalize_lookup_name(item_name), 0)
                done = owned >= target
        elif goal_type == "gp":
            target = goal.get("targetGp")
            done = bool(target) and gp_total >= target
        elif goal_type == "skill":
            skill, metric, target = goal.get("skill"), goal.get("metric"), goal.get("target")
            if skill and metric and target:
                # Both LVL and XP goals are actually checked against
                # xp, never the plugin-reported `level` stat -- that's
                # the player's real, 99-capped in-game level, which a
                # "virtual" level target (above MAX_SKILL_LEVEL's old
                # 99 cap -- see its own comment) could never reach no
                # matter how much xp they have. A level target is
                # converted to its own xp requirement via
                # _xp_for_level first, so it's really always an xp
                # comparison underneath either way.
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


def build_mindmaps_state(db: Session, player: Player, context: Optional[Dict] = None) -> Dict:
    """The combined state the Mindmaps page loads once (see
    render_mindmaps in app/pages.py) -- every one of the player's
    mindmaps, each with its full node list, ordered oldest-created
    first (matching how Purchase Goals orders gear setups). `context`
    (see evaluate_completion) is optional only so this stays easy to
    call from a quick script/test without a full goal context on hand
    -- every real caller in app/main.py always passes one (built by
    _build_goal_context there) so every node's `completed` flag is
    always real, not just defaulted false."""
    mindmaps = (
        db.query(MindMap)
        .filter(MindMap.player_id == player.id)
        .order_by(MindMap.created_at.asc())
        .all()
    )
    return {"mindmaps": [serialize_mindmap(m, context) for m in mindmaps]}

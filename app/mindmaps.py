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
import uuid
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import MindMap, Player

# The fixed palette a node's `color` can be -- deliberately a small,
# named set (not a free-form hex value) so the client can style each
# one with a real CSS class instead of trusting arbitrary color input,
# the same reasoning GearSetup's owned/not-owned/affordable border
# colors already follow. "gray" (panel-2, the site's own default box
# shade) is what every new node starts as; see mindmaps.css for what
# each name actually renders as.
NODE_COLORS = ["gray", "red", "orange", "yellow", "green", "blue", "purple", "white"]
DEFAULT_COLOR = "gray"
DEFAULT_TEXT = "New"
MAX_NODE_TEXT_LENGTH = 120
MAX_MINDMAP_NAME_LENGTH = 60


def _clean_text(text: Optional[str]) -> str:
    text = (text or "").strip()[:MAX_NODE_TEXT_LENGTH].strip()
    return text or DEFAULT_TEXT


def _clean_color(color: Optional[str]) -> str:
    return color if color in NODE_COLORS else DEFAULT_COLOR


def new_root_node(text: Optional[str] = None) -> Dict:
    """The single starting node a brand new mindmap is created with."""
    return {
        "id": str(uuid.uuid4()),
        "parentId": None,
        "text": _clean_text(text),
        "color": DEFAULT_COLOR,
        "order": 0.0,
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

    new_node = {
        "id": str(uuid.uuid4()),
        "text": _clean_text(text),
        "color": _clean_color(color),
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
    new_node = {
        "id": str(uuid.uuid4()),
        "text": _clean_text(text),
        "color": _clean_color(color),
        "parentId": primary_parent_id,
        "order": _next_child_order(nodes, primary_parent_id),
        "extraParentIds": parent_ids[1:],
    }
    return nodes + [new_node], new_node["id"]


def update_node(nodes: List[Dict], node_id: str, text: Optional[str] = None, color: Optional[str] = None) -> List[Dict]:
    """Returns a NEW node list with the given node's text and/or color
    replaced -- whichever of the two is not None. Raises ValueError if
    the node doesn't exist."""
    if _find(nodes, node_id) is None:
        raise ValueError("That node no longer exists.")
    updated = []
    for n in nodes:
        if n["id"] == node_id:
            n = dict(n)
            if text is not None:
                n["text"] = _clean_text(text)
            if color is not None:
                n["color"] = _clean_color(color)
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

    Every node's text/color is re-cleaned exactly like any other write
    path (see _clean_text/_clean_color) even though the snapshot was
    already valid once, since it's still untrusted input off the wire,
    not something this function can assume came from a real previous
    server response just because the client claims it did.

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
        new_node = {
            "id": n["id"],
            "parentId": n.get("parentId"),
            "text": _clean_text(n.get("text")),
            "color": _clean_color(n.get("color")),
            "order": float(n.get("order") or 0.0),
        }
        extra_parent_ids = n.get("extraParentIds")
        if extra_parent_ids:
            pruned = [pid for pid in extra_parent_ids if pid in id_set and pid != n["id"]]
            if pruned:
                new_node["extraParentIds"] = pruned
        cleaned.append(new_node)
    return cleaned


def serialize_mindmap(mindmap: MindMap) -> Dict:
    return {
        "id": str(mindmap.id),
        "name": mindmap.name,
        "createdAt": mindmap.created_at.isoformat() if mindmap.created_at else None,
        "nodes": mindmap.nodes,
    }


def build_mindmaps_state(db: Session, player: Player) -> Dict:
    """The combined state the Mindmaps page loads once (see
    render_mindmaps in app/pages.py) -- every one of the player's
    mindmaps, each with its full node list, ordered oldest-created
    first (matching how Purchase Goals orders gear setups)."""
    mindmaps = (
        db.query(MindMap)
        .filter(MindMap.player_id == player.id)
        .order_by(MindMap.created_at.asc())
        .all()
    )
    return {"mindmaps": [serialize_mindmap(m) for m in mindmaps]}

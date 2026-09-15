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
NODE_COLORS = ["gray", "gold", "red", "amber", "green", "blue", "white"]
DEFAULT_COLOR = "gray"
DEFAULT_TEXT = "New idea"
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


def add_node(
    nodes: List[Dict], relative_id: str, relation: str, text: Optional[str] = None, color: Optional[str] = None
) -> "tuple[List[Dict], str]":
    """Returns a NEW node list with one extra node inserted relative to
    an existing one (`relative_id`), per `relation`:

      - "child": a new child of the relative node, after its existing
        children (if any).
      - "sibling": a new node sharing the relative node's own parent,
        placed immediately after it. The relative node can't be the
        tree's root (a root has no parent to share a sibling under --
        see the single-root shape MindMap.nodes assumes throughout).
      - "parent": a new node takes over the relative node's exact spot
        (same parentId and order) among its current siblings, and the
        relative node becomes that new node's only child. If the
        relative node was the root, the new node simply becomes the
        new root.

    Returns (new_nodes, new_node_id) -- the caller (see
    add_mindmap_node in app/main.py) hands the id straight back to the
    client so it can select the just-created node without having to
    diff the old and new node lists itself.

    Raises ValueError (its message is safe to show the player as-is)
    on an unknown relation, a missing relative node, or a sibling
    requested for the root."""
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
        new_node["order"] = _order_after(nodes, relative)
        return nodes + [new_node], new_node["id"]

    if relation == "parent":
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
    delete_mindmap in app/main.py), not by deleting just this node."""
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
    return [n for n in nodes if n["id"] not in to_remove]


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

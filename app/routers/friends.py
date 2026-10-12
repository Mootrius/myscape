"""Friends: per-character friend requests and friendships (see Friendship in
app/models.py).

Everything is scoped to the session's *active* GameAccount, except the
notification poll, which is Account-wide so the header dot next to ACCOUNT
reflects requests to any of this login's characters (the account page's
character cards use the per-character breakdown).

Codes are the GameAccount.public_code also used for myscape.io/c/<code>. Every
path that sends a request creates a pending row the other side must accept.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth import (
    get_current_account_from_session,
    get_current_verified_game_account_from_session,
    get_optional_current_game_account_from_session,
)
from app.database import get_db
from app.limiter import limiter
from app.models import Account, Friendship, GameAccount, _utcnow
from app.public_profile import find_game_account_by_code, generate_public_code

router = APIRouter(prefix="/api/friends", tags=["friends"])

PENDING = "pending"
ACCEPTED = "accepted"

# Most open outgoing requests per character. Declining deletes the row, so
# without a cap a declined requester could keep re-asking. Complements the
# per-IP rate limit on POST /requests.
MAX_PENDING_OUTGOING = 25


class FriendRequestBody(BaseModel):
    code: str = Field(min_length=1, max_length=32)


def _name(game_account: GameAccount) -> str:
    return game_account.runescape_name or "Unknown"


def _between(db: Session, a_id: uuid.UUID, b_id: uuid.UUID) -> Optional[Friendship]:
    """The one Friendship row between two characters, whichever was the requester
    (a request in the opposite direction auto-accepts instead of creating a
    second).
    """
    return (
        db.query(Friendship)
        .filter(
            or_(
                (Friendship.requester_id == a_id) & (Friendship.addressee_id == b_id),
                (Friendship.requester_id == b_id) & (Friendship.addressee_id == a_id),
            )
        )
        .first()
    )


def _ensure_code(db: Session, game_account: GameAccount) -> str:
    """Safety net: every linked character should already have a code (set at link
    time, backfilled by the friendships migration).
    """
    if not game_account.public_code:
        game_account.public_code = generate_public_code(db)
        db.commit()
        db.refresh(game_account)
    return game_account.public_code


@router.get("")
def list_friends(
    db: Session = Depends(get_db),
    me: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """The account page's Friends section for the active character: its own code,
    incoming requests (newest first) and accepted friends (A-Z). Each friend's
    `code` is their *current* public_code, so it follows a reset.
    """
    if me.account_hash is None:
        # An empty, unlinked slot has no character to friend as; the account
        # page shows a link hint instead.
        return {"linked": False, "code": None, "friends": [], "incoming": []}
    code = _ensure_code(db, me)
    rows = (
        db.query(Friendship)
        .filter(or_(Friendship.requester_id == me.id, Friendship.addressee_id == me.id))
        .all()
    )
    friends = []
    incoming = []
    for row in rows:
        other = row.addressee if row.requester_id == me.id else row.requester
        if row.status == ACCEPTED:
            became_friends = row.responded_at or row.created_at
            friends.append({
                "id": str(row.id),
                "name": _name(other),
                "code": other.public_code,
                # Acceptance time, shown in the SINCE column.
                "since": became_friends.isoformat() if became_friends else None,
            })
        elif row.addressee_id == me.id:
            incoming.append({"id": str(row.id), "name": _name(other), "createdAt": row.created_at})
    friends.sort(key=lambda f: f["name"].lower())
    incoming.sort(key=lambda r: r["createdAt"] or _utcnow(), reverse=True)
    for r in incoming:
        r["createdAt"] = r["createdAt"].isoformat() if r["createdAt"] else None
    return {"linked": True, "code": code, "friends": friends, "incoming": incoming}


@router.get("/notifications")
def friend_notifications(
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_from_session),
):
    """Polled by every page header (the dot next to ACCOUNT) and the account
    page's character cards: waiting incoming requests, in total and per
    character. One grouped COUNT query, cheap enough to poll.
    """
    rows = (
        db.query(Friendship.addressee_id, func.count(Friendship.id))
        .join(GameAccount, GameAccount.id == Friendship.addressee_id)
        .filter(GameAccount.account_id == account.id, Friendship.status == PENDING)
        .group_by(Friendship.addressee_id)
        .all()
    )
    by_character = {str(ga_id): count for ga_id, count in rows}
    return {"total": sum(by_character.values()), "byCharacter": by_character}


@router.get("/status/{code}")
@limiter.limit("60/minute")
def friend_status(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    viewer: Optional[GameAccount] = Depends(get_optional_current_game_account_from_session),
):
    """What the 'send friend request' button on a profile page should do for the
    active character: anonymous / self / own (another character on the
    viewer's account) / friends / pending_out / pending_in / none.
    """
    target = find_game_account_by_code(db, code)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    if viewer is None:
        return {"state": "anonymous"}
    if target.id == viewer.id:
        return {"state": "self"}
    if target.account_id == viewer.account_id:
        return {"state": "own"}
    row = _between(db, viewer.id, target.id)
    if row is None:
        return {"state": "none"}
    if row.status == ACCEPTED:
        return {"state": "friends"}
    return {"state": "pending_out" if row.requester_id == viewer.id else "pending_in"}


@router.post("/requests")
@limiter.limit("20/minute")
def send_friend_request(
    payload: FriendRequestBody,
    request: Request,
    db: Session = Depends(get_db),
    me: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Both ways of adding a friend (code on the account page, or the profile
    page button) land here. Always a *request*, except that if the other
    character already asked, this accepts theirs.
    """
    if me.account_hash is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Link this character first.")
    target = find_game_account_by_code(db, payload.code)
    if target is None or target.account_hash is None:
        # Same answer as a real request ("If there is a character with that
        # code, a friend request has been sent."), so codes cannot be probed for
        # existence.
        return {"status": PENDING, "name": None}
    if target.id == me.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That's your own code.")
    if target.account_id == me.account_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That character is on your own account.")

    existing = _between(db, me.id, target.id)
    if existing is not None:
        if existing.status == ACCEPTED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"You're already friends with {_name(target)}.")
        if existing.requester_id == me.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"You've already sent {_name(target)} a request.")
        existing.status = ACCEPTED
        existing.responded_at = _utcnow()
        db.commit()
        return {"status": ACCEPTED, "name": _name(target)}

    open_requests = (
        db.query(func.count(Friendship.id))
        .filter(Friendship.requester_id == me.id, Friendship.status == PENDING)
        .scalar()
    )
    if open_requests >= MAX_PENDING_OUTGOING:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You have too many pending friend requests. Wait for some to be answered first.",
        )
    db.add(Friendship(requester_id=me.id, addressee_id=target.id, status=PENDING))
    db.commit()
    return {"status": PENDING, "name": _name(target)}


def _incoming_or_404(db: Session, me: GameAccount, request_id: uuid.UUID) -> Friendship:
    row = (
        db.query(Friendship)
        .filter(Friendship.id == request_id, Friendship.addressee_id == me.id, Friendship.status == PENDING)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friend request not found.")
    return row


@router.post("/requests/{request_id}/accept")
def accept_friend_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    me: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    row = _incoming_or_404(db, me, request_id)
    row.status = ACCEPTED
    row.responded_at = _utcnow()
    db.commit()
    return {"status": ACCEPTED}


@router.delete("/requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def decline_friend_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    me: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Silent decline: the row is deleted and the requester is not told."""
    row = _incoming_or_404(db, me, request_id)
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{friendship_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_friend(
    friendship_id: uuid.UUID,
    db: Session = Depends(get_db),
    me: GameAccount = Depends(get_current_verified_game_account_from_session),
):
    """Silent, immediate unfriend by either side; takes effect for both (the
    other side loses private overview access on next load).
    """
    row = (
        db.query(Friendship)
        .filter(
            Friendship.id == friendship_id,
            Friendship.status == ACCEPTED,
            or_(Friendship.requester_id == me.id, Friendship.addressee_id == me.id),
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friend not found.")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

"""Account-page endpoints that aren't specifically about linking an
OSRS character (app/routers/linking.py's own game-account endpoints)
or the login/password/email credentials flow (app/routers/auth.py).

Starts with just the Shared Links section -- every myscape.io/s/<code>
link (see SharedContent in app/models.py and app/sharing.py) created
from any of the signed-in Account's own GameAccounts, across every
app that can create one, with a way to revoke one early. Anything
else account-wide that doesn't fit either of those two more specific
routers belongs here too.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_account_from_session
from app.database import get_db
from app.models import Account, GameAccount, SharedContent
from app.pages import _SITE_URL
from app.schemas import SharedLinkSummary
from app.sharing import SHARE_CONTENT_TYPE_LABELS

router = APIRouter(prefix="/api/account", tags=["account"])


@router.get("/shared-links", response_model=List[SharedLinkSummary])
def list_shared_links(
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_from_session),
):
    """Every currently-valid share link created from any of the signed-
    in Account's own GameAccounts, newest first -- the account page's
    own Shared Links section, underneath its Linked Accounts list.
    Joins through GameAccount (rather than filtering SharedContent
    directly) the same way list_shared_links' own sibling,
    list_game_accounts in app/routers/linking.py, scopes everything to
    `account.id` -- a share has no account_id of its own, only a
    game_account_id, so this is the only way to prove ownership.

    Expired rows are left out entirely rather than shown as "expired"
    -- nothing useful to revoke once a link's already stopped working
    on its own (see SharedContent.is_valid), and the account page
    doesn't need its own row just to say so. is_valid is checked here
    in Python, after the query, rather than a second expires_at filter
    written into the query itself -- the same lazy, read-time-only
    convention find_valid_share in app/sharing.py already uses."""
    rows = (
        db.query(SharedContent, GameAccount.runescape_name)
        .join(GameAccount, SharedContent.game_account_id == GameAccount.id)
        .filter(GameAccount.account_id == account.id)
        .order_by(SharedContent.created_at.desc())
        .all()
    )
    return [
        SharedLinkSummary(
            id=share.id,
            code=share.code,
            url=f"{_SITE_URL}/s/{share.code}",
            content_type=share.content_type,
            content_type_label=SHARE_CONTENT_TYPE_LABELS.get(share.content_type, share.content_type),
            character_name=runescape_name,
            expires_at=share.expires_at,
        )
        for share, runescape_name in rows
        if share.is_valid
    ]


@router.delete("/shared-links/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shared_link(
    share_id: uuid.UUID,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_from_session),
):
    """Revokes one share link early -- the account page's own
    "DEACTIVATE" button. A plain delete (same as every other place
    this app revokes something early rather than waiting on its own
    expiry -- there's no separate "deactivated" state to land in, just
    gone, the same as delete_game_account in app/routers/linking.py
    doesn't leave a tombstone behind either). find_valid_share in
    app/sharing.py (what GET /s/{code} itself calls) already treats a
    missing row and an expired one identically, so there's nothing
    left for a visitor with the old link to see either way.

    Ownership is proven the same join-through-GameAccount way
    list_shared_links above does -- scoping straight to `account.id`
    rather than, say, trusting a share_id the client already has,
    since that alone says nothing about who created it."""
    share = (
        db.query(SharedContent)
        .join(GameAccount, SharedContent.game_account_id == GameAccount.id)
        .filter(SharedContent.id == share_id, GameAccount.account_id == account.id)
        .first()
    )
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found.")
    db.delete(share)
    db.commit()

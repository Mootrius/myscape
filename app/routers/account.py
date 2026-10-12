"""Account-page endpoints that are neither game-account linking
(app/routers/linking.py) nor credentials (app/routers/auth.py).

Currently the Shared Links section: every myscape.io/s/<code> link
(SharedContent in app/models.py, app/sharing.py) created from any of the
signed-in Account's GameAccounts, with early revocation.
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
    """Every currently-valid share link from any of the signed-in Account's
    GameAccounts, newest first (the Shared Links section under Linked
    Accounts). A share has only a game_account_id, so ownership is proven by
    joining through GameAccount to `account.id`, as list_game_accounts in
    app/routers/linking.py does.
    
    Expired rows are omitted (nothing to revoke). is_valid is checked in
    Python after the query, the lazy read-time convention of find_valid_share
    in app/sharing.py.
    """
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
    """Revokes one share link early (the "DEACTIVATE" button). A plain delete
    with no tombstone; find_valid_share (app/sharing.py, used by GET
    /s/{code}) treats a missing and an expired row identically.
    
    Ownership is proven by the join through GameAccount, as in
    list_shared_links; a share_id from the client proves nothing about who
    created it.
    """
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


@router.delete("/shared-links", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_shared_links(
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_from_session),
):
    """Revokes all of this Account's share links (the "DELETION" column header,
    armed with the same two clicks as DEACTIVATE; see delete_shared_link).
    Same ownership join as list_shared_links, without the id filter, and valid
    or not. Uses a subquery because Query.delete() cannot act through a joined
    table.
    """
    (
        db.query(SharedContent)
        .filter(
            SharedContent.game_account_id.in_(
                db.query(GameAccount.id).filter(GameAccount.account_id == account.id)
            )
        )
        .delete(synchronize_session=False)
    )
    db.commit()

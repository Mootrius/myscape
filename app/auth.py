"""Dependency for authenticating requests from the RuneLite plugin.

Every request the plugin makes after linking carries its API key in a
standard `Authorization: Bearer <key>` header. We hash whatever comes in
and look up the match -- the raw key is never stored, so this is the
only way to check it.
"""
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Player, PlayerApiKey
from app.security import hash_token


def get_current_player(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> Player:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header (expected 'Bearer <api key>').",
        )
    raw_key = authorization[len("bearer "):].strip()
    if not raw_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty API key.")

    key_hash = hash_token(raw_key)
    api_key = (
        db.query(PlayerApiKey)
        .filter(PlayerApiKey.key_hash == key_hash, PlayerApiKey.revoked_at.is_(None))
        .first()
    )
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key.")

    api_key.last_used_at = datetime.now(timezone.utc)
    db.commit()

    return api_key.player

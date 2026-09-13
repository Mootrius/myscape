"""SQLAlchemy models.

Just enough to prove the database round-trip end to end for the first
deploy -- one Player row per myscape account. Purchase Goals / Loot
Tracker data model comes later, once this is live and the RuneLite
plugin exists to send it.

Account linking (how a RuneLite plugin install proves which website
account it belongs to) follows the same pattern Wise Old Man and similar
sites use: the website generates a random verification_code for the
player, the player pastes that code into the plugin's config panel, and
every request the plugin sends includes it -- the server never trusts a
client-asserted username on its own.
"""
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


def _generate_verification_code():
    # 24 hex chars (96 bits) -- long enough to not be guessable, short
    # enough to paste into a plugin config field without misery.
    return secrets.token_hex(12)


class Player(Base):
    __tablename__ = "players"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The player's OSRS display name, as reported by the RuneLite plugin
    # once it's linked -- nullable because an account can exist (e.g. just
    # signed up on the website) before it's ever linked to a plugin.
    runescape_name = Column(String, nullable=True, unique=True)
    email = Column(String, nullable=True, unique=True)
    verification_code = Column(String, nullable=False, unique=True, default=_generate_verification_code)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

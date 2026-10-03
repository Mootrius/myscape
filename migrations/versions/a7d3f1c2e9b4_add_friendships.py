"""add friendships table, backfill public codes for linked characters

Revision ID: a7d3f1c2e9b4
Revises: b525638f94c7
Create Date: 2026-10-03 12:00:00.000000

"""
import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'a7d3f1c2e9b4'
down_revision: Union[str, Sequence[str], None] = 'b525638f94c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """friendships -- one row per friend request/friendship between two
    GameAccounts (see Friendship's own docstring in app/models.py).

    Also gives every already-linked character that doesn't have a
    public_code yet one -- the friends feature reuses that same code as
    its friend code, and from now on every character gets one when it's
    linked (see exchange_link_code in app/routers/linking.py), so this
    just catches up the characters linked before that. is_public_profile
    stays at its default (private) and public_code_regenerated_at stays
    NULL, so nobody is exposed or throttled by this backfill."""
    op.create_table(
        "friendships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("requester_id", UUID(as_uuid=True), sa.ForeignKey("game_accounts.id"), nullable=False),
        sa.Column("addressee_id", UUID(as_uuid=True), sa.ForeignKey("game_accounts.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("requester_id", "addressee_id", name="uq_friendships_pair"),
    )
    op.create_index("ix_friendships_requester_id", "friendships", ["requester_id"])
    op.create_index("ix_friendships_addressee_id", "friendships", ["addressee_id"])

    # Backfill friend codes for already-linked characters.
    from app.public_profile import CODE_ALPHABET, CODE_LENGTH, _contains_blocked_word

    bind = op.get_bind()
    needs_code = [
        row[0]
        for row in bind.execute(
            sa.text("SELECT id FROM game_accounts WHERE account_hash IS NOT NULL AND public_code IS NULL")
        ).fetchall()
    ]
    taken = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT public_code FROM game_accounts WHERE public_code IS NOT NULL")
        ).fetchall()
    }
    for game_account_id in needs_code:
        for _ in range(500):
            candidate = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if candidate in taken or _contains_blocked_word(candidate):
                continue
            taken.add(candidate)
            bind.execute(
                sa.text("UPDATE game_accounts SET public_code = :code WHERE id = :id"),
                {"code": candidate, "id": game_account_id},
            )
            break
        else:
            raise RuntimeError("Could not generate a unique friend code during backfill.")


def downgrade() -> None:
    # The backfilled public_codes are deliberately left in place --
    # they're just a code on a still-private profile, harmless without
    # this table, and indistinguishable from codes set any other way.
    op.drop_index("ix_friendships_addressee_id", table_name="friendships")
    op.drop_index("ix_friendships_requester_id", table_name="friendships")
    op.drop_table("friendships")

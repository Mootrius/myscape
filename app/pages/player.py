"""The PlayerView passed to every page renderer, and how it is built from an Account and its GameAccount."""
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.models import Account, GameAccount


@dataclass
class PlayerView:
    """The combined identity + game-data view every render_* function takes,
    built per request by build_player_view from an Account and its active
    GameAccount (docs/multi-account-scoping.md). Pages never query models.
    """

    id: uuid.UUID
    email: Optional[str]
    email_verified_at: Optional[datetime]
    runescape_name: Optional[str]
    account_hash: Optional[str]
    # Hiscores snapshot (see app/hiscores.py). An empty dict means "never
    # synced"; every boss synced at least once is a key, 0 or otherwise.
    boss_kill_counts: dict
    hiscores_synced_at: Optional[datetime]


def build_player_view(account: "Account", game_account: Optional["GameAccount"]) -> PlayerView:
    """Combine an Account with its (possibly absent) active GameAccount: identity
    fields from the Account, game-data fields from the GameAccount.
    """
    return PlayerView(
        id=account.id,
        email=account.email,
        email_verified_at=account.email_verified_at,
        runescape_name=game_account.runescape_name if game_account else None,
        account_hash=game_account.account_hash if game_account else None,
        boss_kill_counts=dict(game_account.boss_kill_counts or {}) if game_account else {},
        hiscores_synced_at=game_account.hiscores_synced_at if game_account else None,
    )

"""Builders shared by several routers (payloads for the Character Overview, skills and collection log; name helpers)."""
from app.bosses import collection_log_page_kill_counts
from app.character_progress_data import (
    get_ca_tier_totals,
    get_diary_tier_totals,
    get_quest_list,
)
from app.collectionlog import get_collection_log_tabs
from app.mindmaps import (
    DIARY_TIERS,
    _normalize_lookup_name,
)
from app.models import GameAccount


def _skills_payload(game_account: GameAccount) -> dict:
    """Factored out of read_skills so both share one payload builder (like
    _character_overview_summary_payload).
    """
    return {"skills": game_account.skills or {}}


def _collection_log_payload(game_account: GameAccount) -> dict:
    """Factored out of read_collection_log so both share one payload builder."""
    return {
        "tabs": get_collection_log_tabs(),
        "obtainedItems": game_account.collection_log_items or {},
        "syncedAt": game_account.collection_log_synced_at.isoformat() if game_account.collection_log_synced_at else None,
        # Page name -> kill/completion counts (several for combo pages or raid
        # modes). {} if hiscores were never synced.
        "killCounts": collection_log_page_kill_counts(
            game_account.boss_kill_counts or {},
            game_account.clue_scroll_counts or {},
        ),
    }


def _diary_progress_rows(game_account: GameAccount) -> list[dict]:
    """One entry per diary area with completed/total TASK counts and per-tier
    state; shared by the progress payload and the summary tile so they agree.

    Completed tasks come from the plugin's per-tier task counts
    (GameAccount.diary_task_counts) when it has sent any, so partly finished
    tiers show their progress. Otherwise (older plugin versions) every task in
    a tier up to the highest completed one counts, with no partial progress.
    """
    diary_totals = get_diary_tier_totals()
    account_diary_tiers = game_account.diary_tiers or {}
    account_task_counts = game_account.diary_task_counts or {}
    diaries = []
    for area, tier_totals in diary_totals.items():
        highest = account_diary_tiers.get(area)
        highest_index = DIARY_TIERS.index(highest) if highest in DIARY_TIERS else -1
        if account_task_counts:
            area_counts = account_task_counts.get(area) or {}
            # Clamped to the tier's task total so a count the game reports
            # differently from the wiki can never push a row past 100%.
            completed = sum(
                min(max(int(area_counts.get(t) or 0), 0), tier_totals[t])
                for t in DIARY_TIERS
                if t in tier_totals
            )
        else:
            completed = sum(tier_totals[t] for i, t in enumerate(DIARY_TIERS) if i <= highest_index and t in tier_totals)
        total = sum(tier_totals.values())
        tiers = {
            t: ("completed" if i <= highest_index else "not_completed")
            for i, t in enumerate(DIARY_TIERS)
        }
        diaries.append({"area": area, "completed": completed, "total": total, "tiers": tiers})
    return diaries


def _achievement_diary_tile_counts(game_account: GameAccount) -> tuple:
    """(completed, total) in TASKS for the Achievement Diaries tile. The in-game
    figure can be a tier count (e.g. 36/48), so it is computed from the synced
    task counts, or diary_tiers for plugin versions that send only those.
    """
    if game_account.diary_task_counts or game_account.diary_tiers:
        rows = _diary_progress_rows(game_account)
        return sum(r["completed"] for r in rows), sum(r["total"] for r in rows)
    return (
        game_account.character_summary_achievements_completed,
        game_account.character_summary_achievements_total,
    )


def _combat_tasks_tile_total(game_account: GameAccount):
    """Total for the Combat Achievements tile. The in-game total varies between
    accounts (632 vs 655), so fixed per-tier totals are used once a completed
    count has synced.
    """
    if game_account.character_summary_combat_tasks_completed is None:
        return game_account.character_summary_combat_tasks_total
    return sum(get_ca_tier_totals().values())


def _character_overview_summary_payload(game_account: GameAccount) -> dict:
    """The summary-row payload, shared with the public counterpart.
    modelViewerBackgroundIndex rides along so public viewers and other devices
    pick up the background.
    """
    achievements_completed, achievements_total = _achievement_diary_tile_counts(game_account)
    return {
        "combatLevel": game_account.character_summary_combat_level,
        "totalLevel": game_account.character_summary_total_level,
        "totalXp": game_account.character_summary_total_xp,
        "questsCompleted": game_account.character_summary_quests_completed,
        "questsTotal": game_account.character_summary_quests_total,
        "achievementsCompleted": achievements_completed,
        "achievementsTotal": achievements_total,
        "combatTasksCompleted": game_account.character_summary_combat_tasks_completed,
        "combatTasksTotal": _combat_tasks_tile_total(game_account),
        "collectionsCompleted": game_account.character_summary_collections_completed,
        "collectionsTotal": game_account.character_summary_collections_total,
        "accountType": game_account.account_type,
        "modelViewerBackgroundIndex": game_account.model_viewer_background_index,
        "syncedAt": game_account.character_summary_synced_at.isoformat() if game_account.character_summary_synced_at else None,
    }


def _character_overview_progress_payload(game_account: GameAccount) -> dict:
    """The quests/diaries/combat-achievements payload, shared by the session and
    public endpoints. Quest names are matched case-insensitively (RuneLite and
    wiki names differ in case). diary_tiers stores only the highest completed
    tier, so lower tiers count as completed and there is no partial progress.
    Combat achievements give a completed count per tier (null if never synced)
    and the fixed total.
    """
    quest_list = get_quest_list()
    completed_lookup = {_normalize_lookup_name(n) for n in (game_account.completed_quests or [])}
    in_progress_lookup = {_normalize_lookup_name(n) for n in (game_account.in_progress_quests or [])}

    def quest_state(name: str) -> str:
        normalized = _normalize_lookup_name(name)
        if normalized in completed_lookup:
            return "completed"
        if normalized in in_progress_lookup:
            return "in_progress"
        return "not_started"

    quests = {
        group: [{"name": name, "state": quest_state(name)} for name in names]
        for group, names in quest_list.items()
    }

    diaries = _diary_progress_rows(game_account)

    ca_totals = get_ca_tier_totals()
    ca_completed = game_account.character_summary_combat_task_tier_completed
    combat_achievements = [
        {
            "tier": tier,
            "completed": (ca_completed or {}).get(tier) if ca_completed is not None else None,
            "total": total,
        }
        for tier, total in ca_totals.items()
    ]

    return {"quests": quests, "diaries": diaries, "combatAchievements": combat_achievements}


def _duplicate_name(name: str) -> str:
    """"<name> (copy)", with the base trimmed to fit the 60-character name limit
    so the "(copy)" marker always survives.
    """
    suffix = " (copy)"
    base = (name or "").strip()
    if len(base) + len(suffix) > 60:
        base = base[: 60 - len(suffix)].rstrip()
    return base + suffix

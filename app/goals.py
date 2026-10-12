"""Goal Tracking's own goal list: a flat set of targets (boss kill count, skill
level/xp, item quantity) with progress computed live on each read, never
stored. Not built on app/mindmaps.py's tree-shaped goals;
gp/quest/diary/manual goals stay Mindmaps-only.
Skill goals reuse app.mindmaps' xp machinery so level and xp targets stay
comparable; item goals reuse app.purchase_goals.build_owned_pools plus
app.item_ids.find_item_ids and app.mindmaps._offhand_pair_name.
kc goals read game_account.boss_kill_counts (hiscores-seeded, kept live from
chat; app/hiscores.py), not Mindmaps' LootEvent-based count, which misses
kills made before the plugin. Hence only app.bosses.HISCORE_BOSSES are
offered.
"""
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy.orm import Session

from app.bosses import HISCORE_BOSSES
from app.item_ids import find_item_ids
from app.models import Goal, _utcnow
from app.mindmaps import (
    MAX_SKILL_LEVEL,
    MAX_SKILL_XP,
    MIN_SKILL_LEVEL,
    MIN_SKILL_XP,
    SKILL_NAMES,
    SKILL_XP_TABLE,
    _clean_int_in_range,
    _normalize_lookup_name,
    _offhand_pair_name,
    _xp_for_level,
)
from app.purchase_goals import build_owned_pools

if TYPE_CHECKING:
    from app.models import GameAccount

GOAL_TYPES = ("kc", "skill", "item")
SKILL_METRICS = ("level", "xp")
MAX_ITEM_NAME_LENGTH = 80
# kc/item target ceiling (INT32_MAX), separate from app.mindmaps' limits, which
# bound a different number.
MAX_KC_TARGET = 2_147_483_647
MAX_ITEM_QTY_TARGET = 2_147_483_647

# Recurring cadence units ("every recur_interval recur_unit"): fixed durations
# (MONTH = 30 days, YEAR = 365). Order is the display order in the wizard
# (wizardStageCadenceHtml, app/pages.py).
RECUR_UNITS = ("hour", "day", "week", "month", "year")
_RECUR_UNIT_SECONDS = {"hour": 3600, "day": 86400, "week": 7 * 86400, "month": 30 * 86400, "year": 365 * 86400}
MAX_RECUR_INTERVAL = 999
# Recurring is offered only for kc/skill: an item goal's progress is a live
# quantity, not a monotonic total, so "gained since the last period" is
# meaningless for it.
RECURRING_GOAL_TYPES = ("kc", "skill")

# What a one-time goal's target_value means (see Goal.baseline_value in
# app/models.py): "reach" (default) is a lifetime total; "gain" baselines at
# creation, so target_value is "how much MORE". Recurring goals have no choice;
# their period baseline is already "gain".
GOAL_TARGET_MODES = ("reach", "gain")


def target_mode_allows_gain(goal_type: str, metric: Optional[str], is_recurring: bool) -> bool:
    """Whether a one-time goal can use "gain" mode: kc or an xp-metric skill
    goal, not recurring. Level-metric skill goals have no "gain N levels"
    reading (xp per level is nonlinear), and item goals are not monotonic (see
    RECURRING_GOAL_TYPES).
    """
    if is_recurring:
        return False
    if goal_type == "kc":
        return True
    if goal_type == "skill":
        return metric == "xp"
    return False


def clean_target_mode(goal_type: str, metric: Optional[str], is_recurring: bool, target_mode) -> str:
    """Validates a new goal's gain/reach choice against the already-cleaned
    goal_type/metric/is_recurring (target_mode is not a Goal column; see
    create_goal in app/main.py). None defaults to "reach" so raw API calls
    keep the absolute reading. "gain" raises GoalValidationError where
    target_mode_allows_gain is False.
    """
    mode = target_mode or "reach"
    if mode not in GOAL_TARGET_MODES:
        raise GoalValidationError(f"target_mode must be one of {GOAL_TARGET_MODES}.")
    if mode == "gain" and not target_mode_allows_gain(goal_type, metric, is_recurring):
        raise GoalValidationError("Gain mode is only available for a one-time kc goal or a one-time xp-metric skill goal.")
    return mode


# HISCORE_BOSSES display names keyed lowercase, so any casing resolves.
_BOSS_NAME_BY_LOWER = {name.lower(): name for _slug, name, _has_icon in HISCORE_BOSSES}


class GoalValidationError(ValueError):
    """Raised with a message safe to show the player as-is."""


def clean_new_goal(
    goal_type: str,
    target_name: str,
    metric: Optional[str],
    target_value,
    item_id=None,
    is_recurring=False,
    recur_interval=None,
    recur_unit: Optional[str] = None,
) -> dict:
    """Validates a goal-creation request into the Goal(**cleaned) fields.
    recur_period_start/baseline_value are set by create_goal in app/main.py.
    Raises GoalValidationError. Wraps _clean_new_goal so _clean_int_in_range's
    ValueError becomes a 400 instead of a 500.
    """
    try:
        return _clean_new_goal(goal_type, target_name, metric, target_value, item_id, is_recurring, recur_interval, recur_unit)
    except GoalValidationError:
        raise
    except ValueError as exc:
        raise GoalValidationError(str(exc)) from exc


def _clean_new_goal(
    goal_type: str,
    target_name: str,
    metric: Optional[str],
    target_value,
    item_id,
    is_recurring,
    recur_interval,
    recur_unit,
) -> dict:
    if goal_type not in GOAL_TYPES:
        raise GoalValidationError(f"goal_type must be one of {GOAL_TYPES}.")

    is_recurring = bool(is_recurring)
    if is_recurring and goal_type not in RECURRING_GOAL_TYPES:
        raise GoalValidationError(f"Recurring goals are only available for {RECURRING_GOAL_TYPES}.")

    clean_recur_interval = None
    clean_recur_unit = None
    if is_recurring:
        if recur_unit not in RECUR_UNITS:
            raise GoalValidationError(f"recur_unit must be one of {RECUR_UNITS}.")
        clean_recur_interval = _clean_int_in_range(recur_interval, "recur_interval", 1, MAX_RECUR_INTERVAL)
        clean_recur_unit = recur_unit
    recurrence = {"is_recurring": is_recurring, "recur_interval": clean_recur_interval, "recur_unit": clean_recur_unit}

    if goal_type == "kc":
        display_name = _BOSS_NAME_BY_LOWER.get((target_name or "").strip().lower())
        if display_name is None:
            raise GoalValidationError("Pick a real OSRS hiscores boss.")
        value = _clean_int_in_range(target_value, "target_value", 1, MAX_KC_TARGET)
        return {"goal_type": "kc", "target_name": display_name, "metric": None, "target_value": value, "item_id": None, **recurrence}

    if goal_type == "skill":
        skill = (target_name or "").strip().lower()
        if skill not in SKILL_NAMES:
            raise GoalValidationError(f"skill must be one of {sorted(SKILL_NAMES)}.")
        if metric not in SKILL_METRICS:
            raise GoalValidationError("metric must be 'level' or 'xp'.")
        # A recurring skill goal tracks xp only (a level is a capped ceiling);
        # the wizard hides the metric toggle for it, so this only fires for
        # requests bypassing the UI.
        if is_recurring and metric != "xp":
            raise GoalValidationError("Recurring skill goals only track experience.")
        bounds = (MIN_SKILL_XP, MAX_SKILL_XP) if metric == "xp" else (MIN_SKILL_LEVEL, MAX_SKILL_LEVEL)
        value = _clean_int_in_range(target_value, "target_value", *bounds)
        return {"goal_type": "skill", "target_name": skill, "metric": metric, "target_value": value, "item_id": None, **recurrence}

    # item: free text, since an unresolved name can still match
    # build_owned_pools' name-keyed pool (see absolute_value).
    name = (target_name or "").strip()[:MAX_ITEM_NAME_LENGTH]
    if not name:
        raise GoalValidationError("Pick an item.")
    value = _clean_int_in_range(target_value, "target_value", 1, MAX_ITEM_QTY_TARGET)
    # item_id is only a display hint (Goal.item_id in app/models.py); loosely
    # checked, never required.
    clean_item_id = None
    if item_id is not None:
        try:
            candidate = int(item_id)
            if candidate > 0:
                clean_item_id = candidate
        except (TypeError, ValueError):
            pass
    return {"goal_type": "item", "target_name": name, "metric": None, "target_value": value, "item_id": clean_item_id, **recurrence}


def build_progress_context(db, game_account) -> dict:
    """Everything current_value needs, fetched once per request rather than per
    goal.
    """
    owned_pool_by_id, owned_pool_by_name = build_owned_pools(db, game_account)
    return {
        "boss_kill_counts": game_account.boss_kill_counts or {},
        "skills": game_account.skills or {},
        "owned_pool_by_id": owned_pool_by_id,
        "owned_pool_by_name": owned_pool_by_name,
    }


def current_value(goal, context: dict) -> int:
    """Live progress toward target_value, in its unit: absolute_value(), minus
    goal.baseline_value when one exists (recurring period start, or a one-time
    gain goal's creation; see Goal.baseline_value in app/models.py). Call
    maybe_roll_recurring_period first, as list_goals does. Clamped at 0
    against hiscores glitches.
    """
    absolute = absolute_value(goal, context)
    if goal.baseline_value is None:
        return absolute
    return max(0, absolute - goal.baseline_value)


def progress_pct(goal, context: dict) -> float:
    """Progress bar fill, 0-100: current_value()/target_value, except for
    level-metric skill goals, where levels are a nonlinear stand-in for
    effort; those are scored as live xp over _xp_for_level(target_value).
    Level-metric goals are never recurring, so no baseline applies.
    """
    if goal.goal_type == "skill" and goal.metric == "level":
        have_xp = (context["skills"].get(goal.target_name) or {}).get("xp", 0)
        need_xp = _xp_for_level(goal.target_value)
        if need_xp <= 0:
            return 100.0
        return max(0.0, min(100.0, (have_xp / need_xp) * 100))
    if goal.target_value <= 0:
        return 0.0
    return max(0.0, min(100.0, (current_value(goal, context) / goal.target_value) * 100))


def absolute_value(goal, context: dict) -> int:
    """The goal's live lifetime number in target_value's unit (kills; xp, or
    level for level-metric skill goals; owned quantity), derived from
    `context` and never stored. current_value applies any baseline;
    create_goal and maybe_roll_recurring_period use this to capture one.
    """
    if goal.goal_type == "kc":
        kc = context["boss_kill_counts"].get(goal.target_name)
        return kc if isinstance(kc, int) else 0

    if goal.goal_type == "skill":
        have_xp = (context["skills"].get(goal.target_name) or {}).get("xp", 0)
        if goal.metric == "xp":
            return have_xp
        # Level goals compare as xp internally (virtual levels above 99) but
        # report the level that xp reaches.
        return _level_for_xp(have_xp)

    # item
    names = _item_name_variants(goal.target_name)
    ids = [i for n in names for i in (find_item_ids(n) or [])]
    if ids:
        return sum(context["owned_pool_by_id"].get(i, 0) for i in ids)
    return sum(context["owned_pool_by_name"].get(_normalize_lookup_name(n), 0) for n in names)


def maybe_roll_recurring_period(goal, context: dict) -> bool:
    """Advances a recurring goal to the period containing `now` and re-baselines
    it; list_goals (app/main.py) calls this before current_value. Returns True
    if anything changed. Only a live snapshot exists, so skipped periods are
    not reconstructed: the period start fast-forwards and the baseline is the
    current value.
    """
    if not goal.is_recurring or not goal.recur_period_start or not goal.recur_interval or not goal.recur_unit:
        return False
    period_seconds = goal.recur_interval * _RECUR_UNIT_SECONDS[goal.recur_unit]
    if period_seconds <= 0:
        return False
    elapsed = (_utcnow() - goal.recur_period_start).total_seconds()
    if elapsed < period_seconds:
        return False
    periods_elapsed = int(elapsed // period_seconds)
    goal.recur_period_start = goal.recur_period_start + timedelta(seconds=periods_elapsed * period_seconds)
    goal.baseline_value = absolute_value(goal, context)
    return True


def _item_name_variants(item_name: str) -> List[str]:
    """item_name plus its off-hand pair, matching evaluate_completion's item
    branch in app.mindmaps.
    """
    names = [item_name]
    pair_name = _offhand_pair_name(item_name)
    if pair_name and pair_name.lower() != item_name.strip().lower():
        names.append(pair_name)
    return names


def _level_for_xp(xp: int) -> int:
    """Inverse of app.mindmaps._xp_for_level: the highest level (1-126) this xp
    reaches. Linear scan over the small table.
    """
    level = MIN_SKILL_LEVEL
    for candidate in range(MIN_SKILL_LEVEL, MAX_SKILL_LEVEL + 1):
        if SKILL_XP_TABLE[candidate] <= xp:
            level = candidate
        else:
            break
    return level


def target_display(goal) -> str:
    """Target label with unit for the UI: "80" for a level goal, "13,034,431 xp"
    for xp; kc/item need no suffix.
    """
    if goal.goal_type == "skill" and goal.metric == "xp":
        return f"{goal.target_value:,} xp"
    return f"{goal.target_value:,}"



def import_goals_from_share_payload(db: Session, game_account: "GameAccount", payload: dict) -> List[Goal]:
    """The reverse of build_goal_tracking_share_snapshot (app/main.py): creates
    an editable Goal for every goal in a Goal Tracking share's frozen payload
    (POST /api/goals/shares/{code}/import). Only the definition fields of each
    payload["goals"] entry are read; the rest is the sharer's frozen reading.
    Only the presence of baseline_value is used (the number is the sharer's);
    dropping it would turn a gain goal into reach. A fresh baseline is
    captured from this account's absolute_value(), as create_goal does.
    Recurring goals always get one, starting now. The caller commits.
    """
    context = build_progress_context(db, game_account)
    new_goals: List[Goal] = []
    for entry in payload.get("goals") or []:
        goal = Goal(
            # Explicit id, as in import_mindmap_from_share_payload, since the
            # column default applies only at flush.
            id=uuid.uuid4(),
            game_account_id=game_account.id,
            goal_type=entry["goal_type"],
            target_name=entry["target_name"],
            metric=entry.get("metric"),
            target_value=entry["target_value"],
            item_id=entry.get("item_id"),
            is_recurring=bool(entry.get("is_recurring")),
            recur_interval=entry.get("recur_interval"),
            recur_unit=entry.get("recur_unit"),
        )
        if goal.is_recurring:
            goal.recur_period_start = _utcnow()
            goal.baseline_value = absolute_value(goal, context)
        elif entry.get("baseline_value") is not None:
            # A one-time gain-mode goal in the sharer's list (only baseline
            # presence is used).
            goal.baseline_value = absolute_value(goal, context)
        db.add(goal)
        new_goals.append(goal)
    return new_goals

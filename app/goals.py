"""Goal Tracking's own goal list -- a flat set of targets (a boss kill
count, a skill level/xp, or an item quantity), each with live progress
computed fresh on every read, never stored. Deliberately NOT built on
app/mindmaps.py's tree-shaped goal nodes, even though mindmaps.py
already implements six goal types (kc/item/gp/skill/quest/diary, plus
a manual one): those live inside a mind map's own tree, one node among
possibly many unrelated ones, when what this page wants is a plain,
purpose-built list of exactly the targets a player is actively working
toward -- and only the three goal types this page actually offers;
gp/quest/diary/manual goals stay a Mindmaps-only feature for now.

Where the underlying logic already exists correctly elsewhere, this
reuses it rather than re-deriving it:
- skill goals: app.mindmaps' own xp-conversion machinery (SKILL_NAMES,
  SKILL_XP_TABLE/_xp_for_level/_clean_int_in_range) -- a level target
  and an xp target need to stay comparable the exact same way
  Mindmaps' own skill goals already do.
- item goals: app.purchase_goals.build_owned_pools (the same "how much
  of this item does this account actually own, summed across every
  storage" helper Purchase Goals and Mindmaps' own item goals both
  already use) plus app.item_ids.find_item_ids and
  app.mindmaps._offhand_pair_name for name -> id resolution, including
  the same off-hand-pair handling Mindmaps' item goals already give
  (an "Imcando hammer" goal is satisfied by either the plain or
  off-hand variant).

kc (boss kill count) goals are the one type NOT borrowed from
app.mindmaps: Mindmaps' own "kc" goal type counts raw LootEvent
occurrences (kc_counts_by_player in app/loot.py) -- "kills the loot
tracker has actually witnessed," not a real lifetime total, which
undercounts anyone who had real kills before ever installing the
plugin or turning loot tracking on. A boss goal here tracks toward the
REAL lifetime number instead, so it reads game_account.boss_kill_counts
directly -- the same hiscores-seeded, chatbox-kept-live column Goal
Tracking already displayed before this redesign (see app/hiscores.py).
That's also why this only offers the ~70 real OSRS-hiscores bosses
(app.bosses.HISCORE_BOSSES) rather than any NPC name a player could
type the way Mindmaps' own kc goal allows -- boss_kill_counts only
ever has an entry for those.
"""
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from app.bosses import HISCORE_BOSSES
from app.item_ids import find_item_ids
from app.models import _utcnow
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
)
from app.purchase_goals import build_owned_pools

GOAL_TYPES = ("kc", "skill", "item")
SKILL_METRICS = ("level", "xp")
MAX_ITEM_NAME_LENGTH = 80
# Goal Tracking's own kc/item target ceiling -- INT32_MAX, the widest
# a signed 32-bit integer column can hold. Deliberately NOT
# app.mindmaps' own MAX_KC_TARGET/MAX_ITEM_QTY_TARGET: Mindmaps' kc
# goal counts a completely different, much smaller number (loot-
# tracker-witnessed kills -- see this file's own top docstring on why
# Goal Tracking's kc goal was never borrowed from Mindmaps to begin
# with), so tying Goal Tracking's own ceiling to a constant that
# exists for that unrelated purpose would just be an accident waiting
# to diverge later.
MAX_KC_TARGET = 2_147_483_647
MAX_ITEM_QTY_TARGET = 2_147_483_647

# A recurring goal's own cadence -- "every recur_interval recur_unit"
# (e.g. every 2 WEEK). Fixed-duration units, not calendar-exact ones:
# MONTH is always 30 days and YEAR always 365, the same "fixed
# lookback" convention app/loot.py's own range presets already use,
# rather than pulling in real calendar month/year arithmetic for a
# cadence that's already just an approximate repeat interval. Order
# here is display order too -- the wizard's own segmented control
# (see wizardStageCadenceHtml in app/pages.py) renders these in this
# exact sequence.
RECUR_UNITS = ("hour", "day", "week", "month", "year")
_RECUR_UNIT_SECONDS = {"hour": 3600, "day": 86400, "week": 7 * 86400, "month": 30 * 86400, "year": 365 * 86400}
# A generous cap on "every how many" -- "every 999 YEAR" is already
# absurd, this just keeps the field (and the column) bounded rather
# than genuinely limiting anyone's real use of it.
MAX_RECUR_INTERVAL = 999
# Recurring is only offered for "kc"/"skill" in the wizard (see
# wizardStageTypeHtml) -- an "item" goal's own progress is a live owned
# quantity, not a monotonic lifetime total, so "gained since the last
# period" (see maybe_roll_recurring_period) wouldn't mean the same
# thing for it the way it does for a kc/xp/level count that only ever
# goes up.
RECURRING_GOAL_TYPES = ("kc", "skill")

# app.bosses.HISCORE_BOSSES' display names, keyed lowercase, so a goal
# submitted with any casing still resolves -- the real UI always
# submits one of these names verbatim (see the <select> in
# render_goal_tracking), so this leniency only ever matters against a
# raw/direct API call, same spirit as HISCORES_NAME_TO_DISPLAY_NAME's
# own case handling in app/bosses.py.
_BOSS_NAME_BY_LOWER = {name.lower(): name for _slug, name, _has_icon in HISCORE_BOSSES}


class GoalValidationError(ValueError):
    """Raised with a message safe to show the player as-is -- same
    convention app.mindmaps' own clean_goal already follows."""


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
    """Validates and normalizes a goal-creation request into
    {"goal_type", "target_name", "metric", "target_value", "item_id",
    "is_recurring", "recur_interval", "recur_unit"}, ready to write
    straight onto a new Goal row (recur_period_start/
    recur_baseline_value aren't part of this -- see create_goal in
    app/main.py, which sets both from live progress context this
    function has no access to). Raises GoalValidationError naming
    whatever's wrong -- mirrors app.mindmaps.clean_goal's own per-field
    validation, just flattened to one goal per call (no node/color
    dispatch, since this feature has no tree of its own).

    Thin wrapper around _clean_new_goal below: _clean_int_in_range
    (borrowed from app.mindmaps for the target_value bound-check every
    branch does) raises a plain ValueError, not GoalValidationError --
    every OTHER validation failure below already raises
    GoalValidationError directly, so without this the API layer's own
    `except GoalValidationError` (app/main.py's create_goal) would let
    an out-of-range target_value fall through uncaught into a bare 500
    instead of the same clean 400 every other bad field already gets.
    str(exc) is just as safe to show the player either way --
    _clean_int_in_range's own messages never include anything but the
    field name and the bound that failed."""
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
        bounds = (MIN_SKILL_XP, MAX_SKILL_XP) if metric == "xp" else (MIN_SKILL_LEVEL, MAX_SKILL_LEVEL)
        value = _clean_int_in_range(target_value, "target_value", *bounds)
        return {"goal_type": "skill", "target_name": skill, "metric": metric, "target_value": value, "item_id": None, **recurrence}

    # item -- free text, not pre-validated against a real item the way
    # kc/skill are against their own closed vocabularies, same
    # tolerance app.mindmaps' own item goal gives: a name that doesn't
    # resolve to a real item id can still match
    # build_owned_pools' name-keyed pool at read time (see
    # absolute_value below), so rejecting an unresolved name here would
    # just be wrong in some real cases, not merely over-cautious.
    name = (target_name or "").strip()[:MAX_ITEM_NAME_LENGTH]
    if not name:
        raise GoalValidationError("Pick an item.")
    value = _clean_int_in_range(target_value, "target_value", 1, MAX_ITEM_QTY_TARGET)
    # item_id is purely a display hint (see Goal.item_id's own
    # docstring in app/models.py) -- whatever the search suggestion the
    # player actually clicked carried, or None for free-typed text that
    # never matched a result. Loosely sanity-checked (a real OSRS item
    # id, not the free-text name's own bound), never required -- a bad
    # or missing value just means the goal list falls back to the
    # generic item badge, nothing about progress tracking depends on it.
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
    """Everything current_value below needs, fetched once per request
    rather than once per goal -- same "build shared context once,
    reuse per-goal" split app.mindmaps._build_goal_context (app/main.py)
    already uses for its own tree, just scoped to only the three
    sources this feature's three goal types actually need."""
    owned_pool_by_id, owned_pool_by_name = build_owned_pools(db, game_account)
    return {
        "boss_kill_counts": game_account.boss_kill_counts or {},
        "skills": game_account.skills or {},
        "owned_pool_by_id": owned_pool_by_id,
        "owned_pool_by_name": owned_pool_by_name,
    }


def current_value(goal, context: dict) -> int:
    """This goal's live progress number toward target_value, in
    whatever unit target_value is in. For a non-recurring goal this IS
    absolute_value() below -- a lifetime total, exactly as before this
    column existed. For a recurring one it's absolute_value() minus
    goal.recur_baseline_value instead -- how much has been gained
    since the CURRENT period started (see maybe_roll_recurring_period,
    which is what keeps recur_baseline_value/recur_period_start current
    -- this function only ever reads them, never rolls a period over
    itself, so call that first on every goal this is used against, the
    same way list_goals in app/main.py does).

    Clamped at 0 purely as a defensive floor -- absolute_value() should
    never legitimately drop below a baseline captured from that same
    reading (kc/xp/level all only ever go up), but a hiscores glitch or
    a manually-edited account shouldn't be able to show a negative
    progress bar."""
    absolute = absolute_value(goal, context)
    if not goal.is_recurring:
        return absolute
    baseline = goal.recur_baseline_value if goal.recur_baseline_value is not None else absolute
    return max(0, absolute - baseline)


def absolute_value(goal, context: dict) -> int:
    """This goal's live LIFETIME number, in whatever unit its own
    target_value is in (a real kill count; xp, or a level for a
    level-metric goal -- see the skill branch; an owned item quantity)
    -- computed fresh from `context` every call rather than ever stored
    on the Goal row itself, the same "always derive it live" stance
    app.mindmaps.evaluate_completion already takes for its own goal
    nodes. Never itself period-relative -- see current_value above for
    the number a recurring goal's progress bar actually compares
    against target_value, and create_goal/maybe_roll_recurring_period
    (this function is also what each of those calls to capture a fresh
    recur_baseline_value)."""
    if goal.goal_type == "kc":
        kc = context["boss_kill_counts"].get(goal.target_name)
        return kc if isinstance(kc, int) else 0

    if goal.goal_type == "skill":
        have_xp = (context["skills"].get(goal.target_name) or {}).get("xp", 0)
        if goal.metric == "xp":
            return have_xp
        # A level-metric goal is still compared as xp under the hood
        # (see app.mindmaps._xp_for_level's own comment -- a virtual
        # level target above 99 needs this), but xp isn't what a level
        # goal should ever show the player: report the level that xp
        # actually reaches instead, so a "get to level 80" goal's
        # progress reads as a level, not a seven-digit xp number.
        return _level_for_xp(have_xp)

    # item
    names = _item_name_variants(goal.target_name)
    ids = [i for n in names for i in (find_item_ids(n) or [])]
    if ids:
        return sum(context["owned_pool_by_id"].get(i, 0) for i in ids)
    return sum(context["owned_pool_by_name"].get(_normalize_lookup_name(n), 0) for n in names)


def maybe_roll_recurring_period(goal, context: dict) -> bool:
    """Advances a recurring goal's own current period forward to
    whichever one `now` actually falls in, re-baselining it as it goes
    -- called against every goal on every GET /api/goals (see list_goals
    in app/main.py) before current_value reads recur_period_start/
    recur_baseline_value off it, so those two columns are never more
    than one request stale. Returns whether it actually changed
    anything, so the caller knows whether there's something new to
    commit; a no-op (not recurring, or still inside the current period)
    touches nothing and returns False.

    There's no historical time-series of kc/xp/level to roll through
    period by period -- only ever a live snapshot (`context`) of
    wherever the account's real numbers stand RIGHT NOW. So a rollover
    doesn't try to reconstruct what the goal would have read at each
    period boundary it skipped (e.g. every night at midnight for a
    daily goal the player hasn't opened the site in a week); it just
    fast-forwards recur_period_start to the start of the period `now`
    falls in and re-baselines against the current live value, same as
    a brand new period always does at creation (see create_goal in
    app/main.py). A goal that's revisited well within its own cadence
    -- the common case -- never notices any of this; it only matters
    once a real period boundary has actually passed."""
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
    goal.recur_baseline_value = absolute_value(goal, context)
    return True


def _item_name_variants(item_name: str) -> List[str]:
    """item_name plus its off-hand pair (if it has a real one) --
    identical to the name list app.mindmaps' own item-goal branch of
    evaluate_completion builds, see its comment for why both names
    pool together into one combined owned count."""
    names = [item_name]
    pair_name = _offhand_pair_name(item_name)
    if pair_name and pair_name.lower() != item_name.strip().lower():
        names.append(pair_name)
    return names


def _level_for_xp(xp: int) -> int:
    """The inverse of app.mindmaps._xp_for_level -- the highest level
    (1-126, including virtual levels past the real 99 cap) this much xp
    already reaches. SKILL_XP_TABLE is small (126 entries) and this
    only ever runs once per skill goal per request, so a plain linear
    scan is simpler than bisecting for no real cost."""
    level = MIN_SKILL_LEVEL
    for candidate in range(MIN_SKILL_LEVEL, MAX_SKILL_LEVEL + 1):
        if SKILL_XP_TABLE[candidate] <= xp:
            level = candidate
        else:
            break
    return level


def target_display(goal) -> str:
    """A human-readable target label in this goal's own unit, for the
    UI to show next to its progress number -- "80" for a level goal,
    "13,034,431 xp" for an xp goal, so the same numeric
    current_value()/target_value pairing reads correctly regardless of
    which metric a skill goal picked (kc/item targets need no unit
    suffix of their own)."""
    if goal.goal_type == "skill" and goal.metric == "xp":
        return f"{goal.target_value:,} xp"
    return f"{goal.target_value:,}"

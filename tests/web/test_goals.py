"""Daily macro/calorie goals config.

Targets are keyed by USDA number code (208/203/205/204) with env-overridable
defaults; these exercise the config purely offline.
"""

import math

from dietrace.web.goals import load_goals, targets_to_goals


def test_default_goals_cover_the_four_macros() -> None:
    goals = load_goals()
    by_code = {g["code"]: g for g in goals}

    # Calories + the three macros, by USDA number code.
    assert set(by_code) == {"208", "203", "205", "204"}
    for goal in goals:
        assert goal["target"] > 0
        assert goal["name"]
        assert goal["unit"]
    assert by_code["208"]["unit"] == "kcal"


def test_goals_are_env_overridable(monkeypatch) -> None:
    monkeypatch.setenv("DIETRACE_GOAL_CALORIES", "1800")
    monkeypatch.setenv("DIETRACE_GOAL_PROTEIN", "180")

    by_code = {g["code"]: g for g in load_goals()}

    assert by_code["208"]["target"] == 1800.0
    assert by_code["203"]["target"] == 180.0


def test_non_numeric_env_override_falls_back_to_default(monkeypatch) -> None:
    # A malformed override must not crash /goals or /analysis (fail-soft, /§9):
    # degrade to the built-in default rather than raising on the float() coercion.
    monkeypatch.setenv("DIETRACE_GOAL_PROTEIN", "abc")
    monkeypatch.setenv("DIETRACE_GOAL_CALORIES", "1800")

    by_code = {g["code"]: g for g in load_goals()}

    assert by_code["203"]["target"] == 150.0  # protein default, not the bad value
    assert by_code["208"]["target"] == 1800.0  # a valid sibling override still applies


def test_non_finite_env_override_falls_back_to_default(monkeypatch) -> None:
    # float("nan")/float("inf") parse without raising, so they slip past the
    # ValueError guard — but a non-finite target poisons /analysis (remaining =
    # target − consumed becomes NaN/inf) and serializes as invalid JSON
    # (NaN/Infinity). Degrade to the built-in default like any malformed value.
    monkeypatch.setenv("DIETRACE_GOAL_PROTEIN", "nan")
    monkeypatch.setenv("DIETRACE_GOAL_CARB", "inf")
    monkeypatch.setenv("DIETRACE_GOAL_FAT", "-inf")
    monkeypatch.setenv("DIETRACE_GOAL_CALORIES", "1800")

    by_code = {g["code"]: g for g in load_goals()}

    assert by_code["203"]["target"] == 150.0  # protein default, not NaN
    assert by_code["205"]["target"] == 200.0  # carb default, not +inf
    assert by_code["204"]["target"] == 65.0  # fat default, not -inf
    assert by_code["208"]["target"] == 1800.0  # a valid sibling override still applies


def test_non_positive_env_override_falls_back_to_default(monkeypatch) -> None:
    # Zero/negative parse as finite floats, so they slip past both the ValueError
    # and isfinite guards — but a daily target ≤ 0 is just as malformed: it makes
    # the /analysis progress bars divide consumed by a zero or negative target
    # (the frontend's consumed/target ratio → division by zero / a negative bar)
    # and violates the target > 0 invariant. Degrade to the built-in default.
    monkeypatch.setenv("DIETRACE_GOAL_PROTEIN", "0")
    monkeypatch.setenv("DIETRACE_GOAL_CARB", "-50")
    monkeypatch.setenv("DIETRACE_GOAL_CALORIES", "1800")

    by_code = {g["code"]: g for g in load_goals()}

    assert by_code["203"]["target"] == 150.0  # protein default, not 0
    assert by_code["205"]["target"] == 200.0  # carb default, not -50
    assert by_code["208"]["target"] == 1800.0  # a valid sibling override still applies


# ---------------------------------------------------------------------------
# targets_to_goals — converts a saved {code: amount} dict to the goals list.
# Used by GET /goals (app.py:561) and the /analysis path (app.py:774) when a
# user has saved per-user macro targets via POST /macros/save. Integration tests
# in test_macros_endpoints.py always pass all four codes; these unit tests pin
# the branches that are only reachable with partial or unexpected inputs.
# ---------------------------------------------------------------------------


def test_targets_to_goals_empty_dict_returns_empty_list() -> None:
    """No saved targets → no goals (the all-codes-absent branch)."""
    assert targets_to_goals({}) == []


def test_targets_to_goals_full_four_codes_returns_all() -> None:
    targets = {"208": 2000.0, "203": 150.0, "205": 200.0, "204": 65.0}
    goals = targets_to_goals(targets)
    assert len(goals) == 4
    assert {g["code"] for g in goals} == {"208", "203", "205", "204"}


def test_targets_to_goals_preserves_canonical_goal_defs_order() -> None:
    """Output order mirrors _GOAL_DEFS (208→203→205→204) regardless of input order.

    The frontend renders macros in the canonical calories/protein/carb/fat order.
    A targets dict with keys in a different insertion order must not scramble it.
    """
    # Deliberately non-canonical insertion order.
    targets = {"204": 65.0, "205": 200.0, "203": 150.0, "208": 2000.0}
    codes = [g["code"] for g in targets_to_goals(targets)]
    assert codes == ["208", "203", "205", "204"]


def test_targets_to_goals_partial_codes_excludes_missing() -> None:
    """Only codes present in both targets AND _GOAL_DEFS are returned.

    The False branch of `if code in targets:` is never hit by integration
    tests that always save all four codes; this pins it directly.
    """
    targets = {"208": 1800.0, "203": 130.0}  # carb and fat absent
    goals = targets_to_goals(targets)
    by_code = {g["code"]: g for g in goals}
    assert set(by_code) == {"208", "203"}
    assert "205" not in by_code
    assert "204" not in by_code


def test_targets_to_goals_unknown_codes_silently_dropped() -> None:
    """Codes not in _GOAL_DEFS are ignored; only the matching code is returned."""
    targets = {"208": 2000.0, "999": 9999.0}
    goals = targets_to_goals(targets)
    assert len(goals) == 1
    assert goals[0]["code"] == "208"


def test_targets_to_goals_injects_name_and_unit_from_goal_defs() -> None:
    """The caller only provides amounts; name and unit come from _GOAL_DEFS."""
    targets = {"208": 1800.0}
    goals = targets_to_goals(targets)
    assert len(goals) == 1
    assert goals[0]["name"]        # non-empty name from _GOAL_DEFS
    assert goals[0]["unit"] == "kcal"
    assert goals[0]["target"] == 1800.0
    assert goals[0]["code"] == "208"


def test_targets_to_goals_malformed_saved_target_falls_back_to_default() -> None:
    """A non-finite or non-positive saved target degrades to the built-in default.

    Unlike the env-override path (guarded in goals._target) and the ADK tool path
    (guarded in check_against_goals), these saved targets reach here straight from
    the client's POST /macros/save body — MacroSaveRequest.targets is an
    unconstrained ``dict[str, float]``, so pydantic admits NaN/Infinity, and the
    GoalStore persists them verbatim (``json.dumps`` writes ``NaN``/``Infinity``)
    and reads them back as-is. A non-finite target poisons the /analysis
    remaining-vs-target math (remaining = target − consumed → NaN/inf) and
    serializes as invalid JSON; a target ≤ 0 breaks the progress-bar ratio
    (consumed / target). Each malformed code degrades to its _GOAL_DEFS default —
    the same fail-soft outcome the other two ingress points already give — while a
    valid sibling target is preserved.
    """
    # Covers each malformed class: non-finite (NaN, +inf), negative-finite, zero.
    targets = {
        "203": float("nan"),  # NaN → protein default
        "205": float("inf"),  # +inf → carb default
        "204": -50.0,         # negative-finite → fat default
        "208": 0.0,           # zero → calories default
    }
    by_code = {g["code"]: g for g in targets_to_goals(targets)}

    assert by_code["203"]["target"] == 150.0  # protein default, not NaN
    assert by_code["205"]["target"] == 200.0  # carb default, not +inf
    assert by_code["204"]["target"] == 65.0   # fat default, not -50
    assert by_code["208"]["target"] == 2000.0  # calories default, not 0
    # Every target that ships is finite and positive — the goals invariant holds.
    for goal in by_code.values():
        assert math.isfinite(goal["target"]) and goal["target"] > 0


def test_targets_to_goals_valid_saved_target_alongside_malformed_is_preserved() -> None:
    """A valid saved target is carried through unchanged even when a sibling is bad."""
    targets = {"203": 180.0, "205": float("nan")}
    by_code = {g["code"]: g for g in targets_to_goals(targets)}

    assert by_code["203"]["target"] == 180.0  # valid override preserved
    assert by_code["205"]["target"] == 200.0  # carb default, not NaN

"""Daily macro/calorie goals config.

Targets are keyed by USDA number code (208/203/205/204) with env-overridable
defaults; these exercise the config purely offline.
"""

from dietrace.web.goals import load_goals


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

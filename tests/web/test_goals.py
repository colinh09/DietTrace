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

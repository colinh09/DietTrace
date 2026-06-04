"""Verify the macro eval dataset loads and validates."""

from pathlib import Path

MACRO_DIR = Path("evals/dataset/macros")


def test_macro_dataset_directory_exists() -> None:
    assert MACRO_DIR.exists(), f"{MACRO_DIR} not found — create macro eval cases"


def test_macro_dataset_has_at_least_three_cases() -> None:
    cases = sorted(MACRO_DIR.glob("*.json"))
    assert len(cases) >= 3, f"Expected ≥3 macro cases, found {len(cases)}"


def test_all_macro_cases_load_and_validate() -> None:
    """Every macro case validates against the MacroEvalCase schema."""
    from dietrace.evals.macro_schema import load_macro_case

    cases = sorted(MACRO_DIR.glob("*.json"))
    assert cases, "No macro eval cases found"
    for path in cases:
        case = load_macro_case(path)
        assert case.input.age > 0
        assert case.input.weight_kg > 0
        assert case.expected.kcal_min < case.expected.kcal_max
        assert case.expected.protein_g_min < case.expected.protein_g_max
        assert case.expected.fat_g_min < case.expected.fat_g_max
        assert case.expected.carb_g_min < case.expected.carb_g_max


def test_macro_cases_cover_both_sexes() -> None:
    from dietrace.evals.macro_schema import load_macro_case

    cases = [load_macro_case(p) for p in sorted(MACRO_DIR.glob("*.json"))]
    sexes = {c.input.sex for c in cases}
    assert "male" in sexes, "No male profile in macro dataset"
    assert "female" in sexes, "No female profile in macro dataset"


def test_macro_cases_cover_multiple_goals() -> None:
    from dietrace.evals.macro_schema import load_macro_case

    cases = [load_macro_case(p) for p in sorted(MACRO_DIR.glob("*.json"))]
    goals = {c.input.goal for c in cases}
    assert len(goals) >= 2, f"Expected ≥2 goals in macro dataset, found {goals}"

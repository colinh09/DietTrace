"""Unit tests for src/dietrace/evals/schema.py.

These pin the EvalCase JSON contract: every dataset case is an
``{input, expected, metadata}`` object whose ``metadata.nutrient_tier`` selects
the two-tier scoring path — ``"full"`` (whole foods, full micro panel) or
``"label"`` (branded, label subset). The schema is what the numeric evaluators
 and the dataset loader (4.7/4.9) build on, so loading and
validating a case from JSON is the load-bearing behavior here. No DB or network
is touched.
"""

import json

import pytest
from pydantic import ValidationError

from dietrace.evals.schema import (
    CaseMetadata,
    EvalCase,
    ExpectedNutrition,
    load_case,
)

_FULL_CASE = {
    "input": {"text": "two eggs and half an avocado"},
    "expected": {
        "calories": 446.0,
        "protein_g": 17.6,
        "fat_g": 35.2,
        "carb_g": 9.6,
        "grams": 200.0,
        "micros": {"301": 60.0, "307": 142.0},
    },
    "metadata": {
        "nutrient_tier": "full",
        "fdc_id": 748967,
        "tolerance": 0.15,
        "source": "USDA SR Legacy",
    },
}

_LABEL_CASE = {
    "input": {"text": "a Clif builder's bar"},
    "expected": {
        "calories": 280.0,
        "protein_g": 20.0,
        "fat_g": 9.0,
        "carb_g": 30.0,
    },
    "metadata": {"nutrient_tier": "label", "fdc_id": 100001},
}


def test_eval_case_loads_full_tier_from_json() -> None:
    """A whole-food case validates and exposes its expected macros + tier."""
    case = EvalCase.model_validate(_FULL_CASE)

    assert case.input.text == "two eggs and half an avocado"
    assert case.expected.calories == 446.0
    assert case.expected.protein_g == 17.6
    assert case.expected.grams == 200.0
    assert case.expected.micros["301"] == 60.0
    assert case.metadata.nutrient_tier == "full"
    assert case.metadata.fdc_id == 748967
    assert case.metadata.tolerance == 0.15


def test_eval_case_loads_label_tier_with_defaults() -> None:
    """A branded case validates; optional fields default rather than error."""
    case = EvalCase.model_validate(_LABEL_CASE)

    assert case.metadata.nutrient_tier == "label"
    assert case.expected.grams is None
    assert case.expected.micros == {}
    assert case.metadata.tolerance == 0.15  # within_tolerance default ±15%
    assert case.metadata.source is None


def test_load_case_reads_and_validates_a_json_file(tmp_path) -> None:
    """load_case round-trips a JSON file on disk into a validated EvalCase."""
    path = tmp_path / "egg_avocado.json"
    path.write_text(json.dumps(_FULL_CASE))

    case = load_case(path)

    assert isinstance(case, EvalCase)
    assert case.metadata.nutrient_tier == "full"
    assert case.expected.calories == 446.0


def test_nutrient_tier_rejects_unknown_value() -> None:
    """nutrient_tier is constrained to the two scoring tiers."""
    bad = json.loads(json.dumps(_FULL_CASE))
    bad["metadata"]["nutrient_tier"] = "micro"

    with pytest.raises(ValidationError):
        EvalCase.model_validate(bad)


def test_metadata_requires_nutrient_tier() -> None:
    """nutrient_tier is mandatory — scoring cannot dispatch without it."""
    bad = json.loads(json.dumps(_LABEL_CASE))
    del bad["metadata"]["nutrient_tier"]

    with pytest.raises(ValidationError):
        EvalCase.model_validate(bad)


def test_expected_requires_macros() -> None:
    """The scored macros (calories + protein/fat/carb) are required."""
    bad = json.loads(json.dumps(_LABEL_CASE))
    del bad["expected"]["calories"]

    with pytest.raises(ValidationError):
        EvalCase.model_validate(bad)


def test_unknown_fields_are_rejected() -> None:
    """A stray field is a typo, not silently dropped — the schema is strict."""
    bad = json.loads(json.dumps(_LABEL_CASE))
    bad["metadata"]["tier"] = "full"  # misspelling of nutrient_tier

    with pytest.raises(ValidationError):
        EvalCase.model_validate(bad)


def test_case_metadata_rejects_non_finite_or_negative_tolerance():
    """A NaN/inf/negative ±band would silently flip every evaluator's pass/fail
    verdict (``err <= tolerance`` is False against NaN), so the schema must
    reject it loudly rather than corrupt scoring."""
    for bad in (-0.1, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            CaseMetadata(nutrient_tier="full", tolerance=bad)

    # 0.0 (require exact match) and positive bands remain valid.
    assert CaseMetadata(nutrient_tier="full", tolerance=0.0).tolerance == 0.0
    assert CaseMetadata(nutrient_tier="full", tolerance=0.2).tolerance == 0.2


def test_expected_nutrition_rejects_non_finite_ground_truth():
    """A NaN/inf ground-truth value is meaningless and silently distorts scoring:
    every evaluator compares against ``expected`` and falls back to a full-miss
    (1.0) for non-finite error, so a corrupt case would score every output as
    maximally wrong without ever failing to load. The schema must reject it
    loudly — matching ``CaseMetadata.tolerance`` in the same file."""
    base = {"calories": 100.0, "protein_g": 5.0, "fat_g": 2.0, "carb_g": 10.0}
    for field in ("calories", "protein_g", "fat_g", "carb_g", "grams"):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(ValidationError):
                ExpectedNutrition(**{**base, field: bad})

    # A non-finite value buried in the optional micro panel is rejected too.
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            ExpectedNutrition(**base, micros={"307": bad})

    # Finite ground truth (including an omitted grams / empty micros) is valid.
    ok = ExpectedNutrition(**base, grams=200.0, micros={"307": 142.0})
    assert ok.calories == 100.0
    assert ok.grams == 200.0
    assert ExpectedNutrition(**base).grams is None

"""The seed eval dataset validates and carries usable ground truth.

Every case under ``evals/dataset/nutrition/`` must parse against the EvalCase
schema, declare a nutrient tier, and carry the USDA-grounded values the numeric
evaluators score against. Full-tier (whole-food) cases additionally carry a micro
panel and a ground-truth portion weight; both tiers must be represented. No
network or DB is touched.
"""

from pathlib import Path

from dietrace.evals.schema import load_case

DATASET = Path("evals/dataset/nutrition")


def _cases():
    return [load_case(p) for p in sorted(DATASET.glob("*.json"))]


def test_dataset_has_enough_cases() -> None:
    assert len(list(DATASET.glob("*.json"))) >= 8


def test_every_case_validates_and_carries_ground_truth() -> None:
    for case in _cases():
        assert case.metadata.nutrient_tier in ("full", "label")
        assert case.expected.calories > 0
        assert case.metadata.fdc_id is not None
        if case.metadata.nutrient_tier == "full":
            assert case.expected.micros, "full-tier case must carry a micro panel"
            assert case.expected.grams is not None


def test_both_tiers_are_represented() -> None:
    tiers = {case.metadata.nutrient_tier for case in _cases()}
    assert tiers == {"full", "label"}

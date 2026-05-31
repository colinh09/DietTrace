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


def test_dataset_expanded_with_eight_more_cases() -> None:
    """: the seed 8 grows by 8 more USDA-grounded cases."""
    assert len(list(DATASET.glob("*.json"))) >= 16


def test_expansion_keeps_both_tiers_with_branded_labels() -> None:
    """The growth is mostly whole-food full-micro plus a couple branded labels."""
    cases = _cases()
    full = [c for c in cases if c.metadata.nutrient_tier == "full"]
    label = [c for c in cases if c.metadata.nutrient_tier == "label"]
    # Whole-food full-micro cases dominate; branded labels grow past the seed 2.
    assert len(full) >= 12
    assert len(label) >= 4


def test_every_case_pins_a_unique_fdc_id() -> None:
    """Each case is pinned to a distinct USDA food so ground truth is traceable."""
    fdc_ids = [c.metadata.fdc_id for c in _cases()]
    assert all(fid is not None for fid in fdc_ids)
    assert len(set(fdc_ids)) == len(fdc_ids)

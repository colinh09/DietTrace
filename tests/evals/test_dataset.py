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


# : eight more everyday whole-food cases (apple, banana, white
# rice cooked, chicken breast cooked, broccoli, almonds, greek yogurt, egg),
# each grounded to a distinct USDA food pulled from data/food.sqlite.
_WHOLE_FOOD_11_4 = [
    "apple_peeled.json",
    "banana_ripe.json",
    "white_rice_medium_grain.json",
    "chicken_breast_grilled.json",
    "broccoli_cooked_cup.json",
    "almonds_dry_roasted.json",
    "greek_yogurt_nonfat.json",
    "egg_hard_boiled.json",
]


def test_eleven_four_adds_eight_common_whole_food_cases() -> None:
    """The eight new everyday-food cases exist and validate against the schema."""
    for name in _WHOLE_FOOD_11_4:
        case = load_case(DATASET / name)
        assert case.expected.calories > 0
        assert case.metadata.fdc_id is not None
        if case.metadata.nutrient_tier == "full":
            assert case.expected.micros, f"{name}: full-tier case needs micros"
            assert case.expected.grams is not None


def test_eleven_four_represents_both_tiers() -> None:
    """The new batch carries both a full-micro tier and a label tier."""
    tiers = {load_case(DATASET / name).metadata.nutrient_tier for name in _WHOLE_FOOD_11_4}
    assert tiers == {"full", "label"}


def test_eleven_four_cases_pin_unused_fdc_ids() -> None:
    """The eight new cases are distinct foods, not duplicates of earlier cases."""
    new_ids = [load_case(DATASET / name).metadata.fdc_id for name in _WHOLE_FOOD_11_4]
    prior_ids = {
        c.metadata.fdc_id
        for p in sorted(DATASET.glob("*.json"))
        if p.name not in _WHOLE_FOOD_11_4
        for c in [load_case(p)]
    }
    assert len(set(new_ids)) == len(new_ids)
    assert prior_ids.isdisjoint(new_ids)

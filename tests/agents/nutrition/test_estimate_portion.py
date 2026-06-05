"""Tests for estimate_portion — deterministic portion→grams (3.1; ).

``estimate_portion(food, quantity, unit)`` resolves a household portion to a
gram weight using the food's serving sizes first, then a generic fallback
table, and reports the ``source`` and a ``confidence`` so the eval surface and
supervisor can see how the number was reached. Per the done criterion it
covers "1 egg", "half an avocado", and "1 slice toast"; these tests build the
foods directly (matching the fixture's USDA-grounded serving sizes) so the
portion logic is exercised independently of the DB read layer.
"""

import pytest

from dietrace.agents.nutrition.estimate_portion import PortionEstimate, estimate_portion
from dietrace.nutrition.models import Food, ServingSize


def _egg() -> Food:
    return Food(
        fdc_id=748967,
        description="Egg, whole, raw, fresh",
        data_type="sr_legacy_food",
        serving_sizes=[
            ServingSize(amount=1.0, unit="large", gram_weight=50.0, description="1 large")
        ],
    )


def _avocado() -> Food:
    return Food(
        fdc_id=171705,
        description="Avocados, raw, all commercial varieties",
        data_type="sr_legacy_food",
        serving_sizes=[
            ServingSize(amount=1.0, unit="fruit", gram_weight=201.0, description="1 fruit"),
            ServingSize(amount=0.5, unit="fruit", gram_weight=100.5, description="half an avocado"),
        ],
    )


def _toast() -> Food:
    return Food(
        fdc_id=172686,
        description="Bread, whole-wheat, commercially prepared",
        data_type="sr_legacy_food",
        serving_sizes=[
            ServingSize(amount=1.0, unit="slice", gram_weight=28.0, description="1 slice")
        ],
    )


def _plain() -> Food:
    """A food with no serving sizes, to exercise the fallback table."""
    return Food(fdc_id=11111, description="Spinach, raw", data_type="sr_legacy_food")


def test_one_egg_uses_primary_serving() -> None:
    """"1 egg" is one whole egg → the egg's primary serving (50 g)."""
    est = estimate_portion(_egg(), 1.0, "egg")

    assert isinstance(est, PortionEstimate)
    assert est.grams == pytest.approx(50.0)
    assert est.source == "whole_item"
    assert est.confidence > 0.0


def test_half_avocado_scales_primary_serving() -> None:
    """"half an avocado" → half the whole-fruit serving (201 g → 100.5 g).

    The avocado lists a serving whose description names the fruit ("half an
    avocado"), so the unit resolves through the more-specific serving-size match.
    """
    est = estimate_portion(_avocado(), 0.5, "avocado")

    assert est.grams == pytest.approx(100.5)
    assert est.source == "serving_size"


def test_one_slice_toast_matches_serving_unit() -> None:
    """"1 slice" matches the toast's "slice" serving size (28 g)."""
    est = estimate_portion(_toast(), 1.0, "slice")

    assert est.grams == pytest.approx(28.0)
    assert est.source == "serving_size"


def test_serving_unit_match_scales_by_quantity() -> None:
    """Two slices is twice the per-slice gram weight."""
    est = estimate_portion(_toast(), 2.0, "slice")

    assert est.grams == pytest.approx(56.0)
    assert est.source == "serving_size"


def test_explicit_mass_unit_is_passed_through() -> None:
    """A gram quantity is returned verbatim at full confidence."""
    est = estimate_portion(_egg(), 120.0, "g")

    assert est.grams == pytest.approx(120.0)
    assert est.source == "mass"
    assert est.confidence == pytest.approx(1.0)


def test_ounces_convert_to_grams() -> None:
    """Ounces convert by the standard factor."""
    est = estimate_portion(_egg(), 2.0, "oz")

    assert est.grams == pytest.approx(56.699, abs=1e-2)
    assert est.source == "mass"


def test_fallback_table_when_no_serving_size_matches() -> None:
    """A unit absent from the food's servings falls back to a generic table."""
    est = estimate_portion(_plain(), 1.0, "cup")

    assert est.grams == pytest.approx(240.0)
    assert est.source == "fallback_table"
    assert 0.0 < est.confidence < 0.9


def test_serving_size_is_more_confident_than_fallback() -> None:
    """A real serving-size hit outranks a fallback-table guess in confidence."""
    serving = estimate_portion(_toast(), 1.0, "slice")
    fallback = estimate_portion(_plain(), 1.0, "cup")

    assert serving.confidence > fallback.confidence


def test_unknown_unit_reports_no_grams() -> None:
    """An unresolvable unit yields no grams at zero confidence rather than raising."""
    est = estimate_portion(_plain(), 1.0, "smidgen")

    assert est.grams is None
    assert est.source == "unknown"
    assert est.confidence == pytest.approx(0.0)


def _granola() -> Food:
    """A food whose first serving is an oversized package, with an NLEA one after.

    USDA branded data often lists a whole-package serving before the FDA label
    (NLEA) serving; a bare count should scale by the edible NLEA serving, not the
    whole package ( — "NLEA/edible-portion servings preferred over
    oversized package servings").
    """
    return Food(
        fdc_id=42,
        description="Granola, oats and honey",
        data_type="branded_food",
        serving_sizes=[
            ServingSize(amount=1.0, unit="package", gram_weight=340.0, description="1 package"),
            ServingSize(amount=1.0, unit="cup", gram_weight=55.0, description="1 NLEA serving"),
        ],
    )


def _cereal_no_nlea() -> Food:
    """An oversized box serving listed before a normal edible cup serving."""
    return Food(
        fdc_id=43,
        description="Cereal flakes",
        data_type="branded_food",
        serving_sizes=[
            ServingSize(amount=1.0, unit="box", gram_weight=500.0, description="1 box"),
            ServingSize(amount=1.0, unit="cup", gram_weight=30.0, description="1 cup"),
        ],
    )


def test_whole_item_prefers_nlea_over_oversized_package() -> None:
    """A bare count scales by the NLEA serving, not the oversized package listed first."""
    est = estimate_portion(_granola(), 1.0, "serving")

    assert est.grams == pytest.approx(55.0)
    assert est.source == "whole_item"


def test_whole_item_prefers_edible_serving_over_oversized() -> None:
    """Without an NLEA marker, a bare count still avoids the oversized package serving."""
    est = estimate_portion(_cereal_no_nlea(), 1.0, "serving")

    assert est.grams == pytest.approx(30.0)
    assert est.source == "whole_item"


def test_only_oversized_serving_still_resolves() -> None:
    """When the only serving is an oversized package, it is still used (fail-soft)."""
    food = Food(
        fdc_id=44,
        description="Cola, carbonated beverage",
        data_type="branded_food",
        serving_sizes=[
            ServingSize(amount=1.0, unit="bottle", gram_weight=591.0, description="1 bottle")
        ],
    )

    est = estimate_portion(food, 1.0, "serving")

    assert est.grams == pytest.approx(591.0)
    assert est.source == "whole_item"


def test_explicit_package_unit_is_honored() -> None:
    """An explicit "package" unit still resolves to the package — the preference for
    edible servings only governs *bare* counts, not a unit the user named outright."""
    est = estimate_portion(_granola(), 1.0, "package")

    assert est.grams == pytest.approx(340.0)
    assert est.source == "serving_size"


# ---- FNDDS-style portions: a per-piece serving, sized pieces, and the survey's
# "Quantity not specified" as-eaten default (the portion-import fix). ----


def _almonds() -> Food:
    """An FNDDS food: a single-piece serving ("1 nut") plus larger measures."""
    return Food(
        fdc_id=2707485,
        description="Almonds, NFS",
        data_type="survey_fndds_food",
        serving_sizes=[
            ServingSize(amount=1.0, unit="nut", gram_weight=1.2, description="1 nut"),
            ServingSize(amount=1.0, unit="cup", gram_weight=141.0, description="1 cup"),
            ServingSize(amount=1.0, unit="oz", gram_weight=28.35, description="1 oz"),
            ServingSize(
                amount=1.0, unit="quantity not specified", gram_weight=28.0,
                description="Quantity not specified",
            ),
        ],
    )


def _shrimp() -> Food:
    """An FNDDS food with tiny/small-medium/large sized pieces."""
    return Food(
        fdc_id=2706360,
        description="Shrimp, NFS",
        data_type="survey_fndds_food",
        serving_sizes=[
            ServingSize(
                amount=1.0, unit="tiny shrimp", gram_weight=5.0, description="1 tiny shrimp"
            ),
            ServingSize(
                amount=1.0, unit="small/medium shrimp", gram_weight=10.0,
                description="1 small/medium shrimp",
            ),
            ServingSize(
                amount=1.0, unit="large/jumbo shrimp", gram_weight=15.0,
                description="1 large/jumbo shrimp",
            ),
            ServingSize(
                amount=1.0, unit="quantity not specified", gram_weight=85.0,
                description="Quantity not specified",
            ),
        ],
    )


def _latte() -> Food:
    """An FNDDS beverage whose first serving is a tiny per-fl-oz reference."""
    return Food(
        fdc_id=2710386,
        description="Coffee, Latte",
        data_type="survey_fndds_food",
        serving_sizes=[
            ServingSize(amount=1.0, unit="fl oz", gram_weight=30.0, description="1 fl oz"),
            ServingSize(amount=1.0, unit="cup", gram_weight=240.0, description="1 cup (8 fl oz)"),
            ServingSize(
                amount=1.0, unit="quantity not specified", gram_weight=360.0,
                description="Quantity not specified",
            ),
        ],
    )


def _pizza() -> Food:
    """An FNDDS pizza whose pieces are labeled "piece", not "slice"."""
    return Food(
        fdc_id=2709876,
        description="Pizza, cheese, whole wheat thin crust",
        data_type="survey_fndds_food",
        serving_sizes=[
            ServingSize(amount=1.0, unit="piece", gram_weight=119.0, description="1 piece"),
            ServingSize(
                amount=1.0, unit="personal size pizza", gram_weight=175.0,
                description="1 personal size pizza",
            ),
        ],
    )


def test_counted_small_pieces_use_per_piece_serving() -> None:
    """"10 almonds" scales the single-almond weight, not a cup or package (12 g)."""
    est = estimate_portion(_almonds(), 10.0, "almonds")

    assert est.grams == pytest.approx(12.0)  # 10 × 1.2 g, NOT 10 × 100 g
    assert est.source == "whole_item"


def test_bare_item_uses_quantity_not_specified_default() -> None:
    """A bare item ("almonds") scales the FNDDS as-eaten default (28 g), not a piece."""
    est = estimate_portion(_almonds(), 1.0, "")

    assert est.grams == pytest.approx(28.0)
    assert est.source == "whole_item"


def test_bare_multi_count_scales_a_single_piece_not_the_default() -> None:
    """"10 almonds" when the parse leaves the unit bare still counts pieces (12 g),
    not ten as-eaten handfuls (280 g)."""
    est = estimate_portion(_almonds(), 10.0, "")

    assert est.grams == pytest.approx(12.0)
    assert est.source == "whole_item"


def test_sized_piece_count_prefers_medium() -> None:
    """"5 shrimp" picks the small/medium piece (10 g each), not tiny or jumbo (50 g)."""
    est = estimate_portion(_shrimp(), 5.0, "shrimp")

    assert est.grams == pytest.approx(50.0)
    assert est.source == "serving_size"


def test_bare_beverage_uses_default_not_tiny_reference() -> None:
    """"a latte" scales the as-eaten default (360 g), not the per-fl-oz reference (30 g)."""
    est = estimate_portion(_latte(), 1.0, "")

    assert est.grams == pytest.approx(360.0)
    assert est.source == "whole_item"


def test_pizza_slice_uses_food_piece_not_bread_fallback() -> None:
    """"2 slices of pizza" use the pizza's own piece (119 g), not the 28 g slice guess."""
    est = estimate_portion(_pizza(), 2.0, "slice")

    assert est.grams == pytest.approx(238.0)
    assert est.source == "whole_item"


def _whole_avocado() -> Food:
    """An FNDDS avocado with a small "slice" serving and a whole "fruit" one."""
    return Food(
        fdc_id=2709223,
        description="Avocado, raw",
        data_type="survey_fndds_food",
        serving_sizes=[
            ServingSize(amount=1.0, unit="slice", gram_weight=15.0, description="1 slice"),
            ServingSize(amount=1.0, unit="fruit", gram_weight=150.0, description="1 fruit"),
            ServingSize(amount=1.0, unit="cup", gram_weight=150.0, description="1 cup"),
            ServingSize(
                amount=1.0, unit="quantity not specified", gram_weight=30.0,
                description="Quantity not specified",
            ),
        ],
    )


def test_counted_whole_fruit_prefers_whole_over_slice() -> None:
    """"an avocado" is one whole fruit (150 g), not the smallest "1 slice" (15 g)."""
    est = estimate_portion(_whole_avocado(), 1.0, "avocado")

    assert est.grams == pytest.approx(150.0)
    assert est.source == "whole_item"


# ---- _per_piece_serving NFS branch: an explicit "piece, NFS" beats a "medium piece".
#
# The NFS (Not Further Specified) branch fires between the whole-food-name check
# (priority 1) and the medium/regular-size check (priority 3), so a serving whose
# description or unit contains "nfs" is returned as the representative single piece
# even when a larger "medium" variant is present. Without a direct test this priority
# is invisible: the medium branch would silently win if the two loops were swapped
# and all existing tests would still pass (none carry an NFS-tagged serving). ----


def _grain_nfs() -> Food:
    """A grain food whose serving units do NOT repeat the food name token "roll".

    The medium piece is listed first so _best_unit_match would pick it if step 2
    fired — but step 2 finds no match (neither serving's tokens include "roll"),
    so the resolution falls to step 3 (whole-item count) and _per_piece_serving.
    There, the NFS branch (priority 2) must fire before the medium branch (priority 3),
    returning the 40 g NFS piece over the 55 g medium one.
    """
    return Food(
        fdc_id=9999,
        description="Grain roll, whole wheat",  # "roll" in food name → whole-item match
        data_type="survey_fndds_food",
        serving_sizes=[
            ServingSize(
                amount=1.0, unit="medium", gram_weight=55.0,
                description="1 medium",  # no "roll" in tokens → step 2 skips this
            ),
            ServingSize(
                amount=1.0, unit="piece, NFS", gram_weight=40.0,
                description="1 piece, NFS",  # "nfs" triggers the NFS branch
            ),
        ],
    )


def test_per_piece_nfs_preferred_over_medium_sized_variant() -> None:
    """_per_piece_serving returns the NFS piece (40 g) ahead of the medium piece (55 g).

    Step 2 finds no match (serving units lack "roll"), so resolution reaches step 3
    and calls _per_piece_serving. The NFS branch (priority 2) fires before the
    medium branch (priority 3), so 2 rolls → 80 g, not 110 g. Removing or swapping
    those two loops would silently change logged portion weights.
    """
    est = estimate_portion(_grain_nfs(), 2.0, "roll")

    assert est.grams == pytest.approx(80.0)  # 2 × 40 g (NFS), not 2 × 55 g (medium)
    assert est.source == "whole_item"


# ──  per-portion basis strings ─────────────────────────────────────
# Each estimate must explain HOW the gram weight was derived so the UI can show
# "why peanut butter got 100g" etc. The basis field is a plain-English string.


def test_mass_basis_describes_explicit_weight() -> None:
    """Explicit g/oz has a basis mentioning 'explicit weight'."""
    est = estimate_portion(_egg(), 120.0, "g")

    assert est.source == "mass"
    assert est.basis  # non-empty
    assert "explicit weight" in est.basis.lower()


def test_serving_size_basis_names_the_matched_serving() -> None:
    """A serving-size hit names the matched serving description in its basis."""
    est = estimate_portion(_toast(), 1.0, "slice")

    assert est.source == "serving_size"
    assert "1 slice" in est.basis  # serving description appears verbatim


def test_whole_item_counted_basis_mentions_the_count() -> None:
    """"10 almonds" — the count appears in the basis."""
    est = estimate_portion(_almonds(), 10.0, "almonds")

    assert est.source == "whole_item"
    assert "10" in est.basis


def test_whole_item_default_basis_mentions_reference_serving() -> None:
    """"a latte" — no quantity, so the basis says 'reference serving'."""
    est = estimate_portion(_latte(), 1.0, "")

    assert est.source == "whole_item"
    assert "reference serving" in est.basis.lower()


def test_fallback_table_basis_names_the_unit() -> None:
    """A fallback-table hit names the unit (e.g. 'cup') in its basis."""
    est = estimate_portion(_plain(), 1.0, "cup")

    assert est.source == "fallback_table"
    assert "cup" in est.basis.lower()


def test_unknown_basis_is_non_empty() -> None:
    """An unresolvable unit still produces a non-empty basis string."""
    est = estimate_portion(_plain(), 1.0, "smidgen")

    assert est.source == "unknown"
    assert est.basis  # something is reported even when nothing matched

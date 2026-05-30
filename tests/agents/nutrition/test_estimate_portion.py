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
    """"half an avocado" → half the whole-fruit serving (201 g → 100.5 g)."""
    est = estimate_portion(_avocado(), 0.5, "avocado")

    assert est.grams == pytest.approx(100.5)
    assert est.source == "whole_item"


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

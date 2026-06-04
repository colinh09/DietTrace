"""MacroProfile input validation (review fix #3).

A degenerate profile must be rejected at the boundary, not silently turned into
negative/nonsensical targets. weight_kg=0 stays valid (the preset-eval sentinel).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dietrace.macros.models import MacroProfile


def _valid(**over: object) -> dict[str, object]:
    base: dict[str, object] = dict(
        age=30,
        sex="male",
        height_cm=178.0,
        weight_kg=76.0,
        activity="moderate",
        goal="cut",
    )
    base.update(over)
    return base


def test_valid_profile_constructs() -> None:
    assert MacroProfile(**_valid()).weight_kg == 76.0


@pytest.mark.parametrize(
    "field,value",
    [
        ("age", 0),
        ("age", -5),
        ("age", 200),
        ("height_cm", 0.0),
        ("height_cm", -10.0),
        ("weight_kg", -1.0),
        ("weight_kg", 1000.0),
    ],
)
def test_rejects_out_of_range(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        MacroProfile(**_valid(**{field: value}))


def test_weight_zero_allowed_as_sentinel() -> None:
    # weight_kg=0 is the preset-eval sentinel (skips the protein g/kg axis) and
    # must remain constructible.
    assert MacroProfile(**_valid(weight_kg=0.0)).weight_kg == 0.0

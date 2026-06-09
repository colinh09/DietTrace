"""Tests for the champion-challenger gate.

Stub logger (no Gemini): the preference block makes the preworkout estimate
land on the user's confirmed truth, so a good block improves fit while holding
USDA. Covers scoring, the ship rule, and confirmations→cases.
"""

from __future__ import annotations

from dietrace.web.gate import (
    confirmations_to_cases,
    score_block,
    ship_decision,
)


def _totals(kcal: float) -> list[dict]:
    return [{"code": "208", "name": "Energy", "amount": kcal, "unit": "kcal"}]


def _has_block(examples) -> bool:
    return any(e.get("preference_block") for e in (examples or []))


def _stub_logger(text: str, examples=None) -> dict:
    """USDA meals are estimated fine either way; the preworkout meal is only
    accurate when the preference block is injected (it lifts the carb estimate)."""
    if text.startswith("usda"):
        return {"totals": _totals(100)}
    if "preworkout" in text:
        return {"totals": _totals(600 if _has_block(examples) else 350)}
    return {"totals": _totals(100)}


_USDA = [{"text": "usda-1", "calories": 100}, {"text": "usda-2", "calories": 100}]
_FIT = [{"text": "preworkout oats", "calories": 600}]


def test_score_block_reports_both_axes() -> None:
    current = score_block("", _FIT, _USDA, _stub_logger)
    proposed = score_block("carbs run high preworkout", _FIT, _USDA, _stub_logger)
    # USDA unaffected by the block; fit jumps once the block is present.
    assert current["usda"] == 1.0 and proposed["usda"] == 1.0
    assert current["fit"] < proposed["fit"]
    assert proposed["fit"] == 1.0  # 600 vs 600 expected


def test_ship_when_fit_improves_and_usda_holds() -> None:
    current = score_block("", _FIT, _USDA, _stub_logger)
    proposed = score_block("carbs run high preworkout", _FIT, _USDA, _stub_logger)
    decision = ship_decision(current, proposed)
    assert decision["ship"] is True
    assert decision["usda_ok"] and decision["fit_gain"]


def test_reject_when_usda_floor_breached() -> None:
    current = {"usda": 1.0, "fit": 0.5}
    proposed = {"usda": 0.5, "fit": 1.0}  # big USDA drop, even though fit is better
    decision = ship_decision(current, proposed, eps=0.05)
    assert decision["ship"] is False
    assert decision["usda_ok"] is False
    assert "USDA floor" in decision["reason"]


def test_reject_when_no_fit_gain() -> None:
    current = {"usda": 1.0, "fit": 0.7}
    proposed = {"usda": 1.0, "fit": 0.7}  # bad/empty feedback → no improvement
    decision = ship_decision(current, proposed)
    assert decision["ship"] is False
    assert decision["fit_gain"] is False
    assert "fit improvement" in decision["reason"]


def test_small_usda_dip_is_allowed_within_eps() -> None:
    current = {"usda": 0.90, "fit": 0.50}
    proposed = {"usda": 0.87, "fit": 0.80}  # −0.03 USDA, big fit win
    assert ship_decision(proposed=proposed, current=current, eps=0.05)["ship"] is True


def test_reject_when_fit_gain_below_margin() -> None:
    # A trivial fit bump (under FIT_DELTA) is noise, not a meaningful improvement.
    current = {"usda": 1.0, "fit": 0.70}
    proposed = {"usda": 1.0, "fit": 0.71}  # +0.01 < default 0.02 margin
    decision = ship_decision(current, proposed)
    assert decision["ship"] is False
    assert decision["fit_gain"] is False
    assert "fit improvement" in decision["reason"]


def test_ship_when_fit_gain_meets_margin() -> None:
    current = {"usda": 1.0, "fit": 0.70}
    proposed = {"usda": 1.0, "fit": 0.73}  # +0.03 ≥ 0.02 margin
    decision = ship_decision(current, proposed)
    assert decision["ship"] is True
    assert decision["fit_gain"] is True


def test_fit_margin_is_configurable() -> None:
    current = {"usda": 1.0, "fit": 0.70}
    proposed = {"usda": 1.0, "fit": 0.74}  # +0.04
    # A stricter margin than the gain rejects it.
    assert ship_decision(current, proposed, fit_delta=0.05)["ship"] is False
    assert ship_decision(current, proposed, fit_delta=0.03)["ship"] is True


def test_zero_calorie_case_scores_exact_without_dividing_by_zero() -> None:
    """A confirmed meal whose totals carry no energy (208) entry becomes a
    zero-expected case (calories_of → 0.0). The gate must score it without a
    ZeroDivisionError in abs(est - expected) / expected: an estimate that is
    also 0 kcal is an exact hit (fit 1.0), so a black-coffee-style confirmation
    counts as perfectly fit rather than crashing the whole retune scoring loop."""
    zero_fit = [{"text": "black coffee", "calories": 0}]

    def _zero_logger(text: str, examples=None) -> dict:
        return {"totals": _totals(0)}

    assert score_block("", zero_fit, _USDA, _zero_logger)["fit"] == 1.0


def test_zero_calorie_case_misses_when_estimate_is_nonzero() -> None:
    """The other arm of the zero-expected guard: when the meal's truth is 0 kcal
    but the estimate hallucinates calories, that case scores 0.0 (a miss), again
    without any division by zero."""
    zero_fit = [{"text": "black coffee", "calories": 0}]

    def _nonzero_logger(text: str, examples=None) -> dict:
        return {"totals": _totals(50)}

    assert score_block("", zero_fit, _USDA, _nonzero_logger)["fit"] == 0.0


def test_fit_gain_exactly_at_margin_ships_despite_float_error() -> None:
    """A fit gain of *exactly* the margin must count as meaningful. Scores come back
    rounded to 3 decimals, so realistic pairs land on the boundary: 0.016 → 0.036 is
    a +0.020 gain, but 0.016 + 0.02 == 0.036000000000000004 in float, so a naive
    ``>=`` wrongly rejects it. The gate must ship it."""
    current = {"usda": 1.0, "fit": 0.016}
    proposed = {"usda": 1.0, "fit": 0.036}  # exactly +0.020, the default margin
    decision = ship_decision(current, proposed)
    assert decision["fit_gain"] is True
    assert decision["ship"] is True


def test_usda_floor_exactly_at_eps_holds_despite_float_error() -> None:
    """A USDA drop of *exactly* eps holds the floor (within ε), not breaches it.
    0.07 → 0.02 is a −0.050 drop, but 0.07 − 0.05 == 0.020000000000000004 in float,
    so a naive ``>=`` wrongly flags a floor breach."""
    current = {"usda": 0.07, "fit": 0.50}
    proposed = {"usda": 0.02, "fit": 0.80}  # exactly −0.050 USDA, big fit win
    decision = ship_decision(current, proposed, eps=0.05)
    assert decision["usda_ok"] is True
    assert decision["ship"] is True


def test_genuine_sub_margin_gain_still_rejected_after_tolerance() -> None:
    """The float tolerance must be far below the 3-decimal score granularity, so a
    real sub-margin gain (+0.019 < 0.020) is still rejected — the fix absorbs
    representation error only, it does not loosen the rule."""
    current = {"usda": 1.0, "fit": 0.700}
    proposed = {"usda": 1.0, "fit": 0.719}  # +0.019, just under the 0.020 margin
    assert ship_decision(current, proposed)["fit_gain"] is False


def test_empty_fit_set_scores_zero_without_dividing_by_zero() -> None:
    """A user with corrections but *zero* confirmed meals yields an empty fit set.
    ``_calorie_accuracy`` must return 0.0 for no cases rather than dividing by
    ``len(cases) == 0`` — a ZeroDivisionError here would crash the whole retune
    scoring loop the moment a brand-new user (no confirmations yet) banks a
    correction. The USDA axis still scores normally from its own non-empty set."""
    scores = score_block("any block", [], _USDA, _stub_logger)
    assert scores["fit"] == 0.0
    assert scores["usda"] == 1.0


def test_retune_cannot_ship_without_a_held_out_fit_set() -> None:
    """ / : the gate ships a retune only if it
    *improves your data* — so with no held-out confirmations to prove fit against,
    a retune must never ship, however good the proposed block looks on USDA. An
    empty fit set scores 0.0 for both current and proposed, so the +fit_delta gain
    is unreachable (0.0 ≥ 0.0 + 0.02 is False) and the gate rejects: personalization
    stays proven on real held-out meals, never vibed on an empty set."""
    current = score_block("", [], _USDA, _stub_logger)
    proposed = score_block("carbs run high preworkout", [], _USDA, _stub_logger)
    decision = ship_decision(current, proposed)
    assert decision["fit_gain"] is False
    assert decision["ship"] is False


def test_confirmations_to_cases_uses_confirmed_calories_as_truth() -> None:
    confirmations = [
        {"meal_text": "oatmeal", "totals": _totals(214)},
        {"meal_text": "salmon", "totals": _totals(481)},
    ]
    cases = confirmations_to_cases(confirmations)
    assert cases == [
        {"text": "oatmeal", "calories": 214},
        {"text": "salmon", "calories": 481},
    ]

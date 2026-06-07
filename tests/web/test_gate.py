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
    assert "no fit improvement" in decision["reason"]


def test_small_usda_dip_is_allowed_within_eps() -> None:
    current = {"usda": 0.90, "fit": 0.50}
    proposed = {"usda": 0.87, "fit": 0.80}  # −0.03 USDA, big fit win
    assert ship_decision(proposed=proposed, current=current, eps=0.05)["ship"] is True


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

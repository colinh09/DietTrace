"""The champion-challenger gate.

Pure scoring + ship-decision functions for the per-user retune: score a
preference block on the USDA set (objective accuracy) and the held-out
confirmation set (personal fit), and decide whether a proposed block beats the
current one. The supervisor *gates*; it never proposes — proposing is the
corrector's job, and the eval here is what makes "accept any feedback" safe (bad
feedback → no fit gain → not shipped).

No LLM and no Phoenix here — scoring runs the injected ``logger_fn`` over cases,
so it's fully offline-testable with a stub logger.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dietrace.web.memory import calories_of

# Default USDA regression floor: a proposed block may cost at most this much
# objective accuracy if it improves personal fit.
DEFAULT_EPS = 0.05

# Minimum personal-fit gain to count as a *meaningful* improvement worth shipping;
# a smaller bump is treated as noise so trivial/contradictory feedback can't ship.
DEFAULT_FIT_DELTA = 0.02

# Float-comparison slack for the ship-rule boundaries. Scores are rounded to 3
# decimals, so a gain/drop of *exactly* the margin (e.g. 0.016 + 0.02) can read as
# just-below due to IEEE-754 error and wrongly reject. This tolerance absorbs that
# representation error while staying far below the 1e-3 score granularity, so a
# genuine sub-margin change is never promoted.
_BOUNDARY_TOL = 1e-9


def _case_score(case: dict[str, Any], estimate: Callable[[str], dict]) -> float:
    """Calorie accuracy of one *estimate* against a case (1.0 exact, 0.0 far off)."""
    expected = case["calories"]
    est = calories_of(estimate(case["text"]).get("totals", []))
    if expected <= 0:
        return 1.0 if est == 0 else 0.0
    return round(max(0.0, 1.0 - abs(est - expected) / expected), 3)


def _calorie_accuracy(
    cases: list[dict[str, Any]], estimate: Callable[[str], dict]
) -> float:
    """Mean calorie accuracy over *cases* (0.0 when there are none)."""
    if not cases:
        return 0.0
    return round(sum(_case_score(c, estimate) for c in cases) / len(cases), 3)


def _run_with_block(
    logger_fn: Callable[..., dict], block_text: str
) -> Callable[[str], dict]:
    """A single-arg estimator that logs each meal with *block_text* injected."""
    examples = [{"preference_block": block_text}] if block_text else []
    return lambda text: logger_fn(text, examples=examples)


def confirmations_to_cases(
    confirmations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn confirmed meals (Input A) into ``{text, calories}`` eval cases — the
    user's confirmed calories are the ground truth the gate scores fit against."""
    return [
        {"text": c["meal_text"], "calories": calories_of(c.get("totals", []))}
        for c in confirmations
    ]


def score_block(
    block_text: str,
    fit_cases: list[dict[str, Any]],
    usda_cases: list[dict[str, Any]],
    logger_fn: Callable[..., dict],
) -> dict[str, float]:
    """Score a block on both axes: ``{usda, fit}`` mean calorie accuracy."""
    run = _run_with_block(logger_fn, block_text)
    return {
        "usda": _calorie_accuracy(usda_cases, run),
        "fit": _calorie_accuracy(fit_cases, run),
    }


def ship_decision(
    current: dict[str, float],
    proposed: dict[str, float],
    eps: float = DEFAULT_EPS,
    fit_delta: float = DEFAULT_FIT_DELTA,
) -> dict[str, Any]:
    """Apply the ship rule: USDA floor (ε) AND a *meaningful* held-out fit gain.

    Ships only when the proposed block keeps objective accuracy within ε of the
    current block AND improves personal fit by at least ``fit_delta`` (a smaller
    bump is treated as noise). Returns the verdict plus a plain reason for
    observability.
    """
    usda_ok = proposed["usda"] >= current["usda"] - eps - _BOUNDARY_TOL
    fit_gain = proposed["fit"] >= current["fit"] + fit_delta - _BOUNDARY_TOL
    ship = usda_ok and fit_gain
    if ship:
        reason = (
            f"fit {current['fit']:.0%} → {proposed['fit']:.0%} "
            f"(≥ +{fit_delta:.0%}) with USDA held "
            f"({proposed['usda']:.0%}, within {eps:.0%})"
        )
    elif not usda_ok:
        reason = (
            f"USDA floor breached: {proposed['usda']:.0%} < "
            f"{current['usda']:.0%} − {eps:.0%}"
        )
    else:
        reason = (
            f"no meaningful fit improvement "
            f"({proposed['fit']:.0%} vs {current['fit']:.0%}, "
            f"needs ≥ +{fit_delta:.0%})"
        )
    return {
        "ship": ship,
        "usda_ok": usda_ok,
        "fit_gain": fit_gain,
        "reason": reason,
        "eps": eps,
        "fit_delta": fit_delta,
    }

"""Live smoke test for the per-user learning loop.

Runs the loop end to end against LIVE Gemini + the real food DB — no HTTP server
needed. It uses the demo seed's corrections + confirmations to:

  1. ask the corrector to propose a preference block (live Gemini),
  2. score the agent WITH vs WITHOUT the block, on the held-out confirmations
     (fit) and a slice of the USDA set (objective accuracy) — live per case,
  3. apply the ship rule and print the verdict.

The thing this answers that offline tests can't: is the preworkout-carbs bias
*real*, and does the block fix it enough to ship?

    set -a && . ./.env && set +a
    uv run python scripts/smoke_learning_loop.py            # fast: 5 USDA cases
    uv run python scripts/smoke_learning_loop.py --usda 16  # fuller USDA floor
"""

from __future__ import annotations

import argparse

from dietrace.agents.nutrition.corrector import propose_preference_block
from dietrace.web.app import _load_usda_eval_cases, default_meal_logger
from dietrace.web.demo_seed import DEMO_CONFIRMATIONS, DEMO_FEEDBACK
from dietrace.web.gate import (
    confirmations_to_cases,
    ship_decision,
)
from dietrace.web.memory import calories_of


def _case_score(case: dict, block: str) -> tuple[float, float]:
    """(estimated_kcal, accuracy) for one case logged with *block* injected."""
    examples = [{"preference_block": block}] if block else []
    est = calories_of(default_meal_logger(case["text"], examples=examples).get("totals", []))
    expected = case["calories"]
    if expected <= 0:
        return est, (1.0 if est == 0 else 0.0)
    return est, round(max(0.0, 1.0 - abs(est - expected) / expected), 3)


def _mean(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 3) if xs else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Live learning-loop smoke test.")
    parser.add_argument("--usda", type=int, default=5, help="how many USDA cases to score")
    args = parser.parse_args()

    feedback = [
        {"id": i + 1, "feedback_text": f["feedback_text"], "weight": f.get("weight", 1.0)}
        for i, f in enumerate(DEMO_FEEDBACK)
    ]
    fit_cases = confirmations_to_cases(DEMO_CONFIRMATIONS)
    usda_cases = _load_usda_eval_cases()[: args.usda]

    print(f"Corrections: {len(feedback)} | held-out confirmations: {len(fit_cases)} | "
          f"USDA cases: {len(usda_cases)}\n")
    for f in feedback:
        print(f"  feedback #{f['id']} (x{f['weight']:g}): {f['feedback_text']}")

    print("\n→ Proposing a preference block (live Gemini)...")
    proposed = propose_preference_block(feedback, current_block="")
    if proposed is None:
        print("✗ corrector returned nothing (check Vertex/ADC + GEMINI env).")
        return
    print("\n── PROPOSED BLOCK ─────────────────────────────────────────────")
    print(proposed.block_text)
    print("\n── RULES ──────────────────────────────────────────────────────")
    for r in proposed.rules:
        print(f"  • {r.rule}  —  {r.rationale}  (from {r.from_feedback})")

    block = proposed.block_text

    def score(cases: list[dict], label: str) -> dict[str, float]:
        print(f"\n── {label} (without → with block) ─────────────────────────")
        before_acc, after_acc = [], []
        for c in cases:
            be, ba = _case_score(c, "")
            ae, aa = _case_score(c, block)
            before_acc.append(ba)
            after_acc.append(aa)
            flag = "↑" if aa > ba else ("↓" if aa < ba else "·")
            print(f"  {flag} {c['text'][:46]:48} exp {c['calories']:>5.0f}  "
                  f"{be:>5.0f}({ba:.0%}) → {ae:>5.0f}({aa:.0%})")
        return {"before": _mean(before_acc), "after": _mean(after_acc)}

    fit = score(fit_cases, "FIT (held-out confirmations)")
    usda = score(usda_cases, "USDA (objective floor)")

    current = {"usda": usda["before"], "fit": fit["before"]}
    after = {"usda": usda["after"], "fit": fit["after"]}
    decision = ship_decision(current, after)

    print("\n── VERDICT ────────────────────────────────────────────────────")
    print(f"  fit  : {current['fit']:.0%} → {after['fit']:.0%}")
    print(f"  usda : {current['usda']:.0%} → {after['usda']:.0%}  (floor ε={decision['eps']:.0%})")
    print(f"  SHIP : {decision['ship']}  —  {decision['reason']}")
    if not decision["ship"] and not decision["fit_gain"]:
        print("\n  No fit gain — either the bias isn't real or the block didn't capture it.")
        print("  Inspect the per-case rows above to see where the block helped/hurt.")


if __name__ == "__main__":
    main()

"""Validate the bodybuilder (protein-portion) persona end to end (live).

Confirmed cold baseline: the agent under-portions "big" protein servings. This
checks the full loop:
  1. corrections → a scoped rule (corrector),
  2. held-out big-protein meals (unseen foods) scale UP with the rule (generalize),
  3. the WHEY-SHAKE hold-out stays standard — a naive "more protein" rule would
     inflate it; the scoped rule must not (the gate-theater money shot),
  4. a non-protein control is untouched (scoping).

    set -a && . ./.env && set +a
    uv run python scripts/validate_bodybuilder.py --runs 2
"""

from __future__ import annotations

import argparse

from dietrace.agents.nutrition.corrector import propose_preference_block
from dietrace.web.app import default_meal_logger

FEEDBACK = [
    {"id": 1, "weight": 2.0,
     "feedback_text": "I eat way bigger protein portions after lifting — my chicken "
                      "is more like 10-12 oz, not a small fillet"},
    {"id": 2, "weight": 1.0,
     "feedback_text": "my post-workout protein servings are about double what you logged"},
]

# Held-out big-protein meals (foods NOT in the corrections, casual language) — the
# rule SHOULD scale these up.
PROTEIN = [
    "a big serving of ground turkey after lifting",
    "a huge grilled chicken thigh dinner post-workout",
    "a large cut of sirloin steak after the gym",
]
# The gate-theater hold-out: 2 scoops of whey is a FIXED ~50g protein. A blanket
# "more protein" rule wrongly inflates it; the scoped rule must leave it alone.
HOLDOUT = "a protein shake with two scoops of whey and water"
# Non-protein control — must be untouched.
CONTROL = "a medium apple as a snack"


def macro(totals, code):
    return next((t["amount"] for t in totals if t["code"] == code), 0.0)


def log(text, block):
    examples = [{"preference_block": block}] if block else []
    r = default_meal_logger(text, examples=examples)
    t = r.get("totals", [])
    return macro(t, "203"), macro(t, "208")  # protein g, kcal


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2)
    args = ap.parse_args()

    prot_lifts, holdout_drifts, ctrl_drifts = [], [], []
    for run in range(1, args.runs + 1):
        proposed = propose_preference_block(FEEDBACK, current_block="")
        if proposed is None:
            print(f"run {run}: corrector None")
            continue
        block = proposed.block_text
        rule = proposed.rules[0].rule if proposed.rules else block[:70]
        print(f"\n── run {run} ──  rule: {rule}")
        for text in PROTEIN:
            (pb, _), (pa, _) = log(text, ""), log(text, block)
            prot_lifts.append(pa - pb)
            print(f"  PROT  {text[:42]:44} P {pb:.0f} → {pa:.0f}  ({pa-pb:+.0f})")
        (hb, _), (ha, _) = log(HOLDOUT, ""), log(HOLDOUT, block)
        holdout_drifts.append(ha - hb)
        flag = "  ⚠ INFLATED" if (ha - hb) > 10 else "  ✓ held"
        print(f"  HOLD  {HOLDOUT[:42]:44} P {hb:.0f} → {ha:.0f}  ({ha-hb:+.0f}){flag}")
        (cb, _), (ca, _) = log(CONTROL, ""), log(CONTROL, block)
        ctrl_drifts.append(ca - cb)
        print(f"  CTL   {CONTROL[:42]:44} P {cb:.0f} → {ca:.0f}  ({ca-cb:+.0f})")

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0

    print("\n" + "═" * 64)
    print(f"PROTEIN lift (big meals)  : avg {avg(prot_lifts):+.0f}g  — want clearly positive")
    print(f"WHEY hold-out drift       : avg {avg(holdout_drifts):+.0f}g  — want ~0 (scoped)")
    print(f"CONTROL drift             : avg {avg(ctrl_drifts):+.0f}g  — want ~0")
    print("═" * 64)


if __name__ == "__main__":
    main()

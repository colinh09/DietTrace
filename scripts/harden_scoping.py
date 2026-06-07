"""Measure the learning loop's reliability across runs (live).

The demo's fragile parts are non-deterministic: does the preference block reliably
(a) lift carbs on UNSEEN preworkout meals (generalization) and (b) leave
non-preworkout meals alone (scoping)? This runs the corrector + logs a panel of
held-out meals with/without the block, N times, and reports the distributions so
we can harden the corrector prompt against the weak spots.

    set -a && . ./.env && set +a
    uv run python scripts/harden_scoping.py --runs 3
"""

from __future__ import annotations

import argparse

from dietrace.agents.nutrition.corrector import propose_preference_block
from dietrace.web.app import default_meal_logger
from dietrace.web.demo_seed import DEMO_FEEDBACK

# Held-out preworkout meals (carb sources NOT in the seeded confirmations) — the
# block SHOULD lift their carbs. Controls are clearly not preworkout — it should
# leave them alone.
PREWORKOUT = [
    "a stack of pancakes with maple syrup before the gym",
    "white rice and grilled chicken before training",
    "a peanut butter and honey sandwich before my workout",
]
CONTROL = [
    "a grilled chicken caesar salad for lunch",
    "scrambled eggs and bacon",
    "a greek yogurt parfait with granola",
]


def carbs(text: str, block: str) -> float:
    examples = [{"preference_block": block}] if block else []
    totals = default_meal_logger(text, examples=examples).get("totals", [])
    return next((t["amount"] for t in totals if t["code"] == "205"), 0.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    feedback = [
        {"id": i + 1, "feedback_text": f["feedback_text"], "weight": f.get("weight", 1.0)}
        for i, f in enumerate(DEMO_FEEDBACK)
    ]

    pre_lifts: list[float] = []
    ctrl_deltas: list[float] = []

    for run in range(1, args.runs + 1):
        proposed = propose_preference_block(feedback, current_block="")
        if proposed is None:
            print(f"run {run}: corrector returned None")
            continue
        block = proposed.block_text
        rule = proposed.rules[0].rule if proposed.rules else block[:60]
        print(f"\n── run {run} ──  rule: {rule}")
        for text in PREWORKOUT:
            b, a = carbs(text, ""), carbs(text, block)
            pre_lifts.append(a - b)
            print(f"  PRE  {text[:44]:46} {b:.0f}g → {a:.0f}g  ({a-b:+.0f})")
        for text in CONTROL:
            b, a = carbs(text, ""), carbs(text, block)
            ctrl_deltas.append(a - b)
            flag = "  ⚠ BLEED" if abs(a - b) > 10 else ""
            print(f"  CTL  {text[:44]:46} {b:.0f}g → {a:.0f}g  ({a-b:+.0f}){flag}")

    def stats(xs):
        return (sum(xs) / len(xs), min(xs), max(xs)) if xs else (0, 0, 0)

    pm, pmin, pmax = stats(pre_lifts)
    cm, cmin, cmax = stats([abs(x) for x in ctrl_deltas])
    print("\n" + "═" * 64)
    print(f"PREWORKOUT lift  : avg {pm:+.0f}g  (min {pmin:+.0f}, max {pmax:+.0f})  "
          f"— want clearly positive")
    print(f"CONTROL  |drift| : avg {cm:.0f}g  (max {cmax:.0f})  — want near 0")
    bleeds = sum(1 for x in ctrl_deltas if abs(x) > 10)
    print(f"CONTROL bleeds (>10g): {bleeds}/{len(ctrl_deltas)}")
    print("═" * 64)


if __name__ == "__main__":
    main()

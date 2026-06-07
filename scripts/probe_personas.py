"""Cold-baseline probe for the candidate persona demos (live).

The reviewer panel's #1 warning: every demo's delta depends on the agent being
naively USDA-literal. Before building a scenario, check the bias is REAL — i.e.
the agent's default estimate actually deviates from the persona's reality:

  - photoshoot-cut: does the agent add phantom cooking OIL/FAT to seared/sautéed
    meals (so a dry-cooking competitor is over-charged on fat)?
  - bodybuilder:    does the agent UNDER-portion "big" protein servings (logging
    a standard ~120-170g when the lifter eats 300g+)?

    set -a && . ./.env && set +a
    uv run python scripts/probe_personas.py
"""

from __future__ import annotations

from dietrace.web.app import default_meal_logger


def macro(totals, code):
    return next((t["amount"] for t in totals if t["code"] == code), 0.0)


def log(text: str) -> dict:
    r = default_meal_logger(text, examples=[])
    return r


def show(text: str) -> None:
    r = log(text)
    totals = r.get("totals", [])
    items = r.get("per_item", [])
    print(f"\n  “{text}”")
    for it in items:
        f = macro(it.get("nutrients", []), "204")
        print(f"     {it['grams']:.0f}g  {macro(it.get('nutrients', []), '208'):.0f}kcal  "
              f"P{macro(it.get('nutrients', []), '203'):.0f} F{f:.0f}  {it['description'][:46]}")
    print(f"     TOTAL  {macro(totals,'208'):.0f}kcal · P{macro(totals,'203'):.0f} "
          f"· C{macro(totals,'205'):.0f} · F{macro(totals,'204'):.0f}")


PHOTOSHOOT = [
    "pan-seared chicken breast with sauteed green beans",
    "a grilled steak with roasted broccoli",
    "scrambled eggs with sauteed spinach",
]
BODYBUILDER = [
    "a big post-lift chicken breast with white rice",
    "my usual large grilled salmon fillet with sweet potato",
    "two big chicken breasts and rice after the gym",
]


def main() -> None:
    print("═" * 64)
    print("PHOTOSHOOT-CUT — does the agent add phantom oil/fat? (look at F)")
    print("═" * 64)
    for m in PHOTOSHOOT:
        show(m)
    print("\n" + "═" * 64)
    print("BODYBUILDER — does it under-portion 'big' protein? (look at grams)")
    print("═" * 64)
    for m in BODYBUILDER:
        show(m)


if __name__ == "__main__":
    main()

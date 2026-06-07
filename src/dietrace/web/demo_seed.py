"""Demo seed fixtures for POST /demo/seed.

The fixtures are REAL agent output: each visible meal was logged through the live
pipeline (parse → USDA lookup → portion estimate → online eval) and its exact
``per_item`` / ``totals`` / ``trace`` / quality eval captured into a per-persona
JSON file. Nothing here is hand-authored — the confidence is the genuine mean of
the four eval axes, so the "why this confidence" breakdown adds up. Loading the
canned data keeps /demo/seed deterministic and offline (no Gemini call, no spend).

Two selectable personas (the persona loader, ): an **endurance runner** who
under-logs her training carbs, and a **bodybuilder** who under-logs his post-lift
protein portions. Each ships a visible day + the learning-loop seed (confirmed
meals as the held-out gate set + a couple of corrections) so a judge can hit
"retune" immediately and watch the gate ship a persona-specific rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DIR = Path(__file__).parent


def _load_meals(filename: str) -> list[dict[str, Any]]:
    """Load a persona's captured visible day: each meal is ``{text, totals,
    detail}`` — the same shape ``/demo/seed`` feeds to ``log_store.add``."""
    data = json.loads((_DIR / filename).read_text(encoding="utf-8"))
    return data["meals"]


def _en(kcal: float) -> list[dict[str, Any]]:
    """A totals list carrying only energy (the gate scores fit on calories)."""
    return [{"code": "208", "name": "Energy", "amount": kcal, "unit": "kcal"}]


@dataclass(frozen=True)
class Persona:
    """One selectable demo persona: a visible day + a learning-loop seed."""

    key: str
    label: str           # short name for the picker ("Endurance runner")
    blurb: str           # one-line description for the picker
    goals: dict[str, float]
    goal_rationale: str
    # The on-screen under-count to correct — a substring of one visible meal,
    # plus a plain-words description of the deviation, for the explainer modal.
    hook_meal: str
    hook_note: str
    # What a retune should learn (shown in the explainer so the payoff is clear).
    learns: str
    # The user's freeform "goals + eating style" — standing context for the
    # corrector, so its rules reflect who this person is.
    profile: str = ""
    meals: list[dict[str, Any]] = field(default_factory=list)
    confirmations: list[dict[str, Any]] = field(default_factory=list)
    feedback: list[dict[str, Any]] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Persona A — Endurance runner (CARBS). The big plate of spaghetti is logged at
# ~196 kcal, the visible carb under-count to correct.
# ──────────────────────────────────────────────────────────────────────────────

RUNNER = Persona(
    key="runner",
    label="Endurance runner",
    blurb="Carbs up big before runs, eats heavy protein to recover after.",
    goals={"208": 2400.0, "203": 150.0, "205": 300.0, "204": 70.0},
    goal_rationale=(
        "Sample targets for a marathon runner (~2 400 kcal/day, carb-forward with "
        "real protein needs). The agent under-counts her around training — both her "
        "pre-run carbs and her post-run recovery protein. Correct one in plain "
        "words, then re-tune to watch it learn the pattern."
    ),
    hook_meal="spaghetti",
    hook_note=(
        "Two visible under-counts: the big plate of spaghetti before her run "
        "(~196 kcal — her pre-run carbs) and the post-run beef chili (~14 g "
        "protein — her recovery protein). Correct either, then re-tune."
    ),
    learns="Around training her portions run big — carbs before runs, protein after.",
    profile=(
        "I'm a marathon runner in a lean cut. I carb-load hard before long runs "
        "and races, and I eat big protein portions after a run to recover and hold "
        "muscle while I'm burning a lot of mileage."
    ),
    meals=_load_meals("demo_seed_data.json"),
    # The dataset tells one coherent story on TWO axes (validated live, real cold
    # under-counts): pre-run she carb-loads for performance; post-run she eats
    # heavy protein to recover and hold muscle. Her TRUE intake (held-out ground
    # truth) sits well above the agent's default servings on both — except the
    # plain lunch guard, which the scoped rules must leave alone.
    confirmations=[
        # Carb-loading before runs — agent under-counts (cold ~242-265 → true high).
        {"meal_text": "a baked potato before a race", "items": [], "totals": _en(560)},
        {"meal_text": "a big bowl of white rice before my long run",
         "items": [], "totals": _en(500)},
        # Recovery protein after runs — agent under-counts (cold ~117-208 → true high).
        {"meal_text": "a large salmon fillet after my long run",
         "items": [], "totals": _en(700)},
        {"meal_text": "a big portion of ground turkey after my long run",
         "items": [], "totals": _en(290)},
        # Plain lunch guard — neither pre- nor post-run; the rules must NOT touch it.
        {"meal_text": "a ham and cheese sandwich for lunch", "items": [], "totals": _en(360)},
    ],
    feedback=[
        # Facet 1: pre-run carbs run high.
        {"feedback_text": "my pre-run oats are way bigger than this — closer to 90 g of carbs",
         "meal_text": "oatmeal before my morning run",
         "weight": 2.0},
        # Facet 2: post-run recovery protein runs high.
        {"feedback_text": "after a long run I eat way more protein to recover — almost double",
         "meal_text": "grilled chicken after my long run"},
    ],
)


# ──────────────────────────────────────────────────────────────────────────────
# Persona B — Bodybuilder (PROTEIN portions). The "big serving of ground turkey
# after lifting" logs at ~28 g protein, the visible post-lift under-count.
# ──────────────────────────────────────────────────────────────────────────────

BODYBUILDER = Persona(
    key="bodybuilder",
    label="Bodybuilder",
    blurb="Under-logs his post-lift protein portions — teach it his big servings.",
    goals={"208": 3000.0, "203": 220.0, "205": 300.0, "204": 80.0},
    goal_rationale=(
        "Sample targets for a bodybuilder in a lean bulk (~3 000 kcal/day, "
        "protein-forward). The agent under-portions his post-lift protein — "
        "correct one in plain words, then re-tune to watch it learn his "
        "after-lifting servings."
    ),
    hook_meal="ground turkey",
    hook_note=(
        "The big serving of ground turkey after lifting logged at ~28 g protein "
        "— a small portion's worth. That's the on-screen under-count to correct."
    ),
    learns="After lifting, his protein portions are about double the default.",
    profile=(
        "I'm a bodybuilder on a lean bulk. I lift heavy and eat large protein "
        "portions after training to grow — I track protein closely and my "
        "post-lift servings are bigger than a normal plate."
    ),
    meals=_load_meals("demo_seed_bodybuilder.json"),
    confirmations=[
        # Post-lift protein meals the agent under-portions (the pattern to learn);
        # the user's true (higher) intake is the held-out ground truth.
        {"meal_text": "a big serving of ground turkey after lifting",
         "items": [], "totals": _en(600)},
        {"meal_text": "a large sirloin steak after the gym",
         "items": [], "totals": _en(650)},
        {"meal_text": "a big chicken thigh dinner post-workout",
         "items": [], "totals": _en(550)},
        # Non-post-workout guards — the learned rule must NOT change these.
        {"meal_text": "a turkey sandwich for lunch", "items": [], "totals": _en(450)},
        {"meal_text": "a medium apple as a snack", "items": [], "totals": _en(95)},
    ],
    feedback=[
        {"feedback_text": "I eat way bigger protein portions after lifting — my "
                          "chicken is more like 10-12 oz, not a small fillet",
         "meal_text": "a big serving of ground turkey with rice after lifting",
         "weight": 2.0},
        {"feedback_text": "my post-workout protein servings are about double what you logged",
         "meal_text": "a large sirloin steak with a baked sweet potato for dinner"},
    ],
)


PERSONAS: dict[str, Persona] = {p.key: p for p in (RUNNER, BODYBUILDER)}
DEFAULT_PERSONA = RUNNER.key


def get_persona(key: str | None) -> Persona:
    """The requested persona, falling back to the default for unknown keys."""
    return PERSONAS.get(key or DEFAULT_PERSONA, RUNNER)


# Backwards-compatible module-level aliases = the default (runner) persona, kept
# for the tests + scripts that import them directly.
DEMO_GOALS: dict[str, float] = RUNNER.goals
DEMO_GOAL_RATIONALE = RUNNER.goal_rationale
DEMO_MEALS: list[dict[str, Any]] = RUNNER.meals
DEMO_CONFIRMATIONS: list[dict[str, Any]] = RUNNER.confirmations
DEMO_FEEDBACK: list[dict[str, Any]] = RUNNER.feedback

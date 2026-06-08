"""Nutrition agent assembly: tools → ADK Agent → Runner.

This module wires the five pipeline tools — ``parse_meal`` → ``search_nutrition``
→ ``estimate_portion`` → ``log_entry`` → ``check_against_goals`` — into
an ADK ``Agent`` named ``dietrace_nutrition`` plus a ``Runner`` over an
``InMemorySessionService``, mirroring axon's worker construction.

Each underlying tool function takes domain objects (a ``FoodRepository``, a
Gemini client, ``Food``/``Nutrient`` models). The LLM, however, calls tools with
plain JSON-friendly arguments, so :func:`build_nutrition_tools` wraps each one in
a closure that binds the repository/client and translates to and from those
domain objects — looking foods up by the reproducible ``fdc_id`` the agent
carries through the pipeline. The wrappers stay fail-soft like the tools
they delegate to: a missing food degrades to an empty/``None`` result rather than
raising, so the agent loop keeps running.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool

from dietrace.agents.nutrition.check_against_goals import NutrientGoal
from dietrace.agents.nutrition.check_against_goals import (
    check_against_goals as _check_against_goals,
)
from dietrace.agents.nutrition.estimate_portion import PortionEstimate
from dietrace.agents.nutrition.estimate_portion import (
    estimate_portion as _estimate_portion,
)
from dietrace.agents.nutrition.log_entry import MealItem
from dietrace.agents.nutrition.log_entry import log_entry as _log_entry
from dietrace.agents.nutrition.parse_meal import parse_meal as _parse_meal
from dietrace.agents.nutrition.search_nutrition import (
    search_nutrition as _search_nutrition,
)
from dietrace.llm.config import GEMINI_MODEL
from dietrace.nutrition.models import Nutrient
from dietrace.nutrition.repository import FoodRepository
from dietrace.observability.phoenix import init_tracer

AGENT_NAME = "dietrace_nutrition"
APP_NAME = "dietrace-nutrition"

_INSTRUCTION_PATH = Path(__file__).parent / "instruction.md"


def _load_instruction() -> str:
    """Read the agent instruction from ``instruction.md``."""
    return _INSTRUCTION_PATH.read_text(encoding="utf-8")


def build_nutrition_tools(
    repository: FoodRepository, client: Any | None = None
) -> list[FunctionTool]:
    """Wrap the five pipeline tools as ADK ``FunctionTool``s.

    *repository* backs the deterministic lookups; *client* is the Gemini client
    for ``parse_meal`` (injectable for tests, built lazily by ``parse_meal`` when
    omitted). The tools are returned in the  pipeline order and present the
    JSON-friendly signatures the LLM calls them with — foods are addressed by the
    reproducible ``fdc_id`` returned from ``search_nutrition``.
    """

    def parse_meal(text: str) -> list[dict]:
        """Parse a free-text meal into structured items.

        Args:
            text: The meal described in natural language.

        Returns:
            A list of ``{"food", "quantity", "unit"}`` items, empty if nothing
            could be parsed.
        """
        return [item.model_dump() for item in _parse_meal(text, client=client).items]

    def search_nutrition(food: str) -> dict | None:
        """Look a food up in the nutrition database.

        Args:
            food: The bare food name to resolve.

        Returns:
            ``{"fdc_id", "description", "data_type", "per_100g"}`` for the best
            match, or ``None`` when nothing matches.
        """
        match = _search_nutrition(repository, food)
        return match.model_dump() if match is not None else None

    def estimate_portion(fdc_id: int, quantity: float, unit: str) -> dict:
        """Estimate the gram weight of a household portion of a food.

        Args:
            fdc_id: The food's identifier from ``search_nutrition``.
            quantity: How many units were eaten (e.g. 0.5 for half).
            unit: The household measure (e.g. "slice", "cup", "each").

        Returns:
            ``{"grams", "source", "confidence"}``; ``grams`` is ``None`` for an
            unknown food or unresolvable unit.
        """
        food = repository.get(fdc_id)
        if food is None:
            return PortionEstimate(grams=None, source="unknown", confidence=0.0).model_dump()
        return _estimate_portion(food, quantity, unit).model_dump()

    def log_entry(items: list[dict]) -> dict:
        """Compute per-item and total nutrients for a gram-resolved meal.

        Args:
            items: A list of ``{"fdc_id", "grams"}`` foods to total. Foods that
                cannot be resolved are skipped.

        Returns:
            ``{"per_item", "totals"}`` of scaled nutrient panels.
        """
        meal_items: list[MealItem] = []
        for item in items:
            food = repository.get(int(item["fdc_id"]))
            if food is None:
                continue
            meal_items.append(MealItem(food=food, grams=float(item["grams"])))
        return _log_entry(meal_items).model_dump()

    def check_against_goals(totals: list[dict], goals: list[dict]) -> dict:
        """Compare meal totals to the user's daily goals.

        Args:
            totals: Nutrient totals as ``{"code", "name", "amount", "unit"}``.
            goals: Daily goals as ``{"code", "name", "target", "unit"}``.

        Returns:
            ``{"statuses"}`` — one over/under/within status per goal.
        """
        nutrient_totals = [Nutrient.model_validate(total) for total in totals]
        nutrient_goals = [NutrientGoal.model_validate(goal) for goal in goals]
        return _check_against_goals(nutrient_totals, nutrient_goals).model_dump()

    return [
        FunctionTool(parse_meal),
        FunctionTool(search_nutrition),
        FunctionTool(estimate_portion),
        FunctionTool(log_entry),
        FunctionTool(check_against_goals),
    ]


class NutritionAgent:
    """The assembled nutrition agent: tools, ADK ``Agent``, and ``Runner``.

    Construction is offline-safe — the ADK ``Agent``/``Runner`` take the model as
    a plain string and build no client until a turn is run — so the assembly can
    be exercised in tests with a mocked Gemini client.

    The agent exposes two capability surfaces:

    * **Meal-logging tools** (``self.tools``) — the five ADK ``FunctionTool``s the
      LLM calls through the runner: ``parse_meal`` → ``search_nutrition`` →
      ``estimate_portion`` → ``log_entry`` → ``check_against_goals``.

    * **Macro planning** (``self.plan_macros``) — a direct Python method that
      wraps the macro-planning service under the same agent identity, sharing the
      Phoenix tracing spine that ``build_nutrition_agent`` initialises (,
      ).  It is not an ADK FunctionTool so the runner's tool
      contract (five tools, pipeline order) is unchanged.
    """

    def __init__(
        self,
        repository: FoodRepository,
        client: Any | None = None,
        *,
        instruction: str | None = None,
    ) -> None:
        self.repository = repository
        self.tools = build_nutrition_tools(repository, client)
        self.instruction = instruction if instruction is not None else _load_instruction()
        self.agent = Agent(
            name=AGENT_NAME,
            model=GEMINI_MODEL,
            instruction=self.instruction,
            tools=self.tools,
        )
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            app_name=APP_NAME,
            agent=self.agent,
            session_service=self.session_service,
        )

    def plan_macros(
        self,
        *,
        preset: str | None = None,
        age: int | None = None,
        sex: str | None = None,
        height_cm: float | None = None,
        weight_kg: float | None = None,
        activity: str | None = None,
        goal: str | None = None,
        preference: str | None = None,
        ai_help: bool = False,
        macro_client: Any | None = None,
    ) -> dict:
        """Plan daily macros under the nutritionist-agent identity.

        Accepts either a *preset* key (the privacy-friendly no-profile path) or a
        full profile (the formula/AI-personalised path).  Shares the Phoenix
        tracing spine initialised by :func:`build_nutrition_agent` — any Gemini
        call made via *macro_client* is instrumented by the same provider as the
        meal-logging tools.

        Does not persist anything; callers save the result via the GoalStore.

        Args:
            preset: One of ``"cut"``, ``"maintain"``, ``"bulk"`` for a
                preset plan.  Mutually exclusive with profile fields.
            age: Years of age (profile path).
            sex: ``"male"`` or ``"female"`` (profile path).
            height_cm: Height in centimetres (profile path).
            weight_kg: Body weight in kilograms (profile path).
            activity: Activity level key (profile path).
            goal: ``"cut"``, ``"maintain"``, or ``"bulk"`` (profile path).
            preference: Optional dietary preference hint (profile path).
            ai_help: When ``True``, personalise via Gemini after the formula
                baseline (profile path only).
            macro_client: Injectable Gemini client for *ai_help*; built lazily
                when omitted.

        Returns:
            A ``MacroPlan.model_dump()`` dict with ``targets``, ``rationale``,
            ``source``, ``steps``, ``clamped``, and ``eval`` keys.

        Raises:
            KeyError: When *preset* is not a recognised key.
            pydantic.ValidationError: When required profile fields are missing.
        """
        from dietrace.macros.compute import compute_targets
        from dietrace.macros.eval import evaluate_macro_plan
        from dietrace.macros.models import MacroPlan, MacroProfile
        from dietrace.macros.personalize import personalize_plan
        from dietrace.macros.presets import preset_plan

        # Sentinel profile for evaluate_macro_plan on the preset path: weight_kg=0
        # causes the protein g/kg safety axis to be skipped (no profile submitted).
        _sentinel = MacroProfile(
            age=25,
            sex="male",
            height_cm=170.0,
            weight_kg=0.0,
            activity="moderate",
            goal="maintain",
        )

        if preset is not None:
            plan = preset_plan(preset)  # raises KeyError on unknown preset
            eval_result = evaluate_macro_plan(_sentinel, plan)
        else:
            profile = MacroProfile(
                age=age,
                sex=sex,
                height_cm=height_cm,
                weight_kg=weight_kg,
                activity=activity,
                goal=goal,
                preference=preference,
                ai_help=ai_help,
            )
            plan = compute_targets(profile)
            if ai_help:
                plan = personalize_plan(profile, plan.targets, client=macro_client)
            eval_result = evaluate_macro_plan(profile, plan)

        return MacroPlan(
            targets=plan.targets,
            rationale=plan.rationale,
            source=plan.source,
            steps=plan.steps,
            clamped=plan.clamped,
            eval=eval_result,
        ).model_dump()


def build_nutrition_agent(
    repository: FoodRepository,
    client: Any | None = None,
    *,
    service_name: str = APP_NAME,
) -> NutritionAgent:
    """Build a :class:`NutritionAgent`, initializing Phoenix tracing if configured.

    Tracing is best-effort: ``init_tracer`` is a no-op without
    ``PHOENIX_API_KEY``, and any setup error (e.g. a misconfigured collector
    endpoint) is swallowed here — exactly as the web lifespan does — so a tracing
    problem never blocks agent construction offline, in tests, or in production.
    """
    try:
        init_tracer(service_name)
    except Exception:
        pass
    return NutritionAgent(repository, client)

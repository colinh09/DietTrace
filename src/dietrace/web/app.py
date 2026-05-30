"""FastAPI surface for DietTrace.

One Cloud Run service: log a meal, read history, see the aggregate analysis, and
inspect the agent's reasoning spans from the in-process trace buffer. The
meal-logging callable is injectable so the API is testable offline; the default
wires the live ADK nutrition agent. Tracing init is best-effort.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from dietrace.observability.phoenix import init_tracer
from dietrace.observability.trace_buffer import get_buffer
from dietrace.web.store import MealLogStore

SERVICE_NAME = "dietrace-web"

MealLogger = Callable[[str], dict]


class LogRequest(BaseModel):
    """A meal to log, in natural language."""

    text: str


def default_meal_logger(text: str) -> dict:  # pragma: no cover — live agent + Gemini
    """Run the live ADK nutrition agent over *text* and parse its logged output.

    The deferred live wiring: builds the agent over the food DB and runs
    a turn, returning the agent's structured ``{per_item, totals}`` output.
    """
    import asyncio

    from google.genai import types

    from dietrace.agents.nutrition.agent import APP_NAME, build_nutrition_agent
    from dietrace.nutrition.repository import FoodRepository

    repo = FoodRepository(os.environ.get("DIETRACE_FOOD_DB", "data/food.sqlite"))
    agent = build_nutrition_agent(repo)

    async def _run() -> str:
        session = await agent.session_service.create_session(
            app_name=APP_NAME, user_id="web"
        )
        message = types.Content(role="user", parts=[types.Part(text=text)])
        final = ""
        async for event in agent.runner.run_async(
            user_id="web", session_id=session.id, new_message=message
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final = event.content.parts[0].text or ""
        return final

    return _parse_agent_output(asyncio.run(_run()))


def _parse_agent_output(raw: str) -> dict[str, Any]:
    """Parse the agent's final message into ``{per_item, totals}``.

    Tolerant of the model wrapping its JSON in a ```` ```json ```` fence (which it
    does in practice). Falls back to an empty result carrying the ``raw`` text
    when the output is not valid JSON, so a bad turn never raises.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]  # drop the opening ``` / ```json line
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"totals": [], "per_item": [], "raw": raw}
    parsed.setdefault("totals", [])
    parsed.setdefault("per_item", [])
    return parsed


def _aggregate(meals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sum nutrient totals across logged meals, keyed by USDA code."""
    agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"amount": 0.0, "name": "", "unit": ""}
    )
    for meal in meals:
        for nutrient in meal["totals"]:
            entry = agg[nutrient["code"]]
            entry["amount"] += float(nutrient.get("amount", 0.0))
            entry["name"] = nutrient.get("name", "")
            entry["unit"] = nutrient.get("unit", "")
    return [{"code": code, **vals} for code, vals in agg.items()]


def create_app(
    *,
    meal_logger: MealLogger | None = None,
    store: MealLogStore | None = None,
    tracer_init: Callable[[str], Any] = init_tracer,
) -> FastAPI:
    """Build the DietTrace FastAPI app with injectable logger/store (for tests)."""
    log_store = store or MealLogStore(os.environ.get("DIETRACE_LOG_DB", "data/log.sqlite"))
    logger_fn = meal_logger or default_meal_logger

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            tracer_init(SERVICE_NAME)
        except Exception:
            # Tracing is best-effort; never block boot on it.
            pass
        yield

    app = FastAPI(title="DietTrace", lifespan=lifespan)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/log")
    def log_meal(req: LogRequest) -> dict[str, Any]:
        result = logger_fn(req.text)
        totals = result.get("totals", [])
        entry_id = log_store.add(req.text, totals)
        return {"id": entry_id, **result}

    @app.get("/history")
    def history(limit: int = 50) -> dict[str, Any]:
        return {"meals": log_store.list(limit)}

    @app.get("/analysis")
    def analysis() -> dict[str, Any]:
        meals = log_store.list(1000)
        return {
            "meal_count": len(meals),
            "totals": _aggregate(meals),
            "traces_buffered": get_buffer().trace_count(),
        }

    @app.get("/reasoning/{trace_id}")
    def reasoning(trace_id: str) -> dict[str, Any]:
        return {"trace_id": trace_id, "spans": get_buffer().get_trace(trace_id)}

    return app


# Module-level ASGI app for `uvicorn dietrace.web.app:app` (the Cloud Run entrypoint).
app = create_app()

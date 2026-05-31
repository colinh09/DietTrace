"""FastAPI surface for DietTrace.

One Cloud Run service: log a meal, read history, see the aggregate analysis, and
inspect the agent's reasoning spans from the in-process trace buffer. The
meal-logging callable is injectable so the API is testable offline; the default
runs one Gemini parse then the deterministic pipeline. Tracing is best-effort (§8).
"""

from __future__ import annotations

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


def default_meal_logger(text: str) -> dict:  # pragma: no cover — live Gemini call
    """Production ``/log`` path: one Gemini parse, then the deterministic pipeline.

    Gemini parses the meal into items; ``log_meal`` then runs search → portion →
    calculation deterministically against the food DB, returning the
    ``{per_item, totals}`` the web layer and evaluators read.
    """
    from dietrace.agents.nutrition.orchestrator import log_meal
    from dietrace.nutrition.repository import FoodRepository

    repository = FoodRepository(os.environ.get("DIETRACE_FOOD_DB", "data/food.sqlite"))
    return log_meal(text, repository).model_dump()


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


def _build_trace(
    per_item: list[dict[str, Any]],
    totals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reconstruct the agent's ordered steps for the ``/log`` response.

    Deterministic and LLM-free: ``parse_meal`` → for each logged food
    ``search_nutrition`` (the matched USDA food + its ``fdc_id``) →
    ``estimate_portion`` (grams) → ``log_entry`` (the summed totals). Rebuilt from
    the structured ``per_item`` the pipeline already returns, so it adds no model
    calls — it just names, in order, what the agent did to produce the numbers.
    """
    foods = [item.get("description") or item.get("name") for item in per_item]
    trace: list[dict[str, Any]] = [
        {
            "step": "parse_meal",
            "foods": foods,
            "summary": f"Parsed {len(foods)} food(s): "
            + ", ".join(str(food) for food in foods),
        }
    ]
    for item in per_item:
        food = item.get("description") or item.get("name")
        fdc_id = item.get("fdc_id", item.get("id"))
        grams = item.get("grams")
        trace.append(
            {
                "step": "search_nutrition",
                "food": food,
                "matched": food,
                "fdc_id": fdc_id,
                "summary": f"Matched '{food}' to USDA food {fdc_id}",
            }
        )
        trace.append(
            {
                "step": "estimate_portion",
                "food": food,
                "grams": grams,
                "summary": f"Estimated {grams} g for '{food}'",
            }
        )
    trace.append(
        {
            "step": "log_entry",
            "totals": totals,
            "summary": f"Logged {len(per_item)} item(s) into "
            f"{len(totals)} nutrient total(s)",
        }
    )
    return trace


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
        per_item = result.get("per_item", [])
        entry_id = log_store.add(req.text, totals)
        return {"id": entry_id, **result, "trace": _build_trace(per_item, totals)}

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

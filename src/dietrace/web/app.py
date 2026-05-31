"""FastAPI surface for DietTrace.

One Cloud Run service: log a meal, read history, see the aggregate analysis, and
inspect the agent's reasoning spans from the in-process trace buffer. The
meal-logging callable is injectable so the API is testable offline; the default
runs one Gemini parse then the deterministic pipeline. Tracing is best-effort (§8).
"""

from __future__ import annotations

import datetime
import json
import os
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from dietrace.observability.phoenix import init_tracer
from dietrace.observability.trace_buffer import get_buffer
from dietrace.web.accuracy import accuracy_report, phoenix_dashboard_url
from dietrace.web.feedback import (
    FEEDBACK_DATASET,
    Correction,
    FeedbackPusher,
    FeedbackStore,
    corrected_expected,
    phoenix_push,
    to_example,
)
from dietrace.web.goals import load_goals
from dietrace.web.identity import current_user
from dietrace.web.memory import build_memory, calories_of, sum_totals
from dietrace.web.store import MealLogStore
from dietrace.web.stores import build_stores

SERVICE_NAME = "dietrace-web"

# Where the Next frontend is served from; comma-separated origins, env-overridable
# so deploys can add their real domain.
DEFAULT_CORS_ORIGINS = "http://localhost:3000"

# A small beat between the fast deterministic stream steps so the UI can show them
# arriving one at a time (the parse step is naturally slow; these are instant).
_STREAM_PACE = float(os.environ.get("DIETRACE_STREAM_PACE", "0.18"))

MealLogger = Callable[..., dict]
MealStreamer = Callable[..., Iterator[dict]]


def _cors_origins() -> list[str]:
    """Allowed cross-origin callers, from ``DIETRACE_CORS_ORIGINS`` (default localhost:3000)."""
    raw = os.environ.get("DIETRACE_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


class LogRequest(BaseModel):
    """A meal to log, in natural language.

    ``date`` is the client's local calendar day (YYYY-MM-DD); when given it is the
    day the meal is filed under, so the day boundary follows the user's timezone
    rather than the server's UTC day.
    """

    text: str
    date: str | None = None


class CorrectionItem(BaseModel):
    """One kept item of a corrected meal: the user adjusted its portion (or left it).

    ``nutrients`` is the item's panel as logged (scaled to ``original_grams``); the
    server rescales it to ``corrected_grams``. Items the user removed (e.g. a
    double-counted dish) simply aren't sent.
    """

    description: str
    fdc_id: int = 0
    original_grams: float
    corrected_grams: float
    nutrients: list[dict[str, Any]] = []


class MealCorrection(BaseModel):
    """A user's corrected version of a logged meal — the new ground truth for it."""

    meal_text: str
    items: list[CorrectionItem]


def default_meal_logger(
    text: str, examples: list[dict] | None = None
) -> dict:  # pragma: no cover — live Gemini call
    """Production ``/log`` path: one Gemini parse, then the deterministic pipeline.

    Gemini parses the meal into items (steered by the user's few-shot *examples*
    when given); ``log_meal`` then runs search → portion → calculation
    deterministically against the food DB, returning the
    ``{per_item, totals}`` the web layer and evaluators read.
    """
    from dietrace.agents.nutrition.orchestrator import log_meal
    from dietrace.nutrition.repository import FoodRepository

    repository = FoodRepository(os.environ.get("DIETRACE_FOOD_DB", "data/food.sqlite"))
    return log_meal(text, repository, examples=examples).model_dump()


def default_meal_streamer(
    text: str, examples: list[dict] | None = None
) -> Iterator[dict]:  # pragma: no cover — live Gemini
    """Production ``/log/stream`` path: the live agent pipeline as an event stream."""
    from dietrace.agents.nutrition.orchestrator import stream_meal
    from dietrace.nutrition.repository import FoodRepository

    repository = FoodRepository(os.environ.get("DIETRACE_FOOD_DB", "data/food.sqlite"))
    yield from stream_meal(text, repository, examples=examples)


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


def _goals_progress(
    totals: list[dict[str, Any]],
    goals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Per-macro target, consumed, and remaining-vs-target.

    For each daily goal, look up the aggregated total for its USDA code (0 when the
    day has none) and report ``remaining = target − consumed``.
    """
    by_code = {n["code"]: float(n.get("amount", 0.0)) for n in totals}
    progress: list[dict[str, Any]] = []
    for goal in goals:
        consumed = by_code.get(goal["code"], 0.0)
        progress.append(
            {**goal, "consumed": consumed, "remaining": goal["target"] - consumed}
        )
    return progress


def _recall_step() -> dict[str, Any]:
    """The trace step shown when a meal is served from the user's corrections."""
    return {
        "step": "recall",
        "status": "done",
        "summary": "recalled from your past correction — no guessing needed",
    }


def _rescale_item(item: CorrectionItem) -> dict[str, Any]:
    """A corrected item: its panel rescaled from the logged to the corrected grams."""
    factor = item.corrected_grams / item.original_grams if item.original_grams else 0.0
    nutrients = [
        {**n, "amount": round(float(n.get("amount", 0.0)) * factor, 2)}
        for n in item.nutrients
    ]
    return {
        "fdc_id": item.fdc_id,
        "description": item.description,
        "grams": item.corrected_grams,
        "nutrients": nutrients,
    }


def _meal_example(
    meal_text: str, items: list[dict[str, Any]], totals: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Render a corrected meal as a Phoenix (input, output, metadata) example."""
    by_code = {t["code"]: t["amount"] for t in totals}
    out = {
        "grams": round(sum(i["grams"] for i in items), 1),
        "calories": round(by_code.get("208", 0.0), 1),
        "protein_g": round(by_code.get("203", 0.0), 1),
        "fat_g": round(by_code.get("204", 0.0), 1),
        "carb_g": round(by_code.get("205", 0.0), 1),
    }
    return {"text": meal_text}, out, {"source": "user_meal_correction", "items": len(items)}


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
    """Mean calorie accuracy of *estimate* over *cases* — a before/after number."""
    if not cases:
        return 0.0
    return round(sum(_case_score(c, estimate) for c in cases) / len(cases), 3)


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
        if fdc_id == 0:
            # fdc_id 0 marks a grounded web lookup — the food USDA didn't carry.
            trace.append(
                {
                    "step": "web_search",
                    "food": food,
                    "matched": food,
                    "summary": f"Searched the web for '{food}' (not in USDA)",
                }
            )
        else:
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
    meal_streamer: MealStreamer | None = None,
    store: MealLogStore | None = None,
    feedback_store: FeedbackStore | None = None,
    memory: Any | None = None,
    feedback_pusher: FeedbackPusher = phoenix_push,
    tracer_init: Callable[[str], Any] = init_tracer,
    goals_loader: Callable[[], list[dict[str, Any]]] = load_goals,
) -> FastAPI:
    """Build the DietTrace FastAPI app with injectable logger/store (for tests)."""
    if store is not None and feedback_store is not None:
        log_store, corrections = store, feedback_store
    else:
        default_meals, default_feedback = build_stores()
        log_store = store or default_meals
        corrections = feedback_store or default_feedback
    learning = memory or build_memory()
    logger_fn = meal_logger or default_meal_logger
    streamer_fn = meal_streamer or default_meal_streamer

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            tracer_init(SERVICE_NAME)
        except Exception:
            # Tracing is best-effort; never block boot on it.
            pass
        yield

    app = FastAPI(title="DietTrace", lifespan=lifespan)

    # Let the Next frontend call the API cross-origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/log")
    def log_meal(req: LogRequest, user: str = Depends(current_user)) -> dict[str, Any]:
        recalled = learning.recall(user, req.text)
        if recalled is not None:
            per_item, totals = recalled["per_item"], recalled["totals"]
            entry_id = log_store.add(req.text, totals, date=req.date, user_id=user)
            return {
                "id": entry_id,
                "per_item": per_item,
                "totals": totals,
                "recalled": True,
                "trace": [_recall_step()] + _build_trace(per_item, totals),
            }
        result = logger_fn(req.text, examples=learning.examples(user))
        totals = result.get("totals", [])
        per_item = result.get("per_item", [])
        entry_id = log_store.add(req.text, totals, date=req.date, user_id=user)
        return {"id": entry_id, **result, "trace": _build_trace(per_item, totals)}

    @app.post("/log/stream")
    def log_meal_stream(
        req: LogRequest, user: str = Depends(current_user)
    ) -> StreamingResponse:
        """Stream the agent's work as Server-Sent Events: one ``step`` event per
        pipeline step, then a ``result`` event (which also persists the meal)."""

        pace = float(os.environ.get("DIETRACE_STREAM_PACE", str(_STREAM_PACE)))
        recalled = learning.recall(user, req.text)

        def cached_events() -> Iterator[str]:
            # A meal the user already corrected — recall it instead of re-running.
            per_item, totals = recalled["per_item"], recalled["totals"]
            yield f"data: {json.dumps(_recall_step())}\n\n"
            entry_id = log_store.add(req.text, totals, date=req.date, user_id=user)
            result = {
                "type": "result",
                "id": entry_id,
                "per_item": per_item,
                "totals": totals,
                "recalled": True,
                "trace": [_recall_step()],
            }
            yield f"data: {json.dumps(result)}\n\n"

        def events() -> Iterator[str]:
            for event in streamer_fn(req.text, examples=learning.examples(user)):
                if event.get("type") == "result":
                    event["id"] = log_store.add(
                        req.text, event.get("totals", []), date=req.date, user_id=user
                    )
                elif pace:
                    time.sleep(pace)  # let fast steps arrive one at a time
                yield f"data: {json.dumps(event)}\n\n"

        stream = cached_events() if recalled is not None else events()
        return StreamingResponse(stream, media_type="text/event-stream")

    @app.delete("/meals/{meal_id}")
    def delete_meal(meal_id: int, user: str = Depends(current_user)) -> dict[str, Any]:
        return {"id": meal_id, "deleted": log_store.delete(meal_id, user_id=user)}

    @app.get("/history")
    def history(
        date: str | None = None, limit: int = 50, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        day = date or datetime.datetime.now(tz=datetime.UTC).date().isoformat()
        return {"date": day, "meals": log_store.list(limit, date=day, user_id=user)}

    @app.get("/goals")
    def goals() -> dict[str, Any]:
        return {"goals": goals_loader()}

    @app.get("/accuracy")
    def accuracy_panel() -> dict[str, Any]:
        """The Arize accuracy story + measured numbers for the web /accuracy page."""
        return accuracy_report()

    @app.post("/feedback")
    def feedback(
        correction: Correction, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        """Record a user portion correction and push it to Phoenix as ground truth.

        The correction becomes a new example in the live eval dataset, so the next
        experiment scores against it — the self-supervision loop, driven from the
        UI. Recording is local-first; the Phoenix push is best-effort.
        """
        expected = corrected_expected(correction)
        corrections.add(correction, expected, user_id=user)
        added_to_arize = feedback_pusher(*to_example(correction))
        return {
            "ok": True,
            "added_to_arize": added_to_arize,
            "total_corrections": corrections.count(user_id=user),
            "dataset": FEEDBACK_DATASET,
            "phoenix_url": phoenix_dashboard_url(),
        }

    @app.get("/feedback")
    def feedback_summary(user: str = Depends(current_user)) -> dict[str, Any]:
        return {
            "total_corrections": corrections.count(user_id=user),
            "dataset": FEEDBACK_DATASET,
            "phoenix_url": phoenix_dashboard_url(),
        }

    @app.post("/correct")
    def correct(
        correction: MealCorrection, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        """Save a user's corrected meal → their memory (cache + few-shot) + Arize.

        Each kept item is rescaled to its corrected portion; removed items (e.g. a
        double-counted dish) are simply dropped. The corrected meal is remembered
        so the same meal is recalled next time and similar meals parse better, and
        it's pushed to Phoenix as ground truth.
        """
        corrected_items = [_rescale_item(item) for item in correction.items]
        totals = sum_totals(corrected_items)
        learning.remember(user, correction.meal_text, corrected_items, totals)
        inp, out, meta = _meal_example(correction.meal_text, corrected_items, totals)
        added_to_arize = feedback_pusher(inp, out, meta)
        return {
            "ok": True,
            "added_to_arize": added_to_arize,
            "corrections": learning.count(user),
            "per_item": corrected_items,
            "totals": totals,
            "phoenix_url": phoenix_dashboard_url(),
        }

    @app.get("/memory")
    def memory_summary(user: str = Depends(current_user)) -> dict[str, Any]:
        return {"corrections": learning.count(user)}

    @app.post("/retune")
    def retune(user: str = Depends(current_user)) -> dict[str, Any]:
        """Re-test the agent on the user's corrected meals, before vs after learning.

        Runs the agent over each meal the user corrected — once as the base agent,
        once with their corrections as few-shot — and scores both against their
        corrected calories. The user triggers this when they want to watch their
        agent improve. Live + costs Gemini calls, so it's on-demand only.
        """
        cases = learning.eval_cases(user)
        if not cases:
            return {"cases": 0, "before": None, "after": None, "improved": False}
        examples = learning.examples(user)
        before = _calorie_accuracy(cases, lambda t: logger_fn(t, examples=[]))
        after = _calorie_accuracy(cases, lambda t: logger_fn(t, examples=examples))
        return {
            "cases": len(cases),
            "before": before,
            "after": after,
            "improved": after >= before,
        }

    @app.post("/retune/stream")
    def retune_stream(user: str = Depends(current_user)) -> StreamingResponse:
        """Re-test as a live stream: one event per corrected meal as it's scored,
        then a summary — so the eval is visible happening, not just a final number."""
        cases = learning.eval_cases(user)
        examples = learning.examples(user)

        def events() -> Iterator[str]:
            befores: list[float] = []
            afters: list[float] = []
            for case in cases:
                base = _case_score(case, lambda t: logger_fn(t, examples=[]))
                tuned = _case_score(case, lambda t: logger_fn(t, examples=examples))
                befores.append(base)
                afters.append(tuned)
                event = {
                    "type": "case",
                    "text": case["text"],
                    "expected_calories": round(case["calories"]),
                    "before": base,
                    "after": tuned,
                }
                yield f"data: {json.dumps(event)}\n\n"
            before = round(sum(befores) / len(befores), 3) if befores else None
            after = round(sum(afters) / len(afters), 3) if afters else None
            summary = {
                "type": "summary",
                "cases": len(cases),
                "before": before,
                "after": after,
                "improved": bool(after is not None and before is not None and after >= before),
            }
            yield f"data: {json.dumps(summary)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/analysis")
    def analysis(
        date: str | None = None, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        # Aggregate only the requested day (default today) so the macro band is
        # the day's intake and stays in sync with date navigation.
        day = date or datetime.datetime.now(tz=datetime.UTC).date().isoformat()
        meals = log_store.list(1000, date=day, user_id=user)
        totals = _aggregate(meals)
        return {
            "date": day,
            "meal_count": len(meals),
            "totals": totals,
            "goals": _goals_progress(totals, goals_loader()),
            "traces_buffered": get_buffer().trace_count(),
        }

    @app.get("/reasoning/{trace_id}")
    def reasoning(trace_id: str) -> dict[str, Any]:
        return {"trace_id": trace_id, "spans": get_buffer().get_trace(trace_id)}

    return app


# Module-level ASGI app for `uvicorn dietrace.web.app:app` (the Cloud Run entrypoint).
app = create_app()

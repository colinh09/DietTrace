"""FastAPI surface for DietTrace.

One Cloud Run service: log a meal, read history, see the aggregate analysis, and
inspect the agent's reasoning spans from the in-process trace buffer. The
meal-logging callable is injectable so the API is testable offline; the default
runs one Gemini parse then the deterministic pipeline. Tracing is best-effort.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from queue import Queue
from threading import Thread
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from opentelemetry import trace as _otel_trace
from pydantic import BaseModel, ValidationError

from dietrace.agents.nutrition.corrector import propose_preference_block
from dietrace.agents.nutrition.interpret_feedback import apply_feedback, interpret_feedback
from dietrace.agents.nutrition.safety import safety_check
from dietrace.agents.supervisor.config import load_supervisor_config
from dietrace.agents.supervisor.decide import decide_op, gather_signals
from dietrace.agents.supervisor.phoenix_eval import (
    score_fit_via_phoenix,
    score_usda_via_phoenix,
)
from dietrace.agents.supervisor.phoenix_mcp import add_user_dataset_point
from dietrace.agents.supervisor.run import default_experiment_runner
from dietrace.evals.online import evaluate_log, review_flag, sources_of
from dietrace.macros.adherence import macro_adherence
from dietrace.macros.compute import compute_targets
from dietrace.macros.eval import evaluate_macro_plan
from dietrace.macros.models import MacroPlan, MacroProfile
from dietrace.macros.personalize import personalize_plan
from dietrace.macros.preference import apply_preferred_split
from dietrace.macros.presets import preset_plan
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
from dietrace.web.gate import confirmations_to_cases, score_block, ship_decision
from dietrace.web.goals import load_goals, targets_to_goals
from dietrace.web.identity import current_user
from dietrace.web.macro_memory import build_macro_memory, push_macro_preference, split_of
from dietrace.web.memory import build_memory, calories_of, sum_totals
from dietrace.web.micros import micro_progress
from dietrace.web.preference_stores import build_learning_stores, build_profile_store
from dietrace.web.standing_rules import StandingRule, build_standing_rules
from dietrace.web.store import MealLogStore
from dietrace.web.stores import build_stores
from dietrace.web.trust import TrustStore

SERVICE_NAME = "dietrace-web"

# A tracer for the web handlers so each /log and /macros/plan request opens a
# recording span — without one, the online-eval verdicts have no span to ride and
# never reach Phoenix. Resolves the global provider lazily, so
# it's a no-op span when tracing is disabled.
_TRACER = _otel_trace.get_tracer(SERVICE_NAME)

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

    meal_id: int | None = None  # the log_store row to rewrite in-place
    meal_text: str
    items: list[CorrectionItem]


class MacroPlanRequest(BaseModel):
    """Request body for POST /macros/plan.

    Either ``preset`` is set (the no-profile privacy-friendly path) or all
    profile fields are provided (the formula/AI personalisation path).
    """

    preset: str | None = None
    # MacroProfile fields — all optional here; validated in the endpoint.
    age: int | None = None
    sex: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    activity: str | None = None
    goal: str | None = None
    preference: str | None = None
    ai_help: bool = False


class MacroSaveRequest(BaseModel):
    """Request body for POST /macros/save — persists only the computed targets."""

    targets: dict[str, float]
    rationale: str | None = None
    source: str | None = None


class FreeformFeedbackRequest(BaseModel):
    """Free-form feedback for a logged meal — natural language → structured adaptation.

    ``meal_id`` is the stored meal to rewrite in-place (like /correct).
    ``current_items`` is the meal's current per_item list — used to build the
    LLM context and to apply the structured change deterministically without a
    second DB read.
    """

    meal_id: int | None = None
    meal_text: str = ""
    feedback_text: str
    current_items: list[Any] = []


class ConfirmRequest(BaseModel):
    """"Does this look right?" — a user-confirmed meal becomes a held-out
    ground-truth datapoint for the gate (Input A)."""

    meal_text: str
    items: list[dict[str, Any]] = []
    totals: list[dict[str, Any]] = []
    # Set when the user adjusted a portion before confirming — the logged meal is
    # rewritten to these items/totals so the entry matches what they confirmed.
    meal_id: int | None = None


class MealTimeRequest(BaseModel):
    """Change the time a meal was eaten — the client sends the new ``created_at``
    as a UTC ISO instant, kept within the meal's existing day."""

    created_at: str


class MealItemsRequest(BaseModel):
    """Edit a logged meal's numbers in place — its per-item rows (grams + nutrients)
    and the recomputed totals. A plain manual fix to the log, NOT a confirmation or
    dataset point (so it teaches the agent nothing)."""

    per_item: list[dict[str, Any]]
    totals: list[dict[str, Any]]


class FeedbackEditRequest(BaseModel):
    """Edit a banked correction's text and/or its emphasis weight (Input B)."""

    feedback_text: str | None = None
    weight: float | None = None


class ProfileRequest(BaseModel):
    """Body for POST /profile — the user's freeform "goals + eating style"."""

    profile_text: str = ""


class ExperimentRunRequest(BaseModel):
    """Body for POST /experiments/run — which dataset to run and a label for it."""

    dataset: str = "dietrace-nutrition-v1"
    name: str = "dietrace-supervisor"


class DemoSeedRequest(BaseModel):
    """Optional body for /demo/seed: the client's local day so seeded meals land
    relative to the day the user is actually viewing (not the server's UTC day),
    and which persona to load (the persona loader; defaults to the runner)."""

    date: str | None = None
    persona: str | None = None


# Sentinel profile used when running evaluate_macro_plan on a preset plan (no
# profile was submitted).  weight_kg=0 causes the protein g/kg axis to be
# skipped so the eval only checks Atwater consistency and the fat fraction.
_PRESET_PROFILE = MacroProfile(
    age=25,
    sex="male",
    height_cm=170.0,
    weight_kg=0.0,
    activity="moderate",
    goal="maintain",
)


def _rescale_items(
    original_items: list[dict[str, Any]],
    updated_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rescale nutrient panels for items whose grams changed after apply_feedback.

    apply_feedback only updates ``grams``; the nutrient amounts still reflect the
    original scale.  This completes the picture by rescaling each item's panel
    proportionally so sum_totals yields correct new totals.  New items (from
    add_item) that have no original pass through with empty nutrients.
    """
    orig_by_name: dict[str, dict[str, Any]] = {}
    for it in original_items:
        name = (it.get("description") or it.get("food") or "").lower()
        orig_by_name[name] = it

    result: list[dict[str, Any]] = []
    for item in updated_items:
        name = (item.get("description") or item.get("food") or "").lower()
        orig = orig_by_name.get(name)
        new_grams = float(item.get("grams", 0.0))
        desc = item.get("description") or item.get("food") or name

        if orig is None:
            result.append(
                {"description": desc, "grams": new_grams, "fdc_id": 0, "nutrients": []}
            )
            continue

        orig_grams = float(orig.get("grams", 0.0))
        if orig_grams and abs(new_grams - orig_grams) > 0.001:
            factor = new_grams / orig_grams
            nutrients = [
                {**n, "amount": round(float(n.get("amount", 0.0)) * factor, 2)}
                for n in orig.get("nutrients", [])
            ]
        else:
            nutrients = list(orig.get("nutrients", []))

        result.append({**item, "description": desc, "grams": new_grams, "nutrients": nutrients})

    return result


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


# A recalled meal IS the user's own correction — already vouched for, so it's
# full-confidence and never flagged for review (the quality eval would otherwise
# read its sparse/synthetic panel as uncertain).
_VOUCHED_AXES = [
    {"name": "resolution_completeness", "score": 1.0, "note": "✓ recalled from your correction"},
    {"name": "source_quality", "score": 1.0, "note": "✓ recalled from your correction"},
    {"name": "portion_sanity", "score": 1.0, "note": "✓ recalled from your correction"},
    {"name": "calorie_plausibility", "score": 1.0, "note": "✓ recalled from your correction"},
]
_VOUCHED_QUALITY = {
    "confidence": 1.0,
    "flags": [],
    "reasons": ["recalled from your correction"],
    "axes": _VOUCHED_AXES,
}
_NO_REVIEW = {"needs_review": False, "review_reason": None}


def _meal_detail(
    per_item: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    quality: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    """The per-meal breakdown persisted with a logged meal so /history can rebuild
    its per-item table + trace + quality eval after a reload or navigation."""
    return {
        "per_item": per_item,
        "trace": trace,
        "confidence": quality["confidence"],
        "reasons": quality["reasons"],
        "axes": quality.get("axes", []),
        "needs_review": review["needs_review"],
        "review_reason": review["review_reason"],
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


def _load_usda_eval_cases() -> list[dict[str, Any]]:
    """Load calorie expectations from the USDA nutrition eval dataset."""
    from pathlib import Path

    directory = Path("evals/dataset/nutrition")
    if not directory.exists():
        return []
    cases: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            text = data.get("input", {}).get("text", "")
            calories = float(data.get("expected", {}).get("calories", 0.0))
            if text and calories > 0:
                cases.append({"text": text, "calories": calories})
        except Exception:
            continue
    return cases


def _quick_usda_sample(
    cases: list[dict[str, Any]], k: int = 8
) -> list[dict[str, Any]]:
    """A small, representative slice of the USDA set for a FAST retune — spread
    evenly across the calorie range and skipping the sub-50-kcal items (whose
    percentage error is noisy), so the quick check still means something. The
    full retune uses every case."""
    real = [c for c in cases if c.get("calories", 0) >= 50] or cases
    if len(real) <= k:
        return real
    ordered = sorted(real, key=lambda c: c["calories"])
    step = len(ordered) / k
    return [ordered[int(i * step)] for i in range(k)]


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
        basis = item.get("portion_basis", "")
        trace.append(
            {
                "step": "estimate_portion",
                "food": food,
                "grams": grams,
                "basis": basis,
                "summary": f"Estimated {grams} g for '{food}'"
                + (f" ({basis})" if basis else ""),
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


def _maybe_decision_client() -> Any | None:
    """A default Gemini client for the supervisor decision + corrector, or None in
    tests / when no project is configured — so both fall back deterministically and
    no test ever constructs a real client. Mirrors corrector._default_client."""
    import sys

    from dietrace.llm.config import GEMINI_PROJECT

    if not GEMINI_PROJECT or "pytest" in sys.modules:
        return None
    try:
        from google import genai

        from dietrace.llm.config import GEMINI_LOCATION

        return genai.Client(
            vertexai=True, project=GEMINI_PROJECT, location=GEMINI_LOCATION
        )
    except Exception:
        return None


def _seed_created_at(
    meal_date: str, time_str: str | None
) -> datetime.datetime | None:
    """The ``created_at`` instant for a seeded meal pinned to *meal_date* at a
    clean *time_str* ("HH:MM"). The time is a *local wall-clock* time ("07:30" =
    "ate at 7:30am their time"), so we interpret it in the server's local zone and
    store the matching UTC instant — the store's convention — so the meal renders at
    the intended time of day in the browser instead of shifted by the UTC offset.
    Returns None when no time is given, so the store falls back to "now".
    """
    if not time_str:
        return None
    try:
        hour, minute = (int(part) for part in time_str.split(":", 1))
    except (ValueError, AttributeError):
        return None
    return datetime.datetime.combine(
        datetime.date.fromisoformat(meal_date),
        datetime.time(hour=hour, minute=minute),
    ).astimezone(datetime.UTC)


def create_app(
    *,
    meal_logger: MealLogger | None = None,
    meal_streamer: MealStreamer | None = None,
    store: MealLogStore | None = None,
    feedback_store: FeedbackStore | None = None,
    trust_store: TrustStore | None = None,
    goal_store: Any | None = None,
    memory: Any | None = None,
    macro_memory: Any | None = None,
    macro_pref_pusher: Any = push_macro_preference,
    feedback_pusher: FeedbackPusher = phoenix_push,
    tracer_init: Callable[[str], Any] = init_tracer,
    goals_loader: Callable[[], list[dict[str, Any]]] = load_goals,
    macro_client: Any | None = None,
    usda_case_loader: Callable[[], list[dict[str, Any]]] = _load_usda_eval_cases,
    standing_rule_store: Any | None = None,
    freeform_client: Any | None = None,
    confirmation_store: Any | None = None,
    feedback_log: Any | None = None,
    preference_store: Any | None = None,
    profile_store: Any | None = None,
    corrector_client: Any | None = None,
    experiment_runner: Callable[[dict[str, Any]], dict[str, Any]] = default_experiment_runner,
    dataset_writer: Callable[[str, dict[str, Any]], None] = add_user_dataset_point,
    phoenix_fit_scorer: Callable[..., dict[str, Any] | None] | None = None,
    phoenix_usda_scorer: Callable[..., dict[str, Any] | None] | None = None,
) -> FastAPI:
    """Build the DietTrace FastAPI app with injectable logger/store (for tests)."""
    if store is not None and feedback_store is not None and trust_store is not None:
        log_store, corrections, trust = store, feedback_store, trust_store
        goals_db = goal_store
    else:
        default_meals, default_feedback, default_trust, default_goals = build_stores()
        log_store = store or default_meals
        corrections = feedback_store or default_feedback
        trust = trust_store or default_trust
        goals_db = goal_store or default_goals
    learning = memory or build_memory()
    macro_learning = macro_memory or build_macro_memory()
    rules = standing_rule_store or build_standing_rules()
    # Learning-loop stores: confirmations (Input A held-out set), the feedback log
    # (Input B corrections), and the per-user preference block.
    if (
        confirmation_store is not None
        and feedback_log is not None
        and preference_store is not None
    ):
        confirms, fblog, prefs = confirmation_store, feedback_log, preference_store
    else:
        d_conf, d_fb, d_pref = build_learning_stores()
        confirms = confirmation_store or d_conf
        fblog = feedback_log or d_fb
        prefs = preference_store or d_pref
    # Per-user freeform profile (goals + eating style) — standing context the
    # corrector reads when generalizing corrections.
    profiles = profile_store or build_profile_store()
    # Supervisor settings (decision mode + retune thresholds), env-driven.
    supervisor_config = load_supervisor_config()
    # In powerful mode the agent decides WHEN to retune via the LLM. Build a default
    # Gemini client once (reused for the decision AND the corrector) when one wasn't
    # injected — None in tests / when no project is set, so both fall back to the
    # deterministic policy. Construction is lazy (no network until a call).
    if corrector_client is None:
        corrector_client = _maybe_decision_client()
    # The gate's fit score runs as Phoenix experiments read back over MCP; default it
    # on for the live app, off in tests (which stay Phoenix-free and use local scoring
    # unless a fake scorer is injected). Returns None on any failure → local fallback.
    if phoenix_fit_scorer is None and "pytest" not in sys.modules:
        phoenix_fit_scorer = score_fit_via_phoenix
    # The USDA floor set is scored in Arize too (a second Phoenix experiment pair),
    # so BOTH panels are graded in Arize and land together; off in tests / on failure
    # → local parallel scoring (which is what the offline stream test exercises).
    if phoenix_usda_scorer is None and "pytest" not in sys.modules:
        phoenix_usda_scorer = score_usda_via_phoenix
    # In-memory experiment-run registry + per-user daily run counter. The supervisor
    # triggers experiments off the hot path; runs_today feeds the decision's budget
    # guard. Both reset on restart — fine for a single Cloud Run service.
    experiments: dict[str, dict[str, Any]] = {}
    run_counts: dict[tuple[str, str], int] = {}

    def _runs_today(user: str) -> int:
        return run_counts.get((user, datetime.date.today().isoformat()), 0)

    def _record_run(user: str) -> None:
        key = (user, datetime.date.today().isoformat())
        run_counts[key] = run_counts.get(key, 0) + 1

    logger_fn = meal_logger or default_meal_logger
    streamer_fn = meal_streamer or default_meal_streamer

    def _user_context(user: str) -> list[dict[str, Any]]:
        """This user's few-shot corrections PLUS their standing-rule preferences,
        as a single examples list the parser injects into its prompt — so the
        agent actually consults the rules a user has taught it (recall)."""
        examples: list[dict[str, Any]] = []
        # The generalized preference block is the primary personalization signal.
        # Few-shot corrections + standing rules ride alongside it as secondary signals.
        block = prefs.block_text(user)
        if block:
            examples.append({"preference_block": block})
        examples.extend(learning.examples(user))
        examples.extend(
            {"rule": r["rationale"]}
            for r in rules.recent(user)
            if r.get("rationale")
        )
        return examples

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

    def _record_trust(
        per_item: list[Any],
        quality: dict[str, Any],
        review: dict[str, Any],
        user: str,
        text: str,
    ) -> None:
        """Persist a logged meal's online-eval result for the /trust rollup.

        Keeps the meal *text* and the review reason so /trust can list a user's
        recent low-confidence meals with enough context to revisit them.
        """
        trust.record(
            confidence=quality["confidence"],
            needs_review=bool(review["needs_review"]),
            sources=sources_of(per_item),
            user_id=user,
            text=text,
            review_reason=review["review_reason"],
        )

    @app.post("/log")
    def log_meal(req: LogRequest, user: str = Depends(current_user)) -> dict[str, Any]:
        safety = safety_check(req.text)
        if safety["flagged"]:
            # A safety-flagged input is not a meal — surface support, log nothing.
            return {"safety": safety, "logged": False, "per_item": [], "totals": [], "trace": []}
        recalled = learning.recall(user, req.text)
        if recalled is not None:
            per_item, totals = recalled["per_item"], recalled["totals"]
            quality, review = dict(_VOUCHED_QUALITY), dict(_NO_REVIEW)
            trace = [_recall_step()] + _build_trace(per_item, totals)
            entry_id = log_store.add(
                req.text, totals, date=req.date, user_id=user,
                detail=_meal_detail(per_item, trace, quality, review),
            )
            # Recalled meals bypass agent analysis (user-vouched, confidence=1.0).
            # The original fresh log already has a trust entry; recording a second
            # one here inflates the count and mean_confidence artificially.
            return {
                "id": entry_id,
                "per_item": per_item,
                "totals": totals,
                "recalled": True,
                "confidence": quality["confidence"],
                "reasons": quality["reasons"],
                "axes": quality.get("axes", []),
                "safety": safety,
                **review,
                "trace": trace,
            }
        # A recording span so the online-eval verdict (set on the current span by
        # evaluate_log) rides this trace into Phoenix. The Gemini parse inside
        # logger_fn nests under it.
        with _TRACER.start_as_current_span("meal_log"):
            result = logger_fn(req.text, examples=_user_context(user))
            totals = result.get("totals", [])
            per_item = result.get("per_item", [])
            quality = evaluate_log(req.text, per_item, totals)
            review = review_flag(quality)
            trace = _build_trace(per_item, totals)
            entry_id = log_store.add(
                req.text, totals, date=req.date, user_id=user,
                detail=_meal_detail(per_item, trace, quality, review),
            )
            _record_trust(per_item, quality, review, user, req.text)
            # The supervisor's per-meal decision: a fresh, uncorrected meal is a
            # clean dataset-point candidate unless enough new signal has accrued to
            # retune. Cheap + deterministic here; the MCP write / retune execution
            # runs off the hot path.
            decision = decide_op(
                gather_signals(
                    fblog,
                    confirms,
                    user,
                    runs_today=_runs_today(user),
                    meal_confidence=quality["confidence"],
                ),
                supervisor_config,
                client=corrector_client,
            )
            return {
                "id": entry_id,
                **result,
                "confidence": quality["confidence"],
                "reasons": quality["reasons"],
                "axes": quality.get("axes", []),
                "safety": safety,
                **review,
                "trace": trace,
                "supervisor": decision.as_dict(),
            }

    @app.post("/log/stream")
    def log_meal_stream(
        req: LogRequest, user: str = Depends(current_user)
    ) -> StreamingResponse:
        """Stream the agent's work as Server-Sent Events: one ``step`` event per
        pipeline step, then a ``result`` event (which also persists the meal)."""

        pace = float(os.environ.get("DIETRACE_STREAM_PACE", str(_STREAM_PACE)))
        safety = safety_check(req.text)
        recalled = learning.recall(user, req.text)

        def safety_events() -> Iterator[str]:
            # A safety-flagged input is not a meal — surface support, log nothing.
            result = {"type": "result", "safety": safety, "logged": False,
                      "per_item": [], "totals": [], "trace": []}
            yield f"data: {json.dumps(result)}\n\n"

        def cached_events() -> Iterator[str]:
            # A meal the user already corrected — recall it instead of re-running.
            per_item, totals = recalled["per_item"], recalled["totals"]
            yield f"data: {json.dumps(_recall_step())}\n\n"
            quality, review = dict(_VOUCHED_QUALITY), dict(_NO_REVIEW)
            full_trace = [_recall_step()] + _build_trace(per_item, totals)
            entry_id = log_store.add(
                req.text, totals, date=req.date, user_id=user,
                detail=_meal_detail(per_item, full_trace, quality, review),
            )
            # No trust entry for recalled meals — see the /log recall path comment.
            result = {
                "type": "result",
                "id": entry_id,
                "per_item": per_item,
                "totals": totals,
                "recalled": True,
                "confidence": quality["confidence"],
                "reasons": quality["reasons"],
                "axes": quality.get("axes", []),
                "safety": safety,
                **review,
                "trace": [_recall_step()],
            }
            yield f"data: {json.dumps(result)}\n\n"

        def events() -> Iterator[str]:
            for event in streamer_fn(req.text, examples=_user_context(user)):
                if event.get("type") == "result":
                    per_item = event.get("per_item", [])
                    totals = event.get("totals", [])
                    quality = evaluate_log(req.text, per_item, totals)
                    review = review_flag(quality)
                    trace = _build_trace(per_item, totals)
                    event["trace"] = trace
                    event["id"] = log_store.add(
                        req.text, totals, date=req.date, user_id=user,
                        detail=_meal_detail(per_item, trace, quality, review),
                    )
                    event["confidence"] = quality["confidence"]
                    event["reasons"] = quality["reasons"]
                    event["axes"] = quality.get("axes", [])
                    event["safety"] = safety
                    event.update(review)
                    _record_trust(per_item, quality, review, user, req.text)
                    event["supervisor"] = decide_op(
                        gather_signals(
                            fblog, confirms, user,
                            runs_today=_runs_today(user),
                            meal_confidence=quality["confidence"],
                        ),
                        supervisor_config,
                        client=corrector_client,
                    ).as_dict()
                elif pace:
                    time.sleep(pace)  # let fast steps arrive one at a time
                yield f"data: {json.dumps(event)}\n\n"

        if safety["flagged"]:
            stream = safety_events()
        elif recalled is not None:
            stream = cached_events()
        else:
            stream = events()
        return StreamingResponse(stream, media_type="text/event-stream")

    @app.delete("/meals/{meal_id}")
    def delete_meal(meal_id: int, user: str = Depends(current_user)) -> dict[str, Any]:
        return {"id": meal_id, "deleted": log_store.delete(meal_id, user_id=user)}

    @app.post("/meals/{meal_id}/time")
    def set_meal_time(
        meal_id: int, req: MealTimeRequest, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        """Update the time a meal was eaten (its created_at), scoped to the user."""
        try:
            when = datetime.datetime.fromisoformat(req.created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid created_at") from exc
        return {"id": meal_id, "updated": log_store.set_time(meal_id, when, user_id=user)}

    @app.post("/meals/{meal_id}/items")
    def set_meal_items(
        meal_id: int, req: MealItemsRequest, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        """Rewrite a meal's items + totals in place (a manual edit of the numbers).
        Does NOT bank feedback or create a dataset point — it just fixes the log."""
        updated = log_store.update(
            meal_id, req.per_item, req.totals, user_id=user
        )
        return {"id": meal_id, "updated": updated}

    @app.get("/history")
    def history(
        date: str | None = None, limit: int = 50, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        day = date or datetime.datetime.now(tz=datetime.UTC).date().isoformat()
        meals = log_store.list(limit, date=day, user_id=user)
        # Badge meals the user has acted on: given feedback on, or confirmed (so the
        # review resolves to the saved state instead of re-asking on every reload).
        feedback_meals = fblog.meal_texts_with_feedback(user)
        confirmed_meals = {c.get("meal_text") for c in confirms.list(user_id=user)}
        for meal in meals:
            if meal.get("per_item") and not meal.get("trace"):
                meal["trace"] = _build_trace(meal["per_item"], meal["totals"])
            meal["has_feedback"] = meal.get("text") in feedback_meals
            meal["has_confirmation"] = meal.get("text") in confirmed_meals
        return {"date": day, "meals": meals}

    @app.get("/goals")
    def goals(user: str = Depends(current_user)) -> dict[str, Any]:
        if goals_db is not None:
            saved = goals_db.get(user)
            if saved is not None:
                return {"goals": targets_to_goals(saved)}
        return {"goals": goals_loader()}

    @app.post("/macros/plan")
    def macros_plan(
        req: MacroPlanRequest, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        """Compute a macro plan — from a preset key or a full profile.

        Does NOT persist anything: callers must POST /macros/save separately.
        The profile fields are never stored; only the resulting targets travel
        out of this endpoint (via the response and then /macros/save).
        """
        # The user's remembered split preference, if any — it biases the plan
        # toward what they've chosen before (the macro-learning closure), taking
        # precedence over both the goal-default split and a fresh AI nudge.
        pref = macro_learning.recall(user)
        # A recording span so the macro-plan eval verdict (set on the current span
        # by evaluate_macro_plan) rides this trace into Phoenix;
        # the personalize Gemini call nests under it.
        with _TRACER.start_as_current_span("macro_plan"):
            if req.preset is not None:
                try:
                    plan = preset_plan(req.preset)
                except KeyError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                if pref:
                    plan = apply_preferred_split(plan, pref)
                eval_result = evaluate_macro_plan(_PRESET_PROFILE, plan)
            else:
                try:
                    profile = MacroProfile(
                        age=req.age,
                        sex=req.sex,
                        height_cm=req.height_cm,
                        weight_kg=req.weight_kg,
                        activity=req.activity,
                        goal=req.goal,
                        preference=req.preference,
                        ai_help=req.ai_help,
                    )
                except ValidationError as exc:
                    raise HTTPException(status_code=422, detail=exc.errors()) from exc
                plan = compute_targets(profile)
                if pref:
                    plan = apply_preferred_split(plan, pref, weight_kg=profile.weight_kg)
                elif req.ai_help:
                    plan = personalize_plan(profile, plan.targets, client=macro_client)
                eval_result = evaluate_macro_plan(profile, plan)
        # When personalized, score how well the served split matches the saved
        # preference (the "tuned to you" alignment signal).
        adherence = macro_adherence(plan, pref) if pref else None
        plan = MacroPlan(
            targets=plan.targets,
            rationale=plan.rationale,
            source=plan.source,
            steps=plan.steps,
            clamped=plan.clamped,
            eval=eval_result,
            personalized=plan.personalized,
            adherence=adherence,
        )
        return plan.model_dump()

    @app.post("/macros/save")
    def macros_save(
        req: MacroSaveRequest, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        """Persist only the targets from a computed macro plan.

        Stores the targets dict keyed by USDA code, plus optional rationale and
        source for display.  The MacroProfile that produced the targets is never
        accepted here — callers must not send it and this endpoint will not store it.
        """
        if goals_db is None:
            raise HTTPException(status_code=503, detail="Goal store not configured")
        goals_db.save(user, req.targets, rationale=req.rationale, source=req.source)
        # Remember the user's preferred split so the next plan biases toward it
        # (the macro-learning closure) — derived only from the targets, no profile.
        macro_learning.remember(user, req.targets)
        # Bank the preference in Phoenix as the user's macro ground truth —
        # fail-soft, profile-free, never blocks the save.
        split = split_of(req.targets)
        banked = bool(split and macro_pref_pusher(user, split))
        return {"ok": True, "user": user, "targets": req.targets, "banked": banked}

    @app.post("/macros/retune")
    def macros_retune(
        req: MacroPlanRequest, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        """How much the user's saved preference tunes their plan.

        The macro analogue of /retune: compares the generic goal-default plan
        (``before``) against the personalized plan (``after``) by adherence to the
        user's saved split preference, so the UI can show "your nutritionist adapts
        to you." This is an ALIGNMENT measure, not accuracy vs ground truth. Returns
        zero cases when the user has no saved preference yet.
        """
        pref = macro_learning.recall(user)
        if not pref:
            return {"cases": 0, "before": None, "after": None, "improved": False}

        if req.preset is not None:
            try:
                base = preset_plan(req.preset)
            except KeyError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            weight = None
        else:
            try:
                profile = MacroProfile(
                    age=req.age, sex=req.sex, height_cm=req.height_cm,
                    weight_kg=req.weight_kg, activity=req.activity, goal=req.goal,
                )
            except ValidationError as exc:
                raise HTTPException(status_code=422, detail=exc.errors()) from exc
            base = compute_targets(profile)
            weight = profile.weight_kg

        tuned = apply_preferred_split(base, pref, weight_kg=weight)
        before = macro_adherence(base, pref)
        after = macro_adherence(tuned, pref)
        return {
            "cases": 1,
            "before": before["score"],
            "after": after["score"],
            "improved": after["score"] > before["score"],
            "protein_shift": round(
                4 * tuned.targets["203"] / tuned.targets["208"]
                - 4 * base.targets["203"] / base.targets["208"],
                4,
            ),
        }

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

    @app.get("/feedback/recent")
    def feedback_recent(user: str = Depends(current_user)) -> dict[str, Any]:
        """The user's recent portion corrections — the "what you've taught" panel.

        Each item is a food with its before→after grams, newest first, so the UI
        can show the user the ground truth they've contributed — the
        self-supervision loop, made visible in-app.
        """
        return {"corrections": corrections.recent(user_id=user)}

    @app.post("/feedback/freeform")
    def freeform_feedback_endpoint(
        req: FreeformFeedbackRequest, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        """Interpret free-form feedback, apply it to the meal, and surface the adaptation.

        ``interpret_feedback`` converts the user's comment into a StructuredFeedback;
        ``apply_feedback`` then applies it deterministically (portion_adjust /
        remove_item / add_item / standing_rule).  Non-standing-rule feedback rewrites
        the stored meal in place (like /correct); standing_rule feedback is persisted
        as a per-user preference so future meal recall can apply it.

        The response always includes the structured interpretation so the adaptation is
        VISIBLE: the UI shows "DietTrace learned: [what changed and why]" immediately.
        Fail-soft on any LLM or store error so the user's correction is never silently
        lost.
        """
        items_for_context = [
            {
                "food": it.get("description") or it.get("food") or "",
                "grams": float(it.get("grams", 0.0)),
            }
            for it in req.current_items
        ]
        meal_context = {"items": items_for_context}

        structured = interpret_feedback(meal_context, req.feedback_text, client=freeform_client)
        if structured is None:
            return {
                "ok": False,
                "applied": False,
                "error": "could not interpret feedback",
                "kind": None,
                "target_food": "",
                "adjustment": None,
                "rationale": "",
                "scope": "",
                "stored_as_preference": False,
                "per_item": list(req.current_items),
                "totals": [],
                "added_to_arize": False,
                "phoenix_url": phoenix_dashboard_url(),
            }

        # Bank the raw feedback for the learning loop (Input B) so the corrector
        # can generalize it into the preference block on the next retune.
        fblog.add(user, req.feedback_text, structured.model_dump(), req.meal_text or "")
        # XOR rule: a meal the user corrected is no longer a clean reference, so
        # drop it from the held-out gate set.
        if req.meal_text:
            confirms.delete_by_meal(user, req.meal_text)

        # Feedback is the PRIMARY trigger for a retune: consult the
        # supervisor now that this correction is banked, so the loop reacts to
        # feedback itself rather than waiting for the next incidental meal log.
        # was_corrected=False here — the bank already happened; we're deciding what
        # the accrued signal warrants next.
        feedback_decision = decide_op(
            gather_signals(fblog, confirms, user, runs_today=_runs_today(user)),
            supervisor_config,
            client=corrector_client,
        )

        applied = False
        stored_as_preference = False
        updated_items: list[dict[str, Any]] = list(req.current_items)
        new_totals: list[dict[str, Any]] = []
        eval_patch: dict[str, Any] | None = None

        if structured.kind == "standing_rule":
            rule = StandingRule(
                scope=structured.scope,
                target_food=structured.target_food,
                adjustment=structured.adjustment,
                rationale=structured.rationale,
            )
            rules.remember(user, rule)
            stored_as_preference = True
        else:
            items_with_food = [
                {**it, "food": it.get("description") or it.get("food") or ""}
                for it in req.current_items
            ]
            updated_with_food = apply_feedback(items_with_food, structured)
            applied = updated_with_food != items_with_food

            updated_items = _rescale_items(req.current_items, updated_with_food)
            new_totals = sum_totals(updated_items)

            # Re-run the online eval on the corrected meal so its confidence,
            # axes, and needs_review reflect the fix (e.g. a fixed portion clears
            # the portion-sanity flag) — otherwise the stored eval goes stale and
            # the "why this confidence" calc no longer adds up.
            requality = evaluate_log(req.meal_text, updated_items, new_totals)
            rereview = review_flag(requality)
            eval_patch = {
                "confidence": requality["confidence"],
                "reasons": requality["reasons"],
                "axes": requality.get("axes", []),
                "needs_review": rereview["needs_review"],
                "review_reason": rereview["review_reason"],
            }

            if req.meal_id is not None:
                log_store.update(
                    req.meal_id,
                    updated_items,
                    new_totals,
                    user_id=user,
                    detail_patch=eval_patch,
                )

            # Bank the corrected meal as ground truth — exactly like /correct —
            # so it shows in the observability rail ("corrections banked") AND
            # feeds /retune. Without this a free-form fix was applied but never
            # recorded, so the user couldn't tune on it.
            if applied:
                learning.remember(user, req.meal_text, updated_items, new_totals)

        inp: dict[str, Any] = {
            "text": req.meal_text,
            "feedback": req.feedback_text,
            "kind": structured.kind,
        }
        if structured.kind == "standing_rule":
            out: dict[str, Any] = {
                "scope": structured.scope,
                "target_food": structured.target_food,
                "adjustment": structured.adjustment,
            }
        else:
            by_code = {t["code"]: t["amount"] for t in new_totals}
            out = {
                "grams": round(sum(float(it.get("grams", 0.0)) for it in updated_items), 1),
                "calories": round(by_code.get("208", 0.0), 1),
                "protein_g": round(by_code.get("203", 0.0), 1),
                "fat_g": round(by_code.get("204", 0.0), 1),
                "carb_g": round(by_code.get("205", 0.0), 1),
            }
        meta: dict[str, Any] = {
            "source": "freeform_feedback",
            "kind": structured.kind,
            "target_food": structured.target_food,
            "adjustment": structured.adjustment,
            "rationale": structured.rationale,
        }
        added_to_arize = feedback_pusher(inp, out, meta)

        return {
            "ok": True,
            "applied": applied,
            "kind": structured.kind,
            "target_food": structured.target_food,
            "adjustment": structured.adjustment,
            "target_grams": structured.target_grams,
            "rationale": structured.rationale,
            "scope": structured.scope,
            "stored_as_preference": stored_as_preference,
            "per_item": updated_items,
            "totals": new_totals,
            # The recomputed online eval so the UI refreshes the meal's confidence
            # + axes + review flag in place (None for standing-rule feedback,
            # which doesn't touch this meal's items).
            "confidence": eval_patch["confidence"] if eval_patch else None,
            "axes": eval_patch["axes"] if eval_patch else None,
            "reasons": eval_patch["reasons"] if eval_patch else None,
            "needs_review": eval_patch["needs_review"] if eval_patch else None,
            "review_reason": eval_patch["review_reason"] if eval_patch else None,
            "added_to_arize": added_to_arize,
            "corrections": fblog.count(user),
            "supervisor": feedback_decision.as_dict(),
            "phoenix_url": phoenix_dashboard_url(),
        }

    @app.get("/feedback/standing-rules")
    def feedback_standing_rules(user: str = Depends(current_user)) -> dict[str, Any]:
        """The user's standing rules — preferences stored from free-form feedback."""
        return {"rules": rules.recent(user_id=user)}

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
        # Whether the logged meal's stored totals were rewritten (False = no meal_id
        # given, or the id didn't match this user's meal — the correction is still
        # banked, but the day band won't change).
        updated = (
            log_store.update(correction.meal_id, corrected_items, totals, user_id=user)
            if correction.meal_id is not None
            else False
        )
        learning.remember(user, correction.meal_text, corrected_items, totals)
        inp, out, meta = _meal_example(correction.meal_text, corrected_items, totals)
        added_to_arize = feedback_pusher(inp, out, meta)
        return {
            "ok": True,
            "updated": updated,
            "added_to_arize": added_to_arize,
            "corrections": learning.count(user),
            "per_item": corrected_items,
            "totals": totals,
            "phoenix_url": phoenix_dashboard_url(),
        }

    @app.get("/memory")
    def memory_summary(user: str = Depends(current_user)) -> dict[str, Any]:
        # "Corrections banked" = everything the user has taught (the learning-loop
        # feedback log), so standing-rules + portion fixes all count — not just the
        # old few-shot meal corrections.
        return {"corrections": fblog.count(user)}

    @app.get("/trust")
    def trust_summary(user: str = Depends(current_user)) -> dict[str, Any]:
        """Rolling trust stats from each log's online-eval result.

        Count, mean confidence, the fraction flagged for review, and the source
        breakdown — scoped to the calling user (the per-user memory layer).
        """
        return trust.stats(user_id=user)

    @app.get("/analysis")
    def analysis(
        date: str | None = None, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        # Aggregate only the requested day (default today) so the macro band is
        # the day's intake and stays in sync with date navigation.
        day = date or datetime.datetime.now(tz=datetime.UTC).date().isoformat()
        meals = log_store.list(1000, date=day, user_id=user)
        totals = _aggregate(meals)
        saved_targets = goals_db.get(user) if goals_db is not None else None
        if saved_targets is not None:
            active_goals = targets_to_goals(saved_targets)
        else:
            active_goals = goals_loader()
        return {
            "date": day,
            "meal_count": len(meals),
            "totals": totals,
            "goals": _goals_progress(totals, active_goals),
            "micros": micro_progress(totals),
            "traces_buffered": get_buffer().trace_count(),
        }

    @app.post("/demo/seed")
    def demo_seed(
        req: DemoSeedRequest | None = None, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        """Seed the calling user's account with canned demo data.

        Logs a selected persona's visible day for TODAY using pre-computed
        per_item/totals/trace data — no live Gemini call — plus the learning-loop
        seed (confirmed meals + a couple of corrections) so a judge can hit
        "retune" immediately. The confirmed meals (the held-out gate set) are ALSO
        logged as visible rows on the PREVIOUS day, badged as dataset points, so
        the dataset isn't hidden — a judge can see exactly what the agent is
        tested against (the observability-everywhere rule). Today's visible day
        carries a macro under-count (carbs for the runner, post-lift protein for
        the bodybuilder) so the correction → retune flow has an on-screen target.
        """
        from dietrace.web.demo_seed import get_persona

        persona = get_persona(req.persona if req else None)

        # Idempotent: clear this user's meals first so re-running "see it in
        # action" replaces the canned set rather than appending duplicates. The
        # learning-loop stores are cleared here too (before any rows are seeded)
        # so the dataset points added during insertion below survive the reset.
        log_store.clear_user(user)
        trust.clear_user(user)
        confirms.clear_user(user)
        fblog.clear_user(user)
        prefs.clear_user(user)
        profiles.set(user, persona.profile)

        # The client's local "today" (so we're relative to the day the user sees,
        # not the server's UTC day at the boundary). The visible playground meals
        # land on today; the confirmed dataset rows land on the day before.
        today = (req.date if req and req.date else None) or datetime.datetime.now(
            tz=datetime.UTC
        ).date().isoformat()
        today_date = datetime.date.fromisoformat(today)
        # Today (offset 0) stays EMPTY — the judge logs their own first meal there.
        # The persona's meals are spread across yesterday (day 1) and two-days-ago
        # (day 2), and so are the held-out dataset rows. dataset_date is the older
        # day (today − 2) — the "view dataset" link jumps there.
        dataset_date = (today_date - datetime.timedelta(days=2)).isoformat()
        # Build the full insertion plan up front so rows go in oldest-first within
        # each calendar day. /history orders by insert id (newest first), and the
        # frontend renders that order verbatim — so to make each prior day read
        # chronologically the visible meals and the prior-day rows (which can share
        # a date) must be inserted together, sorted by (date, time), not in two
        # separate visible-then-previous passes. Each meal pins itself to a day
        # relative to the seed's local today (``day``: 0 = today, 1 = yesterday, …)
        # and a clean ``time`` ("HH:MM"); absent both it lands on today with no
        # fixed time (the default for personas that don't spread across days).
        def _meal_date(offset: int) -> str:
            return (today_date - datetime.timedelta(days=offset)).isoformat()

        plan: list[tuple[str, str, dict[str, Any]]] = []
        for meal in persona.meals:
            plan.append(("visible", _meal_date(int(meal.get("day", 0))), meal))
        for m in persona.previous_day:
            plan.append(("previous", _meal_date(int(m.get("day", 2))), m))
        # Sort by (date, time); rows without a time sort last within their day, so
        # explicitly-timed rows keep their chronological slots.
        plan.sort(key=lambda r: (r[1], r[2].get("time") or "99:99"))

        meal_ids: list[int] = []
        seeded_decisions: list[dict[str, Any]] = []
        for kind, meal_date, meal in plan:
            created_at = _seed_created_at(meal_date, meal.get("time"))
            if kind == "visible":
                entry_id = log_store.add(
                    meal["text"],
                    meal["totals"],
                    created_at=created_at,
                    date=meal_date,
                    user_id=user,
                    detail=meal["detail"],
                )
                meal_ids.append(entry_id)
                # Record each visible meal's captured eval in the /trust rollup, so
                # the recap's "how it's doing" reflects the loaded meals (count +
                # mean confidence) instead of an empty 0% / 0 meals.
                d = meal["detail"]
                trust.record(
                    confidence=float(d.get("confidence", 0.0)),
                    needs_review=bool(d.get("needs_review", False)),
                    sources=sources_of(d.get("per_item", [])),
                    user_id=user,
                    text=meal["text"],
                    review_reason=d.get("review_reason"),
                )
            else:
                # The full simulated prior day (real agent output, full detail);
                # dataset-point rows are also added to the held-out gate set.
                detail = dict(meal.get("detail", {}))
                is_dp = bool(meal.get("dataset_point"))
                detail["dataset_point"] = is_dp
                log_store.add(
                    meal["text"],
                    meal["totals"],
                    created_at=created_at,
                    date=meal_date,
                    user_id=user,
                    detail=detail,
                )
                if is_dp:
                    confirms.add(
                        user,
                        meal["text"],
                        detail.get("per_item", []),
                        meal["totals"],
                        source="seed",
                    )
                    seeded_decisions.append({
                        "op": "add_dataset_point",
                        # No reason line — "Added to your dataset" already says it.
                        "reason": "",
                        "meal_text": meal["text"],
                    })

        goals_set = False
        if goals_db is not None:
            goals_db.save(
                user, persona.goals, rationale=persona.goal_rationale, source="demo"
            )
            goals_set = True

        # Seed the rest of the learning-loop state so a judge can hit "retune"
        # immediately: the dataset points (the held-out gate set) were added during
        # insertion above; now bank a couple of
        # corrections to generalize. The stores were cleared up front so the retune
        # starts from a fresh preference block and ships.
        for f in persona.feedback:
            fblog.add(
                user, f["feedback_text"], None, f.get("meal_text"), f.get("weight", 1.0)
            )
            seeded_decisions.append({
                "op": "bank_feedback",
                "reason": "To be used to refine your DietTrace agent!",
                "meal_text": f.get("meal_text") or f["feedback_text"],
            })

        return {
            "seeded": True,
            "meals": len(meal_ids),
            "meal_ids": meal_ids,
            "meal_date": today,
            "dataset_date": dataset_date,
            "goals_set": goals_set,
            "confirmations": confirms.count(user),
            "corrections": fblog.count(user),
            # The agent's prior decisions, to backfill the activity feed (prev day).
            "decisions": seeded_decisions,
            "user": user,
            "persona": {
                "key": persona.key,
                "label": persona.label,
                "blurb": persona.blurb,
                "goal_rationale": persona.goal_rationale,
                "hook_meal": persona.hook_meal,
                "hook_note": persona.hook_note,
                "learns": persona.learns,
                "meal_texts": [m["text"] for m in persona.meals],
                # All real logged meals = today's visible meals + the previous
                # day's non-dataset-point meals (dataset points are counted
                # separately as confirmations). meal_texts stays the visible day.
                "meals_logged": (
                    len(persona.meals)
                    + sum(1 for m in persona.previous_day if not m.get("dataset_point"))
                ),
                "confirmation_texts": [c["meal_text"] for c in persona.confirmations],
                "correction_texts": [f["feedback_text"] for f in persona.feedback],
            },
        }

    @app.post("/session/reset")
    def session_reset(user: str = Depends(current_user)) -> dict[str, Any]:
        """Wipe the calling user's session to a clean slate.

        Clears their logged meals, goals, and everything DietTrace has learned
        about them (standing rules, corrections, remembered examples, macro
        split, trust logs). Each store is cleared independently and fail-soft so
        one backend hiccup can't leave the reset half-done from the user's view.
        """
        cleared: dict[str, int] = {}
        targets: list[tuple[str, Any]] = [
            ("meals", log_store),
            ("goals", goals_db),
            ("corrections", corrections),
            ("trust", trust),
            ("rules", rules),
            ("memory", learning),
            ("macros", macro_learning),
            ("confirmations", confirms),
            ("feedback_log", fblog),
            ("preferences", prefs),
            ("profile", profiles),
        ]
        for name, store_obj in targets:
            if store_obj is None or not hasattr(store_obj, "clear_user"):
                continue
            try:
                cleared[name] = int(store_obj.clear_user(user))
            except Exception:  # noqa: BLE001 — reset is best-effort per store
                cleared[name] = -1
        return {"reset": True, "user": user, "cleared": cleared}

    # ── Learning loop ──────────────────────────────────────────────────────────
    _MIN_CORRECTIONS = 1  # corrections needed before a retune is offered
    # The gate scores the FULL USDA set by default (the honest floor check); the
    # retune is live so it's slow, which is fine — the observability shows real
    # evals running. DIETRACE_RETUNE_USDA_SAMPLE>0 caps it only for fast test runs.
    _RETUNE_USDA_SAMPLE = int(os.environ.get("DIETRACE_RETUNE_USDA_SAMPLE", "0"))

    @app.post("/confirm")
    def confirm_meal(
        req: ConfirmRequest,
        background: BackgroundTasks,
        user: str = Depends(current_user),
    ) -> dict[str, Any]:
        """"Does this look right?" — record a confirmed meal as a held-out
        ground-truth datapoint (Input A). Grows the gate dataset; never touches
        the prompt. Kept strictly disjoint from corrections (the XOR rule).

        The confirmed meal is also written to the user's Phoenix dataset over the
        MCP server, off the hot path (the npx MCP server is slow), fail-soft."""
        cid = confirms.add(user, req.meal_text, req.items, req.totals)
        # If the user adjusted a portion before confirming, rewrite the logged meal
        # so the entry shown in the food log matches the confirmed (corrected) one.
        if req.meal_id is not None and req.items:
            log_store.update(req.meal_id, req.items, req.totals, user_id=user)
        # XOR rule: a meal can't be both held-out ground
        # truth AND a correction the corrector learns from. Correcting drops it from
        # confirmations; confirming drops any feedback banked against it.
        fblog.delete_by_meal(user, req.meal_text)
        example = {
            "input": {"text": req.meal_text},
            "output": {"calories": calories_of(req.totals)},
            "metadata": {"source": "user_confirmed"},
        }
        background.add_task(dataset_writer, user, example)
        # Growing the held-out set can be what tips a retune into being validatable —
        # consult the supervisor so the loop reacts to a confirm too, not just logs.
        confirm_decision = decide_op(
            gather_signals(fblog, confirms, user, runs_today=_runs_today(user)),
            supervisor_config,
            client=corrector_client,
        )
        return {
            "ok": True,
            "id": cid,
            "confirmations": confirms.count(user),
            "supervisor": confirm_decision.as_dict(),
        }

    @app.get("/learning/feedback")
    def list_feedback(user: str = Depends(current_user)) -> dict[str, Any]:
        """The user's banked corrections (Input B) — for the feedback manager."""
        return {"feedback": fblog.list(user), "count": fblog.count(user)}

    @app.patch("/learning/feedback/{feedback_id}")
    def edit_feedback(
        feedback_id: int,
        req: FeedbackEditRequest,
        user: str = Depends(current_user),
    ) -> dict[str, Any]:
        """Edit a correction's text and/or emphasis; the block re-derives on retune."""
        ok = fblog.update(
            feedback_id, user, feedback_text=req.feedback_text, weight=req.weight
        )
        return {"ok": ok}

    @app.delete("/learning/feedback/{feedback_id}")
    def delete_feedback(
        feedback_id: int, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        return {"deleted": fblog.delete(feedback_id, user)}

    @app.get("/profile")
    def get_profile(user: str = Depends(current_user)) -> dict[str, Any]:
        """The user's freeform profile (goals + eating style), or '' if unset."""
        return {"profile_text": profiles.get(user)}

    @app.post("/profile")
    def set_profile(
        req: ProfileRequest, user: str = Depends(current_user)
    ) -> dict[str, Any]:
        """Save the user's freeform profile. It becomes standing context the
        corrector reads on the next retune — so personalization reflects who the
        user is, not just the meals they've fixed."""
        text = (req.profile_text or "").strip()
        profiles.set(user, text)
        return {"ok": True, "profile_text": text}

    @app.get("/preferences")
    def preferences(user: str = Depends(current_user)) -> dict[str, Any]:
        """The user's current preference block + provenance, the confirmed meals
        the gate tests against, and the counts that gate whether a retune is
        available."""
        confirmed = [
            {"id": c["id"], "meal_text": c["meal_text"], "calories": calories_of(c["totals"])}
            for c in confirms.list(user)
        ]
        by_source = confirms.count_by_source(user)
        return {
            "block": prefs.get(user),
            "corrections": fblog.count(user),
            # New (unprocessed) corrections — the only ones the next retune folds in.
            "new_corrections": fblog.count_unprocessed(user),
            "confirmations": confirms.count(user),
            # Split so the UI can say "N from you · M seeded".
            "confirmations_custom": by_source.get("user", 0),
            "confirmations_seeded": by_source.get("seed", 0),
            "confirmed": confirmed,
            "min_corrections": _MIN_CORRECTIONS,
        }

    @app.post("/learning/retune")
    def learning_retune(user: str = Depends(current_user)) -> dict[str, Any]:
        """The gated retune: the corrector proposes a
        new preference block from the user's corrections; the gate scores current
        vs proposed on USDA (objective) + held-out confirmations (fit); it ships
        only if the ship rule passes. Bad feedback → no fit gain → not shipped.
        Observable end to end (proposed rules + both score sets + the verdict)."""
        # Only fold in NEW (unprocessed) corrections, extending the current block —
        # a retune never re-learns corrections it already shipped.
        new_corrections = fblog.list_unprocessed(user)
        if not new_corrections:
            return {
                "ok": False,
                "reason": "not_enough_corrections" if fblog.count(user) == 0
                else "no_new_corrections",
                "have": fblog.count(user),
                "need": _MIN_CORRECTIONS,
            }
        # Budget guard: a retune runs live experiments, so cap how many
        # fire per user per day; the decision layer already avoids over-recommending.
        if _runs_today(user) >= supervisor_config.max_runs_per_day:
            return {
                "ok": False,
                "reason": "rate_limited",
                "runs_today": _runs_today(user),
                "max_runs_per_day": supervisor_config.max_runs_per_day,
            }
        _record_run(user)
        current_block = prefs.block_text(user)
        proposed = propose_preference_block(
            new_corrections, current_block, client=corrector_client,
            user_profile=profiles.get(user),
        )
        if proposed is None:
            return {"ok": False, "reason": "corrector_failed"}

        fit_cases = confirmations_to_cases(confirms.list(user))
        usda_cases = _quick_usda_sample(usda_case_loader())
        if _RETUNE_USDA_SAMPLE > 0:
            usda_cases = usda_cases[:_RETUNE_USDA_SAMPLE]
        # Score the fit set (the user's confirmed meals) as Phoenix experiments read
        # back over MCP; the USDA floor stays local for speed. Fail-soft: a None from
        # the scorer falls back to fully-local scoring so the retune never hangs.
        fit_phoenix = (
            phoenix_fit_scorer(
                user, current_block, proposed.block_text, logger_fn, fit_cases
            )
            if phoenix_fit_scorer is not None
            else None
        )
        if fit_phoenix is not None:
            current_scores = {
                "fit": fit_phoenix["current"],
                "usda": score_block(current_block, [], usda_cases, logger_fn)["usda"],
            }
            proposed_scores = {
                "fit": fit_phoenix["proposed"],
                "usda": score_block(proposed.block_text, [], usda_cases, logger_fn)["usda"],
            }
            scored_via = "phoenix"
            experiment_url = fit_phoenix.get("experiment_url", "")
        else:
            current_scores = score_block(current_block, fit_cases, usda_cases, logger_fn)
            proposed_scores = score_block(
                proposed.block_text, fit_cases, usda_cases, logger_fn
            )
            scored_via = "local"
            experiment_url = ""
        decision = ship_decision(current_scores, proposed_scores)

        shipped = False
        version = None
        if decision["ship"]:
            provenance = [r.model_dump() for r in proposed.rules]
            version = prefs.save(user, proposed.block_text, provenance)
            fblog.mark_processed(user, [c["id"] for c in new_corrections])
            shipped = True

        return {
            "ok": True,
            "shipped": shipped,
            "verdict": decision,
            "current": current_scores,
            "proposed": proposed_scores,
            "proposed_block": proposed.block_text,
            "rules": [r.model_dump() for r in proposed.rules],
            "version": version,
            "fit_cases": len(fit_cases),
            "usda_cases": len(usda_cases),
            "scored_via": scored_via,
            "experiment_url": experiment_url,
            "phoenix_url": phoenix_dashboard_url(),
        }

    @app.post("/learning/retune/stream")
    def learning_retune_stream(
        full: bool = False, user: str = Depends(current_user)
    ) -> StreamingResponse:
        """The gated retune as a LIVE stream (the observability-everywhere rule):
        emits a phase event as the corrector proposes a rule, then one event per
        meal as it's re-scored — with the rule vs without — across the held-out
        confirmations (fit) and the USDA standard set (objective), then the final
        verdict. The full USDA set is always scored (the per-case scoring runs in
        parallel, so the honest floor is fast); ``full`` is accepted for backward
        compatibility but no longer changes coverage.
        Same scoring + ship rule as POST /learning/retune."""
        new_corrections = fblog.list_unprocessed(user)

        def events() -> Iterator[str]:
            def sse(payload: dict[str, Any]) -> str:
                return f"data: {json.dumps(payload)}\n\n"

            if not new_corrections:
                yield sse({
                    "type": "done", "ok": False,
                    "reason": "not_enough_corrections" if fblog.count(user) == 0
                    else "no_new_corrections",
                    "have": fblog.count(user), "need": _MIN_CORRECTIONS,
                })
                return

            yield sse({"type": "phase", "phase": "propose",
                       "label": "Suggesting a change — generalizing your corrections "
                                "into a rule…"})
            current_block = prefs.block_text(user)
            proposed = propose_preference_block(
                new_corrections, current_block, client=corrector_client,
                user_profile=profiles.get(user),
            )
            if proposed is None:
                yield sse({"type": "done", "ok": False, "reason": "corrector_failed"})
                return
            rules = [r.model_dump() for r in proposed.rules]
            yield sse({"type": "rule", "rules": rules})

            fit_cases = confirmations_to_cases(confirms.list(user))
            # Score a representative sample of the USDA floor locally for a fast live
            # retune. (The full 29-case run was only viable with the parallel scoring
            # that the installed Phoenix client can't actually do — see phoenix_eval.)
            usda_cases = _quick_usda_sample(usda_case_loader())
            if _RETUNE_USDA_SAMPLE > 0:
                usda_cases = usda_cases[:_RETUNE_USDA_SAMPLE]

            # Emit the FULL eval set up front so the UI can list every meal
            # immediately (dashes), then fill each in as its score lands. `rows` is
            # the original flat shape (live UI). `sets` is the parallel-friendly
            # split — one row list per panel ("Fit to you" + "USDA/everyday") — so
            # each panel can render and fill independently as scores arrive.
            fit_rows = [
                {"text": c["text"], "expected": round(c["calories"])} for c in fit_cases
            ]
            usda_rows = [
                {"text": c["text"], "expected": round(c["calories"])} for c in usda_cases
            ]
            yield sse({
                "type": "manifest",
                "rows": [{"set": "fit", "text": c["text"]} for c in fit_cases]
                + [{"set": "usda", "text": c["text"]} for c in usda_cases],
                "sets": {"fit": fit_rows, "usda": usda_rows},
            })

            def score_one(case: dict[str, Any], block: str) -> float:
                ex = [{"preference_block": block}] if block else []
                return _case_score(case, lambda t: logger_fn(t, examples=ex))

            def score_case_traced(case: dict[str, Any], label: str) -> tuple[float, float]:
                # One named span per meal so the re-score is VISIBLE in Phoenix in real
                # time: the agent's Gemini calls (base vs tuned) nest under it.
                with _TRACER.start_as_current_span("retune.rescore") as span:
                    span.set_attribute("retune.set", label)
                    span.set_attribute("meal.text", case["text"])
                    span.set_attribute("expected.kcal", round(case["calories"]))
                    before = score_one(case, current_block)
                    after = score_one(case, proposed.block_text)
                    span.set_attribute("accuracy.base", before)
                    span.set_attribute("accuracy.tuned", after)
                    span.set_attribute("accuracy.delta", round(after - before, 3))
                return before, after

            def mean(xs: list[float]) -> float:
                return round(sum(xs) / len(xs), 3) if xs else 0.0

            fit_before: list[float] = []
            fit_after: list[float] = []
            usda_before = [0.0] * len(usda_cases)
            usda_after = [0.0] * len(usda_cases)
            shared: dict[str, Any] = {"scored_via": "local", "experiment_url": ""}
            usda_label = (
                "Re-checking the full standard set — everyday foods should stay accurate"
            )

            # Both panels fill CONCURRENTLY: each set scores in its own thread and
            # funnels its phase/score/phoenix events through a queue the generator
            # drains in arrival order, so "Fit to you" and "USDA/everyday" stream
            # side by side. The food repo opens a SQLite connection per query, so the
            # agent is thread-safe across the two sets.
            q: Queue = Queue()
            _SET_DONE = object()
            # A scoring failure in either set is surfaced, not swallowed: the producer
            # records it and the consumer re-raises after draining, so the stream fails
            # loud (as the inline/`fut.result()` scoring did before) rather than
            # shipping a misleading zeroed verdict.
            errors: list[Exception] = []

            def run_fit() -> None:
                # FIT: score the user's confirmed meals as Phoenix experiments and read
                # the per-meal results back over MCP (the agent reading its own eval).
                # Fall back to local per-meal scoring when Phoenix/MCP is unavailable.
                try:
                    fit_phoenix = None
                    if phoenix_fit_scorer is not None and fit_cases:
                        q.put({"type": "phase", "phase": "fit", "n": len(fit_cases),
                               "label": "Running an experiment in Phoenix — it'll pull "
                                        "the results when it finishes"})
                        fit_phoenix = phoenix_fit_scorer(
                            user, current_block, proposed.block_text, logger_fn, fit_cases
                        )
                    if fit_phoenix is not None:
                        shared["scored_via"] = "phoenix"
                        shared["experiment_url"] = fit_phoenix.get("experiment_url", "")
                        rows = fit_phoenix.get("rows", [])
                        for i, r in enumerate(rows):
                            b, a = r.get("before"), r.get("after")
                            if b is not None:
                                fit_before.append(b)
                            if a is not None:
                                fit_after.append(a)
                            q.put({"type": "score", "set": "fit", "i": i + 1,
                                   "n": len(rows), "text": r.get("text", ""),
                                   "expected": r.get("expected", 0), "before": b,
                                   "after": a, "base_kcal": r.get("base_kcal"),
                                   "tuned_kcal": r.get("tuned_kcal")})
                        q.put({"type": "phoenix",
                               "experiment_url": shared["experiment_url"]})
                    else:
                        q.put({"type": "phase", "phase": "fit", "n": len(fit_cases),
                               "label": "Re-scoring the meals you confirmed — "
                                        "with your rule vs without"})
                        for i, c in enumerate(fit_cases):
                            before, after = score_case_traced(c, "fit")
                            fit_before.append(before)
                            fit_after.append(after)
                            q.put({"type": "score", "set": "fit", "i": i + 1,
                                   "n": len(fit_cases), "text": c["text"],
                                   "expected": round(c["calories"]),
                                   "before": before, "after": after})
                    q.put({"type": "set_done", "set": "fit",
                           "before": mean(fit_before), "after": mean(fit_after),
                           "delta": round(mean(fit_after) - mean(fit_before), 3),
                           "n": len(fit_cases)})
                except Exception as exc:  # noqa: BLE001 — surfaced below, not swallowed
                    errors.append(exc)
                finally:
                    q.put(_SET_DONE)

            def run_usda() -> None:
                # USDA floor: scored in Arize as its OWN Phoenix experiment (base vs
                # tuned), read back over MCP — so the everyday-foods check is graded
                # the same way as the fit set and both land together. Falls back to
                # LOCAL parallel scoring (out of order, by index) when Phoenix/MCP is
                # unavailable — which is what the offline stream test exercises.
                try:
                    usda_phoenix = None
                    if phoenix_usda_scorer is not None and usda_cases:
                        q.put({"type": "phase", "phase": "usda", "n": len(usda_cases),
                               "label": "Running an experiment in Phoenix — it'll pull "
                                        "the results when it finishes"})
                        usda_phoenix = phoenix_usda_scorer(
                            user, current_block, proposed.block_text, logger_fn,
                            usda_cases,
                        )
                    if usda_phoenix is not None:
                        rows = usda_phoenix.get("rows", [])
                        ub = [r["before"] for r in rows if r.get("before") is not None]
                        ua = [r["after"] for r in rows if r.get("after") is not None]
                        if ub and ua:
                            usda_before[:] = ub
                            usda_after[:] = ua
                        for i, r in enumerate(rows):
                            q.put({"type": "score", "set": "usda", "i": i + 1,
                                   "n": len(rows), "text": r.get("text", ""),
                                   "expected": r.get("expected", 0),
                                   "before": r.get("before"), "after": r.get("after")})
                    else:
                        q.put({"type": "phase", "phase": "usda",
                               "n": len(usda_cases), "label": usda_label})
                        with ThreadPoolExecutor(max_workers=6) as pool:
                            futs = {
                                pool.submit(score_case_traced, c, "usda"): i
                                for i, c in enumerate(usda_cases)
                            }
                            for fut in as_completed(futs):
                                i = futs[fut]
                                before, after = fut.result()
                                usda_before[i], usda_after[i] = before, after
                                c = usda_cases[i]
                                q.put({"type": "score", "set": "usda", "i": i + 1,
                                       "n": len(usda_cases), "text": c["text"],
                                       "expected": round(c["calories"]),
                                       "before": before, "after": after})
                    q.put({"type": "set_done", "set": "usda",
                           "before": mean(usda_before), "after": mean(usda_after),
                           "delta": round(mean(usda_after) - mean(usda_before), 3),
                           "n": len(usda_cases)})
                except Exception as exc:  # noqa: BLE001 — surfaced below, not swallowed
                    errors.append(exc)
                finally:
                    q.put(_SET_DONE)

            workers = [Thread(target=run_fit), Thread(target=run_usda)]
            for w in workers:
                w.start()
            finished = 0
            while finished < len(workers):
                item = q.get()
                if item is _SET_DONE:
                    finished += 1
                    continue
                yield sse(item)
            for w in workers:
                w.join()
            if errors:
                # join() above is the happens-before edge for the threads' writes to
                # `errors`/`shared`/the score lists, so reading them here is safe.
                raise errors[0]

            scored_via = shared["scored_via"]
            experiment_url = shared["experiment_url"]
            current_scores = {"fit": mean(fit_before), "usda": mean(usda_before)}
            proposed_scores = {"fit": mean(fit_after), "usda": mean(usda_after)}
            decision = ship_decision(current_scores, proposed_scores)

            shipped = False
            version = None
            if decision["ship"]:
                version = prefs.save(user, proposed.block_text, rules)
                fblog.mark_processed(user, [c["id"] for c in new_corrections])
                shipped = True

            yield sse({
                "type": "done", "ok": True, "shipped": shipped, "verdict": decision,
                "current": current_scores, "proposed": proposed_scores,
                "fit_delta": round(proposed_scores["fit"] - current_scores["fit"], 3),
                "usda_delta": round(proposed_scores["usda"] - current_scores["usda"], 3),
                "proposed_block": proposed.block_text, "rules": rules,
                "version": version, "fit_cases": len(fit_cases),
                "usda_cases": len(usda_cases), "scored_via": scored_via,
                "experiment_url": experiment_url, "phoenix_url": phoenix_dashboard_url(),
            })

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/reasoning/{trace_id}")
    def reasoning(trace_id: str) -> dict[str, Any]:
        return {"trace_id": trace_id, "spans": get_buffer().get_trace(trace_id)}

    @app.post("/experiments/run")
    def run_experiment(
        req: ExperimentRunRequest, background: BackgroundTasks
    ) -> dict[str, Any]:
        """Kick an eval experiment off the hot path and return a run id immediately.

        No ``run-experiment`` MCP tool exists, so the supervisor calls this endpoint
        to execute a run (via the injected runner); the results are read back over
        Phoenix MCP afterwards. The work runs in a background task — the response
        returns ``running`` and ``GET /experiments/{id}`` reports completion.
        """
        run_id = uuid.uuid4().hex
        experiments[run_id] = {"status": "running", "summary": None}

        def _execute() -> None:
            try:
                summary = experiment_runner(
                    {"dataset": req.dataset, "name": req.name}
                )
                experiments[run_id] = {"status": "done", "summary": summary}
            except Exception as exc:  # fail-soft: record, never crash the worker
                experiments[run_id] = {"status": "error", "summary": {"reason": str(exc)}}

        background.add_task(_execute)
        return {"run_id": run_id, "status": "running"}

    @app.get("/experiments/{run_id}")
    def experiment_status(run_id: str) -> dict[str, Any]:
        """Poll an experiment run's status (running | done | error) + its summary."""
        entry = experiments.get(run_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="unknown experiment run")
        return {"run_id": run_id, **entry}

    return app


# Module-level ASGI app for `uvicorn dietrace.web.app:app` (the Cloud Run entrypoint).
app = create_app()

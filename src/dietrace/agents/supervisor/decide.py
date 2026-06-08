"""Per-meal supervisor decision: pick exactly one of three ops (design §1).

Conservative mode is a deterministic policy (here); powerful mode layers an
LLM-reasoned variant on top (phase 6). The op is *what to do*; the deterministic
gate still decides whether a retune actually ships.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from dietrace.agents.supervisor.config import SupervisorConfig

OP_BANK_FEEDBACK = "bank_feedback"
OP_ADD_DATASET_POINT = "add_dataset_point"
OP_RETUNE = "retune"


@dataclass(frozen=True)
class DecisionSignals:
    """Inputs to the per-meal decision, gathered from the user's stores."""

    was_corrected: bool = False
    new_feedback: int = 0  # unprocessed corrections since the last retune
    dataset_points: int = 0  # held-out fit-set size
    runs_today: int = 0
    meal_confidence: float = 1.0


@dataclass(frozen=True)
class Decision:
    op: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"op": self.op, "reason": self.reason}


def decide(signals: DecisionSignals, config: SupervisorConfig) -> Decision:
    """Deterministic conservative policy → exactly one op.

    Precedence: a correction on this meal is captured first (it's tied to this
    meal); else retune when there's enough *new* signal and we're under the daily
    cap; else the clean meal becomes a held-out dataset point.
    """
    if signals.was_corrected:
        return Decision(OP_BANK_FEEDBACK, "meal was corrected — banking the feedback")

    retune_ready = (
        signals.new_feedback >= config.min_new_feedback
        and signals.dataset_points >= config.min_new_dataset_points
        and signals.runs_today < config.max_runs_per_day
    )
    if retune_ready:
        return Decision(
            OP_RETUNE,
            f"enough new signal ({signals.new_feedback} corrections, "
            f"{signals.dataset_points} dataset points) — retuning",
        )

    return Decision(
        OP_ADD_DATASET_POINT,
        "clean meal accepted as-is — adding to the held-out dataset",
    )


def gather_signals(
    fblog: Any,
    confirms: Any,
    user: str,
    *,
    was_corrected: bool = False,
    runs_today: int = 0,
    meal_confidence: float = 1.0,
) -> DecisionSignals:
    """Build :class:`DecisionSignals` from the user's feedback + confirmation stores."""
    return DecisionSignals(
        was_corrected=was_corrected,
        new_feedback=fblog.count_unprocessed(user),
        dataset_points=confirms.count(user),
        runs_today=runs_today,
        meal_confidence=meal_confidence,
    )


# --- powerful mode: LLM-reasoned decision (phase 6) ------------------------


class _LLMDecision(BaseModel):
    op: Literal["bank_feedback", "add_dataset_point", "retune"]
    rationale: str


def _strip_fences(text: str) -> str:
    """Strip ```json … ``` fences a model may wrap its JSON in."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped.rsplit("```", 1)[0]
    return stripped.strip()


def _llm_prompt(signals: DecisionSignals, config: SupervisorConfig, trend: str) -> str:
    """The supervisor's decision prompt.

    Strong heuristics + a few canonical examples rather than brittle if/else logic,
    so the model reasons about borderline cases. The thresholds are *soft guides*
    here (the prompt) and a *hard guard* in :func:`decide` (the fail-soft fallback);
    the deterministic ship gate — not this decision — still decides whether a retune
    is actually kept.
    """
    f, d, cap = (
        config.min_new_feedback,
        config.min_new_dataset_points,
        config.max_runs_per_day,
    )
    return (
        "You are DietTrace's supervisor. Right after a meal is logged or a piece of "
        "feedback is banked, you choose the single best next action for the learning "
        "loop. You only decide WHEN it's worth testing a retune — a deterministic gate "
        "(not you) decides whether the retune is actually kept, so you can never ship a "
        "regression.\n\n"
        "<actions>\n"
        "- bank_feedback: the user corrected THIS meal; record the correction as signal.\n"
        "- add_dataset_point: a clean, uncorrected meal becomes held-out ground truth.\n"
        "- retune: re-derive the preference block from the banked corrections now.\n"
        "</actions>\n\n"
        "<how_to_decide>\n"
        "Corrections are the SIGNAL that something should change; held-out meals are "
        "how a change gets VALIDATED. So:\n"
        f"- New corrections are the main reason to retune — once roughly {f}+ have "
        "accrued, a retune is worth considering. This is the primary trigger.\n"
        f"- Only retune when there are enough held-out meals to prove it out (roughly "
        f"{d}+) — without a test set a retune can't be trusted, so keep banking dataset "
        "points instead.\n"
        f"- Never retune over the daily budget ({cap} runs/day) — bank a point instead.\n"
        "- If accuracy is already strong and flat, there's less to gain — lean to holding.\n"
        "These are guides, not hard gates; weigh them together.\n"
        "</how_to_decide>\n\n"
        "<examples>\n"
        '{"signals":"was_corrected=true, new_feedback=2, dataset_points=6, runs_today=0",'
        ' "op":"bank_feedback", "rationale":"this meal was corrected — capture it first"}\n'
        '{"signals":"was_corrected=false, new_feedback=0, dataset_points=3, runs_today=0",'
        ' "op":"add_dataset_point", "rationale":"clean meal, no new corrections to act on — '
        'grow the held-out set"}\n'
        '{"signals":"was_corrected=false, new_feedback=4, dataset_points=6, runs_today=0",'
        ' "op":"retune", "rationale":"enough fresh corrections and a held-out set to '
        'validate against — worth testing a retune"}\n'
        '{"signals":"was_corrected=false, new_feedback=5, dataset_points=2, runs_today=0",'
        ' "op":"add_dataset_point", "rationale":"plenty of corrections but too few held-out '
        'meals to trust a retune yet — keep building the test set"}\n'
        '{"signals":"was_corrected=false, new_feedback=6, dataset_points=8, '
        f'runs_today={cap}",'
        ' "op":"add_dataset_point", "rationale":"signal is there but the daily retune '
        'budget is spent — bank a point instead"}\n'
        "</examples>\n\n"
        "<current_signals>\n"
        f"was_corrected={signals.was_corrected}, new_feedback={signals.new_feedback}, "
        f"dataset_points={signals.dataset_points}, "
        f"runs_today={signals.runs_today}/{cap}, "
        f"meal_confidence={signals.meal_confidence:.2f}, "
        f"accuracy_trend={trend or 'n/a'}\n"
        "</current_signals>\n\n"
        'Respond with JSON {"op": ..., "rationale": ...}.'
    )


def _llm_decide(
    signals: DecisionSignals,
    config: SupervisorConfig,
    client: Any,
    *,
    trend: str = "",
) -> Decision:
    """LLM-reasoned op choice; fail-soft to the deterministic policy on any error."""
    from dietrace.llm.config import GEMINI_MODEL

    try:
        from google import genai

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=_llm_prompt(signals, config, trend),
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_LLMDecision,
            ),
        )
        chosen = _LLMDecision.model_validate(
            json.loads(_strip_fences(getattr(response, "text", "") or ""))
        )
    except Exception:
        return decide(signals, config)

    # The daily budget cap stays a hard, deterministic guard even in powerful mode.
    if chosen.op == OP_RETUNE and signals.runs_today >= config.max_runs_per_day:
        return Decision(
            OP_ADD_DATASET_POINT,
            "retune is over the daily budget — adding a dataset point instead",
        )
    return Decision(chosen.op, chosen.rationale)


def decide_op(
    signals: DecisionSignals,
    config: SupervisorConfig,
    *,
    client: Any | None = None,
    trend: str = "",
) -> Decision:
    """Route to the LLM decision in powerful mode (with a client), else deterministic."""
    if config.is_powerful and client is not None:
        return _llm_decide(signals, config, client, trend=trend)
    return decide(signals, config)

"""The conservative per-meal decision picks exactly one of three ops."""

from __future__ import annotations

from types import SimpleNamespace

from dietrace.agents.supervisor.config import SupervisorConfig
from dietrace.agents.supervisor.decide import (
    OP_ADD_DATASET_POINT,
    OP_BANK_FEEDBACK,
    OP_RETUNE,
    DecisionSignals,
    decide,
    gather_signals,
)

# Thresholds: retune needs ≥2 new corrections AND ≥3 dataset points, under 5 runs/day.
_CFG = SupervisorConfig(
    min_new_feedback=2, min_new_dataset_points=3, max_runs_per_day=5
)


def test_corrected_meal_banks_feedback() -> None:
    sig = DecisionSignals(was_corrected=True, new_feedback=9, dataset_points=9)
    assert decide(sig, _CFG).op == OP_BANK_FEEDBACK


def test_clean_meal_below_threshold_adds_dataset_point() -> None:
    sig = DecisionSignals(new_feedback=1, dataset_points=1)  # not enough yet
    assert decide(sig, _CFG).op == OP_ADD_DATASET_POINT


def test_enough_signal_triggers_retune() -> None:
    sig = DecisionSignals(new_feedback=2, dataset_points=3, runs_today=0)
    assert decide(sig, _CFG).op == OP_RETUNE


def test_retune_blocked_below_either_threshold() -> None:
    # Enough feedback but too few dataset points → not yet.
    few_points = DecisionSignals(new_feedback=5, dataset_points=2)
    assert decide(few_points, _CFG).op == OP_ADD_DATASET_POINT
    # Enough dataset points but too little feedback → not yet.
    little_fb = DecisionSignals(new_feedback=1, dataset_points=9)
    assert decide(little_fb, _CFG).op == OP_ADD_DATASET_POINT


def test_daily_cap_blocks_retune() -> None:
    sig = DecisionSignals(new_feedback=9, dataset_points=9, runs_today=5)  # at cap
    assert decide(sig, _CFG).op == OP_ADD_DATASET_POINT


def test_correction_takes_precedence_over_retune() -> None:
    sig = DecisionSignals(was_corrected=True, new_feedback=9, dataset_points=9, runs_today=0)
    assert decide(sig, _CFG).op == OP_BANK_FEEDBACK


class _FakeFblog:
    def __init__(self, n: int) -> None:
        self._n = n

    def count_unprocessed(self, user: str) -> int:
        return self._n


class _FakeConfirms:
    def __init__(self, n: int) -> None:
        self._n = n

    def count(self, user: str) -> int:
        return self._n


class _FakeLLM:
    """A google-genai-shaped client whose generate_content returns canned JSON."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

        class _Models:
            def generate_content(_self, **kwargs):  # noqa: N805
                self.calls += 1
                return SimpleNamespace(text=text)

        self.models = _Models()


def test_conservative_mode_never_calls_the_llm() -> None:
    from dietrace.agents.supervisor.decide import decide_op

    client = _FakeLLM('{"op": "retune", "rationale": "x"}')
    cfg = SupervisorConfig(mode="conservative", min_new_feedback=2, min_new_dataset_points=3)
    sig = DecisionSignals(new_feedback=1, dataset_points=1)
    out = decide_op(sig, cfg, client=client)
    assert out.op == OP_ADD_DATASET_POINT  # deterministic path
    assert client.calls == 0


def test_powerful_mode_uses_the_llm_choice() -> None:
    from dietrace.agents.supervisor.decide import decide_op

    client = _FakeLLM('{"op": "add_dataset_point", "rationale": "looks clean"}')
    cfg = SupervisorConfig(mode="powerful", max_runs_per_day=5)
    # Signals would deterministically bank (was_corrected), but the LLM overrides.
    out = decide_op(DecisionSignals(was_corrected=True), cfg, client=client)
    assert out.op == OP_ADD_DATASET_POINT
    assert out.reason == "looks clean"
    assert client.calls == 1


def test_powerful_mode_enforces_budget_cap_over_llm() -> None:
    from dietrace.agents.supervisor.decide import decide_op

    client = _FakeLLM('{"op": "retune", "rationale": "let us retune"}')
    cfg = SupervisorConfig(mode="powerful", max_runs_per_day=2)
    sig = DecisionSignals(new_feedback=9, dataset_points=9, runs_today=2)  # at cap
    out = decide_op(sig, cfg, client=client)
    assert out.op == OP_ADD_DATASET_POINT  # cap is a hard deterministic guard


def test_powerful_mode_failsoft_to_deterministic_on_bad_json() -> None:
    from dietrace.agents.supervisor.decide import decide_op

    client = _FakeLLM("not json at all")
    cfg = SupervisorConfig(mode="powerful", min_new_feedback=2, min_new_dataset_points=3)
    out = decide_op(DecisionSignals(was_corrected=True), cfg, client=client)
    assert out.op == OP_BANK_FEEDBACK  # fell back to the deterministic policy


def test_powerful_mode_without_client_is_deterministic() -> None:
    from dietrace.agents.supervisor.decide import decide_op

    cfg = SupervisorConfig(mode="powerful")
    out = decide_op(DecisionSignals(was_corrected=True), cfg, client=None)
    assert out.op == OP_BANK_FEEDBACK


def test_llm_prompt_guides_with_heuristics_and_canonical_examples() -> None:
    """The decision prompt guides via soft heuristics + a few canonical examples (not
    brittle if/else), with feedback as the primary trigger and the live signals
    injected for the model to reason over."""
    from dietrace.agents.supervisor.decide import _llm_prompt

    cfg = SupervisorConfig(mode="powerful", min_new_feedback=3, min_new_dataset_points=4)
    prompt = _llm_prompt(
        DecisionSignals(new_feedback=3, dataset_points=4), cfg, trend="flat"
    )
    # Heuristics framed as guides, with feedback primary — not hard-coded conditions.
    assert "primary trigger" in prompt.lower()
    assert "guides, not hard gates" in prompt.lower()
    # Thresholds appear as SOFT guidance ("roughly N+"), keyed off the config values.
    assert "roughly 3+" in prompt and "roughly 4+" in prompt
    # Canonical examples span the key cases (retune-ready, too-few-held-out, budget).
    for op in ('"op":"bank_feedback"', '"op":"add_dataset_point"', '"op":"retune"'):
        assert op in prompt
    # The current signals are injected so the model reasons over the live state.
    assert "new_feedback=3" in prompt and "dataset_points=4" in prompt


def test_decision_carries_phoenix_mcp_detail_per_op() -> None:
    """Each decision carries a short Phoenix-MCP direction + summary for the rail
   : a dataset-point write, a retune's experiment read, none for a
    local bank. Additive — the existing op/reason are untouched."""
    from dietrace.agents.supervisor.decide import phoenix_detail

    assert phoenix_detail(OP_ADD_DATASET_POINT) == "wrote 1 point to your Phoenix dataset"
    assert "read experiment" in phoenix_detail(OP_RETUNE)
    assert phoenix_detail(OP_BANK_FEEDBACK) is None

    # Auto-derived on the Decision and exposed through as_dict (additive key).
    point = decide(DecisionSignals(new_feedback=1, dataset_points=1), _CFG)
    assert point.op == OP_ADD_DATASET_POINT
    assert point.phoenix == "wrote 1 point to your Phoenix dataset"
    assert point.as_dict()["phoenix"] == "wrote 1 point to your Phoenix dataset"
    assert point.as_dict()["op"] == OP_ADD_DATASET_POINT  # existing fields intact

    retune = decide(DecisionSignals(new_feedback=2, dataset_points=3), _CFG)
    assert retune.op == OP_RETUNE
    assert "read experiment" in retune.as_dict()["phoenix"]

    bank = decide(DecisionSignals(was_corrected=True), _CFG)
    assert bank.as_dict()["phoenix"] is None


def test_gather_signals_reads_store_counts() -> None:
    sig = gather_signals(
        _FakeFblog(4), _FakeConfirms(7), "alice", runs_today=2, meal_confidence=0.8
    )
    assert sig.new_feedback == 4
    assert sig.dataset_points == 7
    assert sig.runs_today == 2
    assert sig.meal_confidence == 0.8
    assert sig.was_corrected is False

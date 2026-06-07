"""End-to-end supervisor journey through the real endpoints (offline, stubbed).

Drives the flow the frontend would: log meals (each returns the supervisor's
per-meal decision), make a couple of revisions, confirm meals as held-out
dataset points, then retune once and watch the deterministic gate decide. The
meal logger + corrector + experiment runner are stubbed so the whole loop runs
offline with no Gemini/Phoenix spend; the wiring, decision policy, budget, and
gate are all real. Run with ``-s`` to read the narrative.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from dietrace.web.app import create_app
from dietrace.web.feedback import FeedbackStore
from dietrace.web.preference_stores import (
    ConfirmationStore,
    FeedbackLog,
    PreferenceStore,
    UserProfileStore,
)
from dietrace.web.store import MealLogStore
from dietrace.web.trust import TrustStore

_USER = {"X-DietTrace-User": "alice"}


def _stub_logger(text: str, examples=()) -> dict:
    """A preworkout meal is under-estimated without the preference block and nailed
    with it; everything else is stable — so a good block improves personal fit
    without touching USDA accuracy (mirrors the gate's intent)."""
    has_block = any(e.get("preference_block") for e in (examples or []))
    if "preworkout" in text:
        kcal = 600.0 if has_block else 350.0
    else:
        kcal = 100.0
    return {
        "totals": [{"code": "208", "name": "Energy", "amount": kcal, "unit": "kcal"}],
        "per_item": [{"description": text, "grams": 100.0, "nutrients": []}],
    }


def _fake_corrector() -> object:
    block = {
        "block_text": "Preworkout meals run high on carbs (~90 g).",
        "rules": [
            {
                "rule": "preworkout carbs ~90 g",
                "rationale": "the user confirmed a larger preworkout portion",
                "from_feedback": [],
            }
        ],
    }
    models = SimpleNamespace(
        generate_content=lambda **kw: SimpleNamespace(text=json.dumps(block))
    )
    return SimpleNamespace(models=models)


def _fake_freeform() -> object:
    """Interprets any comment as a portion bump (so the revision banks as Input B)."""
    fb = {
        "kind": "portion_adjust",
        "target_food": "oats",
        "adjustment": 1.5,
        "target_grams": None,
        "scope": "this_food",
        "rationale": "the user says it was a bigger portion",
    }
    models = SimpleNamespace(
        generate_content=lambda **kw: SimpleNamespace(text=json.dumps(fb))
    )
    return SimpleNamespace(models=models)


def _fake_runner(spec: dict) -> dict:
    return {"status": "done", "experiment_id": "exp-e2e", "dataset": spec["dataset"]}


def _build(tmp_path) -> TestClient:
    app = create_app(
        meal_logger=_stub_logger,
        store=MealLogStore(tmp_path / "log.sqlite"),
        feedback_store=FeedbackStore(tmp_path / "fb.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        confirmation_store=ConfirmationStore(tmp_path / "conf.sqlite"),
        feedback_log=FeedbackLog(tmp_path / "fblog.sqlite"),
        preference_store=PreferenceStore(tmp_path / "pref.sqlite"),
        profile_store=UserProfileStore(tmp_path / "profile.sqlite"),
        corrector_client=_fake_corrector(),
        freeform_client=_fake_freeform(),
        experiment_runner=_fake_runner,
        usda_case_loader=lambda: [
            {"text": "usda-egg", "calories": 100.0},
            {"text": "usda-rice", "calories": 100.0},
        ],
        tracer_init=lambda name: None,
    )
    return TestClient(app)


def test_supervisor_end_to_end_journey(tmp_path, monkeypatch, capsys) -> None:
    # Small thresholds so the demo retunes after a couple of signals.
    monkeypatch.setenv("DIETRACE_MIN_NEW_FEEDBACK", "2")
    monkeypatch.setenv("DIETRACE_MIN_NEW_DATASET_POINTS", "2")
    monkeypatch.setenv("DIETRACE_MAX_RUNS_PER_DAY", "5")
    client = _build(tmp_path)

    def log(text: str) -> dict:
        return client.post("/log", json={"text": text}, headers=_USER).json()

    print("\n=== 1. Log a few meals — each carries the supervisor's decision ===")
    for text in ["two eggs and toast", "preworkout oats", "grilled chicken salad"]:
        res = log(text)
        op = res["supervisor"]["op"]
        print(f"  log {text!r:28} -> supervisor: {op} :: {res['supervisor']['reason']}")
        assert op == "add_dataset_point"  # no signal yet → build the held-out set

    print("\n=== 2. Make a couple of revisions (banked corrections) ===")
    for text, fb in [
        ("preworkout oats", "that was way more — a big bowl before my run"),
        ("two eggs and toast", "the toast was two slices, not one"),
    ]:
        client.post(
            "/feedback/freeform",
            json={"meal_text": text, "feedback_text": fb},
            headers=_USER,
        )
        print(f"  revised {text!r}: {fb!r}")

    print("\n=== 3. Confirm meals as held-out dataset points (ground truth) ===")
    confirms = [
        ("preworkout oats", 600.0),
        ("grilled chicken salad", 100.0),
    ]
    for text, kcal in confirms:
        totals = [{"code": "208", "name": "Energy", "amount": kcal, "unit": "kcal"}]
        client.post(
            "/confirm",
            json={"meal_text": text, "items": [], "totals": totals},
            headers=_USER,
        )
        print(f"  confirmed {text!r} @ {kcal:.0f} kcal")

    prefs = client.get("/preferences", headers=_USER).json()
    print(
        f"  state: {prefs['new_corrections']} new corrections, "
        f"{prefs['confirmations']} dataset points"
    )

    print("\n=== 4. Next meal — enough signal now, so the supervisor says RETUNE ===")
    res = log("an apple")
    print(f"  log 'an apple' -> supervisor: {res['supervisor']['op']} :: "
          f"{res['supervisor']['reason']}")
    assert res["supervisor"]["op"] == "retune"

    print("\n=== 5. Run the gated retune once — the deterministic gate decides ===")
    verdict = client.post("/learning/retune", headers=_USER).json()
    print(f"  ok={verdict['ok']} shipped={verdict.get('shipped')}")
    print(f"  current scores: {verdict.get('current')}")
    print(f"  proposed scores: {verdict.get('proposed')}")
    print(f"  verdict: {verdict.get('verdict', {}).get('reason')}")
    assert verdict["ok"] is True
    assert verdict["shipped"] is True  # block improved fit, USDA held → ships
    assert verdict["proposed"]["fit"] > verdict["current"]["fit"]

    print("\n=== 6. The new block now lifts the preworkout estimate ===")
    after = log("preworkout oats")
    kcal = next(t["amount"] for t in after["totals"] if t["code"] == "208")
    print(f"  log 'preworkout oats' -> {kcal:.0f} kcal (was 350 before the block)")
    assert kcal == 600.0  # the shipped block is now injected into parsing

    print("\n=== 7. Experiment run endpoint (the off-hot-path MCP-read path) ===")
    started = client.post("/experiments/run", json={"dataset": "dietrace-user-alice"}).json()
    status = client.get(f"/experiments/{started['run_id']}").json()
    print(f"  run {started['run_id'][:8]}… -> {status['status']} :: {status['summary']}")
    assert status["status"] == "done"

    # Surface the narrative even when the suite runs quietly.
    captured = capsys.readouterr().out
    assert "RETUNE" in captured and "shipped=True" in captured
    print(captured)

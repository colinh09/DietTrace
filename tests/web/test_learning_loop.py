"""End-to-end tests for the learning loop endpoints.

Stub logger + mocked corrector (no Gemini, no Phoenix). Covers: confirm (Input A),
feedback management (Input B), the gated retune (ships on a real held-out fit
gain, rejects otherwise), and that a shipped block reaches /log via injection.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from dietrace.web.app import create_app
from dietrace.web.feedback import FeedbackStore
from dietrace.web.goal_store import GoalStore
from dietrace.web.memory import SqliteMemory
from dietrace.web.preference_stores import (
    ConfirmationStore,
    FeedbackLog,
    PreferenceStore,
)
from dietrace.web.standing_rules import SqliteStandingRuleStore
from dietrace.web.store import MealLogStore
from dietrace.web.trust import TrustStore

_H = {"X-DietTrace-User": "loop-user"}


def _energy(kcal: float) -> list[dict]:
    return [{"code": "208", "name": "Energy", "amount": kcal, "unit": "kcal"}]


def _stub_logger(text: str, examples=None) -> dict:
    """Preworkout meals are under-estimated without the block, accurate with it."""
    has_block = any((e or {}).get("preference_block") for e in (examples or []))
    if "preworkout" in text:
        kcal = 600.0 if has_block else 350.0
    else:
        kcal = 100.0
    return {
        "totals": _energy(kcal),
        "per_item": [{"description": text, "grams": 100.0}],
    }


def _corrector_client(block: str = "Preworkout meals: carbs run high; scale up.") -> Mock:
    payload = json.dumps(
        {
            "block_text": block,
            "rules": [
                {"rule": "Preworkout carbs run high", "rationale": "two corrections",
                 "from_feedback": [1]}
            ],
        }
    )
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=payload)
    return client


def _make_app(tmp_path, *, corrector_client=None, freeform_client=None):
    from dietrace.web.preference_stores import UserProfileStore

    confirms = ConfirmationStore(tmp_path / "confirm.sqlite")
    fblog = FeedbackLog(tmp_path / "fblog.sqlite")
    prefs = PreferenceStore(tmp_path / "pref.sqlite")
    profiles = UserProfileStore(tmp_path / "profile.sqlite")
    app = create_app(
        meal_logger=_stub_logger,
        store=MealLogStore(tmp_path / "log.sqlite"),
        feedback_store=FeedbackStore(tmp_path / "fb.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        goal_store=GoalStore(tmp_path / "goals.sqlite"),
        memory=SqliteMemory(tmp_path / "mem.sqlite"),
        standing_rule_store=SqliteStandingRuleStore(tmp_path / "rules.sqlite"),
        confirmation_store=confirms,
        feedback_log=fblog,
        preference_store=prefs,
        profile_store=profiles,
        corrector_client=corrector_client,
        freeform_client=freeform_client,
        usda_case_loader=lambda: [{"text": "usda meal", "calories": 100}],
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )
    return TestClient(app), confirms, fblog, prefs


# ── Input A: confirmations ──────────────────────────────────────────────────────


def test_confirm_records_a_held_out_datapoint(tmp_path) -> None:
    client, confirms, _, _ = _make_app(tmp_path)
    resp = client.post(
        "/confirm",
        headers=_H,
        json={"meal_text": "preworkout oats", "items": [], "totals": _energy(600)},
    )
    assert resp.status_code == 200
    assert resp.json()["confirmations"] == 1
    assert confirms.count("loop-user") == 1


# ── Input B: feedback management ─────────────────────────────────────────────────


def test_freeform_feedback_is_banked_into_the_feedback_log(tmp_path) -> None:
    fc = Mock()
    fc.models.generate_content.return_value = SimpleNamespace(
        text=json.dumps({"kind": "portion_adjust", "target_food": "oats",
                         "adjustment": 1.5, "scope": "this_food", "rationale": "more carbs"})
    )
    client, _, fblog, _ = _make_app(tmp_path, freeform_client=fc)
    client.post(
        "/feedback/freeform",
        headers=_H,
        json={"meal_id": None, "meal_text": "preworkout oats",
              "feedback_text": "I run more carbs preworkout", "current_items": []},
    )
    assert fblog.count("loop-user") == 1
    assert client.get("/learning/feedback", headers=_H).json()["count"] == 1


def test_correcting_a_meal_removes_it_from_the_gate_set(tmp_path) -> None:
    """XOR: a meal can be confirmed (Input A) OR corrected (Input B), never both.
    Correcting a previously-confirmed meal drops it from the held-out gate set."""
    fc = Mock()
    fc.models.generate_content.return_value = SimpleNamespace(
        text=json.dumps({"kind": "portion_adjust", "target_food": "oats",
                         "adjustment": 0.5, "scope": "this_food", "rationale": "less"})
    )
    client, confirms, _, _ = _make_app(tmp_path, freeform_client=fc)
    client.post("/confirm", headers=_H,
                json={"meal_text": "oatmeal", "items": [], "totals": _energy(300)})
    assert confirms.count("loop-user") == 1  # confirmed → in the gate set

    client.post("/feedback/freeform", headers=_H,
                json={"meal_id": None, "meal_text": "oatmeal",
                      "feedback_text": "less oats", "current_items": []})
    assert confirms.count("loop-user") == 0  # corrected → removed from gate set


def test_confirming_a_meal_removes_its_feedback(tmp_path) -> None:
    """XOR (the other direction): confirming a meal drops any feedback banked
    against it, so it can't be both a correction signal and held-out truth."""
    client, confirms, fblog, _ = _make_app(tmp_path)
    fblog.add("loop-user", "way more oats", None, "oatmeal")
    assert fblog.count("loop-user") == 1

    client.post("/confirm", headers=_H,
                json={"meal_text": "oatmeal", "items": [], "totals": _energy(300)})
    assert confirms.count("loop-user") == 1  # confirmed → in the gate set
    assert fblog.count("loop-user") == 0  # its feedback was dropped (XOR)


def test_edit_and_delete_feedback(tmp_path) -> None:
    client, _, fblog, _ = _make_app(tmp_path)
    fid = fblog.add("loop-user", "original", None, None)
    assert client.patch(
        f"/learning/feedback/{fid}", headers=_H,
        json={"feedback_text": "edited", "weight": 2.0},
    ).json()["ok"] is True
    assert fblog.get(fid, "loop-user")["feedback_text"] == "edited"
    assert client.delete(f"/learning/feedback/{fid}", headers=_H).json()["deleted"] is True
    assert fblog.count("loop-user") == 0


# ── The gated retune ─────────────────────────────────────────────────────────────


def test_retune_ships_when_fit_improves_and_usda_holds(tmp_path) -> None:
    client, confirms, fblog, prefs = _make_app(tmp_path, corrector_client=_corrector_client())
    confirms.add("loop-user", "preworkout oats", [], _energy(600))  # held-out truth
    fblog.add("loop-user", "I run more carbs preworkout")

    body = client.post("/learning/retune", headers=_H).json()
    assert body["ok"] is True
    assert body["shipped"] is True
    assert body["verdict"]["ship"] is True
    assert body["proposed"]["fit"] > body["current"]["fit"]
    assert body["current"]["usda"] == body["proposed"]["usda"]  # USDA held
    # The block was persisted (version 1) and carries provenance.
    assert prefs.get("loop-user")["version"] == 1
    assert body["rules"][0]["rule"]


def test_retune_rejects_a_block_that_does_not_help(tmp_path) -> None:
    # Corrector proposes a block, but there's no preworkout confirmation, so it
    # produces no measurable fit gain → not shipped.
    client, confirms, fblog, prefs = _make_app(tmp_path, corrector_client=_corrector_client())
    confirms.add("loop-user", "plain usda meal", [], _energy(100))
    fblog.add("loop-user", "some vague feedback")

    body = client.post("/learning/retune", headers=_H).json()
    assert body["ok"] is True
    assert body["shipped"] is False
    assert body["verdict"]["fit_gain"] is False
    assert prefs.get("loop-user") is None  # nothing shipped


def test_retune_needs_corrections_first(tmp_path) -> None:
    client, _, _, _ = _make_app(tmp_path, corrector_client=_corrector_client())
    body = client.post("/learning/retune", headers=_H).json()
    assert body["ok"] is False
    assert body["reason"] == "not_enough_corrections"


def test_retune_only_folds_in_new_corrections(tmp_path) -> None:
    """A shipped retune marks its corrections processed; a second retune with
    nothing new is a no-op (no_new_corrections); a fresh correction re-enables it."""
    client, confirms, fblog, _ = _make_app(tmp_path, corrector_client=_corrector_client())
    confirms.add("loop-user", "preworkout oats", [], _energy(600))
    fblog.add("loop-user", "I run more carbs preworkout")

    first = client.post("/learning/retune", headers=_H).json()
    assert first["ok"] is True and first["shipped"] is True
    # The correction is now processed and counts as not-new.
    assert all(f["processed"] for f in fblog.list("loop-user"))
    assert fblog.count_unprocessed("loop-user") == 0
    assert client.get("/preferences", headers=_H).json()["new_corrections"] == 0

    # Re-running with nothing new doesn't re-learn — it reports no_new_corrections.
    again = client.post("/learning/retune", headers=_H).json()
    assert again["ok"] is False
    assert again["reason"] == "no_new_corrections"

    # A new correction makes a retune runnable again.
    fblog.add("loop-user", "even more carbs preworkout")
    assert fblog.count_unprocessed("loop-user") == 1
    third = client.post("/learning/retune", headers=_H).json()
    assert third["ok"] is True


def _sse_events(text: str) -> list[dict]:
    return [
        json.loads(line[len("data: "):])
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


def test_retune_stream_emits_per_meal_scores_then_the_verdict(tmp_path) -> None:
    """The streamed retune is observable: a phase, the proposed rule, one score
    event per re-tested meal (fit + usda), then the final verdict — same ship
    decision as the non-streamed endpoint."""
    client, confirms, fblog, prefs = _make_app(tmp_path, corrector_client=_corrector_client())
    confirms.add("loop-user", "preworkout oats", [], _energy(600))  # held-out truth
    fblog.add("loop-user", "I run more carbs preworkout")

    resp = client.post("/learning/retune/stream", headers=_H)
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    kinds = [e["type"] for e in events]

    assert "phase" in kinds and "rule" in kinds
    # The full eval set is announced up front (fit + usda), before any score, so
    # the UI can list every meal immediately.
    manifest = next(e for e in events if e["type"] == "manifest")
    assert len(manifest["rows"]) >= 1
    assert {r["set"] for r in manifest["rows"]} <= {"fit", "usda"}
    assert kinds.index("manifest") < kinds.index("score")
    scores = [e for e in events if e["type"] == "score"]
    # One score per held-out confirmation (fit) + per USDA case, each carrying a
    # before/after the rule.
    assert any(s["set"] == "fit" for s in scores)
    assert any(s["set"] == "usda" for s in scores)
    assert all("before" in s and "after" in s and s["text"] for s in scores)

    done = events[-1]
    assert done["type"] == "done"
    assert done["ok"] is True and done["shipped"] is True
    assert done["proposed"]["fit"] > done["current"]["fit"]
    assert prefs.get("loop-user")["version"] == 1  # the block shipped + persisted


# ── Injection: a shipped block reaches the agent ─────────────────────────────────


def test_shipped_block_is_injected_into_logging(tmp_path) -> None:
    client, confirms, fblog, prefs = _make_app(tmp_path, corrector_client=_corrector_client())
    confirms.add("loop-user", "preworkout oats", [], _energy(600))
    fblog.add("loop-user", "I run more carbs preworkout")
    client.post("/learning/retune", headers=_H)  # ships the block

    # /preferences shows the learned block.
    prefsresp = client.get("/preferences", headers=_H).json()
    assert prefsresp["block"]["block_text"]
    assert prefsresp["corrections"] == 1 and prefsresp["confirmations"] == 1


# ── User profile: freeform goals/style as standing corrector context ─────────────


def test_profile_set_get_and_reaches_the_corrector(tmp_path) -> None:
    """The freeform profile round-trips through /profile and is injected into the
    corrector's prompt on the next retune (so personalization reflects who the
    user is, not just the meals they fixed)."""
    cc = _corrector_client()
    client, confirms, fblog, _ = _make_app(tmp_path, corrector_client=cc)

    text = "I'm a marathon runner who carb-loads hard before long runs"
    assert client.post("/profile", headers=_H, json={"profile_text": text}).json()["ok"]
    assert client.get("/profile", headers=_H).json()["profile_text"] == text

    confirms.add("loop-user", "preworkout oats", [], _energy(600))
    fblog.add("loop-user", "I run more carbs preworkout")
    client.post("/learning/retune", headers=_H)

    prompt = cc.models.generate_content.call_args.kwargs["contents"]
    assert text in prompt  # the profile reached the corrector


def test_reset_clears_the_profile(tmp_path) -> None:
    client, _, _, _ = _make_app(tmp_path, corrector_client=_corrector_client())
    client.post("/profile", headers=_H, json={"profile_text": "runner who eats big"})
    client.post("/session/reset", headers=_H)
    assert client.get("/profile", headers=_H).json()["profile_text"] == ""

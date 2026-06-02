"""The FastAPI surface: health, log, history, analysis, reasoning (6.1/6.3/6.4).

The meal logger is stubbed and tracing is a no-op, so these exercise the API and
persistence entirely offline.
"""

import datetime
import json

from fastapi.testclient import TestClient

from dietrace.web.app import create_app
from dietrace.web.feedback import FeedbackStore
from dietrace.web.memory import SqliteMemory
from dietrace.web.store import MealLogStore
from dietrace.web.trust import TrustStore

_STUB_TOTALS = [{"code": "208", "name": "Energy", "amount": 105.0, "unit": "kcal"}]


def _stub_logger(text: str, examples=()) -> dict:
    return {"totals": _STUB_TOTALS, "per_item": [{"description": text, "grams": 118.0}]}


def _client(tmp_path, logger=_stub_logger, pusher=lambda *a: False):
    store = MealLogStore(tmp_path / "log.sqlite")
    app = create_app(
        meal_logger=logger,
        store=store,
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        feedback_pusher=pusher,
        tracer_init=lambda name: None,
    )
    return TestClient(app), store


def test_healthz_ok(tmp_path) -> None:
    client, _ = _client(tmp_path)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_log_returns_totals_and_persists(tmp_path) -> None:
    client, store = _client(tmp_path)

    response = client.post("/log", json={"text": "1 banana"})

    assert response.status_code == 200
    body = response.json()
    assert body["totals"][0]["code"] == "208"
    assert isinstance(body["id"], int)
    assert len(store.list()) == 1


def test_history_returns_logged_meals(tmp_path) -> None:
    client, _ = _client(tmp_path)
    client.post("/log", json={"text": "1 banana"})

    response = client.get("/history")

    assert response.status_code == 200
    assert response.json()["meals"][0]["text"] == "1 banana"


def test_history_defaults_to_today_and_filters_by_date(tmp_path) -> None:
    store = MealLogStore(tmp_path / "log.sqlite")
    store.add(
        "old meal", _STUB_TOTALS,
        created_at=datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC),
    )
    store.add("today meal", _STUB_TOTALS)
    app = create_app(store=store, tracer_init=lambda name: None)
    client = TestClient(app)

    # Default = today: the old-dated meal is excluded.
    today_texts = [m["text"] for m in client.get("/history").json()["meals"]]
    assert "today meal" in today_texts
    assert "old meal" not in today_texts

    # An explicit date returns only that day's meals.
    old = client.get("/history", params={"date": "2020-01-01"}).json()["meals"]
    assert [m["text"] for m in old] == ["old meal"]


def test_analysis_aggregates_totals_across_meals(tmp_path) -> None:
    client, _ = _client(tmp_path)
    client.post("/log", json={"text": "1 banana"})
    client.post("/log", json={"text": "another banana"})

    response = client.get("/analysis")

    assert response.status_code == 200
    body = response.json()
    assert body["meal_count"] == 2
    energy = next(t for t in body["totals"] if t["code"] == "208")
    assert energy["amount"] == 210.0
    assert "traces_buffered" in body


def test_reasoning_unknown_trace_is_empty(tmp_path) -> None:
    client, _ = _client(tmp_path)
    response = client.get("/reasoning/deadbeef")
    assert response.status_code == 200
    assert response.json()["spans"] == []


def test_goals_endpoint_returns_targets(tmp_path) -> None:
    client, _ = _client(tmp_path)

    response = client.get("/goals")

    assert response.status_code == 200
    goals = response.json()["goals"]
    by_code = {g["code"]: g for g in goals}
    # Calories + the three macros, by USDA number code.
    assert set(by_code) == {"208", "203", "205", "204"}
    assert all(g["target"] > 0 for g in goals)


def test_analysis_includes_targets_and_remaining(tmp_path) -> None:
    client, _ = _client(tmp_path)
    # Two stubbed meals → 210 kcal of Energy (code 208) consumed.
    client.post("/log", json={"text": "1 banana"})
    client.post("/log", json={"text": "another banana"})

    body = client.get("/analysis").json()

    energy = next(g for g in body["goals"] if g["code"] == "208")
    assert energy["consumed"] == 210.0
    # remaining = target − consumed.
    assert energy["remaining"] == energy["target"] - 210.0
    # A macro with nothing consumed has remaining == its full target.
    protein = next(g for g in body["goals"] if g["code"] == "203")
    assert protein["consumed"] == 0.0
    assert protein["remaining"] == protein["target"]


def test_cors_preflight_allows_default_localhost_origin(tmp_path) -> None:
    client, _ = _client(tmp_path)

    response = client.options(
        "/log",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_origins_come_from_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "DIETRACE_CORS_ORIGINS",
        "https://diettrace.app, https://www.diettrace.app",
    )
    client, _ = _client(tmp_path)

    response = client.options(
        "/log",
        headers={
            "Origin": "https://www.diettrace.app",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"] == "https://www.diettrace.app"
    )


def _trace_logger(text: str, examples=()) -> dict:
    """A logger whose per_item carries the matched USDA food + id and grams."""
    return {
        "totals": _STUB_TOTALS,
        "per_item": [
            {"description": "Rice, white, cooked", "fdc_id": 168878, "grams": 158.0},
            {"description": "Egg, whole, cooked", "fdc_id": 173424, "grams": 50.0},
        ],
    }


def test_log_response_carries_ordered_trace(tmp_path) -> None:
    client, _ = _client(tmp_path, logger=_trace_logger)

    body = client.post("/log", json={"text": "rice and an egg"}).json()
    trace = body["trace"]

    # parse_meal, then (search_nutrition, estimate_portion) per food, then log_entry.
    assert [step["step"] for step in trace] == [
        "parse_meal",
        "search_nutrition",
        "estimate_portion",
        "search_nutrition",
        "estimate_portion",
        "log_entry",
    ]

    # Each search step names the matched USDA food + its fdc_id.
    assert trace[1]["matched"] == "Rice, white, cooked"
    assert trace[1]["fdc_id"] == 168878
    assert trace[3]["matched"] == "Egg, whole, cooked"
    assert trace[3]["fdc_id"] == 173424

    # Each portion step names the food + its grams.
    assert trace[2]["food"] == "Rice, white, cooked"
    assert trace[2]["grams"] == 158.0
    assert trace[4]["food"] == "Egg, whole, cooked"
    assert trace[4]["grams"] == 50.0

    # The per-food steps stay ordered by food across the whole trace.
    assert [step["food"] for step in trace if "food" in step] == [
        "Rice, white, cooked",
        "Rice, white, cooked",
        "Egg, whole, cooked",
        "Egg, whole, cooked",
    ]

    # The final step carries the summed totals.
    assert trace[-1]["step"] == "log_entry"
    assert trace[-1]["totals"] == _STUB_TOTALS


_CLEAN_TOTALS = [
    {"code": "208", "name": "Energy", "amount": 384.0, "unit": "kcal"},
    {"code": "203", "name": "Protein", "amount": 30.0, "unit": "g"},
    {"code": "205", "name": "Carbohydrate", "amount": 40.0, "unit": "g"},
    {"code": "204", "name": "Total lipid (fat)", "amount": 11.6, "unit": "g"},
]


def _clean_logger(text: str, examples=()) -> dict:
    """A logger whose item resolved cleanly to USDA and reconciles by Atwater."""
    return {
        "totals": _CLEAN_TOTALS,
        "per_item": [{"description": "chicken breast", "fdc_id": 171477, "grams": 140.0}],
    }


def test_log_response_carries_confidence_and_reasons(tmp_path) -> None:
    # A clean log (USDA match, plausible portion, calories reconcile) scores high
    # with no reasons; the response surfaces the online-eval result.
    client, _ = _client(tmp_path, logger=_clean_logger)

    body = client.post("/log", json={"text": "a chicken breast"}).json()

    assert isinstance(body["confidence"], (int, float))
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["confidence"] > 0.9
    assert body["reasons"] == []


def test_log_response_reports_low_confidence_with_reasons(tmp_path) -> None:
    # The default stub item has no fdc_id (web-trust) and its energy doesn't
    # reconcile to its (absent) macros — confidence drops and reasons explain why.
    client, _ = _client(tmp_path)

    body = client.post("/log", json={"text": "1 banana"}).json()

    assert body["confidence"] < 0.9
    assert isinstance(body["reasons"], list) and body["reasons"]


def _low_conf_logger(text: str, examples=()) -> dict:
    """A web-trust item with an absurd portion and no macros to reconcile the
    energy against — several axes fail, so confidence lands below 0.6 (12.3)."""
    return {"totals": _STUB_TOTALS, "per_item": [{"description": text, "grams": 9000.0}]}


def test_low_confidence_log_flags_needs_review(tmp_path) -> None:
    # Below the 0.6 review threshold the response sets needs_review with the top
    # reason, so the meal row can offer a calm "review?" affordance.
    client, _ = _client(tmp_path, logger=_low_conf_logger)

    body = client.post("/log", json={"text": "a mystery dish"}).json()

    assert body["confidence"] < 0.6
    assert body["needs_review"] is True
    assert isinstance(body["review_reason"], str) and body["review_reason"]


def test_high_confidence_log_does_not_need_review(tmp_path) -> None:
    # A confident log isn't flagged and carries no review reason.
    client, _ = _client(tmp_path, logger=_clean_logger)

    body = client.post("/log", json={"text": "a chicken breast"}).json()

    assert body["needs_review"] is False
    assert body["review_reason"] is None


def _low_conf_streamer(text, examples=()):
    # A web-trust item with an absurd portion + only-energy totals → low confidence.
    yield {"type": "step", "step": "parse_meal", "status": "done", "summary": "1 food"}
    yield {
        "type": "result",
        "per_item": [{"description": text, "grams": 9000.0}],
        "totals": _STUB_TOTALS,
        "trace": [],
    }


def test_stream_result_carries_needs_review(tmp_path, monkeypatch) -> None:
    # The streamed result event also surfaces the review flag.
    monkeypatch.setenv("DIETRACE_STREAM_PACE", "0")
    app = create_app(
        meal_streamer=_low_conf_streamer,
        store=MealLogStore(tmp_path / "log.sqlite"),
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        tracer_init=lambda name: None,
    )
    response = TestClient(app).post("/log/stream", json={"text": "a mystery dish"})

    events = [
        json.loads(line[6:])
        for line in response.text.split("\n\n")
        if line.startswith("data: ")
    ]
    result = events[-1]
    assert result["type"] == "result"
    assert result["needs_review"] is True
    assert isinstance(result["review_reason"], str) and result["review_reason"]


def test_recalled_log_carries_confidence_and_reasons(tmp_path) -> None:
    client, _ = _client(tmp_path)
    client.post(
        "/correct",
        json={
            "meal_text": "chipotle bowl",
            "items": [
                {
                    "description": "Chipotle Chicken",
                    "fdc_id": 171477,
                    "original_grams": 113.0,
                    "corrected_grams": 113.0,
                    "nutrients": [
                        {"code": "208", "name": "Energy", "amount": 180.0, "unit": "kcal"}
                    ],
                }
            ],
        },
        headers={"X-DietTrace-User": "alice"},
    )

    body = client.post(
        "/log", json={"text": "chipotle bowl"}, headers={"X-DietTrace-User": "alice"}
    ).json()

    assert body["recalled"] is True
    assert isinstance(body["confidence"], (int, float))
    assert 0.0 <= body["confidence"] <= 1.0
    assert isinstance(body["reasons"], list)


def test_meals_are_scoped_per_user(tmp_path) -> None:
    # Each user only sees their own meals — the per-user memory layer.
    client, _ = _client(tmp_path)
    client.post("/log", json={"text": "alice meal"}, headers={"X-DietTrace-User": "alice"})
    client.post("/log", json={"text": "bob meal"}, headers={"X-DietTrace-User": "bob"})

    alice = client.get("/history", headers={"X-DietTrace-User": "alice"}).json()["meals"]
    bob = client.get("/history", headers={"X-DietTrace-User": "bob"}).json()["meals"]

    assert [m["text"] for m in alice] == ["alice meal"]
    assert [m["text"] for m in bob] == ["bob meal"]


def test_one_user_cannot_delete_anothers_meal(tmp_path) -> None:
    client, _ = _client(tmp_path)
    meal_id = client.post(
        "/log", json={"text": "alice meal"}, headers={"X-DietTrace-User": "alice"}
    ).json()["id"]

    # Bob tries to delete Alice's meal — refused; it still belongs to Alice.
    denied = client.delete(f"/meals/{meal_id}", headers={"X-DietTrace-User": "bob"}).json()
    assert denied["deleted"] is False
    alice = client.get("/history", headers={"X-DietTrace-User": "alice"}).json()["meals"]
    assert len(alice) == 1


def test_trust_endpoint_rolls_up_logged_eval_results(tmp_path) -> None:
    # Each /log persists its online-eval result; /trust returns the rolling stats
    # (count, mean confidence, % needs_review, source breakdown) — .
    client, _ = _client(tmp_path, logger=_clean_logger)

    client.post("/log", json={"text": "a chicken breast"})
    client.post("/log", json={"text": "a chicken breast"})

    trust = client.get("/trust").json()
    assert trust["count"] == 2
    assert 0.0 <= trust["mean_confidence"] <= 1.0
    assert trust["mean_confidence"] > 0.9
    assert trust["needs_review_pct"] == 0.0
    # The clean logger resolves to a real USDA id, so the source is usda.
    assert trust["source_breakdown"].get("usda") == 2


def test_trust_counts_low_confidence_logs_as_needs_review(tmp_path) -> None:
    client, _ = _client(tmp_path, logger=_low_conf_logger)

    client.post("/log", json={"text": "a mystery dish"})

    trust = client.get("/trust").json()
    assert trust["count"] == 1
    assert trust["needs_review_pct"] == 1.0
    assert trust["source_breakdown"].get("web") == 1


def test_trust_recent_low_confidence_carries_the_meal_text(tmp_path) -> None:
    # The /trust dashboard's recent list needs the original meal text + reason
    # so the user can see which logs to revisit.
    client, _ = _client(tmp_path, logger=_low_conf_logger)

    client.post("/log", json={"text": "a mystery dish"})

    recent = client.get("/trust").json()["recent_low_confidence"]
    assert recent and recent[0]["text"] == "a mystery dish"
    assert recent[0]["review_reason"]


def test_trust_stats_are_per_user(tmp_path) -> None:
    # One user's logs never leak into another's trust stats (per-user isolation).
    client, _ = _client(tmp_path, logger=_clean_logger)
    client.post(
        "/log", json={"text": "a chicken breast"}, headers={"X-DietTrace-User": "alice"}
    )
    client.post(
        "/log", json={"text": "a chicken breast"}, headers={"X-DietTrace-User": "bob"}
    )
    client.post(
        "/log", json={"text": "a chicken breast"}, headers={"X-DietTrace-User": "bob"}
    )

    alice = client.get("/trust", headers={"X-DietTrace-User": "alice"}).json()
    bob = client.get("/trust", headers={"X-DietTrace-User": "bob"}).json()
    assert alice["count"] == 1
    assert bob["count"] == 2


def test_correction_counts_are_per_user(tmp_path) -> None:
    client, _ = _client(tmp_path)
    body = {"food": "x", "original_grams": 100.0, "corrected_grams": 50.0, "nutrients": []}
    client.post("/feedback", json=body, headers={"X-DietTrace-User": "alice"})
    client.post("/feedback", json=body, headers={"X-DietTrace-User": "alice"})
    client.post("/feedback", json=body, headers={"X-DietTrace-User": "bob"})

    alice = client.get("/feedback", headers={"X-DietTrace-User": "alice"}).json()
    bob = client.get("/feedback", headers={"X-DietTrace-User": "bob"}).json()
    assert alice["total_corrections"] == 2
    assert bob["total_corrections"] == 1


def test_correction_rescales_items_and_reports_totals(tmp_path) -> None:
    client, _ = _client(tmp_path)
    body = client.post(
        "/correct",
        json={
            "meal_text": "a snack",
            "items": [
                {
                    "description": "almonds",
                    "original_grams": 100.0,
                    "corrected_grams": 50.0,
                    "nutrients": [
                        {"code": "208", "name": "Energy", "amount": 200.0, "unit": "kcal"}
                    ],
                }
            ],
        },
    ).json()

    assert body["ok"] and body["corrections"] == 1
    assert body["per_item"][0]["grams"] == 50.0
    # 200 kcal at 100 g → 100 kcal at 50 g.
    assert {t["code"]: t["amount"] for t in body["totals"]}["208"] == 100.0


def test_corrected_meal_is_recalled_on_the_next_identical_log(tmp_path) -> None:
    client, _ = _client(tmp_path)
    client.post(
        "/correct",
        json={
            "meal_text": "chipotle bowl",
            "items": [
                {
                    "description": "Chipotle Chicken",
                    "original_grams": 113.0,
                    "corrected_grams": 113.0,
                    "nutrients": [
                        {"code": "208", "name": "Energy", "amount": 180.0, "unit": "kcal"}
                    ],
                }
            ],
        },
        headers={"X-DietTrace-User": "alice"},
    )

    # Re-logging the same meal (any spacing/case) is served from memory, not the agent.
    body = client.post(
        "/log", json={"text": "Chipotle Bowl"}, headers={"X-DietTrace-User": "alice"}
    ).json()
    assert body["recalled"] is True
    assert [i["description"] for i in body["per_item"]] == ["Chipotle Chicken"]
    assert body["trace"][0]["step"] == "recall"


def test_recall_is_scoped_to_the_correcting_user(tmp_path) -> None:
    client, _ = _client(tmp_path)
    client.post(
        "/correct",
        json={
            "meal_text": "chipotle bowl",
            "items": [
                {
                    "description": "Chicken",
                    "original_grams": 100.0,
                    "corrected_grams": 100.0,
                    "nutrients": [],
                }
            ],
        },
        headers={"X-DietTrace-User": "alice"},
    )

    # Bob logging the same words gets the agent (the stub), not Alice's memory.
    bob = client.post(
        "/log", json={"text": "chipotle bowl"}, headers={"X-DietTrace-User": "bob"}
    ).json()
    assert bob.get("recalled") is not True


def test_retune_reports_before_after_accuracy_on_the_users_corrections(tmp_path) -> None:
    # A logger that overshoots without the user's examples, nails it with them.
    def learning_logger(text, examples=()):
        cal = 750.0 if examples else 1440.0
        return {
            "totals": [{"code": "208", "name": "Energy", "amount": cal, "unit": "kcal"}],
            "per_item": [],
        }

    client, _ = _client(tmp_path, logger=learning_logger)
    client.post(
        "/correct",
        json={
            "meal_text": "chipotle bowl",
            "items": [
                {
                    "description": "bowl",
                    "original_grams": 100.0,
                    "corrected_grams": 100.0,
                    "nutrients": [
                        {"code": "208", "name": "Energy", "amount": 750.0, "unit": "kcal"}
                    ],
                }
            ],
        },
        headers={"X-DietTrace-User": "alice"},
    )

    res = client.post("/retune", headers={"X-DietTrace-User": "alice"}).json()
    assert res["cases"] == 1
    assert res["after"] > res["before"]
    assert res["improved"] is True


def test_retune_stream_emits_a_case_then_a_summary(tmp_path) -> None:
    def learning_logger(text, examples=()):
        cal = 750.0 if examples else 1440.0
        return {
            "totals": [{"code": "208", "name": "Energy", "amount": cal, "unit": "kcal"}],
            "per_item": [],
        }

    client, _ = _client(tmp_path, logger=learning_logger)
    client.post(
        "/correct",
        json={
            "meal_text": "chipotle bowl",
            "items": [
                {
                    "description": "bowl",
                    "original_grams": 100.0,
                    "corrected_grams": 100.0,
                    "nutrients": [
                        {"code": "208", "name": "Energy", "amount": 750.0, "unit": "kcal"}
                    ],
                }
            ],
        },
        headers={"X-DietTrace-User": "alice"},
    )

    res = client.post("/retune/stream", headers={"X-DietTrace-User": "alice"})
    events = [
        json.loads(line[6:])
        for line in res.text.split("\n\n")
        if line.startswith("data: ")
    ]
    assert events[0]["type"] == "case" and events[0]["text"] == "chipotle bowl"
    assert events[0]["after"] > events[0]["before"]
    assert events[-1]["type"] == "summary" and events[-1]["improved"] is True


def test_retune_with_no_corrections_is_a_noop(tmp_path) -> None:
    client, _ = _client(tmp_path)
    res = client.post("/retune", headers={"X-DietTrace-User": "nobody"}).json()
    assert res["cases"] == 0 and res["before"] is None


def test_feedback_records_and_pushes_a_correction_to_arize(tmp_path) -> None:
    pushed: list[tuple] = []

    def recording_pusher(inp, out, meta) -> bool:
        pushed.append((inp, out, meta))
        return True

    client, _ = _client(tmp_path, pusher=recording_pusher)

    response = client.post(
        "/feedback",
        json={
            "food": "Five Guys Bacon Cheeseburger",
            "original_grams": 317.0,
            "corrected_grams": 158.5,
            "nutrients": [{"code": "208", "name": "Energy", "amount": 920.0, "unit": "kcal"}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] and body["added_to_arize"] is True
    assert body["total_corrections"] == 1
    # The pushed example carries the corrected (halved) ground truth.
    inp, out, _meta = pushed[0]
    assert inp == {"text": "Five Guys Bacon Cheeseburger"}
    assert out["grams"] == 158.5 and out["calories"] == 460.0


def test_feedback_is_recorded_even_when_the_arize_push_fails(tmp_path) -> None:
    # Phoenix unreachable → push returns False, but the correction is still saved.
    client, _ = _client(tmp_path, pusher=lambda *a: False)

    body = client.post(
        "/feedback",
        json={"food": "x", "original_grams": 100.0, "corrected_grams": 50.0, "nutrients": []},
    ).json()

    assert body["added_to_arize"] is False
    assert body["total_corrections"] == 1
    assert client.get("/feedback").json()["total_corrections"] == 1


def _web_trace_logger(text: str, examples=()) -> dict:
    """A logger whose item came from the grounded web fallback (fdc_id 0)."""
    return {
        "totals": _STUB_TOTALS,
        "per_item": [
            {"description": "Five Guys Bacon Cheeseburger", "fdc_id": 0, "grams": 317.0}
        ],
    }


def test_log_trace_marks_a_web_grounded_food_as_a_web_search(tmp_path) -> None:
    client, _ = _client(tmp_path, logger=_web_trace_logger)

    trace = client.post("/log", json={"text": "a Five Guys bacon cheeseburger"}).json()["trace"]

    # The fdc_id-0 item is reported as a web search, not a USDA match.
    assert [step["step"] for step in trace] == [
        "parse_meal",
        "web_search",
        "estimate_portion",
        "log_entry",
    ]
    assert "web" in trace[1]["summary"].lower()
    assert "USDA food 0" not in trace[1]["summary"]


def test_delete_meal_removes_it(tmp_path) -> None:
    client, store = _client(tmp_path)
    client.post("/log", json={"text": "1 banana"})
    meal_id = store.list()[0]["id"]

    response = client.delete(f"/meals/{meal_id}")

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert store.list() == []


def test_analysis_is_date_scoped(tmp_path) -> None:
    client, store = _client(tmp_path)
    store.add("today", [{"code": "208", "name": "Energy", "amount": 100.0, "unit": "kcal"}],
              date="2026-05-31")
    store.add("yesterday", [{"code": "208", "name": "Energy", "amount": 500.0, "unit": "kcal"}],
              date="2026-05-30")

    body = client.get("/analysis?date=2026-05-31").json()

    assert body["date"] == "2026-05-31"
    assert body["meal_count"] == 1
    energy = next(t for t in body["totals"] if t["code"] == "208")
    assert energy["amount"] == 100.0  # only today's meal, not the 500 from yesterday


def test_log_accepts_client_date(tmp_path) -> None:
    client, store = _client(tmp_path)
    client.post("/log", json={"text": "1 banana", "date": "2026-05-31"})
    assert store.list()[0]["date"] == "2026-05-31"


_ENERGY = [{"code": "208", "name": "Energy", "amount": 143.0, "unit": "kcal"}]


def _fake_streamer(text, examples=()):
    yield {"type": "step", "step": "parse_meal", "status": "done", "summary": "1 food"}
    yield {"type": "step", "step": "log_entry", "status": "done", "totals": _ENERGY}
    yield {"type": "result", "per_item": [], "totals": _ENERGY, "trace": []}


def test_log_stream_emits_events_and_persists(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DIETRACE_STREAM_PACE", "0")
    store = MealLogStore(tmp_path / "log.sqlite")
    app = create_app(
        meal_streamer=_fake_streamer,
        store=store,
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        tracer_init=lambda name: None,
    )
    client = TestClient(app)

    response = client.post("/log/stream", json={"text": "one egg"})

    assert response.status_code == 200
    events = [
        json.loads(line[6:])
        for line in response.text.split("\n\n")
        if line.startswith("data: ")
    ]
    assert [e["type"] for e in events] == ["step", "step", "result"]
    assert isinstance(events[-1]["id"], int)
    # The result event also carries the online-eval confidence + reasons (12.2).
    assert isinstance(events[-1]["confidence"], (int, float))
    assert isinstance(events[-1]["reasons"], list)
    assert len(store.list()) == 1


def test_accuracy_endpoint_returns_the_report(tmp_path) -> None:
    client, _ = _client(tmp_path)
    body = client.get("/accuracy").json()
    assert "metrics" in body and len(body["loop"]) == 4
    assert body["phoenix_url"]

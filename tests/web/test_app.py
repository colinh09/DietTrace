"""The FastAPI surface: health, log, history, analysis, reasoning (6.1/6.3/6.4).

The meal logger is stubbed and tracing is a no-op, so these exercise the API and
persistence entirely offline.
"""

import datetime
import json

from fastapi.testclient import TestClient

from dietrace.web.app import create_app
from dietrace.web.store import MealLogStore

_STUB_TOTALS = [{"code": "208", "name": "Energy", "amount": 105.0, "unit": "kcal"}]


def _stub_logger(text: str) -> dict:
    return {"totals": _STUB_TOTALS, "per_item": [{"description": text, "grams": 118.0}]}


def _client(tmp_path, logger=_stub_logger):
    store = MealLogStore(tmp_path / "log.sqlite")
    app = create_app(meal_logger=logger, store=store, tracer_init=lambda name: None)
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


def _trace_logger(text: str) -> dict:
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


def _web_trace_logger(text: str) -> dict:
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


def _fake_streamer(text):
    yield {"type": "step", "step": "parse_meal", "status": "done", "summary": "1 food"}
    yield {"type": "step", "step": "log_entry", "status": "done", "totals": _ENERGY}
    yield {"type": "result", "per_item": [], "totals": _ENERGY, "trace": []}


def test_log_stream_emits_events_and_persists(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DIETRACE_STREAM_PACE", "0")
    store = MealLogStore(tmp_path / "log.sqlite")
    app = create_app(
        meal_streamer=_fake_streamer, store=store, tracer_init=lambda name: None
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
    assert len(store.list()) == 1


def test_accuracy_endpoint_returns_the_report(tmp_path) -> None:
    client, _ = _client(tmp_path)
    body = client.get("/accuracy").json()
    assert "metrics" in body and len(body["loop"]) == 4
    assert body["phoenix_url"]

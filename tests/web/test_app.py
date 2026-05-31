"""The FastAPI surface: health, log, history, analysis, reasoning (6.1/6.3/6.4).

The meal logger is stubbed and tracing is a no-op, so these exercise the API and
persistence entirely offline.
"""

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

"""The FastAPI surface: health, log, history, analysis, reasoning (6.1/6.3/6.4).

The meal logger is stubbed and tracing is a no-op, so these exercise the API and
persistence entirely offline.
"""

from fastapi.testclient import TestClient

from dietrace.web.app import _parse_agent_output, create_app
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


def test_parse_agent_output_strips_json_fences() -> None:
    # The live agent wraps its final JSON in a ```json fence; parsing must handle it.
    raw = '```json\n{"per_item": [{"description": "egg", "grams": 100.0}], "totals": []}\n```'
    parsed = _parse_agent_output(raw)
    assert parsed["per_item"][0]["description"] == "egg"
    assert parsed["totals"] == []


def test_parse_agent_output_handles_bare_json_and_defaults() -> None:
    parsed = _parse_agent_output('{"per_item": []}')
    assert parsed["per_item"] == []
    assert parsed["totals"] == []  # defaulted when absent


def test_parse_agent_output_falls_back_on_garbage() -> None:
    parsed = _parse_agent_output("sorry, I could not parse that")
    assert parsed["totals"] == []
    assert parsed["per_item"] == []
    assert "raw" in parsed

"""PhoenixMCPClient parses MCP tool results and calls the right tools (mocked)."""

from __future__ import annotations

import json

from dietrace.agents.supervisor.phoenix_mcp import (
    PhoenixMCPClient,
    mcp_available,
    user_dataset_name,
)


class _FakeContent:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResult:
    def __init__(self, payload: object, is_error: bool = False) -> None:
        self.isError = is_error
        self.content = [_FakeContent(json.dumps(payload))]


class _FakeSession:
    """Records tool calls and returns a canned JSON payload."""

    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict) -> _FakeResult:
        self.calls.append((name, arguments))
        return _FakeResult(self._payload)


# ---- reads ---------------------------------------------------------------


async def test_get_recent_experiments_parses_and_calls_tool() -> None:
    session = _FakeSession({"experiments": [{"id": "e1"}, {"id": "e2"}]})
    client = PhoenixMCPClient(_session=session)

    experiments = await client.get_recent_experiments("ds1", limit=5)

    assert [e["id"] for e in experiments] == ["e1", "e2"]
    assert session.calls[0] == ("list-experiments-for-dataset", {"dataset_id": "ds1", "limit": 5})


async def test_list_datasets_unwraps_payload() -> None:
    session = _FakeSession([{"id": "d1", "name": "dietrace-nutrition-v1"}])
    client = PhoenixMCPClient(_session=session)

    datasets = await client.list_datasets()

    assert datasets[0]["name"] == "dietrace-nutrition-v1"
    assert session.calls[0] == ("list-datasets", {})


async def test_get_experiment_results_unwraps_experiment_result() -> None:
    payload = {
        "metadata": {"id": "exp14"},
        "experimentResult": [
            {"example_id": "e1", "input": {"text": "egg"}, "reference_output": {}, "output": {}},
        ],
    }
    client = PhoenixMCPClient(_session=_FakeSession(payload))

    results = await client.get_experiment_results("exp14")

    assert results[0]["example_id"] == "e1"


async def test_get_spans_uses_camel_trace_id() -> None:
    session = _FakeSession({"spans": [{"name": "parse_meal"}]})
    client = PhoenixMCPClient(_session=session)

    spans = await client.get_spans("trace-9")

    assert spans[0]["name"] == "parse_meal"
    assert session.calls[0] == ("get-spans", {"traceId": "trace-9"})


async def test_find_dataset_matches_by_name() -> None:
    session = _FakeSession(
        [{"id": "d1", "name": "other"}, {"id": "d2", "name": "dietrace-user-alice"}]
    )
    client = PhoenixMCPClient(_session=session)

    found = await client.find_dataset("dietrace-user-alice")

    assert found == {"id": "d2", "name": "dietrace-user-alice"}


# ---- write ---------------------------------------------------------------


async def test_add_dataset_examples_calls_write_tool() -> None:
    session = _FakeSession({"added": 1})
    client = PhoenixMCPClient(_session=session)
    examples = [{"input": {"text": "oats"}, "output": {"calories": 300}, "metadata": {}}]

    out = await client.add_dataset_examples("dietrace-user-alice", examples)

    assert out == {"added": 1}
    name, args = session.calls[0]
    assert name == "add-dataset-examples"
    assert args["dataset_name"] == "dietrace-user-alice"
    assert args["examples"] == examples


# ---- helpers / fail-soft -------------------------------------------------


def test_user_dataset_name_is_deterministic() -> None:
    assert user_dataset_name("alice") == "dietrace-user-alice"


def test_mcp_available_requires_both_creds(monkeypatch) -> None:
    monkeypatch.delenv("PHOENIX_API_KEY", raising=False)
    monkeypatch.delenv("PHOENIX_BASE_URL", raising=False)
    assert mcp_available() is False
    monkeypatch.setenv("PHOENIX_API_KEY", "k")
    assert mcp_available() is False  # base url still missing
    monkeypatch.setenv("PHOENIX_BASE_URL", "https://app.phoenix.arize.com/s/ws")
    assert mcp_available() is True

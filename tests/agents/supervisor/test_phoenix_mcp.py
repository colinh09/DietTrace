"""PhoenixMCPClient parses MCP tool results over an injected session (5.5)."""

import json

from dietrace.agents.supervisor.phoenix_mcp import PhoenixMCPClient


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


async def test_get_recent_experiments_parses_and_calls_tool() -> None:
    session = _FakeSession({"experiments": [{"id": "e1"}, {"id": "e2"}]})
    client = PhoenixMCPClient(_session=session)

    experiments = await client.get_recent_experiments("ds1", limit=5)

    assert [e["id"] for e in experiments] == ["e1", "e2"]
    assert session.calls[0][0] == "list-experiments-for-dataset"
    assert session.calls[0][1] == {"dataset_id": "ds1", "limit": 5}


async def test_list_datasets_unwraps_payload() -> None:
    session = _FakeSession([{"id": "d1", "name": "dietrace-nutrition-v1"}])
    client = PhoenixMCPClient(_session=session)

    datasets = await client.list_datasets()

    assert datasets[0]["name"] == "dietrace-nutrition-v1"


async def test_get_experiment_results_unwraps_experiment_result() -> None:
    payload = {
        "metadata": {"id": "exp14"},
        "experimentResult": [
            {"example_id": "e1", "input": {"text": "egg"}, "reference_output": {}, "output": {}},
        ],
    }
    session = _FakeSession(payload)
    client = PhoenixMCPClient(_session=session)

    results = await client.get_experiment_results("exp14")

    assert results[0]["example_id"] == "e1"
    assert session.calls[0][0] == "get-experiment-by-id"
    assert session.calls[0][1] == {"experiment_id": "exp14"}

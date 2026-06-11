"""PhoenixMCPClient parses MCP tool results and calls the right tools (mocked)."""

from __future__ import annotations

import json

import pytest

from dietrace.agents.supervisor.phoenix_mcp import (
    PhoenixMCPClient,
    mcp_available,
    user_dataset_name,
)


class _FakeContent:
    def __init__(self, text: str) -> None:
        self.text = text


class _NoTextContent:
    """A content block with no ``text`` attribute (e.g. an image/blob part)."""


class _FakeResult:
    def __init__(self, payload: object, is_error: bool = False) -> None:
        self.isError = is_error
        self.content = [_FakeContent(json.dumps(payload))]


class _RawResult:
    """A result whose content blocks are supplied verbatim (no JSON wrapping)."""

    def __init__(self, content: list, is_error: bool = False) -> None:
        self.isError = is_error
        self.content = content


class _FakeSession:
    """Records tool calls and returns a canned JSON payload."""

    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict) -> _FakeResult:
        self.calls.append((name, arguments))
        return _FakeResult(self._payload)


class _CannedResultSession:
    """Returns a pre-built result object verbatim from every tool call."""

    def __init__(self, result: object) -> None:
        self._result = result
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict) -> object:
        self.calls.append((name, arguments))
        return self._result


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


async def test_list_datasets_unwraps_datasets_key() -> None:
    """The MCP server may wrap the list under a ``datasets`` key instead of returning a
    bare array; that shape is unwrapped too, not dropped to an empty read."""
    session = _FakeSession({"datasets": [{"id": "d1", "name": "dietrace-user-alice"}]})
    client = PhoenixMCPClient(_session=session)

    datasets = await client.list_datasets()

    assert [d["name"] for d in datasets] == ["dietrace-user-alice"]


async def test_get_recent_experiments_accepts_bare_list_and_caps_limit() -> None:
    """When the server returns a bare list (no ``experiments`` wrapper), it is still
    parsed and capped to ``limit`` — the same cap as the wrapped shape."""
    session = _FakeSession([{"id": "e1"}, {"id": "e2"}, {"id": "e3"}])
    client = PhoenixMCPClient(_session=session)

    experiments = await client.get_recent_experiments("ds1", limit=2)

    assert [e["id"] for e in experiments] == ["e1", "e2"]


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


async def test_get_experiment_results_accepts_bare_list() -> None:
    """A bare-list experiment payload (no ``experimentResult`` wrapper) is returned
    as-is rather than collapsing to an empty read."""
    payload = [{"example_id": "e1", "input": {}, "reference_output": {}, "output": {}}]
    client = PhoenixMCPClient(_session=_FakeSession(payload))

    results = await client.get_experiment_results("exp14")

    assert [r["example_id"] for r in results] == ["e1"]


async def test_get_experiment_results_scalar_payload_degrades_to_empty() -> None:
    """A payload that is neither a dict nor a list (a bare string) degrades to [] —
    the supervisor reads no results rather than raising (fail-soft)."""
    client = PhoenixMCPClient(_session=_FakeSession("unexpected"))

    assert await client.get_experiment_results("exp14") == []


async def test_get_spans_uses_camel_trace_id() -> None:
    session = _FakeSession({"spans": [{"name": "parse_meal"}]})
    client = PhoenixMCPClient(_session=session)

    spans = await client.get_spans("trace-9")

    assert spans[0]["name"] == "parse_meal"
    assert session.calls[0] == ("get-spans", {"traceId": "trace-9"})


async def test_get_spans_accepts_bare_list() -> None:
    """A bare-list spans payload (no ``spans`` wrapper) is returned directly."""
    session = _FakeSession([{"name": "parse_meal"}, {"name": "log_entry"}])
    client = PhoenixMCPClient(_session=session)

    spans = await client.get_spans("trace-9")

    assert [s["name"] for s in spans] == ["parse_meal", "log_entry"]


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


async def test_tool_error_result_raises_with_message() -> None:
    """An ``isError`` MCP result surfaces as a RuntimeError carrying the error text,
    rather than being silently swallowed into an empty read."""
    result = _RawResult([_FakeContent("dataset not found")], is_error=True)
    client = PhoenixMCPClient(_session=_CannedResultSession(result))

    with pytest.raises(RuntimeError, match="dataset not found"):
        await client.list_datasets()


async def test_error_result_without_text_content_still_raises() -> None:
    """An error result whose blocks carry no ``text`` still raises (empty message),
    never returns as if the call succeeded."""
    result = _RawResult([_NoTextContent()], is_error=True)
    client = PhoenixMCPClient(_session=_CannedResultSession(result))

    with pytest.raises(RuntimeError, match="MCP tool returned an error"):
        await client.get_spans("trace-1")


async def test_no_text_content_parses_to_empty_read() -> None:
    """A success result with no text block parses to None, so reads degrade to []."""
    result = _RawResult([_NoTextContent()])
    client = PhoenixMCPClient(_session=_CannedResultSession(result))

    assert await client.list_datasets() == []


async def test_unexpected_payload_shapes_degrade_to_empty() -> None:
    """When the payload is neither a list nor the expected wrapper dict, each read
    returns an empty result instead of raising — the supervisor degrades fail-soft."""
    client = PhoenixMCPClient(_session=_FakeSession({"unexpected": True}))

    assert await client.list_datasets() == []
    assert await client.get_recent_experiments("ds1") == []
    assert await client.get_experiment_results("exp1") == []
    assert await client.get_spans("trace-1") == []
    assert await client.find_dataset("missing") is None


async def test_add_dataset_examples_falls_back_to_count_on_nondict() -> None:
    """A non-dict write response falls back to a synthetic ``{"added": N}`` summary."""
    client = PhoenixMCPClient(_session=_FakeSession("ok"))
    examples = [{"input": {}, "output": {}, "metadata": {}}, {"input": {}, "output": {}}]

    assert await client.add_dataset_examples("dietrace-user-bob", examples) == {"added": 2}


async def test_session_without_injection_requires_creds(monkeypatch) -> None:
    """With no injected session and Phoenix creds absent, a read raises a clear
    RuntimeError before ever spawning the npx MCP server — callers are expected to
    gate on ``mcp_available()`` first, so reaching a read uncredentialed is a
    misconfiguration, not a silent live attempt (keeps the no-network path
    closed in tests)."""
    monkeypatch.delenv("PHOENIX_API_KEY", raising=False)
    monkeypatch.delenv("PHOENIX_BASE_URL", raising=False)
    client = PhoenixMCPClient()  # no _session injected

    with pytest.raises(RuntimeError, match="PHOENIX_API_KEY and PHOENIX_BASE_URL"):
        await client.list_datasets()


def test_mcp_available_requires_both_creds(monkeypatch) -> None:
    monkeypatch.delenv("PHOENIX_API_KEY", raising=False)
    monkeypatch.delenv("PHOENIX_BASE_URL", raising=False)
    assert mcp_available() is False
    monkeypatch.setenv("PHOENIX_API_KEY", "k")
    assert mcp_available() is False  # base url still missing
    monkeypatch.setenv("PHOENIX_BASE_URL", "https://app.phoenix.arize.com/s/ws")
    assert mcp_available() is True

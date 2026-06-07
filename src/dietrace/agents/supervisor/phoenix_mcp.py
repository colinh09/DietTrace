"""Phoenix MCP client for the supervisor agent.

Wraps the Arize Phoenix MCP server (``npx -y @arizeai/phoenix-mcp``) over the mcp
Python SDK's stdio transport. Exposes the read tools the supervisor needs to make
its decisions (experiments, spans) plus the ``add-dataset-examples`` write used to
grow a user's held-out dataset. A pre-built session can be injected for offline
tests; live calls are fail-soft — callers gate on :func:`mcp_available`.

NOTE: the live server mixes arg casing across tools (snake_case for
``list-experiments-for-dataset``/``get-experiment-by-id``, camelCase ``traceId`` for
``get-spans``). The ``add-dataset-examples`` payload here is a best-effort shape;
confirm it against the live tool schema (exposed via MCP ``list_tools``) before the
demo. The mocked tests assert the tool *name* and that examples are forwarded.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


def _get_env() -> tuple[str, str]:
    """Return (PHOENIX_API_KEY, PHOENIX_BASE_URL) from the environment."""
    return os.environ.get("PHOENIX_API_KEY", ""), os.environ.get("PHOENIX_BASE_URL", "")


def mcp_available() -> bool:
    """True when both Phoenix creds are present, so callers can degrade fail-soft."""
    api_key, base_url = _get_env()
    return bool(api_key and base_url)


def user_dataset_name(user_id: str) -> str:
    """Deterministic per-user Phoenix dataset name (design: one dataset per user)."""
    return f"dietrace-user-{user_id}"


def _parse_tool_result(result: Any) -> Any:
    """Extract and JSON-parse the text payload from a CallToolResult."""
    if result.isError:
        content_text = ""
        for item in result.content:
            if hasattr(item, "text"):
                content_text = item.text
                break
        raise RuntimeError(f"MCP tool returned an error: {content_text}")

    for item in result.content:
        if hasattr(item, "text"):
            try:
                return json.loads(item.text)
            except json.JSONDecodeError:  # pragma: no cover — MCP rarely returns non-JSON
                return item.text  # pragma: no cover

    return None


@asynccontextmanager
async def _mcp_session(api_key: str, base_url: str) -> AsyncIterator[Any]:  # pragma: no cover
    """Async context manager that yields an initialized MCP ClientSession."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@arizeai/phoenix-mcp", "--baseUrl", base_url, "--apiKey", api_key],
        env={**os.environ},
    )
    async with (
        stdio_client(server_params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


class PhoenixMCPClient:
    """Async client over the Phoenix MCP stdio transport.

    Spawns ``npx -y @arizeai/phoenix-mcp`` per call (stateless) unless a
    pre-initialized session is injected for testing.
    """

    def __init__(self, *, _session: Any | None = None) -> None:
        self._injected_session = _session

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[Any]:
        if self._injected_session is not None:
            yield self._injected_session
            return
        api_key, base_url = _get_env()
        if not api_key or not base_url:
            raise RuntimeError("PHOENIX_API_KEY and PHOENIX_BASE_URL are required")
        async with _mcp_session(api_key, base_url) as session:  # pragma: no cover — live MCP
            yield session  # pragma: no cover — live MCP

    # ---- reads ------------------------------------------------------------

    async def list_datasets(self) -> list[dict[str, Any]]:
        """Call ``list-datasets`` and return a list of dataset dicts."""
        async with self._session() as session:
            result = await session.call_tool("list-datasets", arguments={})
        parsed = _parse_tool_result(result)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "datasets" in parsed:
            return parsed["datasets"]
        return []

    async def get_recent_experiments(
        self, dataset_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Return the most recent N experiments for a dataset."""
        async with self._session() as session:
            result = await session.call_tool(
                "list-experiments-for-dataset",
                arguments={"dataset_id": dataset_id, "limit": limit},
            )
        parsed = _parse_tool_result(result)
        if isinstance(parsed, list):
            return parsed[:limit]
        if isinstance(parsed, dict) and "experiments" in parsed:
            return parsed["experiments"][:limit]
        return []

    async def get_experiment_results(self, experiment_id: str) -> list[dict[str, Any]]:
        """Return per-example results for an experiment via ``get-experiment-by-id``.

        Each result carries the example ``input``, ``reference_output`` (ground
        truth), and ``output`` (the run's logged meal).
        """
        async with self._session() as session:
            result = await session.call_tool(
                "get-experiment-by-id", arguments={"experiment_id": experiment_id}
            )
        parsed = _parse_tool_result(result)
        if isinstance(parsed, dict):
            return parsed.get("experimentResult", [])
        if isinstance(parsed, list):
            return parsed
        return []

    async def get_spans(self, trace_id: str) -> list[dict[str, Any]]:
        """Return spans for a given trace_id via ``get-spans``."""
        async with self._session() as session:
            result = await session.call_tool("get-spans", arguments={"traceId": trace_id})
        parsed = _parse_tool_result(result)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "spans" in parsed:
            return parsed["spans"]
        return []

    async def find_dataset(self, name: str) -> dict[str, Any] | None:
        """Find a dataset by exact name via ``list-datasets`` (else None)."""
        for ds in await self.list_datasets():
            if ds.get("name") == name:
                return ds
        return None

    # ---- write ------------------------------------------------------------

    async def add_dataset_examples(
        self, dataset_name: str, examples: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Append examples to a Phoenix dataset via ``add-dataset-examples`` (creates
        on first write). Each example is ``{input, output, metadata}``."""
        async with self._session() as session:
            result = await session.call_tool(
                "add-dataset-examples",
                arguments={"datasetName": dataset_name, "examples": examples},
            )
        parsed = _parse_tool_result(result)
        return parsed if isinstance(parsed, dict) else {"added": len(examples)}

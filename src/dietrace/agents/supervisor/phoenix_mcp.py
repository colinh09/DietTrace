"""Phoenix MCP client for the supervisor agent.

Wraps the Phoenix MCP server via the mcp Python SDK's StdioServerParameters,
spawning ``npx -y @arizeai/phoenix-mcp`` as a subprocess and communicating over
stdio. Exposes async methods for the tools the supervisor needs. A pre-built
session can be injected for offline tests.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


def _get_env() -> tuple[str, str]:
    """Return (PHOENIX_API_KEY, PHOENIX_BASE_URL) from the environment."""
    api_key = os.environ.get("PHOENIX_API_KEY", "")
    base_url = os.environ.get("PHOENIX_BASE_URL", "")
    return api_key, base_url


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
        args=["-y", "@arizeai/phoenix-mcp"],
        env={
            **os.environ,
            "PHOENIX_API_KEY": api_key,
            "PHOENIX_BASE_URL": base_url,
        },
    )

    async with (
        stdio_client(server_params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


class PhoenixMCPClient:
    """Async client that calls Phoenix MCP tools via the stdio transport.

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
        if not api_key:
            raise RuntimeError("PHOENIX_API_KEY is required for PhoenixMCPClient")
        if not base_url:
            raise RuntimeError("PHOENIX_BASE_URL is required for PhoenixMCPClient")
        async with _mcp_session(api_key, base_url) as session:  # pragma: no cover — live MCP
            yield session  # pragma: no cover — live MCP

    async def list_datasets(self) -> list[dict[str, Any]]:
        """Call the ``list-datasets`` MCP tool and return a list of dataset dicts."""
        async with self._session() as session:
            result = await session.call_tool("list-datasets", arguments={})
        parsed = _parse_tool_result(result)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "datasets" in parsed:
            return parsed["datasets"]
        return []

    async def get_recent_experiments(
        self,
        dataset_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return the most recent N experiments for a dataset."""
        async with self._session() as session:
            result = await session.call_tool(
                "list-experiments-for-dataset",
                arguments={"dataset_id": dataset_id, "limit": limit},
            )
        parsed = _parse_tool_result(result)

        experiments: list[dict[str, Any]] = []
        if isinstance(parsed, list):
            experiments = parsed
        elif isinstance(parsed, dict) and "experiments" in parsed:
            experiments = parsed["experiments"]

        return experiments[:limit]

    async def get_spans(self, trace_id: str) -> list[dict[str, Any]]:
        """Return spans for a given trace_id by calling ``get-spans``."""
        async with self._session() as session:
            result = await session.call_tool(
                "get-spans",
                arguments={"traceId": trace_id},
            )
        parsed = _parse_tool_result(result)

        spans: list[dict[str, Any]] = []
        if isinstance(parsed, list):
            spans = parsed
        elif isinstance(parsed, dict) and "spans" in parsed:
            spans = parsed["spans"]

        return [s for s in spans if s.get("traceId") == trace_id or "traceId" not in s]

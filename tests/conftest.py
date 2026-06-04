"""Test configuration. Guards the suite against real network calls so unattended
build sessions stay offline, deterministic, and free of API spend.
"""

import socket

import pytest

_REAL_CONNECT = socket.socket.connect


def _guard_connect(self, address):  # noqa: ANN001
    host = address[0] if isinstance(address, tuple) else address
    if host in ("127.0.0.1", "::1", "localhost"):
        return _REAL_CONNECT(self, address)
    raise RuntimeError(
        f"Real network call to {host!r} blocked in tests. Mock external APIs "
        "(Vertex/Gemini, Phoenix, USDA FDC, GitHub) instead."
    )


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Block outbound sockets to non-local hosts for every test."""
    monkeypatch.setattr(socket.socket, "connect", _guard_connect)


@pytest.fixture(autouse=True)
def _isolate_macro_memory_db(tmp_path, monkeypatch):
    """Point the default macro-memory store at a per-test temp file so a test that
    doesn't inject its own store can't write to the repo's data/ dir or leak
    preferences across tests."""
    monkeypatch.setenv("DIETRACE_MACRO_MEMORY_DB", str(tmp_path / "macro_memory.sqlite"))

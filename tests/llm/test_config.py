"""Tests for the Gemini configuration module.

The module's import-time logic decides two things that are otherwise untested:
its hard requirement on ``DIETRACE_GEMINI_PROJECT`` outside of tests, and the
mirroring of that config into Google's standard env vars so ADK's Gemini wrapper
selects the Vertex backend instead of silently defaulting to the Developer API
(see config.py's module docstring). A regression in the mirroring fails closed or
mis-routes spend, so it is worth pinning.
"""

import importlib
import subprocess
import sys

import pytest

_MODULE = "dietrace.llm.config"
_GOOGLE_VARS = (
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
)


@pytest.fixture
def reimport_config(monkeypatch):
    """Reimport config.py under a controlled environment.

    Clears the Google mirror vars (so monkeypatch restores them on teardown,
    undoing any ``setdefault`` the import performs) and restores the canonical,
    test-mode module afterward so other tests keep seeing it.
    """
    original = sys.modules.get(_MODULE)
    for var in _GOOGLE_VARS:
        monkeypatch.delenv(var, raising=False)

    def _reimport():
        sys.modules.pop(_MODULE, None)
        return importlib.import_module(_MODULE)

    yield _reimport

    sys.modules.pop(_MODULE, None)
    if original is not None:
        sys.modules[_MODULE] = original


def test_project_mirrors_vertex_env(reimport_config, monkeypatch):
    """A set project is mirrored into Google's standard Vertex env vars."""
    monkeypatch.setenv("DIETRACE_GEMINI_PROJECT", "my-gcp-project")
    config = reimport_config()

    assert config.GEMINI_PROJECT == "my-gcp-project"
    import os

    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "TRUE"
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "my-gcp-project"
    assert os.environ["GOOGLE_CLOUD_LOCATION"] == config.GEMINI_LOCATION


def test_explicit_google_env_wins_over_setdefault(reimport_config, monkeypatch):
    """An operator's explicit GOOGLE_CLOUD_PROJECT is preserved (setdefault)."""
    monkeypatch.setenv("DIETRACE_GEMINI_PROJECT", "my-gcp-project")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "operator-override")
    reimport_config()

    import os

    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "operator-override"


def test_no_project_under_pytest_does_not_raise(reimport_config, monkeypatch):
    """Under pytest, a missing project resolves to empty without raising and
    leaves the Vertex mirror untouched (no project → no spend wiring)."""
    monkeypatch.delenv("DIETRACE_GEMINI_PROJECT", raising=False)
    config = reimport_config()

    assert config.GEMINI_PROJECT == ""
    import os

    for var in _GOOGLE_VARS:
        assert var not in os.environ


def test_model_and_location_overrides(reimport_config, monkeypatch):
    """Model and location are env-overridable; default model stays on Gemini 3."""
    monkeypatch.setenv("DIETRACE_GEMINI_PROJECT", "my-gcp-project")
    monkeypatch.setenv("DIETRACE_GEMINI_MODEL", "gemini-3.1-flash-preview")
    monkeypatch.setenv("DIETRACE_GEMINI_LOCATION", "us-central1")
    config = reimport_config()

    assert config.GEMINI_MODEL == "gemini-3.1-flash-preview"
    assert config.GEMINI_LOCATION == "us-central1"


def test_no_project_outside_test_raises():
    """Outside of pytest, a missing project is a hard import-time failure.

    Exercised in a fresh subprocess (no pytest in sys.modules, no
    PYTEST_CURRENT_TEST) since the in-test guard otherwise suppresses the raise.
    Pure import — no network — so the offline guarantee holds.
    """
    import os

    env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
    env.pop("DIETRACE_GEMINI_PROJECT", None)

    result = subprocess.run(
        [sys.executable, "-c", "import dietrace.llm.config"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert "DIETRACE_GEMINI_PROJECT" in result.stderr

"""Pin the storage-backend selector ``build_stores`` (``web/stores.py``).

``build_stores`` is the single switch that decides whether the app talks to the
durable Firestore backend (deployed) or the local SQLite files (tests, local
dev). It is wired in at boot by ``app.py`` but NO test exercised it — the suite
constructs ``create_app`` with explicit stores, so a regression here (flipping
the default to Firestore, swapping an env-var name, mis-resolving the project)
would not fail a single test, yet it would either pull the cloud client into
offline tests (the project rule: no cloud spend in tests) or break the
deployed persistence layer.

These pins assert the contract directly: the DEFAULT and any non-``firestore``
value stay on SQLite (and never import the Firestore module), the env-var path
overrides are honored, and ``DIETRACE_STORE=firestore`` routes to the Firestore
stores with the project resolved from ``GOOGLE_CLOUD_PROJECT`` then
``DIETRACE_GEMINI_PROJECT``.
"""

from __future__ import annotations

import sys

import pytest

from dietrace.web.feedback import FeedbackStore
from dietrace.web.goal_store import GoalStore
from dietrace.web.store import MealLogStore
from dietrace.web.stores import build_stores
from dietrace.web.trust import TrustStore

# The env vars build_stores reads — cleared per test so the process environment
# can't leak a real backend selection into these assertions.
_STORE_ENV = (
    "DIETRACE_STORE",
    "DIETRACE_LOG_DB",
    "DIETRACE_FEEDBACK_DB",
    "DIETRACE_TRUST_DB",
    "DIETRACE_GOALS_DB",
    "GOOGLE_CLOUD_PROJECT",
    "DIETRACE_GEMINI_PROJECT",
)


@pytest.fixture(autouse=True)
def _clean_store_env(monkeypatch):
    for name in _STORE_ENV:
        monkeypatch.delenv(name, raising=False)


def _sqlite_paths(tmp_path, monkeypatch):
    """Point every SQLite path at tmp_path so nothing lands in the repo's data/."""
    monkeypatch.setenv("DIETRACE_LOG_DB", str(tmp_path / "log.sqlite"))
    monkeypatch.setenv("DIETRACE_FEEDBACK_DB", str(tmp_path / "feedback.sqlite"))
    monkeypatch.setenv("DIETRACE_TRUST_DB", str(tmp_path / "trust.sqlite"))
    monkeypatch.setenv("DIETRACE_GOALS_DB", str(tmp_path / "goals.sqlite"))


# ---------------------------------------------------------------------------
# Default / non-firestore → SQLite (and never imports the cloud module)
# ---------------------------------------------------------------------------


def test_default_backend_is_sqlite(tmp_path, monkeypatch):
    """With DIETRACE_STORE unset, build_stores returns the four SQLite stores."""
    _sqlite_paths(tmp_path, monkeypatch)
    meal, feedback, trust, goal = build_stores()
    assert isinstance(meal, MealLogStore)
    assert isinstance(feedback, FeedbackStore)
    assert isinstance(trust, TrustStore)
    assert isinstance(goal, GoalStore)


def test_unrecognized_backend_falls_through_to_sqlite(tmp_path, monkeypatch):
    """Any value that isn't ``firestore`` keeps the SQLite backend (fail-safe default)."""
    _sqlite_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("DIETRACE_STORE", "postgres")
    meal, feedback, trust, goal = build_stores()
    assert isinstance(meal, MealLogStore)
    assert isinstance(goal, GoalStore)


def test_sqlite_branch_never_imports_firestore_module(tmp_path, monkeypatch):
    """The offline default must not pull in the Firestore client module.

    Project rule: no cloud client in offline tests. The Firestore module
    is imported lazily *inside* the firestore branch, so taking the SQLite path
    must leave it absent from ``sys.modules``.
    """
    _sqlite_paths(tmp_path, monkeypatch)
    monkeypatch.delitem(sys.modules, "dietrace.web.firestore_store", raising=False)
    build_stores()
    assert "dietrace.web.firestore_store" not in sys.modules


def test_env_var_paths_are_honored(tmp_path, monkeypatch):
    """Each SQLite store opens at the path named by its env var."""
    _sqlite_paths(tmp_path, monkeypatch)
    meal, feedback, trust, goal = build_stores()
    # The stores create their backing file on construction — assert it lands at
    # the override path, proving the env var (not the data/ default) was used.
    assert (tmp_path / "log.sqlite").exists()
    assert (tmp_path / "feedback.sqlite").exists()
    assert (tmp_path / "trust.sqlite").exists()
    assert (tmp_path / "goals.sqlite").exists()


# ---------------------------------------------------------------------------
# DIETRACE_STORE=firestore → Firestore stores, project resolution
# ---------------------------------------------------------------------------


def _patch_firestore(monkeypatch):
    """Replace the four Firestore store classes with fakes capturing the project.

    build_stores imports them lazily from ``dietrace.web.firestore_store`` at call
    time, so patching the module attributes intercepts construction without ever
    building a real ``firestore.Client`` (which would need credentials / network).
    """
    import dietrace.web.firestore_store as fs

    class _Fake:
        def __init__(self, project=None):
            self.project = project

    for name in (
        "FirestoreMealStore",
        "FirestoreFeedbackStore",
        "FirestoreTrustStore",
        "FirestoreGoalStore",
    ):
        monkeypatch.setattr(fs, name, _Fake)
    return _Fake


def test_firestore_backend_routes_to_firestore_stores(monkeypatch):
    """DIETRACE_STORE=firestore (case-insensitive) builds the Firestore stores."""
    fake = _patch_firestore(monkeypatch)
    monkeypatch.setenv("DIETRACE_STORE", "Firestore")
    stores = build_stores()
    assert all(isinstance(s, fake) for s in stores)


def test_firestore_project_from_google_cloud_project(monkeypatch):
    """GOOGLE_CLOUD_PROJECT is passed through to every Firestore store."""
    _patch_firestore(monkeypatch)
    monkeypatch.setenv("DIETRACE_STORE", "firestore")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-a")
    meal, feedback, trust, goal = build_stores()
    assert meal.project == "proj-a"
    assert goal.project == "proj-a"


def test_firestore_project_falls_back_to_gemini_project(monkeypatch):
    """When GOOGLE_CLOUD_PROJECT is absent, DIETRACE_GEMINI_PROJECT is used."""
    _patch_firestore(monkeypatch)
    monkeypatch.setenv("DIETRACE_STORE", "firestore")
    monkeypatch.setenv("DIETRACE_GEMINI_PROJECT", "proj-b")
    meal, *_ = build_stores()
    assert meal.project == "proj-b"


def test_firestore_project_none_when_unset(monkeypatch):
    """With neither project env var set, the project resolves to None."""
    _patch_firestore(monkeypatch)
    monkeypatch.setenv("DIETRACE_STORE", "firestore")
    meal, *_ = build_stores()
    assert meal.project is None

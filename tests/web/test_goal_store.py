"""GoalStore and FirestoreGoalStore — per-user macro target persistence.

Stores ONLY the computed targets (+rationale/source), never the MacroProfile.
Tests: save→get round-trip, per-user isolation, empty→None, and structural
verification that no profile fields can be stored.
"""

from __future__ import annotations

import inspect
from typing import Any

from dietrace.web.goal_store import GoalStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TARGETS: dict[str, float] = {
    "208": 2200.0,
    "203": 165.0,
    "205": 220.0,
    "204": 73.0,
}

# Fields on MacroProfile — none of these should appear in the save signature.
_PROFILE_FIELDS = {
    "age", "sex", "height_cm", "weight_kg", "activity", "goal", "preference", "ai_help"
}


# ---------------------------------------------------------------------------
# GoalStore (SQLite backend)
# ---------------------------------------------------------------------------


def test_get_returns_none_when_empty(tmp_path) -> None:
    store = GoalStore(tmp_path / "goals.sqlite")
    assert store.get("alice") is None


def test_save_and_get_round_trip(tmp_path) -> None:
    store = GoalStore(tmp_path / "goals.sqlite")
    store.save("alice", _TARGETS, rationale="formula plan", source="formula")
    result = store.get("alice")
    assert result == _TARGETS


def test_save_overwrites_previous(tmp_path) -> None:
    store = GoalStore(tmp_path / "goals.sqlite")
    store.save("alice", _TARGETS)
    new_targets = {"208": 2000.0, "203": 150.0, "205": 200.0, "204": 67.0}
    store.save("alice", new_targets)
    assert store.get("alice") == new_targets


def test_per_user_isolation(tmp_path) -> None:
    store = GoalStore(tmp_path / "goals.sqlite")
    alice_targets = {"208": 1800.0, "203": 140.0, "205": 180.0, "204": 60.0}
    bob_targets = {"208": 2600.0, "203": 195.0, "205": 260.0, "204": 87.0}

    store.save("alice", alice_targets)
    store.save("bob", bob_targets)

    assert store.get("alice") == alice_targets
    assert store.get("bob") == bob_targets
    # A third user sees nothing
    assert store.get("carol") is None


def test_get_returns_only_targets_no_profile_fields(tmp_path) -> None:
    store = GoalStore(tmp_path / "goals.sqlite")
    store.save("alice", _TARGETS, rationale="mifflin", source="formula")
    result = store.get("alice")
    assert result is not None
    # Only USDA-coded target keys — no profile fields may be returned.
    assert not set(result.keys()) & _PROFILE_FIELDS


def test_save_signature_has_no_profile_fields() -> None:
    sig = inspect.signature(GoalStore.save)
    params = set(sig.parameters.keys())
    assert params.isdisjoint(_PROFILE_FIELDS), (
        f"GoalStore.save must not accept profile fields; found: {params & _PROFILE_FIELDS}"
    )


def test_store_persists_across_instances(tmp_path) -> None:
    path = tmp_path / "goals.sqlite"
    GoalStore(path).save("alice", _TARGETS)
    assert GoalStore(path).get("alice") == _TARGETS


def test_optional_rationale_and_source(tmp_path) -> None:
    store = GoalStore(tmp_path / "goals.sqlite")
    # saving without rationale/source must not raise
    store.save("alice", _TARGETS)
    assert store.get("alice") == _TARGETS


# ---------------------------------------------------------------------------
# FirestoreGoalStore (mocked Firestore backend)
# ---------------------------------------------------------------------------


class _MockSnapshot:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class _MockDocument:
    def __init__(self, store: dict[str, Any], doc_id: str) -> None:
        self._store = store
        self._id = doc_id

    def get(self) -> _MockSnapshot:
        return _MockSnapshot(self._store.get(self._id))

    def set(self, data: dict[str, Any]) -> None:
        self._store[self._id] = dict(data)


class _MockCollection:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def document(self, doc_id: str) -> _MockDocument:
        return _MockDocument(self._store, doc_id)


class _MockFirestore:
    def __init__(self) -> None:
        self._collections: dict[str, _MockCollection] = {}

    def collection(self, name: str) -> _MockCollection:
        if name not in self._collections:
            self._collections[name] = _MockCollection()
        return self._collections[name]


def _make_firestore_store() -> Any:
    from dietrace.web.firestore_store import FirestoreGoalStore

    store = FirestoreGoalStore.__new__(FirestoreGoalStore)
    store._db = _MockFirestore()
    return store


def test_firestore_get_returns_none_when_empty() -> None:
    store = _make_firestore_store()
    assert store.get("alice") is None


def test_firestore_save_and_get_round_trip() -> None:
    store = _make_firestore_store()
    store.save("alice", _TARGETS, rationale="formula plan", source="formula")
    result = store.get("alice")
    assert result == _TARGETS


def test_firestore_per_user_isolation() -> None:
    store = _make_firestore_store()
    alice_targets = {"208": 1800.0, "203": 140.0, "205": 180.0, "204": 60.0}
    bob_targets = {"208": 2600.0, "203": 195.0, "205": 260.0, "204": 87.0}

    store.save("alice", alice_targets)
    store.save("bob", bob_targets)

    assert store.get("alice") == alice_targets
    assert store.get("bob") == bob_targets
    assert store.get("carol") is None


def test_firestore_get_returns_only_targets_no_profile_fields() -> None:
    from dietrace.web.firestore_store import FirestoreGoalStore

    sig = inspect.signature(FirestoreGoalStore.save)
    params = set(sig.parameters.keys())
    assert params.isdisjoint(_PROFILE_FIELDS), (
        f"FirestoreGoalStore.save must not accept profile fields; found: {params & _PROFILE_FIELDS}"
    )


# ---------------------------------------------------------------------------
# build_stores() wiring
# ---------------------------------------------------------------------------


def test_build_stores_returns_goal_store(tmp_path, monkeypatch) -> None:
    """build_stores() must include a GoalStore as the fourth element."""
    monkeypatch.setenv("DIETRACE_LOG_DB", str(tmp_path / "log.sqlite"))
    monkeypatch.setenv("DIETRACE_FEEDBACK_DB", str(tmp_path / "feedback.sqlite"))
    monkeypatch.setenv("DIETRACE_TRUST_DB", str(tmp_path / "trust.sqlite"))
    monkeypatch.setenv("DIETRACE_GOALS_DB", str(tmp_path / "goals.sqlite"))
    monkeypatch.delenv("DIETRACE_STORE", raising=False)

    from dietrace.web.stores import build_stores

    stores = build_stores()
    assert len(stores) == 4
    from dietrace.web.goal_store import GoalStore
    assert isinstance(stores[3], GoalStore)


# ---------------------------------------------------------------------------
# create_app wiring
# ---------------------------------------------------------------------------


def test_create_app_accepts_goal_store_param(tmp_path) -> None:
    """create_app must accept a goal_store param without raising."""
    from dietrace.web.app import create_app
    from dietrace.web.feedback import FeedbackStore
    from dietrace.web.memory import SqliteMemory
    from dietrace.web.store import MealLogStore
    from dietrace.web.trust import TrustStore

    goal_store = GoalStore(tmp_path / "goals.sqlite")
    app = create_app(
        meal_logger=lambda text, examples=None: {"totals": [], "per_item": []},
        store=MealLogStore(tmp_path / "log.sqlite"),
        feedback_store=FeedbackStore(tmp_path / "feedback.sqlite"),
        trust_store=TrustStore(tmp_path / "trust.sqlite"),
        goal_store=goal_store,
        memory=SqliteMemory(tmp_path / "memory.sqlite"),
        feedback_pusher=lambda *a: False,
        tracer_init=lambda name: None,
    )
    assert app is not None

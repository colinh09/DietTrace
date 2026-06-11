"""Direct unit tests for SqliteStandingRuleStore (standing_rules.py).

The store's core contract is exercised only via HTTP integration tests today
(test_freeform_feedback.py); none of the critical invariants below are directly
pinned.  A change from INSERT OR REPLACE to INSERT, a broken ORDER BY, or a
per-user isolation bug would not be caught by any existing test.

Tests here isolate just the store layer — no FastAPI, no Gemini, no Phoenix.
"""

from __future__ import annotations

import pytest

from dietrace.web.standing_rules import SqliteStandingRuleStore, StandingRule


def _rule(scope: str = "this_food", target: str = "fries", adj: float | None = 0.5) -> StandingRule:
    return StandingRule(scope=scope, target_food=target, adjustment=adj, rationale="test")


# ---------------------------------------------------------------------------
# zero state
# ---------------------------------------------------------------------------


def test_count_zero_on_empty_store(tmp_path) -> None:
    """A fresh store has no rules."""
    store = SqliteStandingRuleStore(tmp_path / "rules.sqlite")
    assert store.count("alice") == 0


def test_recall_returns_none_when_rule_not_found(tmp_path) -> None:
    """recall() returns None when the (scope, target_food) key has not been stored."""
    store = SqliteStandingRuleStore(tmp_path / "rules.sqlite")
    assert store.recall("alice", "this_food", "fries") is None


def test_recent_returns_empty_list_for_fresh_user(tmp_path) -> None:
    """recent() returns [] when the user has no rules stored."""
    store = SqliteStandingRuleStore(tmp_path / "rules.sqlite")
    assert store.recent("alice") == []


# ---------------------------------------------------------------------------
# round-trip
# ---------------------------------------------------------------------------


def test_remember_and_recall_round_trip(tmp_path) -> None:
    """remember() stores a rule; recall() retrieves it by (scope, target_food)."""
    store = SqliteStandingRuleStore(tmp_path / "rules.sqlite")
    store.remember("alice", StandingRule(scope="meal_type", target_food="preworkout",
                                         adjustment=80.0, rationale="80g carbs"))
    rule = store.recall("alice", "meal_type", "preworkout")
    assert rule is not None
    assert rule.scope == "meal_type"
    assert rule.target_food == "preworkout"
    assert rule.adjustment == pytest.approx(80.0)
    assert rule.rationale == "80g carbs"
    assert store.count("alice") == 1


# ---------------------------------------------------------------------------
# upsert: same (scope, target_food) replaces, count stays at 1
# ---------------------------------------------------------------------------


def test_upsert_replaces_on_same_scope_and_target_food(tmp_path) -> None:
    """Storing a rule twice with the same (scope, target_food) keeps count at 1
    and the latest value wins — the UNIQUE constraint + INSERT OR REPLACE.

    If INSERT OR REPLACE were replaced by INSERT, count would become 2 and recall
    would return whichever the DB picks — this test pins the upsert invariant.
    """
    store = SqliteStandingRuleStore(tmp_path / "rules.sqlite")
    store.remember("alice", StandingRule(scope="this_food", target_food="fries",
                                         adjustment=0.5, rationale="half"))
    store.remember("alice", StandingRule(scope="this_food", target_food="fries",
                                         adjustment=0.25, rationale="quarter"))
    assert store.count("alice") == 1
    rule = store.recall("alice", "this_food", "fries")
    assert rule is not None
    assert rule.adjustment == pytest.approx(0.25)  # latest wins
    assert rule.rationale == "quarter"


def test_different_target_food_creates_separate_rule(tmp_path) -> None:
    """Two rules with the same scope but different target_food are separate entries."""
    store = SqliteStandingRuleStore(tmp_path / "rules.sqlite")
    store.remember("alice", StandingRule(scope="this_food", target_food="fries",
                                         adjustment=0.5, rationale=""))
    store.remember("alice", StandingRule(scope="this_food", target_food="burger",
                                         adjustment=0.75, rationale=""))
    assert store.count("alice") == 2
    assert store.recall("alice", "this_food", "fries") is not None
    assert store.recall("alice", "this_food", "burger") is not None


# ---------------------------------------------------------------------------
# per-user isolation
# ---------------------------------------------------------------------------


def test_per_user_isolation(tmp_path) -> None:
    """Rules stored for one user are not visible to another."""
    store = SqliteStandingRuleStore(tmp_path / "rules.sqlite")
    store.remember("alice", _rule())
    assert store.count("alice") == 1
    assert store.count("bob") == 0
    assert store.recall("bob", "this_food", "fries") is None


# ---------------------------------------------------------------------------
# recent ordering
# ---------------------------------------------------------------------------


def test_recent_returns_newest_first(tmp_path) -> None:
    """recent() returns standing rules in newest-first (descending created_at) order."""
    store = SqliteStandingRuleStore(tmp_path / "rules.sqlite")
    store.remember("alice", StandingRule(scope="meal_type", target_food="lunch",
                                         adjustment=None, rationale="first"))
    store.remember("alice", StandingRule(scope="meal_type", target_food="dinner",
                                         adjustment=None, rationale="second"))
    rows = store.recent("alice")
    assert len(rows) == 2
    # The most recently stored rule is listed first.
    assert rows[0]["target_food"] == "dinner"
    assert rows[1]["target_food"] == "lunch"


def test_recent_respects_limit(tmp_path) -> None:
    """recent() returns at most ``limit`` entries."""
    store = SqliteStandingRuleStore(tmp_path / "rules.sqlite")
    for i in range(5):
        store.remember("alice", StandingRule(scope="this_food", target_food=f"food{i}",
                                              adjustment=float(i), rationale=""))
    rows = store.recent("alice", limit=3)
    assert len(rows) == 3

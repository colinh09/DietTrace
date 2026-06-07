"""Tests for the learning-loop stores.

ConfirmationStore (Input A), FeedbackLog (Input B), PreferenceStore (the block):
CRUD, per-user isolation, emphasis/edit, version bumping, and clear_user.
"""

from __future__ import annotations

from dietrace.web.preference_stores import (
    ConfirmationStore,
    FeedbackLog,
    PreferenceStore,
)

_TOTALS = [{"code": "208", "name": "Energy", "amount": 300.0, "unit": "kcal"}]
_ITEMS = [{"description": "oats", "grams": 80.0, "nutrients": _TOTALS}]


# ── ConfirmationStore ──────────────────────────────────────────────────────────


def test_confirmation_add_list_count(tmp_path) -> None:
    store = ConfirmationStore(tmp_path / "c.sqlite")
    cid = store.add("u1", "oatmeal", _ITEMS, _TOTALS)
    assert isinstance(cid, int)
    rows = store.list("u1")
    assert len(rows) == 1
    assert rows[0]["meal_text"] == "oatmeal"
    assert rows[0]["totals"] == _TOTALS
    assert store.count("u1") == 1


def test_confirmation_is_per_user_and_deletable(tmp_path) -> None:
    store = ConfirmationStore(tmp_path / "c.sqlite")
    a = store.add("u1", "a", _ITEMS, _TOTALS)
    store.add("u2", "b", _ITEMS, _TOTALS)
    assert store.count("u1") == 1 and store.count("u2") == 1
    assert store.delete(a, "u1") is True
    assert store.count("u1") == 0
    assert store.count("u2") == 1  # untouched
    assert store.clear_user("u2") == 1
    assert store.count("u2") == 0


# ── FeedbackLog ────────────────────────────────────────────────────────────────


def test_feedback_add_get_list(tmp_path) -> None:
    log = FeedbackLog(tmp_path / "f.sqlite")
    fid = log.add("u1", "less peanut butter", {"kind": "portion_adjust"}, "pb on apple")
    row = log.get(fid, "u1")
    assert row is not None
    assert row["feedback_text"] == "less peanut butter"
    assert row["structured"] == {"kind": "portion_adjust"}
    assert row["weight"] == 1.0
    assert log.count("u1") == 1


def test_feedback_edit_and_emphasize(tmp_path) -> None:
    log = FeedbackLog(tmp_path / "f.sqlite")
    fid = log.add("u1", "original", None, None)
    assert log.update(fid, "u1", feedback_text="edited", weight=3.0) is True
    row = log.get(fid, "u1")
    assert row["feedback_text"] == "edited"
    assert row["weight"] == 3.0
    # No-op update returns False.
    assert log.update(fid, "u1") is False


def test_feedback_delete_and_isolation(tmp_path) -> None:
    log = FeedbackLog(tmp_path / "f.sqlite")
    fid = log.add("u1", "x")
    log.add("u2", "y")
    assert log.delete(fid, "u1") is True
    assert log.count("u1") == 0
    assert log.count("u2") == 1
    # Can't delete another user's row.
    other = log.list("u2")[0]["id"]
    assert log.delete(other, "u1") is False
    assert log.count("u2") == 1


# ── PreferenceStore ────────────────────────────────────────────────────────────


def test_preference_save_bumps_version(tmp_path) -> None:
    store = PreferenceStore(tmp_path / "p.sqlite")
    assert store.get("u1") is None
    assert store.block_text("u1") == ""  # empty until set

    v1 = store.save("u1", "preworkout carbs run high", [{"rule": "carbs", "from": [1]}])
    assert v1 == 1
    cur = store.get("u1")
    assert cur["block_text"] == "preworkout carbs run high"
    assert cur["version"] == 1
    assert cur["provenance"] == [{"rule": "carbs", "from": [1]}]

    v2 = store.save("u1", "updated block", None)
    assert v2 == 2
    assert store.get("u1")["version"] == 2
    assert store.block_text("u1") == "updated block"


def test_preference_is_per_user_and_clearable(tmp_path) -> None:
    store = PreferenceStore(tmp_path / "p.sqlite")
    store.save("u1", "a")
    store.save("u2", "b")
    assert store.block_text("u1") == "a"
    assert store.clear_user("u1") == 1
    assert store.get("u1") is None
    assert store.block_text("u2") == "b"  # untouched

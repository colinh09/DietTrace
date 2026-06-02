"""TrustStore persists each log's eval result and rolls it up.

Each logged meal's online-eval result (confidence, needs_review, resolution
sources) is appended per user; ``stats`` rolls them into the trust dashboard's
numbers. Offline SQLite backend; the Firestore one mirrors the interface.
"""

from __future__ import annotations

from dietrace.web.trust import TrustStore


def test_record_returns_id_and_stats_roll_up(tmp_path) -> None:
    store = TrustStore(tmp_path / "trust.sqlite")

    row_id = store.record(confidence=0.9, needs_review=False, sources=["usda"])
    assert isinstance(row_id, int)
    store.record(confidence=0.5, needs_review=True, sources=["web", "usda"])

    stats = store.stats()
    assert stats["count"] == 2
    assert stats["mean_confidence"] == 0.7  # (0.9 + 0.5) / 2
    assert stats["needs_review_pct"] == 0.5  # 1 of 2 flagged
    assert stats["source_breakdown"] == {"usda": 2, "web": 1}


def test_stats_are_zeroed_when_empty(tmp_path) -> None:
    stats = TrustStore(tmp_path / "trust.sqlite").stats()

    assert stats == {
        "count": 0,
        "mean_confidence": 0.0,
        "needs_review_pct": 0.0,
        "source_breakdown": {},
        "recent_low_confidence": [],
    }


def test_recent_low_confidence_lists_flagged_logs_newest_first(tmp_path) -> None:
    # The /trust dashboard shows the user's recent low-confidence logs (12.5):
    # only the needs_review ones, most-recent first, carrying the meal text + reason.
    store = TrustStore(tmp_path / "trust.sqlite")
    store.record(
        confidence=0.9, needs_review=False, sources=["usda"], text="a chicken breast"
    )
    store.record(
        confidence=0.4,
        needs_review=True,
        sources=["web"],
        text="a mystery dish",
        review_reason="couldn't resolve the portion",
    )
    store.record(
        confidence=0.3,
        needs_review=True,
        sources=["web"],
        text="some goop",
        review_reason="energy doesn't reconcile",
    )

    recent = store.stats()["recent_low_confidence"]

    assert [r["text"] for r in recent] == ["some goop", "a mystery dish"]
    assert recent[0]["confidence"] == 0.3
    assert recent[0]["review_reason"] == "energy doesn't reconcile"
    assert all("created_at" in r for r in recent)


def test_recent_low_confidence_is_capped_and_per_user(tmp_path) -> None:
    store = TrustStore(tmp_path / "trust.sqlite")
    for i in range(7):
        store.record(
            confidence=0.2,
            needs_review=True,
            sources=["web"],
            text=f"meal {i}",
            review_reason="low",
            user_id="alice",
        )
    store.record(
        confidence=0.1, needs_review=True, sources=["web"], text="bob's", user_id="bob"
    )

    alice = store.stats(user_id="alice")["recent_low_confidence"]
    bob = store.stats(user_id="bob")["recent_low_confidence"]

    assert len(alice) == 5  # capped
    assert alice[0]["text"] == "meal 6"  # newest first
    assert [r["text"] for r in bob] == ["bob's"]  # never leaks across users


def test_records_are_scoped_per_user(tmp_path) -> None:
    store = TrustStore(tmp_path / "trust.sqlite")
    store.record(confidence=0.9, needs_review=False, sources=["usda"], user_id="alice")
    store.record(confidence=0.3, needs_review=True, sources=["web"], user_id="bob")
    store.record(confidence=0.7, needs_review=False, sources=["usda"], user_id="bob")

    alice = store.stats(user_id="alice")
    bob = store.stats(user_id="bob")

    assert alice["count"] == 1
    assert alice["source_breakdown"] == {"usda": 1}
    assert bob["count"] == 2
    assert bob["source_breakdown"] == {"web": 1, "usda": 1}
    assert bob["needs_review_pct"] == 0.5


def test_store_persists_across_instances(tmp_path) -> None:
    path = tmp_path / "trust.sqlite"
    TrustStore(path).record(confidence=0.8, needs_review=False, sources=["usda"])

    assert TrustStore(path).stats()["count"] == 1

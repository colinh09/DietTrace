"""Firestore-backed meal + feedback stores for the deployed app.

Cloud Run's filesystem is ephemeral, so the SQLite stores lose a user's history on
every cold start. These back the same interface with Firestore so each user's
meals and corrections persist — the durable home for the per-user memory layer.
Selected at boot by ``DIETRACE_STORE=firestore``; tests and local dev keep the
SQLite backend, so the Firestore client is imported lazily and never touched
offline.

Meal ids are epoch-microsecond integers (kept under 2^53 so they survive as JS
numbers on the client) — the document id is that integer as a string.
"""

from __future__ import annotations

import datetime
import time
from collections import Counter
from typing import Any

from dietrace.web.feedback import Correction
from dietrace.web.identity import DEMO_USER

_MEALS = "meals"
_CORRECTIONS = "corrections"
_TRUST = "trust_logs"

# The per-meal breakdown fields persisted with a meal so /history can rebuild the
# per-item table + trace + quality eval (the breakdown survives navigation).
_MEAL_DETAIL_KEYS = ("per_item", "trace", "confidence", "reasons", "needs_review", "review_reason")

# How many recent flagged logs the /trust dashboard shows.
_RECENT_LIMIT = 5


def _client(project: str | None) -> Any:
    """Build a Firestore client (lazy import keeps the dep out of offline tests)."""
    from google.cloud import firestore

    return firestore.Client(project=project) if project else firestore.Client()


def _filter(field: str, value: Any) -> Any:
    from google.cloud.firestore_v1.base_query import FieldFilter

    return FieldFilter(field, "==", value)


class FirestoreMealStore:
    """Per-user logged-meal store on Firestore (interface mirrors MealLogStore)."""

    def __init__(self, project: str | None = None) -> None:
        self._db = _client(project)

    def add(
        self,
        text: str,
        totals: list[dict[str, Any]],
        created_at: datetime.datetime | None = None,
        date: str | None = None,
        user_id: str = DEMO_USER,
        detail: dict[str, Any] | None = None,
    ) -> int:
        when = created_at or datetime.datetime.now(tz=datetime.UTC)
        day = date or when.date().isoformat()
        meal_id = int(time.time() * 1_000_000)
        doc = {
            "id": meal_id,
            "user_id": user_id,
            "created_at": when.isoformat(),
            "date": day,
            "text": text,
            "totals": totals,
        }
        if detail:
            doc["detail"] = detail
        self._db.collection(_MEALS).document(str(meal_id)).set(doc)
        return meal_id

    def delete(self, meal_id: int, user_id: str = DEMO_USER) -> bool:
        ref = self._db.collection(_MEALS).document(str(meal_id))
        snap = ref.get()
        if not snap.exists or snap.to_dict().get("user_id") != user_id:
            return False
        ref.delete()
        return True

    def list(
        self, limit: int = 50, date: str | None = None, user_id: str = DEMO_USER
    ) -> list[dict[str, Any]]:
        query = self._db.collection(_MEALS).where(filter=_filter("user_id", user_id))
        meals = [doc.to_dict() for doc in query.stream()]
        if date is not None:
            meals = [m for m in meals if m.get("date") == date]
        meals.sort(key=lambda m: m.get("id", 0), reverse=True)
        out = []
        for m in meals[:limit]:
            meal = {
                "id": m["id"],
                "created_at": m["created_at"],
                "date": m["date"],
                "text": m["text"],
                "totals": m["totals"],
            }
            detail = m.get("detail")
            if detail:
                meal.update(
                    {k: detail[k] for k in _MEAL_DETAIL_KEYS if k in detail}
                )
            out.append(meal)
        return out


class FirestoreFeedbackStore:
    """Per-user correction store on Firestore (interface mirrors FeedbackStore)."""

    def __init__(self, project: str | None = None) -> None:
        self._db = _client(project)

    def add(
        self, correction: Correction, expected: dict[str, Any], user_id: str = DEMO_USER
    ) -> int:
        when = int(time.time() * 1_000_000)
        self._db.collection(_CORRECTIONS).document(str(when)).set(
            {
                "id": when,
                "user_id": user_id,
                "created_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
                "food": correction.food,
                "original_grams": correction.original_grams,
                "corrected_grams": correction.corrected_grams,
                "expected": expected,
            }
        )
        return when

    def count(self, user_id: str = DEMO_USER) -> int:
        query = self._db.collection(_CORRECTIONS).where(filter=_filter("user_id", user_id))
        return sum(1 for _ in query.stream())

    def recent(
        self, user_id: str = DEMO_USER, limit: int = 10
    ) -> list[dict[str, Any]]:
        query = self._db.collection(_CORRECTIONS).where(filter=_filter("user_id", user_id))
        rows = sorted(
            (doc.to_dict() for doc in query.stream()),
            key=lambda r: r.get("id", 0),
            reverse=True,
        )[:limit]
        return [
            {
                "food": r.get("food", ""),
                "original_grams": r.get("original_grams", 0.0),
                "corrected_grams": r.get("corrected_grams", 0.0),
                "created_at": r.get("created_at", ""),
            }
            for r in rows
        ]


class FirestoreTrustStore:
    """Per-user online-eval result store on Firestore (mirrors TrustStore)."""

    def __init__(self, project: str | None = None) -> None:
        self._db = _client(project)

    def record(
        self,
        confidence: float,
        needs_review: bool,
        sources: list[str],
        user_id: str = DEMO_USER,
        created_at: datetime.datetime | None = None,
        text: str = "",
        review_reason: str | None = None,
    ) -> int:
        when = created_at or datetime.datetime.now(tz=datetime.UTC)
        row_id = int(time.time() * 1_000_000)
        self._db.collection(_TRUST).document(str(row_id)).set(
            {
                "id": row_id,
                "user_id": user_id,
                "created_at": when.isoformat(),
                "confidence": float(confidence),
                "needs_review": bool(needs_review),
                "sources": list(sources),
                "text": text,
                "review_reason": review_reason,
            }
        )
        return row_id

    def stats(self, user_id: str = DEMO_USER) -> dict[str, Any]:
        query = self._db.collection(_TRUST).where(filter=_filter("user_id", user_id))
        rows = [doc.to_dict() for doc in query.stream()]
        count = len(rows)
        if count == 0:
            return {
                "count": 0,
                "mean_confidence": 0.0,
                "needs_review_pct": 0.0,
                "source_breakdown": {},
                "recent_low_confidence": [],
            }
        mean_confidence = sum(float(r.get("confidence", 0.0)) for r in rows) / count
        flagged = sum(1 for r in rows if r.get("needs_review"))
        breakdown: Counter[str] = Counter()
        for r in rows:
            breakdown.update(r.get("sources", []))
        recent = sorted(
            (r for r in rows if r.get("needs_review")),
            key=lambda r: r.get("id", 0),
            reverse=True,
        )[:_RECENT_LIMIT]
        return {
            "count": count,
            "mean_confidence": round(mean_confidence, 3),
            "needs_review_pct": round(flagged / count, 3),
            "source_breakdown": dict(breakdown),
            "recent_low_confidence": [
                {
                    "text": r.get("text", ""),
                    "confidence": r.get("confidence", 0.0),
                    "review_reason": r.get("review_reason"),
                    "created_at": r.get("created_at", ""),
                }
                for r in recent
            ],
        }

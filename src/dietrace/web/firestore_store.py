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
from typing import Any

from dietrace.web.feedback import Correction
from dietrace.web.identity import DEMO_USER

_MEALS = "meals"
_CORRECTIONS = "corrections"


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
    ) -> int:
        when = created_at or datetime.datetime.now(tz=datetime.UTC)
        day = date or when.date().isoformat()
        meal_id = int(time.time() * 1_000_000)
        self._db.collection(_MEALS).document(str(meal_id)).set(
            {
                "id": meal_id,
                "user_id": user_id,
                "created_at": when.isoformat(),
                "date": day,
                "text": text,
                "totals": totals,
            }
        )
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
        return [
            {
                "id": m["id"],
                "created_at": m["created_at"],
                "date": m["date"],
                "text": m["text"],
                "totals": m["totals"],
            }
            for m in meals[:limit]
        ]


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

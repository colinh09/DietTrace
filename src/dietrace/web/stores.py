"""Pick the storage backend for meals + corrections + trust.

``DIETRACE_STORE=firestore`` uses the durable Firestore backend (the deployed app,
so per-user history survives cold starts); anything else uses the local SQLite
files (tests, local dev). Returned as a triple the API wires into ``create_app``.
"""

from __future__ import annotations

import os
from typing import Any


def build_stores() -> tuple[Any, Any, Any, Any]:
    """Return ``(meal_store, feedback_store, trust_store, goal_store)`` for the backend."""
    if os.environ.get("DIETRACE_STORE", "sqlite").lower() == "firestore":
        from dietrace.web.firestore_store import (
            FirestoreFeedbackStore,
            FirestoreGoalStore,
            FirestoreMealStore,
            FirestoreTrustStore,
        )

        project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
            "DIETRACE_GEMINI_PROJECT"
        )
        return (
            FirestoreMealStore(project),
            FirestoreFeedbackStore(project),
            FirestoreTrustStore(project),
            FirestoreGoalStore(project),
        )

    from dietrace.web.feedback import FeedbackStore
    from dietrace.web.goal_store import GoalStore
    from dietrace.web.store import MealLogStore
    from dietrace.web.trust import TrustStore

    return (
        MealLogStore(os.environ.get("DIETRACE_LOG_DB", "data/log.sqlite")),
        FeedbackStore(os.environ.get("DIETRACE_FEEDBACK_DB", "data/feedback.sqlite")),
        TrustStore(os.environ.get("DIETRACE_TRUST_DB", "data/trust.sqlite")),
        GoalStore(os.environ.get("DIETRACE_GOALS_DB", "data/goals.sqlite")),
    )

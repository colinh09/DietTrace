"""Pick the storage backend for meals + corrections.

``DIETRACE_STORE=firestore`` uses the durable Firestore backend (the deployed app,
so per-user history survives cold starts); anything else uses the local SQLite
files (tests, local dev). Returned as a pair the API wires into ``create_app``.
"""

from __future__ import annotations

import os
from typing import Any


def build_stores() -> tuple[Any, Any]:
    """Return ``(meal_store, feedback_store)`` for the configured backend."""
    if os.environ.get("DIETRACE_STORE", "sqlite").lower() == "firestore":
        from dietrace.web.firestore_store import (
            FirestoreFeedbackStore,
            FirestoreMealStore,
        )

        project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
            "DIETRACE_GEMINI_PROJECT"
        )
        return FirestoreMealStore(project), FirestoreFeedbackStore(project)

    from dietrace.web.feedback import FeedbackStore
    from dietrace.web.store import MealLogStore

    return (
        MealLogStore(os.environ.get("DIETRACE_LOG_DB", "data/log.sqlite")),
        FeedbackStore(os.environ.get("DIETRACE_FEEDBACK_DB", "data/feedback.sqlite")),
    )

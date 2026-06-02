"""SQLite store for each log's online-eval result, per user.

The online eval (``evals/online.py``) scores every meal as it is logged — a
confidence, whether it ``needs_review``, and the resolution source of each item.
This persists those results so ``GET /trust`` can show a user how trustworthy
their logging has been over time: how many meals, the mean confidence, what
fraction got flagged for review, and a breakdown of where the numbers came from
(USDA vs a web-grounded lookup). One row per logged meal, scoped to a user (the
per-user memory layer, /§7). This is the local/dev backend; the deployed
app uses the Firestore backend behind the same interface.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from dietrace.web.identity import DEMO_USER

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trust_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL DEFAULT 'demo',
    created_at    TEXT NOT NULL,
    confidence    REAL NOT NULL,
    needs_review  INTEGER NOT NULL,
    sources_json  TEXT NOT NULL,
    text          TEXT NOT NULL DEFAULT '',
    review_reason TEXT
)
"""

# How many recent flagged logs the /trust dashboard shows.
_RECENT_LIMIT = 5


class TrustStore:
    """Append-and-aggregate store for per-log eval results at *db_path*, by user."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        parent = Path(self._db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

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
        """Persist one logged meal's eval result for *user_id*; return its row id.

        *text* and *review_reason* are kept so the dashboard can list a user's
        recent low-confidence meals with enough context to revisit them (12.5).
        """
        when = created_at or datetime.datetime.now(tz=datetime.UTC)
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO trust_logs "
                "(user_id, created_at, confidence, needs_review, sources_json, "
                "text, review_reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    when.isoformat(),
                    float(confidence),
                    1 if needs_review else 0,
                    json.dumps(list(sources)),
                    text,
                    review_reason,
                ),
            )
            return int(cursor.lastrowid or 0)

    def stats(self, user_id: str = DEMO_USER) -> dict[str, Any]:
        """Rolling trust stats for *user_id* (the ``GET /trust`` payload).

        Returns ``count``, ``mean_confidence``, ``needs_review_pct`` (a fraction in
        [0,1], matching the codebase's normalized scores), ``source_breakdown``
        (``source -> number of items resolved from it`` across all the user's logs),
        and ``recent_low_confidence`` (the user's most recent flagged meals,
        newest first, capped — the dashboard's "revisit these" list, 12.5).
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT confidence, needs_review, sources_json "
                "FROM trust_logs WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            flagged_rows = conn.execute(
                "SELECT created_at, confidence, text, review_reason "
                "FROM trust_logs WHERE user_id = ? AND needs_review = 1 "
                "ORDER BY id DESC LIMIT ?",
                (user_id, _RECENT_LIMIT),
            ).fetchall()
        count = len(rows)
        if count == 0:
            return {
                "count": 0,
                "mean_confidence": 0.0,
                "needs_review_pct": 0.0,
                "source_breakdown": {},
                "recent_low_confidence": [],
            }
        mean_confidence = sum(row["confidence"] for row in rows) / count
        flagged = sum(1 for row in rows if row["needs_review"])
        breakdown: Counter[str] = Counter()
        for row in rows:
            breakdown.update(json.loads(row["sources_json"]))
        return {
            "count": count,
            "mean_confidence": round(mean_confidence, 3),
            "needs_review_pct": round(flagged / count, 3),
            "source_breakdown": dict(breakdown),
            "recent_low_confidence": [
                {
                    "text": row["text"],
                    "confidence": row["confidence"],
                    "review_reason": row["review_reason"],
                    "created_at": row["created_at"],
                }
                for row in flagged_rows
            ],
        }

"""Per-user standing rules — persistent preferences from free-form feedback (14.12).

When a user says "from now on aim for 80 g carbs before my workout", the
structured interpretation is stored here so future meal logging can surface what
the agent has remembered about this user's food preferences.  Future meal recall
can apply the preference, making the adaptation both visible and persistent.

Pattern mirrors memory.py: SQLite for local/dev/tests, Firestore in production
(DIETRACE_STORE=firestore).  A (user_id, scope, target_food) triple is the
natural key — the same rule replaces on upsert so repeated feedback stays tidy.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dietrace.web.identity import DEMO_USER

_SCHEMA = """
CREATE TABLE IF NOT EXISTS standing_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    scope       TEXT NOT NULL,
    target_food TEXT NOT NULL,
    adjustment  REAL,
    rationale   TEXT,
    created_at  REAL NOT NULL,
    UNIQUE (user_id, scope, target_food)
)
"""


class StandingRule(BaseModel):
    """A persistent per-user food or meal-type preference.

    ``scope`` is one of ``this_food`` (applies to one named food),
    ``this_meal`` (applies to the whole current meal context), or
    ``meal_type`` (applies to all future meals of this category — e.g.
    "preworkout").  ``adjustment`` is a gram target when given, or None.
    ``rationale`` is the plain-English explanation of the user's intent.
    """

    scope: str
    target_food: str
    adjustment: float | None
    rationale: str = ""


class SqliteStandingRuleStore:
    """Per-user standing rules on SQLite (local/dev/tests)."""

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

    def remember(self, user_id: str, rule: StandingRule) -> None:
        """Persist (upsert) *rule* for *user_id*; same (scope, target_food) replaces."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO standing_rules "
                "(user_id, scope, target_food, adjustment, rationale, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    rule.scope,
                    rule.target_food,
                    rule.adjustment,
                    rule.rationale,
                    time.time(),
                ),
            )

    def recall(
        self, user_id: str, scope: str, target_food: str
    ) -> StandingRule | None:
        """Return the rule for *(scope, target_food)*, or None if none exists."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT scope, target_food, adjustment, rationale "
                "FROM standing_rules WHERE user_id = ? AND scope = ? AND target_food = ?",
                (user_id, scope, target_food),
            ).fetchone()
        if row is None:
            return None
        return StandingRule(
            scope=row["scope"],
            target_food=row["target_food"],
            adjustment=row["adjustment"],
            rationale=row["rationale"] or "",
        )

    def recent(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """*user_id*'s most recent standing rules, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT scope, target_food, adjustment, rationale "
                "FROM standing_rules WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [
            {
                "scope": row["scope"],
                "target_food": row["target_food"],
                "adjustment": row["adjustment"],
                "rationale": row["rationale"],
            }
            for row in rows
        ]

    def count(self, user_id: str = DEMO_USER) -> int:
        """How many standing rules *user_id* has set."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM standing_rules WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return int(row["n"]) if row else 0

    def clear_user(self, user_id: str = DEMO_USER) -> int:
        """Delete all of *user_id*'s standing rules; return rows removed."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM standing_rules WHERE user_id = ?", (user_id,)
            )
            return cursor.rowcount


class FirestoreStandingRuleStore:
    """Per-user standing rules on Firestore (production)."""

    def __init__(self, project: str | None = None) -> None:
        from dietrace.web.firestore_store import _client

        self._db = _client(project)
        self._col = "standing_rules"

    def _doc_id(self, user_id: str, scope: str, target_food: str) -> str:
        return f"{user_id}::{scope}::{target_food}"

    def remember(self, user_id: str, rule: StandingRule) -> None:
        self._db.collection(self._col).document(
            self._doc_id(user_id, rule.scope, rule.target_food)
        ).set(
            {
                "user_id": user_id,
                "scope": rule.scope,
                "target_food": rule.target_food,
                "adjustment": rule.adjustment,
                "rationale": rule.rationale,
                "created_at": time.time(),
            }
        )

    def recall(self, user_id: str, scope: str, target_food: str) -> StandingRule | None:
        snap = (
            self._db.collection(self._col)
            .document(self._doc_id(user_id, scope, target_food))
            .get()
        )
        if not snap.exists:
            return None
        data = snap.to_dict()
        return StandingRule(
            scope=data["scope"],
            target_food=data.get("target_food", ""),
            adjustment=data.get("adjustment"),
            rationale=data.get("rationale", ""),
        )

    def recent(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        from dietrace.web.firestore_store import _filter

        docs = [
            d.to_dict()
            for d in self._db.collection(self._col)
            .where(filter=_filter("user_id", user_id))
            .stream()
        ]
        docs.sort(key=lambda d: d.get("created_at", 0), reverse=True)
        return [
            {
                "scope": d["scope"],
                "target_food": d.get("target_food", ""),
                "adjustment": d.get("adjustment"),
                "rationale": d.get("rationale", ""),
            }
            for d in docs[:limit]
        ]

    def count(self, user_id: str = DEMO_USER) -> int:
        from dietrace.web.firestore_store import _filter

        query = (
            self._db.collection(self._col).where(filter=_filter("user_id", user_id))
        )
        return sum(1 for _ in query.stream())

    def clear_user(self, user_id: str = DEMO_USER) -> int:
        """Delete all of *user_id*'s standing rules; return docs removed."""
        from dietrace.web.firestore_store import _clear_collection

        return _clear_collection(self._db, self._col, user_id)


def build_standing_rules() -> Any:
    """Return the configured standing-rules backend (matches DIETRACE_STORE)."""
    import os

    if os.environ.get("DIETRACE_STORE", "sqlite").lower() == "firestore":
        project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
            "DIETRACE_GEMINI_PROJECT"
        )
        return FirestoreStandingRuleStore(project)
    return SqliteStandingRuleStore(
        os.environ.get("DIETRACE_RULES_DB", "data/rules.sqlite")
    )

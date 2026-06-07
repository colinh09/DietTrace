"""SQLite store for per-user macro targets.

Persists ONLY the computed targets (+rationale/source) — never the
MacroProfile that produced them. One row per user (upsert); re-saving replaces.
The deployed app uses FirestoreGoalStore behind the same interface.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from pathlib import Path

from dietrace.web.identity import DEMO_USER

_SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    user_id      TEXT PRIMARY KEY,
    targets_json TEXT NOT NULL,
    rationale    TEXT,
    source       TEXT,
    updated_at   TEXT NOT NULL
)
"""


class GoalStore:
    """Per-user macro target store at *db_path*.

    Only the resulting targets dict (USDA nutrient codes → daily amounts) is
    stored, plus optional rationale and source metadata.  The MacroProfile that
    produced the targets is never persisted here.
    """

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

    def get(self, user: str = DEMO_USER) -> dict[str, float] | None:
        """Return the saved targets for *user*, or None if not yet set."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT targets_json FROM goals WHERE user_id = ?", (user,)
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["targets_json"])

    def save(
        self,
        user: str,
        targets: dict[str, float],
        rationale: str | None = None,
        source: str | None = None,
    ) -> None:
        """Upsert *targets* for *user*.  Never accepts or stores profile fields."""
        when = datetime.datetime.now(tz=datetime.UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO goals (user_id, targets_json, rationale, source, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "  targets_json = excluded.targets_json, "
                "  rationale    = excluded.rationale, "
                "  source       = excluded.source, "
                "  updated_at   = excluded.updated_at",
                (user, json.dumps(targets), rationale, source, when),
            )

    def clear_user(self, user: str = DEMO_USER) -> int:
        """Delete *user*'s saved goals; return how many rows were removed."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM goals WHERE user_id = ?", (user,))
            return cursor.rowcount

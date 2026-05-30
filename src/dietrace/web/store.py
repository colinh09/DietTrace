"""SQLite store for the user's logged meals.

Separate from the read-only food DB: this persists what the user logged (the
free text plus the computed nutrient totals) so ``/history`` and ``/analysis``
can read it back. Small and append-mostly; one row per logged meal.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    text        TEXT NOT NULL,
    totals_json TEXT NOT NULL
)
"""


class MealLogStore:
    """Append-and-read store for logged meals at *db_path*."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, text: str, totals: list[dict[str, Any]]) -> int:
        """Persist a logged meal and return its new row id."""
        created_at = datetime.datetime.now(tz=datetime.UTC).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO meals (created_at, text, totals_json) VALUES (?, ?, ?)",
                (created_at, text, json.dumps(totals)),
            )
            return int(cursor.lastrowid)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recently logged meals, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, text, totals_json FROM meals "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "text": row["text"],
                "totals": json.loads(row["totals_json"]),
            }
            for row in rows
        ]

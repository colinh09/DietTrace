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
    date        TEXT NOT NULL,
    text        TEXT NOT NULL,
    totals_json TEXT NOT NULL
)
"""


class MealLogStore:
    """Append-and-read store for logged meals at *db_path*."""

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

    def add(
        self,
        text: str,
        totals: list[dict[str, Any]],
        created_at: datetime.datetime | None = None,
        date: str | None = None,
    ) -> int:
        """Persist a logged meal and return its new row id.

        ``created_at`` defaults to now (UTC). The calendar ``date`` (the day the
        meal belongs to, for ``list(date=...)``) defaults to that timestamp's day
        but can be passed explicitly so the client's local day is recorded rather
        than the server's UTC day.
        """
        when = created_at or datetime.datetime.now(tz=datetime.UTC)
        day = date or when.date().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO meals (created_at, date, text, totals_json) "
                "VALUES (?, ?, ?, ?)",
                (when.isoformat(), day, text, json.dumps(totals)),
            )
            return int(cursor.lastrowid)

    def delete(self, meal_id: int) -> bool:
        """Delete the meal with *meal_id*; return True if a row was removed."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))
            return cursor.rowcount > 0

    def list(
        self, limit: int = 50, date: str | None = None
    ) -> list[dict[str, Any]]:
        """Return logged meals newest first, optionally filtered to one ``date``.

        ``date`` is a ``YYYY-MM-DD`` calendar day; when omitted, all days are
        returned (up to ``limit``).
        """
        query = "SELECT id, created_at, date, text, totals_json FROM meals"
        params: list[Any] = []
        if date is not None:
            query += " WHERE date = ?"
            params.append(date)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "date": row["date"],
                "text": row["text"],
                "totals": json.loads(row["totals_json"]),
            }
            for row in rows
        ]

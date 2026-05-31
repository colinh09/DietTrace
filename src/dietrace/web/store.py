"""SQLite store for users' logged meals.

Separate from the read-only food DB: this persists what each user logged (the
free text plus the computed nutrient totals) so ``/history`` and ``/analysis``
can read it back. Small and append-mostly; one row per logged meal, scoped to a
user (the per-user memory layer, ). This is the local/dev backend; the
deployed app uses the Firestore backend behind the same interface.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from pathlib import Path
from typing import Any

from dietrace.web.identity import DEMO_USER

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL DEFAULT 'demo',
    created_at  TEXT NOT NULL,
    date        TEXT NOT NULL,
    text        TEXT NOT NULL,
    totals_json TEXT NOT NULL
)
"""


class MealLogStore:
    """Append-and-read store for logged meals at *db_path*, scoped by user."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        parent = Path(self._db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)
            _ensure_user_column(conn, "meals")

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
        user_id: str = DEMO_USER,
    ) -> int:
        """Persist a logged meal for *user_id* and return its new row id.

        ``created_at`` defaults to now (UTC). The calendar ``date`` (the day the
        meal belongs to, for ``list(date=...)``) defaults to that timestamp's day
        but can be passed explicitly so the client's local day is recorded rather
        than the server's UTC day.
        """
        when = created_at or datetime.datetime.now(tz=datetime.UTC)
        day = date or when.date().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO meals (user_id, created_at, date, text, totals_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, when.isoformat(), day, text, json.dumps(totals)),
            )
            return int(cursor.lastrowid)

    def delete(self, meal_id: int, user_id: str = DEMO_USER) -> bool:
        """Delete *user_id*'s meal *meal_id*; return True if a row was removed.

        Scoped to the user so one user can't delete another's meal.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM meals WHERE id = ? AND user_id = ?", (meal_id, user_id)
            )
            return cursor.rowcount > 0

    def list(
        self, limit: int = 50, date: str | None = None, user_id: str = DEMO_USER
    ) -> list[dict[str, Any]]:
        """Return *user_id*'s logged meals newest first, optionally for one ``date``.

        ``date`` is a ``YYYY-MM-DD`` calendar day; when omitted, all days are
        returned (up to ``limit``).
        """
        query = "SELECT id, created_at, date, text, totals_json FROM meals WHERE user_id = ?"
        params: list[Any] = [user_id]
        if date is not None:
            query += " AND date = ?"
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


def _ensure_user_column(conn: sqlite3.Connection, table: str) -> None:
    """Add a ``user_id`` column to *table* if an older DB predates it (migration)."""
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if "user_id" not in cols:
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT '{DEMO_USER}'"
        )

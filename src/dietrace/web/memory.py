"""Per-user learning memory — the layer that makes a correction *take effect*.

When a user fixes a logged meal, the corrected result is remembered for them. Two
uses fall out of the same record:

* **cache** — re-logging the *same* meal returns the corrected result instantly
  (``recall``), so a fix the user made is visibly applied next time; and
* **few-shot** — the corrected meals become worked examples (``examples``) injected
  into *that user's* parse prompt, so *similar* meals improve too (this is what
  generalizes the fix — e.g. "don't count a composite dish AND its components").

Scoped per user and pluggable like the meal/feedback stores: SQLite for local/dev
and tests, Firestore in production (``DIETRACE_STORE=firestore``) so a user's
learning survives cold starts. A correction for a meal text overwrites the prior
one, so the latest fix always wins.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

_CALORIE, _PROTEIN, _FAT, _CARB = "208", "203", "204", "205"


def normalize(text: str) -> str:
    """The cache key for a meal: lowercased, punctuation-stripped, space-collapsed."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def sum_totals(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sum the per-item nutrient panels into meal totals, keyed by USDA code."""
    agg: dict[str, dict[str, Any]] = {}
    for item in items:
        for nutrient in item.get("nutrients", []):
            entry = agg.setdefault(
                nutrient["code"],
                {"code": nutrient["code"], "name": nutrient.get("name", ""), "amount": 0.0,
                 "unit": nutrient.get("unit", "")},
            )
            entry["amount"] += float(nutrient.get("amount", 0.0))
    return list(agg.values())


def calories_of(totals: list[dict[str, Any]]) -> float:
    """The energy (USDA 208) amount from a totals list, or 0.0 if absent."""
    for nutrient in totals:
        if nutrient.get("code") == "208":
            return float(nutrient.get("amount", 0.0))
    return 0.0


def _example_of(meal_text: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Render a remembered correction as a few-shot example for the parse prompt."""
    return {
        "text": meal_text,
        "foods": [
            {"food": item.get("description", ""), "grams": round(item.get("grams", 0.0))}
            for item in items
        ],
    }


class SqliteMemory:
    """Per-user learning memory on SQLite (local/dev/tests)."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS memory (
        user_id     TEXT NOT NULL,
        norm        TEXT NOT NULL,
        meal_text   TEXT NOT NULL,
        items_json  TEXT NOT NULL,
        totals_json TEXT NOT NULL,
        created_at  REAL NOT NULL,
        PRIMARY KEY (user_id, norm)
    )
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        parent = Path(self._db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(self._SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def remember(
        self,
        user_id: str,
        meal_text: str,
        items: list[dict[str, Any]],
        totals: list[dict[str, Any]],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO memory "
                "(user_id, norm, meal_text, items_json, totals_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    normalize(meal_text),
                    meal_text,
                    json.dumps(items),
                    json.dumps(totals),
                    time.time(),
                ),
            )

    def recall(self, user_id: str, meal_text: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT items_json, totals_json FROM memory WHERE user_id = ? AND norm = ?",
                (user_id, normalize(meal_text)),
            ).fetchone()
        if row is None:
            return None
        return {
            "per_item": json.loads(row["items_json"]),
            "totals": json.loads(row["totals_json"]),
        }

    def examples(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT meal_text, items_json FROM memory WHERE user_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [_example_of(r["meal_text"], json.loads(r["items_json"])) for r in rows]

    def count(self, user_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM memory WHERE user_id = ?", (user_id,)
            ).fetchone()
        return int(row["n"]) if row else 0

    def clear_user(self, user_id: str) -> int:
        """Forget all of *user_id*'s remembered examples; return rows removed."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM memory WHERE user_id = ?", (user_id,))
            return cursor.rowcount


class FirestoreMemory:
    """Per-user learning memory on Firestore (production)."""

    def __init__(self, project: str | None = None) -> None:
        from dietrace.web.firestore_store import _client

        self._db = _client(project)
        self._col = "memory"

    def _doc_id(self, user_id: str, meal_text: str) -> str:
        return f"{user_id}::{normalize(meal_text)}"

    def remember(
        self,
        user_id: str,
        meal_text: str,
        items: list[dict[str, Any]],
        totals: list[dict[str, Any]],
    ) -> None:
        self._db.collection(self._col).document(self._doc_id(user_id, meal_text)).set(
            {
                "user_id": user_id,
                "norm": normalize(meal_text),
                "meal_text": meal_text,
                "items": items,
                "totals": totals,
                "created_at": time.time(),
            }
        )

    def recall(self, user_id: str, meal_text: str) -> dict[str, Any] | None:
        snap = self._db.collection(self._col).document(
            self._doc_id(user_id, meal_text)
        ).get()
        if not snap.exists:
            return None
        data = snap.to_dict()
        return {"per_item": data["items"], "totals": data["totals"]}

    def examples(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        from dietrace.web.firestore_store import _filter

        docs = [
            d.to_dict()
            for d in self._db.collection(self._col)
            .where(filter=_filter("user_id", user_id))
            .stream()
        ]
        docs.sort(key=lambda d: d.get("created_at", 0), reverse=True)
        return [_example_of(d["meal_text"], d["items"]) for d in docs[:limit]]

    def count(self, user_id: str) -> int:
        from dietrace.web.firestore_store import _filter

        query = self._db.collection(self._col).where(filter=_filter("user_id", user_id))
        return sum(1 for _ in query.stream())

    def clear_user(self, user_id: str) -> int:
        """Forget all of *user_id*'s remembered examples; return docs removed."""
        from dietrace.web.firestore_store import _clear_collection

        return _clear_collection(self._db, self._col, user_id)


def build_memory() -> Any:
    """Return the configured per-user memory backend (matches DIETRACE_STORE)."""
    if os.environ.get("DIETRACE_STORE", "sqlite").lower() == "firestore":
        project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
            "DIETRACE_GEMINI_PROJECT"
        )
        return FirestoreMemory(project)
    return SqliteMemory(os.environ.get("DIETRACE_MEMORY_DB", "data/memory.sqlite"))

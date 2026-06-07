"""SQLite stores for the per-user learning loop.

Three small, per-user stores that back the personalization loop:

- ``ConfirmationStore`` — **Input A**: meals the user confirmed via "does this
  look right?". These are ground-truth datapoints used ONLY to *gate* a proposed
  prompt (the held-out eval set). They never change the prompt.
- ``FeedbackLog`` — **Input B**: the user's explicit corrections (natural-language
  feedback + its structured interpretation + an emphasis weight). The corrector
  generalizes these into the preference block. They never enter the gate set.
- ``PreferenceStore`` — the per-user **preference block**: a short, generalized,
  token-capped prompt addendum the corrector maintains, with provenance (which
  corrections produced which rule) for observability, and a bumping version.

The XOR rule (a meal is Input A *or* Input B, never both) lives in the endpoints;
these stores just hold the two sets separately. Mirrors the existing store
pattern; the deployed app gets Firestore variants behind the same interfaces.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from pathlib import Path
from typing import Any

from dietrace.web.identity import DEMO_USER


def _now() -> str:
    return datetime.datetime.now(tz=datetime.UTC).isoformat()


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _prepare(db_path: str | Path, schema: str) -> str:
    path = str(db_path)
    parent = Path(path).parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        conn.execute(schema)
    return path


# ──────────────────────────────────────────────────────────────────────────────
# Input A — confirmed meals (the held-out gate dataset)
# ──────────────────────────────────────────────────────────────────────────────

_CONFIRMATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS confirmations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL DEFAULT 'demo',
    created_at  TEXT NOT NULL,
    meal_text   TEXT NOT NULL,
    items_json  TEXT NOT NULL,
    totals_json TEXT NOT NULL
)
"""


class ConfirmationStore:
    """Per-user confirmed meals — ground truth for the gate (Input A)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = _prepare(db_path, _CONFIRMATION_SCHEMA)

    def add(
        self,
        user_id: str,
        meal_text: str,
        items: list[dict[str, Any]],
        totals: list[dict[str, Any]],
    ) -> int:
        """Record a confirmed meal as a held-out datapoint; return its row id."""
        with _connect(self._db_path) as conn:
            cur = conn.execute(
                "INSERT INTO confirmations (user_id, created_at, meal_text, items_json, "
                "totals_json) VALUES (?, ?, ?, ?, ?)",
                (user_id, _now(), meal_text, json.dumps(items), json.dumps(totals)),
            )
            return int(cur.lastrowid)

    def list(self, user_id: str = DEMO_USER, limit: int = 200) -> list[dict[str, Any]]:
        """The user's confirmed meals, newest first."""
        with _connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, created_at, meal_text, items_json, totals_json "
                "FROM confirmations WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "meal_text": r["meal_text"],
                "items": json.loads(r["items_json"]),
                "totals": json.loads(r["totals_json"]),
            }
            for r in rows
        ]

    def count(self, user_id: str = DEMO_USER) -> int:
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM confirmations WHERE user_id = ?", (user_id,)
            ).fetchone()
        return int(row["n"]) if row else 0

    def delete(self, confirmation_id: int, user_id: str = DEMO_USER) -> bool:
        with _connect(self._db_path) as conn:
            cur = conn.execute(
                "DELETE FROM confirmations WHERE id = ? AND user_id = ?",
                (confirmation_id, user_id),
            )
            return cur.rowcount > 0

    def delete_by_meal(self, user_id: str, meal_text: str) -> int:
        """Drop any confirmation for *meal_text* — used to enforce the XOR rule
        (correcting a meal removes it from the held-out gate set)."""
        with _connect(self._db_path) as conn:
            cur = conn.execute(
                "DELETE FROM confirmations WHERE user_id = ? AND meal_text = ?",
                (user_id, meal_text),
            )
            return cur.rowcount

    def clear_user(self, user_id: str = DEMO_USER) -> int:
        with _connect(self._db_path) as conn:
            cur = conn.execute(
                "DELETE FROM confirmations WHERE user_id = ?", (user_id,)
            )
            return cur.rowcount


# ──────────────────────────────────────────────────────────────────────────────
# Input B — corrections / feedback (drives the preference block)
# ──────────────────────────────────────────────────────────────────────────────

_FEEDBACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL DEFAULT 'demo',
    created_at      TEXT NOT NULL,
    feedback_text   TEXT NOT NULL,
    structured_json TEXT,
    meal_text       TEXT,
    weight          REAL NOT NULL DEFAULT 1.0,
    processed_at    TEXT
)
"""


class FeedbackLog:
    """Per-user explicit corrections the corrector generalizes (Input B).

    Each row is one piece of natural-language feedback plus its structured
    interpretation and an emphasis ``weight`` (1.0 default; the user can bump it
    to say "this one really matters"). Editable + deletable, since the preference
    block is a pure function of this set.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = _prepare(db_path, _FEEDBACK_SCHEMA)
        # Migration: add processed_at to a DB created before the column existed,
        # so a retune can fold in only NEW (unprocessed) corrections.
        with _connect(self._db_path) as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(feedback_log)")}
            if "processed_at" not in cols:
                conn.execute("ALTER TABLE feedback_log ADD COLUMN processed_at TEXT")

    def add(
        self,
        user_id: str,
        feedback_text: str,
        structured: dict[str, Any] | None = None,
        meal_text: str | None = None,
        weight: float = 1.0,
    ) -> int:
        with _connect(self._db_path) as conn:
            cur = conn.execute(
                "INSERT INTO feedback_log (user_id, created_at, feedback_text, "
                "structured_json, meal_text, weight) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    _now(),
                    feedback_text,
                    json.dumps(structured) if structured is not None else None,
                    meal_text,
                    float(weight),
                ),
            )
            return int(cur.lastrowid)

    _COLS = (
        "id, created_at, feedback_text, structured_json, meal_text, weight, processed_at"
    )

    def list(self, user_id: str = DEMO_USER, limit: int = 200) -> list[dict[str, Any]]:
        with _connect(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT {self._COLS} FROM feedback_log WHERE user_id = ? "  # noqa: S608
                "ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [self._row(r) for r in rows]

    def list_unprocessed(
        self, user_id: str = DEMO_USER, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Corrections not yet folded into a shipped block — the ONLY ones a
        retune should generalize (so it never re-learns what it already knows)."""
        with _connect(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT {self._COLS} FROM feedback_log "  # noqa: S608
                "WHERE user_id = ? AND processed_at IS NULL ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [self._row(r) for r in rows]

    def mark_processed(self, user_id: str, ids: list[int]) -> int:
        """Stamp corrections as folded into the shipped block (so the next retune
        ignores them). No-op for an empty id list."""
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with _connect(self._db_path) as conn:
            cur = conn.execute(
                f"UPDATE feedback_log SET processed_at = ? "  # noqa: S608 — fixed columns
                f"WHERE user_id = ? AND id IN ({placeholders})",
                (_now(), user_id, *ids),
            )
            return cur.rowcount

    def count_unprocessed(self, user_id: str = DEMO_USER) -> int:
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM feedback_log "
                "WHERE user_id = ? AND processed_at IS NULL",
                (user_id,),
            ).fetchone()
        return int(row["n"]) if row else 0

    def get(self, feedback_id: int, user_id: str = DEMO_USER) -> dict[str, Any] | None:
        with _connect(self._db_path) as conn:
            row = conn.execute(
                f"SELECT {self._COLS} FROM feedback_log "  # noqa: S608
                "WHERE id = ? AND user_id = ?",
                (feedback_id, user_id),
            ).fetchone()
        return self._row(row) if row else None

    def update(
        self,
        feedback_id: int,
        user_id: str = DEMO_USER,
        feedback_text: str | None = None,
        weight: float | None = None,
    ) -> bool:
        """Edit the text and/or emphasis of one correction (partial update)."""
        sets: list[str] = []
        params: list[Any] = []
        if feedback_text is not None:
            sets.append("feedback_text = ?")
            params.append(feedback_text)
        if weight is not None:
            sets.append("weight = ?")
            params.append(float(weight))
        if not sets:
            return False
        # An edited correction is "new" again — clear its processed stamp so the
        # next retune re-folds the changed version.
        sets.append("processed_at = NULL")
        params.extend([feedback_id, user_id])
        with _connect(self._db_path) as conn:
            cur = conn.execute(
                f"UPDATE feedback_log SET {', '.join(sets)} "  # noqa: S608 — fixed columns
                "WHERE id = ? AND user_id = ?",
                params,
            )
            return cur.rowcount > 0

    def delete(self, feedback_id: int, user_id: str = DEMO_USER) -> bool:
        with _connect(self._db_path) as conn:
            cur = conn.execute(
                "DELETE FROM feedback_log WHERE id = ? AND user_id = ?",
                (feedback_id, user_id),
            )
            return cur.rowcount > 0

    def count(self, user_id: str = DEMO_USER) -> int:
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM feedback_log WHERE user_id = ?", (user_id,)
            ).fetchone()
        return int(row["n"]) if row else 0

    def clear_user(self, user_id: str = DEMO_USER) -> int:
        with _connect(self._db_path) as conn:
            cur = conn.execute(
                "DELETE FROM feedback_log WHERE user_id = ?", (user_id,)
            )
            return cur.rowcount

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "feedback_text": row["feedback_text"],
            "structured": json.loads(row["structured_json"])
            if row["structured_json"]
            else None,
            "meal_text": row["meal_text"],
            "weight": float(row["weight"]),
            "processed": row["processed_at"] is not None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# The per-user preference block (what the corrector maintains)
# ──────────────────────────────────────────────────────────────────────────────

_PREFERENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS preference_blocks (
    user_id         TEXT PRIMARY KEY,
    block_text      TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT NOT NULL,
    provenance_json TEXT
)
"""


class PreferenceStore:
    """The per-user preference block — the generalized, gated personalization."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = _prepare(db_path, _PREFERENCE_SCHEMA)

    def get(self, user_id: str = DEMO_USER) -> dict[str, Any] | None:
        """The user's current block, or None if they have none yet."""
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT block_text, version, updated_at, provenance_json "
                "FROM preference_blocks WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "block_text": row["block_text"],
            "version": int(row["version"]),
            "updated_at": row["updated_at"],
            "provenance": json.loads(row["provenance_json"])
            if row["provenance_json"]
            else [],
        }

    def block_text(self, user_id: str = DEMO_USER) -> str:
        """Just the block text (empty string when the user has none) — for injection."""
        current = self.get(user_id)
        return current["block_text"] if current else ""

    def save(
        self,
        user_id: str,
        block_text: str,
        provenance: list[dict[str, Any]] | None = None,
    ) -> int:
        """Upsert the user's block, bumping the version; return the new version."""
        existing = self.get(user_id)
        version = (existing["version"] + 1) if existing else 1
        with _connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO preference_blocks (user_id, block_text, version, "
                "updated_at, provenance_json) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "  block_text = excluded.block_text, "
                "  version = excluded.version, "
                "  updated_at = excluded.updated_at, "
                "  provenance_json = excluded.provenance_json",
                (
                    user_id,
                    block_text,
                    version,
                    _now(),
                    json.dumps(provenance) if provenance is not None else None,
                ),
            )
        return version

    def clear_user(self, user_id: str = DEMO_USER) -> int:
        with _connect(self._db_path) as conn:
            cur = conn.execute(
                "DELETE FROM preference_blocks WHERE user_id = ?", (user_id,)
            )
            return cur.rowcount


# ──────────────────────────────────────────────────────────────────────────────
# The per-user profile — freeform "who I am / how I eat" context
# ──────────────────────────────────────────────────────────────────────────────

_PROFILE_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id      TEXT PRIMARY KEY,
    profile_text TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)
"""


class UserProfileStore:
    """A per-user freeform profile: the user's own words about their goals and
    eating style ("marathon runner cutting weight; I carb-load hard before long
    runs"). Standing context the corrector reads when generalizing corrections,
    so personalization reflects who the user is — not just their fixes."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = _prepare(db_path, _PROFILE_SCHEMA)

    def get(self, user_id: str = DEMO_USER) -> str:
        """The user's profile text, or '' if they haven't set one."""
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT profile_text FROM user_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row["profile_text"] if row else ""

    def set(self, user_id: str, profile_text: str) -> None:
        with _connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO user_profiles (user_id, profile_text, updated_at) "
                "VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
                "  profile_text = excluded.profile_text, updated_at = excluded.updated_at",
                (user_id, profile_text, _now()),
            )

    def clear_user(self, user_id: str = DEMO_USER) -> int:
        with _connect(self._db_path) as conn:
            cur = conn.execute(
                "DELETE FROM user_profiles WHERE user_id = ?", (user_id,)
            )
            return cur.rowcount


def build_profile_store() -> UserProfileStore:
    """Build the per-user profile store from env (local/dev default)."""
    import os

    return UserProfileStore(
        os.environ.get("DIETRACE_PROFILE_DB", "data/profiles.sqlite")
    )


def build_learning_stores() -> tuple[ConfirmationStore, FeedbackLog, PreferenceStore]:
    """Build the SQLite learning-loop stores from env (local/dev default).

    Firestore parity for the deployed backend is a follow-up; the loop is fully
    functional + tested on SQLite, which is what the offline build needs.
    """
    import os

    return (
        ConfirmationStore(os.environ.get("DIETRACE_CONFIRM_DB", "data/confirmations.sqlite")),
        FeedbackLog(os.environ.get("DIETRACE_FEEDBACK_LOG_DB", "data/feedback_log.sqlite")),
        PreferenceStore(os.environ.get("DIETRACE_PREFERENCE_DB", "data/preferences.sqlite")),
    )

"""Per-user macro preference memory — makes a macro correction take effect.

The macro counterpart of the food-logging memory layer. When a user saves macro
targets, their preferred *split* — protein and fat as fractions of total kcal — is
remembered for them, so the next plan can bias toward it instead of the generic
goal-default split. The split is the learning signal because it is:

* **scale-free** — fractions of kcal, so it transfers across different calorie
  targets (a heavier cut next month still keeps "this user runs protein high"); and
* **profile-free** — derived purely from the saved targets (208/203/204), so no
  age/weight/height is stored (the privacy promise holds).

Pluggable like the other stores: SQLite for local/dev/tests, Firestore in
production (``DIETRACE_STORE=firestore``). Latest save wins.
"""

from __future__ import annotations

import math
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

_ENERGY, _PROTEIN, _FAT = "208", "203", "204"

# Standard Atwater factors (kcal/g) — protein and fat shares of total kcal.
_ATWATER_P = 4.0
_ATWATER_F = 9.0

# The user's saved macro preferences accumulate in their own Phoenix dataset (the
# macro counterpart of the food-correction feedback dataset) — versioned, real
# ground truth the supervisor/eval story can fold in. Profile-free.
MACRO_PREFS_DATASET = "dietrace-macro-prefs-v1"
MACRO_PREFS_DESCRIPTION = (
    "User macro split preferences from DietTrace — per-user ground truth (profile-free)."
)

# How a preference is pushed to Phoenix: (user, split) -> succeeded?
MacroPrefPusher = Any


def push_macro_preference(user: str, split: dict[str, float]) -> bool:
    """Append a user's preferred split to the Phoenix macro-prefs dataset (fail-soft).

    Creates the dataset on the first push. Lazy import + broad except + an early env
    check so a missing key or unreachable Phoenix never breaks ``/macros/save`` and
    no network is touched offline. The split is profile-free; the anonymous user id
    rides in metadata only.
    """
    api_key = os.environ.get("PHOENIX_API_KEY")
    base_url = os.environ.get("PHOENIX_BASE_URL")
    if not api_key or not base_url:
        return False
    try:
        from phoenix.client import Client

        client = Client(base_url=base_url, api_key=api_key)
        inp = {"split": "protein/fat fractions of kcal"}
        out = {"protein_pct": split["protein_pct"], "fat_pct": split["fat_pct"]}
        meta = {"source": "user_macro_pref", "user": user}
        try:
            client.datasets.add_examples_to_dataset(
                dataset=MACRO_PREFS_DATASET, inputs=[inp], outputs=[out], metadata=[meta]
            )
        except Exception:
            client.datasets.create_dataset(
                name=MACRO_PREFS_DATASET,
                dataset_description=MACRO_PREFS_DESCRIPTION,
                inputs=[inp],
                outputs=[out],
                metadata=[meta],
            )
        return True
    except Exception:
        return False


def split_of(targets: dict[str, float]) -> dict[str, float] | None:
    """The protein/fat split (fractions of kcal) implied by *targets*, or None.

    Returns ``{"protein_pct": float, "fat_pct": float}`` derived only from the
    energy/protein/fat targets — never the profile. None when kcal is missing or
    non-positive, or when the derived split is non-finite (nothing meaningful to
    remember). ``MacroSaveRequest.targets`` is an unconstrained ``dict[str, float]``
    so pydantic admits ``NaN``/``Infinity``; a non-finite split would poison every
    consumer — it is persisted as a REAL (and NaN even violates the NOT NULL column,
    crashing ``remember``), recalled into ``macro_adherence``'s deltas, and pushed to
    the Phoenix prefs dataset, all serializing as invalid JSON (fail-soft,
    mirrors :func:`dietrace.web.goals._valid_target`).
    """
    kcal = float(targets.get(_ENERGY, 0.0) or 0.0)
    if kcal <= 0.0:
        return None
    protein = float(targets.get(_PROTEIN, 0.0) or 0.0)
    fat = float(targets.get(_FAT, 0.0) or 0.0)
    protein_pct = round(_ATWATER_P * protein / kcal, 4)
    fat_pct = round(_ATWATER_F * fat / kcal, 4)
    if not (math.isfinite(protein_pct) and math.isfinite(fat_pct)):
        return None
    return {"protein_pct": protein_pct, "fat_pct": fat_pct}


class SqliteMacroMemory:
    """Per-user macro preference memory on SQLite (local/dev/tests)."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS macro_memory (
        user_id      TEXT NOT NULL PRIMARY KEY,
        protein_pct  REAL NOT NULL,
        fat_pct      REAL NOT NULL,
        created_at   REAL NOT NULL
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

    def remember(self, user_id: str, targets: dict[str, float]) -> bool:
        """Remember the split implied by *targets* for *user_id*. True if stored."""
        split = split_of(targets)
        if split is None:
            return False
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO macro_memory "
                "(user_id, protein_pct, fat_pct, created_at) VALUES (?, ?, ?, ?)",
                (user_id, split["protein_pct"], split["fat_pct"], time.time()),
            )
        return True

    def recall(self, user_id: str) -> dict[str, float] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT protein_pct, fat_pct FROM macro_memory WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return {"protein_pct": row["protein_pct"], "fat_pct": row["fat_pct"]}

    def count(self, user_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM macro_memory WHERE user_id = ?", (user_id,)
            ).fetchone()
        return int(row["n"]) if row else 0

    def clear_user(self, user_id: str) -> int:
        """Forget *user_id*'s learned macro split; return rows removed."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM macro_memory WHERE user_id = ?", (user_id,)
            )
            return cursor.rowcount


class FirestoreMacroMemory:
    """Per-user macro preference memory on Firestore (production)."""

    def __init__(self, project: str | None = None) -> None:
        from dietrace.web.firestore_store import _client

        self._db = _client(project)
        self._col = "macro_memory"

    def remember(self, user_id: str, targets: dict[str, float]) -> bool:
        split = split_of(targets)
        if split is None:
            return False
        self._db.collection(self._col).document(user_id).set(
            {
                "user_id": user_id,
                "protein_pct": split["protein_pct"],
                "fat_pct": split["fat_pct"],
                "created_at": time.time(),
            }
        )
        return True

    def recall(self, user_id: str) -> dict[str, float] | None:
        snap = self._db.collection(self._col).document(user_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict()
        return {"protein_pct": data["protein_pct"], "fat_pct": data["fat_pct"]}

    def count(self, user_id: str) -> int:
        snap = self._db.collection(self._col).document(user_id).get()
        return 1 if snap.exists else 0

    def clear_user(self, user_id: str) -> int:
        """Forget *user_id*'s learned macro split; return 1 if one existed, else 0."""
        ref = self._db.collection(self._col).document(user_id)
        if ref.get().exists:
            ref.delete()
            return 1
        return 0


def build_macro_memory() -> Any:
    """Return the configured macro-memory backend (matches DIETRACE_STORE)."""
    if os.environ.get("DIETRACE_STORE", "sqlite").lower() == "firestore":
        project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
            "DIETRACE_GEMINI_PROJECT"
        )
        return FirestoreMacroMemory(project)
    return SqliteMacroMemory(
        os.environ.get("DIETRACE_MACRO_MEMORY_DB", "data/macro_memory.sqlite")
    )

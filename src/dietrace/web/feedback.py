"""User corrections → Arize Phoenix ground truth (the self-supervision loop, in-app).

This closes the loop the rest of the system only ran offline: when a logged
estimate is wrong, the user corrects the portion in the UI, and that correction
becomes a new **example in the Phoenix eval dataset** — real, versioned ground
truth. The next eval experiment scores against it, and the ``/accuracy`` page
moves. So the app demonstrably gets more accurate *because it was used*, which is
the Arize-track story made tangible.

A correction carries the item's logged per-portion nutrient panel; rescaling it to
the corrected grams yields the expected macros for the example. Pushing to Phoenix
is best-effort (fail-soft): a correction is always recorded locally even when
Phoenix is unreachable, so the count the UI shows never lies about what was saved.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dietrace.web.identity import DEMO_USER

# User corrections accumulate in their OWN Phoenix dataset rather than the curated
# eval set (`dietrace-nutrition-v1`): they're macro-only ground truth, so keeping
# them separate preserves the full-micro eval cases while still giving the
# supervisor a growing, real corpus to fold in. The /accuracy experiments run on
# the curated set; this is the user-contributed companion.
FEEDBACK_DATASET = "dietrace-feedback-v1"
FEEDBACK_DESCRIPTION = "User portion corrections from the DietTrace app — ground truth."

# USDA number codes for the macros an eval example expects.
_CALORIE, _PROTEIN, _FAT, _CARB = "208", "203", "204", "205"

# How a correction is pushed to Phoenix: (input, output, metadata) -> succeeded?
FeedbackPusher = Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], bool]


class Correction(BaseModel):
    """A user's portion correction for one logged item.

    ``nutrients`` is the item's panel **as logged** (already scaled to
    ``original_grams``), so the corrected macros are just a proportional rescale to
    ``corrected_grams`` — no food-DB lookup needed.
    """

    food: str
    original_grams: float
    corrected_grams: float
    nutrients: list[dict[str, Any]] = []

    def _amount(self, code: str) -> float | None:
        for nutrient in self.nutrients:
            if nutrient.get("code") == code:
                return nutrient.get("amount")
        return None


def corrected_expected(correction: Correction) -> dict[str, Any]:
    """The expected macros for the corrected portion — the example's ground truth.

    Rescales the logged panel by ``corrected/original`` grams. A macro the panel
    didn't carry is omitted rather than guessed at.
    """
    base = correction.original_grams
    factor = correction.corrected_grams / base if base else 0.0
    expected: dict[str, Any] = {"grams": correction.corrected_grams}
    for key, code in (
        ("calories", _CALORIE),
        ("protein_g", _PROTEIN),
        ("fat_g", _FAT),
        ("carb_g", _CARB),
    ):
        amount = correction._amount(code)
        if amount is not None:
            expected[key] = round(amount * factor, 2)
    return expected


def to_example(
    correction: Correction,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Render a correction as a Phoenix dataset (input, output, metadata) example."""
    inp = {"text": correction.food}
    out = corrected_expected(correction)
    meta = {
        "source": "user_feedback",
        "original_grams": correction.original_grams,
        "corrected_grams": correction.corrected_grams,
    }
    return inp, out, meta


def phoenix_push(inp: dict[str, Any], out: dict[str, Any], meta: dict[str, Any]) -> bool:
    """Append one example to the Phoenix feedback dataset; True on success (fail-soft).

    Appends to ``FEEDBACK_DATASET``, creating it on the first correction (Phoenix
    can't append to a dataset that doesn't exist yet). Lazy import + broad except so
    a missing key or an unreachable Phoenix never breaks the user's correction — it
    is already persisted locally either way.
    """
    import os

    api_key = os.environ.get("PHOENIX_API_KEY")
    base_url = os.environ.get("PHOENIX_BASE_URL")
    if not api_key or not base_url:
        return False
    try:
        from phoenix.client import Client

        client = Client(base_url=base_url, api_key=api_key)
        try:
            client.datasets.add_examples_to_dataset(
                dataset=FEEDBACK_DATASET, inputs=[inp], outputs=[out], metadata=[meta]
            )
        except Exception:
            # First correction: the dataset doesn't exist yet — create it.
            client.datasets.create_dataset(
                name=FEEDBACK_DATASET,
                dataset_description=FEEDBACK_DESCRIPTION,
                inputs=[inp],
                outputs=[out],
                metadata=[meta],
            )
        return True
    except Exception:
        return False


_SCHEMA = """
CREATE TABLE IF NOT EXISTS corrections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL DEFAULT 'demo',
    created_at      TEXT NOT NULL,
    food            TEXT NOT NULL,
    original_grams  REAL NOT NULL,
    corrected_grams REAL NOT NULL,
    expected_json   TEXT NOT NULL
)
"""


class FeedbackStore:
    """Append-and-count store for user corrections at *db_path*, scoped by user."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        parent = Path(self._db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(corrections)")}
            if "user_id" not in cols:  # migrate an older DB
                conn.execute(
                    "ALTER TABLE corrections ADD COLUMN user_id TEXT NOT NULL "
                    f"DEFAULT '{DEMO_USER}'"
                )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def add(
        self, correction: Correction, expected: dict[str, Any], user_id: str = DEMO_USER
    ) -> int:
        """Persist a correction for *user_id*; return its new row id."""
        when = datetime.datetime.now(tz=datetime.UTC).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO corrections "
                "(user_id, created_at, food, original_grams, corrected_grams, expected_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    when,
                    correction.food,
                    correction.original_grams,
                    correction.corrected_grams,
                    json.dumps(expected),
                ),
            )
            return int(cursor.lastrowid or 0)

    def count(self, user_id: str = DEMO_USER) -> int:
        """How many corrections *user_id* has contributed."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM corrections WHERE user_id = ?", (user_id,)
            ).fetchone()
            return int(row["n"]) if row else 0

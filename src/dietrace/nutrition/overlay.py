"""Curated common-foods overlay — the head of the food distribution, pinned.

Food logging is extremely head-heavy: a few hundred names cover most real entries.
This maps those common names → a hand-verified canonical ``fdc_id`` so they resolve
**deterministically and instantly**, independent of (and immune to future changes
in) the ranked search. It's the industry-standard "best match"/verified tier — the
permanent fix for the ranking class (carrot, oatmeal, bacon…) that the lexical
heuristics could only band-aid one food at a time.

The mapping itself (query → fdc_id) is a curated artifact, so it lives in the
gitignored ``mappings/`` layer (baked into the deployed image like the food DB),
not the public tree. A miss falls through to the ranked search — the overlay only
*pins*, never blocks.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

_DEFAULT_PATH = Path(__file__).parent / "mappings" / "common_foods.json"


def _singularize(word: str) -> str:
    """Singularize one word so plural and singular names converge on one key.

    The agent's parse emits the singular ("10 almonds" → "almond") while a curated
    key may be plural ("almonds"); normalizing both sides to the singular makes them
    match. Handles -ies → -y (berries → berry), the -es plurals (tomatoes → tomato),
    and a bare trailing -s, leaving short words and -ss endings (e.g. an -us word
    like "asparagus") untouched — those still match because both sides transform
    identically.
    """
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    for suffix in ("oes", "ches", "shes", "xes", "sses", "zzes"):
        if len(word) > len(suffix) and word.endswith(suffix):
            return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def normalize(text: str) -> str:
    """The overlay key for a food name: lowercased, punctuation-stripped, collapsed,
    and singularized word-by-word so "almonds"/"almond" and "green beans"/"green
    bean" resolve to the same pinned food."""
    cleaned = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()
    return " ".join(_singularize(word) for word in cleaned.split())


@lru_cache(maxsize=1)
def load_overlay() -> dict[str, int]:
    """Load the curated ``normalized-name → fdc_id`` map (fail-soft empty if absent)."""
    path = Path(os.environ.get("DIETRACE_OVERLAY", _DEFAULT_PATH))
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {normalize(k): int(v) for k, v in data.items()}
    except Exception:
        return {}


def overlay_fdc_id(food: str, overlay: dict[str, int] | None = None) -> int | None:
    """The pinned ``fdc_id`` for *food* if it's a curated common food, else None."""
    table = load_overlay() if overlay is None else overlay
    return table.get(normalize(food))

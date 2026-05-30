"""Load eval cases from disk and upload them to Phoenix as a Dataset.

``load_cases`` reads and validates every ``*.json`` case under a directory;
``upload`` pushes them to a Phoenix Dataset via the injected client. The client
is injected so the call is testable offline. The exact ``create_dataset``
signature varies across Phoenix SDK versions; inputs/expected/
metadata are passed as parallel lists, which the runner can adapt if pinned.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from dietrace.evals.schema import EvalCase, load_case

DATASET_NAME = "dietrace-nutrition-v1"
DATASET_DESCRIPTION = (
    "DietTrace nutrition accuracy cases: USDA-grounded macros (and full-tier "
    "micros) for natural-language meals."
)


def load_cases(directory: str | Path) -> list[EvalCase]:
    """Load and validate every ``*.json`` eval case under *directory*, sorted."""
    return [load_case(path) for path in sorted(Path(directory).glob("*.json"))]


def _rows(cases: Iterable[EvalCase]) -> tuple[list[dict], list[dict], list[dict]]:
    """Split cases into parallel input / expected / metadata row lists."""
    inputs, expected, metadata = [], [], []
    for case in cases:
        inputs.append(case.input.model_dump())
        expected.append(case.expected.model_dump())
        metadata.append(case.metadata.model_dump())
    return inputs, expected, metadata


def upload(
    client: Any,
    cases: Iterable[EvalCase],
    *,
    name: str = DATASET_NAME,
    description: str = DATASET_DESCRIPTION,
) -> Any:
    """Create a Phoenix Dataset named *name* from *cases* via *client*."""
    inputs, expected, metadata = _rows(cases)
    return client.datasets.create_dataset(
        name=name,
        description=description,
        inputs=inputs,
        outputs=expected,
        metadata=metadata,
    )

"""The self-supervision demo orchestration.

``run_demo`` reproduces the Arize-track narrative as five injectable steps:
commit a deliberate regression to the nutrition instruction → run the evals →
let the supervisor detect it and open a PR → verify the PR carries a sensible
diff → clean up. The steps are injected so the flow is testable offline; the
``scripts/demo_regression.py`` entrypoint wires the live implementations.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Regress = Callable[[], Any]
RunEvals = Callable[[], int]
RunSupervisor = Callable[[], Any]
Verify = Callable[[Any], bool]
Cleanup = Callable[[], Any]


@dataclass
class DemoResult:
    """Summary of a self-supervision demo run."""

    experiments_run: int
    prs_opened: int
    verified: bool
    cleaned_up: bool


def run_demo(
    *,
    regress: Regress,
    run_evals: RunEvals,
    run_supervisor_fn: RunSupervisor,
    verify: Verify,
    cleanup: Cleanup,
) -> DemoResult:
    """Run the regression → evals → supervisor → verify → cleanup demo.

    *cleanup* always runs, even if an earlier step raises, so the repo is never
    left on the throwaway regression branch.
    """
    try:
        regress()
        experiments_run = run_evals()
        supervisor_run = run_supervisor_fn()
        prs_opened = len(supervisor_run.prs_opened)
        verified = verify(supervisor_run)
    finally:
        cleanup()

    return DemoResult(
        experiments_run=experiments_run,
        prs_opened=prs_opened,
        verified=verified,
        cleaned_up=True,
    )

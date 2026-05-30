"""The self-supervision demo runs its steps in order and always cleans up (7.3)."""

import pytest

from dietrace.demo import run_demo


class _SupervisorRun:
    def __init__(self, prs: int) -> None:
        self.prs_opened = [object()] * prs


def test_happy_path_runs_steps_in_order() -> None:
    calls: list[str] = []

    result = run_demo(
        regress=lambda: calls.append("regress"),
        run_evals=lambda: (calls.append("evals") or 2),
        run_supervisor_fn=lambda: (calls.append("supervisor") or _SupervisorRun(1)),
        verify=lambda run: (calls.append("verify") or True),
        cleanup=lambda: calls.append("cleanup"),
    )

    assert result.experiments_run == 2
    assert result.prs_opened == 1
    assert result.verified is True
    assert result.cleaned_up is True
    assert calls == ["regress", "evals", "supervisor", "verify", "cleanup"]


def test_cleanup_runs_even_when_a_step_fails() -> None:
    calls: list[str] = []

    def boom() -> int:
        raise RuntimeError("evals blew up")

    with pytest.raises(RuntimeError):
        run_demo(
            regress=lambda: None,
            run_evals=boom,
            run_supervisor_fn=lambda: _SupervisorRun(0),
            verify=lambda run: True,
            cleanup=lambda: calls.append("cleanup"),
        )

    assert calls == ["cleanup"]

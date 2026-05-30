"""run_supervisor opens a PR for a regressing case, fully mocked (5.6)."""

from dietrace.agents.supervisor.pr import PRResult
from dietrace.agents.supervisor.run import run_supervisor


class _FakeMCP:
    """Returns canned raw experiments (most-recent-first) for get_recent_experiments."""

    def __init__(self, raw: list[dict]) -> None:
        self._raw = raw

    async def get_recent_experiments(self, dataset_id: str, limit: int = 10) -> list[dict]:
        return self._raw


def _raw_exp(exp_id: str, score: float, example_id: str = "egg_large") -> dict:
    passed = score >= 0.5
    return {
        "id": exp_id,
        "name": "dietrace-nutrition",
        "runs": [
            {
                "id": f"{exp_id}-r",
                "datasetExampleId": example_id,
                "output": {"totals": []},
                "annotations": [{"score": score, "label": "pass" if passed else "fail"}],
            }
        ],
    }


def test_opens_one_pr_for_a_regression() -> None:
    # Most-recent-first: recent 0.4, older 0.9 → oldest-first [0.9, 0.4] → regressing.
    mcp = _FakeMCP([_raw_exp("e2", 0.4), _raw_exp("e1", 0.9)])
    opened: list[dict] = []

    def fake_open(**kwargs):
        opened.append(kwargs)
        return PRResult(pr_number=1, pr_url="https://x/pr/1", branch="supervisor/x", dry_run=False)

    run = run_supervisor(
        "ds1",
        mcp_client=mcp,
        _propose_fn=lambda **kwargs: "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-x\n+y\n",
        _open_pr_fn=fake_open,
    )

    assert run.experiments_read == 2
    assert len(run.regressions_found) == 1
    assert run.regressions_found[0].example_id == "egg_large"
    assert len(run.prs_opened) == 1
    assert opened[0]["case_id"] == "egg_large"


def test_no_pr_when_improving() -> None:
    # Most-recent-first: recent 0.9, older 0.4 → oldest-first [0.4, 0.9] → improving.
    # (Clear-cut for the heuristic, so no LLM judge / network is touched.)
    mcp = _FakeMCP([_raw_exp("e2", 0.9), _raw_exp("e1", 0.4)])

    def fake_open(**kwargs):  # pragma: no cover — must not be called
        raise AssertionError("open_pr should not run when there is no regression")

    run = run_supervisor(
        "ds1",
        mcp_client=mcp,
        _propose_fn=lambda **kwargs: "diff",
        _open_pr_fn=fake_open,
    )

    assert run.regressions_found == []
    assert run.prs_opened == []

"""open_pr builds a payload and drives the git sequence with subprocess mocked (5.4)."""

from dietrace.agents.supervisor.pr import _apply_diff_to_branch, _build_payload, open_pr

_DIFF = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-x\n+y\n"


class _FakeCompleted:
    stdout = "main\n"


def test_apply_diff_runs_branch_apply_push(tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _FakeCompleted()

    payload = _build_payload("egg_large", _DIFF, "scores fell")
    _apply_diff_to_branch(payload, tmp_path, _run=fake_run)

    joined = [" ".join(c) for c in calls]
    assert any("checkout -b supervisor/egg_large" in j for j in joined)
    assert any(j.startswith("git apply") for j in joined)
    assert any("push -u origin" in j for j in joined)


def test_open_pr_dry_run_creates_no_pr() -> None:
    result = open_pr("egg_large", _DIFF, "scores fell", dry_run=True)

    assert result.dry_run is True
    assert result.pr_number is None
    assert result.branch.startswith("supervisor/egg_large-")


def test_build_payload_titles_and_bodies_the_case() -> None:
    payload = _build_payload("egg_large", _DIFF, "scores fell")
    assert "egg_large" in payload.title
    assert "fix(nutrition)" in payload.title
    assert "scores fell" in payload.body
    assert _DIFF in payload.body

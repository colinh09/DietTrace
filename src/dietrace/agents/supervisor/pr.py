"""PR opener for the supervisor agent.

Given a diff and rationale, applies it on a fresh branch and opens a GitHub PR
via the REST API — human-in-the-loop, never auto-merged. Branch name format:
``supervisor/<case_id>-<timestamp>``.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_REPO = "colinh09/DietTrace"


@dataclass
class PRPayload:
    """The data that would be sent to open a PR."""

    branch: str
    title: str
    body: str
    diff: str
    base: str = "main"


@dataclass
class PRResult:
    """Result of opening a PR."""

    pr_number: int | None
    pr_url: str | None
    branch: str
    dry_run: bool


def _make_branch_name(case_id: str) -> str:
    ts = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%dT%H%M%S")
    safe_id = case_id.replace("/", "-").replace(" ", "-")[:40]
    return f"supervisor/{safe_id}-{ts}"


def _build_payload(
    case_id: str,
    diff: str,
    rationale: str,
    base: str = "main",
) -> PRPayload:
    branch = _make_branch_name(case_id)
    title = f"fix(nutrition): prompt patch for regressing case {case_id}"
    body = (
        f"## Regression detected\n\n"
        f"Case `{case_id}` was classified as regressing by the supervisor.\n\n"
        f"## Rationale\n\n{rationale}\n\n"
        f"## Proposed diff\n\n```diff\n{diff}\n```"
    )
    return PRPayload(branch=branch, title=title, body=body, diff=diff, base=base)


def _apply_diff_to_branch(
    payload: PRPayload,
    repo_root: Path,
    _run: object | None = None,
) -> None:
    """Create a branch, apply the diff, commit, push, then restore the original branch."""
    run = _run if _run is not None else subprocess.run  # type: ignore[assignment]

    result = run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    original_branch = result.stdout.strip() if hasattr(result, "stdout") else "main"

    try:
        run(
            ["git", "checkout", "-b", payload.branch],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", delete=False, dir=repo_root
        ) as f:
            f.write(payload.diff)
            patch_path = Path(f.name)
        try:
            run(
                ["git", "apply", str(patch_path)],
                cwd=repo_root,
                check=True,
                capture_output=True,
            )
        finally:
            patch_path.unlink(missing_ok=True)

        run(["git", "add", "-A"], cwd=repo_root, check=True, capture_output=True)
        run(
            ["git", "commit", "-m", payload.title],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        run(
            ["git", "push", "-u", "origin", payload.branch],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
    finally:
        run(
            ["git", "checkout", original_branch],
            cwd=repo_root,
            check=False,
            capture_output=True,
        )


def _open_github_pr(  # pragma: no cover — requires live GitHub API
    payload: PRPayload,
    repo: str,
    github_token: str,
) -> tuple[int, str]:
    """Open a PR via the GitHub REST API. Returns (pr_number, pr_url)."""
    import urllib.request

    body_data = json.dumps(
        {
            "title": payload.title,
            "body": payload.body,
            "head": payload.branch,
            "base": payload.base,
        }
    ).encode()

    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/pulls",
        data=body_data,
        headers={
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["number"], data["html_url"]


def open_pr(
    case_id: str,
    diff: str,
    rationale: str,
    *,
    repo: str | None = None,
    github_token: str | None = None,
    repo_root: Path | None = None,
    base: str = "main",
    dry_run: bool = False,
    _run: object | None = None,
) -> PRResult:
    """Open a GitHub PR proposing a prompt patch (human reviews before merge).

    Defaults: *repo* from ``GITHUB_REPOSITORY`` (else ``colinh09/DietTrace``),
    *github_token* from ``GITHUB_TOKEN``/``GH_TOKEN``, *repo_root* to this repo.
    ``dry_run=True`` prints the payload and touches neither git nor GitHub.
    """
    resolved_repo = repo or os.environ.get("GITHUB_REPOSITORY", _DEFAULT_REPO)
    resolved_root = repo_root or Path(__file__).parent.parent.parent.parent.parent

    payload = _build_payload(case_id=case_id, diff=diff, rationale=rationale, base=base)

    if dry_run:
        print(
            json.dumps(
                {
                    "branch": payload.branch,
                    "title": payload.title,
                    "body": payload.body,
                    "base": payload.base,
                },
                indent=2,
            )
        )
        return PRResult(pr_number=None, pr_url=None, branch=payload.branch, dry_run=True)

    token = github_token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
    if not token:
        raise RuntimeError("No GitHub token available. Set GITHUB_TOKEN or pass github_token=.")

    _apply_diff_to_branch(payload, resolved_root, _run=_run)  # pragma: no cover — live GitHub
    pr_number, pr_url = _open_github_pr(payload, resolved_repo, token)  # pragma: no cover
    return PRResult(  # pragma: no cover — live GitHub
        pr_number=pr_number, pr_url=pr_url, branch=payload.branch, dry_run=False
    )

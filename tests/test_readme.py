"""— README polish.

Encodes the done-criterion: the public README is tightened so a
reader gets clear run steps, the accuracy story, and the architecture — and carries
no AI attribution. Faithful to  (overview), §3 (architecture), §6 (eval suite),
and §7 (supervisor loop).
"""

import re
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def _text() -> str:
    assert README.exists(), "README.md missing at repo root"
    return README.read_text()


def _headings() -> list[str]:
    return [ln.strip() for ln in _text().splitlines() if ln.lstrip().startswith("##")]


def test_readme_present():
    """The public README exists and is non-empty."""
    assert README.exists(), "README.md missing at repo root"
    assert _text().strip(), "README.md is empty"


def test_run_steps_clear():
    """A single Run/Quickstart section gives copy-pasteable, fenced commands."""
    text = _text()
    headings = " ".join(_headings()).lower()
    assert "run" in headings or "quickstart" in headings, "no Run/Quickstart heading"
    # At least a couple of fenced code blocks so the steps are copy-pasteable.
    assert text.count("```") >= 4, "run steps should include fenced command blocks"


def test_run_steps_cover_backend_frontend_and_tests():
    """Run steps cover the API server, the web frontend, and how to verify (tests)."""
    text = _text().lower()
    # Backend API server.
    assert "uvicorn" in text, "run steps should show how to start the API server"
    # The Next.js web frontend lives in frontend/ — a reader must be told how to run it.
    assert "frontend" in text, "run steps should explain how to run the web frontend"
    # Verifiability is the whole point — show how to run the eval suite and the tests.
    assert "evals.runner" in text, "run steps should show how to run the eval suite"
    assert "pytest" in text, "run steps should show how to run the test suite"


def test_run_steps_use_repo_tooling():
    """Commands match the repo's actual tooling, not a stale alternative."""
    text = _text()
    # The repo is developed against a local virtualenv + python -m; don't ship a
    # toolchain (uv) the contributor docs never set up.
    assert "uv " not in text and "uv sync" not in text, "README references uv tooling"
    assert "python -m" in text, "run steps should use python -m invocations"


def test_architecture_section_present():
    """An Architecture section explains the pipeline and the self-supervision loop."""
    headings = " ".join(_headings()).lower()
    assert "architecture" in headings, "no Architecture heading"
    text = _text()
    # The mandated tool pipeline is shown in order.
    for stage in (
        "parse_meal",
        "search_nutrition",
        "estimate_portion",
        "log_entry",
        "check_against_goals",
    ):
        assert stage in text, f"architecture missing pipeline stage {stage!r}"
    # Phoenix is the medium between the agent and the supervisor.
    low = text.lower()
    assert "phoenix" in low, "architecture should name Phoenix as the observability medium"
    assert "supervisor" in low, "architecture should describe the supervisor loop"


def test_accuracy_story_present():
    """The accuracy story is concrete: USDA ground truth, numeric evals, the search/calc split."""
    headings = " ".join(_headings()).lower()
    assert "accuracy" in headings, "no Accuracy heading"
    low = _text().lower()
    assert "usda" in low, "accuracy story should cite USDA ground truth"
    assert "fdc_id" in low or "fdc id" in low, "accuracy story should mention pinned fdc ids"
    # The headline accuracy lesson: separate lookup from calculation.
    assert "search" in low and ("calcul" in low or "portion math" in low), (
        "accuracy story should explain the search/calculation split"
    )


def test_links_are_well_formed():
    """Markdown links resolve to a target (no empty parens)."""
    for label, target in re.findall(r"\[([^\]]+)\]\(([^)]*)\)", _text()):
        assert target.strip(), f"empty link target for {label!r}"


def test_no_ai_attribution():
    """Hard rule: the public README reads as Colin's own human work."""
    text = _text().lower()
    banned = ("claude", "anthropic", "copilot", "generated with", "co-authored", "openai", "gpt")
    for term in banned:
        assert term not in text, f"README.md contains banned attribution: {term!r}"

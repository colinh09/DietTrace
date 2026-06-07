"""— DEVPOST.md submission writeup.

Encodes the done-criterion: a DEVPOST.md at the repo root that
carries the hackathon-submission sections — problem, what it does, how it's built
(Gemini 3 + ADK + Phoenix + MCP), the self-supervision loop, the measured accuracy
before/after, challenges, and what's next — faithful to  sections 1, 3, 6, 7.
"""

from pathlib import Path

DEVPOST = Path(__file__).resolve().parents[1] / "DEVPOST.md"


def _text() -> str:
    assert DEVPOST.exists(), "DEVPOST.md missing at repo root"
    return DEVPOST.read_text()


def test_devpost_present():
    """The submission writeup exists at the repo root."""
    assert DEVPOST.exists(), "DEVPOST.md missing at repo root"
    assert _text().strip(), "DEVPOST.md is empty"


def test_required_sections_present():
    """All submission beats are covered as headings."""
    text = _text().lower()
    for needle in (
        "## problem",
        "## what it does",
        "## how",  # "How it's built"
        "## self-supervision",
        "## accuracy",  # measured before/after
        "## challenges",
        "## what's next",
    ):
        assert needle in text, f"DEVPOST.md missing section heading: {needle!r}"


def test_built_with_stack_named():
    """The 'how it's built' story names the required stack pieces."""
    text = _text()
    for term in ("Gemini 3", "ADK", "Phoenix", "MCP"):
        assert term in text, f"DEVPOST.md does not mention {term!r}"


def test_self_supervision_loop_described():
    """The corrector→supervisor→gate loop is spelled out.

    The supervisor decides per meal, the corrector generalizes, and a deterministic
    gate ships a preference change only if it holds the USDA floor and improves the
    user's held-out meals — over the Phoenix MCP server.
    """
    text = _text().lower()
    for term in ("corrector", "supervisor", "gate", "retune", "dataset", "held-out"):
        assert term in text, f"self-supervision loop missing {term!r}"


def test_accuracy_before_after_present():
    """The accuracy story carries a measured before/after framing."""
    text = _text().lower()
    assert "before" in text and "after" in text, "missing before/after accuracy framing"
    # A concrete, USDA-grounded measurement surface is named.
    assert "usda" in text, "accuracy story should reference USDA ground truth"
    assert "%" in _text(), "accuracy story should carry a numeric (percentage) measure"


def test_no_ai_attribution():
    """Hard rule: the public writeup reads as Colin's own human work."""
    text = _text().lower()
    banned = ("claude", "anthropic", "copilot", "generated with", "co-authored", "openai", "gpt")
    for term in banned:
        assert term not in text, f"DEVPOST.md contains banned attribution: {term!r}"

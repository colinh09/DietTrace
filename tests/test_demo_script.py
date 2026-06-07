"""— docs/demo_script.md demo walkthrough.

Encodes the done-criterion: a ~3-minute demo walkthrough
sectioned by beat with timings, tracing the project's headline narrative
: log a meal → see the trace → show the Phoenix
experiment → the supervisor retunes and the gate ships a personalization.
"""

import re
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1] / "docs" / "demo_script.md"

# A timing cue like `0:00`, `1:30`, `12:05` — minute:second.
_TIMING = re.compile(r"\b\d{1,2}:[0-5]\d\b")


def _text() -> str:
    assert DEMO.exists(), "docs/demo_script.md missing"
    return DEMO.read_text()


def test_demo_script_present():
    """The demo walkthrough exists and is non-empty."""
    assert DEMO.exists(), "docs/demo_script.md missing"
    assert _text().strip(), "docs/demo_script.md is empty"


def test_sectioned_by_beat():
    """The walkthrough is broken into named beats (markdown headings)."""
    beats = [ln for ln in _text().splitlines() if ln.lstrip().startswith("##")]
    assert len(beats) >= 4, f"expected >=4 beat sections, found {len(beats)}"


def test_beats_carry_timings():
    """Every beat heading carries a minute:second timing cue."""
    beat_headings = [
        ln for ln in _text().splitlines() if re.match(r"^#{2,3}\s", ln.strip())
    ]
    assert beat_headings, "no beat headings found"
    for heading in beat_headings:
        assert _TIMING.search(heading), f"beat heading lacks a timing: {heading!r}"


def test_narrative_beats_covered():
    """The four headline beats from the task are each present."""
    text = _text().lower()
    assert "log" in text and "meal" in text, "missing the log-a-meal beat"
    assert "trace" in text, "missing the see-the-trace beat"
    assert "phoenix" in text and "experiment" in text, "missing the Phoenix experiment beat"
    assert "supervisor" in text and ("retune" in text or "gate" in text), (
        "missing the supervisor retune / gate beat"
    )


def test_runtime_about_three_minutes():
    """The script is paced for ~3 minutes: latest timing lands in [2:30, 3:30]."""
    timings = _TIMING.findall(_text())
    assert timings, "no timing cues found"
    seconds = [int(m) * 60 + int(s) for m, s in (t.split(":") for t in timings)]
    assert 150 <= max(seconds) <= 210, f"final cue {max(seconds)}s outside ~3-minute window"


def test_no_ai_attribution():
    """Hard rule: the walkthrough reads as Colin's own human work."""
    text = _text().lower()
    banned = ("claude", "anthropic", "copilot", "generated with", "co-authored", "openai", "gpt")
    for term in banned:
        assert term not in text, f"docs/demo_script.md contains banned attribution: {term!r}"

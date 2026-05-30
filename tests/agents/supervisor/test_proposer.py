"""propose_patch returns a validated unified diff or rejects prose (5.3)."""

import pytest

from dietrace.agents.supervisor.proposer import propose_patch

_GOOD_DIFF = (
    "--- a/src/dietrace/agents/nutrition/instruction.md\n"
    "+++ b/src/dietrace/agents/nutrition/instruction.md\n"
    "@@ -1 +1 @@\n"
    "-old line\n"
    "+new line\n"
)


def _instruction(tmp_path) -> object:
    path = tmp_path / "instruction.md"
    path.write_text("old line\n")
    return path


def test_returns_validated_diff(tmp_path) -> None:
    diff = propose_patch(
        "egg_large", "one egg", "accurate macros", "score trend", "trace",
        instruction_file=_instruction(tmp_path),
        _llm_fn=lambda prompt: _GOOD_DIFF,
    )
    assert "@@" in diff and diff.startswith("---")


def test_rejects_prose(tmp_path) -> None:
    with pytest.raises(ValueError):
        propose_patch(
            "egg_large", "one egg", "accurate macros", "score trend", "trace",
            instruction_file=_instruction(tmp_path),
            _llm_fn=lambda prompt: "Sorry, I cannot produce a diff.",
        )


def test_strips_markdown_fences(tmp_path) -> None:
    fenced = f"```diff\n{_GOOD_DIFF}```\n"
    diff = propose_patch(
        "egg_large", "one egg", "accurate macros", "score trend", "trace",
        instruction_file=_instruction(tmp_path),
        _llm_fn=lambda prompt: fenced,
    )
    assert not diff.strip().startswith("```")
    assert "@@" in diff

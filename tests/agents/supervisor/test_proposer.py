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


def test_strips_prose_wrapped_fences(tmp_path) -> None:
    """A fenced diff surrounded by chatter must come back as the diff alone —
    no prose and no fence markers reach ``git apply``."""
    wrapped = f"Sure! Here is the fix:\n\n```diff\n{_GOOD_DIFF}```\n\nThat should do it.\n"
    diff = propose_patch(
        "egg_large", "one egg", "accurate macros", "score trend", "trace",
        instruction_file=_instruction(tmp_path),
        _llm_fn=lambda prompt: wrapped,
    )
    assert "```" not in diff
    assert "Here is the fix" not in diff
    assert "That should do it" not in diff
    assert diff.lstrip().startswith("--- a/")
    assert "@@" in diff


def test_keeps_fenced_content_lines_inside_diff(tmp_path) -> None:
    """A diff that legitimately edits backtick-fenced prompt lines (prefixed by
    space/+/-) must survive — only column-zero fences are wrapper delimiters."""
    diff_with_fences = (
        "--- a/src/dietrace/agents/nutrition/instruction.md\n"
        "+++ b/src/dietrace/agents/nutrition/instruction.md\n"
        "@@ -1,3 +1,3 @@\n"
        " ```\n"
        "-old line\n"
        "+new line\n"
        " ```\n"
    )
    fenced = f"```diff\n{diff_with_fences}```\n"
    diff = propose_patch(
        "egg_large", "one egg", "accurate macros", "score trend", "trace",
        instruction_file=_instruction(tmp_path),
        _llm_fn=lambda prompt: fenced,
    )
    assert diff.count("```") == 2  # the two context-line fences, prefixed by a space
    assert " ```\n" in diff
    assert diff.lstrip().startswith("--- a/")

"""propose_patch returns a validated unified diff or rejects prose (5.3).

Also pins _truncate_instruction: short text passes through, long text is
truncated at the char limit with a "... [truncated]" sentinel and a UserWarning,
and propose_patch itself still succeeds when given an oversized instruction file.
"""

import warnings

import pytest

from dietrace.agents.supervisor.proposer import (
    _MAX_INSTRUCTION_CHARS,
    _truncate_instruction,
    propose_patch,
)

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


# ---------------------------------------------------------------------------
# _truncate_instruction: the oversized-prompt guard
#
# All existing tests pass a tiny instruction file ("old line\n"), so the
# truncation path — including the character-limit clamp, the "... [truncated]"
# sentinel, and the UserWarning — was never reached by any test.  A broken
# truncation lets an arbitrarily large instruction file reach the LLM prompt
# intact, potentially blowing the context window silently.
# ---------------------------------------------------------------------------


def test_truncate_instruction_short_text_unchanged() -> None:
    """Text within the limit is returned unchanged."""
    text = "a" * (_MAX_INSTRUCTION_CHARS - 1)
    assert _truncate_instruction(text) == text


def test_truncate_instruction_exact_limit_unchanged() -> None:
    """Text at exactly the limit is not truncated (the guard is ≤, not <)."""
    text = "x" * _MAX_INSTRUCTION_CHARS
    result = _truncate_instruction(text)
    assert result == text
    assert "truncated" not in result


def test_truncate_instruction_long_text_cut_at_limit() -> None:
    """Text exceeding the limit is cut at _MAX_INSTRUCTION_CHARS characters."""
    text = "y" * (_MAX_INSTRUCTION_CHARS + 500)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = _truncate_instruction(text)
    # The first _MAX_INSTRUCTION_CHARS characters are preserved verbatim.
    assert result.startswith("y" * _MAX_INSTRUCTION_CHARS)


def test_truncate_instruction_long_text_ends_with_sentinel() -> None:
    """Truncated output ends with the '... [truncated]' sentinel."""
    text = "z" * (_MAX_INSTRUCTION_CHARS + 1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = _truncate_instruction(text)
    assert result.endswith("\n... [truncated]")


def test_truncate_instruction_emits_user_warning() -> None:
    """Truncation issues a UserWarning naming the char count and the limit."""
    text = "a" * (_MAX_INSTRUCTION_CHARS + 100)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _truncate_instruction(text)
    assert caught, "expected a UserWarning but none was raised"
    assert issubclass(caught[0].category, UserWarning)
    msg = str(caught[0].message)
    assert str(len(text)) in msg
    assert str(_MAX_INSTRUCTION_CHARS) in msg


def test_propose_patch_with_oversized_instruction_still_succeeds(tmp_path) -> None:
    """When the instruction file exceeds the limit, propose_patch truncates it
    and still returns a valid diff (the LLM mock is called with the truncated text)."""
    path = tmp_path / "instruction.md"
    path.write_text("x" * (_MAX_INSTRUCTION_CHARS + 200) + "\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        diff = propose_patch(
            "egg_large", "one egg", "accurate macros", "score trend", "trace",
            instruction_file=path,
            _llm_fn=lambda prompt: _GOOD_DIFF,
        )
    assert "@@" in diff and diff.startswith("---")

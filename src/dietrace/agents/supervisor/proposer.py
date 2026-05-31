"""Patch proposer for the supervisor agent.

Given a regressing eval case and its failing trace, generates a proposed unified
diff against the nutrition agent's instruction document. The LLM is asked for raw
diff text only; the result is fence-stripped and validated so prose never reaches
``git apply``.
"""

from __future__ import annotations

import textwrap
import warnings
from pathlib import Path

_INSTRUCTION_REL = "src/dietrace/agents/nutrition/parse_prompt.md"
_MAX_INSTRUCTION_CHARS = 8000


def _instruction_path() -> Path:
    """Return the absolute path to the meal-parsing prompt — the generative step
    that drives parse accuracy, so it is the artifact worth fixing on a regression."""
    return Path(__file__).parent.parent / "nutrition" / "parse_prompt.md"


def _build_prompt(
    example_id: str,
    case_input: str,
    case_expected: str,
    agent_output: str,
    trace_summary: str,
    instruction_text: str,
) -> str:
    return textwrap.dedent(f"""
        You are a prompt-engineering assistant reviewing a failing eval case for the
        DietTrace nutrition agent. The agent parses a natural-language meal into
        food items, then deterministically looks up and totals their macros; the
        prompt below drives that parse step, and this case regressed on accuracy.

        ## Failing case

        Case ID      : {example_id}
        Input        : {case_input}
        Expected     : {case_expected}
        Agent output : {agent_output}
        Trace summary: {trace_summary}

        ## Current meal-parsing prompt

        ```
        {instruction_text}
        ```

        ## Your task

        Propose a minimal change to the meal-parsing prompt that would fix this
        regression without breaking other behavior. Output ONLY a unified diff
        (--- / +++ / @@ header lines, then context and change lines). Do NOT output
        any explanation, prose, or markdown fencing — raw diff text only. The diff
        must apply cleanly against the instruction document shown above.

        Use "a/{_INSTRUCTION_REL}" and "b/{_INSTRUCTION_REL}" as the file paths in
        the --- and +++ lines.
    """).strip()


def _call_llm(prompt: str) -> str:  # pragma: no cover — requires live Gemini
    from google import genai

    from dietrace.llm.config import GEMINI_LOCATION, GEMINI_MODEL, GEMINI_PROJECT

    client = genai.Client(vertexai=True, project=GEMINI_PROJECT, location=GEMINI_LOCATION)
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return response.text.strip()


def _truncate_instruction(text: str, max_chars: int = _MAX_INSTRUCTION_CHARS) -> str:
    """Truncate instruction text that would overflow the LLM context window."""
    if len(text) <= max_chars:
        return text
    warnings.warn(
        f"instruction.md is {len(text)} chars, exceeding the {max_chars}-char limit; "
        "truncating before embedding in LLM prompt.",
        stacklevel=3,
    )
    return text[:max_chars] + "\n... [truncated]"


def _validate_diff(diff: str) -> None:
    """Raise ValueError if *diff* is missing required unified-diff header lines."""
    has_from = any(line.startswith("---") for line in diff.splitlines())
    has_to = any(line.startswith("+++") for line in diff.splitlines())
    has_hunk = any(line.startswith("@@") for line in diff.splitlines())
    if not (has_from and has_to and has_hunk):
        raise ValueError(
            "LLM returned prose instead of a unified diff: "
            "missing one or more of '---', '+++', '@@' header lines.\n"
            f"Raw output (first 200 chars): {diff[:200]!r}"
        )


def _is_fence(line: str) -> bool:
    """A wrapper fence is a column-zero ```` ``` ````; diff body lines are prefixed
    with a space/+/- so backticks inside the diff never match here."""
    return line.rstrip("\r\n").startswith("```")


def _strip_fences(text: str) -> str:
    """Return the diff with any markdown code fence wrapper removed.

    The LLM is asked for raw diff text, but often wraps it in a ```` ```diff ````
    block and surrounds that with prose ("Here is the fix: …"). When a column-zero
    fence is present, return only the content of the first fenced block so neither
    the fence markers nor the surrounding chatter reach ``git apply``. With no
    fence the text is returned unchanged (and validated downstream)."""
    lines = text.splitlines(keepends=True)
    opens = [i for i, line in enumerate(lines) if _is_fence(line)]
    if not opens:
        return text
    start = opens[0]
    closes = [i for i in opens if i > start]
    end = closes[0] if closes else len(lines)
    return "".join(lines[start + 1 : end])


def propose_patch(
    example_id: str,
    case_input: str,
    case_expected: str,
    agent_output: str,
    trace_summary: str,
    *,
    instruction_file: Path | None = None,
    _llm_fn: object | None = None,
) -> str:
    """Generate a unified diff that fixes a regressing eval case.

    *instruction_file* and *_llm_fn* are injectable for tests. Returns a unified
    diff string suitable for ``git apply``; raises ValueError if the model
    returned prose instead of a diff.
    """
    path = instruction_file if instruction_file is not None else _instruction_path()
    instruction_text = _truncate_instruction(path.read_text())

    prompt = _build_prompt(
        example_id=example_id,
        case_input=case_input,
        case_expected=case_expected,
        agent_output=agent_output,
        trace_summary=trace_summary,
        instruction_text=instruction_text,
    )

    call = _llm_fn if _llm_fn is not None else _call_llm
    raw = call(prompt)
    diff = _strip_fences(raw)
    _validate_diff(diff)
    return diff

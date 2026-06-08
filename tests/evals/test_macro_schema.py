"""Unit tests for src/dietrace/evals/macro_schema.py.

These pin the MacroEvalCase JSON contract: every file
under ``evals/dataset/macros/`` is an ``{input, expected, metadata}`` object whose
``input`` is a ``MacroProfile``-shaped dict, ``expected`` is a set of acceptable
target ranges per macro, and ``metadata`` documents the case. The module's
documented contract is that every model is ``extra="forbid"`` so a mistyped field
in a hand-authored case fails loudly rather than being silently ignored — the
sibling ``test_schema.py`` pins this for ``EvalCase`` but nothing pins it here, so
a removed ``extra="forbid"`` (or a broken ``load_macro_case``) would silently
weaken the macro eval suite with no failing test. No DB or network is touched.
"""

import json

import pytest
from pydantic import ValidationError

from dietrace.evals.macro_schema import (
    MacroCaseMetadata,
    MacroEvalCase,
    MacroEvalInput,
    MacroExpectedTargets,
    load_macro_case,
)

_CASE = {
    "input": {
        "age": 30,
        "sex": "male",
        "height_cm": 180.0,
        "weight_kg": 80.0,
        "activity": "moderate",
        "goal": "maintain",
    },
    "expected": {
        "kcal_min": 2400.0,
        "kcal_max": 2800.0,
        "protein_g_min": 120.0,
        "protein_g_max": 200.0,
        "fat_g_min": 60.0,
        "fat_g_max": 100.0,
        "carb_g_min": 200.0,
        "carb_g_max": 350.0,
    },
    "metadata": {"source": "Mifflin-St Jeor", "notes": "baseline maintenance"},
}


def test_macro_case_validates_from_json() -> None:
    """A well-formed case validates and exposes its input, ranges, and metadata."""
    case = MacroEvalCase.model_validate(_CASE)

    assert case.input.age == 30
    assert case.input.sex == "male"
    assert case.expected.kcal_min == 2400.0
    assert case.expected.carb_g_max == 350.0
    assert case.metadata.source == "Mifflin-St Jeor"


def test_macro_input_optional_fields_default() -> None:
    """``preference`` and ``ai_help`` default rather than being required."""
    case = MacroEvalCase.model_validate(_CASE)

    assert case.input.preference is None
    assert case.input.ai_help is False


def test_macro_metadata_optional_fields_default() -> None:
    """Metadata documents the case but every field is optional."""
    bare = json.loads(json.dumps(_CASE))
    bare["metadata"] = {}

    case = MacroEvalCase.model_validate(bare)

    assert case.metadata.source is None
    assert case.metadata.notes is None


def test_load_macro_case_reads_and_validates_a_json_file(tmp_path) -> None:
    """load_macro_case round-trips a JSON file on disk into a validated case."""
    path = tmp_path / "male_moderate_maintain.json"
    path.write_text(json.dumps(_CASE))

    case = load_macro_case(path)

    assert isinstance(case, MacroEvalCase)
    assert case.input.goal == "maintain"
    assert case.expected.kcal_max == 2800.0


def test_load_macro_case_raises_on_malformed_file(tmp_path) -> None:
    """A hand-authored case that violates the schema fails loudly on load."""
    bad = json.loads(json.dumps(_CASE))
    del bad["expected"]["kcal_min"]
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(bad))

    with pytest.raises(ValidationError):
        load_macro_case(path)


def test_expected_requires_every_range() -> None:
    """Each macro range bound is mandatory — scoring can't dispatch without it."""
    bad = json.loads(json.dumps(_CASE))
    del bad["expected"]["protein_g_max"]

    with pytest.raises(ValidationError):
        MacroEvalCase.model_validate(bad)


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [("sex", "other"), ("activity", "extreme"), ("goal", "recomp")],
)
def test_input_literals_reject_unknown_values(field: str, bad_value: str) -> None:
    """sex/activity/goal are constrained enums — an out-of-set value is rejected."""
    bad = json.loads(json.dumps(_CASE))
    bad["input"][field] = bad_value

    with pytest.raises(ValidationError):
        MacroEvalCase.model_validate(bad)


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (MacroEvalInput, _CASE["input"]),
        (MacroExpectedTargets, _CASE["expected"]),
        (MacroCaseMetadata, _CASE["metadata"]),
    ],
)
def test_models_forbid_extra_fields(model, kwargs) -> None:
    """A stray field is a typo, not silently dropped — every model is strict.

    This pins the module's documented ``extra="forbid"`` contract: without it, a
    misspelled bound (e.g. ``protein_g_mn``) in a hand-authored macro case would
    be ignored and the plan scored against a missing range."""
    with pytest.raises(ValidationError):
        model(**{**kwargs, "typoed_field": "x"})


def test_macro_eval_case_forbids_extra_top_level_field() -> None:
    """The top-level case object is strict too — a misplaced key fails loudly."""
    bad = json.loads(json.dumps(_CASE))
    bad["inputs"] = bad["input"]  # plural typo of "input"

    with pytest.raises(ValidationError):
        MacroEvalCase.model_validate(bad)

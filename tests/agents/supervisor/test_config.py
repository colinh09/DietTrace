"""Supervisor config loads conservative-by-default and honors env overrides."""

from __future__ import annotations

from dietrace.agents.supervisor.config import (
    CONSERVATIVE,
    DEFAULT_MAX_RUNS_PER_DAY,
    DEFAULT_MIN_NEW_DATASET_POINTS,
    DEFAULT_MIN_NEW_FEEDBACK,
    POWERFUL,
    load_supervisor_config,
)

_ENV_KEYS = (
    "DIETRACE_SUPERVISOR_MODE",
    "DIETRACE_MIN_NEW_FEEDBACK",
    "DIETRACE_MIN_NEW_DATASET_POINTS",
    "DIETRACE_MAX_RUNS_PER_DAY",
)


def _clear(monkeypatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults_are_conservative(monkeypatch) -> None:
    _clear(monkeypatch)
    cfg = load_supervisor_config()
    assert cfg.mode == CONSERVATIVE
    assert cfg.is_powerful is False
    assert cfg.min_new_feedback == DEFAULT_MIN_NEW_FEEDBACK
    assert cfg.min_new_dataset_points == DEFAULT_MIN_NEW_DATASET_POINTS
    assert cfg.max_runs_per_day == DEFAULT_MAX_RUNS_PER_DAY


def test_env_overrides_parse(monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("DIETRACE_SUPERVISOR_MODE", "POWERFUL")  # case-insensitive
    monkeypatch.setenv("DIETRACE_MIN_NEW_FEEDBACK", "1")
    monkeypatch.setenv("DIETRACE_MIN_NEW_DATASET_POINTS", "2")
    monkeypatch.setenv("DIETRACE_MAX_RUNS_PER_DAY", "50")
    cfg = load_supervisor_config()
    assert cfg.mode == POWERFUL and cfg.is_powerful is True
    assert cfg.min_new_feedback == 1
    assert cfg.min_new_dataset_points == 2
    assert cfg.max_runs_per_day == 50


def test_unknown_mode_falls_back_to_conservative(monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("DIETRACE_SUPERVISOR_MODE", "turbo")
    assert load_supervisor_config().mode == CONSERVATIVE


def test_unparseable_int_falls_back_to_default(monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("DIETRACE_MIN_NEW_FEEDBACK", "lots")
    assert load_supervisor_config().min_new_feedback == DEFAULT_MIN_NEW_FEEDBACK

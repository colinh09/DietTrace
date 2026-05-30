"""Smoke tests — the package imports and core config defaults are sane."""

import dietrace
from dietrace.llm import config


def test_version():
    assert dietrace.__version__ == "0.1.0"


def test_model_defaults_to_gemini_3():
    # The hackathon requires a Gemini 3 model; the default must not regress to 2.x.
    assert config.GEMINI_MODEL.startswith("gemini-3")


def test_env_prefix_is_dietrace():
    assert config.GEMINI_LOCATION  # resolved without raising under pytest

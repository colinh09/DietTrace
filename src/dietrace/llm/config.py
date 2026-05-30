"""Gemini configuration constants resolved from environment variables.

The model defaults to Gemini 3 — the hackathon requires a Gemini 3 model, so the
default is pinned high and remains env-overridable.
"""

import os
import sys

# Gemini 3 by default. Override with DIETRACE_GEMINI_MODEL.
GEMINI_MODEL: str = os.environ.get("DIETRACE_GEMINI_MODEL", "gemini-3-pro-preview")
GEMINI_LOCATION: str = os.environ.get("DIETRACE_GEMINI_LOCATION", "us-central1")

_project = os.environ.get("DIETRACE_GEMINI_PROJECT", "")
# True during pytest collection AND execution (PYTEST_CURRENT_TEST is only set
# during execution, so also check whether pytest is imported).
_in_test = "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules

if not _project and not _in_test:
    raise RuntimeError(
        "DIETRACE_GEMINI_PROJECT env var is required. Set it to your GCP project ID."
    )

GEMINI_PROJECT: str = _project

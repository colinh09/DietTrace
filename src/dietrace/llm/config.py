"""Gemini configuration constants resolved from environment variables.

The model defaults to Gemini 3 — the hackathon requires a Gemini 3 model, so the
default is pinned high and remains env-overridable.
"""

import os
import sys

# Gemini 3 by default. Override with DIETRACE_GEMINI_MODEL.
GEMINI_MODEL: str = os.environ.get("DIETRACE_GEMINI_MODEL", "gemini-3.1-pro-preview")
# Gemini 3 preview models are served from the "global" location on Vertex — regional
# endpoints (e.g. us-central1) return 404 for them.
GEMINI_LOCATION: str = os.environ.get("DIETRACE_GEMINI_LOCATION", "global")

_project = os.environ.get("DIETRACE_GEMINI_PROJECT", "")
# True during pytest collection AND execution (PYTEST_CURRENT_TEST is only set
# during execution, so also check whether pytest is imported).
_in_test = "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules

if not _project and not _in_test:
    raise RuntimeError(
        "DIETRACE_GEMINI_PROJECT env var is required. Set it to your GCP project ID."
    )

GEMINI_PROJECT: str = _project

# Google ADK's Gemini wrapper picks its backend (Vertex vs Developer API) from
# Google's standard env vars, not from an explicit client — so the agent's
# orchestrating model would otherwise default to the Developer API and fail on a
# missing key. Mirror our config into those vars so the whole agent uses Vertex.
# Guarded on GEMINI_PROJECT so tests (no project set) never touch them; setdefault
# so an explicit override still wins.
if GEMINI_PROJECT:
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", GEMINI_PROJECT)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", GEMINI_LOCATION)

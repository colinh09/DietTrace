"""Anonymous per-user identity for the API (the per-user memory layer, ).

DietTrace personalizes from a user's own corrections, so every meal and correction
is scoped to a user. There is no login: the frontend mints a random id on first
visit and sends it as the ``X-DietTrace-User`` header. When the header is absent
(curl, health checks, the very first paint) requests fall back to a shared
``demo`` user, so nothing breaks — they just share one bucket.
"""

from __future__ import annotations

from fastapi import Header

# The bucket for requests that don't carry an id yet (anonymous/demo).
DEMO_USER = "demo"


def current_user(x_diettrace_user: str | None = Header(default=None)) -> str:
    """Resolve the calling user from the ``X-DietTrace-User`` header (FastAPI dep)."""
    user = (x_diettrace_user or "").strip()
    return user or DEMO_USER

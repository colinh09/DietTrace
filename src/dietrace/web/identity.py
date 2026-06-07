"""Per-user identity for the API (the per-user memory layer, ).

Every meal and correction is scoped to a user. Two identity sources, in priority:

1. **Firebase Auth** — a signed-in user (Google) sends a Firebase ID token as
   ``Authorization: Bearer <token>``. We verify it against the Firebase project
   and key the user by their stable Firebase uid, so their history follows them
   across devices.
2. **Anonymous** — when there's no valid token (Firebase not configured, or a
   quick anonymous visitor), the frontend sends a random id in the
   ``X-DietTrace-User`` header. Absent that too, requests share the ``demo``
   bucket so nothing breaks (curl, health checks, the very first paint).

Token verification is fail-soft: any error (no project configured, expired or
forged token, offline cert fetch) falls through to the anonymous path rather
than 500-ing, so the app always works even with Firebase switched off.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Header

# The bucket for requests that don't carry an id yet (anonymous/demo).
DEMO_USER = "demo"


def _firebase_project() -> str | None:
    """The Firebase project id used as the ID-token audience (env-configured)."""
    return (
        os.environ.get("DIETRACE_FIREBASE_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("DIETRACE_GEMINI_PROJECT")
        or None
    )


def _default_verify(token: str, project: str) -> dict[str, Any] | None:
    """Verify a Firebase ID *token* against *project*; return its claims or None.

    Uses google-auth's Firebase verifier (checks signature against Google's
    public certs and that the audience matches the project). Network/cert errors
    return None so the caller falls back to anonymous.
    """
    try:
        from google.auth.transport import requests as g_requests
        from google.oauth2 import id_token as g_id_token

        claims = g_id_token.verify_firebase_token(
            token, g_requests.Request(), audience=project
        )
        return claims if isinstance(claims, dict) else None
    except Exception:
        return None


# Indirection so tests can substitute a fake verifier (no live network / certs).
verify_token = _default_verify


def _firebase_uid(authorization: str | None) -> str | None:
    """The verified Firebase uid from a ``Bearer`` *authorization* header, or None."""
    if not authorization:
        return None
    scheme, _, raw = authorization.partition(" ")
    if scheme.lower() != "bearer" or not raw.strip():
        return None
    project = _firebase_project()
    if not project:
        return None
    claims = verify_token(raw.strip(), project)
    if not claims:
        return None
    uid = claims.get("sub") or claims.get("user_id")
    return str(uid) if uid else None


def current_user(
    authorization: str | None = Header(default=None),
    x_diettrace_user: str | None = Header(default=None),
) -> str:
    """Resolve the calling user (FastAPI dep): a verified Firebase uid if present,
    else the anonymous ``X-DietTrace-User`` id, else the shared ``demo`` bucket."""
    uid = _firebase_uid(authorization)
    if uid:
        return uid
    user = (x_diettrace_user or "").strip()
    return user or DEMO_USER

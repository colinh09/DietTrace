"""current_user resolves a Firebase uid (Bearer token) or the anonymous header.

Verification is mocked — no live Google cert fetch — and the priority/fallback
rules are pinned: a valid token wins, an invalid/absent one falls back to the
anonymous ``X-DietTrace-User`` id, then to the shared ``demo`` bucket.
"""

from __future__ import annotations

import dietrace.web.identity as identity
from dietrace.web.identity import DEMO_USER, current_user


def test_no_headers_falls_back_to_demo() -> None:
    assert current_user(authorization=None, x_diettrace_user=None) == DEMO_USER


def test_anonymous_header_is_used_when_no_token() -> None:
    assert current_user(authorization=None, x_diettrace_user="anon-123") == "anon-123"


def test_valid_bearer_token_resolves_to_firebase_uid(monkeypatch) -> None:
    monkeypatch.setenv("DIETRACE_FIREBASE_PROJECT", "diettrace")
    monkeypatch.setattr(identity, "verify_token", lambda tok, proj: {"sub": "fb-uid-9"})

    # The verified uid takes precedence over the anonymous header.
    user = current_user(authorization="Bearer good.token", x_diettrace_user="anon-123")
    assert user == "fb-uid-9"


def test_invalid_token_falls_back_to_anonymous(monkeypatch) -> None:
    monkeypatch.setenv("DIETRACE_FIREBASE_PROJECT", "diettrace")
    monkeypatch.setattr(identity, "verify_token", lambda tok, proj: None)  # rejected

    user = current_user(authorization="Bearer forged", x_diettrace_user="anon-123")
    assert user == "anon-123"


def test_bearer_token_ignored_when_no_project_configured(monkeypatch) -> None:
    monkeypatch.delenv("DIETRACE_FIREBASE_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("DIETRACE_GEMINI_PROJECT", raising=False)
    # Even a "valid" verifier is never consulted without an audience project.
    called = {"n": 0}

    def _verify(tok, proj):  # pragma: no cover - asserted not called
        called["n"] += 1
        return {"sub": "x"}

    monkeypatch.setattr(identity, "verify_token", _verify)
    user = current_user(authorization="Bearer t", x_diettrace_user="anon-123")
    assert user == "anon-123"
    assert called["n"] == 0


def test_non_bearer_authorization_is_ignored(monkeypatch) -> None:
    monkeypatch.setenv("DIETRACE_FIREBASE_PROJECT", "diettrace")
    monkeypatch.setattr(identity, "verify_token", lambda tok, proj: {"sub": "should-not"})
    user = current_user(authorization="Basic abc123", x_diettrace_user=None)
    assert user == DEMO_USER


def test_real_verifier_is_fail_soft_on_bad_token(monkeypatch) -> None:
    """The real verifier never raises — a malformed token returns None."""
    monkeypatch.setenv("DIETRACE_FIREBASE_PROJECT", "diettrace")
    # identity.verify_token is the real _default_verify here (not patched); a junk
    # token must fail-soft to None and fall back, not 500.
    user = current_user(authorization="Bearer not-a-real-jwt", x_diettrace_user="anon-9")
    assert user == "anon-9"

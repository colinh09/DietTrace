"""Reset module-level caches between web tests for isolation."""

import pytest

import dietrace.web.accuracy as accuracy_mod


@pytest.fixture(autouse=True)
def _reset_accuracy_base_cache():
    """Reset the base seeding snapshot before each test so cache state from a prior
    test cannot influence the next one."""
    accuracy_mod._base_snapshot = None
    yield
    accuracy_mod._base_snapshot = None

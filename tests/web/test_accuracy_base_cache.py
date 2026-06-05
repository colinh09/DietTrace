"""— cache the static base seeding accuracy numbers.

The USDA experiment story (baseline → current measured numbers) never changes between
Phoenix runs.  Caching the computed base report avoids re-running _measured_macro_scores
on every request, so the modal opens instantly even when the live Phoenix fetch is
slow or unreachable.
"""

from __future__ import annotations

import dietrace.web.accuracy as accuracy_mod
from dietrace.web.accuracy import accuracy_report


def _no_live():
    return None


# ---------------------------------------------------------------------------
# base cache correctness
# ---------------------------------------------------------------------------


def test_base_report_source_is_measured_on_first_cold_call() -> None:
    """First call with no live data computes from _BASELINE/_CURRENT (source='measured')."""
    accuracy_mod._base_snapshot = None  # cold cache
    report = accuracy_report(fetch=_no_live)
    assert report["source"] == "measured"


def test_base_report_source_is_cached_on_subsequent_absent_fetch() -> None:
    """After the base is seeded, a second call with no live data returns source='cached',
    proving the precomputed snapshot is served without re-running evaluators.
    """
    accuracy_mod._base_snapshot = None  # cold cache

    first = accuracy_report(fetch=_no_live)
    assert first["source"] == "measured"

    second = accuracy_report(fetch=_no_live)
    assert second["source"] == "cached"


def test_cached_base_headline_matches_first_computed_headline() -> None:
    """Cached base and freshly computed base must expose identical headline data."""
    accuracy_mod._base_snapshot = None

    first = accuracy_report(fetch=_no_live)
    second = accuracy_report(fetch=_no_live)

    assert second["headline"] == first["headline"]


def test_cached_base_metrics_match_first_computed_metrics() -> None:
    """Metrics list is identical when served from the base cache."""
    accuracy_mod._base_snapshot = None

    first = accuracy_report(fetch=_no_live)
    second = accuracy_report(fetch=_no_live)

    assert second["metrics"] == first["metrics"]


def test_cached_base_macros_match_first_computed_macros() -> None:
    """Macros section (the expensive part) is identical when served from cache."""
    accuracy_mod._base_snapshot = None

    first = accuracy_report(fetch=_no_live)
    second = accuracy_report(fetch=_no_live)

    assert second["macros"]["headline"] == first["macros"]["headline"]


# ---------------------------------------------------------------------------
# _measured_macro_scores is called at most once per TTL window
# ---------------------------------------------------------------------------


def test_measured_macro_scores_not_called_on_cache_hit(monkeypatch) -> None:
    """The expensive _measured_macro_scores computation is only called once to
    seed the base cache; subsequent absent-live-fetch calls skip it.
    """
    accuracy_mod._base_snapshot = None

    call_count: list[int] = []
    original = accuracy_mod._measured_macro_scores

    def counting_measured():
        call_count.append(1)
        return original()

    monkeypatch.setattr(accuracy_mod, "_measured_macro_scores", counting_measured)

    # First call — seeds the cache; evaluators must run exactly once.
    accuracy_report(fetch=_no_live)
    assert len(call_count) == 1

    # Subsequent calls — served from cache; evaluators must NOT run again.
    accuracy_report(fetch=_no_live)
    accuracy_report(fetch=_no_live)
    assert len(call_count) == 1  # still only one call


# ---------------------------------------------------------------------------
# live data still overrides the base cache
# ---------------------------------------------------------------------------


def test_live_data_overrides_cached_base() -> None:
    """When live Phoenix fetch succeeds, live data is used (source='live'), not the base cache."""
    accuracy_mod._base_snapshot = None

    # Seed the base cache first.
    accuracy_report(fetch=_no_live)

    live = {
        "baseline": {
            "macro_pct_error": 0.05,
            "calorie_accuracy": 0.02,
            "within_tolerance": 0.0,
            "portion_error": 0.1,
        },
        "current": {
            "macro_pct_error": 0.58,
            "calorie_accuracy": 0.60,
            "within_tolerance": 0.38,
            "portion_error": 0.58,
        },
        "experiments": 3,
    }

    report = accuracy_report(fetch=lambda: live)
    assert report["source"] == "live"
    assert report["headline"]["calorie_accuracy"] == 0.60


def test_base_cache_independent_of_live_cache() -> None:
    """The base snapshot is only used when the live fetch is absent; a subsequent
    absent call still hits the base cache even if the previous call used live data.
    """
    accuracy_mod._base_snapshot = None

    live = {
        "baseline": {"macro_pct_error": 0.05, "calorie_accuracy": 0.02,
                     "within_tolerance": 0.0, "portion_error": 0.1},
        "current": {"macro_pct_error": 0.58, "calorie_accuracy": 0.60,
                    "within_tolerance": 0.38, "portion_error": 0.58},
        "experiments": 2,
    }

    # Live call — should not affect the base cache (or seed it harmlessly).
    accuracy_report(fetch=lambda: live)

    # Now absent call — should either seed or hit base cache (never error).
    report = accuracy_report(fetch=_no_live)
    assert report["source"] in ("measured", "cached")
    assert "headline" in report

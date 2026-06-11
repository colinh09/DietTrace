"""Per-user learning memory: cache (recall) + few-shot (examples) (memory.py)."""

from __future__ import annotations

from dietrace.web.memory import SqliteMemory, calories_of, normalize, sum_totals


def _items() -> list[dict]:
    return [
        {
            "description": "Chipotle Chicken",
            "grams": 113.0,
            "nutrients": [
                {"code": "208", "name": "Energy", "amount": 180.0, "unit": "kcal"},
                {"code": "203", "name": "Protein", "amount": 32.0, "unit": "g"},
            ],
        },
        {
            "description": "Chipotle White Rice",
            "grams": 113.0,
            "nutrients": [{"code": "208", "name": "Energy", "amount": 210.0, "unit": "kcal"}],
        },
    ]


def test_normalize_is_a_stable_cache_key() -> None:
    assert normalize("  Chipotle BOWL, with rice! ") == "chipotle bowl with rice"


def test_sum_totals_aggregates_by_code() -> None:
    totals = {t["code"]: t["amount"] for t in sum_totals(_items())}
    assert totals["208"] == 390.0  # 180 + 210
    assert totals["203"] == 32.0


def test_recall_returns_the_corrected_meal_for_the_same_text(tmp_path) -> None:
    mem = SqliteMemory(tmp_path / "mem.sqlite")
    items = _items()
    mem.remember("alice", "chipotle bowl", items, sum_totals(items))

    # Same meal, different spacing/case → cache hit.
    hit = mem.recall("alice", "  Chipotle Bowl ")
    assert hit is not None
    assert [i["description"] for i in hit["per_item"]] == [
        "Chipotle Chicken",
        "Chipotle White Rice",
    ]
    assert {t["code"]: t["amount"] for t in hit["totals"]}["208"] == 390.0


def test_recall_is_scoped_per_user_and_misses_unknown_meals(tmp_path) -> None:
    mem = SqliteMemory(tmp_path / "mem.sqlite")
    mem.remember("alice", "chipotle bowl", _items(), [])

    assert mem.recall("bob", "chipotle bowl") is None  # another user
    assert mem.recall("alice", "a banana") is None  # never corrected


def test_remember_overwrites_a_prior_correction_for_the_same_meal(tmp_path) -> None:
    mem = SqliteMemory(tmp_path / "mem.sqlite")
    mem.remember("alice", "chipotle bowl", _items(), [])
    mem.remember("alice", "chipotle bowl", _items()[:1], [])  # corrected again

    hit = mem.recall("alice", "chipotle bowl")
    assert len(hit["per_item"]) == 1
    assert mem.count("alice") == 1


def test_examples_render_as_few_shot_food_lists(tmp_path) -> None:
    mem = SqliteMemory(tmp_path / "mem.sqlite")
    mem.remember("alice", "chipotle bowl", _items(), [])

    examples = mem.examples("alice")
    assert examples[0]["text"] == "chipotle bowl"
    assert [f["food"] for f in examples[0]["foods"]] == [
        "Chipotle Chicken",
        "Chipotle White Rice",
    ]


# ---------------------------------------------------------------------------
# calories_of — the energy extractor used in app.py:274 (_case_score) and in
# _eval_case (memory.py:60). Two branches: 208 present → the amount; absent →
# 0.0. Never directly exercised in this file despite being imported in app.py.
# ---------------------------------------------------------------------------


def test_calories_of_returns_energy_when_208_present() -> None:
    totals = [
        {"code": "203", "name": "Protein", "amount": 20.0, "unit": "g"},
        {"code": "208", "name": "Energy", "amount": 350.0, "unit": "kcal"},
    ]
    assert calories_of(totals) == 350.0


def test_calories_of_returns_zero_when_208_absent() -> None:
    totals = [{"code": "203", "name": "Protein", "amount": 20.0, "unit": "g"}]
    assert calories_of(totals) == 0.0


def test_calories_of_returns_zero_for_empty_list() -> None:
    assert calories_of([]) == 0.0


# calories_of feeds the deterministic gate (gate.py) and the /history +
# /eval-case endpoints (app.py), reading totals straight from persisted
# confirmations and request bodies. A garbled energy total — an explicit null
# amount, a non-numeric value, or a non-finite NaN/inf — must degrade to "no
# reliable calories" (0.0), not crash the retune or the endpoint, mirroring the
# isfinite guards in parse_meal / web_nutrition / estimate_portion /
# check_against_goals (fail-soft).


def test_calories_of_returns_zero_when_208_amount_is_null() -> None:
    totals = [{"code": "208", "name": "Energy", "amount": None, "unit": "kcal"}]
    assert calories_of(totals) == 0.0


def test_calories_of_returns_zero_when_208_amount_non_numeric() -> None:
    totals = [{"code": "208", "name": "Energy", "amount": "lots", "unit": "kcal"}]
    assert calories_of(totals) == 0.0


def test_calories_of_returns_zero_when_208_amount_non_finite() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        totals = [{"code": "208", "name": "Energy", "amount": bad, "unit": "kcal"}]
        assert calories_of(totals) == 0.0


# ---------------------------------------------------------------------------
# count — the SqliteMemory method checked indirectly in the overwrite test but
# never at zero. A fresh store must return 0, not raise.
# ---------------------------------------------------------------------------


def test_count_is_zero_on_empty_store(tmp_path) -> None:
    mem = SqliteMemory(tmp_path / "mem.sqlite")
    assert mem.count("alice") == 0


# ---------------------------------------------------------------------------
# sum_totals — the empty-input branch ([] items → [] totals) is not covered by
# the existing test, which passes a two-item list.
# ---------------------------------------------------------------------------


def test_sum_totals_empty_items_returns_empty_list() -> None:
    assert sum_totals([]) == []

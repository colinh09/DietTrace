"""MealLogStore persists and reads back logged meals."""

from dietrace.web.store import MealLogStore


def test_add_returns_id_and_list_reads_back(tmp_path) -> None:
    store = MealLogStore(tmp_path / "log.sqlite")
    totals = [{"code": "208", "name": "Energy", "amount": 105.0, "unit": "kcal"}]

    meal_id = store.add("1 banana", totals)

    assert isinstance(meal_id, int)
    meals = store.list()
    assert len(meals) == 1
    assert meals[0]["text"] == "1 banana"
    assert meals[0]["totals"] == totals
    assert meals[0]["created_at"]


def test_list_is_newest_first(tmp_path) -> None:
    store = MealLogStore(tmp_path / "log.sqlite")
    store.add("first", [])
    store.add("second", [])

    assert [m["text"] for m in store.list()] == ["second", "first"]


def test_store_persists_across_instances(tmp_path) -> None:
    path = tmp_path / "log.sqlite"
    MealLogStore(path).add("1 egg", [])

    assert len(MealLogStore(path).list()) == 1

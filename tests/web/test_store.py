"""MealLogStore persists and reads back logged meals."""

import datetime

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


def test_add_records_the_entry_date(tmp_path) -> None:
    store = MealLogStore(tmp_path / "log.sqlite")
    at = datetime.datetime(2026, 5, 28, 12, 0, tzinfo=datetime.UTC)

    store.add("1 banana", [], created_at=at)

    assert store.list()[0]["date"] == "2026-05-28"


def test_list_filters_by_date(tmp_path) -> None:
    store = MealLogStore(tmp_path / "log.sqlite")
    day1 = datetime.datetime(2026, 5, 28, 12, 0, tzinfo=datetime.UTC)
    day2 = datetime.datetime(2026, 5, 29, 9, 0, tzinfo=datetime.UTC)
    store.add("breakfast d1", [], created_at=day1)
    store.add("lunch d1", [], created_at=day1)
    store.add("dinner d2", [], created_at=day2)

    assert [m["text"] for m in store.list(date="2026-05-28")] == [
        "lunch d1",
        "breakfast d1",
    ]
    assert [m["text"] for m in store.list(date="2026-05-29")] == ["dinner d2"]


def test_list_without_date_returns_all(tmp_path) -> None:
    store = MealLogStore(tmp_path / "log.sqlite")
    store.add("d1", [], created_at=datetime.datetime(2026, 5, 28, tzinfo=datetime.UTC))
    store.add("d2", [], created_at=datetime.datetime(2026, 5, 29, tzinfo=datetime.UTC))

    assert len(store.list()) == 2


def test_add_with_explicit_date_files_under_that_day(tmp_path) -> None:
    store = MealLogStore(tmp_path / "log.sqlite")
    store.add("late snack", [], date="2026-05-31")
    assert len(store.list(date="2026-05-31")) == 1
    assert store.list(date="2026-06-01") == []


def test_delete_removes_a_meal(tmp_path) -> None:
    store = MealLogStore(tmp_path / "log.sqlite")
    meal_id = store.add("1 banana", [])
    assert store.delete(meal_id) is True
    assert store.list() == []
    assert store.delete(meal_id) is False  # already gone

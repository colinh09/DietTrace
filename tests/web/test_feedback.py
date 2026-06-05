"""User corrections → Phoenix ground truth (feedback.py).

A portion correction rescales the logged panel to the corrected grams, persists
locally, and renders as a Phoenix dataset example. Phoenix itself is never called
here — the push is injected at the endpoint; this pins the pure pieces.
"""

from __future__ import annotations

from dietrace.web.feedback import (
    Correction,
    FeedbackStore,
    corrected_expected,
    to_example,
)


def _correction(original: float, corrected: float) -> Correction:
    # A Five Guys burger logged at 317 g ≈ 920 kcal / 51 P / 62 F / 40 C.
    return Correction(
        food="Five Guys Bacon Cheeseburger",
        original_grams=original,
        corrected_grams=corrected,
        nutrients=[
            {"code": "208", "name": "Energy", "amount": 920.0, "unit": "kcal"},
            {"code": "203", "name": "Protein", "amount": 51.0, "unit": "g"},
            {"code": "204", "name": "Total lipid (fat)", "amount": 62.0, "unit": "g"},
            {"code": "205", "name": "Carbohydrate", "amount": 40.0, "unit": "g"},
        ],
    )


def test_corrected_expected_rescales_macros_to_the_new_grams() -> None:
    # Halve the portion: every macro halves, grams is the corrected value.
    expected = corrected_expected(_correction(original=317.0, corrected=158.5))

    assert expected["grams"] == 158.5
    assert expected["calories"] == 460.0
    assert expected["protein_g"] == 25.5
    assert expected["fat_g"] == 31.0
    assert expected["carb_g"] == 20.0


def test_correction_renders_as_a_phoenix_example() -> None:
    inp, out, meta = to_example(_correction(original=317.0, corrected=317.0))

    assert inp == {"text": "Five Guys Bacon Cheeseburger"}
    assert out["calories"] == 920.0 and out["grams"] == 317.0
    assert meta["source"] == "user_feedback"
    assert meta["corrected_grams"] == 317.0


def test_macro_absent_from_the_panel_is_omitted_not_guessed() -> None:
    correction = Correction(
        food="mystery", original_grams=100.0, corrected_grams=50.0, nutrients=[]
    )
    expected = corrected_expected(correction)

    assert expected == {"grams": 50.0}  # only grams; no fabricated macros


def test_corrected_expected_corrected_grams_zero() -> None:
    """A correction to 0 g (user didn't eat it) yields all-zero macros.

    The rescale factor is 0/base = 0.0, so every macro becomes 0. The result
    is a valid ground-truth entry that says the food contributed nothing — the
    correct expectation when the user removes a logged item via a correction.
    """
    expected = corrected_expected(_correction(original=317.0, corrected=0.0))
    assert expected["grams"] == 0.0
    assert expected["calories"] == 0.0
    assert expected["protein_g"] == 0.0
    assert expected["fat_g"] == 0.0
    assert expected["carb_g"] == 0.0


def test_corrected_expected_original_grams_zero_is_defensive_noop() -> None:
    """When original_grams is 0 the function cannot rescale (0/0 is undefined).

    The ``if base else 0.0`` guard yields factor=0.0 so all macros are zeroed
    and grams is set to the corrected value. This pins the defensive branch so
    a future refactor cannot accidentally raise ZeroDivisionError or produce NaN.
    """
    correction = Correction(
        food="mystery",
        original_grams=0.0,
        corrected_grams=100.0,
        nutrients=[
            {"code": "208", "name": "Energy", "amount": 200.0, "unit": "kcal"},
        ],
    )
    expected = corrected_expected(correction)
    assert expected["grams"] == 100.0
    assert expected.get("calories") == 0.0


def test_corrected_expected_negative_corrected_grams_clamps_to_zero() -> None:
    """A negative corrected_grams must not produce negative calorie ground truth.

    The Phoenix feedback dataset would be poisoned by a negative-calorie example
    (same class of defect as the ParsedItem.quantity NaN/negative fix and the
    apply_feedback negative-gram clamps). The corrected grams and all macro values
    must be floored at 0.0 on degenerate input.
    """
    expected = corrected_expected(_correction(original=317.0, corrected=-50.0))
    assert expected["grams"] == 0.0
    for key in ("calories", "protein_g", "fat_g", "carb_g"):
        assert expected.get(key, 0.0) >= 0.0, f"{key} must not be negative"


def test_store_migrates_older_db_missing_user_id_column(tmp_path) -> None:
    """An older corrections DB without user_id migrates transparently on open.

    The migration branch (ALTER TABLE … ADD COLUMN user_id … DEFAULT 'demo') runs
    when FeedbackStore opens a DB whose corrections table predates per-user scoping.
    After migration, existing rows are visible under DEMO_USER and new writes work.
    """
    import sqlite3

    from dietrace.web.identity import DEMO_USER

    _OLD_SCHEMA = (
        "CREATE TABLE IF NOT EXISTS corrections ("
        "id              INTEGER PRIMARY KEY AUTOINCREMENT, "
        "created_at      TEXT NOT NULL, "
        "food            TEXT NOT NULL, "
        "original_grams  REAL NOT NULL, "
        "corrected_grams REAL NOT NULL, "
        "expected_json   TEXT NOT NULL)"
    )

    db_path = tmp_path / "old_feedback.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(_OLD_SCHEMA)
    conn.execute(
        "INSERT INTO corrections "
        "(created_at, food, original_grams, corrected_grams, expected_json) "
        "VALUES (?, ?, ?, ?, ?)",
        ("2024-01-01T00:00:00+00:00", "oatmeal", 80.0, 100.0, '{"grams": 100.0}'),
    )
    conn.commit()
    conn.close()

    store = FeedbackStore(db_path)

    # Existing row is surfaced under DEMO_USER (the migration DEFAULT).
    assert store.count(DEMO_USER) == 1
    recent = store.recent(DEMO_USER)
    assert len(recent) == 1
    assert recent[0]["food"] == "oatmeal"
    assert recent[0]["original_grams"] == 80.0
    assert recent[0]["corrected_grams"] == 100.0

    # New writes after migration work normally.
    correction = _correction(317.0, 200.0)
    store.add(correction, corrected_expected(correction), user_id=DEMO_USER)
    assert store.count(DEMO_USER) == 2


def test_store_persists_and_counts_corrections(tmp_path) -> None:
    store = FeedbackStore(tmp_path / "feedback.sqlite")
    assert store.count() == 0

    correction = _correction(317.0, 200.0)
    store.add(correction, corrected_expected(correction))
    store.add(correction, corrected_expected(correction))

    assert store.count() == 2


def test_store_lists_recent_corrections_newest_first_per_user(tmp_path) -> None:
    # The "what you've taught" panel reads each correction's food + before→after
    # grams, newest first, scoped to the user.
    store = FeedbackStore(tmp_path / "feedback.sqlite")
    burger = _correction(317.0, 200.0)
    oatmeal = Correction(
        food="oatmeal", original_grams=80.0, corrected_grams=120.0, nutrients=[]
    )
    store.add(burger, corrected_expected(burger), user_id="alice")
    store.add(oatmeal, corrected_expected(oatmeal), user_id="alice")
    store.add(burger, corrected_expected(burger), user_id="bob")

    recent = store.recent(user_id="alice")
    assert [r["food"] for r in recent] == [
        "oatmeal",
        "Five Guys Bacon Cheeseburger",
    ]
    assert recent[0]["original_grams"] == 80.0
    assert recent[0]["corrected_grams"] == 120.0
    assert recent[0]["created_at"]
    # Bob's correction never leaks into alice's panel.
    bob = store.recent(user_id="bob")
    assert [r["food"] for r in bob] == ["Five Guys Bacon Cheeseburger"]

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


def test_store_persists_and_counts_corrections(tmp_path) -> None:
    store = FeedbackStore(tmp_path / "feedback.sqlite")
    assert store.count() == 0

    correction = _correction(317.0, 200.0)
    store.add(correction, corrected_expected(correction))
    store.add(correction, corrected_expected(correction))

    assert store.count() == 2

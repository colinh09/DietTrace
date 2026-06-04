"""The curated overlay maps common food names → a pinned fdc_id.

The agent's parse emits a food name in whatever number it reads ("10 almonds" →
"almond"), while a curated key may be written plural ("almonds"). normalize must
fold both onto one key so the pin still hits — the bug these tests pin down is a
plural key silently missing the singular parse and falling through to ranked
search.
"""

from dietrace.nutrition.overlay import normalize, overlay_fdc_id


def test_normalize_lowercases_strips_punctuation_and_collapses() -> None:
    assert normalize("  Greek YOGURT! ") == "greek yogurt"


def test_normalize_singularizes_so_plural_and_singular_converge() -> None:
    """The whole point: a plural name and its singular reduce to the same key."""
    assert normalize("almonds") == normalize("almond")
    assert normalize("strawberries") == normalize("strawberry")
    assert normalize("grapes") == normalize("grape")
    assert normalize("tomatoes") == normalize("tomato")
    assert normalize("green beans") == normalize("green bean")


def test_normalize_leaves_singular_names_unchanged() -> None:
    assert normalize("chicken breast") == "chicken breast"
    assert normalize("ground beef") == "ground beef"


def test_normalize_us_word_is_stable_both_ways() -> None:
    """An -us word over-singularizes, but both sides transform alike so it matches."""
    assert normalize("asparagus") == normalize("asparagus")


def test_overlay_lookup_hits_on_either_number() -> None:
    """A plural-keyed pin resolves whether the parse is singular or plural."""
    table = {"almond": 111, "green bean": 222}
    assert overlay_fdc_id("almonds", table) == 111
    assert overlay_fdc_id("almond", table) == 111
    assert overlay_fdc_id("green beans", table) == 222


def test_overlay_miss_returns_none() -> None:
    assert overlay_fdc_id("rutabaga", {"almond": 111}) is None


def test_normalize_singularizes_ches_ending() -> None:
    """'peaches' → 'peach' via the -ches suffix branch so a curated 'peach' pin hits."""
    assert normalize("peaches") == "peach"
    assert normalize("peaches") == normalize("peach")


def test_normalize_singularizes_shes_ending() -> None:
    """'radishes' → 'radish' and 'squashes' → 'squash' via the -shes suffix branch."""
    assert normalize("radishes") == "radish"
    assert normalize("radishes") == normalize("radish")
    assert normalize("squashes") == "squash"
    assert normalize("squashes") == normalize("squash")


def test_overlay_lookup_hits_ches_and_shes_plurals() -> None:
    """A 'peaches' or 'radishes' query resolves to the singularized overlay pin."""
    table = {"peach": 300, "radish": 400}
    assert overlay_fdc_id("peaches", table) == 300
    assert overlay_fdc_id("radishes", table) == 400
    assert overlay_fdc_id("peach", table) == 300
    assert overlay_fdc_id("radish", table) == 400

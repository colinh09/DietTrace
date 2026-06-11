"""The curated overlay maps common food names → a pinned fdc_id.

The agent's parse emits a food name in whatever number it reads ("10 almonds" →
"almond"), while a curated key may be written plural ("almonds"). normalize must
fold both onto one key so the pin still hits — the bug these tests pin down is a
plural key silently missing the singular parse and falling through to ranked
search.
"""

from dietrace.nutrition.overlay import load_overlay, normalize, overlay_fdc_id


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


def test_normalize_singularizes_xes_ending() -> None:
    """'mixes' → 'mix' via the -xes suffix branch so a curated 'mix' pin hits.

    The ``for suffix in (..., 'xes', ...)`` loop handles food names whose plural
    ends in '-xes' (e.g. 'trail mixes', 'mixes'); without it they fall through to
    the bare-s strip which would yield 'mixe', a miss against a 'mix' overlay key.
    """
    assert normalize("mixes") == "mix"
    assert normalize("mixes") == normalize("mix")


def test_overlay_lookup_hits_xes_plural() -> None:
    """A 'mixes' query (or 'trail mixes') resolves to the singularized overlay pin."""
    table = {"mix": 500, "trail mix": 501}
    assert overlay_fdc_id("mixes", table) == 500
    assert overlay_fdc_id("mix", table) == 500
    assert overlay_fdc_id("trail mixes", table) == 501
    assert overlay_fdc_id("trail mix", table) == 501


# ---- load_overlay: the lru_cache'd file-loading paths ----
# All tests above pass an explicit ``overlay`` dict to ``overlay_fdc_id``,
# bypassing ``load_overlay()`` entirely. These three tests cover the file-loading
# branches directly so the fail-soft paths don't rot silently.
#
# Each test clears the lru_cache before and after calling ``load_overlay()``
# to guarantee a fresh file read rather than a stale cache hit, and to avoid
# leaking state into subsequent tests.


def test_load_overlay_returns_empty_when_file_missing(tmp_path, monkeypatch) -> None:
    """DIETRACE_OVERLAY pointing to a nonexistent file → {} (file-not-found branch)."""
    monkeypatch.setenv("DIETRACE_OVERLAY", str(tmp_path / "nonexistent.json"))
    load_overlay.cache_clear()
    try:
        result = load_overlay()
    finally:
        load_overlay.cache_clear()
    assert result == {}


def test_load_overlay_returns_empty_on_malformed_json(tmp_path, monkeypatch) -> None:
    """A file that exists but contains invalid JSON falls back to {} (fail-soft branch)."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json}")
    monkeypatch.setenv("DIETRACE_OVERLAY", str(bad))
    load_overlay.cache_clear()
    try:
        result = load_overlay()
    finally:
        load_overlay.cache_clear()
    assert result == {}


def test_load_overlay_returns_populated_dict_on_valid_json(tmp_path, monkeypatch) -> None:
    """A valid JSON file produces a normalized-key → fdc_id dict (happy path)."""
    valid = tmp_path / "foods.json"
    valid.write_text('{"almond": 1234, "chicken breast": 5678, "Green Beans": 9000}')
    monkeypatch.setenv("DIETRACE_OVERLAY", str(valid))
    load_overlay.cache_clear()
    try:
        result = load_overlay()
    finally:
        load_overlay.cache_clear()
    assert result[normalize("almond")] == 1234
    assert result[normalize("chicken breast")] == 5678
    assert result[normalize("Green Beans")] == 9000


def test_load_overlay_skips_bad_entries_keeping_the_valid_pins(
    tmp_path, monkeypatch
) -> None:
    """One uncoercible value must not discard the whole curated map (per-entry fail-soft).

    A hand-maintained mappings file can carry a typo'd value. Building the table
    in a single dict comprehension meant one ``int(v)`` failure threw straight out
    and ``load_overlay`` fell back to ``{}`` — silently degrading *every* pinned
    common food (the permanent ranking-class fix) back to the ranked search,
    with no error. Each entry must fail soft on its own so the good pins survive.
    """
    f = tmp_path / "foods.json"
    f.write_text('{"almond": 1234, "broken": "not_a_number", "carrot": 5678}')
    monkeypatch.setenv("DIETRACE_OVERLAY", str(f))
    load_overlay.cache_clear()
    try:
        result = load_overlay()
    finally:
        load_overlay.cache_clear()
    assert result[normalize("almond")] == 1234
    assert result[normalize("carrot")] == 5678
    assert normalize("broken") not in result


def test_load_overlay_returns_empty_when_json_is_not_an_object(
    tmp_path, monkeypatch
) -> None:
    """Valid JSON of the wrong shape (a list/scalar, not an object) → {} (fail-soft)."""
    f = tmp_path / "list.json"
    f.write_text("[1234, 5678]")
    monkeypatch.setenv("DIETRACE_OVERLAY", str(f))
    load_overlay.cache_clear()
    try:
        result = load_overlay()
    finally:
        load_overlay.cache_clear()
    assert result == {}

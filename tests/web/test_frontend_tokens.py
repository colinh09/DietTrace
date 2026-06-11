"""shadcn components + sage design tokens in the Next.js frontend.

Encodes the done-criterion: button/card/input are added under src/components/ui,
the cn() util exists, and src/app/globals.css carries the sage palette + fonts +
density tokens. The Next build itself
is verified separately via `cd frontend && npm run build`.
"""

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
GLOBALS = FRONTEND / "src" / "app" / "globals.css"


def test_base_ui_components_added():
    """button/card/input components and the cn() util are installed."""
    ui = FRONTEND / "src" / "components" / "ui"
    for name in ("button.tsx", "card.tsx", "input.tsx"):
        assert (ui / name).exists(), f"shadcn component {name} missing"
    assert (FRONTEND / "src" / "lib" / "utils.ts").exists(), "cn() util (src/lib/utils.ts) missing"


def test_sage_accent_tokens_present():
    """The sage accent ramp from the design doc lands in globals.css."""
    css = GLOBALS.read_text()
    assert "--accent: #5E7A5C" in css, "sage accent token missing"
    assert "--accent-ink: #46603F" in css, "sage accent-ink token missing"
    assert "--bg: #FAFAF8" in css, "warm background token missing"
    assert "--amber: #B07F34" in css, "amber (medium-confidence) token missing"


def test_semantic_tokens_wired_to_sage():
    """shadcn semantic tokens map onto the sage design palette."""
    css = GLOBALS.read_text()
    assert "--primary: var(--accent)" in css, "primary should map to the sage accent"
    assert "--background: var(--bg)" in css, "background should map to the warm bg"
    assert "--border: var(--line)" in css, "border should map to the hairline"


def test_fonts_and_density_tokens_present():
    """Typography (serif/mono stacks) and density (radius) tokens are set."""
    css = GLOBALS.read_text()
    assert "JetBrains Mono" in css, "mono font stack missing"
    assert "Iowan Old Style" in css, "serif font stack missing"
    assert "--radius: 14px" in css, "radius density token missing"

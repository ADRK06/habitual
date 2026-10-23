from pathlib import Path

APP_CSS = Path(__file__).resolve().parent.parent / "habitual" / "static" / "css" / "app.css"

# The 10 raw Colonies palette tokens (tailwind/input.css, from
# docs/reference/colonies/screens/Main.dc.html) that must survive into the
# committed, compiled stylesheet. Tailwind v4 only emits a @theme CSS
# variable when some utility class in the scanned templates actually
# references it - a token with no real `bg-*`/`text-*`/etc. usage
# anywhere gets silently dropped, rendering as an unset custom property
# (nothing drawn) wherever it's referenced via var(). Steel and Regolith
# hit exactly this: dev/styleguide.html used to reference them only via
# inline `style="...var(--color-steel)"`, which Tailwind's scanner never
# sees, so they never made it into app.css at all.
PALETTE_TOKENS = [
    "void",
    "hull",
    "bulkhead",
    "bone",
    "dust",
    "phosphor",
    "rust",
    "signal",
    "steel",
    "regolith",
]


def test_compiled_css_exists():
    assert APP_CSS.is_file(), f"{APP_CSS} is missing - run ./tailwindcss -i tailwind/input.css -o {APP_CSS}"


def test_all_ten_palette_tokens_are_emitted_into_compiled_css():
    css = APP_CSS.read_text()

    missing = [t for t in PALETTE_TOKENS if f"--color-{t}:" not in css]
    assert not missing, f"palette tokens missing from compiled app.css (likely unused anywhere -> tree-shaken): {missing}"


def test_all_ten_palette_tokens_have_a_bg_utility_emitted():
    # Belt-and-suspenders: confirms each token is also reachable through a
    # real utility class, not just present as a variable declaration with
    # nothing to put it to use.
    css = APP_CSS.read_text()

    missing = [t for t in PALETTE_TOKENS if f".bg-{t}{{" not in css]
    assert not missing, f"no compiled .bg-* utility for these palette tokens: {missing}"

"""Dev-only tooling, never registered unless HABITUAL_DEV is set (see
habitual/config.py and habitual/__init__.py) - this module only exists at
all when that flag is on, so there is no route to probe for in prod even
with the flag absent.
"""

import json
import struct
from pathlib import Path

from flask import Blueprint, render_template
from flask_login import current_user

dev = Blueprint("dev", __name__)

ART_DIR = Path(__file__).parent / "static" / "art"
SPRITE_SHEET_PATH = ART_DIR / "_sheet.png"
COMPOSITES_DIR = ART_DIR / "_composites"
MANIFEST_PATH = ART_DIR / "manifest.json"

# manifest.json "category" -> display heading, in the order sections appear.
CATEGORY_LABELS = {
    "avatar_part": "Avatar parts",
    "avatar_render": "Avatar renders",
    "building": "Buildings",
    "overlay": "Building overlays",
    "planet_building": "Planet-scale buildings (review)",
    "icon": "Icons",
    "planet_material": "Planet materials",
    "planet_decoration": "Planet decorations",
    "planet_render": "Planet renders",
    "scene": "Scenes",
    "ship": "Ships",
    "fleet": "Fleet",
    "effect": "Effects",
}

PLANET_BUILDING_TYPES = [
    ("defense_tower", "Defense Tower"),
    ("research_lab", "Research Lab"),
    ("power_reactor", "Power Reactor"),
    ("biodome", "Biodome"),
    ("observatory", "Observatory"),
    ("custom_module", "Custom Module"),
]

FIXED_BUILDINGS = [
    "building_research_lab",
    "building_defense_tower",
    "building_biodome",
    "building_observatory",
    "building_power_reactor",
]


def _png_size(path: Path) -> tuple[int, int] | None:
    """Read a PNG's real pixel dimensions from its IHDR chunk (stdlib only -
    Pillow is a dev-only dependency, see requirements-dev.txt, so this route
    can't import it)."""
    if not path.exists():
        return None
    with path.open("rb") as f:
        header = f.read(24)
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def _sprite_groups() -> tuple[list[dict], list[dict]]:
    """Every sprite from manifest.json, grouped by category, plus a
    separate flat list of the new (Phase 2b) ones for a dedicated review
    section. Each sprite carries its own natural pixel size so the template
    can render it at that exact size x4 - never stretched or squeezed."""
    if not MANIFEST_PATH.exists():
        return [], []

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    by_category: dict[str, list[dict]] = {key: [] for key in CATEGORY_LABELS}
    new_sprites: list[dict] = []

    for entry in sorted(manifest, key=lambda e: e["name"]):
        size = _png_size(ART_DIR / f"{entry['name']}.png")
        if size is None:
            continue
        sprite = {
            "name": entry["name"],
            "filename": f"art/{entry['name']}.png",
            "width": size[0],
            "height": size[1],
            "is_new": bool(entry.get("new")),
        }
        by_category.setdefault(entry["category"], []).append(sprite)
        if sprite["is_new"]:
            new_sprites.append(sprite)

    sprite_groups = [
        {"label": CATEGORY_LABELS[key], "sprites": by_category[key]}
        for key in CATEGORY_LABELS
        if by_category.get(key)
    ]
    return sprite_groups, new_sprites


def _composite_rows() -> list[dict]:
    """The damage-overlay and shield-dome composite tests, as individual
    per-building PNGs (built by `scripts/make_sprites.py composites`) so
    each can be shown at its own true proportions instead of packed into a
    shared thumbnail cell."""
    rows = []
    for kind, title in [("damage", "Damage overlay"), ("shield", "Shield dome")]:
        entries = []
        for building in FIXED_BUILDINGS:
            filename = f"{building}_{kind}.png"
            size = _png_size(COMPOSITES_DIR / filename)
            if size is None:
                continue
            entries.append(
                {
                    "name": building.removeprefix("building_").replace("_", " ").title(),
                    "filename": f"art/_composites/{filename}",
                    "width": size[0],
                    "height": size[1],
                }
            )
        if entries:
            # "entries", not "items" - Jinja's `row.items` would resolve to
            # dict.items (the builtin method) via attribute lookup before
            # ever trying key lookup, since dicts have an `items` method.
            rows.append({"title": title, "entries": entries})
    return rows


def _planet_building_rows() -> list[dict]:
    """The 18 planet-scale building sprites (scripts/make_sprites.py's
    PLANET_BUILDING_DRAWERS), one row per building type with its LV1-3
    progression, each shown at x1 AND x4 (x1 to judge true in-context
    size against the planet, x4 to inspect detail - a generic sprite_card
    alone only ever shows x4). These are the WIRED (production) sprites -
    see habitual.colony.BUILDING_SLOTS."""
    rows = []
    for building_type, label in PLANET_BUILDING_TYPES:
        levels = []
        for level in (1, 2, 3):
            name = f"planet_building_{building_type}_lv{level}"
            size = _png_size(ART_DIR / f"{name}.png")
            if size is None:
                continue
            levels.append({"level": level, "filename": f"art/{name}.png", "width": size[0], "height": size[1]})
        if levels:
            rows.append({"label": label, "levels": levels})
    return rows


PLANET_PREVIEW_FILES = [
    ("planet_preview_empty.png", "Empty (clean planet, no buildings)"),
    ("planet_preview_lv1.png", "All six built · LV1"),
    ("planet_preview_lv3.png", "All six built · LV3 (reproduces the original bake)"),
    ("planet_preview_mixed_bare.png", "Realistic mix · 2 built, 4 locked (no marker)"),
    ("planet_preview_mixed_dot.png", "Realistic mix · 2 built, 4 locked (dim locked dot)"),
]


def _planet_previews() -> list[dict]:
    """The five full-planet mockups built by scripts/make_sprites.py's
    build_planet_previews() (empty / all-LV1 / all-LV3 / a realistic
    2-built-4-locked mix shown both with and without the dim locked-dot
    marker), shown large so the developer can judge how each building's
    cluster reads on planet_render_rust_clean.png - the same art wired
    into /colony."""
    previews = []
    for filename, label in PLANET_PREVIEW_FILES:
        size = _png_size(COMPOSITES_DIR / filename)
        if size is not None:
            previews.append({"label": label, "filename": f"art/_composites/{filename}", "width": size[0], "height": size[1]})
    return previews


def _planet_variant_comparison() -> list[dict]:
    """The original planet_render_rust.png next to planet_render_rust_
    clean.png (antenna/debris erased) for a side-by-side approval call -
    see scripts/make_sprites.py's draw_planet_render_rust_clean docstring
    for exactly what was removed and why."""
    variants = []
    for name, label in [("planet_render_rust", "Original"), ("planet_render_rust_clean", "Clean (antenna/debris removed)")]:
        size = _png_size(ART_DIR / f"{name}.png")
        if size is not None:
            variants.append({"label": label, "filename": f"art/{name}.png", "width": size[0], "height": size[1]})
    return variants


@dev.get("/dev/styleguide")
def styleguide():
    # No @login_required - the styleguide itself must work logged out
    # too (app_base.html's shell hides the commander card/HUD for an
    # anonymous visitor instead). Logged in, it shows the real shell
    # with real nav_balance/nav_streak, same as every other page.
    from habitual.habits import nav_shell_context

    nav_context = nav_shell_context(current_user) if current_user.is_authenticated else {}
    sprite_groups, new_sprites = _sprite_groups()
    composite_rows = _composite_rows()
    sheet_size = _png_size(SPRITE_SHEET_PATH)
    planet_building_rows = _planet_building_rows()
    planet_previews = _planet_previews()
    planet_variants = _planet_variant_comparison()
    return render_template(
        "dev/styleguide.html",
        sprite_groups=sprite_groups,
        new_sprites=new_sprites,
        composite_rows=composite_rows,
        planet_variants=planet_variants,
        sheet_size=sheet_size,
        planet_building_rows=planet_building_rows,
        planet_previews=planet_previews,
        **nav_context,
    )

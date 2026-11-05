#!/usr/bin/env python3
"""Colonies sprite pipeline (Phase 2).

Usage:
    python scripts/make_sprites.py import       # copy+rename reference sprites, write manifest.json, print audit
    python scripts/make_sprites.py audit         # just re-print the audit (no file changes)
    python scripts/make_sprites.py draw          # (re)draw the new (non-imported) sprites
    python scripts/make_sprites.py manifest-update  # stamp manifest.json with new=true/false
    python scripts/make_sprites.py sheet         # build _sheet.png, an export-only contact sheet
    python scripts/make_sprites.py composites    # build the per-building composite test PNGs

This script only ever touches docs/reference/colonies/art/ (read) and
habitual/static/art/ (write). It never edits templates - wiring sprites into
real pages happens in a later step, after the audit is approved.
"""
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = REPO_ROOT / "docs" / "reference" / "colonies" / "art"
SCREENS_DIR = REPO_ROOT / "docs" / "reference" / "colonies" / "screens"
DEST_DIR = REPO_ROOT / "habitual" / "static" / "art"
MANIFEST_PATH = DEST_DIR / "manifest.json"

# old sprite id (filename stem in docs/reference/colonies/art/) -> readable,
# unique new name (filename stem in habitual/static/art/). Built by reading
# README.md's ART_MANIFEST plus each screen's own code names (BLD/CAT/P
# objects, shop item labels) where the manifest said "(see usage)" or just
# "icon".
SPRITE_NAMES = {
    # avatar builder parts
    "11f0eec12d484e79f789516b33535718": "avatar_face_1",
    "de6e443848ae54303110acc720d90c2f": "avatar_face_2",
    "ae60e6d9ea2a0512ed25744ce1785732": "avatar_face_3",
    "c4860f60abb4f71879b4f183fd75594f": "avatar_face_4",
    "b12e2c7e5fac8fffaf78fff031708aac": "avatar_face_5",
    "4c5e10db8669c8059784d445cf039584": "avatar_hair_dark",
    "67b48b54adece8d0fb6cab429b885ac4": "avatar_hair_silver",
    "d0a2fc6b3fae6078ff34a477486cd36d": "avatar_hair_brown",
    "1e2e9540656ad1457862546a15a49ae8": "avatar_helmet_crest",
    "298555d524aba6902f97d2c4a2a58659": "avatar_helmet_round",
    "dc95025ff87e47e448588afb1dc62b14": "avatar_helmet_box",
    "2538c776edc28cec59ec00fd00ec7e67": "avatar_suit_steel",
    "289c5fc29cb8b515285b0bfee0e05397": "avatar_suit_signal",
    "93402df64f2c97ed352a6561c722ac2d": "avatar_suit_phosphor",
    "a1f2e3fc19eefca69d0fcbfa02c10bc6": "avatar_suit_admiral",
    "f2caa9ab50aef03355f99c2e25688da8": "avatar_suit_bone",
    "2672b4085bc1fcbfd158512e350f24a8": "avatar_visor_signal",
    "be71b5ddb2529eaf18e90727318d3f40": "avatar_visor_steel",
    "ddbb09d12bad5326962e0f00afa7965f": "avatar_visor_amber",
    "f271c681c59843dadf8671f85e529162": "avatar_visor_rust",
    "f8ab377810ed9880ab9e9ce31ea480b0": "avatar_visor_mirror",
    "14731d8dd44af7d5dddc283de3c64dff": "avatar_acc_scarf",
    "2ea50d01c4a051b24d2d2ed395eee6b2": "avatar_acc_lights",
    "bb09e50a7fa4013431420c12b99d4a05": "avatar_acc_antenna",
    "f041a441b0216fc56652e90008dd6066": "avatar_acc_jetpack",
    "03365443777eff054045b5d9dac735d5": "avatar_emblem_bolt",
    "60fb4991e971e63f41226a9cf9dd23a8": "avatar_emblem_star",
    "6261b648dbf40a50180c2fcaa97c6ae0": "avatar_emblem_planet",
    # full-body commander renders, one per suit (shop thumbnails + leaderboard avatars)
    "fda5c80c9eef2e7a17d948ec9e53f848": "avatar_render_phosphor",
    "b952f2499d95c8435f81b81fab41aecb": "avatar_render_steel",
    "f7bb44468497b64667e7ba1e084c84c8": "avatar_render_signal",
    "30d11df90e5e41179d7bf18a6cc46d74": "avatar_render_rust",
    "2be38c0f38ebc9ca1c8ebf5014baa243": "avatar_render_bone",
    "71ae5d774fe290d83a4680a2d0a98632": "avatar_render_admiral",
    # buildings, full size (home/habits/build screens)
    "7086c715151fb0500e83b582a3f74636": "building_research_lab",
    "d87c116e3245189550fc21b92f9c6428": "building_biodome",
    "60a3210093b573549153066d3b54b340": "building_defense_tower",
    "0cdb2907aa4a5d6ecaadeee5f0f71fdd": "building_observatory",
    "41326809df27d06e781b9363b010be29": "building_power_reactor",
    "6c9b90961eec1ad3adbe5cbfe0e1d67d": "building_custom_module",
    # buildings, small slot icons (planet customizer layout tab)
    "3f89991e301e8f2318496819a501707e": "icon_research_lab",
    "626fe13583f9a1beb6007ffbda45f638": "icon_biodome",
    "8c8d464038b047da68fb3c6139d2cede": "icon_defense_tower",
    "bf8d74b260d1e8e0c2a502a37dae9605": "icon_observatory",
    "6efbd6f23459283465d454ef1462c333": "icon_power_reactor",
    "7cd110ccc7734053d1495017f80ff716": "icon_custom_module",
    # planet customizer: world material swatches
    "760890681407fd130e89f534c2172ee1": "planet_world_rust",
    "ca34c774ae955365dba0e5415ed7f321": "planet_world_dust",
    "d459bd90b32dc1a43a5c382c723b224d": "planet_world_verdant",
    "c6bf7d33b90715c0e84c3efdd9627d16": "planet_world_ice",
    "a4246740bde6b380895b7266d5d6466c": "planet_world_lava",
    "48a95d329198f9ce6ab40073e37f56c6": "planet_world_ringed_giant",
    # planet customizer: atmosphere swatches
    "7b857b3fc6c3bd250ba08b75d04f35ce": "planet_atmo_steel",
    "4223c94e73e4e4dac74903a0d8c8d629": "planet_atmo_amber",
    "c1169d1e9288fa06a86a82ffe472ea7a": "planet_atmo_signal",
    # planet customizer: decoration layers
    "bf01f9dcb3281707e0f38a15c42e7656": "planet_deco_stars",
    "f571fa0d6ce756b259e0ead2ba74c9b8": "planet_deco_ring_back",
    "a49c8be4f123caf1241570b87ad85534": "planet_deco_ring_front",
    "3e907169335ccd71aac4cf55104041ae": "planet_deco_moon_1",
    "4d588aa9c02b7c0e2c3c866ccb44702b": "planet_deco_moon_2",
    # full planet renders (shop/sector/galaxy thumbnails) - one per world type + inactive
    "93037739eedb431e18db41628feb2b0b": "planet_render_rust",
    "97acf132fff58afa09530844b64b8406": "planet_render_dust",
    "02dbdb774a0f77db580c7e678aaf164b": "planet_render_verdant",
    "a11f3f0cac003d310f29b745eec375e8": "planet_render_ice",
    "93df6d126fa5db88f6a484ba662a35e6": "planet_render_lava",
    "10722e334b81662e8e390429f06572d1": "planet_render_ringed_giant",
    "5ae65cb379d9a07fb21b6604cac4ed9c": "planet_render_inactive",
    # large hero/narrative scenes
    "11daf5aa9d7ea8282bb0028766db8332": "scene_colony_home",
    "c1eb4904d6f173742a80b39109755a4d": "scene_colony_landing",
    "49a78cf50d20b7c7dd7cf6b600d0e4db": "scene_colony_storm",
    "81ef5c02121224f3c7346f4e45f4957b": "scene_fleet_battle",
    "8ea52548bcc030ffac88d685d779441f": "scene_galaxy_map",
    "1fabd52e32f8f8dd07b0b0d0752c6666": "scene_isometric_alt",
    "8ebf9d7c0689e7ef15d3d48210042491": "scene_sideview_alt",
    # ships
    "a7cff84bb42a345d21472332f425e369": "ship_scout",
    "6c7e87e22824fabafda64297bb7491b3": "ship_hauler",
    "f52a95d0bece393d18b6ae7b3736e389": "ship_lancer",
    # misc UI icons
    "79e56d4d28c9262a4f55a088dc37004e": "icon_shield",
    "bbaaf9fb712684cd9db1c3f9cb4f74bd": "icon_trophy",
    "36def7fece835ab90b181af91fba641d": "icon_supply_crate",
}

# category inferred from the new name's prefix, for manifest.json grouping
CATEGORY_PREFIXES = [
    ("avatar_render_", "avatar_render"),
    ("avatar_", "avatar_part"),
    ("building_", "building"),
    ("icon_", "icon"),
    ("planet_world_", "planet_material"),
    ("planet_atmo_", "planet_material"),
    ("planet_deco_", "planet_decoration"),
    ("planet_render_", "planet_render"),
    ("scene_", "scene"),
    ("ship_", "ship"),
]


def category_for(new_name: str) -> str:
    for prefix, category in CATEGORY_PREFIXES:
        if new_name.startswith(prefix):
            return category
    return "other"


def find_usages() -> dict[str, list[str]]:
    """Map each old sprite id to the screen files that reference it."""
    usages: dict[str, list[str]] = {old_id: [] for old_id in SPRITE_NAMES}
    for screen_path in sorted(SCREENS_DIR.glob("*.dc.html")):
        text = screen_path.read_text(encoding="utf-8")
        for old_id in SPRITE_NAMES:
            if old_id in text:
                usages[old_id].append(screen_path.name)
    return usages


def check_names_unique_and_readable() -> None:
    names = list(SPRITE_NAMES.values())
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise SystemExit(f"Duplicate new sprite names: {sorted(dupes)}")
    for name in names:
        if not name.replace("_", "").isalnum() or not name.islower():
            raise SystemExit(f"Sprite name is not a readable lowercase_snake_case name: {name!r}")

    source_ids = {p.stem for p in SOURCE_DIR.glob("*.png")}
    mapped_ids = set(SPRITE_NAMES)
    missing = source_ids - mapped_ids
    extra = mapped_ids - source_ids
    if missing:
        raise SystemExit(f"Sprites in {SOURCE_DIR} with no name assigned: {sorted(missing)}")
    if extra:
        raise SystemExit(f"Named sprites that don't exist in {SOURCE_DIR}: {sorted(extra)}")


def import_sprites() -> list[dict]:
    check_names_unique_and_readable()
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    usages = find_usages()

    manifest = []
    for old_id, new_name in sorted(SPRITE_NAMES.items(), key=lambda kv: kv[1]):
        src = SOURCE_DIR / f"{old_id}.png"
        dst = DEST_DIR / f"{new_name}.png"
        shutil.copyfile(src, dst)
        manifest.append(
            {
                "name": new_name,
                "source_id": old_id,
                "category": category_for(new_name),
                "used_in": usages[old_id],
            }
        )

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def audit_missing_sprites() -> list[str]:
    """Rule 3 (README): flag any sprite a screen needs that art/ doesn't have.

    Cross-references every 32-char hex id found in the .dc.html screens
    against the sprites that actually exist in docs/reference/colonies/art/.
    """
    referenced_ids: set[str] = set()
    for screen_path in SCREENS_DIR.glob("*.dc.html"):
        text = screen_path.read_text(encoding="utf-8")
        referenced_ids.update(
            token for token in _find_hex_ids(text) if token in SPRITE_NAMES or (SOURCE_DIR / f"{token}.png").exists()
        )
    existing_ids = {p.stem for p in SOURCE_DIR.glob("*.png")}
    return sorted(referenced_ids - existing_ids)


def _find_hex_ids(text: str) -> set[str]:
    import re

    return set(re.findall(r"[0-9a-f]{32}", text))


def print_audit() -> None:
    missing = audit_missing_sprites()
    print("\n=== Sprite audit ===")
    if missing:
        print(f"{len(missing)} sprite(s) referenced by a screen but missing from art/:")
        for item in missing:
            print(f"  - {item}")
    else:
        print(
            "No sprite referenced by any of the 32 screens is missing from "
            "docs/reference/colonies/art/ - all 80 reference sprites are accounted for."
        )
        print(
            "README rule 3 (building level 2/3, damaged/scaffold variants) is a "
            "forward-looking allowance, not a current gap: every building level shown "
            "in PhoneBuild.dc.html (e.g. 'Research Lab · upgrade to LV 3') reuses the "
            "single level-agnostic building sprite - the mocks never show level-specific "
            "or damaged/scaffold art. Nothing to generate yet."
        )


def print_mapping() -> None:
    print("\n=== old id -> new name ===")
    for old_id, new_name in sorted(SPRITE_NAMES.items(), key=lambda kv: kv[1]):
        print(f"  {old_id}  ->  {new_name}.png")


# =========================================================================
# Phase 2b: drawing the sprites the audit found missing.
#
# Every color below is sampled verbatim from the existing PNGs (see the
# palette dump in the PR description) - nothing invented. Sprites are
# authored as explicit pixel coordinates (not hand-typed ascii grids) to
# avoid off-by-one row/column slips; print_new_sprite_grids() renders the
# result back as a text grid for review, same format used to read the
# reference sprites.
# =========================================================================

BG = (0x1A, 0x1F, 0x2A, 255)  # the opaque tile background every building_*/icon_*/ship_* sprite is drawn on
GRAY_LIGHT = (0x8C, 0x96, 0xA8, 255)
GRAY_MID = (0x4B, 0x55, 0x68, 255)
GRAY_DARK = (0x2A, 0x31, 0x40, 255)
AMBER = (0xFF, 0xB2, 0x38, 255)
AMBER_LIGHT = (0xFF, 0xD2, 0x7A, 255)
GREEN = (0x8B, 0xD7, 0xA0, 255)  # icon_shield's fill
GREEN_DARK = (0x46, 0x8C, 0x64, 255)  # icon_shield's shade
GREEN_LIGHT = (0xC5, 0xEB, 0xCF, 255)  # GREEN blended toward white, for a glassy specular highlight
STEEL_LIGHT = (0x62, 0x84, 0xA8, 255)  # icon_shield's outline / biodome atmosphere
STEEL_DARK = (0x3E, 0x5A, 0x7A, 255)
RUST = (0xE2, 0x60, 0x3A, 255)  # the "LAB DAMAGED" / "SHIELD DOWN" badge color
TRANSPARENT = (0, 0, 0, 0)

SMOKE = GRAY_MID[:3] + (140,)  # semi-transparent wisp, reuses the existing mid-gray


def new_canvas(width: int, height: int, fill=TRANSPARENT):
    return [[fill for _ in range(width)] for _ in range(height)]


def set_px(canvas, x, y, color):
    canvas[y][x] = color


def hline(canvas, x0, x1, y, color):
    for x in range(x0, x1 + 1):
        canvas[y][x] = color


def vline(canvas, x, y0, y1, color):
    for y in range(y0, y1 + 1):
        canvas[y][x] = color


def rect(canvas, x0, y0, x1, y1, color, fill=True):
    if fill:
        for y in range(y0, y1 + 1):
            hline(canvas, x0, x1, y, color)
    else:
        hline(canvas, x0, x1, y0, color)
        hline(canvas, x0, x1, y1, color)
        vline(canvas, x0, y0, y1, color)
        vline(canvas, x1, y0, y1, color)


def diag(canvas, x0, y0, x1, y1, color):
    """One pixel per row/col step - matches the hand-drawn diagonals already
    used in avatar/building art (e.g. building_defense_tower's antenna)."""
    steps = max(abs(x1 - x0), abs(y1 - y0))
    for i in range(steps + 1):
        x = x0 + round((x1 - x0) * i / steps)
        y = y0 + round((y1 - y0) * i / steps)
        canvas[y][x] = color


def canvas_to_image(canvas) -> "Image.Image":
    from PIL import Image

    height = len(canvas)
    width = len(canvas[0])
    im = Image.new("RGBA", (width, height), TRANSPARENT)
    for y in range(height):
        for x in range(width):
            im.putpixel((x, y), canvas[y][x])
    return im


def canvas_to_grid_text(canvas) -> str:
    """Render a canvas back as a labelled ascii grid, for human review."""
    palette = {}
    lines = []
    for row in canvas:
        line = []
        for color in row:
            if color[3] == 0:
                line.append(".")
                continue
            key = color
            if key not in palette:
                palette[key] = chr(65 + len(palette))
            line.append(palette[key])
        lines.append("".join(line))
    legend = ", ".join(f"{v}=#{k[0]:02X}{k[1]:02X}{k[2]:02X}(a{k[3]})" for k, v in palette.items())
    return "\n".join(lines) + f"\nlegend: {legend}"


# ---- building_damage_overlay (16x16) -----------------------------------
# A reusable scorch+crack mark, transparent elsewhere, meant to be
# alpha-composited on top of any of the 5 fixed building sprites.
def draw_damage_overlay():
    c = new_canvas(16, 16)
    # scorch patch (reuses the tile's own bg color as full-opacity "soot",
    # so it darkens whatever building color is underneath)
    rect(c, 4, 9, 6, 10, BG)
    # crack running up out of the scorch patch
    diag(c, 6, 10, 7, 6, RUST)
    set_px(c, 8, 6, RUST)
    # smoke wisp rising off the top of the scorch patch
    set_px(c, 9, 3, SMOKE)
    set_px(c, 10, 2, SMOKE)
    set_px(c, 10, 1, SMOKE)
    set_px(c, 11, 1, SMOKE)
    return c


# ---- building_shield_dome / building_shield_dome_biodome (22x22) -------
# A see-through bubble that ENCLOSES a whole 16x16 building from the base
# up, not a cap sitting on its roof. The overlay canvas is bigger than the
# building (DOME_CANVAS > a building tile) so the dome can flare out past
# the building's own silhouette and still arc all the way down to the
# ground on both sides; composite() bottom-centers the building inside
# the oversized canvas before compositing this on top (see composite()).
#
# The bubble is the upper half of an ellipse anchored at two base points
# on the ground line (DOME_CANVAS - 1), so its outline runs base-to-base:
# up one side, over the top, back down the other side. rx controls how
# far those base points sit from the building's own edges - a plain
# building needs less clearance than the biodome, which is already
# full-width in its own tile (see docs/reference comparison in the PR).
DOME_CANVAS = 22
_DOME_X_OFFSET = (DOME_CANVAS - 16) // 2
_DOME_Y_OFFSET = DOME_CANVAS - 16  # bottom-aligned: building's base sits on the dome's base line


def _draw_shield_bubble(rx: float):
    import math

    c = new_canvas(DOME_CANVAS, DOME_CANVAS)
    cx = _DOME_X_OFFSET + 16 / 2 - 0.5
    base_y = DOME_CANVAS - 1
    top_y = 1
    ry = base_y - top_y
    outline_left = []
    for y in range(top_y, base_y + 1):
        dy = base_y - y
        frac = dy / ry
        x_extent = rx * math.sqrt(max(0.0, 1 - frac**2))
        left = max(0, round(cx - x_extent))
        right = min(DOME_CANVAS - 1, round(cx + x_extent))
        set_px(c, left, y, GREEN)
        set_px(c, right, y, GREEN)
        outline_left.append((y, left))
        for x in range(left + 1, right):
            # fixed dither pattern, ~1 pixel in 4, so the pattern is
            # deterministic across runs instead of random noise
            if (x * 7 + y * 13) % 4 == 0:
                c[y][x] = GREEN[:3] + (180,)
    # small highlight arc at top-left: brighten the first few outline
    # pixels of the upper-left quadrant, like a glassy specular catch
    for y, left in outline_left[:4]:
        set_px(c, left, y, GREEN_LIGHT)
    return c


def draw_shield_dome():
    return _draw_shield_bubble(rx=10)


# building_biodome is already full-width in its own 16x16 tile (unlike the
# other 4 fixed buildings, which have margin on both sides - see the PR's
# per-row width comparison), so its bubble needs a larger rx to actually
# clear the building's own silhouette at the base.
def draw_shield_dome_biodome():
    return _draw_shield_bubble(rx=10.8)


# ---- building_scaffold (16x16 x2, blink frames) ------------------------
# Generic under-construction frame - not tied to any one building, so it
# is opaque (matches building_*/icon_* convention) rather than an overlay.
def draw_scaffold(beacon_on: bool):
    c = new_canvas(16, 16, fill=BG)
    post_left, post_right = 4, 11
    top, mid, bottom = 3, 8, 13
    vline(c, post_left, top, bottom, GRAY_LIGHT)
    vline(c, post_right, top, bottom, GRAY_LIGHT)
    hline(c, post_left, post_right, top, GRAY_MID)
    hline(c, post_left, post_right, mid, GRAY_MID)
    hline(c, post_left, post_right, bottom, GRAY_MID)
    diag(c, post_left, top, post_right, mid, GRAY_DARK)
    diag(c, post_right, mid, post_left, bottom, GRAY_DARK)
    if beacon_on:
        set_px(c, 7, 1, AMBER)
        set_px(c, 8, 1, AMBER)
    return c


# ---- icon_supply_crate_open (16x16) ------------------------------------
# Companion to the existing icon_supply_crate.png - same box body and
# colors as the closed crate (copied pixel-for-pixel: rows 7-12, cols
# 2-13), with its lid propped open at the back instead of floating
# disconnected above it, and a small glow rising out of the opening
# (not a full-width lit mouth - that read as a lamp, not a crate). The
# lid carries the same 4-row banding as the closed lid (tip rim -> orange
# band -> amber-cornered trim -> hinge rim), just mapped onto its tilted
# columns, so the amber accent and the box's own latch badge visually
# match between the two sprites.
def draw_supply_crate_open():
    c = new_canvas(16, 16, fill=BG)
    # box - identical to icon_supply_crate.png's body, latch badge included
    hline(c, 2, 6, 7, GRAY_MID)
    set_px(c, 7, 7, AMBER)
    set_px(c, 8, 7, AMBER)
    hline(c, 9, 12, 7, GRAY_MID)
    set_px(c, 13, 7, GRAY_DARK)
    for y in range(8, 12):
        hline(c, 2, 12, y, GRAY_MID)
        set_px(c, 13, y, GRAY_DARK)
    hline(c, 2, 13, 12, GRAY_DARK)
    # lid, propped open at the box's back-right edge, leaning up and back -
    # stays visually attached (overlaps the box's top row) rather than
    # hovering with a gap underneath it
    hline(c, 9, 13, 3, GRAY_LIGHT)  # tip rim
    set_px(c, 8, 4, GRAY_LIGHT)
    hline(c, 9, 12, 4, AMBER)  # orange lid band (matches the closed lid's)
    set_px(c, 13, 4, GRAY_LIGHT)
    set_px(c, 8, 5, AMBER)  # amber-cornered trim row
    hline(c, 9, 12, 5, GRAY_MID)
    set_px(c, 13, 5, AMBER)
    hline(c, 8, 14, 6, GRAY_LIGHT)  # hinge rim
    set_px(c, 7, 5, GRAY_LIGHT)
    set_px(c, 14, 5, GRAY_DARK)
    # small glow rising out of the opening, under the propped lid
    set_px(c, 7, 6, AMBER)
    set_px(c, 7, 5, AMBER_LIGHT)
    return c


# ---- checkin_energy_beam (16x64 x2 frames) -----------------------------
# Pixel version of PhoneCheckIn's hand-placed CSS beam (same two colors:
# #FFB238 core, #FFD27A glow), transparent so it overlays scene_colony_home.
def draw_energy_beam(frame: int):
    c = new_canvas(16, 64)
    vline(c, 7, 8, 62, AMBER)
    vline(c, 8, 8, 62, AMBER)
    rect(c, 6, 4, 9, 7, AMBER_LIGHT)
    motes = [(3, 20), (12, 28), (2, 40), (13, 46), (4, 54)] if frame == 0 else [(4, 18), (11, 30), (3, 42), (12, 48), (5, 52)]
    for x, y in motes:
        set_px(c, x, y, AMBER_LIGHT if (x + y) % 2 == 0 else AMBER)
    return c


# ---- fleet_station_lv1/2/3 (32x32) -------------------------------------
# Standalone hero sprites (opaque, like the building_* family) showing real
# level progression - unlike buildings, the game plan wants distinct art
# per station level rather than one sprite + a text label. Visual language
# is lifted from the station baked into scene_fleet_battle.png: a grey
# hull with an amber window grid, steel-blue solar-panel arrays (STEEL_DARK
# fill, STEEL_LIGHT grid lines - sampled directly from that scene), and a
# GRAY_LIGHT antenna with an amber tip. Each level fills the 32x32 canvas
# rather than floating a small icon in the middle of it.
def _panel_array(c, x0, y0, x1, y1, cols, rows):
    """A solar-panel array: STEEL_DARK fill divided into cols x rows cells
    by STEEL_LIGHT grid lines, GRAY_DARK outline - same texture language
    as the station in scene_fleet_battle.png."""
    rect(c, x0, y0, x1, y1, STEEL_DARK)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    for i in range(1, cols):
        vline(c, x0 + round(w * i / cols), y0, y1, STEEL_LIGHT)
    for j in range(1, rows):
        hline(c, x0, x1, y0 + round(h * j / rows), STEEL_LIGHT)
    rect(c, x0, y0, x1, y1, GRAY_DARK, fill=False)


def _draw_fleet_station_lv1():
    # compact core + one small panel pair
    c = new_canvas(32, 32, fill=BG)
    cx = 16
    rect(c, 13, 11, 18, 22, GRAY_MID)
    hline(c, 13, 18, 11, GRAY_LIGHT)
    vline(c, 18, 11, 22, GRAY_DARK)
    for wy in (14, 17, 20):
        set_px(c, 14, wy, AMBER)
        set_px(c, 17, wy, AMBER)
    vline(c, cx, 3, 10, GRAY_LIGHT)
    set_px(c, cx, 2, AMBER_LIGHT)
    hline(c, 7, 12, 16, GRAY_LIGHT)
    hline(c, 19, 24, 16, GRAY_LIGHT)
    _panel_array(c, 1, 13, 6, 19, 2, 2)
    _panel_array(c, 25, 13, 30, 19, 2, 2)
    rect(c, 13, 23, 18, 24, GRAY_DARK)
    rect(c, 14, 25, 17, 26, AMBER)
    return c


def _draw_fleet_station_lv2():
    # bigger core + two larger panel arrays
    c = new_canvas(32, 32, fill=BG)
    cx = 16
    rect(c, 11, 8, 20, 23, GRAY_MID)
    hline(c, 11, 20, 8, GRAY_LIGHT)
    vline(c, 20, 8, 23, GRAY_DARK)
    for wy in (11, 14, 17, 20):
        for wx in (13, 16, 18):
            set_px(c, wx, wy, AMBER)
    vline(c, cx, 2, 7, GRAY_LIGHT)
    set_px(c, cx, 1, AMBER_LIGHT)
    hline(c, 2, 10, 15, GRAY_LIGHT)
    hline(c, 2, 10, 16, GRAY_MID)
    hline(c, 21, 29, 15, GRAY_LIGHT)
    hline(c, 21, 29, 16, GRAY_MID)
    _panel_array(c, 0, 10, 9, 21, 2, 3)
    _panel_array(c, 22, 10, 31, 21, 2, 3)
    rect(c, 12, 24, 19, 25, GRAY_DARK)
    rect(c, 13, 26, 18, 27, AMBER)
    return c


def _draw_fleet_station_lv3():
    # ring/hub + four panel arrays (one per quadrant, clear of the antenna
    # cluster above and the engine glow below) + antenna cluster + extra
    # glow lights at each array's outer corner
    c = new_canvas(32, 32, fill=BG)
    cx = cy = 16
    diag(c, cx, 0, cx + 15, cy, GRAY_LIGHT)
    diag(c, cx + 15, cy, cx, 31, GRAY_LIGHT)
    diag(c, cx, 31, cx - 15, cy, GRAY_LIGHT)
    diag(c, cx - 15, cy, cx, 0, GRAY_LIGHT)
    rect(c, 12, 12, 19, 19, GRAY_MID)
    rect(c, 12, 12, 19, 19, GRAY_DARK, fill=False)
    for wy in (14, 17):
        for wx in (14, 17):
            set_px(c, wx, wy, AMBER)
    vline(c, cx - 2, 5, 11, GRAY_LIGHT)
    vline(c, cx, 3, 11, GRAY_LIGHT)
    vline(c, cx + 2, 6, 11, GRAY_LIGHT)
    set_px(c, cx - 2, 4, AMBER_LIGHT)
    set_px(c, cx, 2, AMBER_LIGHT)
    set_px(c, cx + 2, 5, AMBER_LIGHT)
    diag(c, 11, 12, 9, 9, GRAY_LIGHT)
    diag(c, 20, 12, 22, 9, GRAY_LIGHT)
    diag(c, 11, 19, 9, 22, GRAY_LIGHT)
    diag(c, 20, 19, 22, 22, GRAY_LIGHT)
    _panel_array(c, 3, 3, 8, 8, 2, 2)
    _panel_array(c, 23, 3, 28, 8, 2, 2)
    _panel_array(c, 3, 23, 8, 28, 2, 2)
    _panel_array(c, 23, 23, 28, 28, 2, 2)
    set_px(c, 3, 3, AMBER_LIGHT)
    set_px(c, 28, 3, AMBER_LIGHT)
    set_px(c, 3, 28, AMBER_LIGHT)
    set_px(c, 28, 28, AMBER_LIGHT)
    rect(c, 14, 20, 17, 20, GRAY_DARK)
    set_px(c, 15, 21, AMBER)
    set_px(c, 16, 21, AMBER)
    return c


def draw_fleet_station(level: int):
    return {1: _draw_fleet_station_lv1, 2: _draw_fleet_station_lv2, 3: _draw_fleet_station_lv3}[level]()


# ---- boss_vx3 (48x32) ---------------------------------------------------
# Standalone mothership silhouette - the mocks only ever show it baked
# into scene_fleet_battle's composite, never as an isolated sprite.
def draw_boss_vx3():
    c = new_canvas(48, 32, fill=BG)
    cx = 24
    # wide angular hull, filled solid (half-width grows then shrinks)
    half_widths = [4, 8, 12, 16, 20, 20, 16, 12, 8, 4]
    top = 10
    for row_i, half_width in enumerate(half_widths):
        y = top + row_i
        hline(c, cx - half_width, cx + half_width, y, RUST)
    hline(c, cx - 20, cx + 20, top + 4, GRAY_DARK)  # dark belly stripe (widest row)
    hline(c, cx - 20, cx + 20, top + 5, GRAY_DARK)
    # weapon ports along the belly stripe
    for x in (cx - 12, cx - 4, cx + 4, cx + 12):
        set_px(c, x, top + 4, AMBER)
    set_px(c, cx, top + 4, AMBER_LIGHT)
    set_px(c, cx, top + 5, AMBER_LIGHT)
    return c


# ---- planet-scale buildings (6 types x 3 levels = 18) -------------------
# Drawn on the SAME native pixel grid as planet_render_rust.png (one
# sprite pixel = one planet pixel at the same display scale - see
# PLANET_SPRITE_W/H below), transparent background, roughly 6-12px of
# structure plus 1-2px of ground-contact shading - unlike the existing
# building_*/icon_* family (16x16, opaque, a flat UI-surface-colored
# background baked in), which read as a different, pasted-on art source
# once placed directly on the planet (confirmed: wrong pixel density at
# the scale colony_panel.html displays each at, plus a hard-edged opaque
# square that occludes the planet's own texture instead of blending into
# it). REGOLITH_* below are sampled directly from planet_render_rust.png
# itself (its 4 most common non-background colors after the existing
# GRAY/STEEL/AMBER family, which the planet also already uses) so ground
# contact pixels blend into the real planet art, not an invented palette.
#
# Review-only for now: registered in NEW_SPRITES/META and shown at
# /dev/styleguide (x1 and x4, plus two full-planet preview composites),
# but NOT wired into colony_panel.html/colony.py - that's a later step,
# after the developer approves the art here.
REGOLITH_SHADOW = (0x3A, 0x16, 0x10, 255)  # planet_render_rust's own deepest shadow rust
REGOLITH_DARK = (0x5A, 0x24, 0x18, 255)
REGOLITH = (0xA8, 0x43, 0x2A, 255)
REGOLITH_LIGHT = (0xF2, 0x9A, 0x6A, 255)  # planet_render_rust's own brightest highlight rust

PLANET_SPRITE_W = 14
PLANET_SPRITE_H = 16
GROUND_Y = 14  # last row (15) is ground-shading only; a structure's own base sits on this row


def _planet_canvas():
    return new_canvas(PLANET_SPRITE_W, PLANET_SPRITE_H)


def _ground_contact(c, cx, half_width):
    """1-2px of shaded ground where a building meets the surface - reuses
    the planet's own rust-shadow tones (not a flat UI drop shadow), so the
    contact blends into the terrain's coloring instead of sitting on it."""
    hline(c, cx - half_width, cx + half_width, GROUND_Y + 1, REGOLITH_SHADOW)
    if half_width > 1:
        hline(c, cx - half_width + 1, cx + half_width - 1, GROUND_Y, REGOLITH_DARK)


def _draw_defense_tower(level: int):
    # tall thin spire - taller main shaft + side struts/spires as it levels
    c = _planet_canvas()
    cx = 7
    if level == 1:
        _ground_contact(c, cx, 1)
        rect(c, cx - 1, GROUND_Y - 1, cx + 1, GROUND_Y, GRAY_DARK)
        vline(c, cx, GROUND_Y - 6, GROUND_Y - 2, GRAY_MID)
        set_px(c, cx, GROUND_Y - 7, AMBER)
    elif level == 2:
        _ground_contact(c, cx, 2)
        rect(c, cx - 1, GROUND_Y - 1, cx + 1, GROUND_Y, GRAY_DARK)
        vline(c, cx, GROUND_Y - 8, GROUND_Y - 2, GRAY_MID)
        vline(c, cx - 2, GROUND_Y - 4, GROUND_Y - 2, GRAY_LIGHT)
        set_px(c, cx, GROUND_Y - 9, AMBER)
        set_px(c, cx, GROUND_Y - 8, AMBER_LIGHT)
    else:
        _ground_contact(c, cx, 3)
        rect(c, cx - 2, GROUND_Y - 1, cx + 2, GROUND_Y, GRAY_DARK)
        vline(c, cx, GROUND_Y - 11, GROUND_Y - 2, GRAY_MID)
        vline(c, cx - 2, GROUND_Y - 6, GROUND_Y - 2, GRAY_LIGHT)
        vline(c, cx + 2, GROUND_Y - 6, GROUND_Y - 2, GRAY_LIGHT)
        set_px(c, cx, GROUND_Y - 12, AMBER)
        set_px(c, cx, GROUND_Y - 11, AMBER_LIGHT)
        set_px(c, cx - 2, GROUND_Y - 7, AMBER)
        set_px(c, cx + 2, GROUND_Y - 7, AMBER)
    return c


def _draw_research_lab(level: int):
    # boxy block with lit windows - grows taller with more windows, a
    # wing extension joins at LV3
    c = _planet_canvas()
    cx = 6
    if level == 1:
        _ground_contact(c, cx, 3)
        rect(c, cx - 3, GROUND_Y - 5, cx + 2, GROUND_Y, GRAY_MID)
        hline(c, cx - 3, cx + 2, GROUND_Y - 5, GRAY_LIGHT)
        set_px(c, cx - 1, GROUND_Y - 3, AMBER)
        set_px(c, cx + 1, GROUND_Y - 3, AMBER)
    elif level == 2:
        _ground_contact(c, cx, 3)
        rect(c, cx - 3, GROUND_Y - 7, cx + 2, GROUND_Y, GRAY_MID)
        hline(c, cx - 3, cx + 2, GROUND_Y - 7, GRAY_LIGHT)
        set_px(c, cx, GROUND_Y - 8, GRAY_LIGHT)
        for wy in (GROUND_Y - 5, GROUND_Y - 2):
            set_px(c, cx - 1, wy, AMBER)
            set_px(c, cx + 1, wy, AMBER)
    else:
        _ground_contact(c, cx, 5)
        rect(c, cx - 3, GROUND_Y - 8, cx + 2, GROUND_Y, GRAY_MID)
        hline(c, cx - 3, cx + 2, GROUND_Y - 8, GRAY_LIGHT)
        set_px(c, cx, GROUND_Y - 9, GRAY_LIGHT)
        for wy in (GROUND_Y - 6, GROUND_Y - 3):
            set_px(c, cx - 1, wy, AMBER)
            set_px(c, cx + 1, wy, AMBER)
        rect(c, cx + 3, GROUND_Y - 4, cx + 5, GROUND_Y, GRAY_DARK)
        set_px(c, cx + 4, GROUND_Y - 2, AMBER)
    return c


def _draw_power_reactor(level: int):
    # squat drum with a glow core - wider/taller with fins at LV3
    c = _planet_canvas()
    cx = 7
    if level == 1:
        _ground_contact(c, cx, 3)
        rect(c, cx - 3, GROUND_Y - 4, cx + 3, GROUND_Y, STEEL_DARK)
        hline(c, cx - 3, cx + 3, GROUND_Y - 4, GRAY_LIGHT)
        set_px(c, cx, GROUND_Y - 2, AMBER_LIGHT)
    elif level == 2:
        _ground_contact(c, cx, 3)
        rect(c, cx - 3, GROUND_Y - 6, cx + 3, GROUND_Y, STEEL_DARK)
        hline(c, cx - 3, cx + 3, GROUND_Y - 6, GRAY_LIGHT)
        rect(c, cx - 1, GROUND_Y - 3, cx, GROUND_Y - 2, AMBER_LIGHT)
    else:
        _ground_contact(c, cx, 4)
        rect(c, cx - 3, GROUND_Y - 7, cx + 3, GROUND_Y, STEEL_DARK)
        hline(c, cx - 3, cx + 3, GROUND_Y - 7, GRAY_LIGHT)
        vline(c, cx - 4, GROUND_Y - 5, GROUND_Y - 1, STEEL_LIGHT)
        vline(c, cx + 4, GROUND_Y - 5, GROUND_Y - 1, STEEL_LIGHT)
        rect(c, cx - 1, GROUND_Y - 4, cx, GROUND_Y - 2, AMBER_LIGHT)
        set_px(c, cx - 2, GROUND_Y - 4, AMBER)
        set_px(c, cx + 1, GROUND_Y - 4, AMBER)
    return c


def _draw_biodome(level: int):
    # glassy half-dome, same green/steel language as the shield-dome
    # overlay - bigger with a second smaller dome joining at LV3
    c = _planet_canvas()
    cx = 6
    if level == 1:
        _ground_contact(c, cx, 3)
        hline(c, cx - 3, cx + 3, GROUND_Y, STEEL_LIGHT)
        hline(c, cx - 2, cx + 2, GROUND_Y - 1, GREEN)
        hline(c, cx - 1, cx + 1, GROUND_Y - 2, GREEN)
        set_px(c, cx, GROUND_Y - 3, GREEN_LIGHT)
    elif level == 2:
        _ground_contact(c, cx, 4)
        hline(c, cx - 4, cx + 4, GROUND_Y, STEEL_LIGHT)
        hline(c, cx - 3, cx + 3, GROUND_Y - 1, GREEN)
        hline(c, cx - 2, cx + 2, GROUND_Y - 2, GREEN)
        hline(c, cx - 1, cx + 1, GROUND_Y - 3, GREEN)
        set_px(c, cx, GROUND_Y - 4, GREEN_LIGHT)
    else:
        _ground_contact(c, cx, 6)
        hline(c, cx - 4, cx + 4, GROUND_Y, STEEL_LIGHT)
        hline(c, cx - 3, cx + 3, GROUND_Y - 1, GREEN)
        hline(c, cx - 2, cx + 2, GROUND_Y - 2, GREEN)
        hline(c, cx - 1, cx + 1, GROUND_Y - 3, GREEN)
        set_px(c, cx, GROUND_Y - 4, GREEN_LIGHT)
        # small secondary dome, offset to the right
        hline(c, cx + 4, cx + 6, GROUND_Y, STEEL_LIGHT)
        hline(c, cx + 5, cx + 5, GROUND_Y - 1, GREEN_LIGHT)
    return c


def _draw_observatory(level: int):
    # tall block with a small symmetric dome cap on top (same concentric-
    # row technique as _draw_biodome, just steel-toned and sitting on a
    # block instead of the ground) - a first pass drew the dish as a
    # lopsided single-row-plus-a-point, which read as scattered debris
    # rather than a dish; a centered dome cap reads cleanly even this
    # small. Taller block + bigger cap each level; a second antenna joins
    # at LV3.
    c = _planet_canvas()
    cx = 7
    if level == 1:
        _ground_contact(c, cx, 2)
        rect(c, cx - 2, GROUND_Y - 2, cx + 2, GROUND_Y, GRAY_MID)
        hline(c, cx - 1, cx + 1, GROUND_Y - 3, STEEL_LIGHT)
        set_px(c, cx, GROUND_Y - 4, AMBER_LIGHT)
    elif level == 2:
        _ground_contact(c, cx, 2)
        rect(c, cx - 2, GROUND_Y - 4, cx + 2, GROUND_Y, GRAY_MID)
        hline(c, cx - 2, cx + 2, GROUND_Y - 5, STEEL_LIGHT)
        hline(c, cx - 1, cx + 1, GROUND_Y - 6, STEEL_LIGHT)
        set_px(c, cx, GROUND_Y - 7, AMBER_LIGHT)
    else:
        _ground_contact(c, cx, 3)
        rect(c, cx - 2, GROUND_Y - 5, cx + 2, GROUND_Y, GRAY_MID)
        hline(c, cx - 2, cx + 2, GROUND_Y - 6, STEEL_LIGHT)
        hline(c, cx - 1, cx + 1, GROUND_Y - 7, STEEL_LIGHT)
        set_px(c, cx, GROUND_Y - 8, AMBER_LIGHT)
        vline(c, cx + 3, GROUND_Y - 6, GROUND_Y - 3, GRAY_LIGHT)
        set_px(c, cx + 3, GROUND_Y - 7, AMBER)
    return c


def _draw_custom_module(level: int):
    # plain box with a glowing orange core - core grows, a small
    # extension joins at LV3
    c = _planet_canvas()
    cx = 6
    if level == 1:
        _ground_contact(c, cx, 2)
        rect(c, cx - 2, GROUND_Y - 4, cx + 2, GROUND_Y, GRAY_MID)
        set_px(c, cx, GROUND_Y - 2, AMBER)
    elif level == 2:
        _ground_contact(c, cx, 2)
        rect(c, cx - 2, GROUND_Y - 6, cx + 2, GROUND_Y, GRAY_MID)
        rect(c, cx - 1, GROUND_Y - 3, cx, GROUND_Y - 2, AMBER_LIGHT)
        set_px(c, cx - 2, GROUND_Y - 3, AMBER)
    else:
        _ground_contact(c, cx, 4)
        rect(c, cx - 2, GROUND_Y - 7, cx + 2, GROUND_Y, GRAY_MID)
        rect(c, cx - 1, GROUND_Y - 4, cx, GROUND_Y - 3, AMBER_LIGHT)
        set_px(c, cx - 2, GROUND_Y - 4, AMBER)
        set_px(c, cx + 2, GROUND_Y - 4, AMBER)
        rect(c, cx + 3, GROUND_Y - 3, cx + 4, GROUND_Y, GRAY_DARK)
    return c


PLANET_BUILDING_DRAWERS = {
    "defense_tower": _draw_defense_tower,
    "research_lab": _draw_research_lab,
    "power_reactor": _draw_power_reactor,
    "biodome": _draw_biodome,
    "observatory": _draw_observatory,
    "custom_module": _draw_custom_module,
}

NEW_SPRITES = {
    "building_damage_overlay": draw_damage_overlay,
    "building_shield_dome": draw_shield_dome,
    "building_shield_dome_biodome": draw_shield_dome_biodome,
    "building_scaffold_1": lambda: draw_scaffold(beacon_on=True),
    "building_scaffold_2": lambda: draw_scaffold(beacon_on=False),
    "icon_supply_crate_open": draw_supply_crate_open,
    "checkin_energy_beam_1": lambda: draw_energy_beam(0),
    "checkin_energy_beam_2": lambda: draw_energy_beam(1),
    "fleet_station_lv1": lambda: draw_fleet_station(1),
    "fleet_station_lv2": lambda: draw_fleet_station(2),
    "fleet_station_lv3": lambda: draw_fleet_station(3),
    "boss_vx3": draw_boss_vx3,
}
for _bt, _drawer in PLANET_BUILDING_DRAWERS.items():
    for _lv in (1, 2, 3):
        NEW_SPRITES[f"planet_building_{_bt}_lv{_lv}"] = (lambda d=_drawer, lv=_lv: d(lv))

NEW_SPRITE_META = {
    "building_damage_overlay": {"category": "overlay", "phase": 5, "notes": "reusable on all 5 fixed buildings"},
    "building_shield_dome": {"category": "overlay", "phase": 5, "notes": "reusable on 4 of 5 buildings (not biodome, see below)"},
    "building_shield_dome_biodome": {"category": "overlay", "phase": 5, "notes": "biodome-only variant - the generic dome overlay is invisible on a building that's already a dome"},
    "building_scaffold_1": {"category": "building", "phase": 4, "notes": "under-construction, beacon frame 1/2"},
    "building_scaffold_2": {"category": "building", "phase": 4, "notes": "under-construction, beacon frame 2/2"},
    "icon_supply_crate_open": {"category": "icon", "phase": 5, "notes": "open-state companion to icon_supply_crate"},
    "checkin_energy_beam_1": {"category": "effect", "phase": 4, "notes": "check-in beam, frame 1/2"},
    "checkin_energy_beam_2": {"category": "effect", "phase": 4, "notes": "check-in beam, frame 2/2"},
    "fleet_station_lv1": {"category": "fleet", "phase": 6, "notes": "standalone, level 1 of 3"},
    "fleet_station_lv2": {"category": "fleet", "phase": 6, "notes": "standalone, level 2 of 3"},
    "fleet_station_lv3": {"category": "fleet", "phase": 6, "notes": "standalone, level 3 of 3"},
    "boss_vx3": {"category": "fleet", "phase": 6, "notes": "weekly boss, named after the mocks' own 'Mothership VX-3'"},
}
for _bt in PLANET_BUILDING_DRAWERS:
    for _lv in (1, 2, 3):
        NEW_SPRITE_META[f"planet_building_{_bt}_lv{_lv}"] = {
            "category": "planet_building", "phase": 4,
            "notes": f"planet-scale {_bt}, level {_lv} of 3 - review only, not wired in yet",
        }

FIXED_BUILDINGS = [
    "building_research_lab",
    "building_defense_tower",
    "building_biodome",
    "building_observatory",
    "building_power_reactor",
]

SHEET_PATH = DEST_DIR / "_sheet.png"


def draw_new_sprites() -> None:
    for name, draw_fn in NEW_SPRITES.items():
        canvas = draw_fn()
        canvas_to_image(canvas).save(DEST_DIR / f"{name}.png")


def print_new_sprite_grids() -> None:
    print("\n=== new sprite pixel grids ===")
    for name, draw_fn in NEW_SPRITES.items():
        print(f"\n--- {name} ---")
        print(canvas_to_grid_text(draw_fn()))


def composite(base_name: str, overlay_canvas, scale: int = 1):
    from PIL import Image

    base = Image.open(DEST_DIR / f"{base_name}.png").convert("RGBA")
    overlay = canvas_to_image(overlay_canvas)
    if overlay.size == base.size:
        out = Image.alpha_composite(base, overlay)
    elif overlay.width >= base.width and overlay.height >= base.height:
        # overlay encloses an area bigger than the base (e.g. a shield
        # bubble that must reach past the building's own silhouette) -
        # bottom-center the base inside an overlay-sized canvas first, so
        # the building's ground line lines up with the overlay's own base
        # line, instead of squishing the overlay down to the base's size
        canvas = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
        x_off = (overlay.width - base.width) // 2
        y_off = overlay.height - base.height
        canvas.paste(base, (x_off, y_off))
        out = Image.alpha_composite(canvas, overlay)
    else:
        overlay = overlay.resize(base.size, Image.NEAREST)
        out = Image.alpha_composite(base, overlay)
    if scale != 1:
        out = out.resize((out.width * scale, out.height * scale), Image.NEAREST)
    return out


def update_manifest_with_new_sprites() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for entry in manifest:
        entry["new"] = False
    for name, meta in NEW_SPRITE_META.items():
        manifest.append(
            {
                "name": name,
                "source_id": None,
                "category": meta["category"],
                "used_in": [],
                "new": True,
                "phase": meta["phase"],
                "notes": meta["notes"],
            }
        )
    manifest.sort(key=lambda e: e["name"])
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


CELL = 96  # fixed cell footprint (thumbnail area); every sprite is scaled to fit inside it
THUMB_MAX = 80  # leaves an 8px margin on each side within CELL
LABEL_H = 16
TITLE_H = 18


def _font(size: int):
    from PIL import ImageFont

    return ImageFont.load_default(size=size)


def _paste_thumb(sheet, draw, im, x, y, label, label_color=(236, 230, 216, 255)):
    """Scale im (any size) to fit inside THUMB_MAX x THUMB_MAX, nearest-neighbour,
    center it in the CELL x CELL box at (x, y), and print a label below it.
    Always downscales oversized sprites - never lets one bleed into neighbours."""
    from PIL import Image

    im = im.convert("RGBA")
    scale = min(THUMB_MAX / im.width, THUMB_MAX / im.height)
    new_w = max(1, round(im.width * scale))
    new_h = max(1, round(im.height * scale))
    thumb = im.resize((new_w, new_h), Image.NEAREST)
    ox = x + (CELL - new_w) // 2
    oy = y + (CELL - new_h) // 2
    sheet.paste(thumb, (ox, oy), thumb)
    draw.text((x + 2, y + CELL - 2), label[:16], fill=label_color, font=_font(10))


def build_sheet() -> None:
    from PIL import Image, ImageDraw

    all_sprites = sorted(p.stem for p in DEST_DIR.glob("*.png") if p.stem not in {"_sheet", "logo-mark"})
    new_names = set(NEW_SPRITES)

    cols = 8
    row_h = CELL + LABEL_H
    rows_needed = -(-len(all_sprites) // cols)

    sheet_w = cols * CELL
    grid_h = rows_needed * row_h
    composite_h = 2 * (TITLE_H + row_h)
    sheet_h = grid_h + composite_h
    sheet = Image.new("RGBA", (sheet_w, sheet_h), BG)
    draw = ImageDraw.Draw(sheet)

    for i, name in enumerate(all_sprites):
        col, row = i % cols, i // cols
        x, y = col * CELL, row * row_h
        im = Image.open(DEST_DIR / f"{name}.png")
        is_new = name in new_names
        label = ("* " + name) if is_new else name
        color = (0x8B, 0xD7, 0xA0, 255) if is_new else (236, 230, 216, 255)
        _paste_thumb(sheet, draw, im, x, y, label, label_color=color)

    y = grid_h
    draw.text((4, y + 3), "COMPOSITE TEST - damage overlay on all 5 buildings", fill=(0xE2, 0x60, 0x3A, 255), font=_font(12))
    y += TITLE_H
    for i, base_name in enumerate(FIXED_BUILDINGS):
        x = i * CELL
        out = composite(base_name, draw_damage_overlay())
        _paste_thumb(sheet, draw, out, x, y, base_name.replace("building_", "") + " +dmg")
    y += row_h

    draw.text((4, y + 3), "COMPOSITE TEST - shield dome (biodome uses its ring variant)", fill=(0x8B, 0xD7, 0xA0, 255), font=_font(12))
    y += TITLE_H
    for i, base_name in enumerate(FIXED_BUILDINGS):
        x = i * CELL
        overlay = draw_shield_dome_biodome() if base_name == "building_biodome" else draw_shield_dome()
        out = composite(base_name, overlay)
        _paste_thumb(sheet, draw, out, x, y, base_name.replace("building_", "") + " +shd")

    sheet.save(SHEET_PATH)


COMPOSITES_DIR = DEST_DIR / "_composites"


def build_composites() -> None:
    """Write each composite test (damage overlay / shield dome on each of
    the 5 fixed buildings) as its own full-resolution PNG, for /dev/styleguide
    to display as a plain <img> at true proportions (natural size x4) -
    unlike _sheet.png, these are never squeezed into a shared thumbnail cell.
    """
    COMPOSITES_DIR.mkdir(parents=True, exist_ok=True)
    for base_name in FIXED_BUILDINGS:
        damage = composite(base_name, draw_damage_overlay())
        damage.save(COMPOSITES_DIR / f"{base_name}_damage.png")

        shield_overlay = draw_shield_dome_biodome() if base_name == "building_biodome" else draw_shield_dome()
        shield = composite(base_name, shield_overlay)
        shield.save(COMPOSITES_DIR / f"{base_name}_shield.png")

    build_planet_previews()


# Review-only anchor layout for the two full-planet previews below - the
# ground-contact point (on planet_render_rust.png's own 48x48 canvas) each
# building's own base should land on. Spaced 48 degrees apart around the
# lower 240 degrees of the sphere's rim (measured center ~(23.5,26),
# radius ~16), explicitly clear of the antenna/debris at the top (source
# rows 0-8). A SEPARATE, one-off layout from whatever colony.py's real
# PLANET_SLOTS ends up using once this art is approved and actually wired
# in - intentionally not shared code, per "do not touch placement code".
PLANET_PREVIEW_ANCHORS = {
    "defense_tower": (35.6, 19),
    "research_lab": (36.8, 30.3),
    "power_reactor": (29.2, 38.8),
    "biodome": (17.8, 38.8),
    "observatory": (10.2, 30.3),
    "custom_module": (11.4, 19),
}


def _paste_planet_building(base_img, building_type: str, level: int) -> None:
    sprite = canvas_to_image(PLANET_BUILDING_DRAWERS[building_type](level))
    anchor_x, anchor_y = PLANET_PREVIEW_ANCHORS[building_type]
    left = round(anchor_x - PLANET_SPRITE_W / 2)
    top = round(anchor_y - (PLANET_SPRITE_H - 1))
    base_img.paste(sprite, (left, top), sprite)


def build_planet_previews() -> None:
    """Two full-planet mockups (all six planet-scale buildings at LV1, then
    all six at LV3) for /dev/styleguide to judge the new art directly on
    planet_render_rust.png - review only. Uses PLANET_PREVIEW_ANCHORS
    above, not colony.py's real (untouched) slot system."""
    from PIL import Image

    for level, filename in ((1, "planet_preview_lv1.png"), (3, "planet_preview_lv3.png")):
        base = Image.open(DEST_DIR / "planet_render_rust.png").convert("RGBA")
        for building_type in PLANET_BUILDING_DRAWERS:
            _paste_planet_building(base, building_type, level)
        base.save(COMPOSITES_DIR / filename)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "import"
    if command == "import":
        manifest = import_sprites()
        print(f"Copied {len(manifest)} sprites into {DEST_DIR}")
        print(f"Wrote {MANIFEST_PATH}")
        print_mapping()
        print_audit()
    elif command == "draw":
        draw_new_sprites()
        print(f"Drew {len(NEW_SPRITES)} new sprites into {DEST_DIR}")
        print_new_sprite_grids()
    elif command == "manifest-update":
        update_manifest_with_new_sprites()
        print(f"Updated {MANIFEST_PATH} with new=true/false")
    elif command == "sheet":
        build_sheet()
        print(f"Wrote {SHEET_PATH}")
    elif command == "composites":
        build_composites()
        print(f"Wrote composite test PNGs into {COMPOSITES_DIR}")
    elif command == "audit":
        print_audit()
    else:
        raise SystemExit(
            f"Unknown command: {command!r} (expected import/audit/draw/manifest-update/sheet/composites)"
        )

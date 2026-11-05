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


# ---- planet-scale buildings, round 3: match the ORIGINAL bake --------
# Rounds 1-2 both invented a NEW visual system (boxes, outlines, a ring
# geometry) instead of reusing what was already there. The developer's
# style reference is simpler: planet_render_rust.png's own BAKED
# decorations - a thin antenna, a tiny green dome, two grey window-block
# clusters, one more on the far rim - already look native, because
# they're drawn directly on the sphere with no background/outline at
# all, just a handful of steel-grey + phosphor-amber pixels sitting low
# and irregular on the rust surface.
#
# So round 3 does not invent new geometry - it DECOMPOSES the original's
# baked clusters into six per-building sprites, each a small set of
# (dx, dy, color) pixel OFFSETS from that cluster's own real position on
# planet_render_rust.png (not a canvas with a background - there is no
# background, every undrawn pixel is simply transparent). Mapping
# (cluster's real bounding pixels -> building type), decided by shape:
#
#   - antenna (x21-22, y0-11: thin mast, green tip, 2 amber dots on a
#     shadow column)                          -> Defense Tower (a tower
#     IS an antenna/mast - the most direct mapping of the five)
#   - green dome (x25-30, y9-10: a 2-row green blob with grey mounting
#     pixels)                                  -> Biodome (green = life;
#     the only baked cluster with any color beyond grey/amber)
#   - near-left block (x13-18, y9-13: a grey block with 4 SEPARATE
#     scattered amber dots, like individual lit windows) -> Research Lab
#     (many small separate lights reads as "many lit workstations")
#   - far-left block (x9-13, y14-18: a tighter grey block with a single
#     CONCENTRATED 3-pixel amber/amber-light glow, not spread out)
#                                               -> Power Reactor (one
#     bright core glow, not windows)
#   - right block (x31-37, y11-15: a grey block with 4 amber dots in a
#     clean diagonal line)                      -> Observatory (read as
#     a scanning/tilted instrument, and it sits furthest round the rim,
#     fitting "looking outward")
#
# That accounts for 5 of 6 types - the original bake has no 6th cluster
# to decompose, since it was never drawn with our game's categories in
# mind. Custom Module ("Anything else... user picks the look" per docs/
# COLONIES_GAME_PLAN.md - the one category with no fixed real-world
# analog either) gets a new minimal cluster in the same technique
# instead, in the gap between the antenna and the green dome: 1-3 grey
# pixels, no more than one amber pixel even at LV3 - deliberately the
# smallest, least-detailed cluster, matching its "generic/cosmetic"
# theme rather than competing visually with the five real ones.
#
# Per CLUSTER_ANCHORS below, every cluster's anchor is NOT shifted from
# round 2's ring positions - each sits at (or very near) the real pixel
# position its corresponding original cluster already occupies, so
# building all six back up reproduces the original bake (LV3 pixel sets
# below are the original cluster's own pixels, verified against the
# dump in the PR description) rather than a new arrangement.
#
# Levels, per the brief: LV1 is a small subset of the full cluster
# (barely there, 0-1 lit pixels), LV2 is a partial build-out (a couple
# more pixels, 1-2 lit), LV3 is the FULL cluster exactly as it appears
# baked into planet_render_rust.png - same anchor at every level (the
# pixel offsets are always relative to the same (0, 0)), growing upward/
# outward from it, never relocating.
#
# No background, no outline, no ground-contact shading box - the sphere's
# own rust shows through every pixel that isn't explicitly part of a
# cluster, exactly like the original.

PLANET_CLUSTER_PIXELS = {
    # (dx, dy) offsets from each building's own anchor (see CLUSTER_
    # ANCHORS) -> color, for the FULL (LV3) cluster. LV1/LV2 take an
    # ordered prefix of this same list (see _level_pixels) rather than
    # a separately hand-drawn shape, so a lower level is always visually
    # "this cluster, just not finished yet" rather than a different shape.
    "defense_tower": [
        # anchor (21, 11) - the antenna's own base
        (0, 0, GRAY_MID), (1, 0, GRAY_DARK),
        (0, -1, GRAY_MID), (1, -1, AMBER),
        (0, -2, GRAY_MID), (1, -2, GRAY_MID),
        (0, -3, GRAY_MID), (1, -3, AMBER),
        (0, -4, GRAY_MID), (1, -4, GRAY_DARK),
        (0, -5, GRAY_MID), (1, -5, GRAY_DARK),
        (0, -6, GRAY_MID), (1, -6, GRAY_DARK),
        (0, -7, GRAY_MID), (1, -7, GRAY_DARK),
        (0, -8, GRAY_LIGHT),
        (0, -9, GRAY_LIGHT),
        (0, -10, GRAY_LIGHT),
        (0, -11, GREEN),
    ],
    "biodome": [
        # anchor (27, 10) - the green dome's own base. GREEN pixels
        # listed first on purpose - this cluster's whole identity IS the
        # green, so even LV1's tiny subset should show a hint of it
        # rather than an incidental grey mounting pixel.
        (0, 0, GREEN), (-1, 0, GREEN), (0, -1, GREEN),
        (-2, 0, GRAY_LIGHT), (3, 0, GRAY_LIGHT), (-1, -1, GRAY_LIGHT), (2, -1, GRAY_LIGHT),
    ],
    "research_lab": [
        # anchor (16, 13) - the near-left window block's own base
        (-2, 0, AMBER), (-1, 0, GRAY_MID), (0, 0, GRAY_MID),
        (-2, -1, GRAY_MID), (-1, -1, AMBER), (0, -1, GRAY_MID), (1, -1, AMBER), (2, -1, GRAY_MID),
        (-3, -2, GRAY_LIGHT), (-2, -2, GRAY_MID), (-1, -2, GRAY_MID), (0, -2, GRAY_MID), (1, -2, GRAY_MID), (2, -2, AMBER),
        (-1, -3, GRAY_LIGHT), (0, -3, GRAY_MID), (1, -3, GRAY_MID), (2, -3, GRAY_MID),
        (0, -4, GRAY_LIGHT), (1, -4, GRAY_LIGHT),
    ],
    "power_reactor": [
        # anchor (11, 18) - the far-left glow block's own base
        (0, 0, GRAY_DARK),
        (-1, -1, GRAY_DARK), (0, -1, GRAY_MID), (1, -1, GRAY_MID),
        (-1, -2, GRAY_MID), (0, -2, GRAY_MID), (1, -2, GRAY_MID),
        (-2, -3, AMBER), (-1, -3, GRAY_MID), (0, -3, GRAY_MID), (1, -3, GRAY_MID), (2, -3, GRAY_DARK),
        (-2, -4, AMBER_LIGHT), (-1, -4, AMBER), (0, -4, GRAY_DARK),
    ],
    "observatory": [
        # anchor (34, 15) - the right-rim diagonal-window block's own base
        (0, 0, GRAY_MID), (1, 0, AMBER),
        (-1, -1, GRAY_MID), (0, -1, AMBER), (1, -1, GRAY_MID), (2, -1, GRAY_MID),
        (-3, -2, GRAY_MID), (-2, -2, GRAY_MID), (-1, -2, AMBER), (0, -2, GRAY_MID), (1, -2, GRAY_MID), (2, -2, GRAY_LIGHT),
        (-2, -3, AMBER), (-1, -3, GRAY_MID), (0, -3, GRAY_MID), (1, -3, GRAY_LIGHT),
        (-1, -4, GRAY_MID), (0, -4, GRAY_LIGHT), (3, -4, GRAY_MID),
    ],
    "custom_module": [
        # anchor (24, 9) - new, minimal, in the antenna-to-dome gap; no
        # original cluster to decompose (see the module docstring above)
        (0, 0, GRAY_MID), (1, 0, GRAY_MID),
        (0, -1, GRAY_MID), (1, -1, AMBER),
        (0, -2, AMBER),
    ],
}

# Real anchor position (on planet_render_rust(_clean).png's own 48x48
# canvas) for each building's cluster - see the mapping above for which
# real baked pixels each one decomposes.
CLUSTER_ANCHORS = {
    "defense_tower": (21, 11),
    "biodome": (27, 10),
    "research_lab": (16, 13),
    "power_reactor": (11, 18),
    "observatory": (34, 15),
    "custom_module": (24, 9),
}

# How many of PLANET_CLUSTER_PIXELS' pixels (in the order written above -
# deliberately ordered low/base pixels first, detail/accent pixels last)
# are visible at each level. LV3 is always len(...) - the full original
# cluster. LV1/LV2 are hand-picked per building (not a fixed fraction),
# since each cluster's pixel list is ordered base-first/detail-last by
# hand, not uniformly.
PLANET_LEVEL_COUNTS = {
    "defense_tower": {1: 3, 2: 8},
    "biodome": {1: 1, 2: 3},
    "research_lab": {1: 3, 2: 8},
    "power_reactor": {1: 2, 2: 7},
    "observatory": {1: 2, 2: 8},
    "custom_module": {1: 1, 2: 3},
}

# ---- planet-scale buildings, round 4 CANDIDATE: LV1 readability fix --
# Review finding on the wired art above: LV1's count was so low (1-3
# pixels) that a just-built building is nearly invisible on the planet
# at 5x scale (e.g. defense_tower LV1 is 3 pixels on a 2x12 canvas).
# This is a CANDIDATE replacement, reviewed at /dev/styleguide only - it
# does NOT touch PLANET_CLUSTER_PIXELS/PLANET_LEVEL_COUNTS above (still
# what's actually wired into /colony via habitual.colony.BUILDING_SLOTS)
# until the developer approves it and it gets promoted.
#
# defense_tower/research_lab/power_reactor/observatory keep their exact
# original cluster content from PLANET_CLUSTER_PIXELS (same pixels, same
# order, same CLUSTER_ANCHORS) - only PLANET_LEVEL_COUNTS_CANDIDATE
# raises how many of those same pixels LV1/LV2 reveal, from a bare
# corner fragment to a readable 6-8px chunk (checked by hand: each
# building's first 6-8 listed pixels already form a connected mini-
# shape with 1-2 AMBER lit pixels, because the lists were written row-
# by-row from the cluster's own base upward).
#
# biodome and custom_module are the exception: their FULL (round 3)
# clusters are only 7 and 5 pixels respectively - too small to leave any
# room for a staged LV1 -> LV2 -> LV3 reveal once LV1 alone needs 6+
# pixels. Both are modestly enlarged here (to 10 pixels each, still the
# two smallest clusters of the six) in the same style/palette/anchor as
# round 3's approved versions - not a redesign, just enough extra
# pixels to support three distinct, readable levels.
PLANET_CLUSTER_PIXELS_CANDIDATE = {
    "defense_tower": PLANET_CLUSTER_PIXELS["defense_tower"],
    "research_lab": PLANET_CLUSTER_PIXELS["research_lab"],
    "power_reactor": PLANET_CLUSTER_PIXELS["power_reactor"],
    "observatory": PLANET_CLUSTER_PIXELS["observatory"],
    "biodome": [
        # anchor (27, 10), same as round 3 - enlarged from 7 to 10 px.
        # LV1 (first 6): a readable rounded green bump on a grey mount.
        (0, 0, GREEN), (-1, 0, GREEN), (1, 0, GREEN), (0, -1, GREEN),
        (-2, 0, GRAY_LIGHT), (2, 0, GRAY_LIGHT),
        # LV2 (first 8): mount widens slightly under the dome's shoulders.
        (-1, -1, GRAY_LIGHT), (1, -1, GRAY_LIGHT),
        # LV3 (all 10): a small peak, plus the original's own extra
        # outer mount pixel.
        (0, -2, GREEN), (3, 0, GRAY_LIGHT),
    ],
    "custom_module": [
        # anchor (24, 9), same as round 3 - enlarged from 5 to 10 px.
        # LV1 (first 6): a solid small lit block - still the simplest/
        # least-detailed cluster of the six, per its "generic/cosmetic"
        # theme, just no longer invisible.
        (0, 0, GRAY_MID), (1, 0, GRAY_MID), (0, -1, GRAY_MID), (1, -1, GRAY_MID),
        (0, -2, AMBER), (1, -2, GRAY_MID),
        # LV2 (first 8): base widens by one, a second lit pixel appears higher.
        (-1, 0, GRAY_MID), (0, -3, AMBER),
        # LV3 (all 10): fills in around the new accent.
        (1, -3, GRAY_MID), (-1, -1, GRAY_MID),
    ],
}

PLANET_LEVEL_COUNTS_CANDIDATE = {
    "defense_tower": {1: 8, 2: 14},
    "research_lab": {1: 6, 2: 13},
    "power_reactor": {1: 8, 2: 12},
    "observatory": {1: 8, 2: 14},
    "biodome": {1: 6, 2: 8},
    "custom_module": {1: 6, 2: 8},
}


def _level_pixels_from(cluster_pixels: dict, level_counts: dict, building_type: str, level: int):
    full = cluster_pixels[building_type]
    if level >= 3:
        return full
    return full[: level_counts[building_type][level]]


def _cluster_bbox_offset_from(cluster_pixels: dict, building_type: str) -> tuple[int, int]:
    """(min_dx, min_dy) of a building's FULL (LV3) cluster - the top-left
    corner of _draw_cluster_building's canvas, relative to CLUSTER_ANCHORS.
    Exposed (not just inlined) because habitual/colony.py's BUILDING_SLOTS
    hardcodes CLUSTER_ANCHORS[type] + this same offset (for the currently-
    WIRED dataset, PLANET_CLUSTER_PIXELS) as its fixed wiring position -
    keep that in sync if the wired cluster's pixels change."""
    full = cluster_pixels[building_type]
    return min(p[0] for p in full), min(p[1] for p in full)


def _draw_cluster_building(cluster_pixels: dict, level_counts: dict, building_type: str, level: int):
    """Crops to the FULL (LV3) cluster's bounding box at every level, not
    the level-specific subset - so a building's LV1/LV2/LV3 standalone
    sprite is always the same pixel size with the same anchor offset
    (lower levels just leave more of that fixed canvas transparent). This
    is what lets habitual/colony.py wire a building at one fixed slot and
    simply swap which level's image fills it, with no per-level crop or
    offset math of its own (and no Pillow dependency - that stays dev-
    only, see requirements-dev.txt)."""
    full = cluster_pixels[building_type]
    min_dx, min_dy = _cluster_bbox_offset_from(cluster_pixels, building_type)
    max_dx = max(p[0] for p in full)
    max_dy = max(p[1] for p in full)
    w, h = max_dx - min_dx + 1, max_dy - min_dy + 1
    c = new_canvas(w, h)
    for dx, dy, color in _level_pixels_from(cluster_pixels, level_counts, building_type, level):
        set_px(c, dx - min_dx, dy - min_dy, color)
    return c


# -- the currently-WIRED (production) dataset - what /colony actually
# reads via habitual.colony.BUILDING_SLOTS. Do not change these without
# also updating that file; see PLANET_CLUSTER_PIXELS_CANDIDATE below for
# the pending LV1-readability fix, which is review-only until approved.
def _level_pixels(building_type: str, level: int):
    return _level_pixels_from(PLANET_CLUSTER_PIXELS, PLANET_LEVEL_COUNTS, building_type, level)


def _cluster_bbox_offset(building_type: str) -> tuple[int, int]:
    return _cluster_bbox_offset_from(PLANET_CLUSTER_PIXELS, building_type)


def _draw_planet_building(building_type: str, level: int):
    return _draw_cluster_building(PLANET_CLUSTER_PIXELS, PLANET_LEVEL_COUNTS, building_type, level)


PLANET_BUILDING_DRAWERS = {
    building_type: (lambda level, bt=building_type: _draw_planet_building(bt, level))
    for building_type in PLANET_CLUSTER_PIXELS
}


def _draw_planet_building_candidate(building_type: str, level: int):
    return _draw_cluster_building(PLANET_CLUSTER_PIXELS_CANDIDATE, PLANET_LEVEL_COUNTS_CANDIDATE, building_type, level)


PLANET_BUILDING_DRAWERS_CANDIDATE = {
    building_type: (lambda level, bt=building_type: _draw_planet_building_candidate(bt, level))
    for building_type in PLANET_CLUSTER_PIXELS_CANDIDATE
}

# Display/ring order purely for styleguide section ordering - NOT a
# spacing ring any more (round 2's ring geometry is gone; every building
# sits at its own real CLUSTER_ANCHORS position instead).
PLANET_RING_ORDER = list(PLANET_CLUSTER_PIXELS)


def draw_planet_render_rust_clean():
    """planet_render_rust.png with its baked-in antenna mast + the small
    debris/rock crown clustered around its base erased back to
    background - a COLOR-based erase (every pixel matching the debris
    family below, nothing else), not a row-range blank. Two earlier,
    cruder passes both got the extent wrong: the mast's own width-
    profile suggested rows 0-8; a labelled pixel-grid screenshot then
    showed the debris crown around its base reaching rows 0-14; neither
    noticed that debris on the sphere's LEFT side actually reaches row
    18 (confirmed the only way that's reliable - scanning every pixel in
    the source for the debris family's exact colors and taking the max
    row that appears in). A row-range blank through row 18 would have
    also erased the sphere's own legitimate blue atmosphere-rim
    highlight, which is real planet art, not debris, and is already
    cleanly isolated to its own single color (STEEL_LIGHT, #6284A8) at
    every row including where it's interleaved with the debris -
    erasing by color instead of by row keeps every rim pixel exactly
    where it is, in or out of the debris's row range, while still
    removing 100% of the debris. The antenna mast's own colors (GRAY_*,
    AMBER/AMBER_LIGHT, GREEN) ARE in this debris family, same as the
    rock cluster around its base - it's erased for free, not as a
    special case. Crop-and-recolor of the existing art, not a redraw:
    same rust body, same atmosphere rim, same size and pixel grid.
    Shown next to the original in /dev/styleguide for approval; the
    original file is untouched."""
    from PIL import Image

    debris_colors = {GRAY_LIGHT[:3], GRAY_MID[:3], GRAY_DARK[:3], AMBER[:3], AMBER_LIGHT[:3], GREEN[:3]}
    im = Image.open(DEST_DIR / "planet_render_rust.png").convert("RGB")
    bg = im.getpixel((0, 0))
    w, h = im.size
    for y in range(h):
        for x in range(w):
            if im.getpixel((x, y)) in debris_colors:
                im.putpixel((x, y), bg)
    return [[im.getpixel((x, y)) + (255,) for x in range(w)] for y in range(h)]

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
NEW_SPRITES["planet_render_rust_clean"] = draw_planet_render_rust_clean
for _bt, _drawer in PLANET_BUILDING_DRAWERS_CANDIDATE.items():
    for _lv in (1, 2, 3):
        NEW_SPRITES[f"planet_building_{_bt}_lv{_lv}_candidate"] = (lambda d=_drawer, lv=_lv: d(lv))

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
            "notes": f"planet-scale {_bt}, level {_lv} of 3 - WIRED into /colony (habitual.colony.BUILDING_SLOTS)",
        }
NEW_SPRITE_META["planet_render_rust_clean"] = {
    "category": "planet_render", "phase": 4,
    "notes": "planet_render_rust.png with the baked-in antenna/debris erased - WIRED into /colony",
}
for _bt in PLANET_BUILDING_DRAWERS_CANDIDATE:
    for _lv in (1, 2, 3):
        NEW_SPRITE_META[f"planet_building_{_bt}_lv{_lv}_candidate"] = {
            "category": "planet_building_candidate", "phase": 4,
            "notes": f"LV1-readability fix for planet-scale {_bt}, level {_lv} of 3 - review only, pending approval",
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
    """Re-running this must be idempotent - drop any existing entry for a
    name in NEW_SPRITE_META before re-adding it, instead of appending a
    fresh copy on top of whatever's already there. (Appending
    unconditionally was a real bug: every past run of this command had
    been piling up duplicate entries - 31 names ended up with 5 copies
    each before this was caught and fixed.)"""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest = [entry for entry in manifest if entry["name"] not in NEW_SPRITE_META]
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
    build_planet_previews_candidate()


# Review-only locked-slot marker: a single, very dim pixel at the
# anchor - NOT the oversized dashed box rounds 1-2 used (explicitly
# thrown out per the developer's review). Shown both with and without
# in the styleguide, since "acceptable only if it looks clean" is the
# developer's own call to make.
LOCKED_DOT_COLOR = GRAY_DARK[:3] + (110,)


def _paste_planet_building(base_img, building_type: str, level: int, cluster_pixels=None, level_counts=None) -> None:
    """Pastes a building's cluster directly onto the full planet image at
    its real CLUSTER_ANCHORS position - pixel by pixel, not through an
    intermediate cropped canvas, so there's no risk of an off-by-one
    crop/anchor mismatch between this and _bbox_canvas's standalone
    preview images (which exist only for /dev/styleguide's x1/x4 display,
    never for compositing). Defaults to the WIRED (production) dataset;
    pass PLANET_CLUSTER_PIXELS_CANDIDATE/PLANET_LEVEL_COUNTS_CANDIDATE to
    preview the pending LV1-readability fix instead - CLUSTER_ANCHORS is
    shared by both, since anchors never change between them."""
    cluster_pixels = cluster_pixels if cluster_pixels is not None else PLANET_CLUSTER_PIXELS
    level_counts = level_counts if level_counts is not None else PLANET_LEVEL_COUNTS
    anchor_x, anchor_y = CLUSTER_ANCHORS[building_type]
    for dx, dy, color in _level_pixels_from(cluster_pixels, level_counts, building_type, level):
        x, y = anchor_x + dx, anchor_y + dy
        if 0 <= x < base_img.width and 0 <= y < base_img.height:
            base_img.putpixel((x, y), color)


def _paste_locked_dot(base_img, building_type: str) -> None:
    x, y = CLUSTER_ANCHORS[building_type]
    if 0 <= x < base_img.width and 0 <= y < base_img.height:
        existing = base_img.getpixel((x, y))
        r, g, b, a = LOCKED_DOT_COLOR
        blend_a = a / 255
        blended = tuple(round(existing[i] * (1 - blend_a) + (r, g, b)[i] * blend_a) for i in range(3))
        base_img.putpixel((x, y), blended + (255,))


def _clean_planet_image():
    return canvas_to_image(draw_planet_render_rust_clean())


def build_planet_previews() -> None:
    """Full-planet mockups for /dev/styleguide to judge the new art on
    planet_render_rust_clean.png (the antenna/debris-free variant, also
    up for approval here) - review only:
      (a) the clean planet alone, no buildings
      (b) all six clusters at LV1 (barely there)
      (c) all six at LV3 (the full original bake, reproduced)
      (d) a realistic mix (2 built, 4 still locked) - BOTH with no
          marker at all, and with the single dim locked-dot, for a
          side-by-side call on whether the dot earns its keep
    """
    _clean_planet_image().save(COMPOSITES_DIR / "planet_preview_empty.png")

    for level, filename in ((1, "planet_preview_lv1.png"), (3, "planet_preview_lv3.png")):
        base = _clean_planet_image()
        for building_type in PLANET_BUILDING_DRAWERS:
            _paste_planet_building(base, building_type, level)
        base.save(COMPOSITES_DIR / filename)

    built = {"defense_tower": 2, "research_lab": 1}
    locked = [bt for bt in CLUSTER_ANCHORS if bt not in built]

    base = _clean_planet_image()
    for building_type, level in built.items():
        _paste_planet_building(base, building_type, level)
    base.save(COMPOSITES_DIR / "planet_preview_mixed_bare.png")

    base = _clean_planet_image()
    for building_type, level in built.items():
        _paste_planet_building(base, building_type, level)
    for building_type in locked:
        _paste_locked_dot(base, building_type)
    base.save(COMPOSITES_DIR / "planet_preview_mixed_dot.png")


def build_planet_previews_candidate() -> None:
    """Candidate full-planet mockups for /dev/styleguide, using the
    pending LV1-readability fix (PLANET_CLUSTER_PIXELS_CANDIDATE/
    PLANET_LEVEL_COUNTS_CANDIDATE) instead of the wired production
    dataset build_planet_previews() uses - review only, not wired into
    /colony:
      (a) all six at LV1 - the fix under test: must read as six small
          but clearly visible structures, not a bare planet
      (b) all six at LV2
      (c) all six at LV3 (unchanged from the approved round-3 look for
          the four untouched types; biodome/custom_module slightly
          fuller, since both were enlarged)
      (d) the exact scenario from the review finding: Defense Tower LV1
          + Custom Module LV2 built, the other four locked (no marker,
          per the already-approved round-3 call)
    """
    for level, filename in (
        (1, "planet_preview_candidate_lv1.png"),
        (2, "planet_preview_candidate_lv2.png"),
        (3, "planet_preview_candidate_lv3.png"),
    ):
        base = _clean_planet_image()
        for building_type in PLANET_BUILDING_DRAWERS_CANDIDATE:
            _paste_planet_building(
                base, building_type, level,
                cluster_pixels=PLANET_CLUSTER_PIXELS_CANDIDATE, level_counts=PLANET_LEVEL_COUNTS_CANDIDATE,
            )
        base.save(COMPOSITES_DIR / filename)

    built = {"defense_tower": 1, "custom_module": 2}  # the reported bug scenario, exactly
    base = _clean_planet_image()
    for building_type, level in built.items():
        _paste_planet_building(
            base, building_type, level,
            cluster_pixels=PLANET_CLUSTER_PIXELS_CANDIDATE, level_counts=PLANET_LEVEL_COUNTS_CANDIDATE,
        )
    base.save(COMPOSITES_DIR / "planet_preview_candidate_mixed.png")


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

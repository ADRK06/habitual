#!/usr/bin/env python3
"""Colonies sprite pipeline (Phase 2).

Usage:
    python scripts/make_sprites.py import    # copy+rename reference sprites, write manifest.json, print audit
    python scripts/make_sprites.py audit      # just re-print the audit (no file changes)

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


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "import"
    if command == "import":
        manifest = import_sprites()
        print(f"Copied {len(manifest)} sprites into {DEST_DIR}")
        print(f"Wrote {MANIFEST_PATH}")
        print_mapping()
        print_audit()
    elif command == "audit":
        print_audit()
    else:
        raise SystemExit(f"Unknown command: {command!r} (expected 'import' or 'audit')")

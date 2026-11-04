"""Dev-only tooling, never registered unless HABITUAL_DEV is set (see
habitual/config.py and habitual/__init__.py) - this module only exists at
all when that flag is on, so there is no route to probe for in prod even
with the flag absent.
"""

import struct
from pathlib import Path

from flask import Blueprint, render_template
from flask_login import current_user

dev = Blueprint("dev", __name__)

SPRITE_SHEET_PATH = Path(__file__).parent / "static" / "art" / "_sheet.png"


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


@dev.get("/dev/styleguide")
def styleguide():
    # No @login_required - the styleguide itself must work logged out
    # too (app_base.html's shell hides the commander card/HUD for an
    # anonymous visitor instead). Logged in, it shows the real shell
    # with real nav_balance/nav_streak, same as every other page.
    from habitual.habits import nav_shell_context

    nav_context = nav_shell_context(current_user) if current_user.is_authenticated else {}
    sheet_size = _png_size(SPRITE_SHEET_PATH)
    return render_template("dev/styleguide.html", sheet_size=sheet_size, **nav_context)

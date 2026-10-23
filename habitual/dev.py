"""Dev-only tooling, never registered unless HABITUAL_DEV is set (see
habitual/config.py and habitual/__init__.py) - this module only exists at
all when that flag is on, so there is no route to probe for in prod even
with the flag absent.
"""

from flask import Blueprint, render_template
from flask_login import current_user

dev = Blueprint("dev", __name__)


@dev.get("/dev/styleguide")
def styleguide():
    # No @login_required - the styleguide itself must work logged out
    # too (app_base.html's shell hides the commander card/HUD for an
    # anonymous visitor instead). Logged in, it shows the real shell
    # with real nav_balance/nav_streak, same as every other page.
    from habitual.habits import nav_shell_context

    nav_context = nav_shell_context(current_user) if current_user.is_authenticated else {}
    return render_template("dev/styleguide.html", **nav_context)

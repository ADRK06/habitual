"""Dev-only tooling, never registered unless HABITUAL_DEV is set (see
habitual/config.py and habitual/__init__.py) - this module only exists at
all when that flag is on, so there is no route to probe for in prod even
with the flag absent.
"""

from flask import Blueprint, render_template

dev = Blueprint("dev", __name__)


@dev.get("/dev/styleguide")
def styleguide():
    return render_template("dev/styleguide.html")

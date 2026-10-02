"""App-wide error pages (CLAUDE.md Phase 5: friendly 404/500 in the dark
neon design, with a link back home) - registered on the app in
habitual/__init__.py. Kept as plain functions (not inline closures in
create_app) so they're directly callable from tests without going through
Flask's exception-propagation machinery.
"""

from flask import render_template

from habitual import db


def not_found(_error):
    return render_template(
        "errors/error.html",
        code=404,
        emoji="🧭",
        title="Page not found",
        message="That page doesn't exist, or it moved. Let's get you back on track.",
    ), 404


def server_error(_error):
    # A mid-request DB error can leave the session in a broken/pending state
    # that would otherwise poison every later query on this connection.
    db.session.rollback()
    return render_template(
        "errors/error.html",
        code=500,
        emoji="🛠️",
        title="Something broke",
        message="That's on us, not you. Try again in a moment.",
    ), 500

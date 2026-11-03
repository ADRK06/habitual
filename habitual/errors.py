"""App-wide error pages (CLAUDE.md Phase 5: friendly 404/500/403/429 in
the Colonies design, with a link back home) - registered on the app in
habitual/__init__.py. Kept as plain functions (not inline closures in
create_app) so they're directly callable from tests without going through
Flask's exception-propagation machinery.

403/429 have no caller anywhere in the app today (every current rate-limit
and permission check renders its own 200/400 page with a flash/form error
instead of aborting) - these two are registered anyway so an abort(403)/
abort(429) added later, or a future CSRFError/rate-limiter that does raise
one, lands on the same styled page as 404/500 instead of Flask's bare
default error response.
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


def forbidden(_error):
    return render_template(
        "errors/error.html",
        code=403,
        emoji="🔒",
        title="Access denied",
        message="You don't have permission to see that.",
    ), 403


def rate_limited(_error):
    return render_template(
        "errors/error.html",
        code=429,
        emoji="⏳",
        title="Slow down",
        message="Too many attempts - try again in a few minutes.",
    ), 429


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

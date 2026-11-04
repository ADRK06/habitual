"""Lint-style guard for Habit.active() (Phase 3 archiving - see CLAUDE.md's
"Deleting a habit or leaving a room archives it"). Every query call site
that means "this user's/room's CURRENT habits" must filter out archived
ones, so a new bare `Habit.query` appearing unaudited is almost always a
real bug (a query that should exclude archived habits but doesn't), not
just a style nit. This test keeps an explicit, reasoned allowlist of the
exceptions in sync with the actual source - a new one must either be
routed through Habit.active() or added here with a reason; a removed one
must be dropped from the allowlist.

Scope: only the literal `Habit.query` attribute access is scanned (via
ast, so docstrings/comments mentioning it as text don't false-positive).
`db.session.get(Habit, id)` - fetching one known row by primary key, e.g.
the dev-only cli.py backdate command - is a different access pattern not
covered here.
"""
import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "habitual"

ALLOWED_BARE_HABIT_QUERY = {
    ("habits.py", 388): "scans archived habits specifically (anti-farming title match)",
    ("rooms.py", 680): "room feed wants every habit ever created for the room, archived included",
    ("auth.py", 328): "account deletion must hard-delete archived habits too",
    ("auth.py", 339): "account deletion must hard-delete archived habits too",
    ("badges.py", 107): "badges are permanent lifetime achievements, earned on archived habits too",
}


def _find_bare_habit_query_usages():
    found = []
    for path in APP_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "query"
                and isinstance(node.value, ast.Name)
                and node.value.id == "Habit"
            ):
                found.append((path.name, node.lineno))
    return found


def test_every_bare_habit_query_is_audited():
    found = set(_find_bare_habit_query_usages())
    allowed = set(ALLOWED_BARE_HABIT_QUERY.keys())

    unaudited = found - allowed
    assert not unaudited, (
        f"Unaudited bare Habit.query usage at {sorted(unaudited)} - route through "
        f"Habit.active(), or add it to ALLOWED_BARE_HABIT_QUERY (tests/test_habit_query_audit.py) "
        f"with a reason."
    )

    stale = allowed - found
    assert not stale, (
        f"ALLOWED_BARE_HABIT_QUERY references lines that no longer exist (moved/removed?): "
        f"{sorted(stale)} - update the allowlist to match."
    )

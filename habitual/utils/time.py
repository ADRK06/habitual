from datetime import datetime, time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo


def local_now(user):
    """The current datetime in `user`'s timezone — for time-of-day rules
    (e.g. the "At risk" status badge), never the server's/UTC's."""
    return datetime.now(ZoneInfo(user.timezone))


def local_today(user, at=None):
    """The date in `user`'s timezone — never use server/UTC time for habit
    dates. Defaults to right now; pass an aware UTC datetime (e.g. a stored
    `archived_at`) via `at` to get the local date THAT instant fell on
    instead - the one ZoneInfo conversion point for "was this on the
    user's today", reused rather than re-implemented at each call site.

    `at` is assumed UTC if naive (no tzinfo) - same reasoning as auth.
    _aware_utc: Postgres/psycopg always hands back an aware datetime for a
    DateTime(timezone=True) column, but SQLite (the test suite) hands back
    a naive one that still MEANS UTC. Without this, datetime.astimezone()
    on a naive value assumes it's already in the SYSTEM's own local
    timezone instead - silently wrong (by exactly that offset) whenever
    the system timezone happens to equal `user`'s, which it always does
    in this codebase's tests (every test user defaults to the same
    timezone the dev machine runs in)."""
    if at is None:
        return local_now(user).date()
    if at.tzinfo is None:
        at = at.replace(tzinfo=dt_timezone.utc)
    return at.astimezone(ZoneInfo(user.timezone)).date()


def midnight_epoch_ms(user):
    """Epoch milliseconds of the next local midnight for `user` - the
    authoritative "today ends here" instant, computed from the server using
    the user's own timezone. The dashboard's countdown ticks client-side
    against this fixed target (Date.now() is UTC-epoch-based and needs no
    timezone of its own), but the target itself must never be guessed from
    the browser's own clock/timezone, which the account's chosen timezone
    may not match."""
    now = local_now(user)
    midnight = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=now.tzinfo)
    return int(midnight.timestamp() * 1000)

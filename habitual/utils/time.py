from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


def local_now(user):
    """The current datetime in `user`'s timezone — for time-of-day rules
    (e.g. the "At risk" status badge), never the server's/UTC's."""
    return datetime.now(ZoneInfo(user.timezone))


def local_today(user):
    """The current date in `user`'s timezone — never use server/UTC time for habit dates."""
    return local_now(user).date()


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

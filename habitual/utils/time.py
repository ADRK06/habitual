from datetime import datetime
from zoneinfo import ZoneInfo


def local_now(user):
    """The current datetime in `user`'s timezone — for time-of-day rules
    (e.g. the "At risk" status badge), never the server's/UTC's."""
    return datetime.now(ZoneInfo(user.timezone))


def local_today(user):
    """The current date in `user`'s timezone — never use server/UTC time for habit dates."""
    return local_now(user).date()

from datetime import datetime
from zoneinfo import ZoneInfo


def local_today(user):
    """The current date in `user`'s timezone — never use server/UTC time for habit dates."""
    return datetime.now(ZoneInfo(user.timezone)).date()

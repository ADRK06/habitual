from datetime import datetime, timezone as dt_timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from habitual import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    username = db.Column(db.String(20), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    timezone = db.Column(db.String(50), nullable=False, default="Asia/Kolkata")
    theme = db.Column(db.String(10), nullable=False, default="dark")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(dt_timezone.utc)
    )
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True), nullable=True)
    failed_join_attempts = db.Column(db.Integer, nullable=False, default=0)
    join_locked_until = db.Column(db.DateTime(timezone=True), nullable=True)
    failed_forgot_attempts = db.Column(db.Integer, nullable=False, default=0)
    forgot_locked_until = db.Column(db.DateTime(timezone=True), nullable=True)
    # Bumped on every password reset/change - see get_id()/load_user below.
    session_version = db.Column(db.Integer, nullable=False, default=0)

    # Stored lowercased/stripped. Nullable at the DB level (pre-existing
    # accounts have none yet) even though the signup form requires it for
    # new ones. Deliberately NOT globally unique - see the partial index
    # below - an unverified claim is provisional and never blocks anyone
    # else from claiming (and then verifying) the same address first.
    email = db.Column(db.String(255), nullable=True, index=True)
    # A new/changed address staged here until ITS OWN verification link is
    # clicked - only then does it get promoted into `email` (see
    # auth._claim_verified_email). Never unique: two people mid-change to
    # the same typo'd address is harmless until one of them actually proves
    # ownership.
    pending_email = db.Column(db.String(255), nullable=True)
    email_verified_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Uniqueness only among VERIFIED emails - see the `email` column's
        # comment. Both dialects this app runs on (Postgres in prod/dev,
        # SQLite in tests) support a partial/filtered unique index.
        db.Index(
            "uq_users_email_verified", "email", unique=True,
            postgresql_where=db.text("email_verified_at IS NOT NULL"),
            sqlite_where=db.text("email_verified_at IS NOT NULL"),
        ),
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        # Encodes session_version into Flask-Login's session identifier so
        # bumping it (on an email-link password reset) invalidates every
        # session cookie already holding the old value - see load_user,
        # which refuses to resolve a mismatched version. A self-service
        # password change on the account security page bumps this too, but
        # immediately re-calls login_user() to refresh ITS OWN session with
        # the new version, so only other sessions get logged out.
        return f"{self.id}.{self.session_version}"

    @staticmethod
    def parse_id(user_id):
        try:
            raw_id, version = user_id.split(".", 1)
            return int(raw_id), int(version)
        except (AttributeError, ValueError):
            return None, None


@login_manager.user_loader
def load_user(user_id):
    raw_id, version = User.parse_id(user_id)
    if raw_id is None:
        return None
    user = db.session.get(User, raw_id)
    if user is None or user.session_version != version:
        return None
    return user


class Habit(db.Model):
    __tablename__ = "habits"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=True, index=True)
    title = db.Column(db.String(60), nullable=False)
    emoji = db.Column(db.String(8), nullable=False)
    tiny_version = db.Column(db.String(120), nullable=True)
    created_on = db.Column(db.Date, nullable=False)
    # "daily" (default) | "days" (specific weekdays) | "weekly" (X times/week).
    # frequency_days: 7-bit mask (bit i = weekday i scheduled, Mon=0..Sun=6,
    # matching date.weekday()) - only meaningful for "days". frequency_target:
    # 1-6 - only meaningful for "weekly". frequency_changed_on: set to the
    # local date of the most recent frequency edit, NULL if never edited -
    # every frequency-aware stat restarts counting from this date rather than
    # created_on once it's set (see habitual/frequency.py).
    frequency_type = db.Column(db.String(10), nullable=False, default="daily", server_default="daily")
    frequency_days = db.Column(db.Integer, nullable=True)
    frequency_target = db.Column(db.Integer, nullable=True)
    frequency_changed_on = db.Column(db.Date, nullable=True)

    checkins = db.relationship(
        "Checkin", backref="habit", cascade="all, delete-orphan", passive_deletes=False
    )
    freezes = db.relationship(
        "Freeze", backref="habit", cascade="all, delete-orphan", passive_deletes=False
    )
    point_transactions = db.relationship(
        "PointTransaction", backref="habit", cascade="all, delete-orphan", passive_deletes=False
    )
    # No cascade here on purpose - a room habit is a normal habit, and when
    # a member leaves, leave_room() deletes their own Habit directly. By
    # that point no other Habit should still reference the deleted Room.
    room = db.relationship("Room", backref="habits")


class Checkin(db.Model):
    __tablename__ = "checkins"
    __table_args__ = (db.UniqueConstraint("habit_id", "date", name="uq_checkin_habit_date"),)

    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey("habits.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(dt_timezone.utc)
    )
    proof_note = db.Column(db.String(280), nullable=True)

    vouches = db.relationship(
        "Vouch", backref="checkin", cascade="all, delete-orphan", passive_deletes=False
    )


class Freeze(db.Model):
    __tablename__ = "freezes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    habit_id = db.Column(db.Integer, db.ForeignKey("habits.id"), nullable=True, index=True)
    purchased_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(dt_timezone.utc)
    )
    used_on = db.Column(db.Date, nullable=True)


class PointTransaction(db.Model):
    __tablename__ = "point_transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    habit_id = db.Column(db.Integer, db.ForeignKey("habits.id"), nullable=True, index=True)
    amount = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(20), nullable=False)  # daily | milestone | crown | freeze_purchase
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(dt_timezone.utc)
    )


class Room(db.Model):
    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(60), nullable=False)
    emoji = db.Column(db.String(8), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    duration_days = db.Column(db.Integer, nullable=False)
    # Always the creator's own local date at creation time (never server/UTC
    # time) - every member's final day is computed from this in their own
    # timezone, so the room has no single shared "today".
    start_date = db.Column(db.Date, nullable=False)
    invite_token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    # Short human-typeable alternative to the link - regenerated together
    # with invite_token so an old code/link pair is invalidated as a unit.
    join_code = db.Column(db.String(6), unique=True, nullable=False, index=True)
    # Same meaning as Habit's frequency_type/frequency_days/frequency_target -
    # set once by the creator and copied onto every member's Habit row at
    # join/create time. No frequency_changed_on here: room frequency is locked
    # after creation (no edit route), so there's nothing to re-base.
    frequency_type = db.Column(db.String(10), nullable=False, default="daily", server_default="daily")
    frequency_days = db.Column(db.Integer, nullable=True)
    frequency_target = db.Column(db.Integer, nullable=True)
    # High-water mark for crown finalization - every date from start_date
    # through this one (inclusive) has already been decided for good
    # (crown awarded or not), so rooms.finalize_due_crowns never re-walks
    # it. NULL means nothing has been finalized yet. See that function's
    # docstring for why this makes finalization cost independent of room
    # age instead of re-scanning the whole history on every call.
    finalized_through = db.Column(db.Date, nullable=True)

    members = db.relationship(
        "RoomMember", backref="room", cascade="all, delete-orphan", passive_deletes=False
    )
    crowns = db.relationship(
        "RoomCrown", backref="room", cascade="all, delete-orphan", passive_deletes=False
    )


class RoomMember(db.Model):
    __tablename__ = "room_members"
    __table_args__ = (db.UniqueConstraint("room_id", "user_id", name="uq_room_member"),)

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    joined_on = db.Column(db.Date, nullable=False)

    user = db.relationship("User")


class Vouch(db.Model):
    __tablename__ = "vouches"
    __table_args__ = (db.UniqueConstraint("checkin_id", "user_id", name="uq_vouch_checkin_user"),)

    id = db.Column(db.Integer, primary_key=True)
    checkin_id = db.Column(db.Integer, db.ForeignKey("checkins.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    emoji = db.Column(db.String(8), nullable=False)  # ✅ or 🔥

    user = db.relationship("User")


class Badge(db.Model):
    __tablename__ = "badges"
    __table_args__ = (db.UniqueConstraint("user_id", "type", name="uq_badge_user_type"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    type = db.Column(db.String(30), nullable=False)
    earned_on = db.Column(db.Date, nullable=False)


class RoomCrown(db.Model):
    """One row per date a room's crown has been finalized - the permanent
    record backing the leaderboard's crown count and point history, created
    once by rooms.finalize_due_crowns() and never rewritten. checkin_id is
    nullable: if the winner later leaves the room (deleting their habit and
    its check-ins), this row survives as history with checkin_id cleared,
    rather than disappearing or dangling."""

    __tablename__ = "room_crowns"
    __table_args__ = (db.UniqueConstraint("room_id", "date", name="uq_room_crown_room_date"),)

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    checkin_id = db.Column(db.Integer, db.ForeignKey("checkins.id"), nullable=True, index=True)

    user = db.relationship("User")


class EmailToken(db.Model):
    """A one-time link token - either `purpose="verify_email"` (confirms
    the user controls `target_email`, the first time or after an
    add/change) or `purpose="reset"` (forgot-password). Only a SHA-256
    digest is stored, not a slow password-style hash: unlike a password or
    the old recovery codes, this token is a fresh 256-bit random value
    (secrets.token_urlsafe), already far too high-entropy to brute-force
    offline, so a fast hash with a direct indexed lookup is both the
    standard approach for this kind of token and meaningfully cheaper per
    email sent. target_email freezes which address this specific token is
    for, so an older token can't verify a DIFFERENT (earlier) pending
    address if the user changed their mind in between. used_at (not a
    delete) keeps a permanent "already spent" record."""

    __tablename__ = "email_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    purpose = db.Column(db.String(20), nullable=False)
    target_email = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(dt_timezone.utc)
    )
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)


class RateLimit(db.Model):
    """Generic rate limit/cooldown for anything with no logged-in user to
    key a lockout column off of - `key` is whatever identifies the
    requester for this scope (an IP address, an email address, ...). The
    account-keyed half of forgot-password's limiting lives on User
    (failed_forgot_attempts/forgot_locked_until) instead, mirroring
    login's/join's existing per-account pattern."""

    __tablename__ = "rate_limits"
    __table_args__ = (db.UniqueConstraint("key", "scope", name="uq_rate_limit_key_scope"),)

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(255), nullable=False)
    scope = db.Column(db.String(30), nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True), nullable=True)

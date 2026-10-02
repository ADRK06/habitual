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

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Habit(db.Model):
    __tablename__ = "habits"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=True, index=True)
    title = db.Column(db.String(60), nullable=False)
    emoji = db.Column(db.String(8), nullable=False)
    tiny_version = db.Column(db.String(120), nullable=True)
    created_on = db.Column(db.Date, nullable=False)

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

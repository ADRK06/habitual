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

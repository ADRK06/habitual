import re
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import urlsplit
from zoneinfo import available_timezones

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy.exc import IntegrityError
from wtforms import HiddenField, PasswordField, StringField
from wtforms.validators import DataRequired, EqualTo, ValidationError

from habitual import db
from habitual.models import User

auth = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).{8,}$")

USERNAME_HELP = "3-20 characters: lowercase letters, numbers, underscore only."
PASSWORD_HELP = "At least 8 characters, with an uppercase letter, a lowercase letter, a digit, and a special character."


def _validate_username_format(form, field):
    if not USERNAME_RE.match((field.data or "").strip().lower()):
        raise ValidationError(USERNAME_HELP)


def _validate_password_strength(form, field):
    if not PASSWORD_RE.match(field.data or ""):
        raise ValidationError(PASSWORD_HELP)


def _aware_utc(dt):
    # SQLite (used in tests) doesn't honor DateTime(timezone=True) and hands back
    # naive datetimes even though Postgres/Neon correctly returns aware ones.
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=dt_timezone.utc)
    return dt


def safe_next_path(target):
    """Only allow same-site relative paths, never an absolute/external URL."""
    if not target:
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not parts.path.startswith("/"):
        return None
    return target


class SignupForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    username = StringField("Username", validators=[DataRequired(), _validate_username_format])
    password = PasswordField("Password", validators=[DataRequired(), _validate_password_strength])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    timezone = HiddenField("Timezone")
    next = HiddenField("Next")


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    next = HiddenField("Next")


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(safe_next_path(request.args.get("next")) or url_for("habits.dashboard"))

    form = SignupForm(next=request.args.get("next", ""))

    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        tz = form.timezone.data
        if tz not in available_timezones():
            tz = "Asia/Kolkata"

        user = User(name=form.name.data.strip(), username=username, timezone=tz)
        user.set_password(form.password.data)
        db.session.add(user)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.username.errors.append("That username is taken.")
        else:
            login_user(user)
            flash("Welcome to Habitual!", "success")
            return redirect(safe_next_path(form.next.data) or url_for("habits.dashboard"))

    return render_template("auth/signup.html", form=form)


@auth.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(safe_next_path(request.args.get("next")) or url_for("habits.dashboard"))

    form = LoginForm(next=request.args.get("next", ""))

    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        user = User.query.filter_by(username=username).first()
        now = datetime.now(dt_timezone.utc)
        locked_until = _aware_utc(user.locked_until) if user else None

        if locked_until and locked_until > now:
            minutes_left = int((locked_until - now).total_seconds() // 60) + 1
            form.username.errors.append(
                f"Too many failed attempts. Try again in {minutes_left} minute(s)."
            )
        elif user and user.check_password(form.password.data):
            user.failed_login_attempts = 0
            user.locked_until = None
            db.session.commit()
            login_user(user)
            return redirect(safe_next_path(form.next.data) or url_for("habits.dashboard"))
        else:
            if user:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= 5:
                    user.locked_until = now + timedelta(minutes=10)
                db.session.commit()
            form.username.errors.append("Incorrect username or password.")

    return render_template("auth/login.html", form=form)


@auth.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("home"))


@auth.route("/auth/check-username")
def check_username():
    username = (request.args.get("username") or "").strip().lower()

    if not USERNAME_RE.match(username):
        available, message = False, USERNAME_HELP
    elif User.query.filter_by(username=username).first():
        available, message = False, "Username taken."
    else:
        available, message = True, "Username available."

    return render_template("partials/username_check.html", available=available, message=message)

import re
import secrets
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import urlsplit
from zoneinfo import available_timezones

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import HiddenField, PasswordField, StringField
from wtforms.validators import DataRequired, EqualTo, ValidationError
from zxcvbn import zxcvbn

from habitual import db
from habitual.models import IpLockout, RecoveryCode, User

auth = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).{8,}$")

USERNAME_HELP = "3-20 characters: lowercase letters, numbers, underscore only."
PASSWORD_HELP = "At least 8 characters, with an uppercase letter, a lowercase letter, a digit, and a special character."

# The checklist (PASSWORD_RE) only checks character variety, which "Password1!"
# satisfies while still being trivially guessable. zxcvbn's score (0-4, based
# on actual crack-time estimates, dictionary/pattern matching, and whatever
# user_inputs it's given) is the real gate - the checklist stays as UX
# guidance, never as the sole server-side bar.
MIN_ZXCVBN_SCORE = 3

# Unambiguous: no 0/O or 1/I/L, so a code read off a phone screen or printed
# page is never misread. 10 chars x 8 codes keeps each code easy to type
# while the alphabet (32 symbols) still gives ~50 bits of entropy per code.
RECOVERY_CODE_ALPHABET = "".join(c for c in "ABCDEFGHJKMNPQRSTUVWXYZ23456789" if c not in "ILO01")
RECOVERY_CODE_LENGTH = 10
RECOVERY_CODE_COUNT = 8

# Same shape as login's existing failed_login_attempts/locked_until - 5
# failures locks for 10 minutes, just duplicated across a per-username
# column pair (User.failed_forgot_attempts/forgot_locked_until, mirroring
# the join-code rate limit's existing pattern) and a per-IP table
# (IpLockout), since forgot-password has no session to key a per-user
# lockout off of before it even knows whether the username is real.
LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 10
FORGOT_SCOPE = "forgot_password"

# Burned in a failed forgot-password attempt against an unknown username, so
# that branch costs about the same as hashing a real (wrong) code - without
# this, a username's mere existence would be observable by comparing
# response times. Computed once at import time (not per-request).
_DUMMY_CODE_HASH = generate_password_hash(secrets.token_hex(16))


def _validate_username_format(form, field):
    if not USERNAME_RE.match((field.data or "").strip().lower()):
        raise ValidationError(USERNAME_HELP)


def _validate_password_strength(form, field):
    if not PASSWORD_RE.match(field.data or ""):
        raise ValidationError(PASSWORD_HELP)


def _validate_password_guessability(password, user_inputs):
    """Raises ValidationError if zxcvbn scores `password` below
    MIN_ZXCVBN_SCORE against `user_inputs` (name/username, so a password
    built from either scores low) - shared by signup, password reset, and
    the account-security change-password form."""
    result = zxcvbn(password or "", user_inputs=[s for s in user_inputs if s])
    if result["score"] < MIN_ZXCVBN_SCORE:
        feedback = result.get("feedback") or {}
        message = feedback.get("warning") or next(iter(feedback.get("suggestions") or []), None)
        raise ValidationError(message or "This password is too easy to guess - try something longer or less common.")


def _signup_zxcvbn(form, field):
    _validate_password_guessability(field.data, [form.username.data, form.name.data])


def _forgot_zxcvbn(form, field):
    # No `name` field on this form - looks the user up to include it anyway,
    # same user_inputs as signup gets. The lookup itself can't leak whether
    # the username exists: this validator only ever affects the password-
    # strength error, which looks identical either way.
    username = (form.username.data or "").strip().lower()
    user = User.query.filter_by(username=username).first()
    _validate_password_guessability(field.data, [username, user.name if user else None])


def _account_zxcvbn(form, field):
    _validate_password_guessability(field.data, [current_user.username, current_user.name])


def _generate_recovery_codes(user):
    """Replaces every one of `user`'s existing codes (used or not) with
    RECOVERY_CODE_COUNT fresh ones - regenerating always invalidates the
    old set as a unit, same idea as a room's invite_token/join_code pair.
    Returns the plaintext codes for the caller to show exactly once; only
    the hash is ever added to the session (caller still commits)."""
    RecoveryCode.query.filter_by(user_id=user.id).delete()
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        code = "".join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
        codes.append(code)
        db.session.add(RecoveryCode(user_id=user.id, code_hash=generate_password_hash(code)))
    return codes


def _ip_lockout_locked_until(ip, scope, now):
    row = IpLockout.query.filter_by(ip=ip, scope=scope).first()
    locked_until = _aware_utc(row.locked_until) if row else None
    return locked_until and locked_until > now


def _record_ip_failure(ip, scope, now):
    row = IpLockout.query.filter_by(ip=ip, scope=scope).first()
    if row is None:
        row = IpLockout(ip=ip, scope=scope, failed_attempts=0)
        db.session.add(row)
    row.failed_attempts += 1
    if row.failed_attempts >= LOCKOUT_THRESHOLD:
        row.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)


def _reset_ip_lockout(ip, scope):
    IpLockout.query.filter_by(ip=ip, scope=scope).delete()


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
    password = PasswordField(
        "Password", validators=[DataRequired(), _validate_password_strength, _signup_zxcvbn]
    )
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


class ForgotPasswordForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    recovery_code = StringField("Recovery code", validators=[DataRequired()])
    new_password = PasswordField(
        "New password", validators=[DataRequired(), _validate_password_strength, _forgot_zxcvbn]
    )
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")],
    )


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField(
        "New password", validators=[DataRequired(), _validate_password_strength, _account_zxcvbn]
    )
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")],
    )


class CSRFOnlyForm(FlaskForm):
    """No fields of its own - just gives the "generate/regenerate codes"
    button a real CSRF-protected POST without a password or any other
    input to collect."""


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
            codes = _generate_recovery_codes(user)
            db.session.commit()
            flash("Welcome to Habitual!", "success")
            next_url = safe_next_path(form.next.data) or url_for("habits.dashboard")
            return render_template("auth/recovery_codes.html", codes=codes, continue_url=next_url)

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


@auth.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("habits.dashboard"))

    form = ForgotPasswordForm()
    generic_error = "That username or recovery code isn't right."

    if form.validate_on_submit():
        ip = request.remote_addr or "unknown"
        now = datetime.now(dt_timezone.utc)
        username = form.username.data.strip().lower()
        user = User.query.filter_by(username=username).first()
        user_locked_until = _aware_utc(user.forgot_locked_until) if user else None

        if _ip_lockout_locked_until(ip, FORGOT_SCOPE, now) or (user_locked_until and user_locked_until > now):
            form.username.errors.append("Too many failed attempts. Try again in a few minutes.")
        else:
            code_input = (form.recovery_code.data or "").strip().upper()
            matched_code = None
            if user is not None:
                for candidate in RecoveryCode.query.filter_by(user_id=user.id, used_at=None):
                    if check_password_hash(candidate.code_hash, code_input):
                        matched_code = candidate
                        break
            else:
                # Burns roughly the same work a real (wrong) code comparison
                # would, so a nonexistent username can't be told apart from
                # a real one with no matching code by response time alone.
                check_password_hash(_DUMMY_CODE_HASH, code_input)

            if user is None or matched_code is None:
                _record_ip_failure(ip, FORGOT_SCOPE, now)
                if user is not None:
                    user.failed_forgot_attempts += 1
                    if user.failed_forgot_attempts >= LOCKOUT_THRESHOLD:
                        user.forgot_locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                db.session.commit()
                form.username.errors.append(generic_error)
            else:
                matched_code.used_at = now
                user.set_password(form.new_password.data)
                # Invalidates every session currently logged in as this
                # user (see User.get_id/load_user) - there's no "this is my
                # session" to spare here, unlike the account-security
                # change-password flow, since whoever's resetting via a
                # recovery code is, by definition, not currently logged in.
                user.session_version += 1
                user.failed_login_attempts = 0
                user.locked_until = None
                user.failed_forgot_attempts = 0
                user.forgot_locked_until = None
                _reset_ip_lockout(ip, FORGOT_SCOPE)
                db.session.commit()
                flash("Password reset - log in with your new password.", "success")
                return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html", form=form)


@auth.get("/account/security")
@login_required
def account_security():
    has_codes = RecoveryCode.query.filter_by(user_id=current_user.id, used_at=None).first() is not None
    return render_template(
        "auth/account_security.html",
        has_codes=has_codes, new_codes=None,
        password_form=ChangePasswordForm(), codes_form=CSRFOnlyForm(),
    )


@auth.post("/account/security/codes")
@login_required
def regenerate_codes():
    if not CSRFOnlyForm().validate_on_submit():
        abort(400)
    codes = _generate_recovery_codes(current_user)
    db.session.commit()
    flash("New recovery codes generated - save them now, they won't be shown again.", "success")
    return render_template(
        "auth/account_security.html",
        has_codes=True, new_codes=codes,
        password_form=ChangePasswordForm(), codes_form=CSRFOnlyForm(),
    )


@auth.post("/account/security/password")
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            form.current_password.errors.append("Incorrect current password.")
        else:
            current_user.set_password(form.new_password.data)
            current_user.session_version += 1
            db.session.commit()
            # Refreshes THIS session's cookie to the new session_version -
            # every OTHER session (that never gets this call) still carries
            # the old version and is rejected by load_user on its next
            # request, exactly the "other sessions are signed out" behavior
            # a password change should have, without also signing out the
            # session that just made the change. Must be the real model
            # instance, not the `current_user` LocalProxy itself - passing
            # the proxy makes Flask-Login cache the proxy as this request's
            # g._login_user, and every later read of current_user (even on
            # a later request, via the stale cached proxy) resolves back
            # through itself forever.
            login_user(current_user._get_current_object())
            flash("Password changed. Other devices have been signed out.", "success")
            return redirect(url_for("auth.account_security"))

    has_codes = RecoveryCode.query.filter_by(user_id=current_user.id, used_at=None).first() is not None
    return render_template(
        "auth/account_security.html",
        has_codes=has_codes, new_codes=None,
        password_form=form, codes_form=CSRFOnlyForm(),
    ), 400


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

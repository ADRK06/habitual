import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import urlsplit
from zoneinfo import available_timezones

from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy.exc import IntegrityError
from wtforms import HiddenField, PasswordField, StringField
from wtforms.validators import DataRequired, EqualTo, ValidationError
from zxcvbn import zxcvbn

from habitual import db, mailer
from habitual.models import (
    Badge, EmailToken, Freeze, Habit, PointTransaction, RateLimit, Room, RoomCrown, RoomMember, User, Vouch,
)

auth = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).{8,}$")
# Deliberately minimal, not RFC 5322 - good enough to catch typos without a
# new dependency (email-validator). Real deliverability is proven by
# actually clicking the verification link, not by the regex.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

USERNAME_HELP = "3-20 characters: lowercase letters, numbers, underscore only."
PASSWORD_HELP = "At least 8 characters, with an uppercase letter, a lowercase letter, a digit, and a special character."
EMAIL_HELP = "Enter a valid email address."

# The checklist (PASSWORD_RE) only checks character variety, which "Password1!"
# satisfies while still being trivially guessable. zxcvbn's score (0-4, based
# on actual crack-time estimates, dictionary/pattern matching, and whatever
# user_inputs it's given) is the real gate - the checklist stays as UX
# guidance, never as the sole server-side bar.
MIN_ZXCVBN_SCORE = 3

RESET_TOKEN_LIFETIME = timedelta(minutes=30)
VERIFY_TOKEN_LIFETIME = timedelta(hours=24)

# Rate limiting / cooldowns for the email-sending routes (forgot-password,
# resend-verification). See _check_rate_limit's docstring for the shape:
# every allowed send sets a short cooldown, and hitting the hourly cap
# extends that into a full hour. The account-keyed dimension (a specific
# user's reset-SUBMISSION failures, as opposed to reset-REQUEST sends)
# still lives on User.failed_forgot_attempts/forgot_locked_until, mirroring
# login's/join's existing per-account lockout.
RESEND_COOLDOWN_SECONDS = 60
EMAIL_SEND_CAP_PER_HOUR = 5
IP_REQUEST_CAP_PER_HOUR = 10
LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 10

RL_SCOPE_FORGOT_EMAIL = "forgot_email"
RL_SCOPE_FORGOT_IP = "forgot_ip"
RL_SCOPE_RESET_SUBMIT_IP = "reset_submit_ip"
RL_SCOPE_VERIFY_RESEND = "verify_resend"


def _validate_username_format(form, field):
    if not USERNAME_RE.match((field.data or "").strip().lower()):
        raise ValidationError(USERNAME_HELP)


def _validate_email_format(form, field):
    if not EMAIL_RE.match((field.data or "").strip()):
        raise ValidationError(EMAIL_HELP)


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


def _account_zxcvbn(form, field):
    _validate_password_guessability(field.data, [current_user.username, current_user.name])


def _apply_zxcvbn_check(form, field_name, user):
    """Manually runs the guessability check against `user`'s own
    username/name, for forms where the user is only known from request
    context (a token, here) rather than from the form's own fields -
    WTForms field validators only ever see (form, field), with no way to
    inject extra context like a resolved user at declare-time. Returns
    False (and appends the error, same as a normal validator) on failure."""
    field = getattr(form, field_name)
    try:
        _validate_password_guessability(field.data, [user.username, user.name])
    except ValidationError as exc:
        field.errors.append(str(exc))
        return False
    return True


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


def _client_ip():
    """The real client IP behind Vercel's edge, which terminates the
    connection and sets X-Forwarded-For itself (the first hop isn't a
    value an end client can forge past it) - falls back to the raw socket
    peer for local dev, where there's no such header at all."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _check_rate_limit(key, scope, cap, cooldown_seconds, now):
    """Records this attempt for (key, scope) and returns whether it's
    allowed right now. Every allowed attempt (optionally) sets a short
    cooldown before the next one; once `cap` attempts land before that
    cooldown fully lapses, the lock extends to a full hour instead - same
    "N before locking, then wait" shape as the existing login/join
    lockouts, just reused here for rate-limiting sends/requests instead of
    counting failures. Caller still has to commit."""
    row = RateLimit.query.filter_by(key=key, scope=scope).first()
    if row is not None and row.locked_until is not None and _aware_utc(row.locked_until) > now:
        return False

    if row is None:
        row = RateLimit(key=key, scope=scope, attempts=0)
        db.session.add(row)
    elif row.locked_until is not None and _aware_utc(row.locked_until) <= now:
        row.attempts = 0

    row.attempts += 1
    if row.attempts >= cap:
        row.locked_until = now + timedelta(hours=1)
    elif cooldown_seconds:
        row.locked_until = now + timedelta(seconds=cooldown_seconds)
    return True


def _claim_verified_email(user, email, now):
    """Marks `email` verified and owned by `user`. Returns False (no
    changes made) if another account already verified-owns it - a genuine
    race, or a stale token for an address someone else got to first.
    Otherwise clears that address from every OTHER account's unverified
    `email`/`pending_email`: an unverified claim is provisional, and the
    first VERIFIED claim wins, which is what the partial unique index on
    users.email (verified rows only) is there to enforce."""
    taken_by_someone_else = User.query.filter(
        User.id != user.id, User.email == email, User.email_verified_at.isnot(None)
    ).first()
    if taken_by_someone_else is not None:
        return False

    User.query.filter(
        User.id != user.id, User.email == email, User.email_verified_at.is_(None)
    ).update({"email": None})
    User.query.filter(User.id != user.id, User.pending_email == email).update({"pending_email": None})

    user.email = email
    user.pending_email = None
    user.email_verified_at = now
    return True


def _issue_email_token(user, purpose, target_email, lifetime, now):
    """Deletes this user's older unused tokens of the same purpose (only
    the newest link for a given purpose is ever valid), then creates and
    returns the plaintext token for a fresh one. Only its SHA-256 digest is
    stored - see EmailToken's docstring for why a fast hash (not a slow,
    password-style one) is the right call for a 256-bit random value.
    Caller still has to commit."""
    EmailToken.query.filter_by(user_id=user.id, purpose=purpose, used_at=None).delete()
    token = secrets.token_urlsafe(32)
    db.session.add(EmailToken(
        user_id=user.id,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        purpose=purpose,
        target_email=target_email,
        expires_at=now + lifetime,
    ))
    return token


def _find_valid_token(token, purpose, now):
    """A direct indexed hash lookup, not an iterate-and-compare loop - the
    token is a 256-bit random value, already far too high-entropy for an
    attacker to have any candidate set worth comparing against, unlike a
    password or the old recovery codes. Returns None for a missing, wrong-
    purpose, already-used, or expired token."""
    token_hash = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
    row = EmailToken.query.filter_by(token_hash=token_hash, purpose=purpose, used_at=None).first()
    if row is None or _aware_utc(row.expires_at) <= now:
        return None
    return row


def _resolve_token_user_id(token, purpose):
    """Looks up which user a token hash belongs to regardless of whether
    it's still valid - used only to attribute a bad/expired/reused
    reset-password SUBMISSION to an account for lockout purposes, never to
    accept it."""
    token_hash = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
    row = EmailToken.query.filter_by(token_hash=token_hash, purpose=purpose).first()
    return row.user_id if row else None


def _send_verification_email(user, target_email, now):
    token = _issue_email_token(user, "verify_email", target_email, VERIFY_TOKEN_LIFETIME, now)
    db.session.commit()
    link = url_for("auth.verify_email", token=token, _external=True)
    text_body = render_template("emails/verify_email.txt", name=user.name, username=user.username, link=link)
    html_body = render_template("emails/verify_email.html", name=user.name, username=user.username, link=link)
    return mailer.send_email(target_email, "Verify your email for Habitual", text_body, html_body)


def _send_reset_email(user, now):
    token = _issue_email_token(user, "reset", user.email, RESET_TOKEN_LIFETIME, now)
    db.session.commit()
    link = url_for("auth.reset_password", token=token, _external=True)
    text_body = render_template("emails/reset_password.txt", name=user.name, link=link)
    html_body = render_template("emails/reset_password.html", name=user.name, link=link)
    return mailer.send_email(user.email, "Reset your Habitual password", text_body, html_body)


class SignupForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    username = StringField("Username", validators=[DataRequired(), _validate_username_format])
    email = StringField("Email", validators=[DataRequired(), _validate_email_format])
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
    email = StringField("Email", validators=[DataRequired(), _validate_email_format])


class ResetPasswordForm(FlaskForm):
    new_password = PasswordField("New password", validators=[DataRequired(), _validate_password_strength])
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


class ChangeEmailForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), _validate_email_format])


class CSRFOnlyForm(FlaskForm):
    """No fields of its own - just gives a button (resend verification,
    etc.) a real CSRF-protected POST with nothing else to collect."""


class DeleteAccountForm(FlaskForm):
    confirm_username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


def _delete_account(user):
    """Deletes `user` and everything that belongs to them. Caller still
    has to commit - this is meant to run as one transaction, with the
    actual User row deleted last so an error partway through never leaves
    an orphaned half-deleted account.

    - Every room the account is in: handled exactly like leaving it
      normally (rooms._leave_room_as) - deletes their room habit,
      transfers ownership or deletes the room if they were the last
      member. Called once per membership, so this covers every room.
    - Every remaining (solo) habit and its own cascade (check-ins,
      freezes, point transactions) - room habits are already gone by the
      point this runs, from the step above.
    - Freezes/point-transactions not tied to any habit (habit_id NULL -
      an unused freeze, or a freeze_purchase ledger row), which no
      Habit's own cascade reaches.
    - Vouches THIS user gave on someone ELSE's check-in. Vouches on their
      OWN check-ins already went with those check-ins' habit, via
      Checkin's own cascade, above - no separate step needed for those.
    - Badges, email tokens, and the rate-limit rows keyed to their
      account/email (never the IP-keyed ones - those aren't "theirs").
    - Finalized room-crown history survives with the winner reference
      cleared, same idea as checkin_id already being nulled when the
      habit behind it is deleted (see _leave_room_as).

    Deleting the User row itself is enough to invalidate every session
    everywhere (load_user's db.session.get simply finds nothing) -
    there's no separate session_version step needed the way a password
    reset needs one."""
    from habitual import rooms  # local import avoids a circular import with rooms.py

    for member in RoomMember.query.filter_by(user_id=user.id).all():
        room = db.session.get(Room, member.room_id)
        members = rooms._room_members(room)
        rooms._leave_room_as(room, members, user)

    for habit in Habit.query.filter_by(user_id=user.id).all():
        db.session.delete(habit)

    Freeze.query.filter_by(user_id=user.id, habit_id=None).delete()
    PointTransaction.query.filter_by(user_id=user.id, habit_id=None).delete()
    Vouch.query.filter_by(user_id=user.id).delete()
    Badge.query.filter_by(user_id=user.id).delete()
    EmailToken.query.filter_by(user_id=user.id).delete()
    RoomCrown.query.filter_by(user_id=user.id).update({"user_id": None}, synchronize_session=False)

    RateLimit.query.filter_by(key=f"user:{user.id}", scope=RL_SCOPE_VERIFY_RESEND).delete()
    if user.email:
        RateLimit.query.filter_by(key=user.email, scope=RL_SCOPE_FORGOT_EMAIL).delete()

    db.session.delete(user)


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(safe_next_path(request.args.get("next")) or url_for("habits.dashboard"))

    form = SignupForm(next=request.args.get("next", ""))

    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        email = form.email.data.strip().lower()
        tz = form.timezone.data
        if tz not in available_timezones():
            tz = "Asia/Kolkata"

        already_verified_elsewhere = User.query.filter_by(email=email).filter(
            User.email_verified_at.isnot(None)
        ).first()
        if already_verified_elsewhere is not None:
            form.email.errors.append("That email is already registered.")
            return render_template("auth/signup.html", form=form)

        user = User(name=form.name.data.strip(), username=username, timezone=tz, email=email)
        user.set_password(form.password.data)
        db.session.add(user)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.username.errors.append("That username is taken.")
        else:
            login_user(user)
            now = datetime.now(dt_timezone.utc)
            sent = _send_verification_email(user, email, now)
            flash(
                "Welcome to Habitual! Check your email to verify your account." if sent
                else "Welcome to Habitual! We couldn't send a verification email right now - "
                     "you can resend it from Account security.",
                "success" if sent else "warning",
            )
            return redirect(url_for("auth.check_email"))

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


@auth.get("/check-email")
@login_required
def check_email():
    target = current_user.pending_email or current_user.email
    return render_template("auth/check_email.html", email=target, resend_form=CSRFOnlyForm())


@auth.post("/resend-verification")
@login_required
def resend_verification():
    if not CSRFOnlyForm().validate_on_submit():
        abort(400)
    next_url = safe_next_path(request.form.get("next")) or url_for("habits.dashboard")

    target = current_user.pending_email or current_user.email
    nothing_pending = target is None or (current_user.pending_email is None and current_user.email_verified_at is not None)
    if nothing_pending:
        flash("Your email is already verified.", "info")
        return redirect(next_url)

    now = datetime.now(dt_timezone.utc)
    key = f"user:{current_user.id}"
    if not _check_rate_limit(key, RL_SCOPE_VERIFY_RESEND, EMAIL_SEND_CAP_PER_HOUR, RESEND_COOLDOWN_SECONDS, now):
        db.session.commit()
        flash("Please wait a bit before requesting another verification email.", "info")
        return redirect(next_url)
    db.session.commit()

    sent = _send_verification_email(current_user, target, now)
    flash(
        "Verification email sent - check your inbox." if sent
        else "Couldn't send the email right now - try again shortly.",
        "success" if sent else "error",
    )
    return redirect(next_url)


@auth.get("/verify-email/<token>")
def verify_email(token):
    now = datetime.now(dt_timezone.utc)
    row = _find_valid_token(token, "verify_email", now)
    ok = False
    if row is not None:
        user = db.session.get(User, row.user_id)
        # The address this token was issued for might no longer be what's
        # pending (the user could have started another change since) -
        # only honor it if it still matches current state.
        current_target = user.pending_email or user.email if user is not None else None
        if user is not None and row.target_email == current_target:
            ok = _claim_verified_email(user, row.target_email, now)
        row.used_at = now
        db.session.commit()

    resp = make_response(render_template(
        "auth/verify_email_result.html", ok=ok,
        already_logged_in=current_user.is_authenticated,
    ))
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@auth.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("habits.dashboard"))

    form = ForgotPasswordForm()

    if form.validate_on_submit():
        now = datetime.now(dt_timezone.utc)
        email = form.email.data.strip().lower()
        ip = _client_ip()

        # Both checks always run and always get recorded, and the response
        # below is identical no matter what they find - whether the email
        # exists, is verified, or any limit is already hit never changes
        # what the requester sees.
        email_allowed = _check_rate_limit(email, RL_SCOPE_FORGOT_EMAIL, EMAIL_SEND_CAP_PER_HOUR, RESEND_COOLDOWN_SECONDS, now)
        ip_allowed = _check_rate_limit(ip, RL_SCOPE_FORGOT_IP, IP_REQUEST_CAP_PER_HOUR, 0, now)
        db.session.commit()

        if email_allowed and ip_allowed:
            user = User.query.filter_by(email=email).filter(User.email_verified_at.isnot(None)).first()
            if user is not None:
                account_locked_until = _aware_utc(user.forgot_locked_until)
                if not (account_locked_until and account_locked_until > now):
                    _send_reset_email(user, now)

        flash("If that email has a verified Habitual account, we've sent a password reset link to it.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html", form=form)


@auth.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    now = datetime.now(dt_timezone.utc)
    row = _find_valid_token(token, "reset", now)
    user = db.session.get(User, row.user_id) if row is not None else None
    if row is not None and user is not None and row.target_email != user.email:
        row = None  # the link was for an address this account no longer has

    if row is None or user is None:
        if request.method == "POST":
            ip = _client_ip()
            _check_rate_limit(ip, RL_SCOPE_RESET_SUBMIT_IP, IP_REQUEST_CAP_PER_HOUR, 0, now)
            # A bad GET (e.g. a mail client's safe-link prescanner fetching
            # an old email's link) never counts toward this - only a real
            # submission attempt does.
            attributed_user_id = _resolve_token_user_id(token, "reset")
            if attributed_user_id is not None:
                attributed_user = db.session.get(User, attributed_user_id)
                if attributed_user is not None:
                    attributed_user.failed_forgot_attempts += 1
                    if attributed_user.failed_forgot_attempts >= LOCKOUT_THRESHOLD:
                        attributed_user.forgot_locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            db.session.commit()
        resp = make_response(render_template("auth/reset_password.html", form=None, invalid=True))
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    form = ResetPasswordForm()
    if form.validate_on_submit() and _apply_zxcvbn_check(form, "new_password", user):
        row.used_at = now
        user.set_password(form.new_password.data)
        # Invalidates every session currently logged in as this user (see
        # User.get_id/load_user) - there's no "this is my session" to
        # spare here, unlike the account-security change-password flow,
        # since resetting via an emailed link means you're not currently
        # logged in anywhere you trust.
        user.session_version += 1
        user.failed_login_attempts = 0
        user.locked_until = None
        user.failed_forgot_attempts = 0
        user.forgot_locked_until = None
        db.session.commit()
        flash("Password reset - log in with your new password.", "success")
        return redirect(url_for("auth.login"))

    resp = make_response(render_template("auth/reset_password.html", form=form, invalid=False))
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@auth.get("/account/security")
@login_required
def account_security():
    return render_template(
        "auth/account_security.html",
        password_form=ChangePasswordForm(), email_form=ChangeEmailForm(), resend_form=CSRFOnlyForm(),
        delete_form=DeleteAccountForm(),
    )


@auth.post("/account/security/email")
@login_required
def change_email():
    form = ChangeEmailForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        taken_by_someone_else = User.query.filter(
            User.id != current_user.id, User.email == email, User.email_verified_at.isnot(None)
        ).first()
        if taken_by_someone_else is not None:
            # Authenticated context, not anonymous enumeration - unlike
            # forgot-password, there's no meaningful existence to protect
            # here (this is the user claiming an address, not probing one).
            form.email.errors.append("That email is already associated with another account.")
        else:
            now = datetime.now(dt_timezone.utc)
            current_user.pending_email = email
            db.session.commit()
            sent = _send_verification_email(current_user, email, now)
            flash(
                "Check your new email to confirm the change." if sent
                else "Couldn't send the verification email right now - try resending from here.",
                "success" if sent else "error",
            )
            return redirect(url_for("auth.account_security"))

    return render_template(
        "auth/account_security.html",
        password_form=ChangePasswordForm(), email_form=form, resend_form=CSRFOnlyForm(),
        delete_form=DeleteAccountForm(),
    ), 400


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
            # request. Must be the real model instance, not the
            # `current_user` LocalProxy itself - passing the proxy makes
            # Flask-Login cache the proxy as this request's g._login_user,
            # and every later read of current_user (even on a later
            # request, via the stale cached proxy) resolves back through
            # itself forever.
            login_user(current_user._get_current_object())
            flash("Password changed. Other devices have been signed out.", "success")
            return redirect(url_for("auth.account_security"))

    return render_template(
        "auth/account_security.html",
        password_form=form, email_form=ChangeEmailForm(), resend_form=CSRFOnlyForm(),
        delete_form=DeleteAccountForm(),
    ), 400


@auth.post("/account/security/delete")
@login_required
def delete_account():
    form = DeleteAccountForm()
    now = datetime.now(dt_timezone.utc)
    locked_until = _aware_utc(current_user.delete_locked_until)

    if locked_until and locked_until > now:
        minutes_left = int((locked_until - now).total_seconds() // 60) + 1
        flash(f"Too many failed attempts. Try again in {minutes_left} minute(s).", "error")
        return redirect(url_for("auth.account_security"))

    if form.validate_on_submit():
        username_ok = form.confirm_username.data.strip().lower() == current_user.username
        password_ok = current_user.check_password(form.password.data)

        if username_ok and password_ok:
            user = current_user._get_current_object()
            _delete_account(user)
            db.session.commit()
            logout_user()
            flash("Your account has been deleted.", "info")
            return redirect(url_for("home"))

        current_user.failed_delete_attempts += 1
        if current_user.failed_delete_attempts >= LOCKOUT_THRESHOLD:
            current_user.delete_locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        db.session.commit()
        if not username_ok:
            form.confirm_username.errors.append("That's not your username.")
        if not password_ok:
            form.password.errors.append("Incorrect password.")

    return render_template(
        "auth/account_security.html",
        password_form=ChangePasswordForm(), email_form=ChangeEmailForm(), resend_form=CSRFOnlyForm(),
        delete_form=form,
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

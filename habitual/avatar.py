"""Phase 4b: the commander avatar editor/locker - habitual.game's
AVATAR_SLOTS/AVATAR_STARTER_VALUES/validate_avatar_payload are the
single source of truth for what's actually ownable and saveable; this
module only adds the ROUTE, FORM, and display-only catalog (locked
options' labels/lock-reasons, for the picker grid and the try-on-but-
blocked UX) on top of that.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import HiddenField
from wtforms.validators import DataRequired, ValidationError

from habitual import db, game

avatar = Blueprint("avatar", __name__)

# Every value a slot can show in the picker grid, starter and locked
# alike (locked ones so they can be tried on, per the approved design -
# "Locked parts are visible and try-on-able, Save is blocked until
# every equipped part is a starter part"). (value, label, lock_reason)
# - lock_reason is None for starter values. Transcribed from docs/
# COLONIES_GAME_PLAN.md's "Avatar parts and planet looks" table, not
# invented. No shop/owned_items in this phase (Phase 8) - a locked
# value here is never purchasable or earnable yet, it's just real art
# the developer can preview before it's ownable.
AVATAR_CATALOG = {
    "helmet": [
        ("round", "Round", None), ("box", "Boxy", None),
        ("crest", "Crest", "Captain rank"),
    ],
    "visor": [
        ("open", "Open", None), ("amber", "Amber", None), ("steel", "Steel", None), ("rust", "Rust", None),
        ("signal", "Signal", "60 Energy"), ("mirror", "Mirror", "30-day streak"),
    ],
    "face": [(str(n), f"Skin {n}", None) for n in range(1, 6)],
    "hair": [
        ("none", "Covered", None), ("dark", "Dark", None), ("brown", "Brown", None), ("silver", "Silver", None),
    ],
    "suit": [
        ("phosphor", "Phosphor", None),
        ("steel", "Steel", "150 Energy"), ("signal", "Signal", "150 Energy"), ("bone", "Bone", "220 Energy"),
        ("admiral", "Admiral", "Top 3 sector finish"),
    ],
    "gear": [
        ("none", "None", None), ("antenna", "Antenna", None),
        ("lights", "Lights", "90 Energy"), ("jetpack", "Jetpack", "200 Energy"), ("scarf", "Scarf", "Beat a fleet boss"),
    ],
    "emblem": [
        ("none", "None", None), ("star", "Star", None), ("bolt", "Bolt", None),
        ("planet", "Planet", "Colony LV 10"),
    ],
}
AVATAR_SLOT_LABELS = {
    "helmet": "Helmet", "visor": "Visor", "face": "Skin tone", "hair": "Hair",
    "suit": "Suit", "gear": "Gear", "emblem": "Badge",
}
# The one value per slot that draws no layer at all (bare head/face,
# no visor, etc.) - every other value has a real sprite (confirmed
# against manifest.json during the Phase 4b art audit - nothing
# missing). A slot whose current value is here must never render an
# <img> at all, in every place a layer gets rendered - not an <img>
# with an empty/missing src.
AVATAR_NO_LAYER_VALUE = {"visor": "open", "hair": "none", "gear": "none", "emblem": "none"}

# Sprite filename prefix per slot - "gear" is the one slot whose own
# sprite files use a different word ("acc", for "accessory") than its
# slot name; every other slot's prefix matches its slot name exactly
# (confirmed against manifest.json: avatar_helmet_*, avatar_visor_*,
# avatar_face_*, avatar_hair_*, avatar_suit_*, avatar_acc_*, avatar_
# emblem_*). One mapping, used everywhere a filename is built (here,
# the picker grid via AVATAR_SWATCHES below, and the client-side live
# preview's JS), so this can only ever need fixing in one place.
AVATAR_FILE_PREFIX = {
    "helmet": "helmet", "visor": "visor", "face": "face", "hair": "hair",
    "suit": "suit", "gear": "acc", "emblem": "emblem",
}

# z-order for the stacked preview, back to front - mirrors the mock's
# own layering script (Playbook: "stacking transparent PNGs... in the
# same z-order the mock's script uses").
AVATAR_LAYER_ORDER = ("suit", "emblem", "helmet", "face", "hair", "visor", "gear")


def avatar_sprite_filename(slot: str, value: str) -> str:
    """The sprite filename for one slot/value pair - the one place
    that combines AVATAR_FILE_PREFIX with a value. Callers must check
    AVATAR_NO_LAYER_VALUE first - this never returns a sensible result
    for a "no layer" value, since no such sprite exists."""
    return f"avatar_{AVATAR_FILE_PREFIX[slot]}_{value}.png"


# Every (slot, value) pair's picker-grid thumbnail, including locked
# values (so they can be shown for try-on) - None for a "no layer"
# value, same meaning as colony.PLANET_LOOK_SWATCHES. Computed once
# from AVATAR_CATALOG so the picker grid template never builds a
# filename by string concatenation itself.
AVATAR_SWATCHES = {
    (slot, value): (None if AVATAR_NO_LAYER_VALUE.get(slot) == value else avatar_sprite_filename(slot, value))
    for slot, options in AVATAR_CATALOG.items()
    for value, _, _ in options
}


def avatar_layer_filenames(avatar_dict: dict) -> list[str]:
    """The sprite filenames to stack for a given avatar dict, back to
    front, skipping any slot whose value draws no layer. `avatar_dict`
    must already be validated (game.validate_avatar_payload) or be
    game.DEFAULT_AVATAR - this never takes raw request/query input, so
    a tampered value can never reach a filename here."""
    filenames = []
    for slot in AVATAR_LAYER_ORDER:
        value = avatar_dict[slot]
        if AVATAR_NO_LAYER_VALUE.get(slot) == value:
            continue
        filenames.append(avatar_sprite_filename(slot, value))
    return filenames


def _validate_known_avatar_value(slot):
    """First line of defense at the form layer: accept anything in this
    slot's FULL catalog (starter or locked - so a legitimate "try on a
    locked part" submission doesn't hard-fail here), reject anything
    else outright (a slot/value pair that was never offered at all).
    The SEPARATE, authoritative starter-only check is habitual.game.
    validate_avatar_payload, called in commander_locker() below - THAT
    is what actually decides whether a save is allowed."""
    known_values = {value for value, _, _ in AVATAR_CATALOG[slot]}

    def validator(form, field):
        if field.data not in known_values:
            raise ValidationError("Pick a known option.")
    return validator


class AvatarForm(FlaskForm):
    helmet = HiddenField(default=lambda: game.DEFAULT_AVATAR["helmet"], validators=[DataRequired(), _validate_known_avatar_value("helmet")])
    visor = HiddenField(default=lambda: game.DEFAULT_AVATAR["visor"], validators=[DataRequired(), _validate_known_avatar_value("visor")])
    face = HiddenField(default=lambda: game.DEFAULT_AVATAR["face"], validators=[DataRequired(), _validate_known_avatar_value("face")])
    hair = HiddenField(default=lambda: game.DEFAULT_AVATAR["hair"], validators=[DataRequired(), _validate_known_avatar_value("hair")])
    suit = HiddenField(default=lambda: game.DEFAULT_AVATAR["suit"], validators=[DataRequired(), _validate_known_avatar_value("suit")])
    gear = HiddenField(default=lambda: game.DEFAULT_AVATAR["gear"], validators=[DataRequired(), _validate_known_avatar_value("gear")])
    emblem = HiddenField(default=lambda: game.DEFAULT_AVATAR["emblem"], validators=[DataRequired(), _validate_known_avatar_value("emblem")])


class CSRFOnlyForm(FlaskForm):
    """Mirrors habitual.auth.CSRFOnlyForm exactly (not imported from
    there - auth.py is not a dependency of this module, and this is a
    zero-field form, nothing to actually share)."""


def onboarding_redirect_or_none(user):
    """A redirect to the commander step if `user` hasn't finished (or
    skipped) it yet, else None. `avatar IS NULL` is the one and only
    "has this user onboarded" sentinel - see User.avatar's comment."""
    if user.avatar is None:
        return redirect(url_for("avatar.commander_locker", onboarding=1))
    return None


@avatar.route("/commander", methods=["GET", "POST"])
@login_required
def commander_locker():
    onboarding = bool(request.args.get("onboarding"))
    current_avatar = current_user.avatar or game.DEFAULT_AVATAR
    form = AvatarForm(data=current_avatar)

    if form.validate_on_submit():
        payload = {slot: getattr(form, slot).data for slot in game.AVATAR_SLOTS}
        ok, failing_slot = game.validate_avatar_payload(payload)
        if ok:
            current_user.avatar = payload
            db.session.commit()
            if onboarding:
                return redirect(url_for("colony.edit_planet", onboarding=1))
            flash("Commander saved.", "success")
            return redirect(url_for("avatar.commander_locker"))
        # Soft block, not a hard error: keep showing exactly what they
        # tried on (not their last-saved avatar) so "tried on but not
        # saved" is visible, not just asserted in a flash message.
        current_avatar = payload
        flash(
            f"\"{AVATAR_SLOT_LABELS.get(failing_slot, failing_slot)}\" isn't unlocked yet - "
            "use free parts or pick a different option to save.",
            "info",
        )

    category_counts = _category_counts_for_class(current_user)
    return render_template(
        "avatar/editor.html",
        form=form,
        skip_form=CSRFOnlyForm(),
        onboarding=onboarding,
        avatar=current_avatar,
        avatar_catalog=AVATAR_CATALOG,
        avatar_slot_labels=AVATAR_SLOT_LABELS,
        avatar_no_layer_value=AVATAR_NO_LAYER_VALUE,
        avatar_file_prefix=AVATAR_FILE_PREFIX,
        avatar_swatches=AVATAR_SWATCHES,
        avatar_layer_order=AVATAR_LAYER_ORDER,
        rank=game.rank_for_xp(_earned_points_for(current_user)),
        commander_class=game.class_for_category_counts(category_counts),
        **_nav_shell_context(current_user),
    )


@avatar.post("/commander/skip")
@login_required
def skip_commander_step():
    if not CSRFOnlyForm().validate_on_submit():
        abort(400)
    if current_user.avatar is None:
        current_user.avatar = dict(game.DEFAULT_AVATAR)
        db.session.commit()
    return redirect(url_for("colony.edit_planet", onboarding=1))


def _earned_points_for(user):
    from habitual.habits import _header_stats  # local import avoids a circular import with habits.py
    return _header_stats(user)["earned_points"]


def _category_counts_for_class(user):
    from habitual.colony import _category_checkin_counts  # local import avoids a circular import with colony.py
    return _category_checkin_counts(user)


def _nav_shell_context(user):
    from habitual.habits import nav_shell_context  # local import avoids a circular import with habits.py
    return nav_shell_context(user)

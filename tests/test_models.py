from habitual.models import User


def test_password_hash_roundtrip(db):
    user = User(name="Aadhira", username="aadhira")
    user.set_password("Sup3r$ecret")
    db.session.add(user)
    db.session.commit()

    assert user.check_password("Sup3r$ecret") is True
    assert user.check_password("wrong-password") is False


def test_defaults(db):
    user = User(name="Aadhira", username="aadhira2")
    user.set_password("Sup3r$ecret")
    db.session.add(user)
    db.session.commit()

    assert user.timezone == "Asia/Kolkata"
    assert user.theme == "dark"
    assert user.failed_login_attempts == 0
    assert user.locked_until is None

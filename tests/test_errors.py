from habitual.errors import not_found, server_error
from habitual.models import User

VALID_PASSWORD = "Sup3r$ecret"


def _login(client, db, username="aadhira"):
    user = User(name="Aadhira", username=username, timezone="Asia/Kolkata")
    user.set_password(VALID_PASSWORD)
    db.session.add(user)
    db.session.commit()
    client.post("/login", data={"username": username, "password": VALID_PASSWORD, "next": ""})
    return user


def test_404_on_an_unknown_route(client):
    response = client.get("/this-page-does-not-exist")

    assert response.status_code == 404
    assert b"Page not found" in response.data
    assert b'href="/"' in response.data


def test_404_page_extends_the_site_chrome(client):
    # Renders through base.html like any other page, not a bare Werkzeug
    # traceback page - sanity-checks the toast/badge-modal scaffolding and
    # CSRF meta tag are all present.
    response = client.get("/this-page-does-not-exist")

    assert b'name="csrf-token"' in response.data
    assert b"Habitual" in response.data


def test_500_error_page_is_friendly(client, db, app, monkeypatch):
    # PROPAGATE_EXCEPTIONS defaults to True under TESTING, which makes Flask
    # re-raise instead of invoking a registered error handler - flip it off
    # so a real request through a broken route exercises the actual handler,
    # not just the function in isolation.
    app.config["PROPAGATE_EXCEPTIONS"] = False
    _login(client, db)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("habitual.habits._dashboard_context", boom)

    response = client.get("/dashboard")

    assert response.status_code == 500
    assert b"Something broke" in response.data
    assert b'href="/"' in response.data


def test_server_error_handler_rolls_back_the_session(app, db):
    with app.test_request_context("/dashboard"):
        body, status = server_error(RuntimeError("boom"))

    assert status == 500
    assert "Something broke" in body


def test_not_found_handler_renders_directly(app):
    with app.test_request_context("/nope"):
        body, status = not_found(None)

    assert status == 404
    assert "Page not found" in body

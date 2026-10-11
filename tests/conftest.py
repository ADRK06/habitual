import pytest

from habitual import create_app, db as _db, mailer
from habitual.config import TestConfig


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app, monkeypatch):
    # Every test that makes requests through `client` gets a recording
    # fake mailer instead of the real one - no test should ever print via
    # the console provider or attempt a real network call. Tests that care
    # what was "sent" (a verification/reset link) read client.sent_emails;
    # everyone else is unaffected either way.
    sent = []

    def fake_send_email(to_email, subject, text_body, html_body=None):
        sent.append({"to": to_email, "subject": subject, "text": text_body, "html": html_body})
        return True

    monkeypatch.setattr(mailer, "send_email", fake_send_email)

    test_client = app.test_client()
    test_client.sent_emails = sent
    return test_client

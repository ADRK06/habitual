import smtplib
import urllib.error

import pytest

from habitual import mailer


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Every provider branch reads straight from os.environ - start each
    # test from a blank slate so one test's env can't leak into another's.
    for key in (
        "EMAIL_PROVIDER", "VERCEL", "BREVO_API_KEY", "MAIL_FROM_EMAIL", "MAIL_FROM_NAME",
        "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)


# -- console (dev default) ----------------------------------------------------


def test_console_is_the_default_provider_and_prints(monkeypatch, capsys):
    result = mailer.send_email("a@example.com", "Subject", "Body text")
    assert result is True
    out = capsys.readouterr().out
    assert "a@example.com" in out
    assert "Subject" in out
    assert "Body text" in out


def test_console_refuses_on_vercel(monkeypatch, capsys):
    monkeypatch.setenv("VERCEL", "1")
    result = mailer.send_email("a@example.com", "Subject", "Body text")
    assert result is False
    assert "a@example.com" not in capsys.readouterr().out


# -- brevo ----------------------------------------------------------------------


def test_brevo_sends_correct_request(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "brevo")
    monkeypatch.setenv("BREVO_API_KEY", "secret-key")
    monkeypatch.setenv("MAIL_FROM_EMAIL", "noreply@habitual.app")
    monkeypatch.setenv("MAIL_FROM_NAME", "Habitual")

    captured = {}

    class FakeResponse:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = request.data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = mailer.send_email("to@example.com", "Hi", "text body", "<p>html</p>")
    assert result is True
    assert captured["url"] == mailer.BREVO_API_URL
    assert captured["headers"]["Api-key"] == "secret-key"
    assert captured["timeout"] == mailer.TIMEOUT_SECONDS
    import json
    payload = json.loads(captured["body"])
    assert payload["to"] == [{"email": "to@example.com"}]
    assert payload["sender"] == {"email": "noreply@habitual.app", "name": "Habitual"}
    assert payload["textContent"] == "text body"
    assert payload["htmlContent"] == "<p>html</p>"


def test_brevo_missing_config_fails_without_sending(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "brevo")
    # No BREVO_API_KEY/MAIL_FROM_EMAIL set.
    called = []
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: called.append(1))
    result = mailer.send_email("to@example.com", "Hi", "text body")
    assert result is False
    assert not called


def test_brevo_http_error_returns_false(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "brevo")
    monkeypatch.setenv("BREVO_API_KEY", "secret-key")
    monkeypatch.setenv("MAIL_FROM_EMAIL", "noreply@habitual.app")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            mailer.BREVO_API_URL, 400, "Bad Request", {}, fp=__import__("io").BytesIO(b'{"message":"bad"}')
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert mailer.send_email("to@example.com", "Hi", "text body") is False


def test_brevo_timeout_returns_false(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "brevo")
    monkeypatch.setenv("BREVO_API_KEY", "secret-key")
    monkeypatch.setenv("MAIL_FROM_EMAIL", "noreply@habitual.app")

    def fake_urlopen(request, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert mailer.send_email("to@example.com", "Hi", "text body") is False


# -- smtp -------------------------------------------------------------------


class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.logged_in = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def login(self, user, password):
        self.logged_in = (user, password)

    def sendmail(self, from_addr, to_addrs, message):
        self.sent = (from_addr, to_addrs, message)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_smtp_sends_with_login_and_message(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "me@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)

    result = mailer.send_email("to@example.com", "Hi", "text body", "<p>html</p>")
    assert result is True
    smtp = _FakeSMTP.instances[0]
    assert smtp.host == "smtp.gmail.com"
    assert smtp.timeout == mailer.TIMEOUT_SECONDS
    assert smtp.logged_in == ("me@gmail.com", "app-password")
    from_addr, to_addrs, message = smtp.sent
    assert to_addrs == ["to@example.com"]
    assert "text body" in message


def test_smtp_missing_config_fails_without_connecting(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    called = []
    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: called.append(1))
    assert mailer.send_email("to@example.com", "Hi", "text body") is False
    assert not called


def test_smtp_connection_error_returns_false(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_USER", "me@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")

    def raise_connection_error(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(smtplib, "SMTP_SSL", raise_connection_error)
    assert mailer.send_email("to@example.com", "Hi", "text body") is False


# -- unknown provider ----------------------------------------------------------


def test_unknown_provider_fails_closed(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "carrier-pigeon")
    assert mailer.send_email("to@example.com", "Hi", "text body") is False

import smtplib

import pytest

from habitual import mailer


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Every provider branch reads straight from os.environ - start each
    # test from a blank slate so one test's env can't leak into another's.
    for key in (
        "EMAIL_PROVIDER", "VERCEL", "MAIL_FROM_EMAIL", "MAIL_FROM_NAME",
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


def test_console_refuses_on_vercel(monkeypatch, capsys, caplog):
    monkeypatch.setenv("VERCEL", "1")
    result = mailer.send_email("a@example.com", "Subject", "Body text")
    assert result is False
    assert "a@example.com" not in capsys.readouterr().out
    assert "reason=console_on_vercel" in caplog.text


# -- smtp -----------------------------------------------------------------


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


def _set_smtp_env(monkeypatch, password="abcd efgh ijkl mnop"):
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("SMTP_USER", "me@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", password)
    monkeypatch.setenv("MAIL_FROM_EMAIL", "me@gmail.com")
    monkeypatch.setenv("MAIL_FROM_NAME", "Habitual")


def test_smtp_sends_with_login_and_message(monkeypatch):
    _FakeSMTP.instances = []
    _set_smtp_env(monkeypatch)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)

    result = mailer.send_email("to@example.com", "Hi", "text body", "<p>html</p>")
    assert result is True

    smtp = _FakeSMTP.instances[0]
    # Defaults to Gmail's host/port when SMTP_HOST/SMTP_PORT aren't set.
    assert smtp.host == "smtp.gmail.com"
    assert smtp.port == 465
    assert smtp.timeout == mailer.TIMEOUT_SECONDS
    # Spaces stripped from the app password as Google displays it.
    assert smtp.logged_in == ("me@gmail.com", "abcdefghijklmnop")

    from_addr, to_addrs, message = smtp.sent
    assert from_addr == "me@gmail.com"
    assert to_addrs == ["to@example.com"]
    assert "text body" in message
    assert "Habitual <me@gmail.com>" in message


def test_smtp_respects_custom_host_and_port(monkeypatch):
    _FakeSMTP.instances = []
    _set_smtp_env(monkeypatch)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)

    mailer.send_email("to@example.com", "Hi", "text body")
    assert _FakeSMTP.instances[0].host == "smtp.example.org"
    assert _FakeSMTP.instances[0].port == 587


def test_smtp_missing_config_fails_without_connecting(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    called = []
    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: called.append(1))
    assert mailer.send_email("to@example.com", "Hi", "text body") is False
    assert not called


def test_smtp_from_address_must_match_the_gmail_account(monkeypatch, caplog):
    _set_smtp_env(monkeypatch)
    monkeypatch.setenv("MAIL_FROM_EMAIL", "someone-else@example.com")
    called = []
    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: called.append(1))

    result = mailer.send_email("to@example.com", "Hi", "text body")
    assert result is False
    assert not called  # fails fast, never even attempts to connect
    assert "reason=from_address_mismatch" in caplog.text


def test_smtp_auth_failure_returns_false_and_logs_reason(monkeypatch, caplog):
    _set_smtp_env(monkeypatch)

    class _AuthFailSMTP(_FakeSMTP):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"Authentication failed")

    monkeypatch.setattr(smtplib, "SMTP_SSL", _AuthFailSMTP)
    result = mailer.send_email("to@example.com", "Hi", "text body")
    assert result is False
    assert "reason=auth" in caplog.text
    assert "535" not in caplog.text  # no provider detail leaked, just the fixed reason code


def test_smtp_timeout_returns_false_and_logs_reason(monkeypatch, caplog):
    _set_smtp_env(monkeypatch)

    def raise_timeout(*a, **k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(smtplib, "SMTP_SSL", raise_timeout)
    result = mailer.send_email("to@example.com", "Hi", "text body")
    assert result is False
    assert "reason=timeout" in caplog.text


def test_smtp_connection_refused_returns_false_and_logs_reason(monkeypatch, caplog):
    _set_smtp_env(monkeypatch)

    def raise_refused(*a, **k):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(smtplib, "SMTP_SSL", raise_refused)
    result = mailer.send_email("to@example.com", "Hi", "text body")
    assert result is False
    assert "reason=refused" in caplog.text


def test_smtp_never_logs_the_password_or_body(monkeypatch, caplog):
    _set_smtp_env(monkeypatch, password="super secret app password")

    def raise_refused(*a, **k):
        raise ConnectionRefusedError("x")

    monkeypatch.setattr(smtplib, "SMTP_SSL", raise_refused)
    mailer.send_email("to@example.com", "Hi", "a secret reset link body")
    assert "secretapppassword" not in caplog.text
    assert "secret app password" not in caplog.text
    assert "reset link" not in caplog.text


# -- unknown provider ----------------------------------------------------------


def test_unknown_provider_fails_closed(monkeypatch, caplog):
    monkeypatch.setenv("EMAIL_PROVIDER", "carrier-pigeon")
    assert mailer.send_email("to@example.com", "Hi", "text body") is False
    assert "reason=unknown_provider" in caplog.text

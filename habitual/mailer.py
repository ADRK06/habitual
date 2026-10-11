"""Provider-agnostic transactional email, selected via the EMAIL_PROVIDER
env var:

- "brevo"   - Brevo's HTTPS transactional API, stdlib urllib only (no new
              dependency). Env: BREVO_API_KEY, MAIL_FROM_EMAIL, MAIL_FROM_NAME.
- "smtp"    - smtplib over SSL (e.g. a dedicated Gmail + app password).
              Env: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, MAIL_FROM_EMAIL.
- "console" - dev default: prints the email to the Flask terminal instead
              of sending. Refuses outright if the VERCEL env var is set,
              so a missing/misconfigured EMAIL_PROVOIDER can never silently
              "succeed" on a real deployment without actually sending.

send_email() never raises - every failure mode (bad config, timeout,
non-2xx, network error) is caught and turned into a `False` return, since
callers must never claim a send succeeded when it didn't. Nothing here
ever logs the email body (it may contain a reset/verify link) or a secret
(API key, SMTP password) - only provider-side status/error text, which is
safe because it's never the message content itself.
"""
import json
import logging
import os
import smtplib
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_email(to_email: str, subject: str, text_body: str, html_body: str | None = None) -> bool:
    provider = (os.environ.get("EMAIL_PROVIDER") or "console").strip().lower()
    if provider == "brevo":
        return _send_via_brevo(to_email, subject, text_body, html_body)
    if provider == "smtp":
        return _send_via_smtp(to_email, subject, text_body, html_body)
    if provider == "console":
        return _send_via_console(to_email, subject, text_body)

    logger.error("Unknown EMAIL_PROVIDER %r - email not sent.", provider)
    return False


def _send_via_console(to_email: str, subject: str, text_body: str) -> bool:
    if os.environ.get("VERCEL"):
        logger.error(
            "EMAIL_PROVIDER is \"console\" (or unset) on a Vercel deployment - "
            "refusing to fake-send. Set EMAIL_PROVIDER=brevo or =smtp instead."
        )
        return False

    print(
        "\n----- EMAIL (console provider - not actually sent) -----\n"
        f"To: {to_email}\nSubject: {subject}\n\n{text_body}\n"
        "----------------------------------------------------------\n"
    )
    return True


def _send_via_brevo(to_email: str, subject: str, text_body: str, html_body: str | None) -> bool:
    api_key = os.environ.get("BREVO_API_KEY")
    from_email = os.environ.get("MAIL_FROM_EMAIL")
    from_name = os.environ.get("MAIL_FROM_NAME") or "Habitual"
    if not api_key or not from_email:
        logger.error("EMAIL_PROVIDER=brevo but BREVO_API_KEY/MAIL_FROM_EMAIL isn't set.")
        return False

    payload = {
        "sender": {"email": from_email, "name": from_name},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": text_body,
    }
    if html_body:
        payload["htmlContent"] = html_body

    request = urllib.request.Request(
        BREVO_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if 200 <= response.status < 300:
                return True
            logger.error("Brevo send failed: HTTP %s", response.status)
            return False
    except urllib.error.HTTPError as exc:
        # Brevo's own {code, message} error body - never the email we tried
        # to send, never a secret, so this is safe to log in full (bounded).
        body = exc.read().decode("utf-8", "replace")[:500]
        logger.error("Brevo send failed: HTTP %s - %s", exc.code, body)
        return False
    except (urllib.error.URLError, OSError) as exc:
        # Covers connection errors and timeouts (URLError/OSError both wrap
        # them in different Python/urllib versions) without ever risking a
        # hung request past TIMEOUT_SECONDS.
        logger.error("Brevo send failed: %s", exc)
        return False


def _send_via_smtp(to_email: str, subject: str, text_body: str, html_body: str | None) -> bool:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT") or 465)
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("MAIL_FROM_EMAIL") or user
    if not (host and user and password and from_email):
        logger.error("EMAIL_PROVIDER=smtp but SMTP_HOST/SMTP_USER/SMTP_PASSWORD/MAIL_FROM_EMAIL isn't fully set.")
        return False

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = to_email
    message.attach(MIMEText(text_body, "plain"))
    if html_body:
        message.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(host, port, timeout=TIMEOUT_SECONDS) as smtp:
            smtp.login(user, password)
            smtp.sendmail(from_email, [to_email], message.as_string())
        return True
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("SMTP send failed: %s", exc)
        return False

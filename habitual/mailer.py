"""Transactional email, selected via the EMAIL_PROVIDER env var:

- "smtp"    - Gmail over smtplib (SMTP_SSL, smtp.gmail.com:465) with an app
              password. Env: SMTP_HOST (defaults to smtp.gmail.com),
              SMTP_PORT (defaults to 465), SMTP_USER, SMTP_PASSWORD,
              MAIL_FROM_EMAIL, MAIL_FROM_NAME.
- "console" - dev default: prints the email to the Flask terminal instead
              of sending. Refuses outright if the VERCEL env var is set, so
              a missing/misconfigured EMAIL_PROVIDER can never silently
              "succeed" on a real deployment without actually sending.

send_email() never raises - every failure mode (bad config, timeout, auth
failure, connection refused) is caught and turned into a `False` return,
since callers must never claim a send succeeded when it didn't. Nothing
here ever logs the email body (it may contain a reset/verify link) or a
secret (the SMTP password) - only a short, fixed reason code.
"""
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 465


def send_email(to_email: str, subject: str, text_body: str, html_body: str | None = None) -> bool:
    provider = (os.environ.get("EMAIL_PROVIDER") or "console").strip().lower()
    if provider == "smtp":
        return _send_via_smtp(to_email, subject, text_body, html_body)
    if provider == "console":
        return _send_via_console(to_email, subject, text_body)

    # Deliberately loud, not a silent no-op: on a real deployment this is a
    # configuration bug, not a transient failure, and must show up in the
    # logs rather than just quietly dropping every email.
    logger.error("email send failed: provider=%s reason=unknown_provider", provider or "(unset)")
    return False


def _send_via_console(to_email: str, subject: str, text_body: str) -> bool:
    if os.environ.get("VERCEL"):
        logger.error(
            "email send failed: provider=console reason=console_on_vercel "
            "(EMAIL_PROVIDER is unset or \"console\" on a Vercel deployment - set EMAIL_PROVIDER=smtp)"
        )
        return False

    print(
        "\n----- EMAIL (console provider - not actually sent) -----\n"
        f"To: {to_email}\nSubject: {subject}\n\n{text_body}\n"
        "----------------------------------------------------------\n"
    )
    return True


def _send_via_smtp(to_email: str, subject: str, text_body: str, html_body: str | None) -> bool:
    host = os.environ.get("SMTP_HOST") or DEFAULT_SMTP_HOST
    port = int(os.environ.get("SMTP_PORT") or DEFAULT_SMTP_PORT)
    user = os.environ.get("SMTP_USER")
    # Google displays an app password as four space-separated groups of
    # four ("abcd efgh ijkl mnop") for readability - smtplib needs it
    # without the spaces.
    password = (os.environ.get("SMTP_PASSWORD") or "").replace(" ", "")
    from_name = os.environ.get("MAIL_FROM_NAME") or "Habitual"
    from_email = os.environ.get("MAIL_FROM_EMAIL") or user

    if not (host and user and password and from_email):
        logger.error("email send failed: provider=smtp reason=not_configured")
        return False
    if from_email.strip().lower() != user.strip().lower():
        # Gmail only delivers mail "From" the authenticated account (or a
        # verified alias, which this app doesn't set up) - a mismatch here
        # would otherwise surface as a confusing auth/relay error from
        # Gmail itself instead of this clear, fast, secret-free one.
        logger.error("email send failed: provider=smtp reason=from_address_mismatch")
        return False

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = formataddr((from_name, from_email))
    message["To"] = to_email
    message.attach(MIMEText(text_body, "plain"))
    if html_body:
        message.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(host, port, timeout=TIMEOUT_SECONDS) as smtp:
            smtp.login(user, password)
            smtp.sendmail(from_email, [to_email], message.as_string())
        return True
    except smtplib.SMTPAuthenticationError:
        # Wrong app password, or SMTP_USER/MAIL_FROM_EMAIL isn't a real
        # Gmail account - Google rejects the login itself.
        logger.error("email send failed: provider=smtp reason=auth")
        return False
    except TimeoutError:
        # The connection never completed within TIMEOUT_SECONDS - a slow or
        # silently-dropping network path, as opposed to an active refusal.
        logger.error("email send failed: provider=smtp reason=timeout")
        return False
    except ConnectionRefusedError:
        # Nothing was listening / the port was actively closed - the
        # network path exists but SMTP itself got rejected outright.
        logger.error("email send failed: provider=smtp reason=refused")
        return False
    except (smtplib.SMTPException, OSError):
        # Any other SMTP protocol error or network failure (DNS, a reset
        # connection mid-transfer, Gmail returning an unexpected response).
        logger.error("email send failed: provider=smtp reason=other")
        return False

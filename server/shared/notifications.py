"""Notification channel stubs.

Each send_* function logs what it would do in dev mode. Wire real
implementations by setting env vars in config.py and filling in the bodies.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from .. import config

log = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str, html: bool = False) -> bool:
    if not config.SMTP_HOST:
        log.info("[NOTIFY:email] to=%s subject=%s (no SMTP configured)", to, subject)
        return False
    try:
        msg = MIMEText(body, "html" if html else "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = config.SMTP_FROM
        msg["To"] = to
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as s:
            s.starttls()
            if config.SMTP_USER:
                s.login(config.SMTP_USER, config.SMTP_PASS)
            s.send_message(msg)
        return True
    except Exception as exc:
        log.error("[NOTIFY:email] failed: %s", exc)
        return False


def send_sms(to: str, message: str) -> bool:
    if not config.SMS_API_KEY:
        log.info("[NOTIFY:sms] to=%s msg=%s (no SMS configured)", to, message[:40])
        return False
    # Wire your SMS provider here (Twilio, Exotel, etc.)
    log.info("[NOTIFY:sms] stub — to=%s", to)
    return False


def send_whatsapp(to: str, message: str) -> bool:
    if not config.WHATSAPP_API_KEY:
        log.info("[NOTIFY:whatsapp] to=%s (no WA configured)", to)
        return False
    log.info("[NOTIFY:whatsapp] stub — to=%s", to)
    return False


def send_slack(text: str, channel: str = "") -> bool:
    if not config.SLACK_WEBHOOK:
        log.info("[NOTIFY:slack] %s (no webhook configured)", text[:60])
        return False
    try:
        import urllib.request, json as _json
        payload = _json.dumps({"text": text}).encode()
        urllib.request.urlopen(config.SLACK_WEBHOOK, payload, timeout=5)
        return True
    except Exception as exc:
        log.error("[NOTIFY:slack] failed: %s", exc)
        return False


def notify(
    *,
    email: str | None = None,
    phone: str | None = None,
    subject: str = "",
    body: str,
    channels: list[str] | None = None,
) -> None:
    """Dispatch to one or more channels. channels defaults to ['email']."""
    channels = channels or ["email"]
    if "email" in channels and email:
        send_email(email, subject, body)
    if "sms" in channels and phone:
        send_sms(phone, body)
    if "whatsapp" in channels and phone:
        send_whatsapp(phone, body)
    if "slack" in channels:
        send_slack(f"*{subject}*\n{body}")

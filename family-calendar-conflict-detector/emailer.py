"""SMTP sender for conflict alerts.

Uses a Gmail (or any SMTP) account + app password to actually send the alert
email -- this is the piece the Gmail *connector* can't do. Kept separate from
detection so it can be unit-tested (message construction) without a network.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage


def build_message(sender: str, recipients: list[str], subject: str,
                  body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send(msg: EmailMessage, host: str, port: int, username: str,
         password: str) -> None:
    """Send a message over STARTTLS (Gmail: smtp.gmail.com:587)."""
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls(context=context)
        server.login(username, password)
        server.send_message(msg)

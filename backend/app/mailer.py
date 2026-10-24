"""Sending email. Optional: with nothing configured, mail is off and every email option is hidden.

Ways to send, first match wins:
- Resend's HTTP API: RESEND_API_KEY + MAIL_FROM (needs a verified domain).
- SMTP (any provider, or a Gmail app password): SMTP_HOST + SMTP_USER + SMTP_PASS, with MAIL_FROM.
- Development only: MAIL_OUTBOX_DIR, where each email is written as .html and .txt files to look at.

Everything is sent in the background: a slow or failing mail server never holds up or breaks a
request. Logs never contain addresses, links or tokens: only which kind of email failed and why.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import smtplib
import ssl
import time
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from pathlib import Path

from .config import Settings
from .emails import Email

log = logging.getLogger("snazzlebop.mail")
RESEND_URL = "https://api.resend.com/emails"
TIMEOUT = 15.0
MAX_PENDING = 200  # emails waiting to go out; more are dropped (and logged) rather than queued forever


class Mailer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sent: list[tuple[str, Email]] = []  # (to, email) for tests: kept only when `keep` is on
        self.keep = False
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def mode(self) -> str:
        s = self.settings
        if s.resend_api_key and s.mail_from:
            return "resend"
        if s.smtp_host and s.smtp_user and s.smtp_pass and s.mail_from:
            return "smtp"
        if s.mail_outbox_dir and not s.is_production:
            return "outbox"
        return "memory" if self.keep else "off"

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    def send(self, to: str, email: Email, kind: str) -> None:
        """Queue one email. Returns at once; failures are logged, never raised."""
        if not self.enabled:
            return
        if len(self._tasks) >= MAX_PENDING:
            log.error("mail queue full, dropped: %s", kind)
            return
        task = asyncio.get_running_loop().create_task(self._deliver(to, email, kind))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Wait for queued emails (tests, and a clean shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _deliver(self, to: str, email: Email, kind: str) -> None:
        mode = self.mode
        try:
            if mode == "memory":
                self.sent.append((to, email))
            elif mode == "resend":
                await asyncio.to_thread(self._resend, to, email)
            elif mode == "smtp":
                await asyncio.to_thread(self._smtp, to, email)
            elif mode == "outbox":
                await asyncio.to_thread(self._outbox, to, email, kind)
        except Exception as exc:  # noqa: BLE001 - a mail failure must never surface to the request
            log.error("sending %s email failed: %s", kind, type(exc).__name__)

    # -- transports ------------------------------------------------------------------------------------
    def _resend(self, to: str, email: Email) -> None:
        body = json.dumps(
            {
                "from": self.settings.mail_from,
                "to": [to],
                "subject": email.subject,
                "html": email.html,
                "text": email.text,
            }
        ).encode()
        req = urllib.request.Request(  # noqa: S310 - RESEND_URL is a fixed https address
            RESEND_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.resend_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310  # nosec B310
                resp.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"resend status {exc.code}") from None

    def message(self, to: str, email: Email) -> EmailMessage:
        msg = EmailMessage()
        name, addr = parseaddr(self.settings.mail_from or "Snazzlebop <mail@localhost>")
        msg["From"] = formataddr((name or "Snazzlebop", addr))
        msg["To"] = to
        msg["Subject"] = email.subject
        msg["Message-ID"] = make_msgid(domain=addr.partition("@")[2] or None)
        msg.set_content(email.text)
        msg.add_alternative(email.html, subtype="html")
        return msg

    def _smtp(self, to: str, email: Email) -> None:
        s = self.settings
        context = ssl.create_default_context()
        if s.smtp_port == 465:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                s.smtp_host, s.smtp_port, timeout=TIMEOUT, context=context
            )
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=TIMEOUT)
            server.starttls(context=context)
        with server:
            server.login(s.smtp_user, s.smtp_pass)
            server.send_message(self.message(to, email))

    def _outbox(self, to: str, email: Email, kind: str) -> None:
        folder = Path(self.settings.mail_outbox_dir)
        folder.mkdir(parents=True, exist_ok=True)
        stem = f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}-{re.sub(r'[^a-z0-9]+', '-', to.lower())[:40]}"
        (folder / f"{stem}.html").write_text(email.html, encoding="utf-8")
        (folder / f"{stem}.txt").write_text(
            f"To: {to}\nSubject: {email.subject}\n\n{email.text}", encoding="utf-8"
        )

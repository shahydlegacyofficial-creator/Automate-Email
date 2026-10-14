"""Email sending back-ends.

* :class:`OutlookSender` drives the installed Microsoft Outlook (classic) desktop app
  through COM, so mail goes out from the Travel Essence mailbox and lands in its
  Sent Items exactly as if typed by hand.
* :class:`SmtpSender` talks to an SMTP server directly (e.g. Microsoft 365).
* :class:`SimulatedSender` sends nothing - useful for rehearsing a campaign.

Every sender is used from a single worker thread: ``open()`` → ``send()``… → ``close()``.
"""

from __future__ import annotations

import mimetypes
import os
import smtplib
import ssl
import sys
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from .htmlutil import extract_inline_images, html_to_text, merge_into_signature

PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
PR_ATTACHMENT_HIDDEN = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
DISPID_SEND_USING_ACCOUNT = 64209
OL_MAIL_ITEM = 0
OL_BY_VALUE = 1


class SendError(Exception):
    pass


@dataclass
class OutgoingEmail:
    to: list[str]
    subject: str
    html: str
    attachments: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)


def check_attachments(paths: list[str]) -> None:
    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        raise SendError("Attachment not found: " + ", ".join(os.path.basename(p) for p in missing))


def outlook_available() -> tuple[bool, str]:
    if not sys.platform.startswith("win"):
        return False, "Microsoft Outlook integration is only available on Windows."
    try:
        import win32com.client  # noqa: F401
        import pythoncom  # noqa: F401
    except ImportError:
        return False, "The pywin32 package is missing, so Outlook cannot be controlled."
    return True, ""


class BaseSender:
    label = "Sender"

    def open(self) -> None:  # pragma: no cover - interface
        pass

    def send(self, email: OutgoingEmail) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - interface
        pass

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class SimulatedSender(BaseSender):
    label = "Simulation (nothing is sent)"

    def __init__(self, delay: float = 0.6):
        self.delay = delay

    def send(self, email: OutgoingEmail) -> None:
        check_attachments(email.attachments)
        if not email.to:
            raise SendError("No recipient")
        time.sleep(self.delay)


class OutlookSender(BaseSender):
    label = "Microsoft Outlook"

    def __init__(self, account: str = "", include_signature: bool = False):
        self.account_address = (account or "").strip().lower()
        self.include_signature = include_signature
        self._app = None
        self._account = None
        self._com_initialised = False

    def open(self) -> None:
        ok, reason = outlook_available()
        if not ok:
            raise SendError(reason)
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        self._com_initialised = True
        try:
            self._app = win32com.client.Dispatch("Outlook.Application")
            namespace = self._app.GetNamespace("MAPI")
        except Exception as exc:
            raise SendError(
                "Could not start Microsoft Outlook. Make sure classic Outlook for Windows is "
                f"installed and signed in. ({exc})"
            ) from exc

        self._account = None
        if self.account_address:
            for acc in namespace.Accounts:
                address = (getattr(acc, "SmtpAddress", "") or "").lower()
                if address == self.account_address or (acc.DisplayName or "").lower() == self.account_address:
                    self._account = acc
                    break
            if self._account is None:
                raise SendError(f"The Outlook account '{self.account_address}' was not found.")

    def send(self, email: OutgoingEmail) -> None:
        if self._app is None:
            raise SendError("Outlook is not connected")
        check_attachments(email.attachments)
        body_html, inline_images = extract_inline_images(email.html)
        try:
            mail = self._app.CreateItem(OL_MAIL_ITEM)
            if self._account is not None:
                try:
                    mail._oleobj_.Invoke(*(DISPID_SEND_USING_ACCOUNT, 0, 8, 0, self._account))
                except Exception:
                    mail.SendUsingAccount = self._account
            mail.To = "; ".join(email.to)
            if email.cc:
                mail.CC = "; ".join(email.cc)
            if email.bcc:
                mail.BCC = "; ".join(email.bcc)
            mail.Subject = email.subject

            for cid, path in inline_images:
                att = mail.Attachments.Add(os.path.abspath(path), OL_BY_VALUE, 0)
                att.PropertyAccessor.SetProperty(PR_ATTACH_CONTENT_ID, cid)
                try:
                    att.PropertyAccessor.SetProperty(PR_ATTACHMENT_HIDDEN, True)
                except Exception:
                    pass
            for path in email.attachments:
                mail.Attachments.Add(os.path.abspath(path))

            if self.include_signature:
                try:
                    mail.GetInspector  # loads the default signature into HTMLBody
                    body_html = merge_into_signature(mail.HTMLBody, body_html)
                except Exception:
                    pass
            mail.HTMLBody = body_html
            mail.Send()
        except SendError:
            raise
        except Exception as exc:
            raise SendError(_com_error_text(exc)) from exc

    def close(self) -> None:
        self._account = None
        self._app = None
        if self._com_initialised:
            import pythoncom

            pythoncom.CoUninitialize()
            self._com_initialised = False


class SmtpSender(BaseSender):
    label = "SMTP"

    def __init__(self, host: str, port: int, security: str, username: str, password: str,
                 from_email: str, from_name: str = "", timeout: int = 60):
        self.host = host
        self.port = int(port)
        self.security = security
        self.username = username
        self.password = password
        self.from_email = from_email or username
        self.from_name = from_name
        self.timeout = timeout
        self._smtp: smtplib.SMTP | None = None

    def _connect(self) -> None:
        if not self.host:
            raise SendError("SMTP server is not configured (Settings → Sending method).")
        if not self.from_email:
            raise SendError("A 'From' email address is required for SMTP.")
        context = ssl.create_default_context()
        try:
            if self.security == "ssl":
                smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context)
            else:
                smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
                smtp.ehlo()
                if self.security == "starttls":
                    smtp.starttls(context=context)
                    smtp.ehlo()
            if self.username:
                smtp.login(self.username, self.password)
        except smtplib.SMTPAuthenticationError as exc:
            raise SendError("SMTP login failed - check the username and password "
                            "(Microsoft 365 may require SMTP AUTH to be enabled).") from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise SendError(f"Could not connect to {self.host}:{self.port} - {exc}") from exc
        self._smtp = smtp

    def open(self) -> None:
        self._connect()

    def _build(self, email: OutgoingEmail) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = formataddr((self.from_name, self.from_email)) if self.from_name else self.from_email
        msg["To"] = ", ".join(email.to)
        if email.cc:
            msg["Cc"] = ", ".join(email.cc)
        msg["Subject"] = email.subject
        msg["Message-ID"] = make_msgid(domain=self.from_email.rsplit("@", 1)[-1])
        body_html, inline_images = extract_inline_images(email.html)
        msg.set_content(html_to_text(email.html) or " ")
        msg.add_alternative(body_html, subtype="html")
        if inline_images:
            html_part = msg.get_payload()[1]
            for cid, path in inline_images:
                ctype = mimetypes.guess_type(path)[0] or "image/png"
                maintype, subtype = ctype.split("/", 1)
                with open(path, "rb") as fh:
                    html_part.add_related(fh.read(), maintype=maintype, subtype=subtype,
                                          cid=f"<{cid}>", filename=os.path.basename(path))
        for path in email.attachments:
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            with open(path, "rb") as fh:
                msg.add_attachment(fh.read(), maintype=maintype, subtype=subtype,
                                   filename=os.path.basename(path))
        return msg

    def send(self, email: OutgoingEmail) -> None:
        check_attachments(email.attachments)
        msg = self._build(email)
        recipients = email.to + email.cc + email.bcc
        for attempt in range(2):
            if self._smtp is None:
                self._connect()
            try:
                self._smtp.send_message(msg, to_addrs=recipients)
                return
            except smtplib.SMTPRecipientsRefused as exc:
                raise SendError(f"Recipient refused by server: {exc.recipients}") from exc
            except smtplib.SMTPServerDisconnected as exc:
                # Idle connections are often dropped between campaign sends; reconnect once.
                self._smtp = None
                if attempt:
                    raise SendError("The SMTP server closed the connection.") from exc
            except smtplib.SMTPException as exc:
                raise SendError(str(exc)) from exc
            except OSError as exc:
                self._smtp = None
                if attempt:
                    raise SendError(str(exc)) from exc

    def close(self) -> None:
        if self._smtp is not None:
            try:
                self._smtp.quit()
            except Exception:
                pass
            self._smtp = None


def _com_error_text(exc: Exception) -> str:
    args = getattr(exc, "args", ())
    # pywintypes.com_error: (hresult, text, (wcode, source, description, ...), argerr)
    if len(args) >= 3 and isinstance(args[2], tuple) and len(args[2]) >= 3 and args[2][2]:
        return str(args[2][2]).strip()
    if len(args) >= 2 and isinstance(args[1], str):
        return args[1]
    return str(exc)


def create_sender(settings: dict, password: str = "") -> BaseSender:
    backend = settings.get("backend", "outlook")
    if backend == "smtp":
        return SmtpSender(
            host=settings.get("smtp_host", ""),
            port=int(settings.get("smtp_port", 587) or 587),
            security=settings.get("smtp_security", "starttls"),
            username=settings.get("smtp_username", ""),
            password=password,
            from_email=settings.get("smtp_from_email", ""),
            from_name=settings.get("smtp_from_name", ""),
        )
    if backend == "simulate":
        return SimulatedSender()
    if backend == "graph":
        from .graph import GraphSender, client_from_settings   # local import: graph imports this module

        return GraphSender(client_from_settings(settings))
    return OutlookSender(settings.get("outlook_account", ""), bool(settings.get("include_signature")))


def backend_label(settings: dict) -> str:
    backend = settings.get("backend", "outlook")
    if backend == "smtp":
        return f"SMTP · {settings.get('smtp_from_email') or settings.get('smtp_username') or 'not configured'}"
    if backend == "simulate":
        return "Simulation mode (no emails are sent)"
    if backend == "graph":
        return f"Microsoft 365 / new Outlook · {settings.get('ms_account') or 'not signed in'}"
    account = settings.get("outlook_account") or "default account"
    return f"Microsoft Outlook · {account}"

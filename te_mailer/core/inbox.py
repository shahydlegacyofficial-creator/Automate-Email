"""Receiving email: the Travel Essence inbox.

Any combination of mailboxes can be watched:

* ``outlook``  - every account in the classic Outlook app on this PC (COM)
* ``graph``    - the Microsoft 365 / new Outlook mailbox signed in under Settings
* ``imap``     - any number of IMAP mailboxes (web-host, Zoho, Gmail, ...)
* ``simulate`` - a practice mailbox with sample emails, in Simulation mode only

Each email gets a stable ``key`` from its mailbox and, the first time the app sees
it, a local ever-increasing number ``seq`` - so "what arrived since #41?" is one
cheap question for the AI assistant. The first look at a mailbox is quiet: what is
already there is numbered but not announced as new.

No Qt in here. The GUI and the MCP tools call it from worker threads; the
:class:`Inbox` serialises access with a lock.
"""

from __future__ import annotations

import base64
import email as email_lib
import hashlib
import html as html_lib
import imaplib
import logging
import os
import re
import ssl
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from email import policy
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from typing import Callable

from . import storage
from .htmlutil import BODY_OPEN_RE, body_inner, build_email_html, extract_inline_images, html_to_text
from .senders import (
    OL_BY_VALUE, PR_ATTACH_CONTENT_ID, PR_ATTACHMENT_HIDDEN, BaseSender, OutgoingEmail, SendError,
    check_attachments, outlook_available,
)

log = logging.getLogger(__name__)

FETCH_LIMIT = 50                 # newest emails read per mailbox on each check
MAX_SEEN = 5000                  # remembered keys (so an old email never counts as new again)
MAX_FULL_FETCH = 3 * 1024 * 1024  # IMAP: bigger emails are listed from their headers only
PREVIEW_CHARS = 280


@dataclass
class InboxMessage:
    key: str
    source: str                   # outlook | graph | imap | simulate
    account: str                  # which mailbox received it
    from_name: str
    from_email: str
    subject: str
    received: str                 # ISO 8601, local time
    preview: str = ""
    unread: bool = True
    attachments: int = 0
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    reply_to: str = ""
    message_id: str = ""          # RFC 5322 Message-ID (threads IMAP replies)
    references: str = ""
    seq: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "InboxMessage":
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def sender(self) -> str:
        return f"{self.from_name} <{self.from_email}>" if self.from_name else self.from_email


# ====================================================================== helpers
def _clean_preview(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:PREVIEW_CHARS]


def _iso(dt: datetime | None) -> str:
    return (dt or datetime.now()).replace(microsecond=0).isoformat()


def reply_subject(subject: str) -> str:
    subject = (subject or "").strip()
    return subject if re.match(r"^(re|aw|sv)\s*:", subject, re.IGNORECASE) else f"Re: {subject}"


def reply_fragment(editor_html: str, signature: str = "") -> str:
    """Our reply as a block that can sit on top of the quoted original."""
    inner, style = body_inner(build_email_html(editor_html, signature))
    return f"<div>{inner}</div><br>" if not style else f"<div style=\"{style}\">{inner}</div><br>"


def insert_at_top(document: str, fragment: str) -> str:
    """Put ``fragment`` straight after <body ...> (Outlook/Graph reply drafts quote below it)."""
    m = BODY_OPEN_RE.search(document or "")
    if not m:
        return fragment + (document or "")
    return document[: m.end()] + fragment + document[m.end():]


def quoted_reply_document(fragment: str, msg: InboxMessage, original_html: str) -> str:
    """Reply + "On <date>, <sender> wrote:" + the original, for mailboxes that don't quote for us."""
    when = msg.received.replace("T", " ")[:16]
    original, _ = body_inner(original_html or "")
    return ("<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\"></head><body>"
            f"{fragment}<div style=\"font-family:'Segoe UI', Arial, sans-serif; font-size:10pt; color:#555\">"
            f"On {html_lib.escape(when)}, {html_lib.escape(msg.sender)} wrote:</div>"
            "<blockquote style=\"margin:4px 0 0 4px; border-left:2px solid #ccc; padding-left:10px\">"
            f"{original}</blockquote></body></html>")


def _cache_dir(key: str):
    path = storage.sub_dir("inbox_cache") / hashlib.sha1(key.encode()).hexdigest()[:16]
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file_url(path) -> str:
    return "file:///" + str(path).replace("\\", "/")


def _safe_name(name: str, fallback: str = "attachment") -> str:
    return re.sub(r'[\\/:*?"<>|\r\n]', "_", name or "")[:120] or fallback


def reply_recipients(msg: InboxMessage, reply_all: bool, own: set[str]) -> tuple[list[str], list[str]]:
    sender = (msg.reply_to or msg.from_email).lower()
    to = [sender] if sender else []
    cc: list[str] = []
    if reply_all:
        for address in msg.to + msg.cc:
            address = address.lower()
            if address and address not in own and address not in to and address not in cc:
                cc.append(address)
    return to, cc


# ====================================================================== mailboxes
class InboxSource:
    """One mailbox. Every method may block (network / COM) - never call on the GUI thread."""

    kind = ""

    def __init__(self, name: str):
        self.name = name          # stable id, e.g. "imap:sales@host"
        self.label = name

    def fetch(self, limit: int, known: dict[str, dict]) -> list[InboxMessage]:
        raise NotImplementedError

    def body(self, msg: InboxMessage) -> dict:
        """{"html": str, "text": str, "attachments": [file names]}"""
        raise NotImplementedError

    def set_read(self, msg: InboxMessage, read: bool) -> None:
        raise NotImplementedError

    def reply(self, msg: InboxMessage, fragment: str, attachments: list[str], reply_all: bool) -> dict:
        """Send the reply; returns {"to": [...], "cc": [...]}."""
        raise NotImplementedError


# ---------------------------------------------------------------- classic Outlook
OL_FOLDER_INBOX = 6
OL_MAIL_CLASS = 43
OL_TO, OL_CC = 1, 2


class OutlookSource(InboxSource):
    """Every account's Inbox in the classic Outlook app (replies go out from that account)."""

    kind = "outlook"

    def __init__(self):
        super().__init__("outlook")
        self.label = "Outlook app on this PC"

    @staticmethod
    def _split(key: str) -> tuple[str, str]:
        store_id, entry_id = key.split(":", 1)[1].split("|", 1)
        return store_id, entry_id

    @staticmethod
    def running() -> bool:
        """Is Outlook already open? (Checking must not start it in the background every few minutes.)"""
        ok, _ = outlook_available()
        if not ok:
            return False
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            win32com.client.GetActiveObject("Outlook.Application")
            return True
        except Exception:
            return False
        finally:
            pythoncom.CoUninitialize()

    def fetch(self, limit, known):
        from .outlook_data import _safe, _to_datetime, outlook_session, recipient_smtp, sender_smtp

        ok, reason = outlook_available()
        if not ok:
            raise SendError(reason)
        if not self.running():
            raise SendError("Outlook is not open - open it and new emails will show here.")
        out: list[InboxMessage] = []
        with outlook_session() as (_app, ns):
            for store in ns.Stores:
                try:
                    folder = store.GetDefaultFolder(OL_FOLDER_INBOX)
                except Exception:
                    continue   # archives / public folders have no Inbox
                account = _safe(store, "DisplayName")
                store_id = _safe(folder, "StoreID")
                items = folder.Items
                try:
                    items.Sort("[ReceivedTime]", True)
                except Exception:
                    pass
                item = items.GetFirst()
                count = 0
                while item is not None and count < limit:
                    if _safe(item, "Class", 0) == OL_MAIL_CLASS:
                        count += 1
                        key = f"outlook:{store_id}|{_safe(item, 'EntryID')}"
                        if key in known:   # only the read/unread flag can have changed
                            row = InboxMessage.from_dict(known[key])
                            row.unread = bool(_safe(item, "UnRead", False))
                            out.append(row)
                        else:
                            to, cc = [], []
                            try:
                                for rcp in item.Recipients:
                                    address = recipient_smtp(rcp)
                                    if address:
                                        (cc if _safe(rcp, "Type", OL_TO) == OL_CC else to).append(address)
                            except Exception:
                                pass
                            try:
                                attachments = int(item.Attachments.Count)
                            except Exception:
                                attachments = 0
                            out.append(InboxMessage(
                                key=key, source=self.kind, account=account,
                                from_name=_safe(item, "SenderName"), from_email=sender_smtp(item),
                                subject=_safe(item, "Subject"),
                                received=_iso(_to_datetime(_safe(item, "ReceivedTime", None))),
                                preview=_clean_preview(_safe(item, "Body")),
                                unread=bool(_safe(item, "UnRead", False)), attachments=attachments,
                                to=to, cc=cc))
                    item = items.GetNext()
        return out

    def _item(self, ns, msg):
        store_id, entry_id = self._split(msg.key)
        return ns.GetItemFromID(entry_id, store_id)

    def body(self, msg):
        from .outlook_data import _safe, outlook_session

        with outlook_session() as (_app, ns):
            item = self._item(ns, msg)
            text = _safe(item, "Body")
            html = _safe(item, "HTMLBody") or f"<pre>{html_lib.escape(text)}</pre>"
            names: list[str] = []
            target = _cache_dir(msg.key)
            try:
                count = int(item.Attachments.Count)
            except Exception:
                count = 0
            for i in range(1, count + 1):
                att = item.Attachments.Item(i)
                name = _safe_name(_safe(att, "FileName"), f"attachment{i}")
                try:
                    cid = att.PropertyAccessor.GetProperty(PR_ATTACH_CONTENT_ID) or ""
                except Exception:
                    cid = ""
                if cid and f"cid:{cid}".lower() in html.lower():
                    path = target / name
                    try:
                        att.SaveAsFile(str(path))
                        html = re.sub(rf"cid:{re.escape(cid)}", _file_url(path), html, flags=re.IGNORECASE)
                    except Exception:
                        pass
                    continue
                names.append(name)
            return {"html": html, "text": text, "attachments": names}

    def set_read(self, msg, read):
        from .outlook_data import outlook_session

        with outlook_session() as (_app, ns):
            item = self._item(ns, msg)
            item.UnRead = not read
            item.Save()

    def reply(self, msg, fragment, attachments, reply_all):
        from .outlook_data import _safe, outlook_session, recipient_smtp
        from .senders import _com_error_text

        check_attachments(attachments)
        with outlook_session() as (_app, ns):
            try:
                item = self._item(ns, msg)
                draft = item.ReplyAll() if reply_all else item.Reply()
                document, inline = extract_inline_images(insert_at_top(draft.HTMLBody or "", fragment))
                for cid, path in inline:
                    att = draft.Attachments.Add(os.path.abspath(path), OL_BY_VALUE, 0)
                    att.PropertyAccessor.SetProperty(PR_ATTACH_CONTENT_ID, cid)
                    try:
                        att.PropertyAccessor.SetProperty(PR_ATTACHMENT_HIDDEN, True)
                    except Exception:
                        pass
                for path in attachments:
                    draft.Attachments.Add(os.path.abspath(path))
                draft.HTMLBody = document
                to, cc = [], []
                for rcp in draft.Recipients:
                    address = recipient_smtp(rcp) or _safe(rcp, "Address")
                    (cc if _safe(rcp, "Type", OL_TO) == OL_CC else to).append(address)
                draft.Send()
            except SendError:
                raise
            except Exception as exc:
                raise SendError(_com_error_text(exc)) from exc
        return {"to": to, "cc": cc}


# ---------------------------------------------------------------- Microsoft 365 / Graph
class GraphSource(InboxSource):
    """The signed-in Microsoft 365 / new Outlook mailbox."""

    kind = "graph"
    FIELDS = ("id,subject,from,replyTo,toRecipients,ccRecipients,receivedDateTime,bodyPreview,isRead,"
              "hasAttachments,internetMessageId")

    def __init__(self, client, account: str):
        super().__init__("graph")
        self.client = client
        self.account = account or "Microsoft 365"
        self.label = f"Microsoft 365 · {self.account}"

    @staticmethod
    def _path(msg_or_id) -> str:
        from .graph import _encode

        raw = msg_or_id.key.split(":", 1)[1] if isinstance(msg_or_id, InboxMessage) else msg_or_id
        return "/me/messages/" + _encode(raw)

    @staticmethod
    def _addresses(items) -> list[str]:
        return [((r or {}).get("emailAddress") or {}).get("address", "").lower() for r in items or []
                if ((r or {}).get("emailAddress") or {}).get("address")]

    def fetch(self, limit, known):
        from .graph import _parse_date

        data = self.client.request(
            "GET", f"/me/mailFolders/inbox/messages?$top={int(limit)}"
                   f"&$orderby=receivedDateTime%20desc&$select={self.FIELDS}")
        out = []
        for m in data.get("value", []):
            sender = (m.get("from") or {}).get("emailAddress") or {}
            reply_to = self._addresses(m.get("replyTo"))
            out.append(InboxMessage(
                key="graph:" + m["id"], source=self.kind, account=self.account,
                from_name=sender.get("name") or "", from_email=(sender.get("address") or "").lower(),
                subject=m.get("subject") or "", received=_iso(_parse_date(m.get("receivedDateTime"))),
                preview=_clean_preview(m.get("bodyPreview")), unread=not m.get("isRead", False),
                attachments=1 if m.get("hasAttachments") else 0,
                to=self._addresses(m.get("toRecipients")), cc=self._addresses(m.get("ccRecipients")),
                reply_to=reply_to[0] if reply_to else "", message_id=m.get("internetMessageId") or ""))
        return out

    def body(self, msg):
        path = self._path(msg)
        data = self.client.request("GET", path + "?$select=body,hasAttachments")
        body = data.get("body") or {}
        content = body.get("content") or ""
        if (body.get("contentType") or "").lower() == "text":
            text, html = content, f"<pre>{html_lib.escape(content)}</pre>"
        else:
            html, text = content, html_to_text(content)
        names: list[str] = []
        if data.get("hasAttachments") or "cid:" in html.lower():
            target = _cache_dir(msg.key)
            for att in self.client.request("GET", path + "/attachments").get("value", []):
                name = _safe_name(att.get("name"))
                cid = (att.get("contentId") or "").strip("<>")
                if att.get("isInline") and cid and att.get("contentBytes") and f"cid:{cid}".lower() in html.lower():
                    file_path = target / name
                    file_path.write_bytes(base64.b64decode(att["contentBytes"]))
                    html = re.sub(rf"cid:{re.escape(cid)}", _file_url(file_path), html, flags=re.IGNORECASE)
                elif not att.get("isInline"):
                    names.append(name)
        return {"html": html, "text": text, "attachments": names}

    def set_read(self, msg, read):
        self.client.request("PATCH", self._path(msg), {"isRead": bool(read)})

    def reply(self, msg, fragment, attachments, reply_all):
        from .graph import _encode, _mime

        check_attachments(attachments)
        draft = self.client.request("POST", self._path(msg) + ("/createReplyAll" if reply_all else "/createReply"), {})
        draft_path = "/me/messages/" + _encode(draft["id"])
        try:
            quoted = (draft.get("body") or {}).get("content") or ""
            document, inline = extract_inline_images(insert_at_top(quoted, fragment))
            self.client.request("PATCH", draft_path, {"body": {"contentType": "HTML", "content": document}})
            for cid, path in inline:
                with open(path, "rb") as fh:
                    self.client.request("POST", draft_path + "/attachments", {
                        "@odata.type": "#microsoft.graph.fileAttachment", "name": cid, "contentType": _mime(path),
                        "contentBytes": base64.b64encode(fh.read()).decode(), "isInline": True, "contentId": cid})
            from .graph import SIMPLE_ATTACHMENT_LIMIT

            for path in attachments:
                if os.path.getsize(path) > SIMPLE_ATTACHMENT_LIMIT:
                    self.client._upload(_encode(draft["id"]), path)
                    continue
                with open(path, "rb") as fh:
                    self.client.request("POST", draft_path + "/attachments", {
                        "@odata.type": "#microsoft.graph.fileAttachment", "name": os.path.basename(path),
                        "contentType": _mime(path), "contentBytes": base64.b64encode(fh.read()).decode()})
            self.client.request("POST", draft_path + "/send")
        except Exception:
            try:
                self.client.request("DELETE", draft_path)
            except SendError:
                pass
            raise
        return {"to": self._addresses(draft.get("toRecipients")), "cc": self._addresses(draft.get("ccRecipients"))}


# ---------------------------------------------------------------- IMAP
def _parse_message(raw: bytes) -> email_lib.message.EmailMessage:
    return email_lib.message_from_bytes(raw, policy=policy.default)


def _message_text(msg) -> tuple[str, str]:
    """(html, text) of a parsed email - whichever parts it has."""
    html = text = ""
    try:
        part = msg.get_body(preferencelist=("html",))
        if part is not None:
            html = part.get_content()
        part = msg.get_body(preferencelist=("plain",))
        if part is not None:
            text = part.get_content()
    except Exception:
        pass
    if not text and html:
        text = html_to_text(html)
    if not html and text:
        html = f"<pre style=\"white-space:pre-wrap; font-family:inherit\">{html_lib.escape(text)}</pre>"
    return html, text


def _header(msg, name: str) -> str:
    try:
        return str(msg.get(name, "") or "")
    except Exception:
        return ""


class ImapSource(InboxSource):
    """An IMAP mailbox. Replies go out through the app's sending method, threaded with In-Reply-To."""

    kind = "imap"

    def __init__(self, account: dict, password: str, sender_factory: Callable[[], BaseSender] | None = None,
                 timeout: int = 30, own: set[str] | None = None):
        self.host = (account.get("host") or "").strip()
        self.port = int(account.get("port") or 993)
        self.security = account.get("security") or "ssl"
        self.username = (account.get("username") or "").strip()
        super().__init__(f"imap:{self.username}@{self.host}")
        self.label = account.get("name") or self.username
        self.password = password
        self.sender_factory = sender_factory
        self.timeout = timeout
        self.own = {self.username.lower(), *(a.lower() for a in (own or set()) if a)}

    # -------------------------------------------------------------- connection
    def _connect(self) -> imaplib.IMAP4:
        if not self.host or not self.username:
            raise SendError("The IMAP mailbox needs a server and a username.")
        context = ssl.create_default_context()
        try:
            if self.security == "ssl":
                conn = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=context, timeout=self.timeout)
            else:
                conn = imaplib.IMAP4(self.host, self.port, timeout=self.timeout)
                if self.security == "starttls":
                    conn.starttls(ssl_context=context)
        except (OSError, imaplib.IMAP4.error) as exc:
            raise SendError(f"Could not connect to {self.host}:{self.port} - {exc}") from exc
        try:
            conn.login(self.username, self.password)
        except imaplib.IMAP4.error as exc:
            try:
                conn.logout()
            except Exception:
                pass
            raise SendError(f"{self.username}: sign-in failed - check the password (or app password).") from exc
        return conn

    def _open(self, readonly: bool = True) -> tuple[imaplib.IMAP4, str]:
        conn = self._connect()
        typ, _ = conn.select("INBOX", readonly=readonly)
        if typ != "OK":
            conn.logout()
            raise SendError(f"{self.username}: the Inbox could not be opened.")
        validity = (conn.response("UIDVALIDITY")[1] or [b"0"])[0]
        return conn, (validity or b"0").decode()

    @staticmethod
    def _close(conn) -> None:
        try:
            conn.logout()
        except Exception:
            pass

    def _key(self, validity: str, uid: str) -> str:
        return f"{self.name}:{validity}:{uid}"

    @staticmethod
    def _uid(msg: InboxMessage) -> str:
        return msg.key.rsplit(":", 1)[1]

    @staticmethod
    def _flags_of(meta: bytes) -> tuple[str, bool]:
        uid = re.search(rb"UID (\d+)", meta)
        flags = re.search(rb"FLAGS \(([^)]*)\)", meta)
        seen = bool(flags and b"\\seen" in flags.group(1).lower())
        return (uid.group(1).decode() if uid else ""), seen

    def _fetch_raw(self, conn, uid: str, header_only: bool = False) -> tuple[bytes, bool]:
        part = "BODY.PEEK[HEADER]" if header_only else "BODY.PEEK[]"
        typ, data = conn.uid("FETCH", uid, f"(UID FLAGS {part})")
        if typ != "OK":
            raise SendError(f"{self.username}: could not read email {uid}.")
        raw, meta = None, b""
        for item in data or []:
            if isinstance(item, tuple):
                meta += item[0]
                raw = raw if raw is not None else item[1]
            elif isinstance(item, bytes):
                meta += item        # some servers send FLAGS after the message literal
        if raw is None:
            raise SendError(f"{self.username}: email {uid} is no longer in the Inbox.")
        return raw, self._flags_of(meta)[1]

    # -------------------------------------------------------------- reading
    def fetch(self, limit, known):
        conn, validity = self._open()
        try:
            typ, data = conn.uid("SEARCH", None, "ALL")
            uids = (data[0] or b"").split() if typ == "OK" else []
            uids = [u.decode() for u in uids[-limit:]]
            if not uids:
                return []
            flags: dict[str, bool] = {}
            typ, data = conn.uid("FETCH", ",".join(uids), "(UID FLAGS RFC822.SIZE)")
            sizes: dict[str, int] = {}
            for item in data or []:
                meta = item[0] if isinstance(item, tuple) else item
                if not isinstance(meta, bytes):
                    continue
                uid, seen = self._flags_of(meta)
                if uid:
                    flags[uid] = seen
                    size = re.search(rb"RFC822\.SIZE (\d+)", meta)
                    sizes[uid] = int(size.group(1)) if size else 0
            out = []
            for uid in reversed(uids):    # newest first
                key = self._key(validity, uid)
                if key in known:
                    row = InboxMessage.from_dict(known[key])
                    row.unread = not flags.get(uid, not row.unread)
                    out.append(row)
                    continue
                big = sizes.get(uid, 0) > MAX_FULL_FETCH
                raw, seen = self._fetch_raw(conn, uid, header_only=big)
                out.append(self._row(key, _parse_message(raw), seen, big))
            return out
        finally:
            self._close(conn)

    def _row(self, key: str, msg, seen: bool, big: bool) -> InboxMessage:
        name, address = parseaddr(_header(msg, "From"))
        reply_to = parseaddr(_header(msg, "Reply-To"))[1]
        try:
            when = parsedate_to_datetime(_header(msg, "Date"))
            when = when.astimezone().replace(tzinfo=None) if when.tzinfo else when
        except Exception:
            when = None
        if big:
            preview, attachments = "(large email - open it to read)", 1
        else:
            preview = _message_text(msg)[1]
            attachments = sum(1 for _ in msg.iter_attachments()) if msg.is_multipart() else 0
        return InboxMessage(
            key=key, source=self.kind, account=self.label, from_name=name, from_email=address.lower(),
            subject=_header(msg, "Subject"), received=_iso(when), preview=_clean_preview(preview),
            unread=not seen, attachments=attachments,
            to=[a.lower() for _, a in getaddresses([_header(msg, "To")]) if a],
            cc=[a.lower() for _, a in getaddresses([_header(msg, "Cc")]) if a],
            reply_to=reply_to.lower(), message_id=_header(msg, "Message-ID").strip(),
            references=_header(msg, "References").strip())

    def body(self, msg):
        conn, _ = self._open()
        try:
            raw, _ = self._fetch_raw(conn, self._uid(msg))
        finally:
            self._close(conn)
        parsed = _parse_message(raw)
        html, text = _message_text(parsed)
        target = _cache_dir(msg.key)
        names = []
        for part in parsed.walk():
            if part.is_multipart():
                continue
            cid = (part.get("Content-ID") or "").strip().strip("<>")
            name = part.get_filename()
            if cid and f"cid:{cid}".lower() in html.lower():
                path = target / _safe_name(name or cid)
                try:
                    path.write_bytes(part.get_payload(decode=True) or b"")
                    html = re.sub(rf"cid:{re.escape(cid)}", _file_url(path), html, flags=re.IGNORECASE)
                except OSError:
                    pass
            elif name:
                names.append(_safe_name(name))
        return {"html": html, "text": text, "attachments": names}

    def set_read(self, msg, read):
        conn, _ = self._open(readonly=False)
        try:
            conn.uid("STORE", self._uid(msg), "+FLAGS" if read else "-FLAGS", "(\\Seen)")
        finally:
            self._close(conn)

    def reply(self, msg, fragment, attachments, reply_all):
        if self.sender_factory is None:
            raise SendError("No sending method is set up for replies (Settings → Sending method).")
        check_attachments(attachments)
        original = self.body(msg)
        to, cc = reply_recipients(msg, reply_all, self.own)
        if not to:
            raise SendError("This email has no sender address to reply to.")
        headers = {}
        if msg.message_id:
            headers = {"In-Reply-To": msg.message_id,
                       "References": f"{msg.references} {msg.message_id}".strip()}
        outgoing = OutgoingEmail(to=to, cc=cc, subject=reply_subject(msg.subject),
                                 html=quoted_reply_document(fragment, msg, original["html"]),
                                 attachments=list(attachments), headers=headers)
        with self.sender_factory() as sender:
            sender.send(outgoing)
        try:
            self.set_read(msg, True)
        except Exception:
            pass
        return {"to": to, "cc": cc}


# ---------------------------------------------------------------- practice mailbox
SAMPLE_EMAILS = [
    ("Sarah Khan", "sarah.khan@example.com", "Honeymoon in the Maldives - March",
     "Hi Travel Essence team,\n\nMy fiancé and I are getting married in February and would love a 7-night "
     "honeymoon in an overwater villa in March. Our budget is around USD 8,000 for two. Could you send us "
     "a few options with seaplane transfers?\n\nThank you!\nSarah", 35),
    ("James Miller", "j.miller@example.org", "Family trip in December - 2 adults, 2 kids",
     "Hello,\n\nWe are looking at a family resort for 22-29 December with a kids club and a good house reef "
     "for snorkelling. Kids are 6 and 9. Is there still availability?\n\nBest regards,\nJames Miller", 160),
    ("Resort Partnerships", "partners@example-resort.com", "Updated 2027 contract rates attached",
     "Dear partner,\n\nPlease find attached our updated 2027 contracted rates and the new early-bird offer "
     "(book 90 days ahead, 25% off). Let us know if you have any questions.\n\nKind regards,\nPartnerships", 1440),
]


class SimulatedSource(InboxSource):
    """Simulation mode's practice mailbox - sample customer emails, replies go nowhere."""

    kind = "simulate"
    _lock = threading.Lock()
    _messages: dict[str, InboxMessage] = {}
    _counter = 0

    def __init__(self):
        super().__init__("simulate")
        self.label = "Practice mailbox (Simulation mode)"
        with self._lock:
            if not SimulatedSource._messages:
                for name, address, subject, body, minutes_ago in reversed(SAMPLE_EMAILS):
                    self._add(name, address, subject, body, datetime.now() - timedelta(minutes=minutes_ago))

    @classmethod
    def _add(cls, name, address, subject, body, when=None) -> InboxMessage:
        cls._counter += 1
        key = f"simulate:{cls._counter}"
        msg = InboxMessage(key=key, source=cls.kind, account="Practice mailbox", from_name=name,
                           from_email=address, subject=subject, received=_iso(when or datetime.now()),
                           preview=_clean_preview(body), to=["sales.marketing@travelessence.mv"],
                           message_id=f"<sim-{cls._counter}@example.com>")
        msg._body = body   # type: ignore[attr-defined]
        cls._messages[key] = msg
        return msg

    @classmethod
    def deliver(cls, name: str, address: str, subject: str, body: str) -> InboxMessage:
        """Drop a new email into the practice mailbox (tests and demos)."""
        with cls._lock:
            return cls._add(name, address, subject, body)

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._messages = {}
            cls._counter = 0

    def fetch(self, limit, known):
        with self._lock:
            rows = sorted(self._messages.values(), key=lambda m: m.received, reverse=True)[:limit]
            return [InboxMessage.from_dict(m.to_dict()) for m in rows]

    def body(self, msg):
        with self._lock:
            stored = self._messages.get(msg.key)
        text = getattr(stored, "_body", msg.preview) if stored else msg.preview
        return {"html": f"<pre style=\"white-space:pre-wrap; font-family:inherit\">{html_lib.escape(text)}</pre>",
                "text": text, "attachments": []}

    def set_read(self, msg, read):
        with self._lock:
            if msg.key in self._messages:
                self._messages[msg.key].unread = not read

    def reply(self, msg, fragment, attachments, reply_all):
        check_attachments(attachments)
        to, cc = reply_recipients(msg, reply_all, {"sales.marketing@travelessence.mv"})
        self.set_read(msg, True)
        return {"to": to, "cc": cc}


# ====================================================================== which mailboxes
def imap_password_key(account: dict) -> str:
    return f"imap:{(account.get('username') or '').strip()}@{(account.get('host') or '').strip()}"


def watched(settings: dict) -> dict:
    """Which mailboxes are watched, with the automatic defaults resolved."""
    backend = settings.get("backend")
    outlook = settings.get("inbox_outlook")
    if outlook is None:
        outlook = backend == "outlook" and outlook_available()[0]
    graph = settings.get("inbox_graph")
    if graph is None:
        graph = backend == "graph" or settings.get("outlook_source") == "graph"
    imap = [a for a in settings.get("inbox_imap_accounts") or [] if isinstance(a, dict) and a.get("host")]
    simulate = backend == "simulate" and not (outlook or graph or imap)
    return {"outlook": bool(outlook), "graph": bool(graph) and bool(settings.get("ms_account")),
            "graph_wanted": bool(graph), "imap": imap, "simulate": simulate}


def own_addresses(settings: dict) -> set[str]:
    """Every address that is Travel Essence itself (never copied back in on Reply all)."""
    found = {settings.get(k) for k in ("smtp_from_email", "smtp_username", "ms_account", "outlook_account",
                                       "test_email")}
    found.add((settings.get("signature") or {}).get("email"))
    found |= {a.get("username") for a in settings.get("inbox_imap_accounts") or [] if isinstance(a, dict)}
    return {a.strip().lower() for a in found if isinstance(a, str) and "@" in a}


def build_sources(settings: dict, password_for: Callable[[str], str],
                  sender_factory: Callable[[], BaseSender] | None = None) -> list[InboxSource]:
    if not settings.get("inbox_enabled", True):
        return []
    w = watched(settings)
    own = own_addresses(settings)
    sources: list[InboxSource] = []
    if w["outlook"]:
        sources.append(OutlookSource())
    if w["graph"]:
        from .graph import client_from_settings

        sources.append(GraphSource(client_from_settings(settings), settings.get("ms_account", "")))
    for account in w["imap"]:
        sources.append(ImapSource(account, password_for(imap_password_key(account)), sender_factory, own=own))
    if w["simulate"]:
        sources.append(SimulatedSource())
    return sources


# ====================================================================== the inbox
class Inbox:
    """Every watched mailbox merged into one list, numbered and remembered in inbox.json."""

    def __init__(self, sources: Callable[[], list[InboxSource]]):
        self._sources = sources
        self._lock = threading.RLock()
        self._refreshing = threading.Lock()
        data = storage.read_json(storage.data_dir() / "inbox.json", {})
        data = data if isinstance(data, dict) else {}
        self.next_seq = int(data.get("next_seq", 1) or 1)
        self.seen: dict[str, int] = dict(data.get("seen") or {})
        self.armed: set[str] = set(data.get("armed") or [])
        self.rows: dict[str, InboxMessage] = {}
        for row in data.get("messages") or []:
            try:
                msg = InboxMessage.from_dict(row)
                self.rows[msg.key] = msg
            except TypeError:
                continue
        self.last_checked: str = data.get("last_checked") or ""
        self.errors: dict[str, str] = {}
        self.source_labels: dict[str, str] = dict(data.get("labels") or {})

    # -------------------------------------------------------------- persistence
    def _save(self) -> None:
        seen = dict(sorted(self.seen.items(), key=lambda kv: kv[1])[-MAX_SEEN:])
        self.seen = seen
        storage.write_json(storage.data_dir() / "inbox.json", {
            "next_seq": self.next_seq, "seen": seen, "armed": sorted(self.armed),
            "last_checked": self.last_checked, "labels": self.source_labels,
            "messages": [m.to_dict() for m in self.messages()],
        })

    # -------------------------------------------------------------- reading
    def messages(self) -> list[InboxMessage]:
        with self._lock:
            return sorted(self.rows.values(), key=lambda m: (m.received, m.seq), reverse=True)

    def find(self, seq_or_key) -> InboxMessage | None:
        with self._lock:
            if isinstance(seq_or_key, str) and not seq_or_key.isdigit():
                return self.rows.get(seq_or_key)
            seq = int(seq_or_key)
            return next((m for m in self.rows.values() if m.seq == seq), None)

    @property
    def latest_seq(self) -> int:
        return self.next_seq - 1

    def unread_count(self) -> int:
        with self._lock:
            return sum(1 for m in self.rows.values() if m.unread)

    # -------------------------------------------------------------- checking
    def refresh(self, limit: int = FETCH_LIMIT) -> list[InboxMessage]:
        """Check every mailbox. Returns the emails that are new since the last check."""
        with self._refreshing:
            sources = self._sources()
            names = {s.name for s in sources}
            fresh: list[InboxMessage] = []
            errors: dict[str, str] = {}
            with self._lock:
                for gone in [k for k, m in self.rows.items() if self._source_name(m) not in names]:
                    del self.rows[gone]   # a mailbox that is no longer watched
            for source in sources:
                with self._lock:
                    known = {k: m.to_dict() for k, m in self.rows.items() if self._source_name(m) == source.name}
                try:
                    fetched = source.fetch(limit, known)
                except Exception as exc:
                    errors[source.name] = f"{source.label}: {exc}"
                    log.warning("Inbox check failed for %s: %s", source.name, exc)
                    continue
                with self._lock:
                    self.source_labels[source.name] = source.label
                    fresh += self._merge(source.name, fetched)
            with self._lock:
                self.errors = errors
                self.last_checked = _iso(datetime.now())
                self._save()
            return fresh

    @staticmethod
    def _source_name(msg: InboxMessage) -> str:
        if msg.source == "imap":
            return msg.key.rsplit(":", 2)[0]
        return msg.source

    def _merge(self, source_name: str, fetched: list[InboxMessage]) -> list[InboxMessage]:
        first_look = source_name not in self.armed
        for key in [k for k, m in self.rows.items() if self._source_name(m) == source_name]:
            del self.rows[key]
        fresh = []
        for msg in sorted(fetched, key=lambda m: m.received):    # oldest first, so numbers follow time
            if msg.key in self.seen:
                msg.seq = self.seen[msg.key]
            else:
                msg.seq = self.seen[msg.key] = self.next_seq
                self.next_seq += 1
                if not first_look:
                    fresh.append(msg)
            self.rows[msg.key] = msg
        self.armed.add(source_name)
        return fresh

    # -------------------------------------------------------------- acting
    def _source_for(self, msg: InboxMessage) -> InboxSource:
        name = self._source_name(msg)
        for source in self._sources():
            if source.name == name:
                return source
        raise SendError(f"The mailbox for this email ({msg.account}) is no longer connected.")

    def body(self, msg: InboxMessage) -> dict:
        return self._source_for(msg).body(msg)

    def set_read(self, msg: InboxMessage, read: bool = True) -> None:
        self._source_for(msg).set_read(msg, read)
        with self._lock:
            if msg.key in self.rows:
                self.rows[msg.key].unread = not read
            self._save()

    def reply(self, msg: InboxMessage, editor_html: str, signature: str = "", attachments: list[str] | None = None,
              reply_all: bool = False) -> dict:
        result = self._source_for(msg).reply(msg, reply_fragment(editor_html, signature), list(attachments or []),
                                             reply_all)
        with self._lock:
            if msg.key in self.rows:
                self.rows[msg.key].unread = False
            self._save()
        return {"to": result.get("to", []), "cc": result.get("cc", []), "subject": reply_subject(msg.subject)}

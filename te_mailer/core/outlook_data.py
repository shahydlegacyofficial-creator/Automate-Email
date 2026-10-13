"""Read data out of the Outlook (classic) desktop app via COM.

Collects customer addresses and the emails Travel Essence has sent from Outlook
(Sent Items), received (Inbox) or stored (Contacts), and can load a previously
sent message back into the composer as a reusable template.

All functions are meant to run inside a worker thread; they initialise COM for
the calling thread and only return plain Python data.
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from .senders import PR_ATTACH_CONTENT_ID, PR_SMTP_ADDRESS, SendError, outlook_available
from .storage import sub_dir

PR_SENT_REPRESENTING_SMTP = "http://schemas.microsoft.com/mapi/proptag/0x5D01001F"
OL_FOLDER_SENT = 5
OL_FOLDER_INBOX = 6
OL_FOLDER_CONTACTS = 10
OL_MAIL_CLASS = 43
OL_CONTACT_CLASS = 40

FOLDER_CHOICES = [
    ("sent", "Sent Items (emails Travel Essence sent)"),
    ("inbox", "Inbox (customers who emailed us)"),
    ("both", "Sent Items + Inbox"),
    ("contacts", "Outlook Contacts"),
    ("custom", "Choose a folder…"),
]

ALLOWED_TEMPLATE_ATTACHMENTS = (".jpg", ".jpeg", ".png", ".pdf")


@dataclass
class ContactRow:
    email: str
    name: str = ""
    company: str = ""
    phone: str = ""
    interactions: int = 0
    last_contact: datetime | None = None
    last_subject: str = ""


@dataclass
class MessageRow:
    date: datetime | None
    folder: str
    sender: str
    recipients: str
    subject: str
    attachments: int
    entry_id: str
    store_id: str


@dataclass
class CollectOptions:
    store: str = ""                 # store display name; "" = all accounts
    folder: str = "sent"            # see FOLDER_CHOICES
    custom_entry_id: str = ""
    custom_store_id: str = ""
    date_from: datetime | None = None
    date_to: datetime | None = None
    subject_contains: str = ""
    exclude: list[str] = field(default_factory=list)   # addresses or @domains to skip
    max_items: int = 5000


@dataclass
class CollectResult:
    contacts: list[ContactRow] = field(default_factory=list)
    messages: list[MessageRow] = field(default_factory=list)
    scanned: int = 0
    own_addresses: list[str] = field(default_factory=list)


@contextmanager
def outlook_session():
    ok, reason = outlook_available()
    if not ok:
        raise SendError(reason)
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        try:
            app = win32com.client.Dispatch("Outlook.Application")
            namespace = app.GetNamespace("MAPI")
        except Exception as exc:
            raise SendError("Could not connect to Microsoft Outlook. Make sure classic Outlook "
                            f"for Windows is installed and signed in. ({exc})") from exc
        yield app, namespace
    finally:
        pythoncom.CoUninitialize()


def _to_datetime(value) -> datetime | None:
    try:
        return datetime(value.year, value.month, value.day, value.hour, value.minute, value.second)
    except Exception:
        return None


def _safe(obj, attr, default=""):
    try:
        value = getattr(obj, attr)
        return default if value is None else value
    except Exception:
        return default


def recipient_smtp(recipient) -> str:
    address = _safe(recipient, "Address")
    if "@" in address and not address.startswith("/"):
        return address.lower()
    try:
        value = recipient.PropertyAccessor.GetProperty(PR_SMTP_ADDRESS)
        if value:
            return str(value).lower()
    except Exception:
        pass
    try:
        user = recipient.AddressEntry.GetExchangeUser()
        if user is not None and user.PrimarySmtpAddress:
            return user.PrimarySmtpAddress.lower()
    except Exception:
        pass
    return ""


def sender_smtp(item) -> str:
    if _safe(item, "SenderEmailType") == "EX":
        try:
            user = item.Sender.GetExchangeUser()
            if user is not None and user.PrimarySmtpAddress:
                return user.PrimarySmtpAddress.lower()
        except Exception:
            pass
        try:
            value = item.PropertyAccessor.GetProperty(PR_SENT_REPRESENTING_SMTP)
            if value:
                return str(value).lower()
        except Exception:
            pass
    address = _safe(item, "SenderEmailAddress")
    return address.lower() if "@" in address else ""


def list_accounts() -> list[dict]:
    """Return Outlook accounts and data stores (mailboxes)."""
    with outlook_session() as (_app, ns):
        accounts = []
        for acc in ns.Accounts:
            accounts.append({
                "name": _safe(acc, "DisplayName"),
                "smtp": (_safe(acc, "SmtpAddress") or "").lower(),
            })
        stores = []
        for store in ns.Stores:
            stores.append(_safe(store, "DisplayName"))
        return {"accounts": accounts, "stores": stores}


def pick_folder() -> tuple[str, str, str] | None:
    """Show Outlook's own folder picker. Returns (entry_id, store_id, folder_path)."""
    with outlook_session() as (_app, ns):
        folder = ns.PickFolder()
        if folder is None:
            return None
        return folder.EntryID, folder.StoreID, _safe(folder, "FolderPath")


def _is_excluded(email: str, exclude: list[str]) -> bool:
    email = email.lower()
    domain = email.rsplit("@", 1)[-1]
    for entry in exclude:
        entry = entry.strip().lower()
        if entry and (entry == email or entry.lstrip("@") == domain):
            return True
    return False


def _folders_for(ns, options: CollectOptions) -> list[tuple[object, str]]:
    if options.folder == "custom":
        folder = ns.GetFolderFromID(options.custom_entry_id, options.custom_store_id)
        return [(folder, "contacts" if _safe(folder, "DefaultItemType", 0) == 2 else "mail")]

    wanted = {
        "sent": [OL_FOLDER_SENT],
        "inbox": [OL_FOLDER_INBOX],
        "both": [OL_FOLDER_SENT, OL_FOLDER_INBOX],
        "contacts": [OL_FOLDER_CONTACTS],
    }[options.folder]

    folders = []
    for store in ns.Stores:
        name = _safe(store, "DisplayName")
        if options.store and name != options.store:
            continue
        for kind in wanted:
            try:
                folder = store.GetDefaultFolder(kind)
            except Exception:
                continue  # e.g. public folders / archives without that folder
            folders.append((folder, "contacts" if kind == OL_FOLDER_CONTACTS else "mail"))
    return folders


def collect(options: CollectOptions,
            progress: Callable[[int, int, str], None] | None = None,
            cancelled: Callable[[], bool] | None = None) -> CollectResult:
    progress = progress or (lambda *a: None)
    cancelled = cancelled or (lambda: False)
    result = CollectResult()
    contacts: dict[str, ContactRow] = {}
    subject_filter = options.subject_contains.strip().lower()

    with outlook_session() as (_app, ns):
        own = {(_safe(a, "SmtpAddress") or "").lower() for a in ns.Accounts}
        own.discard("")
        result.own_addresses = sorted(own)
        exclude = [e.lower() for e in options.exclude] + sorted(own)

        def touch(email: str, name: str, when: datetime | None, subject: str) -> None:
            if not email or "@" not in email or _is_excluded(email, exclude):
                return
            row = contacts.get(email)
            if row is None:
                row = contacts[email] = ContactRow(email=email)
            clean_name = name.strip().strip("'\"")
            if clean_name and "@" not in clean_name and not row.name:
                row.name = clean_name
            row.interactions += 1
            if when and (row.last_contact is None or when > row.last_contact):
                row.last_contact = when
                row.last_subject = subject

        folders = _folders_for(ns, options)
        for folder, kind in folders:
            if cancelled():
                break
            folder_name = _safe(folder, "Name")
            items = folder.Items
            total = int(_safe(items, "Count", 0) or 0)

            if kind == "contacts":
                item = items.GetFirst()
                index = 0
                while item is not None and not cancelled():
                    index += 1
                    result.scanned += 1
                    if _safe(item, "Class", 0) == OL_CONTACT_CLASS:
                        for slot in ("Email1Address", "Email2Address", "Email3Address"):
                            address = (_safe(item, slot) or "").lower()
                            if "@" not in address or _is_excluded(address, exclude):
                                continue
                            row = contacts.setdefault(address, ContactRow(email=address))
                            row.name = row.name or _safe(item, "FullName")
                            row.company = row.company or _safe(item, "CompanyName")
                            row.phone = row.phone or _safe(item, "MobileTelephoneNumber") or \
                                _safe(item, "BusinessTelephoneNumber")
                            row.interactions += 1
                    if index % 25 == 0:
                        progress(index, total, f"Reading {folder_name}… {index}/{total}")
                    item = items.GetNext()
                continue

            is_sent = _is_sent_folder(folder)
            date_field = "[SentOn]" if is_sent else "[ReceivedTime]"
            try:
                items.Sort(date_field, True)
            except Exception:
                pass
            item = items.GetFirst()
            index = 0
            while item is not None and not cancelled() and len(result.messages) < options.max_items:
                index += 1
                result.scanned += 1
                if index % 20 == 0:
                    progress(index, total, f"Reading {folder_name}… {index}/{total}")
                if _safe(item, "Class", 0) != OL_MAIL_CLASS:
                    item = items.GetNext()
                    continue
                when = _to_datetime(_safe(item, "SentOn" if is_sent else "ReceivedTime", None))
                if when and options.date_to and when > options.date_to:
                    item = items.GetNext()
                    continue
                if when and options.date_from and when < options.date_from:
                    break  # sorted newest first - everything after is older
                subject = _safe(item, "Subject")
                if subject_filter and subject_filter not in subject.lower():
                    item = items.GetNext()
                    continue

                to_list: list[str] = []
                try:
                    for rcp in item.Recipients:
                        address = recipient_smtp(rcp)
                        if address:
                            to_list.append(address)
                            if is_sent:
                                touch(address, _safe(rcp, "Name"), when, subject)
                except Exception:
                    pass
                sender = sender_smtp(item)
                if not is_sent:
                    touch(sender, _safe(item, "SenderName"), when, subject)

                try:
                    attachment_count = int(item.Attachments.Count)
                except Exception:
                    attachment_count = 0
                result.messages.append(MessageRow(
                    date=when, folder=folder_name, sender=sender,
                    recipients="; ".join(to_list), subject=subject,
                    attachments=attachment_count,
                    entry_id=_safe(item, "EntryID"), store_id=_safe(folder, "StoreID"),
                ))
                item = items.GetNext()

    result.contacts = sorted(contacts.values(),
                             key=lambda c: (c.last_contact or datetime.min), reverse=True)
    result.messages.sort(key=lambda m: m.date or datetime.min, reverse=True)
    progress(1, 1, "Done")
    return result


def _is_sent_folder(folder) -> bool:
    if "sent" in (_safe(folder, "Name") or "").lower():
        return True
    try:
        return folder.Store.GetDefaultFolder(OL_FOLDER_SENT).EntryID == folder.EntryID
    except Exception:
        return False


def load_message(entry_id: str, store_id: str) -> dict:
    """Fetch a stored email as a template: subject, HTML body and attachments.

    Inline images are saved locally and re-pointed at the files so they show in the
    editor and are embedded again when sending.
    """
    with outlook_session() as (_app, ns):
        item = ns.GetItemFromID(entry_id, store_id)
        subject = _safe(item, "Subject")
        body = _safe(item, "HTMLBody") or ""
        target = sub_dir("outlook_templates") / datetime.now().strftime("%Y%m%d-%H%M%S")
        target.mkdir(parents=True, exist_ok=True)

        attachments: list[str] = []
        skipped: list[str] = []
        try:
            count = int(item.Attachments.Count)
        except Exception:
            count = 0
        for i in range(1, count + 1):
            att = item.Attachments.Item(i)
            filename = re.sub(r'[\\/:*?"<>|]', "_", _safe(att, "FileName") or f"attachment{i}")
            try:
                cid = att.PropertyAccessor.GetProperty(PR_ATTACH_CONTENT_ID) or ""
            except Exception:
                cid = ""
            path = target / filename
            if cid:
                try:
                    att.SaveAsFile(str(path))
                except Exception:
                    continue
                url = "file:///" + str(path).replace("\\", "/")
                body = re.sub(rf"cid:{re.escape(cid)}", url, body, flags=re.IGNORECASE)
                continue
            if os.path.splitext(filename)[1].lower() not in ALLOWED_TEMPLATE_ATTACHMENTS:
                skipped.append(filename)
                continue
            try:
                att.SaveAsFile(str(path))
                attachments.append(str(path))
            except Exception:
                skipped.append(filename)

        return {"subject": subject, "html": body, "attachments": attachments, "skipped": skipped}

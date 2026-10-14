"""Microsoft 365 / new Outlook / Outlook.com access through Microsoft Graph.

The *new* Outlook for Windows (and Outlook on the web) can't be automated like classic
Outlook, so the app talks to the mailbox directly instead. Sign-in uses the OAuth device-code
flow: the app shows a short code, the user enters it at microsoft.com/devicelogin.

Everything here is plain Python (urllib) so it runs in a worker thread and is unit-tested
against a local fake server.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Callable

from .htmlutil import extract_inline_images
from .outlook_data import (
    ALLOWED_TEMPLATE_ATTACHMENTS, CollectOptions, CollectResult, ContactRow, MessageRow,
)
from .senders import BaseSender, OutgoingEmail, SendError, check_attachments
from .storage import data_dir, sub_dir

SCOPES = "offline_access User.Read Mail.ReadWrite Mail.Send Contacts.Read"
SIMPLE_ATTACHMENT_LIMIT = 3 * 1024 * 1024
UPLOAD_CHUNK = 320 * 1024 * 10


class TokenStore:
    """Sign-in tokens on disk, encrypted for the current Windows user with DPAPI."""

    def __init__(self, path=None):
        self.path = path or (data_dir() / "ms_tokens.bin")

    @staticmethod
    def _protect(data: bytes) -> bytes:
        if sys.platform.startswith("win"):
            import win32crypt

            return win32crypt.CryptProtectData(data, "TravelEssence", None, None, None, 0)
        return base64.b64encode(data)

    @staticmethod
    def _unprotect(data: bytes) -> bytes:
        if sys.platform.startswith("win"):
            import win32crypt

            return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]
        return base64.b64decode(data)

    def load(self) -> dict | None:
        try:
            with open(self.path, "rb") as fh:
                return json.loads(self._unprotect(fh.read()).decode("utf-8"))
        except (OSError, ValueError, Exception):
            return None

    def save(self, value: dict | None) -> None:
        if value is None:
            try:
                os.remove(self.path)
            except OSError:
                pass
            return
        with open(self.path, "wb") as fh:
            fh.write(self._protect(json.dumps(value).encode("utf-8")))


def _encode(value: str) -> str:
    return urllib.parse.quote(value, safe="")


class GraphClient:
    def __init__(self, client_id: str, tenant: str = "common", tokens: TokenStore | None = None,
                 graph_base: str = "https://graph.microsoft.com/v1.0",
                 login_base: str = "https://login.microsoftonline.com"):
        self.client_id = (client_id or "").strip()
        self.tenant = (tenant or "common").strip() or "common"
        self.tokens = tokens or TokenStore()
        self.graph_base = graph_base
        self.authority = f"{login_base}/{self.tenant}/oauth2/v2.0"

    # ------------------------------------------------------------ HTTP
    @staticmethod
    def _http(method: str, url: str, body: bytes | None = None, headers: dict | None = None,
              timeout: int = 120) -> tuple[int, bytes, dict]:
        req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read() or b"", dict(exc.headers or {})
        except (urllib.error.URLError, OSError) as exc:
            raise SendError(f"Network error: {getattr(exc, 'reason', exc)}") from exc

    def _form(self, url: str, fields: dict) -> tuple[int, dict]:
        code, body, _ = self._http("POST", url, urllib.parse.urlencode(fields).encode(),
                                   {"Content-Type": "application/x-www-form-urlencoded"})
        try:
            return code, json.loads(body or b"{}")
        except ValueError:
            return code, {"error_description": body[:300].decode("utf-8", "replace")}

    @staticmethod
    def _auth_error(data: dict, code: int) -> str:
        desc = (data.get("error_description") or "").splitlines()[0] if data.get("error_description") else ""
        if "AADSTS7000218" in desc:
            return ("Public client flows are not enabled for this app registration "
                    "(Authentication → Allow public client flows = Yes).")
        if "AADSTS700016" in desc:
            return "Application (client) ID not found. Check it in Settings."
        if data.get("error") == "access_denied":
            return "Sign-in was declined."
        return desc or f"Sign-in failed (HTTP {code})"

    # ------------------------------------------------------------ auth
    def start_device_login(self) -> dict:
        if not self.client_id:
            raise SendError("Enter the Application (client) ID in Settings first.")
        code, data = self._form(f"{self.authority}/devicecode", {"client_id": self.client_id, "scope": SCOPES})
        if code != 200:
            raise SendError(self._auth_error(data, code))
        data.setdefault("verification_uri", "https://microsoft.com/devicelogin")
        return data

    def complete_device_login(self, device: dict, cancelled: Callable[[], bool] = lambda: False) -> str:
        interval = max(2, int(device.get("interval", 5)))
        deadline = time.time() + int(device.get("expires_in", 900))
        while time.time() < deadline:
            if cancelled():
                raise SendError("Sign-in cancelled")
            time.sleep(interval)
            code, data = self._form(f"{self.authority}/token", {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": self.client_id, "device_code": device["device_code"],
            })
            if code == 200:
                self._store(data)
                return self.me()
            error = data.get("error")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            raise SendError(self._auth_error(data, code))
        raise SendError("The sign-in code expired. Please try again.")

    def _store(self, data: dict, previous_refresh: str = "") -> None:
        self.tokens.save({
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token") or previous_refresh,
            "expires_at": time.time() + int(data.get("expires_in", 3600)) - 120,
        })

    @property
    def is_signed_in(self) -> bool:
        saved = self.tokens.load()
        return bool(saved and saved.get("refresh_token"))

    def sign_out(self) -> None:
        self.tokens.save(None)

    def access_token(self) -> str:
        saved = self.tokens.load()
        if not saved:
            raise SendError("Not signed in to Microsoft 365 / Outlook. Sign in from Settings.")
        if time.time() < float(saved.get("expires_at", 0)):
            return saved["access_token"]
        refresh = saved.get("refresh_token")
        if not refresh:
            raise SendError("Your Microsoft sign-in has expired. Sign in again from Settings.")
        code, data = self._form(f"{self.authority}/token", {
            "grant_type": "refresh_token", "client_id": self.client_id,
            "refresh_token": refresh, "scope": SCOPES,
        })
        if code != 200:
            raise SendError(f"Your Microsoft sign-in has expired ({self._auth_error(data, code)}). "
                            "Sign in again from Settings.")
        self._store(data, refresh)
        return data["access_token"]

    # ------------------------------------------------------------ REST
    def request(self, method: str, path_or_url: str, payload: dict | None = None) -> dict:
        url = path_or_url if path_or_url.startswith("http") else self.graph_base + path_or_url
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        for attempt in range(3):
            headers = {"Authorization": f"Bearer {self.access_token()}", "Accept": "application/json"}
            if body is not None:
                headers["Content-Type"] = "application/json"
            code, raw, resp_headers = self._http(method, url, body, headers)
            if code in (429, 503, 504) and attempt < 2:
                retry_after = resp_headers.get("Retry-After") or resp_headers.get("retry-after")
                time.sleep(min(60, max(1, int(retry_after) if str(retry_after).isdigit() else 5 * (attempt + 1))))
                continue
            if not 200 <= code < 300:
                raise SendError(self._graph_error(code, raw))
            return json.loads(raw) if raw.strip() else {}
        raise SendError("Microsoft Graph is busy - try again later.")

    @staticmethod
    def _graph_error(code: int, raw: bytes) -> str:
        try:
            message = json.loads(raw)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = ""
        if code == 401:
            return f"Microsoft rejected the sign-in ({message}). Sign in again from Settings."
        if code == 403:
            return f"Access denied - the account may not have a mailbox or permission ({message})."
        return message or f"Microsoft Graph error HTTP {code}"

    def me(self) -> str:
        me = self.request("GET", "/me?$select=displayName,mail,userPrincipalName")
        return (me.get("mail") or me.get("userPrincipalName") or "").lower()

    # ------------------------------------------------------------ sending
    @staticmethod
    def _recipients(addresses: list[str]) -> list[dict]:
        return [{"emailAddress": {"address": a}} for a in addresses]

    def send(self, email: OutgoingEmail) -> None:
        check_attachments(email.attachments)
        body_html, inline = extract_inline_images(email.html)
        message: dict = {
            "subject": email.subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": self._recipients(email.to),
        }
        if email.cc:
            message["ccRecipients"] = self._recipients(email.cc)
        if email.bcc:
            message["bccRecipients"] = self._recipients(email.bcc)

        small = []
        for cid, path in inline:
            with open(path, "rb") as fh:
                small.append({"@odata.type": "#microsoft.graph.fileAttachment", "name": cid,
                              "contentType": _mime(path), "contentBytes": base64.b64encode(fh.read()).decode(),
                              "isInline": True, "contentId": cid})
        large = [p for p in email.attachments if os.path.getsize(p) > SIMPLE_ATTACHMENT_LIMIT]
        for path in email.attachments:
            if path in large:
                continue
            with open(path, "rb") as fh:
                small.append({"@odata.type": "#microsoft.graph.fileAttachment", "name": os.path.basename(path),
                              "contentType": _mime(path), "contentBytes": base64.b64encode(fh.read()).decode()})
        if small:
            message["attachments"] = small

        if not large:
            self.request("POST", "/me/sendMail", {"message": message, "saveToSentItems": True})
            return
        # Big files: create a draft, stream each file through an upload session, then send.
        draft = self.request("POST", "/me/messages", message)
        msg_id = _encode(draft["id"])
        try:
            for path in large:
                self._upload(msg_id, path)
            self.request("POST", f"/me/messages/{msg_id}/send")
        except Exception:
            try:
                self.request("DELETE", f"/me/messages/{msg_id}")
            except SendError:
                pass
            raise

    def _upload(self, msg_id: str, path: str) -> None:
        size = os.path.getsize(path)
        session = self.request("POST", f"/me/messages/{msg_id}/attachments/createUploadSession", {
            "AttachmentItem": {"attachmentType": "file", "name": os.path.basename(path),
                               "size": size, "contentType": _mime(path)}})
        offset = 0
        with open(path, "rb") as fh:
            while offset < size:
                chunk = fh.read(UPLOAD_CHUNK)
                if not chunk:
                    break
                code, raw, _ = self._http("PUT", session["uploadUrl"], chunk, {
                    "Content-Type": "application/octet-stream",
                    "Content-Range": f"bytes {offset}-{offset + len(chunk) - 1}/{size}"})
                if not 200 <= code < 300:
                    raise SendError(f"Uploading {os.path.basename(path)} failed: {self._graph_error(code, raw)}")
                offset += len(chunk)


def _mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
            ".pdf": "application/pdf"}.get(ext, "application/octet-stream")


class GraphSender(BaseSender):
    label = "Microsoft 365 / new Outlook"

    def __init__(self, client: GraphClient):
        self.client = client

    def open(self) -> None:
        self.client.access_token()   # fail fast if the sign-in has expired

    def send(self, email: OutgoingEmail) -> None:
        self.client.send(email)


def client_from_settings(settings: dict) -> GraphClient:
    return GraphClient(settings.get("ms_client_id", ""), settings.get("ms_tenant", "common"))


# ====================================================================== mailbox data
def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone().replace(tzinfo=None)
    except ValueError:
        return None


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect(client: GraphClient, options: CollectOptions,
            progress: Callable[[int, int, str], None] | None = None,
            cancelled: Callable[[], bool] | None = None) -> CollectResult:
    """Customers and messages from Sent Items / Inbox / Contacts of the signed-in mailbox."""
    progress = progress or (lambda *a: None)
    cancelled = cancelled or (lambda: False)
    result = CollectResult()
    own = client.me()
    result.own_addresses = [own] if own else []
    exclude = [e.lower() for e in options.exclude] + result.own_addresses
    contacts: dict[str, ContactRow] = {}
    subject_filter = options.subject_contains.strip().lower()

    def excluded(email: str) -> bool:
        domain = email.rsplit("@", 1)[-1]
        return any(e and (e == email or e.lstrip("@") == domain) for e in exclude)

    def touch(email: str, name: str, when: datetime | None, subject: str, company: str = "", phone: str = ""):
        email = (email or "").strip().lower()
        if "@" not in email or excluded(email):
            return
        row = contacts.setdefault(email, ContactRow(email=email))
        name = (name or "").strip().strip("'\"")
        if name and "@" not in name and not row.name:
            row.name = name
        row.company = row.company or company
        row.phone = row.phone or phone
        row.interactions += 1
        if when and (row.last_contact is None or when > row.last_contact):
            row.last_contact, row.last_subject = when, subject

    if options.folder == "contacts":
        url = "/me/contacts?$select=displayName,emailAddresses,companyName,mobilePhone,businessPhones&$top=100"
        while url and not cancelled():
            page = client.request("GET", url)
            for c in page.get("value", []):
                result.scanned += 1
                phone = c.get("mobilePhone") or next(iter(c.get("businessPhones") or []), "")
                for addr in c.get("emailAddresses") or []:
                    touch(addr.get("address", ""), c.get("displayName", ""), None, "",
                          c.get("companyName") or "", phone or "")
            progress(result.scanned, result.scanned, f"Reading contacts… {result.scanned}")
            url = page.get("@odata.nextLink")
    else:
        folders = {"inbox": ["inbox"], "both": ["sentitems", "inbox"]}.get(options.folder, ["sentitems"])
        for folder in folders:
            sent = folder == "sentitems"
            field = "sentDateTime" if sent else "receivedDateTime"
            clauses = [f"{field} ge {_iso_utc(options.date_from or datetime(2000, 1, 1))}"]
            if options.date_to:
                clauses.append(f"{field} le {_iso_utc(options.date_to)}")
            url = ("/me/mailFolders/" + folder + "/messages?$select=subject,sentDateTime,receivedDateTime,from,"
                   "toRecipients,ccRecipients,bccRecipients,hasAttachments"
                   "&$orderby=" + _encode(f"{field} desc") + "&$top=100&$filter=" + _encode(" and ".join(clauses)))
            label = "Sent Items" if sent else "Inbox"
            while url and not cancelled() and len(result.messages) < options.max_items:
                page = client.request("GET", url)
                for m in page.get("value", []):
                    if len(result.messages) >= options.max_items:
                        break
                    result.scanned += 1
                    subject = m.get("subject") or ""
                    if subject_filter and subject_filter not in subject.lower():
                        continue
                    when = _parse_date(m.get(field))
                    to_list = []
                    for key in ("toRecipients", "ccRecipients", "bccRecipients"):
                        for r in m.get(key) or []:
                            ea = r.get("emailAddress") or {}
                            address = (ea.get("address") or "").lower()
                            if address:
                                to_list.append(address)
                                if sent:
                                    touch(address, ea.get("name", ""), when, subject)
                    sender = ((m.get("from") or {}).get("emailAddress") or {})
                    if not sent:
                        touch(sender.get("address", ""), sender.get("name", ""), when, subject)
                    result.messages.append(MessageRow(
                        date=when, folder=label, sender=(sender.get("address") or "").lower(),
                        recipients="; ".join(to_list), subject=subject,
                        attachments=1 if m.get("hasAttachments") else 0, entry_id=m["id"], store_id="graph"))
                progress(len(result.messages), options.max_items, f"Reading {label}… {len(result.messages)} emails")
                url = page.get("@odata.nextLink")

    result.contacts = sorted(contacts.values(), key=lambda c: c.last_contact or datetime.min, reverse=True)
    result.messages.sort(key=lambda m: m.date or datetime.min, reverse=True)
    progress(1, 1, "Done")
    return result


def load_message(client: GraphClient, message_id: str) -> dict:
    """A sent email as a reusable template (inline pictures saved and re-linked locally)."""
    path = "/me/messages/" + _encode(message_id)
    msg = client.request("GET", path + "?$select=subject,body")
    body = (msg.get("body") or {}).get("content") or ""
    if ((msg.get("body") or {}).get("contentType") or "").lower() == "text":
        import html as _html
        body = "<p>" + _html.escape(body).replace("\n", "<br>") + "</p>"
    target = sub_dir("outlook_templates") / datetime.now().strftime("%Y%m%d-%H%M%S")
    target.mkdir(parents=True, exist_ok=True)
    attachments, skipped = [], []
    for att in client.request("GET", path + "/attachments").get("value", []):
        name = re.sub(r'[\\/:*?"<>|]', "_", att.get("name") or "attachment")
        if "contentBytes" not in att:
            skipped.append(name)
            continue
        data = base64.b64decode(att["contentBytes"])
        cid = (att.get("contentId") or "").strip("<>")
        file_path = target / name
        if att.get("isInline") and cid:
            file_path.write_bytes(data)
            body = re.sub(rf"cid:{re.escape(cid)}", "file:///" + str(file_path).replace("\\", "/"),
                          body, flags=re.IGNORECASE)
        elif os.path.splitext(name)[1].lower() in ALLOWED_TEMPLATE_ATTACHMENTS:
            file_path.write_bytes(data)
            attachments.append(str(file_path))
        else:
            skipped.append(name)
    return {"subject": msg.get("subject") or "", "html": body, "attachments": attachments, "skipped": skipped}

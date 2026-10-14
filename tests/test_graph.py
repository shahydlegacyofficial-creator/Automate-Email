"""Microsoft Graph client (new Outlook / Microsoft 365) against a local fake of the Microsoft endpoints."""

import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from te_mailer.core.graph import GraphClient, SIMPLE_ATTACHMENT_LIMIT, collect, load_message
from te_mailer.core.outlook_data import CollectOptions
from te_mailer.core.senders import OutgoingEmail


class MemoryTokens:
    def __init__(self, value=None):
        self.value = value

    def load(self):
        return self.value

    def save(self, value):
        self.value = value


@pytest.fixture
def fake_microsoft():
    requests = []
    polls = {"n": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _respond(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("latin-1") if length else ""
            path = self.path
            requests.append((self.command, path, body))
            base = f"http://127.0.0.1:{self.server.server_port}"
            if path.endswith("/devicecode"):
                code, data = 200, {"device_code": "DEV", "user_code": "ABC-123", "expires_in": 60, "interval": 1,
                                   "verification_uri": "https://microsoft.com/devicelogin"}
            elif path.endswith("/token") and "device_code" in body:
                polls["n"] += 1
                code, data = (400, {"error": "authorization_pending"}) if polls["n"] < 2 else \
                    (200, {"access_token": "AT1", "refresh_token": "RT1", "expires_in": 3600})
            elif path.endswith("/token") and "refresh_token" in body:
                code, data = 200, {"access_token": "AT2", "expires_in": 3600}
            elif path.startswith("/graph/me?"):
                code, data = 200, {"mail": "Sales.Marketing@TravelEssence.mv"}
            elif path == "/graph/me/sendMail":
                code, data = 202, None
            elif path == "/graph/me/messages":
                code, data = 201, {"id": "MSG/1="}
            elif path.endswith("/createUploadSession"):
                code, data = 201, {"uploadUrl": f"{base}/upload/1"}
            elif path.startswith("/upload/") or path.endswith("/send"):
                code, data = 200, {}
            elif path.startswith("/graph/me/mailFolders/sentitems/messages"):
                code, data = 200, {"value": [
                    {"id": "m1", "subject": "Maldives offers", "sentDateTime": "2026-10-01T09:00:00Z",
                     "from": {"emailAddress": {"address": "sales.marketing@travelessence.mv"}},
                     "toRecipients": [{"emailAddress": {"address": "Sarah@Gmail.com", "name": "Sarah Khan"}}],
                     "ccRecipients": [{"emailAddress": {"address": "ops@travelessence.mv", "name": "Ops"}}],
                     "hasAttachments": True}],
                    "@odata.nextLink": f"{base}/graph/page2"}
            elif path == "/graph/page2":
                code, data = 200, {"value": [
                    {"id": "m2", "subject": "Dubai quotation", "sentDateTime": "2026-09-01T09:00:00Z",
                     "from": {"emailAddress": {"address": "sales.marketing@travelessence.mv"}},
                     "toRecipients": [{"emailAddress": {"address": "sarah@gmail.com", "name": "Sarah"}},
                                      {"emailAddress": {"address": "leo@icloud.com", "name": "Leo"}}]}]}
            elif path.startswith("/graph/me/messages/m1?"):
                code, data = 200, {"subject": "Maldives offers",
                                   "body": {"contentType": "html",
                                            "content": '<html><body><p>Hi</p><img src="cid:logo1"></body></html>'}}
            elif path.startswith("/graph/me/messages/m1/attachments"):
                code, data = 200, {"value": [
                    {"name": "logo.png", "contentBytes": "iVBORw0KGgo=", "isInline": True, "contentId": "<logo1>"},
                    {"name": "Brochure.pdf", "contentBytes": "JVBERi0xLjQ=", "isInline": False},
                    {"name": "notes.docx", "contentBytes": "UEs=", "isInline": False}]}
            else:
                code, data = 404, {"error": {"code": "NotFound", "message": f"no route {path}"}}
            payload = json.dumps(data).encode() if data is not None else b""
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do_PUT = do_DELETE = _respond

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    yield base, requests
    server.shutdown()


def make(base, tokens):
    return GraphClient("client-id", "common", tokens, graph_base=f"{base}/graph", login_base=base)


def signed_in():
    return MemoryTokens({"access_token": "AT", "refresh_token": "RT", "expires_at": time.time() + 3600})


def test_device_login_and_send_with_inline_image(fake_microsoft, tmp_path):
    base, requests = fake_microsoft
    tokens = MemoryTokens()
    client = make(base, tokens)
    device = client.start_device_login()
    assert device["user_code"] == "ABC-123"
    assert client.complete_device_login(device) == "sales.marketing@travelessence.mv"
    assert client.is_signed_in

    icon = tmp_path / "email.png"
    icon.write_bytes(b"\x89PNG fake")
    client.send(OutgoingEmail(to=["sarah@gmail.com"], subject="Hello",
                              html=f'<p>Hi</p><img src="file:///{str(icon).lstrip("/")}">', cc=["cc@x.com"]))
    body = json.loads(next(r for r in requests if r[1] == "/graph/me/sendMail")[2])
    msg = body["message"]
    assert body["saveToSentItems"] is True
    assert msg["toRecipients"][0]["emailAddress"]["address"] == "sarah@gmail.com"
    assert msg["ccRecipients"][0]["emailAddress"]["address"] == "cc@x.com"
    att = msg["attachments"][0]
    assert att["isInline"] and f'cid:{att["contentId"]}' in msg["body"]["content"]


def test_expired_token_is_refreshed(fake_microsoft):
    base, _ = fake_microsoft
    tokens = MemoryTokens({"access_token": "OLD", "refresh_token": "RT1", "expires_at": 0})
    assert make(base, tokens).access_token() == "AT2"
    assert tokens.value["refresh_token"] == "RT1"


def test_large_attachment_uses_upload_session(fake_microsoft, tmp_path):
    base, requests = fake_microsoft
    big = tmp_path / "brochure.pdf"
    big.write_bytes(b"0" * (SIMPLE_ATTACHMENT_LIMIT + 10))
    make(base, signed_in()).send(OutgoingEmail(["a@x.com"], "Brochure", "<p>Attached</p>", [str(big)]))
    paths = [r[1] for r in requests]
    assert "/graph/me/messages" in paths
    assert any(p.endswith("/createUploadSession") for p in paths)
    assert "%2F" in next(p for p in paths if p.endswith("/createUploadSession"))   # message id is URL-encoded
    assert sum(len(r[2]) for r in requests if r[1].startswith("/upload/")) == big.stat().st_size
    assert paths[-1].endswith("/send")


def test_collect_sent_items_follows_paging_and_excludes_own_domain(fake_microsoft):
    base, requests = fake_microsoft
    result = collect(make(base, signed_in()), CollectOptions(folder="sent", exclude=["@travelessence.mv"]))
    assert [m.subject for m in result.messages] == ["Maldives offers", "Dubai quotation"]
    assert {c.email: c.interactions for c in result.contacts} == {"sarah@gmail.com": 2, "leo@icloud.com": 1}
    assert result.contacts[0].name == "Sarah Khan"
    query = urllib.parse.unquote(next(r[1] for r in requests if "mailFolders" in r[1]))
    assert "sentDateTime ge" in query and "$orderby=sentDateTime desc" in query


def test_load_message_as_template(fake_microsoft):
    base, _ = fake_microsoft
    data = load_message(make(base, signed_in()), "m1")
    assert data["subject"] == "Maldives offers"
    assert "cid:" not in data["html"] and "file:///" in data["html"]
    assert [a.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for a in data["attachments"]] == ["Brochure.pdf"]
    assert data["skipped"] == ["notes.docx"]

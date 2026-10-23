"""The inbox: numbering and "new" detection, IMAP against a fake server, Microsoft 365 against a fake Graph."""

import json
import socketserver
import threading
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from te_mailer.core.inbox import (
    GraphSource, ImapSource, Inbox, InboxMessage, InboxSource, SimulatedSource, insert_at_top,
    quoted_reply_document, reply_fragment, reply_subject, watched,
)
from te_mailer.core.senders import BaseSender


# ------------------------------------------------------------------ numbering / new detection
class ListSource(InboxSource):
    def __init__(self, name="list"):
        super().__init__(name)
        self.kind = name
        self.rows = []
        self.fail = None

    def add(self, n, when):
        self.rows.append(InboxMessage(key=f"{self.name}:{n}", source=self.name, account="a", from_name="X",
                                      from_email=f"x{n}@example.com", subject=f"S{n}", received=when))

    def fetch(self, limit, known):
        if self.fail:
            raise RuntimeError(self.fail)
        return [InboxMessage.from_dict(r.to_dict()) for r in self.rows]


def test_first_look_is_quiet_then_new_emails_are_numbered_in_order():
    src = ListSource()
    src.add(1, "2026-10-20T09:00:00")
    src.add(2, "2026-10-21T09:00:00")
    inbox = Inbox(lambda: [src])
    assert inbox.refresh() == []                         # what was already there is not "new"
    assert [m.seq for m in inbox.messages()] == [2, 1]   # but it is numbered, newest first
    src.add(3, "2026-10-22T10:00:00")
    src.add(4, "2026-10-22T09:00:00")
    fresh = inbox.refresh()
    assert [m.key for m in fresh] == ["list:4", "list:3"]   # numbered by arrival time
    assert inbox.find(4).key == "list:3" and inbox.latest_seq == 4
    assert inbox.refresh() == []

    reopened = Inbox(lambda: [src])                      # numbers and "seen" survive a restart
    assert reopened.refresh() == [] and reopened.find("list:3").seq == 4

    src.fail = "server down"
    assert reopened.refresh() == [] and "server down" in reopened.errors["list"]
    assert len(reopened.messages()) == 4                 # a failed check keeps what we had


def test_unwatched_mailbox_disappears():
    a, b = ListSource("a"), ListSource("b")
    a.add(1, "2026-10-20T09:00:00")
    b.add(1, "2026-10-20T10:00:00")
    sources = [a, b]
    inbox = Inbox(lambda: list(sources))
    inbox.refresh()
    sources.remove(b)
    inbox.refresh()
    assert [m.key for m in inbox.messages()] == ["a:1"]


def test_own_addresses():
    from te_mailer.core.inbox import own_addresses

    assert own_addresses({"smtp_from_email": "Sales@TE.mv", "signature": {"email": "info@te.mv"},
                          "inbox_imap_accounts": [{"username": "box@te.mv"}], "ms_account": ""}) == {
        "sales@te.mv", "info@te.mv", "box@te.mv"}


def test_watched_defaults():
    assert watched({"backend": "graph", "ms_account": "me@x.com"})["graph"] is True
    assert watched({"backend": "graph"})["graph"] is False          # not signed in yet
    assert watched({"backend": "simulate"})["simulate"] is True
    s = watched({"backend": "simulate", "inbox_imap_accounts": [{"host": "h", "username": "u"}]})
    assert s["simulate"] is False and len(s["imap"]) == 1


def test_reply_html_helpers():
    assert reply_subject("Quote") == "Re: Quote" and reply_subject("RE: Quote") == "RE: Quote"
    frag = reply_fragment("<html><body><p>Thanks!</p></body></html>", "<table>SIG</table>")
    assert "Thanks!" in frag and "SIG" in frag
    doc = insert_at_top('<html><body class="x"><p>original</p></body></html>', frag)
    assert doc.index("Thanks!") < doc.index("original") and doc.startswith('<html><body class="x">')
    msg = InboxMessage(key="k", source="imap", account="a", from_name="Sarah", from_email="s@x.com",
                       subject="Hi", received="2026-10-22T09:15:00")
    quoted = quoted_reply_document(frag, msg, "<html><body><p>Can you help?</p></body></html>")
    assert "On 2026-10-22 09:15, Sarah &lt;s@x.com&gt; wrote:" in quoted and "<blockquote" in quoted


def test_practice_mailbox():
    SimulatedSource.reset()
    src = SimulatedSource()
    inbox = Inbox(lambda: [src])
    assert inbox.refresh() == [] and len(inbox.messages()) == 3
    SimulatedSource.deliver("Ali", "ali@example.com", "Quote please", "Need a quote")
    fresh = inbox.refresh()
    assert [m.subject for m in fresh] == ["Quote please"]
    assert inbox.body(fresh[0])["text"] == "Need a quote"
    out = inbox.reply(fresh[0], "<p>Sure</p>")
    assert out == {"to": ["ali@example.com"], "cc": [], "subject": "Re: Quote please"}
    assert inbox.find(fresh[0].seq).unread is False


# ------------------------------------------------------------------ IMAP
def make_email(uid, sender, subject, text, html=None, cc=""):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "Travel Essence <sales.marketing@travelessence.mv>"
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject
    msg["Date"] = f"Thu, {uid + 10} Oct 2026 09:00:00 +0500"
    msg["Message-ID"] = f"<m{uid}@example.com>"
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
        msg.get_payload()[1].add_related(b"\x89PNG img", maintype="image", subtype="png", cid="<logo>")
    msg.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf", filename="brochure.pdf")
    return msg.as_bytes()


class FakeImap:
    """Just enough IMAP4rev1 for imaplib: LOGIN, SELECT/EXAMINE, UID SEARCH/FETCH/STORE, LOGOUT."""

    def __init__(self):
        self.mails = {}        # uid -> (bytes, set(flags))
        self.password = "secret"
        self.commands = []

        fake = self

        class Handler(socketserver.StreamRequestHandler):
            def send(self, line):
                self.wfile.write(line if isinstance(line, bytes) else line.encode())

            def handle(self):
                self.send("* OK fake IMAP ready\r\n")
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    tag, cmd, *rest = line.decode().rstrip("\r\n").split(" ", 2)
                    args = rest[0] if rest else ""
                    cmd = cmd.upper()
                    fake.commands.append(f"{cmd} {args}")
                    if cmd == "CAPABILITY":
                        self.send("* CAPABILITY IMAP4rev1\r\n" f"{tag} OK done\r\n")
                    elif cmd == "LOGIN":
                        ok = args.split(" ")[1].strip('"') == fake.password
                        self.send(f"{tag} OK logged in\r\n" if ok else f"{tag} NO bad password\r\n")
                    elif cmd in ("SELECT", "EXAMINE"):
                        self.send(f"* {len(fake.mails)} EXISTS\r\n* OK [UIDVALIDITY 77] ok\r\n{tag} OK done\r\n")
                    elif cmd == "UID":
                        self.uid(tag, args)
                    elif cmd == "LOGOUT":
                        self.send(f"* BYE\r\n{tag} OK bye\r\n")
                        return
                    else:
                        self.send(f"{tag} BAD unknown\r\n")

            def uid(self, tag, args):
                sub, rest = args.split(" ", 1)
                sub = sub.upper()
                if sub == "SEARCH":
                    self.send("* SEARCH " + " ".join(str(u) for u in sorted(fake.mails)) + f"\r\n{tag} OK done\r\n")
                    return
                uid_set, what = rest.split(" ", 1)
                uids = [int(u) for u in uid_set.split(",")]
                if sub == "STORE":
                    for u in uids:
                        flags = fake.mails[u][1]
                        (flags.add if what.startswith("+") else flags.discard)("\\Seen")
                    self.send(f"{tag} OK stored\r\n")
                    return
                for n, u in enumerate(uids, 1):
                    raw, flags = fake.mails[u]
                    meta = f"UID {u} FLAGS ({' '.join(sorted(flags))})"
                    if "RFC822.SIZE" in what:
                        self.send(f"* {n} FETCH ({meta} RFC822.SIZE {len(raw)})\r\n")
                    else:
                        data = raw.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n" if "HEADER" in what else raw
                        section = "BODY[HEADER]" if "HEADER" in what else "BODY[]"
                        self.send(f"* {n} FETCH ({meta} {section} {{{len(data)}}}\r\n".encode() + data + b")\r\n")
                self.send(f"{tag} OK fetched\r\n")

        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class CapturingSender(BaseSender):
    sent = []

    def open(self):
        pass

    def send(self, email):
        CapturingSender.sent.append(email)

    def close(self):
        pass


@pytest.fixture
def imap():
    server = FakeImap()
    server.mails[1] = (make_email(1, "Sarah Khan <sarah@example.com>", "Honeymoon in March", "Can you quote?",
                                  html='<p>Can you quote? <img src="cid:logo"></p>',
                                  cc="Ops <ops@travelessence.mv>, Mum <mum@example.com>"), set())
    server.mails[2] = (make_email(2, "James <james@example.org>", "Family trip", "Kids club?"), {"\\Seen"})
    yield server
    server.stop()


def imap_source(server, password="secret"):
    CapturingSender.sent = []
    account = {"host": "127.0.0.1", "port": server.port, "security": "none", "username": "sales@travelessence.mv"}
    return ImapSource(account, password, sender_factory=CapturingSender, timeout=5,
                      own={"sales.marketing@travelessence.mv"})


def test_imap_read_mark_and_threaded_reply(imap):
    src = imap_source(imap)
    inbox = Inbox(lambda: [src])
    inbox.refresh()
    rows = inbox.messages()
    assert [(m.subject, m.unread, m.from_email) for m in rows] == [
        ("Family trip", False, "james@example.org"), ("Honeymoon in March", True, "sarah@example.com")]
    sarah = rows[1]
    assert sarah.key == "imap:sales@travelessence.mv@127.0.0.1:77:1" and sarah.attachments == 1
    assert sarah.preview == "Can you quote?" and sarah.cc == ["ops@travelessence.mv", "mum@example.com"]
    assert not any(c.startswith("UID STORE") for c in imap.commands)   # reading never marks as read

    body = inbox.body(sarah)
    assert body["attachments"] == ["brochure.pdf"]
    assert "cid:logo" not in body["html"] and "file:///" in body["html"]   # inline picture saved locally

    imap.mails[3] = (make_email(3, "Ali <ali@example.com>", "Quote please", "Price for 2?"), set())
    fresh = inbox.refresh()
    assert [m.subject for m in fresh] == ["Quote please"] and fresh[0].seq == 3

    inbox.set_read(sarah, True)
    assert "\\Seen" in imap.mails[1][1] and inbox.find(sarah.seq).unread is False
    inbox.set_read(sarah, False)
    assert "\\Seen" not in imap.mails[1][1]

    out = inbox.reply(sarah, "<p>Here are three villas.</p>", "<b>SIG</b>", reply_all=True)
    assert out == {"to": ["sarah@example.com"], "cc": ["ops@travelessence.mv", "mum@example.com"],
                   "subject": "Re: Honeymoon in March"}
    sent = CapturingSender.sent[0]
    assert sent.subject == "Re: Honeymoon in March"
    assert sent.headers == {"In-Reply-To": "<m1@example.com>", "References": "<m1@example.com>"}
    assert sent.html.index("three villas") < sent.html.index("SIG") < sent.html.index("Can you quote?")
    assert "\\Seen" in imap.mails[1][1]


def test_imap_wrong_password_is_reported(imap):
    inbox = Inbox(lambda: [imap_source(imap, "nope")])
    assert inbox.refresh() == []
    assert "sign-in failed" in list(inbox.errors.values())[0]


# ------------------------------------------------------------------ Microsoft 365
@pytest.fixture
def fake_graph():
    calls = []
    state = {"read": False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _respond(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"null") if length else None
            path = self.path
            calls.append((self.command, path, body))
            code, data = 200, {}
            if path.startswith("/graph/me/mailFolders/inbox/messages"):
                data = {"value": [{
                    "id": "AAM/1=", "subject": "Villa quote", "receivedDateTime": "2026-10-22T04:00:00Z",
                    "from": {"emailAddress": {"name": "Sarah Khan", "address": "Sarah@Example.com"}},
                    "replyTo": [], "toRecipients": [{"emailAddress": {"address": "sales@travelessence.mv"}}],
                    "ccRecipients": [], "bodyPreview": "Can you quote a water villa?", "isRead": state["read"],
                    "hasAttachments": True, "internetMessageId": "<g1@example.com>"}]}
            elif path.startswith("/graph/me/messages/AAM%2F1%3D?"):
                data = {"hasAttachments": True, "body": {"contentType": "html",
                                                         "content": '<p>Quote?</p><img src="cid:pic">'}}
            elif path == "/graph/me/messages/AAM%2F1%3D/attachments":
                data = {"value": [{"name": "pic.png", "isInline": True, "contentId": "<pic>", "contentBytes": "iVBO"},
                                  {"name": "passport.pdf", "isInline": False, "contentBytes": "JVBE"}]}
            elif path == "/graph/me/messages/AAM%2F1%3D" and self.command == "PATCH":
                state["read"] = body["isRead"]
            elif path == "/graph/me/messages/AAM%2F1%3D/createReply":
                code, data = 201, {"id": "DRAFT/1", "body": {"content": "<html><body><p>QUOTED</p></body></html>"},
                                   "toRecipients": [{"emailAddress": {"address": "sarah@example.com"}}]}
            elif path.startswith("/graph/me/messages/DRAFT%2F1"):
                code, data = (202, None) if path.endswith("/send") else (200, {})
            else:
                code, data = 404, {"error": {"message": f"no route {path}"}}
            payload = json.dumps(data).encode() if data is not None else b""
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do_PATCH = do_DELETE = _respond

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", calls
    server.shutdown()


def test_graph_inbox_read_and_reply(fake_graph, tmp_path):
    from te_mailer.core.graph import GraphClient
    from tests.test_graph import signed_in

    base, calls = fake_graph
    client = GraphClient("cid", "common", signed_in(), graph_base=f"{base}/graph", login_base=base)
    src = GraphSource(client, "sales@travelessence.mv")
    inbox = Inbox(lambda: [src])
    inbox.refresh()
    (msg,) = inbox.messages()
    assert (msg.from_email, msg.unread, msg.account, msg.received) == (
        "sarah@example.com", True, "sales@travelessence.mv", msg.received)
    assert "%20desc" in calls[0][1]

    body = inbox.body(msg)
    assert body["attachments"] == ["passport.pdf"] and "cid:pic" not in body["html"]

    inbox.set_read(msg, True)
    assert ("PATCH", "/graph/me/messages/AAM%2F1%3D", {"isRead": True}) in calls

    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG")
    out = inbox.reply(msg, "<p>Three villas for you.</p>", f'<img src="file:///{logo.as_posix().lstrip("/")}">')
    assert out["to"] == ["sarah@example.com"] and out["subject"] == "Re: Villa quote"
    patch = next(b for c, p, b in calls if c == "PATCH" and p == "/graph/me/messages/DRAFT%2F1")
    html = patch["body"]["content"]
    assert html.index("Three villas") < html.index("QUOTED") and "cid:te-img-" in html
    inline = next(b for c, p, b in calls if p == "/graph/me/messages/DRAFT%2F1/attachments")
    assert inline["isInline"] is True and inline["contentId"].startswith("te-img-")
    assert calls[-1][:2] == ("POST", "/graph/me/messages/DRAFT%2F1/send")

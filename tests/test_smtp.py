import email
import socket

import pytest

from te_mailer.core.senders import OutgoingEmail, SmtpSender

aiosmtpd = pytest.importorskip("aiosmtpd.controller")


class Capture:
    def __init__(self):
        self.messages = []

    async def handle_DATA(self, server, session, envelope):
        self.messages.append(envelope)
        return "250 OK"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_smtp_html_inline_image_and_attachment(tmp_path):
    handler = Capture()
    port = free_port()
    controller = aiosmtpd.Controller(handler, hostname="127.0.0.1", port=port)
    controller.start()
    try:
        img = tmp_path / "banner.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        pdf = tmp_path / "Itinerary.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        html = f'<html><body><p>Hello <b>Sarah</b></p><img src="file:///{str(img).lstrip("/")}"></body></html>'

        sender = SmtpSender("127.0.0.1", port, "none", "", "", "info@travelessence.com", "Travel Essence")
        with sender:
            sender.send(OutgoingEmail(to=["sarah@example.com"], subject="Your trip", html=html,
                                      attachments=[str(pdf)], bcc=["log@travelessence.com"]))
    finally:
        controller.stop()

    envelope = handler.messages[0]
    assert set(envelope.rcpt_tos) == {"sarah@example.com", "log@travelessence.com"}
    msg = email.message_from_bytes(envelope.content)
    assert msg["Subject"] == "Your trip"
    assert "Bcc" not in msg
    assert "Travel Essence" in msg["From"]
    parts = {p.get_content_type(): p for p in msg.walk()}
    assert "text/plain" in parts and "text/html" in parts
    html_part = parts["text/html"].get_payload(decode=True).decode()
    cid = parts["image/png"]["Content-ID"].strip("<>")
    assert f"cid:{cid}" in html_part
    assert parts["application/pdf"].get_filename() == "Itinerary.pdf"

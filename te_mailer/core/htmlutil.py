"""HTML helpers: personalisation, email-safe HTML, inline images, plain-text fallback."""

from __future__ import annotations

import hashlib
import html
import os
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

from .recipients import Recipient

PLACEHOLDERS = {
    "first_name": "First name",
    "last_name": "Last name",
    "name": "Full name",
    "email": "Email address",
}

PLACEHOLDER_RE = re.compile(r"\{\s*(first_name|last_name|name|email)\s*\}", re.IGNORECASE)
BODY_RE = re.compile(r"<body([^>]*)>(.*)</body>", re.IGNORECASE | re.DOTALL)
BODY_OPEN_RE = re.compile(r"<body[^>]*>", re.IGNORECASE)
STYLE_ATTR_RE = re.compile(r'style\s*=\s*"([^"]*)"', re.IGNORECASE)
IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc\s*=\s*)(["\'])(.*?)\2', re.IGNORECASE | re.DOTALL)


def _values(recipient: Recipient, fallback: str) -> dict[str, str]:
    first = recipient.first_name or fallback
    name = recipient.name or fallback
    return {
        "first_name": first,
        "last_name": recipient.last_name,
        "name": name,
        "email": recipient.email,
    }


def personalize(text: str, recipient: Recipient, fallback: str = "", is_html: bool = False) -> str:
    values = _values(recipient, fallback)

    def repl(match: re.Match) -> str:
        value = values[match.group(1).lower()]
        return html.escape(value) if is_html else value

    return PLACEHOLDER_RE.sub(repl, text or "")


def body_inner(document: str) -> tuple[str, str]:
    """Return (inner_html, body_style) of an HTML document."""
    m = BODY_RE.search(document or "")
    if not m:
        return document or "", ""
    style_match = STYLE_ATTR_RE.search(m.group(1))
    return m.group(2), (style_match.group(1).strip() if style_match else "")


def build_email_html(editor_html: str, signature_html: str = "") -> str:
    """Turn the editor's HTML document into clean, email-client-friendly HTML.

    ``signature_html`` (from :mod:`signature`) is appended below the message.
    """
    inner, style = body_inner(editor_html)
    style = style or "font-family:'Segoe UI', Arial, sans-serif; font-size:11pt;"
    signature = f"<br>{signature_html}" if signature_html else ""
    return (
        "<!DOCTYPE html>\n<html><head><meta http-equiv=\"Content-Type\" "
        "content=\"text/html; charset=utf-8\"></head>\n"
        f"<body><div style=\"{style}\">{inner}</div>{signature}</body></html>"
    )


def merge_into_signature(signature_document: str, email_html: str) -> str:
    """Place our message at the top of an Outlook HTML body that holds the signature."""
    inner, _ = body_inner(email_html)
    m = BODY_OPEN_RE.search(signature_document or "")
    if not m:
        return email_html
    return signature_document[: m.end()] + inner + signature_document[m.end():]


def _local_path_from_src(src: str) -> str | None:
    src = html.unescape(src.strip())
    if src.lower().startswith("file:"):
        parsed = urlparse(src)
        path = unquote(parsed.path)
        if parsed.netloc:  # UNC path file://server/share/...
            path = f"//{parsed.netloc}{path}"
        if re.match(r"^/[A-Za-z]:", path):  # /C:/Users/... -> C:/Users/...
            path = path[1:]
        return path
    if re.match(r"^[A-Za-z]:[\\/]", src) or src.startswith("/") or src.startswith("\\\\"):
        return src
    return None


def extract_inline_images(document: str) -> tuple[str, list[tuple[str, str]]]:
    """Replace local <img> sources with ``cid:`` references.

    Returns the rewritten HTML and a list of ``(content_id, file_path)`` pairs the
    sender must embed in the message.
    """
    images: dict[str, str] = {}

    def repl(match: re.Match) -> str:
        path = _local_path_from_src(match.group(3))
        if not path or not os.path.isfile(path):
            return match.group(0)
        if path not in images:
            digest = hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]
            ext = os.path.splitext(path)[1].lower() or ".png"
            images[path] = f"te-img-{digest}{ext}"
        return f"{match.group(1)}{match.group(2)}cid:{images[path]}{match.group(2)}"

    rewritten = IMG_SRC_RE.sub(repl, document or "")
    return rewritten, [(cid, path) for path, cid in images.items()]


def strip_unresolved_cid_images(document: str) -> str:
    return re.sub(r"<img\b[^>]*\bsrc\s*=\s*[\"']cid:[^\"']*[\"'][^>]*>", "", document or "",
                  flags=re.IGNORECASE)


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0
        self._pending_href: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head"):
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n - ")
        elif tag in self.BLOCK:
            self.parts.append("\n")
        elif tag == "a":
            href = dict(attrs).get("href")
            if href and href.startswith("http"):
                self._pending_href = href

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "tr"):
            self.parts.append("\n")
        elif tag == "a" and self._pending_href:
            self.parts.append(f" ({self._pending_href})")
            self._pending_href = None

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(document: str) -> str:
    parser = _TextExtractor()
    parser.feed(document or "")
    text = "".join(parser.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_blank_html(document: str) -> bool:
    if re.search(r"<img\b", document or "", re.IGNORECASE):
        return False
    return not html_to_text(document).strip()

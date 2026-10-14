"""Branded email signature: contact rows with icons, social links and a logo.

The HTML uses nested tables, inline styles and fixed-size PNG images because that is what
renders reliably across Outlook (Word engine), Gmail, Apple Mail and phone clients.
Image sources are supplied by the caller (local file URLs on Windows) and are embedded
into each email as inline attachments by the senders.
"""

from __future__ import annotations

import html
import re
from typing import Callable
from urllib.parse import quote

# (key, label, URL prefix used when only a handle / number is entered)
SOCIALS = [
    ("facebook", "Facebook", "https://www.facebook.com/"),
    ("instagram", "Instagram", "https://www.instagram.com/"),
    ("whatsapp", "WhatsApp", "https://wa.me/"),
    ("tiktok", "TikTok", "https://www.tiktok.com/@"),
    ("linkedin", "LinkedIn", "https://www.linkedin.com/company/"),
    ("youtube", "YouTube", "https://www.youtube.com/@"),
    ("x", "X (Twitter)", "https://x.com/"),
]

DEFAULT_SIGNATURE: dict = {
    "enabled": True,
    "theme": "dark",                  # dark | light
    "accent": "#1E88E5",
    "name": "",
    "title": "",
    "email": "sales.marketing@travelessence.mv",
    "phone": "+960 7978580",
    "address": "H.Finivairoalhi, 2nd Floor\nRaivilla Magu, Henveiru",
    "website": "travelessence.mv",
    "logo_path": "",
    "logo_width": 200,
    "socials": {key: "" for key, _, _ in SOCIALS},
}

THEMES = {
    "dark": {"background": "#2B2B2B", "text": "#BDBDBD", "strong": "#FFFFFF"},
    "light": {"background": "#FFFFFF", "text": "#4B5563", "strong": "#111827"},
}

IconSource = Callable[[str, str], str]   # (kind: "contact" | "social", name) -> image src


def normalized(config: dict | None) -> dict:
    """Fill in missing keys so older settings files keep working."""
    cfg = {**DEFAULT_SIGNATURE, **(config or {})}
    cfg["socials"] = {**DEFAULT_SIGNATURE["socials"], **((config or {}).get("socials") or {})}
    return cfg


def social_url(platform: str, value: str) -> str:
    """Turn what the user typed (full link, @handle, page name or phone number) into a URL."""
    value = (value or "").strip()
    if not value:
        return ""
    if re.match(r"^https?://", value, re.IGNORECASE):
        return value
    if re.match(r"^(www\.)?[\w-]+\.[a-z]{2,}/", value, re.IGNORECASE):
        return "https://" + value          # e.g. facebook.com/travelessence
    prefix = next((p for key, _, p in SOCIALS if key == platform), "https://")
    if platform == "whatsapp":
        digits = re.sub(r"\D", "", value)
        return prefix + digits if digits else ""
    return prefix + quote(value.lstrip("@").strip("/"))


def website_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    return value if re.match(r"^https?://", value, re.IGNORECASE) else "https://" + value


def _e(text: str) -> str:
    return html.escape(text or "", quote=True)


def build_signature_html(config: dict, icon_src: IconSource, logo_src: str = "") -> str:
    cfg = normalized(config)
    colors = THEMES.get(cfg["theme"], THEMES["dark"])
    accent = cfg["accent"] or "#1E88E5"
    font = "font-family:Arial,Helvetica,sans-serif;"
    text_style = f"{font}font-size:14px;line-height:20px;color:{colors['text']};"
    link_style = f"color:{colors['text']};text-decoration:none;"

    rows: list[str] = []

    def row(icon: str, content: str) -> None:
        rows.append(
            f'<tr><td width="30" valign="top" style="padding:4px 0;">'
            f'<img src="{_e(icon_src("contact", icon))}" width="20" height="20" alt="" '
            f'style="display:block;border:0;width:20px;height:20px;"></td>'
            f'<td valign="top" style="padding:4px 0 4px 6px;{text_style}">{content}</td></tr>'
        )

    if cfg["name"].strip() or cfg["title"].strip():
        name = f'<span style="{font}font-size:16px;font-weight:bold;color:{colors["strong"]};">{_e(cfg["name"])}</span>'
        title = (f'<br><span style="{text_style}">{_e(cfg["title"])}</span>' if cfg["title"].strip() else "")
        rows.append(f'<tr><td colspan="2" style="padding:0 0 8px 0;">{name}{title}</td></tr>')

    if cfg["email"].strip():
        email = cfg["email"].strip()
        row("email", f'<a href="mailto:{_e(email)}" style="{link_style}">{_e(email)}</a>')
    if cfg["phone"].strip():
        phone = cfg["phone"].strip()
        tel = re.sub(r"[^\d+]", "", phone)
        row("phone", f'<a href="tel:{_e(tel)}" style="{link_style}">{_e(phone)}</a>')
    if cfg["address"].strip():
        lines = [line.strip() for line in cfg["address"].splitlines() if line.strip()]
        maps = "https://www.google.com/maps/search/?api=1&query=" + quote(", ".join(lines))
        row("address", f'<a href="{_e(maps)}" style="{link_style}">{"<br>".join(_e(l) for l in lines)}</a>')
    site = website_url(cfg["website"])
    if site:
        shown = re.sub(r"^https?://", "", site, flags=re.IGNORECASE).rstrip("/")
        row("website", f'<a href="{_e(site)}" style="color:{accent};font-weight:bold;text-decoration:none;">{_e(shown)}</a>')

    icons = []
    for key, label, _ in SOCIALS:
        url = social_url(key, cfg["socials"].get(key, ""))
        if url:
            icons.append(
                f'<a href="{_e(url)}" title="{_e(label)}" style="text-decoration:none;">'
                f'<img src="{_e(icon_src("social", key))}" width="28" height="28" alt="{_e(label)}" '
                f'style="border:0;width:28px;height:28px;"></a>'
            )
    if icons:
        rows.append(f'<tr><td colspan="2" style="padding:12px 0 0 0;">{"&nbsp;&nbsp;".join(icons)}</td></tr>')

    if logo_src:
        width = max(80, min(int(cfg.get("logo_width") or 200), 360))
        logo = f'<img src="{_e(logo_src)}" width="{width}" alt="Logo" style="display:block;border:0;width:{width}px;height:auto;">'
        if site:
            logo = f'<a href="{_e(site)}" style="text-decoration:none;">{logo}</a>'
        rows.append(f'<tr><td colspan="2" style="padding:18px 0 0 0;">{logo}</td></tr>')

    if not rows:
        return ""
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;background-color:{colors["background"]};">'
        f'<tr><td bgcolor="{colors["background"]}" style="padding:18px 22px;">'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;">'
        f'{"".join(rows)}</table></td></tr></table>'
    )

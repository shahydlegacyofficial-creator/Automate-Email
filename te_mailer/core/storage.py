"""Persistent storage: settings, draft, recipients, templates and send history.

Everything lives as JSON in ``%APPDATA%\\TravelEssenceEmailStudio`` on Windows
(``~/.local/share/TravelEssenceEmailStudio`` elsewhere).
"""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from .. import APP_ID

KEYRING_SERVICE = APP_ID

DEFAULT_SETTINGS: dict = {
    "theme": "light",
    "backend": "outlook",           # outlook | smtp | simulate
    "outlook_account": "",          # SMTP address of the Outlook account to send from ("" = default)
    "include_signature": False,
    "interval_seconds": 60,
    "name_fallback": "Valued Customer",
    "test_email": "",
    "smtp_host": "smtp.office365.com",
    "smtp_port": 587,
    "smtp_security": "starttls",    # starttls | ssl | none
    "smtp_username": "",
    "smtp_from_email": "",
    "smtp_from_name": "Travel Essence",
    "smtp_remember_password": True,
    "suppression_list": "",
    "outlook_exclude": "",
    "ms_client_id": "",            # Microsoft 365 / new Outlook (Microsoft Graph) app registration
    "ms_tenant": "common",
    "ms_account": "",
    "outlook_source": "classic",   # classic (Outlook app on this PC) | graph (Microsoft 365 / new Outlook)
    "signature": {},               # see core.signature.DEFAULT_SIGNATURE
    "ai_enabled": False,           # MCP server that lets Legacy AI (or another AI assistant) control the app
    "ai_port": 8765,
    "ai_token": "",
    "ai_approval": "campaigns",    # always | campaigns | never - when to ask in the app before AI sends
}

_lock = threading.RLock()


def data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    path = base / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def sub_dir(name: str) -> Path:
    path = data_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    """Atomic write so a crash never leaves a half-written file."""
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise


# ---------------------------------------------------------------- settings
def load_settings() -> dict:
    stored = read_json(data_dir() / "settings.json", {})
    settings = dict(DEFAULT_SETTINGS)
    if isinstance(stored, dict):
        settings.update({k: v for k, v in stored.items() if k in DEFAULT_SETTINGS})
    return settings


def save_settings(settings: dict) -> None:
    write_json(data_dir() / "settings.json", settings)


def get_password(username: str) -> str:
    if not username:
        return ""
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, username) or ""
    except Exception:
        return ""


def set_password(username: str, password: str) -> bool:
    if not username:
        return False
    try:
        import keyring

        if password:
            keyring.set_password(KEYRING_SERVICE, username, password)
        else:
            try:
                keyring.delete_password(KEYRING_SERVICE, username)
            except Exception:
                pass
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- draft & recipients
def load_draft() -> dict:
    draft = read_json(data_dir() / "draft.json", {})
    return {
        "subject": draft.get("subject", "") if isinstance(draft, dict) else "",
        "html": draft.get("html", "") if isinstance(draft, dict) else "",
        "attachments": [p for p in (draft.get("attachments", []) if isinstance(draft, dict) else [])
                        if isinstance(p, str)],
    }


def save_draft(draft: dict) -> None:
    write_json(data_dir() / "draft.json", draft)


def load_recipients() -> list[dict]:
    data = read_json(data_dir() / "recipients.json", [])
    return data if isinstance(data, list) else []


def save_recipients(rows: list[dict]) -> None:
    write_json(data_dir() / "recipients.json", rows)


# ---------------------------------------------------------------- saved recipient lists
def load_lists() -> list[dict]:
    """Named recipient lists: ``[{"name", "updated", "recipients": [{"email", "name"}]}]``."""
    data = read_json(data_dir() / "lists.json", [])
    if not isinstance(data, list):
        return []
    return [d for d in data if isinstance(d, dict) and str(d.get("name", "")).strip()
            and isinstance(d.get("recipients"), list)]


def save_lists(lists: list[dict]) -> None:
    write_json(data_dir() / "lists.json", lists)


# ---------------------------------------------------------------- templates
def load_templates() -> list[dict]:
    data = read_json(data_dir() / "templates.json", [])
    return data if isinstance(data, list) else []


def save_templates(templates: list[dict]) -> None:
    write_json(data_dir() / "templates.json", templates)


# ---------------------------------------------------------------- history
def history_dir() -> Path:
    return sub_dir("history")


def new_session(kind: str, subject: str, backend: str, interval: int, total: int,
                attachments: list[str]) -> dict:
    now = datetime.now()
    return {
        "id": now.strftime("%Y%m%d-%H%M%S-%f"),
        "kind": kind,                         # campaign | manual | test
        "started": now.isoformat(timespec="seconds"),
        "finished": None,
        "subject": subject,
        "backend": backend,
        "interval": interval,
        "total": total,
        "sent": 0,
        "failed": 0,
        "status": "running",                  # running | completed | stopped | error
        "attachments": [os.path.basename(a) for a in attachments],
        "results": [],                        # {email, name, status, time, message}
    }


def save_session(session: dict) -> None:
    write_json(history_dir() / f"{session['id']}.json", session)


def load_sessions() -> list[dict]:
    sessions = []
    for path in history_dir().glob("*.json"):
        data = read_json(path, None)
        if isinstance(data, dict) and "id" in data:
            sessions.append(data)
    # the id carries microseconds, so sessions started within the same second keep their order
    sessions.sort(key=lambda s: (s.get("started", ""), s.get("id", "")), reverse=True)
    return sessions


def delete_session(session_id: str) -> None:
    try:
        (history_dir() / f"{session_id}.json").unlink()
    except OSError:
        pass


def export_session_csv(path: str, session: dict) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Time", "Email", "Name", "Status", "Details"])
        for r in session.get("results", []):
            writer.writerow([r.get("time", ""), r.get("email", ""), r.get("name", ""),
                             r.get("status", ""), r.get("message", "")])


def all_time_stats() -> dict:
    sent = failed = campaigns = 0
    for s in load_sessions():
        sent += int(s.get("sent", 0))
        failed += int(s.get("failed", 0))
        if s.get("kind") == "campaign":
            campaigns += 1
    return {"sent": sent, "failed": failed, "campaigns": campaigns}

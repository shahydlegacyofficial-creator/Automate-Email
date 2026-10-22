"""A small Model Context Protocol (MCP) server over Streamable HTTP.

Lets an AI assistant such as Legacy AI drive the app through *tools*. Only the
parts of MCP this app needs are implemented: the ``initialize`` handshake
(protocol versions 2024-11-05 to 2025-11-25), ``ping``, ``tools/list`` and
``tools/call``, answered as plain JSON over HTTP POST (no SSE streams, no
sessions). Newer clients that open with ``server/discover`` get "method not
found" and fall back to ``initialize`` on their own.

The server only listens on 127.0.0.1, requires a bearer token and rejects
browser requests from other origins (DNS-rebinding protection). It has no Qt
dependency: tool handlers are plain callables, run on the HTTP thread.
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

log = logging.getLogger(__name__)

SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]
ENDPOINT = "/mcp"
MAX_BODY = 2 * 1024 * 1024
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class ToolError(Exception):
    """Raised by a tool handler to report a problem the AI can act on (returned with isError)."""


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[[dict], Any]
    properties: dict = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    title: str = ""
    read_only: bool = False
    destructive: bool = False
    idempotent: bool = False
    open_world: bool = False

    def schema(self) -> dict:
        return {"type": "object", "properties": self.properties, "required": self.required,
                "additionalProperties": False}

    def describe(self) -> dict:
        return {
            "name": self.name,
            "title": self.title or self.name.replace("_", " ").capitalize(),
            "description": self.description,
            "inputSchema": self.schema(),
            "annotations": {
                "title": self.title or self.name.replace("_", " ").capitalize(),
                "readOnlyHint": self.read_only,
                "destructiveHint": self.destructive,
                "idempotentHint": self.idempotent,
                "openWorldHint": self.open_world,
            },
        }


_JSON_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
               "array": list, "object": dict}


def check_arguments(tool: Tool, args: Any) -> dict:
    """Light validation against the tool's schema with messages an LLM can fix."""
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ToolError("Arguments must be a JSON object.")
    missing = [name for name in tool.required if args.get(name) in (None, "")]
    if missing:
        raise ToolError(f"Missing required argument(s): {', '.join(missing)}.")
    unknown = [name for name in args if name not in tool.properties]
    if unknown:
        raise ToolError(f"Unknown argument(s): {', '.join(unknown)}. "
                        f"Allowed: {', '.join(tool.properties) or 'none'}.")
    for name, value in args.items():
        spec = tool.properties[name]
        expected = spec.get("type")
        if value is None or expected is None:
            continue
        py_type = _JSON_TYPES.get(expected)
        if py_type is None:
            continue
        if expected in ("integer", "number") and isinstance(value, bool):
            raise ToolError(f"'{name}' must be a {expected}.")
        if expected == "integer" and isinstance(value, float) and value.is_integer():
            args[name] = value = int(value)
        if not isinstance(value, py_type):
            raise ToolError(f"'{name}' must be a{'n' if expected[0] in 'aeiou' else ''} {expected}.")
        if expected in ("integer", "number"):
            if "minimum" in spec and value < spec["minimum"]:
                raise ToolError(f"'{name}' must be at least {spec['minimum']}.")
            if "maximum" in spec and value > spec["maximum"]:
                raise ToolError(f"'{name}' must be at most {spec['maximum']}.")
        if "enum" in spec and value not in spec["enum"]:
            raise ToolError(f"'{name}' must be one of: {', '.join(map(str, spec['enum']))}.")
        if expected == "array" and spec.get("items", {}).get("type") == "string":
            if not all(isinstance(v, str) for v in value):
                raise ToolError(f"'{name}' must be a list of strings.")
    return args


def _tool_result(data: Any, is_error: bool = False) -> dict:
    if isinstance(data, str):
        text, structured = data, None
    else:
        text = json.dumps(data, ensure_ascii=False, indent=1, default=str)
        structured = data if isinstance(data, dict) else None
    result: dict = {"content": [{"type": "text", "text": text}], "isError": is_error}
    if structured is not None and not is_error:
        result["structuredContent"] = structured
    return result


class McpDispatcher:
    """Transport-independent JSON-RPC handling for the MCP methods above."""

    def __init__(self, tools: list[Tool], name: str, version: str, title: str = "", instructions: str = "",
                 on_call: Callable[[str, dict, dict], None] | None = None):
        self.tools = {t.name: t for t in tools}
        self.server_info = {"name": name, "version": version, **({"title": title} if title else {})}
        self.instructions = instructions
        self.on_call = on_call
        self.client_name = ""  # from the last initialize, e.g. "Legacy" - shown in approvals and the log

    # -------------------------------------------------------------- JSON-RPC
    def handle(self, message: Any) -> dict | None:
        """Handle one decoded JSON-RPC message; returns the response, or None for notifications."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, INVALID_REQUEST, "Invalid JSON-RPC 2.0 message.")
        if "method" not in message:
            return None  # a response to a server request - we never send any, so ignore it
        msg_id = message.get("id")
        if "id" not in message:
            return None  # notification (e.g. notifications/initialized)
        method = message.get("method")
        params = message.get("params") or {}
        if not isinstance(params, dict):
            return _error(msg_id, INVALID_PARAMS, "params must be an object.")
        try:
            if method == "initialize":
                result = self._initialize(params)
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [t.describe() for t in self.tools.values()]}
            elif method == "tools/call":
                result = self._call(params)
            else:
                return _error(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")
        except _RpcError as exc:
            return _error(msg_id, exc.code, str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("MCP %s failed", method)
            return _error(msg_id, INTERNAL_ERROR, f"Internal error: {exc}")
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _initialize(self, params: dict) -> dict:
        info = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
        self.client_name = str(info.get("title") or info.get("name") or "")[:60]
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
        result = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": self.server_info,
        }
        if self.instructions:
            result["instructions"] = self.instructions
        return result

    def _call(self, params: dict) -> dict:
        name = params.get("name")
        tool = self.tools.get(name)
        if tool is None:
            raise _RpcError(INVALID_PARAMS, f"Unknown tool: {name}. Call tools/list to see the available tools.")
        args = params.get("arguments")
        try:
            args = check_arguments(tool, args)
            data = tool.handler(args)
            result = _tool_result(data)
        except ToolError as exc:
            result = _tool_result(str(exc), is_error=True)
        except Exception as exc:
            log.exception("Tool %s failed", name)
            result = _tool_result(f"The app hit an unexpected error: {exc}", is_error=True)
        if self.on_call is not None:
            try:
                self.on_call(name, args if isinstance(args, dict) else {}, result)
            except Exception:  # pragma: no cover - logging must never break a call
                log.exception("on_call hook failed")
        return result


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def new_token() -> str:
    return secrets.token_urlsafe(24)


def _host_only(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("["):
        return value[: value.find("]") + 1] if "]" in value else value
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


class _Handler(BaseHTTPRequestHandler):
    server: "_HttpServer"
    protocol_version = "HTTP/1.1"
    server_version = "TravelEssenceMCP/1"

    def log_message(self, fmt, *args):  # keep the console quiet; errors go to the app log
        log.debug("MCP HTTP " + fmt, *args)

    # -------------------------------------------------------------- helpers
    def _send(self, status: int, body: Any = None, extra: dict | None = None) -> None:
        payload = b"" if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        if body is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _guard(self) -> bool:
        """Path, Host/Origin and token checks. Sends the error and returns False on failure."""
        if urlparse(self.path).path.rstrip("/") != ENDPOINT:
            self._send(404, {"error": f"Not found. The MCP endpoint is {ENDPOINT}"})
            return False
        if _host_only(self.headers.get("Host", "")).lower() not in LOCAL_HOSTS:
            self._send(403, {"error": "Only local connections are allowed."})
            return False
        origin = self.headers.get("Origin")
        if origin and origin != "null" and (urlparse(origin).hostname or "").lower() not in LOCAL_HOSTS:
            self._send(403, {"error": "Requests from web pages are not allowed."})
            return False
        auth = self.headers.get("Authorization", "")
        token = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
        if not token or not hmac.compare_digest(token.encode(), self.server.token.encode()):
            self._send(401, {"error": "Missing or wrong access token. Copy it from the app's "
                                      "AI assistant page."},
                       {"WWW-Authenticate": 'Bearer realm="Legacy AI Email Studio"'})
            return False
        return True

    # -------------------------------------------------------------- verbs
    def do_POST(self):
        if not self._guard():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self._send(413, _error(None, INVALID_REQUEST, "Request body is too large."))
            return
        raw = self.rfile.read(length)
        try:
            message = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._send(400, _error(None, PARSE_ERROR, "Body is not valid JSON."))
            return
        version = self.headers.get("MCP-Protocol-Version")
        if version and version not in SUPPORTED_PROTOCOL_VERSIONS:
            # 400 as the spec asks - answered with the request's own id so the client can tell which
            # request failed (newer clients then fall back to the initialize handshake).
            msg_id = message.get("id") if isinstance(message, dict) else None
            self._send(400, _error(msg_id, INVALID_REQUEST, f"Unsupported MCP-Protocol-Version: {version}. "
                                                            f"Supported: {', '.join(SUPPORTED_PROTOCOL_VERSIONS)}"))
            return
        dispatcher = self.server.dispatcher
        if isinstance(message, list):  # JSON-RPC batch (allowed by 2025-03-26)
            responses = [r for r in (dispatcher.handle(m) for m in message) if r is not None]
            self._send(200, responses) if responses else self._send(202)
            return
        response = dispatcher.handle(message)
        self._send(200, response) if response is not None else self._send(202)

    def do_GET(self):
        # No server-to-client stream is offered; the spec says to answer 405.
        if self._guard():
            self._send(405, {"error": "Use POST."}, {"Allow": "POST"})

    def do_DELETE(self):
        if self._guard():
            self._send(405, {"error": "This server keeps no sessions."}, {"Allow": "POST"})


class _HttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, dispatcher: McpDispatcher, token: str):
        self.dispatcher = dispatcher
        self.token = token
        super().__init__(address, _Handler)


class McpHttpServer:
    """Runs the dispatcher on http://127.0.0.1:<port>/mcp in a background thread."""

    def __init__(self, dispatcher: McpDispatcher, token: str, port: int = 8765, host: str = "127.0.0.1"):
        if not token:
            raise ValueError("A token is required")
        self.dispatcher = dispatcher
        self.token = token
        self.host = host
        self.port = port
        self._httpd: _HttpServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}{ENDPOINT}"

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> None:
        """Bind and serve. Raises OSError when the port is already in use."""
        if self._httpd is not None:
            return
        self._httpd = _HttpServer((self.host, self.port), self.dispatcher, self.token)
        self.port = self._httpd.server_address[1]  # resolves port 0 in tests
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="mcp-http", daemon=True)
        self._thread.start()
        log.info("MCP server listening on %s", self.url)

    def stop(self) -> None:
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
            log.info("MCP server stopped")
        self._thread = None

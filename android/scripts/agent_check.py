"""End-to-end check of the phone's MCP server (run by CI against the emulator through adb forward)."""
import json
import sys
import urllib.request

URL, TOKEN = sys.argv[1], sys.argv[2]


def rpc(method, params=None, rid=1):
    body = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}).encode()
    req = urllib.request.Request(URL, body, {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def call(name, **args):
    res = rpc("tools/call", {"name": name, "arguments": args})["result"]
    text = res["content"][0]["text"]
    print(f"{'ERR' if res['isError'] else 'ok '} {name}: {text[:160].replace(chr(10), ' ')}")
    return res


init = rpc("initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "CI agent check"}})
print("server:", init["result"]["serverInfo"], "protocol", init["result"]["protocolVersion"])
tools = [t["name"] for t in rpc("tools/list")["result"]["tools"]]
print("tools:", ", ".join(tools))
assert "start_campaign" in tools and len(tools) == 13, tools
status = call("get_status")
assert not status["isError"]
assert not call("add_recipients", emails="Ada Lovelace <ada@example.com>, grace@example.com")["isError"]
assert not call("compose_email", subject="Hello {first_name}", body="Dear {first_name},\n\nA note from CI.")["isError"]
prev = call("preview_email", email="ada@example.com")
assert prev["structuredContent"]["subject"] == "Hello Ada", prev
assert not call("send_test_email")["isError"]          # Simulation mode: nothing really leaves the phone
assert call("start_campaign", list_name="VIP")["isError"]  # Android has one list
hist = call("get_history", limit=3)
assert hist["structuredContent"]["sessions"][0]["subject"].startswith("[TEST] Hello"), hist
print("AGENT CHECK PASSED")

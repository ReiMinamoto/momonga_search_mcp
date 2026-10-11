"""Exercise disposable Compose token storage, HTTPS sessions and stdio without real credentials."""

import json
import os
from pathlib import Path
import ssl
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "MOMONGA_SEARCH_API_KEY": "unused-distribution-test-key", "MOMONGA_MCP_HOSTNAME": "localhost"}
COMPOSE = ["docker", "compose", "-p", "momonga-mcp-verify"]


def run(args, *, input=None, include_stderr=False):
    result = subprocess.run(args, cwd=REPO, env=ENV, input=input, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"Command failed: {args[0:3]} (exit {result.returncode})")
    return result.stdout + result.stderr if include_stderr else result.stdout


def issue(label):
    return json.loads(
        run(
            [
                *COMPOSE,
                "run",
                "--rm",
                "token-admin",
                "--store",
                "/run/momonga-tokens/client-tokens.json",
                "issue",
                "--label",
                label,
            ]
        )
    )


try:
    first, second = issue("test-department-a"), issue("test-department-b")
    run([*COMPOSE, "run", "--rm", "-d", "--use-aliases", "--name", "momonga-mcp-verify-server", "mcp"])
    run([*COMPOSE, "run", "--rm", "-d", "--name", "momonga-mcp-verify-tls", "-p", "127.0.0.1:58443:443", "tls"])
    for _attempt in range(40):
        result = subprocess.run(
            ["docker", "exec", "momonga-mcp-verify-tls", "cat", "/data/caddy/pki/authorities/local/root.crt"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            certificate = result.stdout
            break
        time.sleep(0.25)
    else:
        raise RuntimeError("Caddy did not create the public CA certificate")
    context = ssl.create_default_context(cadata=certificate)

    def request(token, method, *, session=None, rpc_method=None):
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-11-25",
        }
        if session:
            headers["MCP-Session-Id"] = session
        data = None
        if method == "POST":
            params = (
                {"protocolVersion": "2025-11-25", "clientInfo": {"name": "distribution-test", "version": "1"}, "capabilities": {}}
                if rpc_method == "initialize"
                else {}
            )
            message = {"jsonrpc": "2.0", "id": 1, "method": rpc_method, "params": params}
            if rpc_method == "notifications/initialized":
                del message["id"]
            data = json.dumps(message).encode()
        req = Request("https://localhost:58443/mcp", data=data, headers=headers, method=method)
        try:
            with urlopen(req, context=context, timeout=5) as response:
                return response.status, response.headers, response.read()
        except HTTPError as response:
            return response.code, response.headers, response.read()

    sessions = []
    for issued in (first, second):
        status, headers, body = request(issued["token"], "POST", rpc_method="initialize")
        assert status == 200
        session = headers["MCP-Session-Id"]
        assert request(issued["token"], "POST", session=session, rpc_method="notifications/initialized")[0] == 202
        status, _, body = request(issued["token"], "POST", session=session, rpc_method="tools/list")
        assert status == 200 and len(json.loads(body)["result"]["tools"]) == 18
        sessions.append(session)
    run(
        [
            *COMPOSE,
            "run",
            "--rm",
            "token-admin",
            "--store",
            "/run/momonga-tokens/client-tokens.json",
            "revoke",
            "--token-id",
            first["id"],
        ]
    )
    assert request(first["token"], "POST", session=sessions[0], rpc_method="ping")[0] == 401
    assert request(second["token"], "POST", session=sessions[1], rpc_method="ping")[0] == 200
    assert request(second["token"], "GET", session=sessions[1])[0] == 405
    logs = run(["docker", "logs", "momonga-mcp-verify-server"], include_stderr=True)
    assert "Uvicorn running" in logs
    assert first["token"] not in logs and second["token"] not in logs and ENV["MOMONGA_SEARCH_API_KEY"] not in logs
    print("Compose HTTPS: two independent clients, 18 tools, shared token volume, hot revocation and secret-free logs verified")

    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    output = run(
        ["docker", "run", "--rm", "-i", "momonga-search-mcp:local", "--transport", "stdio"],
        input="".join(json.dumps(message) + "\n" for message in messages),
    )
    responses = [json.loads(line) for line in output.splitlines()]
    assert len(responses) == 2 and len(responses[1]["result"]["tools"]) == 18
    print("Container stdio: initialize and unchanged 18-tool metadata verified")
finally:
    subprocess.run(["docker", "rm", "-f", "momonga-mcp-verify-server", "momonga-mcp-verify-tls"], capture_output=True)
    subprocess.run([*COMPOSE, "down", "--volumes", "--remove-orphans"], cwd=REPO, env=ENV, capture_output=True)

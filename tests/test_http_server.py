"""HTTP transport behavior, authentication and the shared public tool contract."""

from io import BytesIO, StringIO
import json

import pytest
from starlette.testclient import TestClient

from momonga_search_mcp.api import MomongaApiClient
from momonga_search_mcp.config import MCP_PROTOCOL_VERSION, Config, ConfigError
from momonga_search_mcp.http_server import MAX_BODY_BYTES, HttpConfig, create_http_app
from momonga_search_mcp.server import StdioMCPServer
from momonga_search_mcp.tokens import TokenStore
from momonga_search_mcp.tools.definitions import tool_definitions
from tests.tools.fakes import FakeApiClient


@pytest.fixture
def runtime(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    id_a, token_a = store.issue("department-a")
    id_b, token_b = store.issue("department-b")
    config = Config(api_key="server-test-key", cache_dir=tmp_path / "cache")
    api = FakeApiClient()
    app = create_http_app(
        config,
        HttpConfig(store.path, allowed_hosts=("testserver",), allowed_origins=("https://allowed.example",)),
        api_client=api,
    )
    with TestClient(app) as client:
        yield client, store, id_a, token_a, id_b, token_b, api, config


def _post(client, token, method, *, session=None, params=None, request_id=1, headers=None):
    common = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
    }
    if session is not None:
        common["MCP-Session-Id"] = session
    if params is None and method == "initialize":
        params = {"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}
    message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if request_id is not None:
        message["id"] = request_id
    return client.post("/mcp", json=message, headers={**common, **(headers or {})})


def _initialize(client, token):
    response = _post(
        client,
        token,
        "initialize",
        params={"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
    )
    assert response.status_code == 200
    assert response.json()["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
    session = response.headers["mcp-session-id"]
    notification = _post(client, token, "notifications/initialized", session=session, request_id=None)
    assert notification.status_code == 202 and notification.content == b""
    skill_index = _post(client, token, "tools/call", session=session, params={"name": "list_skills", "arguments": {}})
    assert not skill_index.json()["result"].get("isError")
    return session


def test_http_tool_list_preserves_all_existing_definitions(runtime):
    client, _, _, token, _, _, _, _ = runtime
    response = _post(client, token, "tools/list", session=_initialize(client, token))
    assert response.status_code == 200
    assert response.json()["result"]["tools"] == tool_definitions()
    assert len(response.json()["result"]["tools"]) == 18  # 17 workflow tools plus diagnose_setup.


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_every_mcp_method_requires_a_client_bearer(runtime, method):
    client = runtime[0]
    response = client.request(method, "/mcp")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_client_token_is_distinct_from_server_api_key_and_revokes_existing_sessions(runtime):
    client, store, id_a, token_a, _, token_b, _, config = runtime
    session = _initialize(client, token_a)
    assert _post(client, config.api_key, "ping", session=session).status_code == 401
    assert _post(client, token_b, "ping", session=session).status_code == 404
    store.revoke(id_a)
    assert _post(client, token_a, "ping", session=session).status_code == 401
    assert _post(client, token_b, "ping", session=_initialize(client, token_b)).status_code == 200


def test_origin_host_and_protocol_are_validated(runtime):
    client, _, _, token, _, _, _, _ = runtime
    assert _post(client, token, "initialize", headers={"Origin": "https://evil.example"}).status_code == 403
    assert _post(client, token, "initialize", headers={"Host": "evil.example"}).status_code == 400
    assert _post(client, token, "initialize", headers={"MCP-Protocol-Version": "2099-01-01"}).status_code == 400
    assert _post(client, token, "initialize", headers={"Origin": "https://allowed.example"}).status_code == 200


def test_get_declines_sse_and_delete_terminates_only_the_authenticated_session(runtime):
    client, _, _, token, _, _, _, _ = runtime
    session = _initialize(client, token)
    headers = {"Authorization": f"Bearer {token}", "MCP-Session-Id": session}
    assert client.get("/mcp", headers=headers).status_code == 405
    assert client.delete("/mcp", headers=headers).status_code == 204
    assert _post(client, token, "ping", session=session).status_code == 404
    assert _post(client, token, "ping").status_code == 400


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("search_issuers", {"q": "example"}),
        ("search_documents", {"query": "example", "top_k": 26}),
        ("list_documents", {"limit": 26}),
        ("get_document_original", {"document_id": "doc", "original_id": "file", "allow_file_download": False}),
    ],
)
def test_http_tool_responses_match_the_stdio_dispatcher(runtime, name, arguments):
    client, _, _, token, _, _, api, config = runtime
    session = _initialize(client, token)
    params = {"name": name, "arguments": arguments}
    response = _post(client, token, "tools/call", session=session, params=params)
    stdio = StdioMCPServer(config, input_stream=StringIO(), output_stream=StringIO(), api_client=api)
    stdio.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
    stdio.handle_message({"jsonrpc": "2.0", "id": 0, "method": "tools/call", "params": {"name": "list_skills", "arguments": {}}})
    expected = stdio.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params})
    assert response.json() == expected
    assert "structuredContent" not in response.json()["result"]


def test_clients_share_cached_sections_and_large_content_stays_a_manifest(runtime):
    client, _, _, token_a, _, token_b, api, _ = runtime
    a, b = _initialize(client, token_a), _initialize(client, token_b)
    api.response = {
        "document_id": "doc",
        "content_sections": [{"section_id": "s1", "section_title": "Example", "character_count": 3001, "content": "x" * 3001}],
    }
    params = {"name": "get_document_content", "arguments": {"document_id": "doc", "section_ids": ["s1"]}}
    first = _post(client, token_a, "tools/call", session=a, params=params)
    second = _post(client, token_b, "tools/call", session=b, params=params)
    assert first.status_code == second.status_code == 200
    assert len(api.calls) == 1
    assert "x" * 3001 not in first.text + second.text
    assert "momonga://documents/doc/sections/s1" in second.text
    payload = json.loads(second.json()["result"]["content"][0]["text"])
    assert not second.json()["result"].get("isError")
    assert payload["cache_hit"] is True


def test_invalid_and_oversized_http_envelopes_are_rejected(runtime):
    client, _, _, token, _, _, _, _ = runtime
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    assert client.post("/mcp", content=b"{", headers=headers).status_code == 400
    assert client.post("/mcp", content=b"x" * (MAX_BODY_BYTES + 1), headers=headers).status_code == 413
    assert client.post("/mcp", json=[], headers=headers).status_code == 400
    assert _post(client, token, "initialize", headers={"Accept": "application/json"}).status_code == 406
    assert _post(client, token, "initialize", headers={"Accept": "application/json, text/event-stream;q=0"}).status_code == 406


def test_missing_api_key_or_unreadable_token_store_refuses_http_startup(tmp_path):
    with pytest.raises(ConfigError, match="API_KEY"):
        create_http_app(Config(api_key="", cache_dir=tmp_path / "cache"), HttpConfig(tmp_path / "missing"))
    with pytest.raises(ConfigError, match="token store"):
        create_http_app(Config(api_key="test", cache_dir=tmp_path / "cache"), HttpConfig(tmp_path / "missing"))


def test_only_the_server_api_key_is_sent_upstream(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    _, client_token = store.issue("department-a")
    config = Config(api_key="server-only-test-key", cache_dir=tmp_path / "cache")
    captured = []

    def transport(request, _timeout):
        captured.append(request.get_header("Authorization"))
        return BytesIO(b'{"results": []}')

    app = create_http_app(
        config, HttpConfig(store.path, allowed_hosts=("testserver",)), api_client=MomongaApiClient(config, transport=transport)
    )
    with TestClient(app) as client:
        session = _initialize(client, client_token)
        response = _post(
            client, client_token, "tools/call", session=session, params={"name": "search_issuers", "arguments": {"q": "example"}}
        )
        assert not response.json()["result"].get("isError")
        assert captured == ["Bearer server-only-test-key"]
        assert config.api_key not in response.text and client_token not in response.text


def test_unreadable_token_store_rejects_existing_client_requests(runtime):
    client, store, _, token, _, _, _, _ = runtime
    session = _initialize(client, token)
    store.path.unlink()
    assert _post(client, token, "ping", session=session).status_code == 503


def test_session_capacity_is_bounded_and_delete_releases_a_slot(runtime):
    _, store, _, token, _, _, api, config = runtime
    app = create_http_app(config, HttpConfig(store.path, allowed_hosts=("testserver",), max_sessions=1), api_client=api)
    with TestClient(app) as client:
        session = _initialize(client, token)
        assert _post(client, token, "initialize").status_code == 503
        assert client.delete("/mcp", headers={"Authorization": f"Bearer {token}", "MCP-Session-Id": session}).status_code == 204
        assert _post(client, token, "initialize").status_code == 200


def test_expired_session_requires_initialization_again(runtime):
    _, store, _, token, _, _, api, config = runtime
    app = create_http_app(config, HttpConfig(store.path, allowed_hosts=("testserver",), session_ttl=0), api_client=api)
    with TestClient(app) as client:
        initialized = _post(client, token, "initialize")
        assert initialized.status_code == 200
        assert _post(client, token, "ping", session=initialized.headers["mcp-session-id"]).status_code == 404

"""Authenticated MCP 2025-11-25 Streamable HTTP with JSON replies and bounded sessions."""

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
import json
import logging
import os
from pathlib import Path
import secrets
import time

import anyio
from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
import uvicorn

from momonga_search_mcp.cache import CacheManager
from momonga_search_mcp.config import MCP_PROTOCOL_VERSION, Config, ConfigError
from momonga_search_mcp.server import StdioMCPServer
from momonga_search_mcp.tokens import TokenStore

logger = logging.getLogger(__name__)
MAX_BODY_BYTES = 1_048_576


@dataclass(frozen=True)
class HttpConfig:
    token_file: Path
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1")
    allowed_origins: tuple[str, ...] = ()
    session_ttl: float = 3600
    max_sessions: int = 128

    @classmethod
    def from_env(cls) -> HttpConfig:
        token_file = os.environ.get("MOMONGA_MCP_TOKEN_FILE", "").strip()
        if not token_file or not Path(token_file).is_absolute():
            raise ConfigError("MOMONGA_MCP_TOKEN_FILE must be an absolute path")
        hosts = tuple(
            value.strip()
            for value in os.environ.get("MOMONGA_MCP_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
            if value.strip()
        )
        origins = tuple(value.strip() for value in os.environ.get("MOMONGA_MCP_ALLOWED_ORIGINS", "").split(",") if value.strip())
        if not hosts or any("*" in host or "/" in host for host in hosts):
            raise ConfigError("MOMONGA_MCP_ALLOWED_HOSTS must contain explicit hostnames")
        return cls(Path(token_file), allowed_hosts=hosts, allowed_origins=origins)


@dataclass
class Session:
    principal: str
    dispatcher: StdioMCPServer
    touched: float


def create_http_app(config: Config, http: HttpConfig, *, api_client=None) -> Starlette:
    if not config.api_key:
        raise ConfigError("MOMONGA_SEARCH_API_KEY is required for HTTP on the server")
    tokens = TokenStore(http.token_file)
    try:
        if not any(not row["revoked"] for row in tokens.list()):
            raise ValueError("no active tokens")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ConfigError("HTTP requires a valid token store with an active client token") from exc
    cache = CacheManager(config.cache_dir, max_bytes=config.cache_max_bytes)
    sessions: dict[str, Session] = {}
    # A single worker serializes dispatcher/cache operations across clients, avoiding
    # file-write/prune races in the existing cache while keeping session state separate.
    lock = anyio.Lock()

    async def endpoint(request: Request) -> Response:
        origin = request.headers.get("origin")
        if origin is not None and origin not in http.allowed_origins:
            return Response(status_code=403)
        authorization = request.headers.get("authorization", "").split()
        if len(authorization) != 2 or authorization[0].lower() != "bearer":
            return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
        try:
            # Reload hashes on every request: revocation takes effect without restart.
            principal = tokens.authenticate(authorization[1])
        except (OSError, ValueError, KeyError, TypeError):
            logger.error("client token store is unavailable")
            return Response(status_code=503)
        if principal is None:
            return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
        protocol = request.headers.get("mcp-protocol-version")
        if protocol is not None and protocol != MCP_PROTOCOL_VERSION:
            return Response(status_code=400)
        if request.method == "GET":
            return Response(status_code=405, headers={"Allow": "POST, DELETE"})
        message = None
        if request.method == "POST":
            accepted = set()
            for item in request.headers.get("accept", "").lower().split(","):
                media_type, *parameters = [part.strip() for part in item.split(";")]
                try:
                    quality = float(next((part[2:] for part in parameters if part.startswith("q=")), "1"))
                except ValueError:
                    quality = 0
                if 0 < quality <= 1:
                    accepted.add(media_type)
            if not {"application/json", "text/event-stream"}.issubset(accepted):
                return Response(status_code=406)
            if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                return Response(status_code=415)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_BODY_BYTES:
                    return Response(status_code=413)
            try:
                message = json.loads(body)
            except (ValueError, UnicodeDecodeError):
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, status_code=400
                )
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
                return Response(status_code=400)
            if "id" in message and message["id"] is not None and type(message["id"]) not in (int, str):
                return Response(status_code=400)
            if "params" in message and not isinstance(message["params"], dict):
                return Response(status_code=400)
        async with lock:
            now = time.monotonic()
            for expired in [key for key, session in sessions.items() if now - session.touched >= http.session_ttl]:
                del sessions[expired]
            session_id = request.headers.get("mcp-session-id")
            if message is not None and message["method"] == "initialize":
                if session_id is not None or "id" not in message:
                    return Response(status_code=400)
                params = message.get("params", {})
                info = params.get("clientInfo", {})
                if (
                    not isinstance(params.get("protocolVersion"), str)
                    or not isinstance(params.get("capabilities"), dict)
                    or not isinstance(info, dict)
                    or not all(isinstance(info.get(field), str) for field in ("name", "version"))
                ):
                    return Response(status_code=400)
                if len(sessions) >= http.max_sessions:
                    return Response(status_code=503, headers={"Retry-After": "60"})
                session_id = secrets.token_urlsafe(32)
                sessions[session_id] = Session(
                    principal,
                    StdioMCPServer(
                        config, input_stream=StringIO(), output_stream=StringIO(), api_client=api_client, cache_manager=cache
                    ),
                    now,
                )
            if session_id is None:
                return Response(status_code=400)
            session = sessions.get(session_id)
            if session is None or session.principal != principal:
                return Response(status_code=404)
            if request.method == "DELETE":
                del sessions[session_id]
                return Response(status_code=204)
            session.touched = now
            try:
                response = await anyio.to_thread.run_sync(session.dispatcher.handle_message, message)
            except Exception:
                logger.error("MCP dispatcher failed")
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32603, "message": "Internal error"}}
                )
            if response is None:
                return Response(status_code=202)
            return JSONResponse(response, headers={"MCP-Session-Id": session_id})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["POST", "GET", "DELETE"])])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(http.allowed_hosts), www_redirect=False)
    return app


def run_http(config: Config, *, host: str, port: int) -> int:
    app = create_http_app(config, HttpConfig.from_env())
    uvicorn.run(app, host=host, port=port, workers=1, access_log=False)
    return 0

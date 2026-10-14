"""Minimal stdio MCP server skeleton."""

from __future__ import annotations

import json
import logging
import sys
from time import perf_counter
from typing import Any, TextIO

from dotenv import load_dotenv

from momonga_search_mcp.api import MomongaApiClient
from momonga_search_mcp.cache import CacheManager
from momonga_search_mcp.config import MCP_PROTOCOL_VERSION, SERVER_NAME, Config, ConfigError, resolved_server_version
from momonga_search_mcp.resources import is_momonga_resource_uri, read_momonga_resource
from momonga_search_mcp.tools.definitions import tool_definitions
from momonga_search_mcp.tools.handlers import call_tool

JSONRPC_VERSION = "2.0"

logger = logging.getLogger(__name__)


class StdioMCPServer:
    def __init__(
        self,
        config: Config,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
        api_client: MomongaApiClient | None = None,
        cache_manager: CacheManager | None = None,
    ) -> None:
        self.config = config
        self.input_stream = sys.stdin if input_stream is None else input_stream
        self.output_stream = sys.stdout if output_stream is None else output_stream
        self.api_client = MomongaApiClient(config) if api_client is None else api_client
        self.cache_manager = cache_manager
        self.initialized = False

    def serve_forever(self) -> None:
        logger.info(
            "starting %s over stdio base_url=%s cache_dir=%s",
            SERVER_NAME,
            self.config.base_url,
            self.config.cache_dir,
        )

        for line in self.input_stream:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
                response = self.handle_message(message)
            except json.JSONDecodeError as exc:
                logger.warning("received invalid JSON-RPC payload: %s", exc)
                response = _error_response(None, -32700, "Parse error")
            except Exception:
                logger.exception("unhandled server error")
                response = _error_response(None, -32603, "Internal error")

            if response is not None:
                _emit_json_line(self.output_stream, response)

        logger.info("stdio input closed; stopping %s", SERVER_NAME)

    def handle_message(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict):
            return _error_response(None, -32600, "Invalid Request")

        is_notification = "id" not in message
        request_id = message.get("id")
        method = message.get("method")

        if message.get("jsonrpc") != JSONRPC_VERSION:
            return _error_response(request_id, -32600, "Invalid Request")

        if is_notification:
            if method == "notifications/initialized":
                logger.info("client initialized")
                self.initialized = True
            else:
                logger.debug("ignored notification method=%s", method)
            return None

        if method == "initialize":
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": self._initialize_result()}
        if method == "ping":
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": {}}
        if not self.initialized:
            return _error_response(request_id, -32002, "Server not initialized")
        if method == "tools/list":
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": {"tools": tool_definitions()}}
        if method == "tools/call":
            params = message.get("params")
            if isinstance(params, dict) and isinstance(params.get("name"), str):
                known_tool_names = {tool["name"] for tool in tool_definitions()}
                if params["name"] not in known_tool_names:
                    return _error_response(request_id, -32602, f"Unknown tool: {params['name']}")
            start = perf_counter()
            try:
                result = call_tool(
                    self.api_client,
                    params,
                    cache_manager_getter=self._cache_manager,
                    config=self.config,
                )
            finally:
                logger.info(
                    "tool_completed name=%s duration_ms=%.1f",
                    params.get("name") if isinstance(params, dict) else None,
                    (perf_counter() - start) * 1000,
                )
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "result": result,
            }
        if method == "resources/list":
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": {"resources": []}}
        if method == "resources/read":
            return self._read_resource_response(request_id, message.get("params"))
        return _error_response(request_id, -32601, f"Method not found: {method}")

    def _initialize_result(self) -> dict[str, Any]:
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "serverInfo": {
                "name": SERVER_NAME,
                "version": resolved_server_version(),
            },
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False},
            },
            "instructions": "Momonga Search document and news API tools. Tool descriptions specify API semantics and retrieval limits.",
        }

    def _read_resource_response(self, request_id: Any, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict) or not isinstance(params.get("uri"), str):
            return _error_response(request_id, -32602, "resources/read requires uri")
        uri = params["uri"]
        try:
            if is_momonga_resource_uri(uri):
                text, mime_type = read_momonga_resource(self._cache_manager(), uri)
            else:
                raise ValueError(f"Unsupported resource URI: {uri}")
        except ValueError as exc:
            return _error_response(request_id, -32602, str(exc))
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "result": {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": mime_type,
                        "text": text,
                    }
                ]
            },
        }

    def _cache_manager(self) -> CacheManager:
        if self.cache_manager is None:
            self.cache_manager = CacheManager(self.config.cache_dir, max_bytes=self.config.cache_max_bytes)
        return self.cache_manager


def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _emit_json_line(output_stream: TextIO, payload: dict[str, Any]) -> None:
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    buffer = getattr(output_stream, "buffer", None)
    if buffer is not None:
        buffer.write(line.encode("utf-8"))
        buffer.flush()
        return
    output_stream.write(line)
    output_stream.flush()


def configure_stdio_encoding() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            logger.debug("failed to reconfigure %s to utf-8", getattr(stream, "name", "stream"), exc_info=True)


def configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=level,
    )


def main() -> int:
    load_dotenv()
    try:
        config = Config.from_env()
    except ConfigError as exc:
        configure_logging("ERROR")
        logger.error("configuration error: %s", exc)
        return 78

    configure_logging(config.log_level)
    configure_stdio_encoding()
    StdioMCPServer(config).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

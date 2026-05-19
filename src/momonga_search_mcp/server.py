"""Minimal stdio MCP server skeleton."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import json
import logging
import sys
from typing import Any, TextIO

from dotenv import load_dotenv

from momonga_search_mcp.api import MomongaApiClient
from momonga_search_mcp.config import Config, ConfigError
from momonga_search_mcp.logging import configure_logging

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "momonga-search-mcp"
SERVER_VERSION = "0.1.0"

logger = logging.getLogger(__name__)


class StdioMCPServer:
    def __init__(
        self,
        config: Config,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
        api_client: MomongaApiClient | None = None,
    ) -> None:
        self.config = config
        self.input_stream = sys.stdin if input_stream is None else input_stream
        self.output_stream = sys.stdout if output_stream is None else output_stream
        self.api_client = MomongaApiClient(config) if api_client is None else api_client

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
                self.output_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                self.output_stream.flush()

        logger.info("stdio input closed; stopping %s", SERVER_NAME)

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        is_notification = "id" not in message
        request_id = message.get("id")
        method = message.get("method")

        if message.get("jsonrpc") != JSONRPC_VERSION:
            return _error_response(request_id, -32600, "Invalid Request")

        if is_notification:
            if method == "notifications/initialized":
                logger.info("client initialized")
            else:
                logger.debug("ignored notification method=%s", method)
            return None

        if method == "initialize":
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": self._initialize_result()}
        if method == "ping":
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": {"tools": []}}
        if method == "resources/list":
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": {"resources": []}}
        if method == "prompts/list":
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": {"prompts": []}}

        return _error_response(request_id, -32601, f"Method not found: {method}")

    def _initialize_result(self) -> dict[str, Any]:
        try:
            server_version = version(SERVER_NAME)
        except PackageNotFoundError:
            server_version = SERVER_VERSION

        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "serverInfo": {
                "name": SERVER_NAME,
                "version": server_version,
            },
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {},
                "prompts": {},
            },
            "instructions": (
                "This MCP server provides Momonga Search API tools and workflow skills. "
                "Use document tools and news tools separately, and respect MCP-side credit and retrieval limits."
            ),
        }

def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def main() -> int:
    load_dotenv()
    try:
        config = Config.from_env()
    except ConfigError as exc:
        configure_logging("ERROR")
        logger.error("configuration error: %s", exc)
        return 78

    configure_logging(config.log_level)
    StdioMCPServer(config).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

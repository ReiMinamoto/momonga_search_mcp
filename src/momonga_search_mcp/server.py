"""Minimal stdio MCP server skeleton."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import json
import logging
import sys
from typing import Any, TextIO
from uuid import uuid4

from dotenv import load_dotenv

from momonga_search_mcp.api import MomongaApiClient
from momonga_search_mcp.cache import CacheManager
from momonga_search_mcp.config import Config, ConfigError
from momonga_search_mcp.logging import configure_logging
from momonga_search_mcp.prompts import get_prompt, prompt_definitions
from momonga_search_mcp.resources import is_momonga_resource_uri, read_momonga_resource
from momonga_search_mcp.skills import read_skill_resource, skill_resources
from momonga_search_mcp.tools.definitions import tool_definitions
from momonga_search_mcp.tools.handlers import call_tool

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-11-25"
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
        cache_manager: CacheManager | None = None,
    ) -> None:
        self.config = config
        self.input_stream = sys.stdin if input_stream is None else input_stream
        self.output_stream = sys.stdout if output_stream is None else output_stream
        self.api_client = MomongaApiClient(config) if api_client is None else api_client
        self.cache_manager = cache_manager
        self.session_id = uuid4().hex
        self.skill_index_seen = False

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
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": {"tools": tool_definitions()}}
        if method == "tools/call":
            params = message.get("params")
            result = call_tool(
                self.api_client,
                params,
                cache_manager_getter=self._cache_manager,
                config=self.config,
                session_id=self.session_id,
                skill_index_seen=self.skill_index_seen,
            )
            if isinstance(params, dict) and params.get("name") in {"list_skills", "get_skill"} and not result.get("isError"):
                self.skill_index_seen = True
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "result": result,
            }
        if method == "resources/list":
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": {"resources": skill_resources()}}
        if method == "resources/read":
            return self._read_resource_response(request_id, message.get("params"))
        if method == "prompts/list":
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": {"prompts": prompt_definitions()}}
        if method == "prompts/get":
            response = self._get_prompt_response(request_id, message.get("params"))
            if "error" not in response:
                self.skill_index_seen = True
            return response

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
                "resources": {"listChanged": False},
                "prompts": {"listChanged": False},
            },
            "instructions": (
                "This MCP server provides Momonga Search API tools and workflow skills. "
                "For every substantive research task, first read skill://index.json. If resource reads are unavailable, "
                "call list_skills as the fallback. Treat skills as the default entry point for supported workflows. "
                "If the index contains a skill that fits the task, follow that skill and read only its detail resource. "
                "If the task later enters a more specific workflow, such as known document content retrieval or file "
                "download, switch to the matching skill and read that skill detail resource before continuing. "
                "Do not load all skill details by default. If no skill fits the task, compose the available tools directly "
                "and preserve the same evidence and limit discipline. "
                "Use document tools and news tools separately. Do not perform integrated document/news ranking in the MVP. "
                "Before retrieving document content, check content_status, read toc when content_status=ready, inspect "
                "section_id, heading_path, and character_count, and retrieve only necessary sections. Respect MCP-side "
                "limits for credits, result count, section count, character count, page images, and original files. "
                "For page images and original files, never auto-download; require allow_file_download=true and return "
                "file_path, resource_uri, and metadata only. Always preserve evidence identifiers: document_id, section_id, "
                "news_id, reference_url, and references[]."
            ),
        }

    def _read_resource_response(self, request_id: Any, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict) or not isinstance(params.get("uri"), str):
            return _error_response(request_id, -32602, "resources/read requires uri")
        uri = params["uri"]
        try:
            if is_momonga_resource_uri(uri):
                text, mime_type = read_momonga_resource(self._cache_manager(), uri)
            else:
                text, mime_type = read_skill_resource(uri)
        except ValueError as exc:
            return _error_response(request_id, -32602, str(exc))
        if not is_momonga_resource_uri(uri):
            self.skill_index_seen = True
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

    def _get_prompt_response(self, request_id: Any, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return _error_response(request_id, -32602, "prompts/get requires name")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _error_response(request_id, -32602, "prompt arguments must be an object")
        try:
            result = get_prompt(params["name"], arguments)
        except ValueError as exc:
            return _error_response(request_id, -32602, str(exc))
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}

    def _cache_manager(self) -> CacheManager:
        if self.cache_manager is None:
            self.cache_manager = CacheManager(self.config.cache_dir)
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

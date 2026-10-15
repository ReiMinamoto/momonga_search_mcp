from __future__ import annotations

from io import BytesIO, StringIO, TextIOWrapper
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from momonga_search_mcp.config import Config, ConfigError
from momonga_search_mcp.server import StdioMCPServer, _emit_json_line, main
from tests.tools.fakes import FakeApiClient


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = self._initialized_server(Config(api_key="ms_test_xxx"))

    def _initialized_server(
        self,
        config: Config,
        *,
        api_client: FakeApiClient | None = None,
    ) -> StdioMCPServer:
        server = StdioMCPServer(config, api_client=api_client)
        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {},
            }
        )
        server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return server

    def test_initialize_response_contains_server_info(self) -> None:
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(response["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(response["result"]["serverInfo"]["name"], "momonga-search-mcp")
        self.assertIsInstance(response["result"]["serverInfo"]["version"], str)
        self.assertIn("tools", response["result"]["capabilities"])

    def test_ping(self) -> None:
        response = self.server.handle_message({"jsonrpc": "2.0", "id": "abc", "method": "ping"})

        self.assertEqual(response, {"jsonrpc": "2.0", "id": "abc", "result": {}})

    def test_initialized_notification_has_no_response(self) -> None:
        response = self.server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})

        self.assertIsNone(response)

    def test_rejects_tools_before_initialized_notification(self) -> None:
        server = StdioMCPServer(Config(api_key="ms_test_xxx"))

        response = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

        self.assertEqual(
            response,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32002,
                    "message": "Server not initialized",
                },
            },
        )

    def test_rejects_non_object_json_rpc_message(self) -> None:
        response = self.server.handle_message([])

        self.assertEqual(
            response,
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32600,
                    "message": "Invalid Request",
                },
            },
        )

    def test_null_id_request_still_gets_response(self) -> None:
        response = self.server.handle_message({"jsonrpc": "2.0", "id": None, "method": "ping"})

        self.assertEqual(response, {"jsonrpc": "2.0", "id": None, "result": {}})

    def test_unknown_method_returns_json_rpc_error(self) -> None:
        response = self.server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "missing"})

        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(response["error"]["code"], -32601)

    def test_tools_list_includes_document_and_news_tools(self) -> None:
        response = self.server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

        self.assertIsNotNone(response)
        assert response is not None
        tool_names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(
            tool_names,
            [
                "search_issuers",
                "list_documents",
                "get_document_metadata",
                "get_document_toc",
                "list_document_page_images",
                "list_document_originals",
                "list_news",
                "get_document_content",
                "search_section_contents",
                "get_section_window",
                "get_document_original",
                "get_document_page_image",
                "search_documents",
                "search_news",
                "diagnose_setup",
                "list_cached_resources",
            ],
        )

    def test_momonga_resources_list_and_read_cached_section_manifest_without_api_replay(self) -> None:
        api_client = FakeApiClient()
        with TemporaryDirectory() as temp_dir:
            server = self._initialized_server(
                Config(api_key="ms_test_xxx", cache_dir=Path(temp_dir)),
                api_client=api_client,
            )

            api_client.response = {
                "document_id": "doc_123",
                "toc": [{"section_id": "sec_1", "section_title": "Risk", "heading_path": ["Risk"], "character_count": 4}],
            }
            server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "get_document_toc", "arguments": {"document_id": "doc_123"}},
                }
            )

            api_client.response = {
                "document_id": "doc_123",
                "content_sections": [
                    {
                        "section_id": "sec_1",
                        "section_title": "Risk",
                        "character_count": 4,
                        "content": "body",
                    }
                ],
            }
            server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "get_document_content",
                        "arguments": {"document_id": "doc_123", "section_ids": ["sec_1"]},
                    },
                }
            )

            list_response = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "list_cached_resources",
                        "arguments": {"document_id": "doc_123", "resource_type": "section"},
                    },
                }
            )
            calls_before_read = list(api_client.calls)
            read_response = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "resources/read",
                    "params": {"uri": "momonga://documents/doc_123/sections/sec_1"},
                }
            )

        self.assertIsNotNone(list_response)
        assert list_response is not None
        payload = json.loads(list_response["result"]["content"][0]["text"])
        resource_uris = {resource["uri"] for resource in payload["resources"]}
        self.assertNotIn("momonga://documents/doc_123/toc", resource_uris)
        self.assertIn("momonga://documents/doc_123/sections/sec_1", resource_uris)
        self.assertIsNotNone(read_response)
        assert read_response is not None
        content = read_response["result"]["contents"][0]
        self.assertEqual(content["mimeType"], "application/json")
        read_payload = json.loads(content["text"])
        self.assertEqual(read_payload["document_id"], "doc_123")
        self.assertEqual(read_payload["section_id"], "sec_1")
        self.assertEqual(read_payload["section_title"], "Risk")
        self.assertEqual(read_payload["character_count"], 4)
        self.assertTrue(read_payload["content_available_in_cache"])
        self.assertEqual(read_payload["source_resource_uri"], "momonga://documents/doc_123/sections/sec_1")
        self.assertIn("get_section_window", read_payload["read_policy"])
        self.assertNotIn("content", read_payload)
        self.assertEqual(api_client.calls, calls_before_read)

    def test_tools_call_validates_required_arguments(self) -> None:
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_document_metadata", "arguments": {}},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertTrue(response["result"]["isError"])
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertIn("invalid_request", response["result"]["content"][0]["text"])
        self.assertEqual(payload["error"]["code"], "invalid_request")
        self.assertIsNone(payload["error"]["status"])
        self.assertEqual(payload["error"]["message"], "document_id is required")
        self.assertEqual(payload["error"]["next_action"], "Fix the tool input and retry the request.")

    def test_tools_call_unknown_tool_returns_json_rpc_error(self) -> None:
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "missing_tool", "arguments": {}},
            }
        )

        self.assertEqual(
            response,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32602,
                    "message": "Unknown tool: missing_tool",
                },
            },
        )

    def test_emit_json_line_writes_utf8_bytes_even_with_legacy_text_wrapper(self) -> None:
        response = {"jsonrpc": "2.0", "id": 2, "result": {"text": "企業開示"}}
        output_buffer = BytesIO()
        output_stream = TextIOWrapper(output_buffer, encoding="cp932")
        _emit_json_line(output_stream, response)
        parsed = json.loads(output_buffer.getvalue().decode("utf-8"))
        self.assertEqual(parsed["result"]["text"], "企業開示")

    def test_research_tools_are_available_without_workflow_setup(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {"results": []}
        server = self._initialized_server(Config(api_key="ms_test_xxx"), api_client=api_client)
        result = server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search_issuers", "arguments": {"q": "企業"}}}
        )
        self.assertNotIn("isError", result["result"])
        self.assertEqual(
            server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "resources/list"})["result"]["resources"], []
        )
        self.assertNotIn("prompts", server._initialize_result()["capabilities"])
        names = {
            tool["name"] for tool in server.handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})["result"]["tools"]
        }
        self.assertFalse(names & {"get_skill", "list_skills"})
        self.assertEqual(server.handle_message({"jsonrpc": "2.0", "id": 4, "method": "prompts/list"})["error"]["code"], -32601)
        self.assertEqual(
            server.handle_message(
                {"jsonrpc": "2.0", "id": 5, "method": "resources/read", "params": {"uri": "skill://index.json"}}
            )["error"]["code"],
            -32602,
        )


class ServerLoopTests(unittest.TestCase):
    def _serve(self, payloads: str) -> list[dict[str, object]]:
        input_stream = StringIO(payloads)
        output_stream = StringIO()
        server = StdioMCPServer(
            Config(api_key="ms_test_xxx"),
            input_stream=input_stream,
            output_stream=output_stream,
        )
        server.serve_forever()
        return [json.loads(line) for line in output_stream.getvalue().splitlines() if line.strip()]

    def test_serve_forever_processes_requests_and_skips_blank_lines(self) -> None:
        payloads = "\n   \n" + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"

        responses = self._serve(payloads)

        self.assertEqual(responses, [{"jsonrpc": "2.0", "id": 1, "result": {}}])

    def test_serve_forever_reports_parse_error_for_invalid_json(self) -> None:
        responses = self._serve("not-json\n")

        self.assertEqual(
            responses,
            [
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
            ],
        )

    def test_serve_forever_reports_internal_error_when_handler_raises(self) -> None:
        input_stream = StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n")
        output_stream = StringIO()
        server = StdioMCPServer(
            Config(api_key="ms_test_xxx"),
            input_stream=input_stream,
            output_stream=output_stream,
        )

        with patch.object(server, "handle_message", side_effect=RuntimeError("boom")):
            server.serve_forever()

        response = json.loads(output_stream.getvalue())
        self.assertEqual(response, {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": "Internal error"}})


class ServerMainTests(unittest.TestCase):
    def test_main_returns_config_error_exit_code(self) -> None:
        with (
            patch("momonga_search_mcp.server.load_dotenv"),
            patch("momonga_search_mcp.server.Config.from_env", side_effect=ConfigError("missing api key")),
        ):
            exit_code = main()

        self.assertEqual(exit_code, 78)

    def test_main_serves_until_stream_closes(self) -> None:
        served: dict[str, object] = {}

        class StubServer:
            def __init__(self, config: Config) -> None:
                served["config"] = config

            def serve_forever(self) -> None:
                served["served"] = True

        with (
            patch("momonga_search_mcp.server.load_dotenv"),
            patch("momonga_search_mcp.server.Config.from_env", return_value=Config(api_key="ms_test_xxx")),
            patch("momonga_search_mcp.server.configure_logging"),
            patch("momonga_search_mcp.server.configure_stdio_encoding") as configure_stdio,
            patch("momonga_search_mcp.server.StdioMCPServer", StubServer),
        ):
            exit_code = main()

        self.assertEqual(exit_code, 0)
        self.assertTrue(served["served"])
        configure_stdio.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

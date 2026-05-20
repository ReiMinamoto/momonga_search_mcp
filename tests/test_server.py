from __future__ import annotations

import unittest

from momonga_search_mcp.config import Config
from momonga_search_mcp.server import StdioMCPServer


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = StdioMCPServer(Config(api_key="ms_test_xxx"))

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
        self.assertEqual(response["result"]["serverInfo"]["name"], "momonga-search-mcp")
        self.assertIn("tools", response["result"]["capabilities"])

    def test_ping(self) -> None:
        response = self.server.handle_message({"jsonrpc": "2.0", "id": "abc", "method": "ping"})

        self.assertEqual(response, {"jsonrpc": "2.0", "id": "abc", "result": {}})

    def test_initialized_notification_has_no_response(self) -> None:
        response = self.server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})

        self.assertIsNone(response)

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
        tool_names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertEqual(
            tool_names,
            {
                "search_issuers",
                "list_documents",
                "get_document_metadata",
                "get_document_toc",
                "list_document_page_images",
                "list_document_originals",
                "list_news",
                "search_documents",
                "search_news",
                "get_document_content",
            },
        )

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
        self.assertIn("document_id is required", response["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest

from momonga_search_mcp.config import Config
from momonga_search_mcp.server import StdioMCPServer
from tests.tools.fakes import FakeApiClient


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
                "get_document_original",
                "get_document_page_image",
                "search_documents",
                "search_news",
                "list_skills",
                "get_skill",
            ],
        )

    def test_resources_list_includes_skill_resources(self) -> None:
        response = self.server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "resources/list"})

        self.assertIsNotNone(response)
        assert response is not None
        uris = [resource["uri"] for resource in response["result"]["resources"]]
        self.assertEqual(
            uris,
            [
                "skill://index.json",
                "skill://skills/document-research.md",
                "skill://skills/document-content-retrieval.md",
                "skill://skills/news-research.md",
                "skill://skills/file-download.md",
                "skill://skills/evidence-answering.md",
            ],
        )

    def test_resources_read_skill_index_is_lightweight_json(self) -> None:
        response = self.server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": "skill://index.json"}}
        )

        self.assertIsNotNone(response)
        assert response is not None
        content = response["result"]["contents"][0]
        self.assertEqual(content["mimeType"], "application/json")
        payload = json.loads(content["text"])
        self.assertEqual(len(payload["skills"]), 5)
        self.assertIn("resource_uri", payload["skills"][0])
        self.assertNotIn("## Workflow", content["text"])

    def test_resources_read_skill_detail(self) -> None:
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "resources/read",
                "params": {"uri": "skill://skills/document-research.md"},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        content = response["result"]["contents"][0]
        self.assertEqual(content["mimeType"], "text/markdown")
        self.assertIn("# Document Research Skill", content["text"])
        self.assertIn("Use `get_document_content`", content["text"])

    def test_prompts_list_and_get_representative_prompt(self) -> None:
        list_response = self.server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "prompts/list"})

        self.assertIsNotNone(list_response)
        assert list_response is not None
        prompt_names = [prompt["name"] for prompt in list_response["result"]["prompts"]]
        self.assertEqual(
            prompt_names,
            ["use_document_research", "use_news_research", "use_evidence_answering"],
        )

        get_response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "prompts/get",
                "params": {
                    "name": "use_document_research",
                    "arguments": {"target": "Toyota", "theme": "risk factors"},
                },
            }
        )

        self.assertIsNotNone(get_response)
        assert get_response is not None
        text = get_response["result"]["messages"][0]["content"]["text"]
        self.assertIn("skill://skills/document-research.md", text)
        self.assertIn("Toyota", text)
        self.assertIn("risk factors", text)

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
        self.assertEqual(payload["error"]["code"], "invalid_request")
        self.assertIsNone(payload["error"]["status"])
        self.assertEqual(payload["error"]["message"], "document_id is required")
        self.assertEqual(payload["error"]["next_action"], "Fix the tool input and retry the request.")

    def test_list_skills_helper(self) -> None:
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "list_skills", "arguments": {}},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertNotIn("isError", response["result"])
        self.assertEqual(
            [skill["id"] for skill in payload["skills"]],
            [
                "document-research",
                "document-content-retrieval",
                "news-research",
                "file-download",
                "evidence-answering",
            ],
        )
        self.assertIn("triggers", payload["skills"][0])

    def test_get_skill_helper(self) -> None:
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_skill", "arguments": {"id": "news-research"}},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["id"], "news-research")
        self.assertIn("# News Research Skill", payload["content"])

    def test_search_issuers_also_requires_skill_index_first(self) -> None:
        api_client = FakeApiClient()
        server = StdioMCPServer(Config(api_key="ms_test_xxx"), api_client=api_client)

        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "search_issuers", "arguments": {"q": "8058"}},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "skill_index_required")
        self.assertEqual(api_client.calls, [])

    def test_research_tool_requires_skill_index_first(self) -> None:
        api_client = FakeApiClient()
        server = StdioMCPServer(Config(api_key="ms_test_xxx"), api_client=api_client)

        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "list_documents", "arguments": {"security_codes": ["8058"]}},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "skill_index_required")
        next_action = payload["error"]["next_action"]
        self.assertIn("skill://index.json", next_action)
        self.assertIn("list_skills", next_action)
        self.assertIn("get_skill", next_action)
        self.assertIn("use_document_research", next_action)
        self.assertEqual(api_client.calls, [])

    def test_list_skills_unlocks_research_tools(self) -> None:
        api_client = FakeApiClient()
        server = StdioMCPServer(Config(api_key="ms_test_xxx"), api_client=api_client)

        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "list_skills", "arguments": {}},
            }
        )
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_documents", "arguments": {"security_codes": ["8058"]}},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertNotIn("isError", response["result"])
        self.assertEqual(api_client.calls, [("GET", "/documents", {"security_codes": ["8058"]})])

    def test_reading_skill_index_resource_unlocks_research_tools(self) -> None:
        api_client = FakeApiClient()
        server = StdioMCPServer(Config(api_key="ms_test_xxx"), api_client=api_client)

        server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": "skill://index.json"}}
        )
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_documents", "arguments": {"security_codes": ["8058"]}},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertNotIn("isError", response["result"])
        self.assertEqual(api_client.calls, [("GET", "/documents", {"security_codes": ["8058"]})])

    def test_reading_skill_detail_resource_unlocks_research_tools(self) -> None:
        api_client = FakeApiClient()
        server = StdioMCPServer(Config(api_key="ms_test_xxx"), api_client=api_client)

        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "resources/read",
                "params": {"uri": "skill://skills/document-research.md"},
            }
        )
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_documents", "arguments": {"security_codes": ["8058"]}},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertNotIn("isError", response["result"])
        self.assertEqual(api_client.calls, [("GET", "/documents", {"security_codes": ["8058"]})])

    def test_reading_unknown_resource_does_not_unlock_research_tools(self) -> None:
        api_client = FakeApiClient()
        server = StdioMCPServer(Config(api_key="ms_test_xxx"), api_client=api_client)

        server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": "skill://unknown.md"}}
        )
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_documents", "arguments": {"security_codes": ["8058"]}},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "skill_index_required")
        self.assertEqual(api_client.calls, [])

    def test_get_skill_unlocks_research_tools(self) -> None:
        api_client = FakeApiClient()
        server = StdioMCPServer(Config(api_key="ms_test_xxx"), api_client=api_client)

        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_skill", "arguments": {"id": "document-research"}},
            }
        )
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_documents", "arguments": {"security_codes": ["8058"]}},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertNotIn("isError", response["result"])
        self.assertEqual(api_client.calls, [("GET", "/documents", {"security_codes": ["8058"]})])

    def test_failed_get_skill_does_not_unlock_research_tools(self) -> None:
        api_client = FakeApiClient()
        server = StdioMCPServer(Config(api_key="ms_test_xxx"), api_client=api_client)

        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_skill", "arguments": {"id": "unknown"}},
            }
        )
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_documents", "arguments": {"security_codes": ["8058"]}},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "skill_index_required")
        self.assertEqual(api_client.calls, [])

    def test_launching_prompt_unlocks_research_tools(self) -> None:
        api_client = FakeApiClient()
        server = StdioMCPServer(Config(api_key="ms_test_xxx"), api_client=api_client)

        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "prompts/get",
                "params": {
                    "name": "use_document_research",
                    "arguments": {"target": "Toyota", "theme": "risk factors"},
                },
            }
        )
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_documents", "arguments": {"security_codes": ["8058"]}},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertNotIn("isError", response["result"])
        self.assertEqual(api_client.calls, [("GET", "/documents", {"security_codes": ["8058"]})])

    def test_failed_prompt_get_does_not_unlock_research_tools(self) -> None:
        api_client = FakeApiClient()
        server = StdioMCPServer(Config(api_key="ms_test_xxx"), api_client=api_client)

        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "prompts/get",
                "params": {"name": "unknown"},
            }
        )
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_documents", "arguments": {"security_codes": ["8058"]}},
            }
        )

        self.assertIsNotNone(response)
        assert response is not None
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "skill_index_required")
        self.assertEqual(api_client.calls, [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from momonga_search_mcp.config import Config
from momonga_search_mcp.server import StdioMCPServer
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
                "list_skills",
                "get_skill",
                "diagnose_setup",
                "list_cached_resources",
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
                "skill://skills/evidence-compression.md",
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
        self.assertEqual(len(payload["skills"]), 6)
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
        self.assertIn("switch to `document-content-retrieval`", content["text"])

    def test_momonga_resources_list_and_read_cached_section_manifest_without_api_replay(self) -> None:
        api_client = FakeApiClient()
        with TemporaryDirectory() as temp_dir:
            server = self._initialized_server(
                Config(api_key="ms_test_xxx", cache_dir=Path(temp_dir)),
                api_client=api_client,
            )
            server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "list_skills", "arguments": {}},
                }
            )

            api_client.response = {"document_id": "doc_123", "toc": [{"section_id": "sec_1", "section_title": "Risk"}]}
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
        payload = list_response["result"]["structuredContent"]
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

    def test_prompts_list_and_get_representative_prompt(self) -> None:
        list_response = self.server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "prompts/list"})

        self.assertIsNotNone(list_response)
        assert list_response is not None
        prompt_names = [prompt["name"] for prompt in list_response["result"]["prompts"]]
        self.assertEqual(
            prompt_names,
            ["use_document_research", "use_news_research", "use_evidence_answering"],
        )
        self.assertEqual(list_response["result"]["prompts"][0]["title"], "Use Document Research")

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

    def test_prompts_get_rejects_unknown_arguments(self) -> None:
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "prompts/get",
                "params": {
                    "name": "use_news_research",
                    "arguments": {"theme": "monetary policy", "ignored": "x"},
                },
            }
        )

        self.assertEqual(
            response,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "error": {
                    "code": -32602,
                    "message": "unknown prompt arguments: ignored",
                },
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
        payload = response["result"]["structuredContent"]
        self.assertIn("See structuredContent.", response["result"]["content"][0]["text"])
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
        payload = response["result"]["structuredContent"]
        self.assertNotIn("isError", response["result"])
        self.assertEqual(
            [skill["id"] for skill in payload["skills"]],
            [
                "document-research",
                "document-content-retrieval",
                "news-research",
                "file-download",
                "evidence-compression",
                "evidence-answering",
            ],
        )
        self.assertIn("triggers", payload["skills"][0])

    def test_evidence_compression_skill_resource(self) -> None:
        index_response = self.server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": "skill://index.json"}}
        )
        self.assertIsNotNone(index_response)
        assert index_response is not None
        index_payload = json.loads(index_response["result"]["contents"][0]["text"])
        skill = next(item for item in index_payload["skills"] if item["id"] == "evidence-compression")
        self.assertEqual(skill["recommended_first_tools"], ["search_section_contents", "get_section_window"])

        detail_response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "resources/read",
                "params": {"uri": "skill://skills/evidence-compression.md"},
            }
        )
        self.assertIsNotNone(detail_response)
        assert detail_response is not None
        content = detail_response["result"]["contents"][0]
        self.assertEqual(content["mimeType"], "text/markdown")
        self.assertIn("# Evidence Compression Skill", content["text"])
        self.assertIn("evidence_notes", content["text"])
        self.assertIn("source_resource_uri", content["text"])

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
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["id"], "news-research")
        self.assertIn("# News Research Skill", payload["content"])

    def test_search_issuers_also_requires_skill_index_first(self) -> None:
        api_client = FakeApiClient()
        server = self._initialized_server(Config(api_key="ms_test_xxx"), api_client=api_client)

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
        payload = response["result"]["structuredContent"]
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "skill_index_required")
        self.assertEqual(api_client.calls, [])

    def test_research_tool_requires_skill_index_first(self) -> None:
        api_client = FakeApiClient()
        server = self._initialized_server(Config(api_key="ms_test_xxx"), api_client=api_client)

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
        payload = response["result"]["structuredContent"]
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
        server = self._initialized_server(Config(api_key="ms_test_xxx"), api_client=api_client)

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
        server = self._initialized_server(Config(api_key="ms_test_xxx"), api_client=api_client)

        server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": "skill://index.json"}})
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
        server = self._initialized_server(Config(api_key="ms_test_xxx"), api_client=api_client)

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
        server = self._initialized_server(Config(api_key="ms_test_xxx"), api_client=api_client)

        server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": "skill://unknown.md"}})
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
        payload = response["result"]["structuredContent"]
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "skill_index_required")
        self.assertEqual(api_client.calls, [])

    def test_get_skill_unlocks_research_tools(self) -> None:
        api_client = FakeApiClient()
        server = self._initialized_server(Config(api_key="ms_test_xxx"), api_client=api_client)

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
        server = self._initialized_server(Config(api_key="ms_test_xxx"), api_client=api_client)

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
        payload = response["result"]["structuredContent"]
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "skill_index_required")
        self.assertEqual(api_client.calls, [])

    def test_launching_prompt_unlocks_research_tools(self) -> None:
        api_client = FakeApiClient()
        server = self._initialized_server(Config(api_key="ms_test_xxx"), api_client=api_client)

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
        server = self._initialized_server(Config(api_key="ms_test_xxx"), api_client=api_client)

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
        payload = response["result"]["structuredContent"]
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "skill_index_required")
        self.assertEqual(api_client.calls, [])


if __name__ == "__main__":
    unittest.main()

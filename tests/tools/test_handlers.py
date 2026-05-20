from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from momonga_search_mcp.api import MomongaApiError
from momonga_search_mcp.cache import CacheManager
from momonga_search_mcp.tools.handlers import call_tool
from tests.tools.fakes import FakeApiClient


class ToolHandlerTests(unittest.TestCase):
    def test_call_tool_routes_document_tools(self) -> None:
        api_client = FakeApiClient()
        calls = [
            ("get_document_metadata", {"document_id": "doc_123"}, "/documents/doc_123", None),
            ("list_document_page_images", {"document_id": "doc_123"}, "/documents/doc_123/page-images", None),
            ("list_document_originals", {"document_id": "doc_123"}, "/documents/doc_123/originals", None),
            (
                "list_documents",
                {"security_codes": ["8058"], "limit": 2, "ignored": "x"},
                "/documents",
                {"security_codes": ["8058"], "limit": 2},
            ),
        ]

        for name, arguments, expected_path, expected_params in calls:
            call_tool(api_client, {"name": name, "arguments": arguments})
            self.assertEqual(api_client.calls[-1], ("GET", expected_path, expected_params))

    def test_call_tool_returns_trimmed_success_response(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {
            "document_id": "doc_123",
            "document_family": "edinet_filing",
            "title": "Report",
            "document_type": "yuho",
            "issuers": [{"security_code": "8058", "name": "三菱商事株式会社"}],
            "timeline_at": "2026-05-01T00:00:00Z",
            "reference_url": "https://example.com/report.pdf",
            "internal_extra": "dropped",
        }

        response = call_tool(api_client, {"name": "get_document_metadata", "arguments": {"document_id": "doc_123"}})

        payload = json.loads(response["content"][0]["text"])
        self.assertEqual(
            payload,
            {
                "ok": True,
                "document_id": "doc_123",
                "document_family": "edinet_filing",
                "title": "Report",
                "document_type": "yuho",
                "issuers": [{"security_code": "8058", "name": "三菱商事株式会社"}],
                "timeline_at": "2026-05-01T00:00:00Z",
                "reference_url": "https://example.com/report.pdf",
            },
        )

    def test_call_tool_routes_credit_search_and_news_tools(self) -> None:
        api_client = FakeApiClient()
        calls = [
            (
                "search_documents",
                {"query": "価格転嫁", "top_k": 3, "include_snippet": True, "ignored": "x"},
                "/search/documents",
                {"query": "価格転嫁", "top_k": 3, "include_snippet": True},
            ),
            (
                "list_news",
                {"security_codes": ["8058"], "limit": 2},
                "/news",
                {"security_codes": ["8058"], "limit": 2},
            ),
            (
                "search_news",
                {"query": "金融政策", "match_type": "lexical"},
                "/search/news",
                {"query": "金融政策", "match_type": "lexical"},
            ),
        ]

        for name, arguments, expected_path, expected_payload in calls:
            call_tool(api_client, {"name": name, "arguments": arguments})
            self.assertEqual(
                api_client.calls[-1], ("POST" if name.startswith("search_") else "GET", expected_path, expected_payload)
            )

    def test_get_document_toc_stores_response(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {"document_id": "doc_123", "title": "Report", "toc": [{"section_id": "sec_1"}]}
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {"name": "get_document_toc", "arguments": {"document_id": "doc_123"}},
                cache_manager_getter=lambda: cache_manager,
            )

            payload = json.loads(response["content"][0]["text"])
            cached_toc = cache_manager.get_document_toc("doc_123")

        self.assertEqual(api_client.calls, [("GET", "/documents/doc_123/toc", None)])
        self.assertFalse(payload["cache_hit"])
        self.assertEqual(payload["resource_uri"], "momonga://documents/doc_123/toc")
        self.assertNotIn("title", payload)
        self.assertIsNotNone(cached_toc)

    def test_get_document_toc_returns_cache_hit_without_api_call(self) -> None:
        api_client = FakeApiClient()
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            cache_manager.store_document_toc("doc_123", {"document_id": "doc_123", "toc": [{"section_id": "sec_1"}]})

            response = call_tool(
                api_client,
                {"name": "get_document_toc", "arguments": {"document_id": "doc_123"}},
                cache_manager_getter=lambda: cache_manager,
            )

        payload = json.loads(response["content"][0]["text"])
        self.assertEqual(api_client.calls, [])
        self.assertTrue(payload["cache_hit"])
        self.assertEqual(payload["toc"][0]["section_id"], "sec_1")

    def test_get_document_content_stores_sections_and_returns_payload(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {
            "document_id": "doc_123",
            "content": "full",
            "content_sections": [
                {
                    "section_id": "sec_1",
                    "section_title": "Risk",
                    "character_count": 4,
                    "content": "body",
                    "internal_extra": "dropped",
                }
            ],
        }
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {
                    "name": "get_document_content",
                    "arguments": {"document_id": "doc_123", "section_ids": ["sec_1"], "return_content": False},
                },
                cache_manager_getter=lambda: cache_manager,
            )

            payload = json.loads(response["content"][0]["text"])
            cached_section = cache_manager.get_document_section("doc_123", "sec_1")

        self.assertEqual(api_client.calls, [("GET", "/documents/doc_123/content", {"sections": ["sec_1"]})])
        self.assertFalse(payload["cache_hit"])
        self.assertNotIn("content", payload)
        self.assertEqual(payload["content_sections"][0]["section_title"], "Risk")
        self.assertEqual(payload["content_sections"][0]["character_count"], 4)
        self.assertIn("resource_uri", payload["content_sections"][0])
        self.assertFalse(payload["content_sections"][0]["cached"])
        self.assertNotIn("internal_extra", payload["content_sections"][0])
        self.assertNotIn("content", payload["content_sections"][0])
        self.assertIsNotNone(cached_section)

    def test_get_document_content_returns_cache_hit_without_api_call(self) -> None:
        api_client = FakeApiClient()
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            cache_manager.store_document_section(
                "doc_123",
                "sec_1",
                {
                    "section_id": "sec_1",
                    "section_title": "Risk",
                    "character_count": 11,
                    "content": "cached body",
                    "internal_extra": "dropped",
                },
            )

            response = call_tool(
                api_client,
                {
                    "name": "get_document_content",
                    "arguments": {"document_id": "doc_123", "section_ids": ["sec_1"], "return_content": False},
                },
                cache_manager_getter=lambda: cache_manager,
            )

        payload = json.loads(response["content"][0]["text"])
        self.assertEqual(api_client.calls, [])
        self.assertTrue(payload["cache_hit"])
        self.assertEqual(payload["content_sections"][0]["section_title"], "Risk")
        self.assertEqual(payload["content_sections"][0]["character_count"], 11)
        self.assertTrue(payload["content_sections"][0]["cached"])
        self.assertNotIn("internal_extra", payload["content_sections"][0])
        self.assertNotIn("content", payload["content_sections"][0])

    def test_cache_backed_tools_require_cache_manager(self) -> None:
        for tool_name in ("get_document_toc", "get_document_content"):
            response = call_tool(FakeApiClient(), {"name": tool_name, "arguments": {"document_id": "doc_123"}})
            payload = json.loads(response["content"][0]["text"])

            self.assertTrue(response["isError"])
            self.assertEqual(payload["error"]["code"], "invalid_request")
            self.assertIsNone(payload["error"]["status"])
            self.assertIn("cache manager is required", payload["error"]["message"])
            self.assertEqual(payload["error"]["next_action"], "Fix the tool input and retry the request.")

    def test_call_tool_returns_model_facing_api_error(self) -> None:
        api_client = FakeApiClient()
        api_client.error = MomongaApiError(status=409, code="content_not_available", message="Content not available")
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {"name": "get_document_toc", "arguments": {"document_id": "doc_123"}},
                cache_manager_getter=lambda: cache_manager,
            )

        self.assertTrue(response["isError"])
        self.assertIn('"content_not_available"', response["content"][0]["text"])

    def test_call_tool_validates_required_arguments(self) -> None:
        response = call_tool(FakeApiClient(), {"name": "get_document_metadata", "arguments": {}})
        payload = json.loads(response["content"][0]["text"])

        self.assertTrue(response["isError"])
        self.assertEqual(
            payload,
            {
                "ok": False,
                "error": {
                    "code": "invalid_request",
                    "status": None,
                    "message": "document_id is required",
                    "next_action": "Fix the tool input and retry the request.",
                },
            },
        )

    def test_call_tool_returns_model_facing_unknown_tool_error(self) -> None:
        response = call_tool(FakeApiClient(), {"name": "missing_tool", "arguments": {}})
        payload = json.loads(response["content"][0]["text"])

        self.assertTrue(response["isError"])
        self.assertEqual(
            payload,
            {
                "ok": False,
                "error": {
                    "code": "unknown_tool",
                    "status": None,
                    "message": "Unknown tool: missing_tool",
                    "next_action": "Use one of the tool names returned by tools/list.",
                },
            },
        )


if __name__ == "__main__":
    unittest.main()

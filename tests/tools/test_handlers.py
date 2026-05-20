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
        api_client.response = {"document_id": "doc_123", "toc": [{"section_id": "sec_1"}]}
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
                    "heading_path": ["Risk"],
                    "character_count": 4,
                    "content": "body",
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
        self.assertEqual(payload["content"], "full")
        self.assertEqual(payload["content_sections"][0]["heading_path"], ["Risk"])
        self.assertEqual(payload["content_sections"][0]["content"], "body")
        self.assertIsNotNone(cached_section)

    def test_get_document_content_returns_cache_hit_without_api_call(self) -> None:
        api_client = FakeApiClient()
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            cache_manager.store_document_section(
                "doc_123",
                "sec_1",
                {"section_id": "sec_1", "heading_path": ["Risk"], "character_count": 11, "content": "cached body"},
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
        self.assertEqual(payload["content_sections"][0]["heading_path"], ["Risk"])
        self.assertEqual(payload["content_sections"][0]["content"], "cached body")

    def test_cache_backed_tools_require_cache_manager(self) -> None:
        for tool_name in ("get_document_toc", "get_document_content"):
            response = call_tool(FakeApiClient(), {"name": tool_name, "arguments": {"document_id": "doc_123"}})

            self.assertTrue(response["isError"])
            self.assertIn("cache manager is required", response["content"][0]["text"])

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

        self.assertTrue(response["isError"])
        self.assertIn("document_id is required", response["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()

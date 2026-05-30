from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from momonga_search_mcp.api import MomongaApiError
from momonga_search_mcp.cache import CacheManager
from momonga_search_mcp.config import Config
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
                {"security_codes": ["8058"], "limit": 2},
                "/documents",
                {"security_codes": ["8058"], "limit": 2},
            ),
        ]

        for name, arguments, expected_path, expected_params in calls:
            call_tool(api_client, {"name": name, "arguments": arguments})
            self.assertEqual(api_client.calls[-1], ("GET", expected_path, expected_params))

    def test_call_tool_quotes_document_id_path_components(self) -> None:
        api_client = FakeApiClient()
        document_id = "doc/with space"
        calls = [
            ("get_document_metadata", "/documents/doc%2Fwith%20space"),
            ("list_document_page_images", "/documents/doc%2Fwith%20space/page-images"),
            ("list_document_originals", "/documents/doc%2Fwith%20space/originals"),
        ]

        for name, expected_path in calls:
            call_tool(api_client, {"name": name, "arguments": {"document_id": document_id}})
            self.assertEqual(api_client.calls[-1], ("GET", expected_path, None))

    def test_call_tool_returns_trimmed_success_response(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {
            "document_id": "doc_123",
            "document_family": "edinet_filing",
            "title": "Report",
            "document_type": "yuho",
            "issuers": [{"security_code": "8058", "name": "三菱商事株式会社"}],
            "published_at": "2026-05-01T00:00:00Z",
            "timeline_at": "2026-05-01T00:00:00Z",
            "character_count": 9000,
            "reference_url": "https://example.com/report.pdf",
            "internal_extra": "dropped",
        }

        response = call_tool(api_client, {"name": "get_document_metadata", "arguments": {"document_id": "doc_123"}})

        payload = response["structuredContent"]
        self.assertEqual(
            payload,
            {
                "ok": True,
                "document_id": "doc_123",
                "document_family": "edinet_filing",
                "title": "Report",
                "document_type": "yuho",
                "issuers": [{"security_code": "8058", "name": "三菱商事株式会社"}],
                "published_at": "2026-05-01T00:00:00Z",
                "timeline_at": "2026-05-01T00:00:00Z",
                "character_count": 9000,
                "reference_url": "https://example.com/report.pdf",
            },
        )

    def test_call_tool_routes_search_and_news_tools(self) -> None:
        api_client = FakeApiClient()
        calls = [
            (
                "search_documents",
                {"query": "価格転嫁", "top_k": 3, "include_snippet": True},
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

            payload = response["structuredContent"]
            cached_toc = cache_manager.get_document_toc("doc_123")

        self.assertEqual(api_client.calls, [("GET", "/documents/doc_123/toc", None)])
        self.assertFalse(payload["cache_hit"])
        self.assertEqual(payload["resource_uri"], "momonga://documents/doc_123/toc")
        self.assertNotIn("title", payload)
        self.assertIsNotNone(cached_toc)

    def test_get_document_toc_quotes_document_id_path_component(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {"document_id": "doc/with space", "toc": []}
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {"name": "get_document_toc", "arguments": {"document_id": "doc/with space"}},
                cache_manager_getter=lambda: cache_manager,
            )
            cached_toc = cache_manager.get_document_toc("doc/with space")

        self.assertEqual(api_client.calls, [("GET", "/documents/doc%2Fwith%20space/toc", None)])
        self.assertNotIn("isError", response)
        self.assertIsNotNone(cached_toc)
        self.assertEqual(response["structuredContent"]["resource_uri"], "momonga://documents/doc%2Fwith%20space/toc")

    def test_get_document_toc_returns_cache_hit_without_api_call(self) -> None:
        api_client = FakeApiClient()
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            cache_manager.store_document_toc(
                "doc_123",
                {"document_id": "doc_123", "toc": [{"section_id": "sec_1", "heading_path": ["Business"]}]},
            )

            response = call_tool(
                api_client,
                {"name": "get_document_toc", "arguments": {"document_id": "doc_123"}},
                cache_manager_getter=lambda: cache_manager,
            )

        payload = response["structuredContent"]
        self.assertEqual(api_client.calls, [])
        self.assertTrue(payload["cache_hit"])
        self.assertEqual(payload["toc"][0]["heading_path"], ["Business"])

    def test_get_document_toc_applies_outline_options_to_cache_hit(self) -> None:
        api_client = FakeApiClient()
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            cache_manager.store_document_toc(
                "doc_123",
                {
                    "document_id": "doc_123",
                    "toc": [
                        {
                            "section_id": "sec_1",
                            "section_title": "Risk",
                            "heading_path": ["Business", "Risk"],
                            "character_count": 100,
                            "page_number": 2,
                        },
                        {
                            "section_id": "sec_2",
                            "section_title": "Governance",
                            "heading_path": ["Governance"],
                            "character_count": 50,
                            "page_number": 8,
                        },
                    ],
                },
            )

            response = call_tool(
                api_client,
                {
                    "name": "get_document_toc",
                    "arguments": {
                        "document_id": "doc_123",
                        "path_prefix": ["Business"],
                        "max_depth": 2,
                        "include_sections": True,
                    },
                },
                cache_manager_getter=lambda: cache_manager,
            )

        payload = response["structuredContent"]
        self.assertEqual(api_client.calls, [])
        self.assertEqual(payload["toc_mode"], "subtree")
        self.assertEqual(payload["toc"][0]["children"][0]["sections"][0]["section_id"], "sec_1")

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

            payload = response["structuredContent"]
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

    def test_get_document_content_reports_missing_requested_sections(self) -> None:
        api_client = FakeApiClient()
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
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {
                    "name": "get_document_content",
                    "arguments": {"document_id": "doc_123", "section_ids": ["sec_1", "sec_missing"]},
                },
                cache_manager_getter=lambda: cache_manager,
            )

        payload = response["structuredContent"]
        self.assertNotIn("isError", response)
        self.assertEqual(payload["requested_section_ids"], ["sec_1", "sec_missing"])
        self.assertEqual(payload["missing_section_ids"], ["sec_missing"])
        self.assertEqual([section["section_id"] for section in payload["content_sections"]], ["sec_1"])

    def test_get_document_content_errors_when_no_requested_sections_are_returned(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {"document_id": "doc_123", "content_sections": []}
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {
                    "name": "get_document_content",
                    "arguments": {"document_id": "doc_123", "section_ids": ["sec_missing"]},
                },
                cache_manager_getter=lambda: cache_manager,
            )

        payload = response["structuredContent"]
        self.assertTrue(response["isError"])
        self.assertEqual(payload["error"]["code"], "invalid_request")
        self.assertEqual(payload["error"]["message"], "requested section_ids were not returned: sec_missing")

    def test_get_document_content_quotes_document_id_path_component(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {
            "document_id": "doc/with space",
            "content_sections": [{"section_id": "sec/with space", "content": "body"}],
        }
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {
                    "name": "get_document_content",
                    "arguments": {"document_id": "doc/with space", "section_ids": ["sec/with space"]},
                },
                cache_manager_getter=lambda: cache_manager,
            )
            cached_section = cache_manager.get_document_section("doc/with space", "sec/with space")

        self.assertEqual(
            api_client.calls,
            [("GET", "/documents/doc%2Fwith%20space/content", {"sections": ["sec/with space"]})],
        )
        self.assertNotIn("isError", response)
        self.assertIsNotNone(cached_section)
        self.assertEqual(
            response["structuredContent"]["content_sections"][0]["resource_uri"],
            "momonga://documents/doc%2Fwith%20space/sections/sec%2Fwith%20space",
        )

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

        payload = response["structuredContent"]
        self.assertEqual(api_client.calls, [])
        self.assertTrue(payload["cache_hit"])
        self.assertEqual(payload["content_sections"][0]["section_title"], "Risk")
        self.assertEqual(payload["content_sections"][0]["character_count"], 11)
        self.assertTrue(payload["content_sections"][0]["cached"])
        self.assertNotIn("internal_extra", payload["content_sections"][0])
        self.assertNotIn("content", payload["content_sections"][0])

    def test_get_document_content_large_section_returns_manifest_and_caches_body(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {
            "document_id": "doc_123",
            "content_sections": [
                {
                    "section_id": "sec_1",
                    "section_title": "Risk",
                    "character_count": 3001,
                    "content": "risk " + ("x" * 2996),
                }
            ],
        }
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {
                    "name": "get_document_content",
                    "arguments": {"document_id": "doc_123", "section_ids": ["sec_1"]},
                },
                cache_manager_getter=lambda: cache_manager,
            )
            payload = response["structuredContent"]
            cached_section = cache_manager.get_document_section("doc_123", "sec_1")
            assert cached_section is not None
            cached_payload = cache_manager.read_json(cached_section)

        section = payload["content_sections"][0]
        self.assertEqual(section["content_mode"], "manifest")
        self.assertEqual(section["reason"], "section_exceeds_inline_threshold")
        self.assertTrue(section["content_available_in_cache"])
        self.assertEqual(section["recommended_tools"], ["search_section_contents", "get_section_window"])
        self.assertEqual(section["next_action"]["tool"], "search_section_contents")
        self.assertEqual(section["next_action"]["argument_hints"]["document_id"], "doc_123")
        self.assertEqual(section["next_action"]["argument_hints"]["section_id"], "sec_1")
        self.assertEqual(section["next_action"]["fallback_tool"], "get_section_window")
        self.assertEqual(section["source_resource_uri"], "momonga://documents/doc_123/sections/sec_1")
        self.assertNotIn("content", section)
        self.assertEqual(cached_payload["content"], "risk " + ("x" * 2996))

    def test_search_section_contents_returns_bounded_matches_from_cache(self) -> None:
        api_client = FakeApiClient()
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            cache_manager.store_document_section(
                "doc_123",
                "sec_1",
                {
                    "section_id": "sec_1",
                    "section_title": "Risk",
                    "heading_path": ["Business", "Risk"],
                    "character_count": 70,
                    "content": "alpha price beta price gamma price delta",
                },
            )

            response = call_tool(
                api_client,
                {
                    "name": "search_section_contents",
                    "arguments": {
                        "document_id": "doc_123",
                        "section_id": "sec_1",
                        "query": "price",
                        "context_chars": 50,
                        "max_matches": 2,
                    },
                },
                cache_manager_getter=lambda: cache_manager,
            )

        payload = response["structuredContent"]
        self.assertEqual(api_client.calls, [])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["section_title"], "Risk")
        self.assertNotIn("heading_path", payload)
        self.assertEqual(payload["source_resource_uri"], "momonga://documents/doc_123/sections/sec_1")
        self.assertEqual(len(payload["matches"]), 2)
        self.assertEqual(payload["matches"][0]["offset"], 6)
        self.assertEqual(payload["matches"][0]["matched_text"], "price")
        self.assertLessEqual(len(payload["matches"][0]["excerpt"]), len("price") + 100)

    def test_search_section_contents_handles_no_matches(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            cache_manager.store_document_section(
                "doc_123",
                "sec_1",
                {"section_id": "sec_1", "content": "cached body"},
            )

            response = call_tool(
                FakeApiClient(),
                {
                    "name": "search_section_contents",
                    "arguments": {"document_id": "doc_123", "section_id": "sec_1", "query": "missing"},
                },
                cache_manager_getter=lambda: cache_manager,
            )

        payload = response["structuredContent"]
        self.assertEqual(payload["matches"], [])
        self.assertEqual(payload["source_resource_uri"], "momonga://documents/doc_123/sections/sec_1")

    def test_search_section_contents_normalizes_query_and_preserves_original_offsets(self) -> None:
        content = "前文 ＡＩ と ２０２６年 （１）終わり"
        cases = [
            ("AI", "ＡＩ"),
            ("2026", "２０２６"),
            ("(1)", "（１）"),
        ]
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            cache_manager.store_document_section(
                "doc_123",
                "sec_1",
                {"section_id": "sec_1", "content": content},
            )

            for query, matched_text in cases:
                with self.subTest(query=query):
                    response = call_tool(
                        FakeApiClient(),
                        {
                            "name": "search_section_contents",
                            "arguments": {
                                "document_id": "doc_123",
                                "section_id": "sec_1",
                                "query": query,
                            },
                        },
                        cache_manager_getter=lambda: cache_manager,
                    )

                    payload = response["structuredContent"]
                    self.assertTrue(payload["ok"])
                    self.assertEqual(payload["matches"][0]["offset"], content.index(matched_text))
                    self.assertEqual(payload["matches"][0]["matched_text"], matched_text)

    def test_get_section_window_returns_offsets_and_respects_max_characters(self) -> None:
        api_client = FakeApiClient()
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            cache_manager.store_document_section(
                "doc_123",
                "sec_1",
                {
                    "section_id": "sec_1",
                    "section_title": "Risk",
                    "heading_path": ["Business", "Risk"],
                    "content": "0123456789abcdefghij",
                },
            )

            response = call_tool(
                api_client,
                {
                    "name": "get_section_window",
                    "arguments": {
                        "document_id": "doc_123",
                        "section_id": "sec_1",
                        "offset": 10,
                        "max_characters": 6,
                    },
                },
                cache_manager_getter=lambda: cache_manager,
            )

        payload = response["structuredContent"]
        self.assertEqual(api_client.calls, [])
        self.assertEqual(payload["content"], "789abc")
        self.assertNotIn("heading_path", payload)
        self.assertEqual(payload["start_offset"], 7)
        self.assertEqual(payload["end_offset"], 13)
        self.assertEqual(payload["actual_characters"], 6)
        self.assertEqual(payload["source_resource_uri"], "momonga://documents/doc_123/sections/sec_1")
        self.assertTrue(payload["truncated"])

    def test_get_section_window_handles_offset_near_edges(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            cache_manager.store_document_section("doc_123", "sec_1", {"section_id": "sec_1", "content": "0123456789"})

            near_start = call_tool(
                FakeApiClient(),
                {
                    "name": "get_section_window",
                    "arguments": {"document_id": "doc_123", "section_id": "sec_1", "offset": 1, "max_characters": 4},
                },
                cache_manager_getter=lambda: cache_manager,
            )["structuredContent"]
            near_end = call_tool(
                FakeApiClient(),
                {
                    "name": "get_section_window",
                    "arguments": {"document_id": "doc_123", "section_id": "sec_1", "offset": 100, "max_characters": 4},
                },
                cache_manager_getter=lambda: cache_manager,
            )["structuredContent"]

        self.assertEqual(near_start["start_offset"], 0)
        self.assertEqual(near_start["content"], "0123")
        self.assertEqual(near_end["start_offset"], 6)
        self.assertEqual(near_end["content"], "6789")

    def test_cached_section_readers_report_uncached_section(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                FakeApiClient(),
                {
                    "name": "search_section_contents",
                    "arguments": {"document_id": "doc_123", "section_id": "sec_missing", "query": "risk"},
                },
                cache_manager_getter=lambda: cache_manager,
            )

        payload = response["structuredContent"]
        self.assertTrue(response["isError"])
        self.assertEqual(payload["error"]["code"], "invalid_request")
        self.assertIn("section content is not cached", payload["error"]["message"])

    def test_list_cached_resources_filters_by_document_and_type(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            cache_manager.store_document_toc("doc_123", {"document_id": "doc_123", "toc": []})
            cache_manager.store_document_section(
                "doc_123",
                "sec_1",
                {"section_id": "sec_1", "content": "body"},
            )
            cache_manager.store_document_section(
                "doc_456",
                "sec_2",
                {"section_id": "sec_2", "content": "other"},
            )

            response = call_tool(
                FakeApiClient(),
                {
                    "name": "list_cached_resources",
                    "arguments": {"document_id": "doc_123", "resource_type": "section"},
                },
                cache_manager_getter=lambda: cache_manager,
            )

        payload = response["structuredContent"]
        self.assertEqual(payload["ok"], True)
        self.assertEqual(
            [resource["uri"] for resource in payload["resources"]],
            ["momonga://documents/doc_123/sections/sec_1"],
        )
        self.assertEqual(payload["resources"][0]["document_id"], "doc_123")
        self.assertEqual(payload["resources"][0]["resource_type"], "section")
        self.assertEqual(payload["resources"][0]["section_id"], "sec_1")

    def test_list_cached_resources_reports_setup_error_when_cache_unavailable(self) -> None:
        response = call_tool(FakeApiClient(), {"name": "list_cached_resources", "arguments": {}})
        payload = response["structuredContent"]

        self.assertTrue(response["isError"])
        self.assertEqual(payload["error"]["code"], "server_setup_error")
        self.assertIn("cache manager is unavailable", payload["error"]["message"])

    def test_diagnose_setup_reports_local_setup_without_secret(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = Config(api_key="secret-key", base_url="https://example.test/v1", cache_dir=Path(temp_dir))

            response = call_tool(FakeApiClient(), {"name": "diagnose_setup", "arguments": {}}, config=config)

            payload = response["structuredContent"]

        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["api_key_configured"], True)
        self.assertEqual(payload["base_url"], "https://example.test/v1")
        self.assertEqual(payload["cache_dir"], temp_dir)
        self.assertEqual(payload["cache_writable"], True)
        self.assertEqual(payload["server_name"], "momonga-search-mcp")
        self.assertEqual(payload["protocol_version"], "2025-11-25")
        self.assertNotIn("api_key", payload)
        self.assertNotIn("secret-key", str(payload))

    def test_diagnose_setup_reports_missing_api_key(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = Config(api_key="", base_url="https://example.test/v1", cache_dir=Path(temp_dir))

            response = call_tool(FakeApiClient(), {"name": "diagnose_setup", "arguments": {}}, config=config)

        payload = response["structuredContent"]
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["api_key_configured"], False)
        self.assertNotIn("api_key", payload)

    def test_api_tools_report_setup_error_when_api_key_missing(self) -> None:
        api_client = FakeApiClient()
        calls = [
            {"name": "search_issuers", "arguments": {"q": "Toyota"}},
            {"name": "get_document_toc", "arguments": {"document_id": "doc_123"}},
        ]

        for params in calls:
            response = call_tool(api_client, params, config=Config(api_key=""))

            payload = response["structuredContent"]
            self.assertTrue(response["isError"])
            self.assertEqual(payload["error"]["code"], "server_setup_error")
            self.assertIn("MOMONGA_SEARCH_API_KEY is required", payload["error"]["message"])
        self.assertEqual(api_client.calls, [])

    def test_search_document_match_does_not_overwrite_cached_section_resource(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {
            "results": [
                {
                    "document_id": "doc_123",
                    "title": "Report",
                    "matches": [
                        {
                            "section_id": "sec_1",
                            "section_title": "Risk",
                            "snippet": "short snippet",
                        }
                    ],
                }
            ]
        }
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            cache_manager.store_document_section(
                "doc_123",
                "sec_1",
                {
                    "section_id": "sec_1",
                    "section_title": "Risk",
                    "character_count": 11,
                    "content": "full body",
                },
            )

            call_tool(
                api_client,
                {"name": "search_documents", "arguments": {"query": "risk"}},
                cache_manager_getter=lambda: cache_manager,
            )
            cached_resource = cache_manager.get_json_resource("momonga://documents/doc_123/sections/sec_1")

            assert cached_resource is not None
            resource_payload = cache_manager.read_json(cached_resource[0])
            self.assertEqual(resource_payload["content"], "full body")
            self.assertNotIn("snippet", resource_payload)

    def test_cache_backed_tools_report_server_setup_error_when_cache_unavailable(self) -> None:
        calls = [
            ("get_document_toc", {"document_id": "doc_123"}),
            ("get_document_content", {"document_id": "doc_123", "section_ids": ["sec_1"]}),
            (
                "search_section_contents",
                {"document_id": "doc_123", "section_id": "sec_1", "query": "risk"},
            ),
            ("get_section_window", {"document_id": "doc_123", "section_id": "sec_1", "offset": 0}),
            (
                "get_document_page_image",
                {"document_id": "doc_123", "page_number": 1, "allow_file_download": True},
            ),
            (
                "get_document_original",
                {"document_id": "doc_123", "original_id": "pdf", "allow_file_download": True},
            ),
        ]
        for tool_name, arguments in calls:
            response = call_tool(FakeApiClient(), {"name": tool_name, "arguments": arguments})
            payload = response["structuredContent"]

            self.assertTrue(response["isError"], msg=tool_name)
            self.assertEqual(payload["error"]["code"], "server_setup_error", msg=tool_name)
            self.assertIsNone(payload["error"]["status"])
            self.assertIn("cache manager is unavailable", payload["error"]["message"])
            self.assertIn("Do not retry", payload["error"]["next_action"])
            self.assertIn("MCP operator", payload["error"]["next_action"])

    def test_get_document_content_allows_full_document_when_section_ids_are_omitted(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {
            "document_id": "doc_123",
            "title": "Report",
            "character_count": 9,
            "content": "full body",
            "content_sections": [{"section_id": "ignored", "content": "ignored"}],
        }
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {"name": "get_document_content", "arguments": {"document_id": "doc_123", "allow_full_document": True}},
                cache_manager_getter=lambda: cache_manager,
            )

            payload = response["structuredContent"]
            cached_section = cache_manager.get_document_section("doc_123", "__mcp_full_document__")

        self.assertEqual(api_client.calls, [("GET", "/documents/doc_123/content", None)])
        self.assertFalse(payload["cache_hit"])
        self.assertEqual(payload["content_sections"][0]["section_id"], "__mcp_full_document__")
        self.assertEqual(payload["content_sections"][0]["section_title"], "Full document")
        self.assertEqual(payload["content_sections"][0]["character_count"], 9)
        self.assertEqual(payload["content_sections"][0]["content"], "full body")
        self.assertIsNotNone(cached_section)

    def test_get_document_content_validates_section_count_and_rejects_offset(self) -> None:
        invalid_calls = [
            ({"document_id": "doc_123"}, "allow_full_document=true is required when section_ids is omitted"),
            ({"document_id": "doc_123", "section_ids": ["sec_1"], "offset": 0}, "unknown arguments: offset"),
            ({"document_id": "doc_123", "section_ids": ["sec_1"] * 6}, "section_ids must contain at most 5 items"),
        ]

        for arguments, expected_message in invalid_calls:
            response = call_tool(FakeApiClient(), {"name": "get_document_content", "arguments": arguments})
            payload = response["structuredContent"]

            self.assertTrue(response["isError"])
            self.assertEqual(payload["error"]["message"], expected_message)

    def test_runtime_limits_reject_large_result_and_section_requests(self) -> None:
        calls = [
            ("list_documents", {"security_codes": ["8058"], "limit": 26}, "limit must be less than or equal to 25"),
            ("search_documents", {"query": "価格転嫁", "top_k": 26}, "top_k must be less than or equal to 25"),
            (
                "get_document_content",
                {"document_id": "doc_123", "section_ids": ["sec_1", "sec_2", "sec_3", "sec_4", "sec_5", "sec_6"]},
                "section_ids must contain at most 5 items",
            ),
        ]

        for name, arguments, expected_message in calls:
            response = call_tool(FakeApiClient(), {"name": name, "arguments": arguments})
            payload = response["structuredContent"]

            self.assertTrue(response["isError"])
            self.assertEqual(payload["error"]["message"], expected_message)

    def test_call_tool_rejects_unknown_arguments(self) -> None:
        response = call_tool(
            FakeApiClient(),
            {"name": "list_documents", "arguments": {"security_codes": ["8058"], "ignored": "x"}},
        )
        payload = response["structuredContent"]

        self.assertTrue(response["isError"])
        self.assertEqual(payload["error"]["message"], "unknown arguments: ignored")

    def test_call_tool_validates_any_of_arguments(self) -> None:
        response = call_tool(FakeApiClient(), {"name": "list_documents", "arguments": {"limit": 10}})
        payload = response["structuredContent"]

        self.assertTrue(response["isError"])
        self.assertEqual(payload["error"]["message"], "one of these argument sets is required: security_codes or timeline_since")

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
        self.assertEqual(response["structuredContent"]["error"]["code"], "content_not_available")
        self.assertIn("See structuredContent.", response["content"][0]["text"])

    def test_call_tool_validates_required_arguments(self) -> None:
        response = call_tool(FakeApiClient(), {"name": "get_document_metadata", "arguments": {}})
        payload = response["structuredContent"]

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

    def test_file_download_tools_require_explicit_flags(self) -> None:
        calls = [
            (
                "get_document_page_image",
                {"document_id": "doc_123", "page_number": 1},
                "allow_file_download is required",
            ),
            (
                "get_document_original",
                {"document_id": "doc_123", "original_id": "pdf", "allow_file_download": False},
                "allow_file_download must be true for file download tools",
            ),
        ]

        for name, arguments, expected_message in calls:
            response = call_tool(FakeApiClient(), {"name": name, "arguments": arguments})
            payload = response["structuredContent"]

            self.assertTrue(response["isError"])
            self.assertEqual(payload["error"]["message"], expected_message)

    def test_get_document_page_image_downloads_and_caches_file(self) -> None:
        api_client = FakeApiClient()
        api_client.binary_response = api_client.binary_response.__class__(
            content=b"jpeg-bytes",
            media_type="image/png",
            filename=None,
        )
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {
                    "name": "get_document_page_image",
                    "arguments": {
                        "document_id": "doc_123",
                        "page_number": 2,
                        "allow_file_download": True,
                    },
                },
                cache_manager_getter=lambda: cache_manager,
            )

            payload = response["structuredContent"]
            cached_page = cache_manager.get_page_image("doc_123", 2)
            downloaded_path = Path(payload["file_path"])
            self.assertTrue(downloaded_path.exists())
            self.assertEqual(downloaded_path.read_bytes(), b"jpeg-bytes")

        self.assertEqual(api_client.calls, [("GET_BINARY", "/documents/doc_123/pages/2/image", None)])
        self.assertFalse(payload["cached"])
        self.assertEqual(payload["page_number"], 2)
        self.assertEqual(payload["media_type"], "image/jpeg")
        self.assertEqual(payload["resource_uri"], "momonga://documents/doc_123/pages/2")
        self.assertNotIn("metadata", payload)
        self.assertIsNotNone(cached_page)

    def test_get_document_original_downloads_and_caches_file(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {
            "document_id": "doc_123",
            "originals": [
                {
                    "original_id": "pdf",
                    "filename": "manifest-report.pdf",
                    "media_type": "application/pdf",
                    "kind": "pdf",
                    "role": "primary",
                    "size_bytes": 1000,
                    "sha256": "not returned in tool metadata",
                }
            ],
        }
        api_client.binary_response = api_client.binary_response.__class__(
            content=b"pdf-bytes",
            media_type="application/octet-stream",
            filename=None,
        )
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {
                    "name": "get_document_original",
                    "arguments": {
                        "document_id": "doc_123",
                        "original_id": "pdf",
                        "allow_file_download": True,
                    },
                },
                cache_manager_getter=lambda: cache_manager,
            )

            payload = response["structuredContent"]
            cached_original = cache_manager.get_original_file("doc_123", "pdf")
            downloaded_path = Path(payload["file_path"])
            self.assertTrue(downloaded_path.exists())
            self.assertEqual(downloaded_path.read_bytes(), b"pdf-bytes")

        self.assertEqual(
            api_client.calls,
            [
                ("GET_BINARY", "/documents/doc_123/originals/pdf", None),
                ("GET", "/documents/doc_123/originals", None),
            ],
        )
        self.assertFalse(payload["cached"])
        self.assertEqual(payload["original_id"], "pdf")
        self.assertEqual(payload["filename"], "manifest-report.pdf")
        self.assertEqual(payload["media_type"], "application/pdf")
        self.assertEqual(payload["resource_uri"], "momonga://documents/doc_123/originals/pdf")
        self.assertNotIn("metadata", payload)
        self.assertIsNotNone(cached_original)

    def test_get_document_original_uses_binary_headers_without_manifest_lookup(self) -> None:
        api_client = FakeApiClient()
        api_client.binary_response = api_client.binary_response.__class__(
            content=b"pdf-bytes",
            media_type="application/pdf",
            filename="header-report.pdf",
        )
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {
                    "name": "get_document_original",
                    "arguments": {
                        "document_id": "doc_123",
                        "original_id": "pdf",
                        "allow_file_download": True,
                    },
                },
                cache_manager_getter=lambda: cache_manager,
            )

            payload = response["structuredContent"]

        self.assertEqual(api_client.calls, [("GET_BINARY", "/documents/doc_123/originals/pdf", None)])
        self.assertFalse(payload["cached"])
        self.assertEqual(payload["filename"], "header-report.pdf")
        self.assertEqual(payload["media_type"], "application/pdf")

    def test_get_document_original_rejects_original_id_not_in_manifest_when_fallback_is_needed(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {"document_id": "doc_123", "originals": [{"original_id": "xbrl"}]}
        api_client.binary_response = api_client.binary_response.__class__(
            content=b"pdf-bytes",
            media_type="application/octet-stream",
            filename=None,
        )
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {
                    "name": "get_document_original",
                    "arguments": {
                        "document_id": "doc_123",
                        "original_id": "pdf",
                        "allow_file_download": True,
                    },
                },
                cache_manager_getter=lambda: cache_manager,
            )

            payload = response["structuredContent"]

        self.assertEqual(
            api_client.calls,
            [
                ("GET_BINARY", "/documents/doc_123/originals/pdf", None),
                ("GET", "/documents/doc_123/originals", None),
            ],
        )
        self.assertTrue(response["isError"])
        self.assertEqual(payload["error"]["message"], "original_id was not returned by list_document_originals")

    def test_get_document_original_requires_manifest_filename_when_fallback_is_needed(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {"document_id": "doc_123", "originals": [{"original_id": "pdf", "media_type": "application/pdf"}]}
        api_client.binary_response = api_client.binary_response.__class__(
            content=b"pdf-bytes",
            media_type="application/octet-stream",
            filename=None,
        )
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))

            response = call_tool(
                api_client,
                {
                    "name": "get_document_original",
                    "arguments": {
                        "document_id": "doc_123",
                        "original_id": "pdf",
                        "allow_file_download": True,
                    },
                },
                cache_manager_getter=lambda: cache_manager,
            )

            payload = response["structuredContent"]

        self.assertEqual(
            api_client.calls,
            [
                ("GET_BINARY", "/documents/doc_123/originals/pdf", None),
                ("GET", "/documents/doc_123/originals", None),
            ],
        )
        self.assertTrue(response["isError"])
        self.assertEqual(payload["error"]["message"], "list_document_originals did not return filename for original_id")

    def test_file_download_cache_hit_avoids_api(self) -> None:
        api_client = FakeApiClient()
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            cache_manager.store_original_file(
                "doc_123",
                "pdf",
                b"cached-pdf",
                filename="cached.pdf",
                media_type="application/pdf",
            )

            response = call_tool(
                api_client,
                {
                    "name": "get_document_original",
                    "arguments": {
                        "document_id": "doc_123",
                        "original_id": "pdf",
                        "allow_file_download": True,
                    },
                },
                cache_manager_getter=lambda: cache_manager,
            )

        payload = response["structuredContent"]
        self.assertEqual(api_client.calls, [])
        self.assertTrue(payload["cached"])
        self.assertEqual(payload["filename"], "cached.pdf")
        self.assertEqual(payload["media_type"], "application/pdf")
        self.assertNotIn("metadata", payload)

    def test_list_originals_does_not_overwrite_downloaded_original_resource(self) -> None:
        api_client = FakeApiClient()
        api_client.response = {
            "document_id": "doc_123",
            "originals": [
                {
                    "original_id": "pdf",
                    "filename": "manifest.pdf",
                    "media_type": "application/pdf",
                }
            ],
        }
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(Path(temp_dir))
            original = cache_manager.store_original_file(
                "doc_123",
                "pdf",
                b"cached-pdf",
                filename="downloaded.pdf",
                media_type="application/pdf",
            )

            call_tool(
                api_client,
                {"name": "list_document_originals", "arguments": {"document_id": "doc_123"}},
                cache_manager_getter=lambda: cache_manager,
            )
            cached_resource = cache_manager.get_json_resource("momonga://documents/doc_123/originals/pdf")

            assert cached_resource is not None
            resource_payload = cache_manager.read_json(cached_resource[0])
            self.assertEqual(resource_payload["file_path"], str(original.path))
            self.assertEqual(resource_payload["filename"], "downloaded.pdf")

    def test_call_tool_returns_model_facing_unknown_tool_error(self) -> None:
        response = call_tool(FakeApiClient(), {"name": "missing_tool", "arguments": {}})
        payload = response["structuredContent"]

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

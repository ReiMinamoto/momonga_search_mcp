from __future__ import annotations

from pathlib import Path
import unittest

from momonga_search_mcp.cache import CachedResource
from momonga_search_mcp.tools.response import get_document_content_response, get_document_toc_response, success_response


class ToolResponseTests(unittest.TestCase):
    def test_list_documents_response_keeps_only_model_facing_fields(self) -> None:
        response = success_response(
            "list_documents",
            {
                "results": [
                    {
                        "document_id": "doc_123",
                        "document_family": "edinet_filing",
                        "title": "Report",
                        "document_type": "yuho",
                        "issuers": [{"security_code": "8058", "name": "三菱商事株式会社"}],
                        "published_at": "2026-05-01T00:00:00Z",
                        "timeline_at": "2026-05-01T00:00:00Z",
                        "timeline_precision": "datetime",
                        "timeline_basis": "official",
                        "first_observed_at": "2026-05-01T00:00:00Z",
                        "content_status": "ready",
                        "character_count": 9000,
                        "page_count": 12,
                        "page_image_count": 0,
                        "reference_url": "https://example.com/report.pdf",
                    }
                ],
                "next_cursor": "cursor_1",
            },
        )

        self.assertEqual(
            response,
            {
                "ok": True,
                "results": [
                    {
                        "document_id": "doc_123",
                        "document_family": "edinet_filing",
                        "title": "Report",
                        "document_type": "yuho",
                        "issuers": [{"security_code": "8058", "name": "三菱商事株式会社"}],
                        "published_at": "2026-05-01T00:00:00Z",
                        "timeline_at": "2026-05-01T00:00:00Z",
                        "timeline_precision": "datetime",
                        "timeline_basis": "official",
                        "first_observed_at": "2026-05-01T00:00:00Z",
                        "content_status": "ready",
                        "character_count": 9000,
                        "reference_url": "https://example.com/report.pdf",
                    }
                ],
                "next_cursor": "cursor_1",
            },
        )

    def test_search_documents_response_trims_matches(self) -> None:
        response = success_response(
            "search_documents",
            {
                "results": [
                    {
                        "document_id": "doc_123",
                        "document_family": "edinet_filing",
                        "title": "Report",
                        "document_type": "yuho",
                        "issuers": [{"security_code": "8058", "name": "三菱商事株式会社"}],
                        "published_at": "2026-05-01T00:00:00Z",
                        "timeline_at": "2026-05-01T00:00:00Z",
                        "content_status": "ready",
                        "character_count": 9000,
                        "reference_url": "https://example.com/report.pdf",
                        "first_observed_at": "2026-05-01T00:00:00Z",
                        "matches": [
                            {
                                "section_id": "sec_1",
                                "section_title": "Risk",
                                "heading_path": ["Business", "Risk"],
                                "character_count": 1200,
                                "score": 9.2,
                                "snippet": "Commodity price risk...",
                                "page_number": 4,
                                "has_visual": True,
                                "internal_extra": "dropped",
                            }
                        ],
                    }
                ]
            },
        )

        self.assertEqual(
            response,
            {
                "ok": True,
                "results": [
                    {
                        "document_id": "doc_123",
                        "document_family": "edinet_filing",
                        "title": "Report",
                        "document_type": "yuho",
                        "issuers": [{"security_code": "8058", "name": "三菱商事株式会社"}],
                        "published_at": "2026-05-01T00:00:00Z",
                        "timeline_at": "2026-05-01T00:00:00Z",
                        "first_observed_at": "2026-05-01T00:00:00Z",
                        "content_status": "ready",
                        "character_count": 9000,
                        "reference_url": "https://example.com/report.pdf",
                        "matches": [
                            {
                                "section_id": "sec_1",
                                "section_title": "Risk",
                                "heading_path": ["Business", "Risk"],
                                "character_count": 1200,
                                "score": 9.2,
                                "snippet": "Commodity price risk...",
                                "page_number": 4,
                                "has_visual": True,
                            }
                        ],
                    }
                ],
            },
        )

    def test_results_response_drops_null_next_cursor(self) -> None:
        response = success_response(
            "list_documents",
            {
                "results": [],
                "next_cursor": None,
            },
        )

        self.assertEqual(response, {"ok": True, "results": []})

    def test_metadata_response_includes_ready_next_action(self) -> None:
        response = success_response(
            "get_document_metadata",
            {
                "document_id": "doc_123",
                "title": "Report",
                "content_status": "ready",
                "reference_url": "https://example.com/report.pdf",
            },
        )

        self.assertEqual(
            response["next_action"],
            {
                "status": "ready",
                "recommended_tools": ["get_document_toc", "get_document_content"],
                "argument_hints": {"document_id": "doc_123"},
            },
        )

    def test_metadata_response_includes_pending_release_next_action(self) -> None:
        response = success_response(
            "get_document_metadata",
            {
                "document_id": "doc_123",
                "title": "Report",
                "content_status": "pending_release",
            },
        )

        self.assertEqual(response["next_action"]["status"], "pending_release")
        self.assertIn("Wait", response["next_action"]["message"])

    def test_metadata_response_includes_external_only_next_action(self) -> None:
        response = success_response(
            "get_document_metadata",
            {
                "document_id": "doc_123",
                "title": "Report",
                "content_status": "external_only",
                "reference_url": "https://example.com/report.pdf",
            },
        )

        self.assertEqual(
            response["next_action"],
            {
                "status": "external_only",
                "message": "Do not retry Momonga content retrieval; inspect the external reference instead.",
                "reference_url": "https://example.com/report.pdf",
            },
        )

    def test_list_page_images_response_returns_available_page_numbers(self) -> None:
        response = success_response(
            "list_document_page_images",
            {
                "document_id": "doc_123",
                "page_count": 17,
                "page_image_count": 9,
                "page_images": [
                    {
                        "page_number": 1,
                        "image_role": "vlm_evidence",
                        "source_route": "vision",
                        "width": 1200,
                    },
                    {"page_number": 5, "image_role": "vlm_evidence"},
                    {"page_number": "dropped"},
                ],
            },
        )

        self.assertEqual(
            response,
            {
                "ok": True,
                "document_id": "doc_123",
                "page_count": 17,
                "page_image_count": 9,
                "page_images": [
                    {"page_number": 1, "source_route": "vision", "image_role": "vlm_evidence"},
                    {"page_number": 5, "image_role": "vlm_evidence"},
                ],
            },
        )

    def test_list_originals_response_drops_sha256(self) -> None:
        response = success_response(
            "list_document_originals",
            {
                "document_id": "doc_123",
                "content_status": "ready",
                "original_available": True,
                "originals": [
                    {
                        "original_id": "pdf",
                        "filename": "report.pdf",
                        "media_type": "application/pdf",
                        "kind": "pdf",
                        "role": "primary",
                        "size_bytes": 1000,
                        "sha256": "not needed in model context",
                    }
                ],
            },
        )

        self.assertEqual(
            response,
            {
                "ok": True,
                "document_id": "doc_123",
                "originals": [
                    {
                        "original_id": "pdf",
                        "filename": "report.pdf",
                        "media_type": "application/pdf",
                        "kind": "pdf",
                        "role": "primary",
                    }
                ],
            },
        )

    def test_list_news_response_returns_title_and_body_without_deprecated_statement(self) -> None:
        response = success_response(
            "list_news",
            {
                "results": [
                    {
                        "news_id": "news_123",
                        "title": "BOJ, policy rate unchanged",
                        "body": "BOJ announced a policy change.",
                        "statement": "BOJ announced a policy change.",
                        "observed_at": "2026-05-01T00:00:00Z",
                        "updated_at": "2026-05-02T00:00:00Z",
                        "related_issuers": [],
                        "references": [{"type": "url", "url": "https://www.boj.or.jp/"}],
                    }
                ],
                "next_cursor": "cursor_1",
            },
        )

        self.assertEqual(
            response,
            {
                "ok": True,
                "results": [
                    {
                        "news_id": "news_123",
                        "title": "BOJ, policy rate unchanged",
                        "body": "BOJ announced a policy change.",
                        "observed_at": "2026-05-01T00:00:00Z",
                        "updated_at": "2026-05-02T00:00:00Z",
                        "related_issuers": [],
                        "references": [{"type": "url", "url": "https://www.boj.or.jp/"}],
                    }
                ],
                "next_cursor": "cursor_1",
            },
        )

    def test_search_news_response_returns_title_and_body_without_statement_and_score(self) -> None:
        response = success_response(
            "search_news",
            {
                "results": [
                    {
                        "news_id": "news_123",
                        "title": "BOJ, policy rate unchanged",
                        "body": "BOJ announced a policy change.",
                        "statement": "BOJ announced a policy change.",
                        "observed_at": "2026-05-01T00:00:00Z",
                        "related_issuers": [],
                        "references": [{"type": "url", "url": "https://www.boj.or.jp/"}],
                        "score": 8.4,
                    }
                ],
            },
        )

        self.assertEqual(
            response,
            {
                "ok": True,
                "results": [
                    {
                        "news_id": "news_123",
                        "title": "BOJ, policy rate unchanged",
                        "body": "BOJ announced a policy change.",
                        "observed_at": "2026-05-01T00:00:00Z",
                        "related_issuers": [],
                        "references": [{"type": "url", "url": "https://www.boj.or.jp/"}],
                    }
                ],
            },
        )

    def test_content_response_uses_content_sections_and_drops_body_when_requested(self) -> None:
        response = get_document_content_response(
            "doc_123",
            [
                (
                    {
                        "section_id": "sec_1",
                        "section_title": "Risk",
                        "character_count": 100,
                        "content": "body",
                        "internal_extra": "dropped",
                    },
                    "momonga://documents/doc_123/sections/sec_1",
                )
            ],
            cache_hit=True,
            cached_sections=True,
            return_content=False,
        )

        self.assertEqual(
            response,
            {
                "ok": True,
                "document_id": "doc_123",
                "content_sections": [
                    {
                        "section_id": "sec_1",
                        "section_title": "Risk",
                        "character_count": 100,
                        "resource_uri": "momonga://documents/doc_123/sections/sec_1",
                        "cached": True,
                    }
                ],
                "max_inline_characters_per_call": 20000,
                "cache_hit": True,
            },
        )

    def test_content_response_returns_inline_for_small_section(self) -> None:
        response = get_document_content_response(
            "doc_123",
            [
                (
                    {
                        "section_id": "sec_1",
                        "section_title": "Risk",
                        "character_count": 10,
                        "content": "0123456789",
                    },
                    "momonga://documents/doc_123/sections/sec_1",
                )
            ],
            cache_hit=False,
            cached_sections=False,
            return_content=True,
        )

        self.assertEqual(
            response["content_sections"][0],
            {
                "section_id": "sec_1",
                "section_title": "Risk",
                "character_count": 10,
                "content": "0123456789",
                "content_mode": "inline",
                "resource_uri": "momonga://documents/doc_123/sections/sec_1",
                "cached": False,
            },
        )

    def test_content_response_includes_requested_and_missing_section_ids(self) -> None:
        response = get_document_content_response(
            "doc_123",
            [
                (
                    {
                        "section_id": "sec_1",
                        "section_title": "Risk",
                        "character_count": 4,
                        "content": "body",
                    },
                    "momonga://documents/doc_123/sections/sec_1",
                )
            ],
            cache_hit=False,
            cached_sections=False,
            return_content=True,
            requested_section_ids=["sec_1", "sec_missing"],
            missing_section_ids=["sec_missing"],
        )

        self.assertEqual(response["requested_section_ids"], ["sec_1", "sec_missing"])
        self.assertEqual(response["missing_section_ids"], ["sec_missing"])

    def test_content_response_returns_manifest_for_section_over_budget(self) -> None:
        response = get_document_content_response(
            "doc_123",
            [
                (
                    {
                        "section_id": "sec_1",
                        "section_title": "Risk",
                        "character_count": 20001,
                        "content": "x" * 20001,
                    },
                    "momonga://documents/doc_123/sections/sec_1",
                )
            ],
            cache_hit=False,
            cached_sections=False,
            return_content=True,
        )

        self.assertEqual(
            response["content_sections"][0],
            {
                "section_id": "sec_1",
                "section_title": "Risk",
                "character_count": 20001,
                "content_mode": "manifest",
                "reason": "inline_budget_exceeded",
                "content_available_in_cache": True,
                "recommended_tools": ["search_section_contents", "get_section_window"],
                "next_action": {
                    "tool": "search_section_contents",
                    "argument_hints": {
                        "document_id": "doc_123",
                        "section_id": "sec_1",
                        "query": "Search terms for the needed evidence in this section.",
                    },
                    "fallback_tool": "get_section_window",
                },
                "resource_uri": "momonga://documents/doc_123/sections/sec_1",
                "source_resource_uri": "momonga://documents/doc_123/sections/sec_1",
                "cached": False,
            },
        )
        self.assertNotIn("content", response["content_sections"][0])

    def test_content_response_inlines_full_document_within_budget(self) -> None:
        response = get_document_content_response(
            "doc_123",
            [
                (
                    {
                        "section_id": "__mcp_full_document__",
                        "section_title": "Full document",
                        "character_count": 9000,
                        "content": "x" * 9000,
                    },
                    "momonga://documents/doc_123/sections/__mcp_full_document__",
                )
            ],
            cache_hit=False,
            cached_sections=False,
            return_content=True,
        )

        section = response["content_sections"][0]
        self.assertEqual(section["content_mode"], "inline")
        self.assertEqual(section["content"], "x" * 9000)

    def test_content_response_returns_manifest_for_full_document_over_budget(self) -> None:
        response = get_document_content_response(
            "doc_123",
            [
                (
                    {
                        "section_id": "__mcp_full_document__",
                        "section_title": "Full document",
                        "character_count": 20001,
                        "content": "x" * 20001,
                    },
                    "momonga://documents/doc_123/sections/__mcp_full_document__",
                )
            ],
            cache_hit=False,
            cached_sections=False,
            return_content=True,
        )

        section = response["content_sections"][0]
        self.assertEqual(section["content_mode"], "manifest")
        self.assertEqual(section["reason"], "inline_budget_exceeded")
        self.assertNotIn("content", section)

    def test_content_response_inlines_multiple_sections_within_budget(self) -> None:
        response = get_document_content_response(
            "doc_123",
            [
                (
                    {
                        "section_id": "sec_1",
                        "character_count": 4,
                        "content": "abcd",
                    },
                    "momonga://documents/doc_123/sections/sec_1",
                ),
                (
                    {
                        "section_id": "sec_2",
                        "character_count": 4,
                        "content": "efgh",
                    },
                    "momonga://documents/doc_123/sections/sec_2",
                ),
            ],
            cache_hit=False,
            cached_sections=False,
            return_content=True,
        )

        self.assertEqual(response["content_sections"][0]["content"], "abcd")
        self.assertEqual(response["content_sections"][0]["content_mode"], "inline")
        self.assertEqual(response["content_sections"][1]["content"], "efgh")
        self.assertEqual(response["content_sections"][1]["content_mode"], "inline")

    def test_content_response_returns_manifest_for_large_section_after_small_sections(self) -> None:
        response = get_document_content_response(
            "doc_123",
            [
                (
                    {
                        "section_id": "sec_1",
                        "character_count": 4,
                        "content": "abcd",
                    },
                    "momonga://documents/doc_123/sections/sec_1",
                ),
                (
                    {
                        "section_id": "sec_2",
                        "character_count": 20001,
                        "content": "x" * 20001,
                    },
                    "momonga://documents/doc_123/sections/sec_2",
                ),
            ],
            cache_hit=False,
            cached_sections=False,
            return_content=True,
        )

        manifest_section = response["content_sections"][1]
        self.assertEqual(
            manifest_section,
            {
                "section_id": "sec_2",
                "character_count": 20001,
                "content_mode": "manifest",
                "reason": "inline_budget_exceeded",
                "content_available_in_cache": True,
                "recommended_tools": ["search_section_contents", "get_section_window"],
                "next_action": {
                    "tool": "search_section_contents",
                    "argument_hints": {
                        "document_id": "doc_123",
                        "section_id": "sec_2",
                        "query": "Search terms for the needed evidence in this section.",
                    },
                    "fallback_tool": "get_section_window",
                },
                "resource_uri": "momonga://documents/doc_123/sections/sec_2",
                "source_resource_uri": "momonga://documents/doc_123/sections/sec_2",
                "cached": False,
            },
        )
        self.assertNotIn("content", manifest_section)
        self.assertNotIn("truncated", manifest_section)
        self.assertNotIn("next_offset", manifest_section)

    def test_content_response_shares_inline_budget_across_sections_in_request_order(self) -> None:
        response = get_document_content_response(
            "doc_123",
            [
                (
                    {"section_id": "sec_1", "character_count": 12000, "content": "a" * 12000},
                    "momonga://documents/doc_123/sections/sec_1",
                ),
                (
                    {"section_id": "sec_2", "character_count": 12000, "content": "b" * 12000},
                    "momonga://documents/doc_123/sections/sec_2",
                ),
                (
                    {"section_id": "sec_3", "character_count": 8000, "content": "c" * 8000},
                    "momonga://documents/doc_123/sections/sec_3",
                ),
            ],
            cache_hit=False,
            cached_sections=False,
            return_content=True,
        )

        sections = response["content_sections"]
        self.assertEqual([section["content_mode"] for section in sections], ["inline", "manifest", "inline"])
        self.assertEqual(sections[1]["reason"], "inline_budget_exceeded")
        self.assertNotIn("content", sections[1])
        self.assertEqual(sections[2]["content"], "c" * 8000)

    def test_get_document_toc_returns_sections_for_small_toc_by_default(self) -> None:
        response = get_document_toc_response(
            {
                "document_id": "doc_123",
                "title": "Report",
                "content_status": "ready",
                "toc": [
                    {
                        "section_id": "sec_1",
                        "section_title": "Risk",
                        "heading_path": ["Business", "Risk"],
                        "character_count": 100,
                        "page_number": 2,
                        "internal_extra": "dropped",
                    },
                    {
                        "section_id": "sec_2",
                        "section_title": "MD&A",
                        "heading_path": ["Business", "MD&A"],
                        "character_count": 150,
                        "page_number": 4,
                    },
                ],
            },
            CachedResource(resource_uri="momonga://documents/doc_123/toc", path=Path("toc.json")),
            cache_hit=False,
        )

        self.assertEqual(
            response,
            {
                "ok": True,
                "document_id": "doc_123",
                "toc_mode": "sections",
                "path_prefix": [],
                "max_depth": 2,
                "include_sections": False,
                "selection_policy": {
                    "mode": "auto",
                    "reason": "toc_is_small",
                    "max_direct_toc_sections": 50,
                    "selected_toc_entry_count": 2,
                },
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
                        "section_title": "MD&A",
                        "heading_path": ["Business", "MD&A"],
                        "character_count": 150,
                        "page_number": 4,
                    },
                ],
                "resource_uri": "momonga://documents/doc_123/toc",
                "cache_hit": False,
            },
        )

    def test_get_document_toc_returns_outline_for_large_toc_by_default(self) -> None:
        groups = [
            ("Business Overview", range(1, 10)),
            ("Operating Results", range(10, 31)),
            ("Governance", range(31, 43)),
            ("Financial Statements", range(43, 52)),
        ]
        toc = [
            {
                "section_id": f"sec_{index}",
                "section_title": f"Section {index}",
                "heading_path": ["Business", group_title, f"Section {index}"],
                "character_count": 10,
                "page_number": index,
            }
            for group_title, indexes in groups
            for index in indexes
        ]

        response = get_document_toc_response(
            {
                "document_id": "doc_123",
                "toc": toc,
            },
            CachedResource(resource_uri="momonga://documents/doc_123/toc", path=Path("toc.json")),
            cache_hit=False,
        )

        self.assertEqual(response["toc_mode"], "outline")
        self.assertEqual(
            response["selection_policy"],
            {
                "mode": "auto",
                "reason": "toc_is_large",
                "max_direct_toc_sections": 50,
                "selected_toc_entry_count": 51,
            },
        )
        self.assertEqual(
            response["next_action_template"],
            {
                "tool": "get_document_toc",
                "argument_hints": {
                    "document_id": "doc_123",
                    "path_prefix": "Choose a relevant heading_path from the returned toc outline.",
                    "include_sections": True,
                },
            },
        )
        self.assertEqual(
            response["toc"],
            [
                {
                    "heading_title": "Business",
                    "heading_path": ["Business"],
                    "section_count": 51,
                    "total_character_count": 510,
                    "page_range": {"start": 1, "end": 51},
                    "has_children": True,
                    "children": [
                        {
                            "heading_title": "Business Overview",
                            "heading_path": ["Business", "Business Overview"],
                            "section_count": 9,
                            "total_character_count": 90,
                            "page_range": {"start": 1, "end": 9},
                            "has_children": True,
                        },
                        {
                            "heading_title": "Operating Results",
                            "heading_path": ["Business", "Operating Results"],
                            "section_count": 21,
                            "total_character_count": 210,
                            "page_range": {"start": 10, "end": 30},
                            "has_children": True,
                        },
                        {
                            "heading_title": "Governance",
                            "heading_path": ["Business", "Governance"],
                            "section_count": 12,
                            "total_character_count": 120,
                            "page_range": {"start": 31, "end": 42},
                            "has_children": True,
                        },
                        {
                            "heading_title": "Financial Statements",
                            "heading_path": ["Business", "Financial Statements"],
                            "section_count": 9,
                            "total_character_count": 90,
                            "page_range": {"start": 43, "end": 51},
                            "has_children": True,
                        },
                    ],
                }
            ],
        )

    def test_get_document_toc_filters_by_path_prefix(self) -> None:
        response = get_document_toc_response(
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
            CachedResource(resource_uri="momonga://documents/doc_123/toc", path=Path("toc.json")),
            cache_hit=True,
            path_prefix=["Business"],
        )

        self.assertEqual(response["toc_mode"], "subtree")
        self.assertEqual(response["selection_policy"]["reason"], "path_prefix_requested")
        self.assertNotIn("next_action_template", response)
        self.assertEqual(response["path_prefix"], ["Business"])
        self.assertEqual(len(response["toc"]), 1)
        self.assertEqual(response["toc"][0]["heading_path"], ["Business"])
        self.assertEqual(response["toc"][0]["section_count"], 1)

    def test_get_document_toc_include_sections_returns_leaf_sections(self) -> None:
        response = get_document_toc_response(
            {
                "document_id": "doc_123",
                "toc": [
                    {
                        "section_id": "sec_1",
                        "section_title": "Risk",
                        "heading_path": ["Business", "Risk"],
                        "character_count": 100,
                        "page_number": 2,
                        "internal_extra": "dropped",
                    }
                ],
            },
            CachedResource(resource_uri="momonga://documents/doc_123/toc", path=Path("toc.json")),
            cache_hit=True,
            max_depth=2,
            include_sections=True,
        )

        self.assertEqual(response["toc_mode"], "sections")
        self.assertEqual(response["toc"][0]["section_id"], "sec_1")
        self.assertNotIn("internal_extra", response["toc"][0])


if __name__ == "__main__":
    unittest.main()

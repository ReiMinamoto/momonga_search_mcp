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
                        "first_observed_at": "2026-05-01T00:00:00Z",
                        "content_status": "ready",
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
                        "timeline_at": "2026-05-01T00:00:00Z",
                        "content_status": "ready",
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
                        "timeline_at": "2026-05-01T00:00:00Z",
                        "content_status": "ready",
                        "reference_url": "https://example.com/report.pdf",
                        "first_observed_at": "dropped",
                        "matches": [
                            {
                                "section_id": "sec_1",
                                "section_title": "Risk",
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
                        "timeline_at": "2026-05-01T00:00:00Z",
                        "content_status": "ready",
                        "reference_url": "https://example.com/report.pdf",
                        "matches": [
                            {
                                "section_id": "sec_1",
                                "section_title": "Risk",
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
                "page_images": [1, 5],
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
                        "credit_cost": 8,
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
                        "credit_cost": 8,
                    }
                ],
            },
        )

    def test_list_news_response_keeps_macro_tags_and_drops_score(self) -> None:
        response = success_response(
            "list_news",
            {
                "results": [
                    {
                        "news_id": "news_123",
                        "parent_news_id": "dropped",
                        "statement": "BOJ announced a policy change.",
                        "observed_at": "2026-05-01T00:00:00Z",
                        "related_issuers": [],
                        "macro_tags": ["Monetary Policy"],
                        "references": [],
                        "score": 8.4,
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
                        "statement": "BOJ announced a policy change.",
                        "observed_at": "2026-05-01T00:00:00Z",
                        "related_issuers": [],
                        "macro_tags": ["Monetary Policy"],
                        "references": [],
                    }
                ],
                "next_cursor": "cursor_1",
            },
        )

    def test_search_news_response_keeps_macro_tags_and_drops_score(self) -> None:
        response = success_response(
            "search_news",
            {
                "results": [
                    {
                        "news_id": "news_123",
                        "statement": "BOJ announced a policy change.",
                        "observed_at": "2026-05-01T00:00:00Z",
                        "related_issuers": [],
                        "macro_tags": ["Monetary Policy"],
                        "references": [],
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
                        "statement": "BOJ announced a policy change.",
                        "observed_at": "2026-05-01T00:00:00Z",
                        "related_issuers": [],
                        "macro_tags": ["Monetary Policy"],
                        "references": [],
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
            max_chars=8000,
            offset=0,
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
                "max_characters": 8000,
                "character_limit_reached": False,
                "cache_hit": True,
            },
        )

    def test_content_response_truncates_content_with_next_offset(self) -> None:
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
            max_chars=4,
            offset=3,
        )

        self.assertEqual(
            response["content_sections"][0],
            {
                "section_id": "sec_1",
                "section_title": "Risk",
                "character_count": 10,
                "content": "3456",
                "truncated": True,
                "offset": 3,
                "next_offset": 7,
                "resource_uri": "momonga://documents/doc_123/sections/sec_1",
                "cached": False,
            },
        )

    def test_content_response_applies_character_limit_across_sections(self) -> None:
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
            max_chars=6,
            offset=0,
        )

        self.assertEqual(response["content_sections"][0]["content"], "abcd")
        self.assertEqual(response["content_sections"][1]["content"], "ef")
        self.assertTrue(response["content_sections"][1]["truncated"])
        self.assertEqual(response["max_characters"], 6)
        self.assertTrue(response["character_limit_reached"])

    def test_content_response_marks_unstarted_sections_omitted_after_character_limit(self) -> None:
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
            max_chars=4,
            offset=0,
        )

        omitted_section = response["content_sections"][1]
        self.assertEqual(
            omitted_section,
            {
                "section_id": "sec_2",
                "character_count": 4,
                "content_omitted": True,
                "omitted_reason": "character_limit_reached",
                "offset": 0,
                "resource_uri": "momonga://documents/doc_123/sections/sec_2",
                "cached": False,
            },
        )
        self.assertNotIn("content", omitted_section)
        self.assertNotIn("truncated", omitted_section)
        self.assertNotIn("next_offset", omitted_section)
        self.assertTrue(response["character_limit_reached"])

    def test_toc_response_keeps_only_toc_fields(self) -> None:
        response = get_document_toc_response(
            {
                "document_id": "doc_123",
                "title": "Report",
                "content_status": "ready",
                "toc": [
                    {
                        "section_id": "sec_1",
                        "section_title": "Risk",
                        "heading_path": ["Risk"],
                        "character_count": 100,
                        "page_number": 2,
                        "internal_extra": "dropped",
                    }
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
                "toc": [
                    {
                        "section_id": "sec_1",
                        "section_title": "Risk",
                        "heading_path": ["Risk"],
                        "character_count": 100,
                        "page_number": 2,
                    }
                ],
                "resource_uri": "momonga://documents/doc_123/toc",
                "cache_hit": False,
            },
        )


if __name__ == "__main__":
    unittest.main()

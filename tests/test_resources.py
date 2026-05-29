from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from momonga_search_mcp.cache import CacheManager
from momonga_search_mcp.resources import read_momonga_resource


class MomongaResourceReadTests(unittest.TestCase):
    def test_section_resource_read_returns_manifest_without_content(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(cache_dir=Path(temp_dir))
            resource = cache_manager.store_document_section(
                "doc_123",
                "sec_1",
                {
                    "section_id": "sec_1",
                    "section_title": "Risk",
                    "heading_path": ["Business", "Risk"],
                    "character_count": 4,
                    "content": "body",
                    "raw_content": "raw body",
                },
            )

            text, mime_type = read_momonga_resource(cache_manager, resource.resource_uri)

        payload = json.loads(text)
        self.assertEqual(mime_type, "application/json")
        self.assertEqual(
            payload,
            {
                "document_id": "doc_123",
                "section_id": "sec_1",
                "section_title": "Risk",
                "heading_path": ["Business", "Risk"],
                "character_count": 4,
                "content_available_in_cache": True,
                "read_policy": (
                    "Use search_section_contents or get_section_window; full cached content is not returned by resources/read."
                ),
                "source_resource_uri": "momonga://documents/doc_123/sections/sec_1",
            },
        )
        self.assertNotIn("content", payload)
        self.assertNotIn("raw_content", payload)

    def test_toc_resource_read_returns_compact_manifest(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(cache_dir=Path(temp_dir))
            resource = cache_manager.store_document_toc(
                "doc_123",
                {
                    "document_id": "doc_123",
                    "toc": [
                        {"section_id": "sec_1", "section_title": "Risk"},
                        {"section_id": "sec_2", "section_title": "MD&A"},
                    ],
                },
            )

            text, _mime_type = read_momonga_resource(cache_manager, resource.resource_uri)

        payload = json.loads(text)
        self.assertEqual(payload["document_id"], "doc_123")
        self.assertEqual(payload["resource_type"], "toc")
        self.assertEqual(payload["toc_entry_count"], 2)
        self.assertEqual(payload["source_resource_uri"], "momonga://documents/doc_123/toc")
        self.assertNotIn("toc", payload)

    def test_page_resource_read_returns_metadata_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(cache_dir=Path(temp_dir))
            resource = cache_manager.store_page_image("doc_123", 3, b"image", metadata={"width": 100})

            text, _mime_type = read_momonga_resource(cache_manager, resource.resource_uri)

        payload = json.loads(text)
        self.assertEqual(payload["resource_type"], "page")
        self.assertEqual(payload["document_id"], "doc_123")
        self.assertEqual(payload["page_number"], 3)
        self.assertEqual(payload["width"], 100)
        self.assertEqual(payload["source_resource_uri"], "momonga://documents/doc_123/pages/3")

    def test_original_resource_read_returns_metadata_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(cache_dir=Path(temp_dir))
            resource = cache_manager.store_original_file(
                "doc_123",
                "orig_1",
                b"original",
                filename="filing.pdf",
                media_type="application/pdf",
                metadata={"size_bytes": 8},
            )

            text, _mime_type = read_momonga_resource(cache_manager, resource.resource_uri)

        payload = json.loads(text)
        self.assertEqual(payload["resource_type"], "original")
        self.assertEqual(payload["document_id"], "doc_123")
        self.assertEqual(payload["original_id"], "orig_1")
        self.assertEqual(payload["filename"], "filing.pdf")
        self.assertEqual(payload["size_bytes"], 8)
        self.assertEqual(payload["source_resource_uri"], "momonga://documents/doc_123/originals/orig_1")


if __name__ == "__main__":
    unittest.main()

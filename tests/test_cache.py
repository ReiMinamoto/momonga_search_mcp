from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from momonga_search_mcp.cache import CacheManager


class CacheManagerTests(unittest.TestCase):
    def test_initializes_sqlite_schema(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))

            with sqlite3.connect(cache.db_path) as connection:
                table_names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

        self.assertIn("document_tocs", table_names)
        self.assertIn("document_sections", table_names)
        self.assertIn("document_page_images", table_names)
        self.assertIn("document_originals", table_names)
        self.assertIn("json_resources", table_names)
        self.assertIn("api_calls", table_names)
        self.assertIn("credit_sessions", table_names)
        self.assertNotIn("document_metadata", table_names)
        self.assertNotIn("news", table_names)
        self.assertNotIn("issuers", table_names)

    def test_stores_and_lists_json_resources(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))

            resource = cache.store_document_toc("doc_123", {"document_id": "doc_123", "toc": []})
            cached_resource = cache.get_json_resource("momonga://documents/doc_123/toc")
            resources = cache.list_json_resources()

            self.assertEqual(resource.resource_uri, "momonga://documents/doc_123/toc")
            self.assertEqual(resources[0]["uri"], "momonga://documents/doc_123/toc")
            self.assertEqual(resources[0]["mimeType"], "application/json")
            assert cached_resource is not None
            self.assertEqual(cache.read_json(cached_resource[0])["document_id"], "doc_123")

    def test_lists_json_resources_with_filters(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))
            cache.store_document_toc("doc_123", {"document_id": "doc_123", "toc": []})
            cache.store_document_section("doc_123", "sec_1", {"section_id": "sec_1"})
            cache.store_document_section("doc_456", "sec_2", {"section_id": "sec_2"})

            resources = cache.list_json_resources(document_id="doc_123", resource_type="section")

        self.assertEqual(
            [resource["uri"] for resource in resources],
            ["momonga://documents/doc_123/sections/sec_1"],
        )

    def test_resource_tables_are_path_indexes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))

            with sqlite3.connect(cache.db_path) as connection:
                toc_columns = {row[1] for row in connection.execute("PRAGMA table_info(document_tocs)")}
                section_columns = {row[1] for row in connection.execute("PRAGMA table_info(document_sections)")}
                page_columns = {row[1] for row in connection.execute("PRAGMA table_info(document_page_images)")}
                original_columns = {row[1] for row in connection.execute("PRAGMA table_info(document_originals)")}

        self.assertEqual(toc_columns, {"document_id", "resource_uri", "toc_path", "cached_at"})
        self.assertEqual(section_columns, {"document_id", "section_id", "resource_uri", "content_path", "cached_at"})
        self.assertEqual(
            page_columns,
            {"document_id", "page_number", "resource_uri", "file_path", "metadata_path", "cached_at"},
        )
        self.assertEqual(
            original_columns,
            {"document_id", "original_id", "resource_uri", "file_path", "metadata_path", "cached_at"},
        )

    def test_stores_document_toc(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))

            resource = cache.store_document_toc("doc_123", {"toc": [{"section_id": "sec_1"}]})
            cached_toc = cache.get_document_toc("doc_123")

            self.assertEqual(resource.resource_uri, "momonga://documents/doc_123/toc")
            self.assertTrue(resource.path.exists())
            assert cached_toc is not None
            self.assertEqual(cached_toc.resource_uri, resource.resource_uri)
            self.assertEqual(cached_toc.path, resource.path)
            self.assertEqual(cache.read_json(cached_toc), {"toc": [{"section_id": "sec_1"}]})

    def test_stores_and_reads_document_section(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))

            resource = cache.store_document_section(
                "doc_123",
                "sec_456",
                {
                    "section_id": "sec_456",
                    "heading_path": ["Business", "Risk"],
                    "content": "Material cost increased.",
                },
            )
            cached_section = cache.get_document_section("doc_123", "sec_456")

            self.assertEqual(resource.resource_uri, "momonga://documents/doc_123/sections/sec_456")
            self.assertTrue(resource.path.exists())
            assert cached_section is not None
            self.assertEqual(cached_section.resource_uri, resource.resource_uri)
            self.assertEqual(cached_section.path, resource.path)

    def test_stores_page_image_and_original_file_under_cache_dir(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))

            page = cache.store_page_image("doc_123", 2, b"image-bytes")
            original = cache.store_original_file(
                "doc_123",
                "orig_1",
                b"pdf-bytes",
                filename="report.pdf",
                media_type="application/pdf",
            )
            cached_page = cache.get_page_image("doc_123", 2)
            cached_original = cache.get_original_file("doc_123", "orig_1")
            page_resource = cache.get_json_resource("momonga://documents/doc_123/pages/2")
            original_resource = cache.get_json_resource("momonga://documents/doc_123/originals/orig_1")

            self.assertEqual(page.resource_uri, "momonga://documents/doc_123/pages/2")
            self.assertEqual(page.path.read_bytes(), b"image-bytes")
            self.assertEqual(original.resource_uri, "momonga://documents/doc_123/originals/orig_1")
            self.assertEqual(original.path.read_bytes(), b"pdf-bytes")
            assert cached_page is not None
            assert cached_original is not None
            self.assertEqual(cached_page.path.read_bytes(), b"image-bytes")
            self.assertEqual(cached_original.path.read_bytes(), b"pdf-bytes")
            self.assertEqual(json.loads(page.path.with_suffix(".json").read_text(encoding="utf-8"))["media_type"], "image/jpeg")
            self.assertEqual(
                json.loads(original.path.with_name("metadata.json").read_text(encoding="utf-8"))["filename"],
                "report.pdf",
            )
            assert page_resource is not None
            assert original_resource is not None
            self.assertEqual(cache.read_json(page_resource[0])["file_path"], str(page.path))
            self.assertEqual(cache.read_json(original_resource[0])["file_path"], str(original.path))

    def test_generates_encoded_resource_uri_segments(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))

            uri = cache.document_section_uri("doc 123", "sec 456")

        self.assertEqual(uri, "momonga://documents/doc%20123/sections/sec%20456")

    def test_rejects_path_traversal_segments(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))

            with self.assertRaisesRegex(ValueError, "path segment"):
                cache.store_document_toc("../secret", {"toc": []})

    def test_sanitizes_original_filename(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))

            resource = cache.store_original_file(
                "doc_123",
                "orig_1",
                b"pdf-bytes",
                filename="../report.pdf",
                media_type="application/pdf",
            )

            self.assertEqual(resource.path.name, ".._report.pdf")
            self.assertEqual(resource.path.read_bytes(), b"pdf-bytes")

    def test_returns_none_for_cache_misses(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))

            self.assertIsNone(cache.get_document_toc("missing"))
            self.assertIsNone(cache.get_document_section("missing", "sec_missing"))
            self.assertIsNone(cache.get_page_image("missing", 1))
            self.assertIsNone(cache.get_original_file("missing", "orig_missing"))


if __name__ == "__main__":
    unittest.main()

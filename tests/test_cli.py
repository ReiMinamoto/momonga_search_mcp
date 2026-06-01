from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from momonga_search_mcp.cache import CacheManager
from momonga_search_mcp.cli import _resolve_cache_dir, main
from momonga_search_mcp.config import default_cache_dir


class CliTests(unittest.TestCase):
    def test_cache_dir_prefers_explicit_argument(self) -> None:
        with patch.dict("os.environ", {"MOMONGA_SEARCH_MCP_CACHE_DIR": "/tmp/new-cache"}, clear=True):
            cache_dir = _resolve_cache_dir(Path("/tmp/explicit-cache"))

        self.assertEqual(cache_dir, Path("/tmp/explicit-cache"))

    def test_cache_dir_uses_current_env(self) -> None:
        with patch.dict("os.environ", {"MOMONGA_SEARCH_MCP_CACHE_DIR": "/tmp/new-cache"}, clear=True):
            cache_dir = _resolve_cache_dir(None)

        self.assertEqual(cache_dir, Path("/tmp/new-cache"))

    def test_cache_dir_ignores_legacy_env(self) -> None:
        with patch.dict("os.environ", {"MOMONGA_MCP_CACHE_DIR": "/tmp/legacy-cache"}, clear=True):
            cache_dir = _resolve_cache_dir(None)

        self.assertEqual(cache_dir, default_cache_dir())

    def test_clear_command_deletes_cached_resources_and_reports(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(Path(temp_dir))
            cache.store_document_toc("doc_1", {"document_id": "doc_1", "toc": []})
            cache.store_document_section("doc_1", "sec_1", {"section_id": "sec_1", "content": "body"})

            argv = ["momonga-search-mcp-cache", "--cache-dir", temp_dir, "clear", "--document-id", "doc_1"]
            out = StringIO()
            with patch.object(sys, "argv", argv), redirect_stdout(out):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            self.assertIn("Deleted 2 cached resource(s)", out.getvalue())
            self.assertIn(temp_dir, out.getvalue())
            self.assertIsNone(CacheManager(Path(temp_dir)).get_document_toc("doc_1"))
            self.assertIsNone(CacheManager(Path(temp_dir)).get_document_section("doc_1", "sec_1"))

    def test_clear_command_filters_by_resource_type(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(Path(temp_dir))
            cache.store_document_toc("doc_1", {"document_id": "doc_1", "toc": []})
            cache.store_document_section("doc_1", "sec_1", {"section_id": "sec_1", "content": "body"})

            argv = ["momonga-search-mcp-cache", "--cache-dir", temp_dir, "clear", "--resource-type", "section"]
            out = StringIO()
            with patch.object(sys, "argv", argv), redirect_stdout(out):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            self.assertIn("Deleted 1 cached resource(s)", out.getvalue())
            self.assertIsNotNone(CacheManager(Path(temp_dir)).get_document_toc("doc_1"))
            self.assertIsNone(CacheManager(Path(temp_dir)).get_document_section("doc_1", "sec_1"))


if __name__ == "__main__":
    unittest.main()

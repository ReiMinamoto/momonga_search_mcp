from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from momonga_search_mcp.cli import _resolve_cache_dir
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


if __name__ == "__main__":
    unittest.main()

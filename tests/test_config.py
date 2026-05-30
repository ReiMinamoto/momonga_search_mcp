from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from momonga_search_mcp.config import (
    API_TIMEOUT_SECONDS,
    BYTES_PER_GB,
    DEFAULT_CACHE_MAX_BYTES,
    Config,
    ConfigError,
    default_cache_dir,
    resolve_cache_dir,
)


class ConfigTests(unittest.TestCase):
    def test_allows_missing_api_key_for_diagnose_setup(self) -> None:
        config = Config.from_env({})

        self.assertEqual(config.api_key, "")

    def test_loads_defaults_from_env(self) -> None:
        config = Config.from_env({"MOMONGA_SEARCH_API_KEY": "ms_test_xxx"})

        self.assertEqual(config.api_key, "ms_test_xxx")
        self.assertEqual(config.base_url, "https://api.momongasearch.com/v1")
        self.assertEqual(config.api_timeout_seconds, API_TIMEOUT_SECONDS)
        self.assertEqual(config.cache_max_bytes, DEFAULT_CACHE_MAX_BYTES)

    def test_loads_overrides_from_env(self) -> None:
        config = Config.from_env(
            {
                "MOMONGA_SEARCH_API_KEY": "ms_test_xxx",
                "MOMONGA_BASE_URL": "https://example.com/api/",
                "MOMONGA_SEARCH_MCP_CACHE_DIR": "/tmp/momonga-cache",
                "MOMONGA_SEARCH_MCP_CACHE_MAX_GB": "2",
                "MOMONGA_MCP_LOG_LEVEL": "debug",
            }
        )

        self.assertEqual(config.base_url, "https://example.com/api")
        self.assertEqual(config.cache_dir, Path("/tmp/momonga-cache"))
        self.assertEqual(config.cache_max_bytes, 2 * BYTES_PER_GB)
        self.assertEqual(config.log_level, "DEBUG")

    def test_loads_fractional_cache_max_gb(self) -> None:
        config = Config.from_env(
            {
                "MOMONGA_SEARCH_API_KEY": "ms_test_xxx",
                "MOMONGA_SEARCH_MCP_CACHE_MAX_GB": "0.5",
            }
        )

        self.assertEqual(config.cache_max_bytes, 500_000_000)

    def test_ignores_old_cache_dir_env(self) -> None:
        config = Config.from_env(
            {
                "MOMONGA_SEARCH_API_KEY": "ms_test_xxx",
                "MOMONGA_MCP_CACHE_DIR": "/tmp/legacy-cache",
            }
        )

        self.assertEqual(config.cache_dir, default_cache_dir())

    def test_resolves_cache_dir_from_xdg_cache_home(self) -> None:
        with patch.dict("os.environ", {"XDG_CACHE_HOME": "/tmp/xdg-cache"}, clear=True):
            cache_dir = resolve_cache_dir({})

        self.assertEqual(cache_dir, Path("/tmp/xdg-cache/momonga-search-mcp"))

    def test_ignores_relative_xdg_cache_home(self) -> None:
        with patch.dict("os.environ", {"XDG_CACHE_HOME": "relative-cache"}, clear=True):
            cache_dir = resolve_cache_dir({})
            expected_cache_dir = default_cache_dir()

        self.assertEqual(cache_dir, expected_cache_dir)

    def test_rejects_relative_cache_dir_override(self) -> None:
        with self.assertRaisesRegex(ConfigError, "MOMONGA_SEARCH_MCP_CACHE_DIR"):
            resolve_cache_dir({"MOMONGA_SEARCH_MCP_CACHE_DIR": "relative-cache"})

    def test_treats_empty_cache_dir_override_as_unset(self) -> None:
        with patch.dict("os.environ", {"XDG_CACHE_HOME": "/tmp/xdg-cache"}, clear=True):
            cache_dir = resolve_cache_dir({"MOMONGA_SEARCH_MCP_CACHE_DIR": ""})

        self.assertEqual(cache_dir, Path("/tmp/xdg-cache/momonga-search-mcp"))

    def test_ignores_old_cache_dir_env_when_new_cache_dir_is_set(self) -> None:
        cache_dir = resolve_cache_dir(
            {
                "MOMONGA_SEARCH_MCP_CACHE_DIR": "/tmp/new-cache",
                "MOMONGA_MCP_CACHE_DIR": "/tmp/legacy-cache",
            }
        )

        self.assertEqual(cache_dir, Path("/tmp/new-cache"))

    def test_rejects_invalid_cache_max_bytes(self) -> None:
        with self.assertRaisesRegex(ConfigError, "MOMONGA_SEARCH_MCP_CACHE_MAX_GB"):
            Config.from_env(
                {
                    "MOMONGA_SEARCH_API_KEY": "ms_test_xxx",
                    "MOMONGA_SEARCH_MCP_CACHE_MAX_GB": "0",
                }
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import unittest

from momonga_search_mcp.config import (
    API_TIMEOUT_SECONDS,
    Config,
    ConfigError,
    default_cache_dir,
    resolve_cache_dir,
)


class ConfigTests(unittest.TestCase):
    def test_requires_api_key(self) -> None:
        with self.assertRaisesRegex(ConfigError, "MOMONGA_SEARCH_API_KEY"):
            Config.from_env({})

    def test_loads_defaults_from_env(self) -> None:
        config = Config.from_env({"MOMONGA_SEARCH_API_KEY": "ms_test_xxx"})

        self.assertEqual(config.api_key, "ms_test_xxx")
        self.assertEqual(config.base_url, "https://api.momongasearch.com/v1")
        self.assertEqual(config.api_timeout_seconds, API_TIMEOUT_SECONDS)

    def test_loads_overrides_from_env(self) -> None:
        config = Config.from_env(
            {
                "MOMONGA_SEARCH_API_KEY": "ms_test_xxx",
                "MOMONGA_BASE_URL": "https://example.com/api/",
                "MOMONGA_SEARCH_MCP_CACHE_DIR": "/tmp/momonga-cache",
                "MOMONGA_MCP_LOG_LEVEL": "debug",
            }
        )

        self.assertEqual(config.base_url, "https://example.com/api")
        self.assertEqual(config.cache_dir, Path("/tmp/momonga-cache"))
        self.assertEqual(config.log_level, "DEBUG")

    def test_ignores_old_cache_dir_env(self) -> None:
        config = Config.from_env(
            {
                "MOMONGA_SEARCH_API_KEY": "ms_test_xxx",
                "MOMONGA_MCP_CACHE_DIR": "/tmp/legacy-cache",
            }
        )

        self.assertEqual(config.cache_dir, default_cache_dir())

    def test_resolves_cache_dir_from_xdg_cache_home(self) -> None:
        cache_dir = resolve_cache_dir({"XDG_CACHE_HOME": "/tmp/xdg-cache"})

        self.assertEqual(cache_dir, Path("/tmp/xdg-cache/momonga-search-mcp"))

    def test_ignores_relative_xdg_cache_home(self) -> None:
        cache_dir = resolve_cache_dir({"XDG_CACHE_HOME": "relative-cache"})

        self.assertEqual(cache_dir, default_cache_dir())

    def test_rejects_relative_cache_dir_override(self) -> None:
        with self.assertRaisesRegex(ConfigError, "MOMONGA_SEARCH_MCP_CACHE_DIR"):
            resolve_cache_dir({"MOMONGA_SEARCH_MCP_CACHE_DIR": "relative-cache"})

    def test_treats_empty_cache_dir_override_as_unset(self) -> None:
        cache_dir = resolve_cache_dir(
            {
                "MOMONGA_SEARCH_MCP_CACHE_DIR": "",
                "XDG_CACHE_HOME": "/tmp/xdg-cache",
            }
        )

        self.assertEqual(cache_dir, Path("/tmp/xdg-cache/momonga-search-mcp"))

    def test_ignores_old_cache_dir_env_when_new_cache_dir_is_set(self) -> None:
        cache_dir = resolve_cache_dir(
            {
                "MOMONGA_SEARCH_MCP_CACHE_DIR": "/tmp/new-cache",
                "MOMONGA_MCP_CACHE_DIR": "/tmp/legacy-cache",
            }
        )

        self.assertEqual(cache_dir, Path("/tmp/new-cache"))


if __name__ == "__main__":
    unittest.main()

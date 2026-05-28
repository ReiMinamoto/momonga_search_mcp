from __future__ import annotations

from pathlib import Path
import unittest

from momonga_search_mcp.config import API_TIMEOUT_SECONDS, Config, ConfigError


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
                "MOMONGA_MCP_CACHE_DIR": "/tmp/momonga-cache",
                "MOMONGA_MCP_LOG_LEVEL": "debug",
            }
        )

        self.assertEqual(config.base_url, "https://example.com/api")
        self.assertEqual(config.cache_dir, Path("/tmp/momonga-cache"))
        self.assertEqual(config.log_level, "DEBUG")


if __name__ == "__main__":
    unittest.main()

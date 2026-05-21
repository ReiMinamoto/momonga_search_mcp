from __future__ import annotations

from pathlib import Path
import unittest

from momonga_search_mcp.config import Config, ConfigError


class ConfigTests(unittest.TestCase):
    def test_requires_api_key(self) -> None:
        with self.assertRaisesRegex(ConfigError, "MOMONGA_SEARCH_API_KEY"):
            Config.from_env({})

    def test_loads_defaults_from_env(self) -> None:
        config = Config.from_env({"MOMONGA_SEARCH_API_KEY": "ms_test_xxx"})

        self.assertEqual(config.api_key, "ms_test_xxx")
        self.assertEqual(config.base_url, "https://api.momongasearch.com/v1")
        self.assertEqual(config.max_credits_per_tool_call, 8)

    def test_loads_overrides_from_env(self) -> None:
        config = Config.from_env(
            {
                "MOMONGA_SEARCH_API_KEY": "ms_test_xxx",
                "MOMONGA_BASE_URL": "https://example.com/api/",
                "MOMONGA_MCP_CACHE_DIR": "/tmp/momonga-cache",
                "MOMONGA_MCP_MAX_CREDITS_PER_TOOL_CALL": "4",
                "MOMONGA_MCP_LOG_LEVEL": "debug",
            }
        )

        self.assertEqual(config.base_url, "https://example.com/api")
        self.assertEqual(config.cache_dir, Path("/tmp/momonga-cache"))
        self.assertEqual(config.max_credits_per_tool_call, 4)
        self.assertEqual(config.log_level, "DEBUG")
        self.assertTrue(config.cache_enabled)

    def test_cache_can_be_disabled_from_env(self) -> None:
        env = {
            "MOMONGA_SEARCH_API_KEY": "ms_test_xxx",
            "MOMONGA_MCP_CACHE_ENABLED": "false",
        }

        config = Config.from_env(env)

        self.assertFalse(config.cache_enabled)

    def test_disable_cache_env_takes_precedence(self) -> None:
        env = {
            "MOMONGA_SEARCH_API_KEY": "ms_test_xxx",
            "MOMONGA_MCP_CACHE_ENABLED": "true",
            "MOMONGA_MCP_DISABLE_CACHE": "1",
        }

        config = Config.from_env(env)

        self.assertFalse(config.cache_enabled)

    def test_rejects_invalid_integer(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must be an integer"):
            Config.from_env(
                {
                    "MOMONGA_SEARCH_API_KEY": "ms_test_xxx",
                    "MOMONGA_MCP_MAX_CREDITS_PER_TOOL_CALL": "many",
                }
            )


if __name__ == "__main__":
    unittest.main()

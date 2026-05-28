"""Runtime configuration for the Momonga Search MCP server."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path

DEFAULT_BASE_URL = "https://api.momongasearch.com/v1"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "momonga-search-mcp"
MAX_LIST_LIMIT = 25
MAX_SEARCH_TOP_K = 25
MAX_SECTIONS_PER_CONTENT_CALL = 5
MAX_CHARACTERS_PER_CONTENT_CALL = 10_000
API_TIMEOUT_SECONDS = 15
DEFAULT_LOG_LEVEL = "INFO"


class ConfigError(RuntimeError):
    """Raised when server configuration is invalid."""


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    cache_dir: Path = DEFAULT_CACHE_DIR
    max_list_limit: int = MAX_LIST_LIMIT
    max_search_top_k: int = MAX_SEARCH_TOP_K
    max_sections_per_content_call: int = MAX_SECTIONS_PER_CONTENT_CALL
    max_characters_per_content_call: int = MAX_CHARACTERS_PER_CONTENT_CALL
    api_timeout_seconds: int = API_TIMEOUT_SECONDS
    log_level: str = DEFAULT_LOG_LEVEL

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        values = os.environ if env is None else env
        api_key = values.get("MOMONGA_SEARCH_API_KEY", "").strip()
        if not api_key:
            raise ConfigError("MOMONGA_SEARCH_API_KEY is required")

        return cls(
            api_key=api_key,
            base_url=_get_str(values, "MOMONGA_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            cache_dir=Path(_get_str(values, "MOMONGA_MCP_CACHE_DIR", str(DEFAULT_CACHE_DIR))).expanduser(),
            log_level=_get_str(values, "MOMONGA_MCP_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
        )


def _get_str(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name, "").strip()
    return value or default

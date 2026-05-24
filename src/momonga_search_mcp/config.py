"""Runtime configuration for the Momonga Search MCP server."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path

DEFAULT_BASE_URL = "https://api.momongasearch.com/v1"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "momonga-search-mcp"
DEFAULT_MAX_LIST_LIMIT = 20
DEFAULT_MAX_SEARCH_TOP_K = 10
DEFAULT_MAX_SECTIONS_PER_CONTENT_CALL = 3
DEFAULT_MAX_CHARACTERS_PER_CONTENT_CALL = 30_000
DEFAULT_MAX_PAGE_IMAGES_PER_CALL = 3
DEFAULT_MAX_ORIGINAL_FILES_PER_CALL = 1
DEFAULT_API_TIMEOUT_SECONDS = 30
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_CACHE_ENABLED = True


class ConfigError(RuntimeError):
    """Raised when server configuration is invalid."""


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    cache_dir: Path = DEFAULT_CACHE_DIR
    max_list_limit: int = DEFAULT_MAX_LIST_LIMIT
    max_search_top_k: int = DEFAULT_MAX_SEARCH_TOP_K
    max_sections_per_content_call: int = DEFAULT_MAX_SECTIONS_PER_CONTENT_CALL
    max_characters_per_content_call: int = DEFAULT_MAX_CHARACTERS_PER_CONTENT_CALL
    max_page_images_per_call: int = DEFAULT_MAX_PAGE_IMAGES_PER_CALL
    max_original_files_per_call: int = DEFAULT_MAX_ORIGINAL_FILES_PER_CALL
    api_timeout_seconds: int = DEFAULT_API_TIMEOUT_SECONDS
    log_level: str = DEFAULT_LOG_LEVEL
    cache_enabled: bool = DEFAULT_CACHE_ENABLED

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
            max_list_limit=_get_int(
                values,
                "MOMONGA_MCP_MAX_LIST_LIMIT",
                DEFAULT_MAX_LIST_LIMIT,
            ),
            max_search_top_k=_get_int(
                values,
                "MOMONGA_MCP_MAX_SEARCH_TOP_K",
                DEFAULT_MAX_SEARCH_TOP_K,
            ),
            max_sections_per_content_call=_get_int(
                values,
                "MOMONGA_MCP_MAX_SECTIONS_PER_CONTENT_CALL",
                DEFAULT_MAX_SECTIONS_PER_CONTENT_CALL,
            ),
            max_characters_per_content_call=_get_int(
                values,
                "MOMONGA_MCP_MAX_CHARACTERS_PER_CONTENT_CALL",
                DEFAULT_MAX_CHARACTERS_PER_CONTENT_CALL,
            ),
            max_page_images_per_call=_get_int(
                values,
                "MOMONGA_MCP_MAX_PAGE_IMAGES_PER_CALL",
                DEFAULT_MAX_PAGE_IMAGES_PER_CALL,
            ),
            max_original_files_per_call=_get_int(
                values,
                "MOMONGA_MCP_MAX_ORIGINAL_FILES_PER_CALL",
                DEFAULT_MAX_ORIGINAL_FILES_PER_CALL,
            ),
            api_timeout_seconds=_get_int(
                values,
                "MOMONGA_MCP_API_TIMEOUT_SECONDS",
                DEFAULT_API_TIMEOUT_SECONDS,
            ),
            log_level=_get_str(values, "MOMONGA_MCP_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
            cache_enabled=_get_cache_enabled(values),
        )


def _get_str(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name, "").strip()
    return value or default


def _get_int(env: Mapping[str, str], name: str, default: int) -> int:
    value = env.get(name, "").strip()
    if not value:
        return default

    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc

    if parsed < 1:
        raise ConfigError(f"{name} must be greater than zero")

    return parsed


def _get_cache_enabled(env: Mapping[str, str]) -> bool:
    disabled = env.get("MOMONGA_MCP_DISABLE_CACHE", "").strip()
    if disabled:
        return not _parse_bool(disabled, "MOMONGA_MCP_DISABLE_CACHE")
    return _parse_bool(env.get("MOMONGA_MCP_CACHE_ENABLED", ""), "MOMONGA_MCP_CACHE_ENABLED", default=DEFAULT_CACHE_ENABLED)


def _parse_bool(value: str, name: str, *, default: bool | None = None) -> bool:
    normalized = value.strip().lower()
    if not normalized and default is not None:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean")

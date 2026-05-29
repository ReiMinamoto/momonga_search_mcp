"""Runtime configuration for the Momonga Search MCP server."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path

from platformdirs import user_cache_dir

DEFAULT_BASE_URL = "https://api.momongasearch.com/v1"
MCP_PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "momonga-search-mcp"
SERVER_VERSION = "0.1.0"
APP_CACHE_DIR_NAME = "momonga-search-mcp"
CACHE_DIR_ENV = "MOMONGA_SEARCH_MCP_CACHE_DIR"
CACHE_MAX_GB_ENV = "MOMONGA_SEARCH_MCP_CACHE_MAX_GB"
BYTES_PER_GB = 1_000_000_000
DEFAULT_CACHE_MAX_GB = Decimal("1")
DEFAULT_CACHE_MAX_BYTES = int(DEFAULT_CACHE_MAX_GB * BYTES_PER_GB)
MAX_LIST_LIMIT = 25
MAX_SEARCH_TOP_K = 25
MAX_SECTIONS_PER_CONTENT_CALL = 5
API_TIMEOUT_SECONDS = 15
DEFAULT_LOG_LEVEL = "INFO"


class ConfigError(RuntimeError):
    """Raised when server configuration is invalid."""


def default_cache_dir() -> Path:
    return Path(user_cache_dir(APP_CACHE_DIR_NAME, appauthor=False))


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    cache_dir: Path = field(default_factory=default_cache_dir)
    max_list_limit: int = MAX_LIST_LIMIT
    max_search_top_k: int = MAX_SEARCH_TOP_K
    max_sections_per_content_call: int = MAX_SECTIONS_PER_CONTENT_CALL
    api_timeout_seconds: int = API_TIMEOUT_SECONDS
    cache_max_bytes: int = DEFAULT_CACHE_MAX_BYTES
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
            cache_dir=resolve_cache_dir(values),
            cache_max_bytes=_get_cache_max_bytes(values),
            log_level=_get_str(values, "MOMONGA_MCP_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
        )


def resolve_cache_dir(env: Mapping[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    cache_dir = _optional_path(values, CACHE_DIR_ENV)
    if cache_dir is not None:
        return cache_dir

    return default_cache_dir()


def _get_str(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name, "").strip()
    return value or default


def _optional_path(env: Mapping[str, str], name: str) -> Path | None:
    value = env.get(name, "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ConfigError(f"{name} must be an absolute path")
    return path


def _get_cache_max_bytes(env: Mapping[str, str]) -> int:
    value = env.get(CACHE_MAX_GB_ENV, "").strip()
    if not value:
        return DEFAULT_CACHE_MAX_BYTES
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ConfigError(f"{CACHE_MAX_GB_ENV} must be a positive number") from exc
    if parsed <= 0:
        raise ConfigError(f"{CACHE_MAX_GB_ENV} must be a positive number")
    return int(parsed * BYTES_PER_GB)

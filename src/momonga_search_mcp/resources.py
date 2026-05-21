"""MCP resources backed by Momonga local cache entries."""

from __future__ import annotations

import json

from momonga_search_mcp.cache import CacheManager

MOMONGA_RESOURCE_PREFIX = "momonga://"


def is_momonga_resource_uri(uri: str) -> bool:
    return uri.startswith(MOMONGA_RESOURCE_PREFIX)


def read_momonga_resource(cache_manager: CacheManager, uri: str) -> tuple[str, str]:
    resource = cache_manager.get_json_resource(uri)
    if resource is None:
        raise ValueError(f"Unknown Momonga resource URI: {uri}")

    cached_resource, mime_type = resource
    payload = cache_manager.read_json(cached_resource)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")), mime_type

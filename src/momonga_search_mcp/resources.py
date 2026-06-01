"""MCP resources backed by Momonga local cache entries."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import unquote, urlparse

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
    manifest = _resource_manifest(uri, payload)
    return json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), mime_type


def _resource_manifest(uri: str, payload: dict[str, Any]) -> dict[str, Any]:
    parsed = _parse_momonga_resource_uri(uri)
    resource_type = parsed["resource_type"]
    if resource_type == "toc":
        return _toc_manifest(uri, parsed["document_id"], payload)
    if resource_type == "section":
        return _section_manifest(uri, parsed["document_id"], parsed["resource_id"], payload)
    if resource_type == "page":
        return _metadata_manifest(uri, payload, "page")
    if resource_type == "original":
        return _metadata_manifest(uri, payload, "original")
    return _metadata_manifest(uri, payload, "resource")


def _parse_momonga_resource_uri(uri: str) -> dict[str, str]:
    parsed = urlparse(uri)
    path_parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if parsed.scheme != "momonga" or parsed.netloc != "documents" or not path_parts:
        raise ValueError(f"Unsupported Momonga resource URI: {uri}")

    document_id = path_parts[0]
    if len(path_parts) == 2 and path_parts[1] == "toc":
        return {"document_id": document_id, "resource_type": "toc", "resource_id": "toc"}
    if len(path_parts) == 3 and path_parts[1] == "sections":
        return {"document_id": document_id, "resource_type": "section", "resource_id": path_parts[2]}
    if len(path_parts) == 3 and path_parts[1] == "pages":
        return {"document_id": document_id, "resource_type": "page", "resource_id": path_parts[2]}
    if len(path_parts) == 3 and path_parts[1] == "originals":
        return {"document_id": document_id, "resource_type": "original", "resource_id": path_parts[2]}
    raise ValueError(f"Unsupported Momonga resource URI: {uri}")


def _toc_manifest(uri: str, document_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    toc = payload.get("toc")
    toc_entries = toc if isinstance(toc, list) else []
    return {
        "document_id": document_id,
        "resource_type": "toc",
        "toc_available_in_cache": True,
        "toc_entry_count": len(toc_entries),
        "read_policy": (
            "Use get_document_toc with path_prefix/max_depth options for outline or subtree retrieval; "
            "full cached TOC JSON is not returned by resources/read."
        ),
        "source_resource_uri": uri,
    }


def _section_manifest(uri: str, document_id: str, section_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    cached_section_id = payload.get("section_id")
    section_title = payload.get("section_title")
    heading_path = payload.get("heading_path")
    character_count = payload.get("character_count")
    content_available = any(
        isinstance(payload.get(field), str) and bool(payload[field]) for field in ("content", "text", "raw_content", "body")
    )

    return {
        "document_id": document_id,
        "section_id": cached_section_id if isinstance(cached_section_id, str) and cached_section_id else section_id,
        "section_title": section_title if isinstance(section_title, str) else None,
        "heading_path": [item for item in heading_path if isinstance(item, str)] if isinstance(heading_path, list) else [],
        "character_count": character_count if isinstance(character_count, int) else None,
        "content_available_in_cache": content_available,
        "read_policy": (
            "Use search_section_contents or get_section_window; full cached content is not returned by resources/read."
        ),
        "recommended_tools": ["search_section_contents", "get_section_window"],
        "source_resource_uri": uri,
    }


def _metadata_manifest(uri: str, payload: dict[str, Any], resource_type: str) -> dict[str, Any]:
    manifest = {key: value for key, value in payload.items() if key not in {"content", "text", "raw_content", "body"}}
    manifest["resource_type"] = resource_type
    manifest["source_resource_uri"] = uri
    return manifest

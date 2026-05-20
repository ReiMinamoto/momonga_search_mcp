"""Tool response payload builders."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any

from momonga_search_mcp.cache import CachedResource

DOCUMENT_FIELDS = (
    "document_id",
    "document_family",
    "title",
    "document_type",
    "issuers",
    "timeline_at",
    "content_status",
    "reference_url",
)

LIST_NEWS_FIELDS = (
    "news_id",
    "statement",
    "observed_at",
    "related_issuers",
    "macro_tags",
    "references",
)

SEARCH_NEWS_FIELDS = LIST_NEWS_FIELDS

CONTENT_SECTION_FIELDS = ("section_id", "section_title", "character_count", "content")
TOC_FIELDS = ("section_id", "section_title", "heading_path", "character_count", "page_number")


def tool_json_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            }
        ]
    }
    if is_error:
        result["isError"] = True
    return result


def success_response(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "search_issuers":
        return {
            "ok": True,
            "results": [
                _pick(item, ("security_code", "edinet_code", "name", "market", "sector")) for item in _list(payload, "results")
            ],
        }
    if tool_name == "list_documents":
        return _results_response(payload, lambda item: _pick(item, DOCUMENT_FIELDS))
    if tool_name == "get_document_metadata":
        return {"ok": True, **_pick(payload, DOCUMENT_FIELDS)}
    if tool_name == "list_document_page_images":
        return {
            "ok": True,
            **_pick(payload, ("document_id", "page_count", "page_image_count")),
            "page_images": _page_numbers(payload),
        }
    if tool_name == "list_document_originals":
        return {
            "ok": True,
            **_pick(payload, ("document_id",)),
            "originals": [
                _pick(item, ("original_id", "filename", "media_type", "credit_cost")) for item in _list(payload, "originals")
            ],
        }
    if tool_name == "list_news":
        return _results_response(payload, lambda item: _pick(item, LIST_NEWS_FIELDS))
    if tool_name == "search_documents":
        return _results_response(payload, _document_search_result)
    if tool_name == "search_news":
        return _results_response(payload, lambda item: _pick(item, SEARCH_NEWS_FIELDS))
    return {"ok": True, **payload}


def get_document_toc_response(payload: dict[str, Any], resource: CachedResource, *, cache_hit: bool) -> dict[str, Any]:
    return {
        "ok": True,
        **_pick(payload, ("document_id",)),
        "toc": [_pick(item, TOC_FIELDS) for item in _list(payload, "toc")],
        "resource_uri": resource.resource_uri,
        "cache_hit": cache_hit,
    }


def get_document_content_response(
    document_id: str,
    content_sections: list[tuple[dict[str, Any], str]],
    *,
    cache_hit: bool,
    cached_sections: bool,
    return_content: bool,
) -> dict[str, Any]:
    return {
        "ok": True,
        "document_id": document_id,
        "content_sections": [
            _content_section_response(
                section,
                resource_uri=resource_uri,
                cached=cached_sections,
                return_content=return_content,
            )
            for section, resource_uri in content_sections
        ],
        "cache_hit": cache_hit,
    }


def _content_section_response(
    section: dict[str, Any],
    *,
    resource_uri: str,
    cached: bool,
    return_content: bool,
) -> dict[str, Any]:
    fields = CONTENT_SECTION_FIELDS if return_content else tuple(field for field in CONTENT_SECTION_FIELDS if field != "content")
    response = _pick(section, fields)
    response["resource_uri"] = resource_uri
    response["cached"] = cached
    return response


def _results_response(payload: dict[str, Any], item_mapper: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    response: dict[str, Any] = {"ok": True, "results": [item_mapper(item) for item in _list(payload, "results")]}
    if "next_cursor" in payload:
        response["next_cursor"] = payload["next_cursor"]
    return response


def _document_search_result(item: dict[str, Any]) -> dict[str, Any]:
    response = _pick(item, DOCUMENT_FIELDS)
    response["matches"] = [
        _pick(match, ("section_id", "section_title", "score", "snippet", "page_number", "has_visual"))
        for match in _list(item, "matches")
    ]
    return response


def _page_numbers(payload: dict[str, Any]) -> list[int]:
    page_numbers = []
    for item in _list(payload, "page_images"):
        page_number = item.get("page_number")
        if type(page_number) is int:
            page_numbers.append(page_number)
    return page_numbers


def _pick(item: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: item[field] for field in fields if field in item}


def _list(payload: dict[str, Any], field: str) -> list[dict[str, Any]]:
    value = payload.get(field)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

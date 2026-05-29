"""Tool response payload builders."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from momonga_search_mcp.cache import CachedResource

DOCUMENT_FIELDS = (
    "document_id",
    "document_family",
    "title",
    "document_type",
    "issuers",
    "published_at",
    "timeline_at",
    "content_status",
    "character_count",
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
MAX_DIRECT_TOC_SECTIONS = 50
MAX_INLINE_SECTION_CHARACTERS = 3_000


def tool_json_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [
            {
                "type": "text",
                "text": _summary_text(payload, is_error=is_error),
            }
        ],
        "structuredContent": payload,
    }
    if is_error:
        result["isError"] = True
    return result


def _summary_text(payload: dict[str, Any], *, is_error: bool) -> str:
    if is_error:
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message")
            if isinstance(code, str) and isinstance(message, str):
                return f"Error {code}: {message}. See structuredContent."
            if isinstance(code, str):
                return f"Error {code}. See structuredContent."
        return "Error. See structuredContent."

    if payload.get("ok") is True:
        result_count = _list_count(payload, "results")
        if result_count is not None:
            return f"OK. Returned {result_count} result(s). See structuredContent."
        section_count = _list_count(payload, "content_sections")
        if section_count is not None:
            return f"OK. Returned {section_count} content section(s). See structuredContent."
        resource_count = _list_count(payload, "resources")
        if resource_count is not None:
            return f"OK. Returned {resource_count} cached resource(s). See structuredContent."
        return "OK. See structuredContent."

    return "Result returned in structuredContent."


def _list_count(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, list):
        return len(value)
    return None


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
            "originals": [_pick(item, ("original_id", "filename", "media_type")) for item in _list(payload, "originals")],
        }
    if tool_name == "list_news":
        return _results_response(payload, lambda item: _pick(item, LIST_NEWS_FIELDS))
    if tool_name == "search_documents":
        return _results_response(payload, _document_search_result)
    if tool_name == "search_news":
        return _results_response(payload, lambda item: _pick(item, SEARCH_NEWS_FIELDS))
    return {"ok": True, **payload}


def get_document_toc_response(
    payload: dict[str, Any],
    resource: CachedResource,
    *,
    cache_hit: bool,
    path_prefix: list[str] | None = None,
    max_depth: int = 2,
    include_sections: bool = False,
) -> dict[str, Any]:
    toc_entries = [_pick(item, TOC_FIELDS) for item in _list(payload, "toc")]
    selected_entries = _filter_toc_by_path_prefix(toc_entries, path_prefix or [])
    toc_mode = _toc_mode(selected_entries, path_prefix=path_prefix, include_sections=include_sections)
    toc_response = (
        selected_entries
        if toc_mode == "sections"
        else _build_toc_outline(selected_entries, max_depth=max_depth, include_sections=include_sections)
    )
    response = {
        "ok": True,
        **_pick(payload, ("document_id",)),
        "toc_mode": toc_mode,
        "path_prefix": path_prefix or [],
        "max_depth": max_depth,
        "include_sections": include_sections,
        "selection_policy": _toc_selection_policy(toc_mode, selected_entries, path_prefix=path_prefix),
        "toc": toc_response,
        "resource_uri": resource.resource_uri,
        "cache_hit": cache_hit,
    }
    next_action_template = _toc_next_action_template(response.get("document_id"), toc_mode)
    if next_action_template is not None:
        response["next_action_template"] = next_action_template
    return response


def get_document_content_response(
    document_id: str,
    content_sections: list[tuple[dict[str, Any], str]],
    *,
    cache_hit: bool,
    cached_sections: bool,
    return_content: bool,
) -> dict[str, Any]:
    section_responses = []
    for section, resource_uri in content_sections:
        section_response = _content_section_response(
            section,
            resource_uri=resource_uri,
            cached=cached_sections,
            return_content=return_content,
        )
        section_responses.append(section_response)

    return {
        "ok": True,
        "document_id": document_id,
        "content_sections": section_responses,
        "max_inline_section_characters": MAX_INLINE_SECTION_CHARACTERS,
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
    if return_content:
        content = response.get("content")
        if isinstance(content, str):
            if _section_text_length(section, content) > MAX_INLINE_SECTION_CHARACTERS:
                return _content_section_manifest_response(
                    section,
                    resource_uri=resource_uri,
                    cached=cached,
                    reason="section_exceeds_inline_threshold",
                )
            response["content_mode"] = "inline"
    response["resource_uri"] = resource_uri
    response["cached"] = cached
    return response


def _content_section_manifest_response(
    section: dict[str, Any],
    *,
    resource_uri: str,
    cached: bool,
    reason: str,
) -> dict[str, Any]:
    response = _pick(section, tuple(field for field in CONTENT_SECTION_FIELDS if field != "content"))
    response["content_mode"] = "manifest"
    response["reason"] = reason
    response["content_available_in_cache"] = True
    response["recommended_tools"] = ["search_section_contents", "get_section_window"]
    response["resource_uri"] = resource_uri
    response["source_resource_uri"] = resource_uri
    response["cached"] = cached
    return response


def _section_text_length(section: dict[str, Any], content: str) -> int:
    character_count = section.get("character_count")
    if type(character_count) is int:
        return character_count
    return len(content)


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


def _filter_toc_by_path_prefix(toc: list[dict[str, Any]], path_prefix: list[str]) -> list[dict[str, Any]]:
    if not path_prefix:
        return toc
    return [
        item
        for item in toc
        if isinstance(item.get("heading_path"), list) and item["heading_path"][: len(path_prefix)] == path_prefix
    ]


def _toc_mode(toc: list[dict[str, Any]], *, path_prefix: list[str] | None, include_sections: bool) -> str:
    if path_prefix:
        return "subtree"
    if include_sections or len(toc) <= MAX_DIRECT_TOC_SECTIONS:
        return "sections"
    return "outline"


def _toc_selection_policy(
    toc_mode: str,
    toc: list[dict[str, Any]],
    *,
    path_prefix: list[str] | None,
) -> dict[str, Any]:
    if path_prefix:
        reason = "path_prefix_requested"
    elif toc_mode == "sections":
        reason = "toc_is_small"
    else:
        reason = "toc_is_large"
    return {
        "mode": "auto",
        "reason": reason,
        "max_direct_toc_sections": MAX_DIRECT_TOC_SECTIONS,
        "selected_toc_entry_count": len(toc),
    }


def _toc_next_action_template(
    document_id: Any,
    toc_mode: str,
) -> dict[str, Any] | None:
    if toc_mode == "sections" or not isinstance(document_id, str) or not document_id:
        return None

    return {
        "tool": "get_document_toc",
        "argument_hints": {
            "document_id": document_id,
            "path_prefix": "Choose a relevant heading_path from the returned toc outline.",
            "include_sections": True,
        },
    }


def _build_toc_outline(toc: list[dict[str, Any]], *, max_depth: int, include_sections: bool) -> list[dict[str, Any]]:
    root: dict[str, Any] = {"children": {}, "sections": []}
    for section in toc:
        heading_path = section.get("heading_path")
        if not isinstance(heading_path, list) or not heading_path:
            heading_path = [section.get("section_title") or section.get("section_id") or "Untitled"]
        heading_path = [item for item in heading_path if isinstance(item, str)]
        if not heading_path:
            continue

        node = root
        current_path = []
        for heading in heading_path:
            current_path.append(heading)
            node = node["children"].setdefault(
                heading,
                {"heading_title": heading, "heading_path": list(current_path), "children": {}, "sections": []},
            )
        node["sections"].append(section)

    depth_limit = max(2, max_depth)
    return [
        _outline_node(child, depth_limit=depth_limit, include_sections=include_sections) for child in root["children"].values()
    ]


def _outline_node(node: dict[str, Any], *, depth_limit: int, include_sections: bool) -> dict[str, Any]:
    children = list(node["children"].values())
    sections = _collect_sections(node)
    page_numbers = [section["page_number"] for section in sections if type(section.get("page_number")) is int]
    result: dict[str, Any] = {
        "heading_title": node["heading_title"],
        "heading_path": node["heading_path"],
        "section_count": len(sections),
        "total_character_count": sum(
            section["character_count"] for section in sections if type(section.get("character_count")) is int
        ),
        "page_range": {"start": min(page_numbers), "end": max(page_numbers)} if page_numbers else None,
        "has_children": bool(children),
    }
    if include_sections:
        result["sections"] = [_pick(section, TOC_FIELDS) for section in sections]
    if len(node["heading_path"]) < depth_limit and children:
        result["children"] = [
            _outline_node(child, depth_limit=depth_limit, include_sections=include_sections) for child in children
        ]
    return result


def _collect_sections(node: dict[str, Any]) -> list[dict[str, Any]]:
    sections = list(node["sections"])
    for child in node["children"].values():
        sections.extend(_collect_sections(child))
    return sections


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

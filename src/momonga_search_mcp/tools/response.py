"""Tool response payload builders."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any

DOCUMENT_FIELDS = (
    "document_id",
    "document_family",
    "title",
    "document_type",
    "issuers",
    "published_at",
    "timeline_at",
    "timeline_precision",
    "timeline_basis",
    "first_observed_at",
    "retry_after_seconds",
    "content_status",
    "character_count",
    "reference_url",
)

NEWS_FIELDS = (
    "news_id",
    "title",
    "body",
    "observed_at",
    "updated_at",
    "related_issuers",
    "references",
    "score",
)

CONTENT_SECTION_FIELDS = ("section_id", "section_title", "character_count", "content")
# get_document_toc lists every section while the text stays within this size;
# beyond it, headings only. Even large yuho TOCs fit (sample max ~16,000).
MAX_TOC_CHARACTERS = 20_000
# Inline body text shared by all sections of one get_document_content call.
# Japanese body text costs up to about one token per character, so this stays under
# typical MCP client output caps (Claude Code: 25,000 tokens).
MAX_INLINE_CHARACTERS_PER_CALL = 20_000
FULL_DOCUMENT_SECTION_ID = "__mcp_full_document__"


def tool_json_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False),
            }
        ],
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
        response = {"ok": True, **_pick(payload, DOCUMENT_FIELDS)}
        next_action = _metadata_next_action(response)
        if next_action is not None:
            response["next_action"] = next_action
        return response
    if tool_name == "list_document_page_images":
        return {
            "ok": True,
            **_pick(payload, ("document_id", "page_count", "page_image_count")),
            "page_images": [
                _pick(item, ("page_number", "source_route", "image_role"))
                for item in _list(payload, "page_images")
                if type(item.get("page_number")) is int
            ],
        }
    if tool_name == "list_document_originals":
        return {
            "ok": True,
            **_pick(payload, ("document_id",)),
            "originals": [
                _pick(item, ("original_id", "filename", "media_type", "kind", "role")) for item in _list(payload, "originals")
            ],
        }
    if tool_name in {"list_news", "search_news"}:
        return _results_response(payload, lambda item: _pick(item, NEWS_FIELDS))
    if tool_name == "search_documents":
        return _results_response(payload, _document_search_result)
    return {"ok": True, **payload}


def get_document_toc_response(
    payload: dict[str, Any],
    *,
    path_prefix: list[str] | None = None,
) -> dict[str, Any]:
    entries = _filter_toc_by_path_prefix(_list(payload, "toc"), path_prefix or [])
    toc_text = _toc_sections_text(entries)
    toc_mode = "sections"
    if len(toc_text) > MAX_TOC_CHARACTERS:
        toc_text = _toc_outline_text(entries, depth_limit=len(path_prefix or []) + 2)
        toc_mode = "outline"
    response = {
        "ok": True,
        **_pick(payload, ("document_id",)),
        "toc_mode": toc_mode,
        "section_count": len(entries),
        "toc": toc_text,
    }
    if path_prefix:
        response["path_prefix"] = path_prefix
    return response


def get_document_content_response(
    document_id: str,
    content_sections: list[tuple[dict[str, Any], str]],
    *,
    cache_hit: bool,
    cached_sections: bool,
    return_content: bool,
    requested_section_ids: list[str] | None = None,
    missing_section_ids: list[str] | None = None,
) -> dict[str, Any]:
    section_responses = []
    inline_budget = MAX_INLINE_CHARACTERS_PER_CALL
    for section, resource_uri in content_sections:
        section_response = _content_section_response(
            section,
            document_id=document_id,
            resource_uri=resource_uri,
            cached=cached_sections,
            return_content=return_content,
            inline_budget=inline_budget,
        )
        if section_response.get("content_mode") == "inline":
            inline_budget -= _section_text_length(section, section_response["content"])
        section_responses.append(section_response)

    response: dict[str, Any] = {
        "ok": True,
        "document_id": document_id,
        "content_sections": section_responses,
        "max_inline_characters_per_call": MAX_INLINE_CHARACTERS_PER_CALL,
        "cache_hit": cache_hit,
    }
    if requested_section_ids is not None:
        response["requested_section_ids"] = requested_section_ids
    if missing_section_ids:
        response["missing_section_ids"] = missing_section_ids
    return response


def _content_section_response(
    section: dict[str, Any],
    *,
    document_id: str,
    resource_uri: str,
    cached: bool,
    return_content: bool,
    inline_budget: int,
) -> dict[str, Any]:
    fields = CONTENT_SECTION_FIELDS if return_content else tuple(field for field in CONTENT_SECTION_FIELDS if field != "content")
    response = _pick(section, fields)
    if return_content:
        content = response.get("content")
        if isinstance(content, str):
            if _section_text_length(section, content) > inline_budget:
                return _content_section_manifest_response(
                    section,
                    document_id=document_id,
                    resource_uri=resource_uri,
                    cached=cached,
                    reason="inline_budget_exceeded",
                )
            response["content_mode"] = "inline"
    response["resource_uri"] = resource_uri
    response["cached"] = cached
    return response


def _content_section_manifest_response(
    section: dict[str, Any],
    *,
    document_id: str,
    resource_uri: str,
    cached: bool,
    reason: str,
) -> dict[str, Any]:
    response = _pick(section, tuple(field for field in CONTENT_SECTION_FIELDS if field != "content"))
    response["content_mode"] = "manifest"
    response["reason"] = reason
    response["content_available_in_cache"] = True
    response["recommended_tools"] = ["search_section_contents", "get_section_window"]
    response["next_action"] = _manifest_section_next_action(document_id, section.get("section_id"))
    response["resource_uri"] = resource_uri
    response["source_resource_uri"] = resource_uri
    response["cached"] = cached
    return response


def _metadata_next_action(response: dict[str, Any]) -> dict[str, Any] | None:
    content_status = response.get("content_status")
    document_id = response.get("document_id")
    reference_url = response.get("reference_url")
    if content_status == "ready" and isinstance(document_id, str) and document_id:
        character_count = response.get("character_count")
        if type(character_count) is int and character_count <= MAX_INLINE_CHARACTERS_PER_CALL:
            return {
                "status": "ready",
                "recommended_tools": ["get_document_content"],
                "argument_hints": {"document_id": document_id, "allow_full_document": True},
            }
        return {
            "status": "ready",
            "recommended_tools": ["get_document_toc", "get_document_content"],
            "argument_hints": {"document_id": document_id},
        }
    if content_status == "pending_release":
        return {
            "status": "pending_release",
            "message": "Content is not available yet. Wait before retrying metadata or content retrieval.",
        }
    if content_status == "external_only":
        next_action: dict[str, Any] = {
            "status": "external_only",
            "message": "Do not retry Momonga content retrieval; inspect the external reference instead.",
        }
        if isinstance(reference_url, str) and reference_url:
            next_action["reference_url"] = reference_url
        return next_action
    return None


def _manifest_section_next_action(document_id: str, section_id: Any) -> dict[str, Any]:
    argument_hints: dict[str, Any] = {
        "document_id": document_id,
        "query": "Search terms for the needed evidence in this section.",
    }
    if isinstance(section_id, str) and section_id:
        argument_hints["section_id"] = section_id
    return {
        "tool": "search_section_contents",
        "argument_hints": argument_hints,
        "fallback_tool": "get_section_window",
    }


def _section_text_length(section: dict[str, Any], content: str) -> int:
    character_count = section.get("character_count")
    if type(character_count) is int:
        return character_count
    return len(content)


def _results_response(payload: dict[str, Any], item_mapper: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    response: dict[str, Any] = {"ok": True, "results": [item_mapper(item) for item in _list(payload, "results")]}
    next_cursor = payload.get("next_cursor")
    if isinstance(next_cursor, str) and next_cursor:
        response["next_cursor"] = next_cursor
    return response


def _document_search_result(item: dict[str, Any]) -> dict[str, Any]:
    response = _pick(item, DOCUMENT_FIELDS)
    response["matches"] = [
        _pick(
            match,
            (
                "section_id",
                "section_title",
                "heading_path",
                "character_count",
                "score",
                "snippet",
                "page_number",
                "has_visual",
            ),
        )
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


def _toc_sections_text(entries: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    previous_path: list[str] = []
    for entry in entries:
        heading_path = entry["heading_path"]
        shared = 0
        while shared < min(len(previous_path), len(heading_path) - 1) and previous_path[shared] == heading_path[shared]:
            shared += 1
        for depth in range(shared, len(heading_path) - 1):
            lines.append("  " * depth + heading_path[depth])
        label = entry.get("section_title") or heading_path[-1]
        fields = [label, entry["section_id"], str(entry["character_count"])]
        if type(entry.get("page_number")) is int:
            fields.append(f"p{entry['page_number']}")
        lines.append("  " * (len(heading_path) - 1) + " | ".join(fields))
        previous_path = heading_path
    return "\n".join(lines)


def _toc_outline_text(entries: list[dict[str, Any]], *, depth_limit: int) -> str:
    # heading -> [section count, character count, child headings], children in document order
    root: dict[str, list[Any]] = {}
    for entry in entries:
        node = root
        for heading in entry["heading_path"][:depth_limit]:
            child = node.setdefault(heading, [0, 0, {}])
            child[0] += 1
            child[1] += entry["character_count"]
            node = child[2]

    lines: list[str] = []

    def walk(node: dict[str, list[Any]], depth: int) -> None:
        for heading, (section_count, character_count, children) in node.items():
            lines.append("  " * depth + f"{heading} | {section_count} sections | {character_count}")
            walk(children, depth + 1)

    walk(root, 0)
    return "\n".join(lines)


def _pick(item: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: item[field] for field in fields if field in item}


def _list(payload: dict[str, Any], field: str) -> list[dict[str, Any]]:
    value = payload.get(field)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

"""MCP tool handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from momonga_search_mcp.api import MomongaApiClient, MomongaApiError, api_error_response
from momonga_search_mcp.cache import CacheManager
from momonga_search_mcp.tools.definitions import CREDIT_TOOLS, ZERO_CREDIT_DOCUMENT_TOOLS
from momonga_search_mcp.tools.response import (
    get_document_content_response,
    get_document_toc_response,
    success_response,
    tool_json_result,
)

DEFAULT_CONTENT_MAX_CHARS = 8000
TOOL_SCHEMAS = {**ZERO_CREDIT_DOCUMENT_TOOLS, **CREDIT_TOOLS}


def call_tool(
    api_client: MomongaApiClient,
    params: Any,
    *,
    cache_manager_getter: Callable[[], CacheManager] | None = None,
) -> dict[str, Any]:
    if not isinstance(params, dict):
        return _validation_error("tools/call params must be an object")

    name = params.get("name")
    arguments = params.get("arguments", {})
    if not isinstance(name, str):
        return _validation_error("tool name is required")
    if not isinstance(arguments, dict):
        return _validation_error("tool arguments must be an object")
    if name not in TOOL_SCHEMAS:
        return _tool_error(
            "unknown_tool",
            f"Unknown tool: {name}",
            next_action="Use one of the tool names returned by tools/list.",
        )

    try:
        _validate_tool_arguments(name, arguments)
        if name == "search_issuers":
            payload = api_client.get("/issuers/search", _require_arguments(arguments, ("q",), optional=("limit",)))
        elif name == "list_documents":
            payload = api_client.get(
                "/documents",
                _select_arguments(
                    arguments,
                    (
                        "security_codes",
                        "document_types",
                        "document_families",
                        "timeline_since",
                        "timeline_until",
                        "limit",
                        "cursor",
                    ),
                ),
            )
        elif name == "get_document_metadata":
            payload = api_client.get(f"/documents/{_quoted_document_id(arguments)}")
        elif name == "get_document_toc":
            return _call_get_document_toc(api_client, arguments, cache_manager_getter)
        elif name == "list_document_page_images":
            payload = api_client.get(f"/documents/{_quoted_document_id(arguments)}/page-images")
        elif name == "list_document_originals":
            payload = api_client.get(f"/documents/{_quoted_document_id(arguments)}/originals")
        elif name == "list_news":
            payload = api_client.get(
                "/news",
                _select_arguments(
                    arguments,
                    ("security_codes", "macro_tags", "timeline_since", "timeline_until", "limit", "cursor"),
                ),
            )
        elif name == "get_document_content":
            return _call_get_document_content(api_client, arguments, cache_manager_getter)
        elif name == "search_documents":
            payload = api_client.post(
                "/search/documents",
                _require_arguments(
                    arguments,
                    ("query",),
                    optional=(
                        "security_codes",
                        "document_types",
                        "document_families",
                        "timeline_since",
                        "timeline_until",
                        "match_type",
                        "top_k",
                        "include_snippet",
                    ),
                ),
            )
        elif name == "search_news":
            payload = api_client.post(
                "/search/news",
                _require_arguments(
                    arguments,
                    ("query",),
                    optional=("security_codes", "macro_tags", "timeline_since", "timeline_until", "match_type", "top_k"),
                ),
            )
        else:
            raise ValueError(f"Unhandled tool: {name}")
    except ValueError as exc:
        return _validation_error(str(exc))
    except MomongaApiError as exc:
        return tool_json_result(api_error_response(exc), is_error=True)

    return tool_json_result(success_response(name, payload))


def _validation_error(message: str) -> dict[str, Any]:
    return _tool_error("invalid_request", message, next_action="Fix the tool input and retry the request.")


def _tool_error(code: str, message: str, *, next_action: str) -> dict[str, Any]:
    return tool_json_result(
        {
            "ok": False,
            "error": {
                "code": code,
                "status": None,
                "message": message,
                "next_action": next_action,
            },
        },
        is_error=True,
    )


def _call_get_document_toc(
    api_client: MomongaApiClient,
    arguments: dict[str, Any],
    cache_manager_getter: Callable[[], CacheManager] | None,
) -> dict[str, Any]:
    document_id = _required_string(arguments, "document_id")
    if cache_manager_getter is None:
        raise ValueError("cache manager is required for get_document_toc")

    cache_manager = cache_manager_getter()
    cached_toc = cache_manager.get_document_toc(document_id)
    if cached_toc is not None:
        payload = cache_manager.read_json(cached_toc)
        return tool_json_result(get_document_toc_response(payload, cached_toc, cache_hit=True))

    payload = api_client.get(f"/documents/{_quote_path_component(document_id)}/toc")
    resource = cache_manager.store_document_toc(document_id, payload)
    return tool_json_result(get_document_toc_response(payload, resource, cache_hit=False))


def _call_get_document_content(
    api_client: MomongaApiClient,
    arguments: dict[str, Any],
    cache_manager_getter: Callable[[], CacheManager] | None,
) -> dict[str, Any]:
    document_id = _required_string(arguments, "document_id")
    section_ids = arguments["section_ids"]
    if not isinstance(section_ids, list) or not all(isinstance(item, str) and item.strip() for item in section_ids):
        raise ValueError("section_ids must be an array of strings")
    return_content = arguments.get("return_content", True)
    if not isinstance(return_content, bool):
        raise ValueError("return_content must be a boolean")
    offset = arguments.get("offset", 0)
    if offset > 0 and len(section_ids) != 1:
        raise ValueError("offset can only be used with exactly one section_id")

    if cache_manager_getter is None:
        raise ValueError("cache manager is required for get_document_content")
    cache_manager = cache_manager_getter()
    if section_ids:
        cached_resources = [cache_manager.get_document_section(document_id, section_id) for section_id in section_ids]
        if all(resource is not None for resource in cached_resources):
            resources = [resource for resource in cached_resources if resource is not None]
            sections = [cache_manager.read_json(resource) for resource in resources]
            return tool_json_result(
                get_document_content_response(
                    document_id,
                    list(zip(sections, [resource.resource_uri for resource in resources], strict=True)),
                    cache_hit=True,
                    cached_sections=True,
                    return_content=return_content,
                    max_chars=DEFAULT_CONTENT_MAX_CHARS,
                    offset=offset,
                )
            )

    params = {"sections": section_ids}
    payload = api_client.get(f"/documents/{_quote_path_component(document_id)}/content", params)
    content_sections = payload.get("content_sections")
    section_resources = []
    if isinstance(content_sections, list):
        for section in content_sections:
            if not isinstance(section, dict):
                continue

            section_id = _required_string(section, "section_id")
            section_resources.append(
                (section, cache_manager.store_document_section(document_id, section_id, section).resource_uri)
            )

    return tool_json_result(
        get_document_content_response(
            document_id,
            section_resources,
            cache_hit=False,
            cached_sections=False,
            return_content=return_content,
            max_chars=DEFAULT_CONTENT_MAX_CHARS,
            offset=offset,
        )
    )


def _validate_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> None:
    schema = TOOL_SCHEMAS[tool_name]["inputSchema"]
    properties = schema["properties"]
    allowed_names = set(properties)
    unknown_names = sorted(set(arguments) - allowed_names)
    if unknown_names:
        raise ValueError(f"unknown arguments: {', '.join(unknown_names)}")

    for name in schema.get("required", []):
        if name not in arguments:
            raise ValueError(f"{name} is required")

    any_of = schema.get("anyOf")
    if isinstance(any_of, list) and not any(
        all(_has_present_value(arguments, required_name) for required_name in option.get("required", [])) for option in any_of
    ):
        alternatives = [" + ".join(option.get("required", [])) for option in any_of]
        raise ValueError(f"one of these argument sets is required: {' or '.join(alternatives)}")

    for name, value in arguments.items():
        _validate_argument_value(name, value, properties[name])


def _has_present_value(arguments: dict[str, Any], name: str) -> bool:
    value = arguments.get(name)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return value is not None


def _validate_argument_value(name: str, value: Any, schema: dict[str, Any]) -> None:
    value_type = schema.get("type")
    if value_type == "string":
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError(f"{name} must be one of: {', '.join(schema['enum'])}")
    elif value_type == "integer":
        if type(value) is not int:
            raise ValueError(f"{name} must be an integer")
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            raise ValueError(f"{name} must be greater than or equal to {minimum}")
        if maximum is not None and value > maximum:
            raise ValueError(f"{name} must be less than or equal to {maximum}")
    elif value_type == "boolean":
        if type(value) is not bool:
            raise ValueError(f"{name} must be a boolean")
    elif value_type == "array":
        if not isinstance(value, list):
            raise ValueError(f"{name} must be an array")
        min_items = schema.get("minItems", 1)
        max_items = schema.get("maxItems")
        if len(value) < min_items:
            raise ValueError(f"{name} must contain at least {min_items} item")
        if max_items is not None and len(value) > max_items:
            raise ValueError(f"{name} must contain at most {max_items} items")
        item_schema = schema.get("items", {})
        for item in value:
            _validate_argument_value(name, item, item_schema)


def _select_arguments(arguments: dict[str, Any], allowed_names: tuple[str, ...]) -> dict[str, Any]:
    return {name: arguments[name] for name in allowed_names if name in arguments}


def _require_arguments(arguments: dict[str, Any], required: tuple[str, ...], *, optional: tuple[str, ...] = ()) -> dict[str, Any]:
    values = _select_arguments(arguments, required + optional)
    for name in required:
        _required_string(values, name)
    return values


def _required_string(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value


def _quoted_document_id(arguments: dict[str, Any]) -> str:
    return _quote_path_component(_required_string(arguments, "document_id"))


def _quote_path_component(value: str) -> str:
    return quote(value, safe="")

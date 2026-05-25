"""MCP tool handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from momonga_search_mcp.api import JsonApiResponse, MomongaApiClient, MomongaApiError, api_error_response
from momonga_search_mcp.cache import CachedResource, CacheManager
from momonga_search_mcp.config import Config
from momonga_search_mcp.skills import get_skill, list_skills
from momonga_search_mcp.tools.definitions import (
    CREDIT_TOOLS,
    SKILL_HELPER_TOOLS,
    TOOL_ARGUMENT_ALTERNATIVES,
    ZERO_CREDIT_DOCUMENT_TOOLS,
)
from momonga_search_mcp.tools.response import (
    get_document_content_response,
    get_document_toc_response,
    success_response,
    tool_json_result,
)

DEFAULT_CONFIG = Config(api_key="")
TOOL_SCHEMAS = {**ZERO_CREDIT_DOCUMENT_TOOLS, **CREDIT_TOOLS, **SKILL_HELPER_TOOLS}
CREDIT_COSTS = {
    "list_news": 1,
    "get_document_content": 8,
    "search_documents": 1,
    "search_news": 1,
    "get_document_page_image": 1,
    "get_document_original": 8,
}
CONTENT_CREDIT_COSTS = {2, 4, 8}
FULL_DOCUMENT_SECTION_ID = "__mcp_full_document__"
SKILL_INDEX_GUARDED_TOOLS = {
    "search_issuers",
    "list_documents",
    "list_news",
    "get_document_content",
    "search_documents",
    "search_news",
}


class ToolSetupError(RuntimeError):
    """Raised when MCP server-side setup prevents a tool from running.

    Distinct from invalid tool input: the agent cannot fix this by retrying
    with different arguments. The MCP operator must fix server configuration.
    """


def call_tool(
    api_client: MomongaApiClient,
    params: Any,
    *,
    cache_manager_getter: Callable[[], CacheManager] | None = None,
    config: Config = DEFAULT_CONFIG,
    session_id: str = "default",
    skill_index_seen: bool = True,
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
    if name in SKILL_INDEX_GUARDED_TOOLS and not skill_index_seen:
        return _tool_error(
            "skill_index_required",
            f"{name} requires reading the Momonga Search skill index before substantive research.",
            next_action=(
                "First read resource skill://index.json or call list_skills. "
                "You can also load a workflow detail via get_skill (id from the index), "
                "or launch a workflow via prompts/get with use_document_research, "
                "use_news_research, or use_evidence_answering."
            ),
        )

    try:
        _validate_tool_arguments(name, arguments)
        _validate_runtime_limits(name, arguments, config)
        if name == "list_skills":
            return tool_json_result({"ok": True, "skills": list_skills()})
        if name == "get_skill":
            return tool_json_result({"ok": True, **get_skill(_required_string(arguments, "id"))})
        if name == "list_cached_resources":
            return tool_json_result(_call_list_cached_resources(arguments, cache_manager_getter))
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
            return _call_get_document_toc(api_client, arguments, cache_manager_getter, config=config)
        elif name == "list_document_page_images":
            payload = api_client.get(f"/documents/{_quoted_document_id(arguments)}/page-images")
        elif name == "list_document_originals":
            payload = api_client.get(f"/documents/{_quoted_document_id(arguments)}/originals")
        elif name == "list_news":
            params = _select_arguments(
                arguments,
                ("security_codes", "macro_tags", "timeline_since", "timeline_until", "limit", "cursor"),
            )
            payload = _call_credit_api(
                api_client.get,
                "/news",
                params,
                tool_name=name,
                cache_manager_getter=cache_manager_getter,
                session_id=session_id,
            )
        elif name == "get_document_content":
            return _call_get_document_content(api_client, arguments, cache_manager_getter, config=config, session_id=session_id)
        elif name == "search_documents":
            payload = _call_credit_api(
                api_client.post,
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
                tool_name=name,
                cache_manager_getter=cache_manager_getter,
                session_id=session_id,
            )
        elif name == "search_news":
            payload = _call_credit_api(
                api_client.post,
                "/search/news",
                _require_arguments(
                    arguments,
                    ("query",),
                    optional=("security_codes", "macro_tags", "timeline_since", "timeline_until", "match_type", "top_k"),
                ),
                tool_name=name,
                cache_manager_getter=cache_manager_getter,
                session_id=session_id,
            )
        elif name == "get_document_page_image":
            return _call_get_document_page_image(
                api_client, arguments, cache_manager_getter, config=config, session_id=session_id
            )
        elif name == "get_document_original":
            return _call_get_document_original(api_client, arguments, cache_manager_getter, config=config, session_id=session_id)
        else:
            raise ValueError(f"Unhandled tool: {name}")
    except ToolSetupError as exc:
        return _tool_error(
            "server_setup_error",
            str(exc),
            next_action=(
                "Stop and report this to the MCP operator as a server setup error. "
                "Do not retry this tool call; tool arguments will not fix it."
            ),
        )
    except ValueError as exc:
        return _validation_error(str(exc))
    except MomongaApiError as exc:
        return tool_json_result(api_error_response(exc), is_error=True)

    response = success_response(name, payload)
    return tool_json_result(response)


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


def _call_list_cached_resources(
    arguments: dict[str, Any],
    cache_manager_getter: Callable[[], CacheManager] | None,
) -> dict[str, Any]:
    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; MCP cache_dir is not configured for list_cached_resources")
    cache_manager = cache_manager_getter()
    resources = cache_manager.list_json_resources(
        limit=arguments.get("limit", 20),
        document_id=arguments.get("document_id"),
        resource_type=arguments.get("resource_type"),
    )
    return {"ok": True, "resources": resources}


def _call_get_document_toc(
    api_client: MomongaApiClient,
    arguments: dict[str, Any],
    cache_manager_getter: Callable[[], CacheManager] | None,
    *,
    config: Config,
) -> dict[str, Any]:
    document_id = _required_string(arguments, "document_id")
    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; MCP cache_dir is not configured for get_document_toc")

    cache_manager = cache_manager_getter()
    cached_toc = cache_manager.get_document_toc(document_id) if config.cache_enabled else None
    if cached_toc is not None:
        payload = cache_manager.read_json(cached_toc)
        return tool_json_result(get_document_toc_response(payload, cached_toc, cache_hit=True))

    payload = api_client.get(f"/documents/{_quote_path_component(document_id)}/toc")
    resource = (
        cache_manager.store_document_toc(document_id, payload)
        if config.cache_enabled
        else CachedResource(resource_uri=cache_manager.document_toc_uri(document_id), path=cache_manager.cache_dir)
    )
    return tool_json_result(get_document_toc_response(payload, resource, cache_hit=False))


def _call_get_document_content(
    api_client: MomongaApiClient,
    arguments: dict[str, Any],
    cache_manager_getter: Callable[[], CacheManager] | None,
    *,
    config: Config,
    session_id: str,
) -> dict[str, Any]:
    document_id = _required_string(arguments, "document_id")
    section_ids = arguments.get("section_ids", [])
    if not isinstance(section_ids, list) or not all(isinstance(item, str) and item.strip() for item in section_ids):
        raise ValueError("section_ids must be an array of strings")
    return_content = arguments.get("return_content", True)
    if not isinstance(return_content, bool):
        raise ValueError("return_content must be a boolean")
    offset = arguments.get("offset", 0)
    if offset > 0 and len(section_ids) > 1:
        raise ValueError("offset can only be used with exactly one section_id")

    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; MCP cache_dir is not configured for get_document_content")
    cache_manager = cache_manager_getter()
    requested_section_ids = section_ids or [FULL_DOCUMENT_SECTION_ID]
    if config.cache_enabled and requested_section_ids:
        cached_resources = [cache_manager.get_document_section(document_id, section_id) for section_id in requested_section_ids]
        if all(resource is not None for resource in cached_resources):
            resources = [resource for resource in cached_resources if resource is not None]
            sections = [cache_manager.read_json(resource) for resource in resources]
            response = get_document_content_response(
                document_id,
                list(zip(sections, [resource.resource_uri for resource in resources], strict=True)),
                cache_hit=True,
                cached_sections=True,
                return_content=return_content,
                max_chars=config.max_characters_per_content_call,
                offset=offset,
            )
            return tool_json_result(response)

    params = {"sections": section_ids} if section_ids else None
    endpoint = f"/documents/{_quote_path_component(document_id)}/content"
    api_response = _call_credit_json_api(
        api_client.get_with_usage,
        endpoint,
        params,
        tool_name="get_document_content",
        cache_manager_getter=cache_manager_getter,
        session_id=session_id,
        valid_actual_credits=CONTENT_CREDIT_COSTS,
    )
    payload = api_response.payload
    section_resources = []
    if section_ids and isinstance(payload.get("content_sections"), list):
        content_sections = payload["content_sections"]
        for section in content_sections:
            if not isinstance(section, dict):
                continue

            section_id = _required_string(section, "section_id")
            resource_uri = (
                cache_manager.store_document_section(document_id, section_id, section).resource_uri
                if config.cache_enabled
                else cache_manager.document_section_uri(document_id, section_id)
            )
            section_resources.append((section, resource_uri))
    elif not section_ids:
        content = payload.get("content")
        if isinstance(content, str):
            full_section = {
                "section_id": FULL_DOCUMENT_SECTION_ID,
                "section_title": "Full document",
                "character_count": payload.get("character_count", len(content)),
                "content": content,
            }
            resource_uri = (
                cache_manager.store_document_section(document_id, FULL_DOCUMENT_SECTION_ID, full_section).resource_uri
                if config.cache_enabled
                else cache_manager.document_section_uri(document_id, FULL_DOCUMENT_SECTION_ID)
            )
            section_resources.append((full_section, resource_uri))

    response = get_document_content_response(
        document_id,
        section_resources,
        cache_hit=False,
        cached_sections=False,
        return_content=return_content,
        max_chars=config.max_characters_per_content_call,
        offset=offset,
    )
    return tool_json_result(response)


def _call_get_document_page_image(
    api_client: MomongaApiClient,
    arguments: dict[str, Any],
    cache_manager_getter: Callable[[], CacheManager] | None,
    *,
    config: Config,
    session_id: str,
) -> dict[str, Any]:
    _require_download_flags(arguments)
    document_id = _required_string(arguments, "document_id")
    page_number = arguments["page_number"]
    if type(page_number) is not int or page_number < 1:
        raise ValueError("page_number must be greater than or equal to 1")
    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; MCP cache_dir is not configured for get_document_page_image")

    cache_manager = cache_manager_getter()
    cached = cache_manager.get_page_image(document_id, page_number) if config.cache_enabled else None
    if cached is not None:
        response = _download_response(
            "get_document_page_image",
            document_id=document_id,
            resource_uri=cached.resource_uri,
            file_path=cached.path,
            cached=True,
            page_number=page_number,
            media_type="image/jpeg",
        )
        cache_manager.record_api_call(
            tool_name="get_document_page_image",
            endpoint=f"/documents/{_quote_path_component(document_id)}/pages/{page_number}/image",
            cache_hit=True,
            credits_used=0,
        )
        return tool_json_result(response)

    endpoint = f"/documents/{_quote_path_component(document_id)}/pages/{page_number}/image"
    binary_response = _call_credit_binary_api(
        api_client.get_binary,
        endpoint,
        tool_name="get_document_page_image",
        cache_manager_getter=cache_manager_getter,
        session_id=session_id,
    )
    image_bytes = binary_response.content
    resource = cache_manager.store_page_image(
        document_id,
        page_number,
        image_bytes,
        media_type="image/jpeg",
    )
    response = _download_response(
        "get_document_page_image",
        document_id=document_id,
        resource_uri=resource.resource_uri,
        file_path=resource.path,
        cached=False,
        page_number=page_number,
        media_type="image/jpeg",
    )
    return tool_json_result(response)


def _call_get_document_original(
    api_client: MomongaApiClient,
    arguments: dict[str, Any],
    cache_manager_getter: Callable[[], CacheManager] | None,
    *,
    config: Config,
    session_id: str,
) -> dict[str, Any]:
    _require_download_flags(arguments)
    document_id = _required_string(arguments, "document_id")
    original_id = _required_string(arguments, "original_id")
    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; MCP cache_dir is not configured for get_document_original")

    cache_manager = cache_manager_getter()
    cached = cache_manager.get_original_file(document_id, original_id) if config.cache_enabled else None
    if cached is not None:
        metadata = cache_manager.read_json(
            CachedResource(resource_uri=cached.resource_uri, path=cached.path.with_name("metadata.json"))
        )
        response = _download_response(
            "get_document_original",
            document_id=document_id,
            resource_uri=cached.resource_uri,
            file_path=cached.path,
            cached=True,
            original_id=original_id,
            media_type=str(metadata.get("media_type") or "application/octet-stream"),
            filename=str(metadata.get("filename") or cached.path.name),
        )
        cache_manager.record_api_call(
            tool_name="get_document_original",
            endpoint=f"/documents/{_quote_path_component(document_id)}/originals/{_quote_path_component(original_id)}",
            cache_hit=True,
            credits_used=0,
        )
        return tool_json_result(response)

    endpoint = f"/documents/{_quote_path_component(document_id)}/originals/{_quote_path_component(original_id)}"
    binary_response = _call_credit_binary_api(
        api_client.get_binary,
        endpoint,
        tool_name="get_document_original",
        cache_manager_getter=cache_manager_getter,
        session_id=session_id,
    )
    file_bytes = binary_response.content
    filename = binary_response.filename
    media_type = binary_response.media_type
    if not filename or media_type == "application/octet-stream":
        original_manifest = _original_manifest_entry(api_client, document_id, original_id)
        if not filename:
            manifest_filename = original_manifest.get("filename")
            if not isinstance(manifest_filename, str) or not manifest_filename.strip():
                raise ValueError("list_document_originals did not return filename for original_id")
            filename = manifest_filename.strip()

        manifest_media_type = original_manifest.get("media_type")
        if media_type == "application/octet-stream" and isinstance(manifest_media_type, str) and manifest_media_type.strip():
            media_type = manifest_media_type
    resource = cache_manager.store_original_file(
        document_id,
        original_id,
        file_bytes,
        filename=filename,
        media_type=media_type,
    )
    response = _download_response(
        "get_document_original",
        document_id=document_id,
        resource_uri=resource.resource_uri,
        file_path=resource.path,
        cached=False,
        original_id=original_id,
        media_type=media_type,
        filename=filename,
    )
    return tool_json_result(response)


def _call_credit_api(
    api_call: Callable[..., dict[str, Any]],
    endpoint: str,
    payload: dict[str, Any],
    *,
    tool_name: str,
    cache_manager_getter: Callable[[], CacheManager] | None,
    session_id: str,
) -> dict[str, Any]:
    credits = CREDIT_COSTS[tool_name]
    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; credit accounting cannot proceed without MCP cache_dir")

    cache_manager = cache_manager_getter()

    response = api_call(endpoint, payload)
    cache_manager.record_session_credits(session_id, credits)
    cache_manager.record_api_call(tool_name=tool_name, endpoint=endpoint, cache_hit=False, credits_used=credits)
    return response


def _call_credit_json_api(
    api_call: Callable[..., JsonApiResponse],
    endpoint: str,
    payload: dict[str, Any],
    *,
    tool_name: str,
    cache_manager_getter: Callable[[], CacheManager] | None,
    session_id: str,
    valid_actual_credits: set[int] | None = None,
) -> JsonApiResponse:
    max_credits = CREDIT_COSTS[tool_name]
    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; credit accounting cannot proceed without MCP cache_dir")

    cache_manager = cache_manager_getter()

    response = api_call(endpoint, payload)
    actual_credits = response.inferred_compute_credits
    if actual_credits is None or (valid_actual_credits is not None and actual_credits not in valid_actual_credits):
        actual_credits = max_credits
    cache_manager.record_session_credits(session_id, actual_credits)
    cache_manager.record_api_call(tool_name=tool_name, endpoint=endpoint, cache_hit=False, credits_used=actual_credits)
    return response


def _call_credit_binary_api(
    api_call: Callable[..., Any],
    endpoint: str,
    *,
    tool_name: str,
    cache_manager_getter: Callable[[], CacheManager] | None,
    session_id: str,
) -> Any:
    credits = CREDIT_COSTS[tool_name]
    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; credit accounting cannot proceed without MCP cache_dir")

    cache_manager = cache_manager_getter()

    response = api_call(endpoint)
    cache_manager.record_session_credits(session_id, credits)
    cache_manager.record_api_call(tool_name=tool_name, endpoint=endpoint, cache_hit=False, credits_used=credits)
    return response


def _require_download_flags(arguments: dict[str, Any]) -> None:
    if arguments.get("allow_file_download") is not True:
        raise ValueError("allow_file_download must be true for file download tools")


def _download_response(
    tool_name: str,
    *,
    document_id: str,
    resource_uri: str,
    file_path: Any,
    cached: bool,
    page_number: int | None = None,
    original_id: str | None = None,
    media_type: str,
    filename: str | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "ok": True,
        "document_id": document_id,
        "file_path": str(file_path),
        "resource_uri": resource_uri,
        "media_type": media_type,
        "cached": cached,
    }
    if tool_name == "get_document_page_image":
        response["page_number"] = page_number
    if tool_name == "get_document_original":
        response["original_id"] = original_id
        response["filename"] = filename
    return response


def _original_manifest_entry(
    api_client: MomongaApiClient,
    document_id: str,
    original_id: str,
) -> dict[str, Any]:
    payload = api_client.get(f"/documents/{_quote_path_component(document_id)}/originals")
    originals = payload.get("originals")
    if not isinstance(originals, list):
        raise ValueError("list_document_originals returned no originals array")
    for item in originals:
        if isinstance(item, dict) and item.get("original_id") == original_id:
            return item
    raise ValueError("original_id was not returned by list_document_originals")


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

    any_of = TOOL_ARGUMENT_ALTERNATIVES.get(tool_name)
    if isinstance(any_of, list) and not any(
        all(_has_present_value(arguments, required_name) for required_name in option.get("required", [])) for option in any_of
    ):
        alternatives = [" + ".join(option.get("required", [])) for option in any_of]
        raise ValueError(f"one of these argument sets is required: {' or '.join(alternatives)}")

    for name, value in arguments.items():
        _validate_argument_value(name, value, properties[name])


def _validate_runtime_limits(tool_name: str, arguments: dict[str, Any], config: Config) -> None:
    limit = arguments.get("limit")
    if tool_name in {"search_issuers", "list_documents", "list_news"} and isinstance(limit, int):
        if limit > config.max_list_limit:
            raise ValueError(f"limit must be less than or equal to {config.max_list_limit}")

    top_k = arguments.get("top_k")
    if tool_name in {"search_documents", "search_news"} and isinstance(top_k, int):
        if top_k > config.max_search_top_k:
            raise ValueError(f"top_k must be less than or equal to {config.max_search_top_k}")

    section_ids = arguments.get("section_ids")
    if tool_name == "get_document_content" and isinstance(section_ids, list):
        if len(section_ids) > config.max_sections_per_content_call:
            raise ValueError(f"section_ids must contain at most {config.max_sections_per_content_call} items")


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

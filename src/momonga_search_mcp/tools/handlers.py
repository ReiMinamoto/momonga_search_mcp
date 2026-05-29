"""MCP tool handlers."""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from typing import Any
import unicodedata
from urllib.parse import quote
from uuid import uuid4

from momonga_search_mcp.api import MomongaApiClient, MomongaApiError, api_error_response
from momonga_search_mcp.cache import CachedResource, CacheManager
from momonga_search_mcp.config import MCP_PROTOCOL_VERSION, SERVER_NAME, SERVER_VERSION, Config
from momonga_search_mcp.skills import get_skill, list_skills
from momonga_search_mcp.tools.definitions import (
    DOCUMENT_LOOKUP_TOOLS,
    RETRIEVAL_TOOLS,
    SKILL_HELPER_TOOLS,
    TOOL_ARGUMENT_ALTERNATIVES,
)
from momonga_search_mcp.tools.response import (
    get_document_content_response,
    get_document_toc_response,
    success_response,
    tool_json_result,
)

DEFAULT_CONFIG = Config(api_key="")
TOOL_SCHEMAS = {**DOCUMENT_LOOKUP_TOOLS, **RETRIEVAL_TOOLS, **SKILL_HELPER_TOOLS}
FULL_DOCUMENT_SECTION_ID = "__mcp_full_document__"
DEFAULT_SECTION_SEARCH_CONTEXT_CHARS = 300
DEFAULT_SECTION_SEARCH_MAX_MATCHES = 5
DEFAULT_SECTION_WINDOW_CHARACTERS = 1500
SKILL_INDEX_GUARDED_TOOLS = {
    "search_issuers",
    "list_documents",
    "list_news",
    "get_document_content",
    "search_section_contents",
    "get_section_window",
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
        if name == "diagnose_setup":
            return tool_json_result(_call_diagnose_setup(config))
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
            return _call_get_document_toc(api_client, arguments, cache_manager_getter)
        elif name == "list_document_page_images":
            payload = api_client.get(f"/documents/{_quoted_document_id(arguments)}/page-images")
        elif name == "list_document_originals":
            payload = api_client.get(f"/documents/{_quoted_document_id(arguments)}/originals")
        elif name == "list_news":
            params = _select_arguments(
                arguments,
                ("security_codes", "macro_tags", "timeline_since", "timeline_until", "limit", "cursor"),
            )
            payload = api_client.get("/news", params)
        elif name == "get_document_content":
            return _call_get_document_content(api_client, arguments, cache_manager_getter, config=config)
        elif name == "search_section_contents":
            return tool_json_result(_call_search_section_contents(arguments, cache_manager_getter))
        elif name == "get_section_window":
            return tool_json_result(_call_get_section_window(arguments, cache_manager_getter))
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
        elif name == "get_document_page_image":
            return _call_get_document_page_image(api_client, arguments, cache_manager_getter)
        elif name == "get_document_original":
            return _call_get_document_original(api_client, arguments, cache_manager_getter)
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


def _call_search_section_contents(
    arguments: dict[str, Any],
    cache_manager_getter: Callable[[], CacheManager] | None,
) -> dict[str, Any]:
    document_id = _required_string(arguments, "document_id")
    section_id = _required_string(arguments, "section_id")
    query = _required_string(arguments, "query").strip()
    match_type = arguments.get("match_type", "lexical")
    if match_type != "lexical":
        raise ValueError("match_type must be lexical")
    context_chars = arguments.get("context_chars", DEFAULT_SECTION_SEARCH_CONTEXT_CHARS)
    max_matches = arguments.get("max_matches", DEFAULT_SECTION_SEARCH_MAX_MATCHES)
    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; MCP cache_dir is not configured for search_section_contents")

    cache_manager = cache_manager_getter()
    resource = cache_manager.get_document_section(document_id, section_id)
    if resource is None:
        raise ValueError(
            "section content is not cached; call get_document_content with this document_id and section_id before searching"
        )
    section = cache_manager.read_json(resource)
    content = section.get("content")
    if not isinstance(content, str):
        raise ValueError("cached section does not contain searchable text content")

    matches = _section_lexical_matches(content, query, context_chars=context_chars, max_matches=max_matches)
    return {
        "ok": True,
        "document_id": document_id,
        "section_id": section_id,
        **_section_metadata(section),
        "match_type": "lexical",
        "query": query,
        "context_chars": context_chars,
        "max_matches": max_matches,
        "matches": matches,
        "source_resource_uri": resource.resource_uri,
        "cache_hit": True,
    }


def _call_get_section_window(
    arguments: dict[str, Any],
    cache_manager_getter: Callable[[], CacheManager] | None,
) -> dict[str, Any]:
    document_id = _required_string(arguments, "document_id")
    section_id = _required_string(arguments, "section_id")
    offset = arguments["offset"]
    max_characters = arguments.get("max_characters", DEFAULT_SECTION_WINDOW_CHARACTERS)
    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; MCP cache_dir is not configured for get_section_window")

    cache_manager = cache_manager_getter()
    resource = cache_manager.get_document_section(document_id, section_id)
    if resource is None:
        raise ValueError(
            "section content is not cached; call get_document_content with this document_id and section_id before reading a window"
        )
    section = cache_manager.read_json(resource)
    content = section.get("content")
    if not isinstance(content, str):
        raise ValueError("cached section does not contain window-readable text content")

    bounded_offset = min(offset, len(content))
    half_window = max_characters // 2
    start_offset = max(0, bounded_offset - half_window)
    end_offset = min(len(content), start_offset + max_characters)
    if end_offset - start_offset < max_characters:
        start_offset = max(0, end_offset - max_characters)
    window = content[start_offset:end_offset]
    return {
        "ok": True,
        "document_id": document_id,
        "section_id": section_id,
        **_section_metadata(section),
        "offset": offset,
        "start_offset": start_offset,
        "end_offset": end_offset,
        "actual_characters": len(window),
        "max_characters": max_characters,
        "content": window,
        "truncated": start_offset > 0 or end_offset < len(content),
        "source_resource_uri": resource.resource_uri,
        "cache_hit": True,
    }


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


def _call_diagnose_setup(config: Config) -> dict[str, Any]:
    try:
        server_version = version(SERVER_NAME)
    except PackageNotFoundError:
        server_version = SERVER_VERSION

    try:
        config.cache_dir.mkdir(parents=True, exist_ok=True)
        probe = config.cache_dir / f".diagnose-{uuid4().hex}.tmp"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        cache_writable = True
    except OSError:
        cache_writable = False

    return {
        "ok": True,
        "api_key_configured": bool(config.api_key.strip()),
        "base_url": config.base_url,
        "cache_dir": str(config.cache_dir),
        "cache_writable": cache_writable,
        "server_name": SERVER_NAME,
        "server_version": server_version,
        "protocol_version": MCP_PROTOCOL_VERSION,
    }


def _call_get_document_toc(
    api_client: MomongaApiClient,
    arguments: dict[str, Any],
    cache_manager_getter: Callable[[], CacheManager] | None,
) -> dict[str, Any]:
    document_id = _required_string(arguments, "document_id")
    path_prefix = arguments.get("path_prefix")
    max_depth = arguments.get("max_depth", 2)
    include_sections = arguments.get("include_sections", False)
    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; MCP cache_dir is not configured for get_document_toc")

    cache_manager = cache_manager_getter()
    cached_toc = cache_manager.get_document_toc(document_id)
    if cached_toc is not None:
        payload = cache_manager.read_json(cached_toc)
        return tool_json_result(
            get_document_toc_response(
                payload,
                cached_toc,
                cache_hit=True,
                path_prefix=path_prefix if isinstance(path_prefix, list) else None,
                max_depth=max_depth if type(max_depth) is int else 2,
                include_sections=include_sections if type(include_sections) is bool else False,
            )
        )

    payload = api_client.get(f"/documents/{_quote_path_component(document_id)}/toc")
    resource = cache_manager.store_document_toc(document_id, payload)
    return tool_json_result(
        get_document_toc_response(
            payload,
            resource,
            cache_hit=False,
            path_prefix=path_prefix if isinstance(path_prefix, list) else None,
            max_depth=max_depth if type(max_depth) is int else 2,
            include_sections=include_sections if type(include_sections) is bool else False,
        )
    )


def _call_get_document_content(
    api_client: MomongaApiClient,
    arguments: dict[str, Any],
    cache_manager_getter: Callable[[], CacheManager] | None,
    *,
    config: Config,
) -> dict[str, Any]:
    document_id = _required_string(arguments, "document_id")
    section_ids = arguments.get("section_ids", [])
    if not isinstance(section_ids, list) or not all(isinstance(item, str) and item.strip() for item in section_ids):
        raise ValueError("section_ids must be an array of strings")
    allow_full_document = arguments.get("allow_full_document", False)
    if not section_ids and allow_full_document is not True:
        raise ValueError("allow_full_document=true is required when section_ids is omitted")
    return_content = arguments.get("return_content", True)
    if not isinstance(return_content, bool):
        raise ValueError("return_content must be a boolean")

    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; MCP cache_dir is not configured for get_document_content")
    cache_manager = cache_manager_getter()
    requested_section_ids = section_ids or [FULL_DOCUMENT_SECTION_ID]
    if requested_section_ids:
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
                requested_section_ids=section_ids or None,
            )
            return tool_json_result(response)

    params = {"sections": section_ids} if section_ids else None
    endpoint = f"/documents/{_quote_path_component(document_id)}/content"
    payload = api_client.get(endpoint, params)
    section_resources = []
    missing_section_ids = []
    if section_ids and isinstance(payload.get("content_sections"), list):
        content_sections = payload["content_sections"]
        for section in content_sections:
            if not isinstance(section, dict):
                continue

            section_id = _required_string(section, "section_id")
            resource_uri = cache_manager.store_document_section(document_id, section_id, section).resource_uri
            section_resources.append((section, resource_uri))
        returned_section_ids = {
            section.get("section_id")
            for section, _resource_uri in section_resources
            if isinstance(section.get("section_id"), str)
        }
        missing_section_ids = [section_id for section_id in section_ids if section_id not in returned_section_ids]
        if not section_resources:
            raise ValueError(f"requested section_ids were not returned: {', '.join(missing_section_ids or section_ids)}")
    elif section_ids:
        missing_section_ids = list(section_ids)
        raise ValueError(f"requested section_ids were not returned: {', '.join(missing_section_ids)}")
    elif not section_ids:
        content = payload.get("content")
        if isinstance(content, str):
            full_section = {
                "section_id": FULL_DOCUMENT_SECTION_ID,
                "section_title": "Full document",
                "character_count": payload.get("character_count", len(content)),
                "content": content,
            }
            resource_uri = cache_manager.store_document_section(document_id, FULL_DOCUMENT_SECTION_ID, full_section).resource_uri
            section_resources.append((full_section, resource_uri))

    response = get_document_content_response(
        document_id,
        section_resources,
        cache_hit=False,
        cached_sections=False,
        return_content=return_content,
        requested_section_ids=section_ids or None,
        missing_section_ids=missing_section_ids,
    )
    return tool_json_result(response)


def _call_get_document_page_image(
    api_client: MomongaApiClient,
    arguments: dict[str, Any],
    cache_manager_getter: Callable[[], CacheManager] | None,
) -> dict[str, Any]:
    _require_download_flags(arguments)
    document_id = _required_string(arguments, "document_id")
    page_number = arguments["page_number"]
    if type(page_number) is not int or page_number < 1:
        raise ValueError("page_number must be greater than or equal to 1")
    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; MCP cache_dir is not configured for get_document_page_image")

    cache_manager = cache_manager_getter()
    cached = cache_manager.get_page_image(document_id, page_number)
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
        return tool_json_result(response)

    endpoint = f"/documents/{_quote_path_component(document_id)}/pages/{page_number}/image"
    binary_response = api_client.get_binary(endpoint)
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
) -> dict[str, Any]:
    _require_download_flags(arguments)
    document_id = _required_string(arguments, "document_id")
    original_id = _required_string(arguments, "original_id")
    if cache_manager_getter is None:
        raise ToolSetupError("cache manager is unavailable; MCP cache_dir is not configured for get_document_original")

    cache_manager = cache_manager_getter()
    cached = cache_manager.get_original_file(document_id, original_id)
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
        return tool_json_result(response)

    endpoint = f"/documents/{_quote_path_component(document_id)}/originals/{_quote_path_component(original_id)}"
    binary_response = api_client.get_binary(endpoint)
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


def _section_metadata(section: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    section_title = section.get("section_title")
    if isinstance(section_title, str):
        metadata["section_title"] = section_title
    heading_path = section.get("heading_path")
    if isinstance(heading_path, list):
        metadata["heading_path"] = [item for item in heading_path if isinstance(item, str)]
    return metadata


def _section_lexical_matches(
    content: str,
    query: str,
    *,
    context_chars: int,
    max_matches: int,
) -> list[dict[str, Any]]:
    matches = []
    normalized_content, offset_map = _normalize_search_text_with_offsets(content)
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return matches
    search_from = 0
    while len(matches) < max_matches:
        normalized_offset = normalized_content.find(normalized_query, search_from)
        if normalized_offset == -1:
            break
        normalized_match_end = normalized_offset + len(normalized_query)
        offset = offset_map[normalized_offset]
        match_end = offset_map[normalized_match_end - 1] + 1
        excerpt_start = max(0, offset - context_chars)
        excerpt_end = min(len(content), match_end + context_chars)
        matches.append(
            {
                "offset": offset,
                "excerpt": content[excerpt_start:excerpt_end],
                "matched_text": content[offset:match_end],
            }
        )
        search_from = normalized_match_end
    return matches


def _normalize_search_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _normalize_search_text_with_offsets(value: str) -> tuple[str, list[int]]:
    normalized_parts = []
    offset_map = []
    for original_offset, character in enumerate(value):
        normalized = _normalize_search_text(character)
        if not normalized:
            continue
        normalized_parts.append(normalized)
        offset_map.extend([original_offset] * len(normalized))
    return "".join(normalized_parts), offset_map


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

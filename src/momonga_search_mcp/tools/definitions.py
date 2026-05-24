"""MCP tool catalog definitions."""

from __future__ import annotations

from typing import Any

MACRO_TAGS = [
    "Economic Indicators",
    "Monetary Policy",
    "Fiscal Policy",
    "Regulatory Policy",
    "Trade & Geopolitical Events",
    "Financial Stability",
    "External Shocks",
]

LIST_LIMIT_SCHEMA = {
    "type": "integer",
    "minimum": 1,
    "maximum": 50,
    "description": "Number of items to return. API maximum is 50; MCP default runtime limit is 20.",
}

TOP_K_SCHEMA = {
    "type": "integer",
    "minimum": 1,
    "maximum": 50,
    "description": "Number of search results to return. API maximum is 50; MCP default runtime limit is 10.",
}

COMMON_ERROR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "code": {"type": "string"},
        "status": {"type": ["integer", "null"]},
        "message": {"type": "string"},
        "next_action": {"type": "string"},
        "retry_after_seconds": {"type": "integer"},
    },
    "required": ["code", "message"],
    "additionalProperties": True,
}

BASE_OUTPUT_PROPERTIES: dict[str, Any] = {
    "ok": {"type": "boolean"},
    "error": COMMON_ERROR_SCHEMA,
}

RESOURCE_OUTPUT_PROPERTIES: dict[str, Any] = {
    "cache_hit": {"type": "boolean"},
    "cached": {"type": "boolean"},
    "resource_uri": {"type": "string"},
}

TOOL_TITLES = {
    "search_issuers": "Search Issuers",
    "list_documents": "List Documents",
    "get_document_metadata": "Get Document Metadata",
    "get_document_toc": "Get Document TOC",
    "list_document_page_images": "List Document Page Images",
    "list_document_originals": "List Document Originals",
    "list_news": "List News",
    "get_document_content": "Get Document Content",
    "get_document_original": "Get Document Original",
    "get_document_page_image": "Get Document Page Image",
    "search_documents": "Search Documents",
    "search_news": "Search News",
    "list_skills": "List Skills",
    "get_skill": "Get Skill",
    "list_cached_resources": "List Cached Resources",
}

OPEN_WORLD_READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "openWorldHint": True,
}

LOCAL_READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "openWorldHint": False,
}

TOOL_ANNOTATIONS = {
    "search_issuers": OPEN_WORLD_READ_ONLY_ANNOTATIONS,
    "list_documents": OPEN_WORLD_READ_ONLY_ANNOTATIONS,
    "get_document_metadata": OPEN_WORLD_READ_ONLY_ANNOTATIONS,
    "get_document_toc": OPEN_WORLD_READ_ONLY_ANNOTATIONS,
    "list_document_page_images": OPEN_WORLD_READ_ONLY_ANNOTATIONS,
    "list_document_originals": OPEN_WORLD_READ_ONLY_ANNOTATIONS,
    "list_news": OPEN_WORLD_READ_ONLY_ANNOTATIONS,
    "get_document_content": OPEN_WORLD_READ_ONLY_ANNOTATIONS,
    "get_document_original": OPEN_WORLD_READ_ONLY_ANNOTATIONS,
    "get_document_page_image": OPEN_WORLD_READ_ONLY_ANNOTATIONS,
    "search_documents": OPEN_WORLD_READ_ONLY_ANNOTATIONS,
    "search_news": OPEN_WORLD_READ_ONLY_ANNOTATIONS,
    "list_skills": LOCAL_READ_ONLY_ANNOTATIONS,
    "get_skill": LOCAL_READ_ONLY_ANNOTATIONS,
    "list_cached_resources": LOCAL_READ_ONLY_ANNOTATIONS,
}

# OpenAI/Codex-compatible tool schemas cannot use top-level anyOf. Enforce these at runtime instead.
TOOL_ARGUMENT_ALTERNATIVES: dict[str, list[dict[str, list[str]]]] = {
    "list_documents": [{"required": ["security_codes"]}, {"required": ["timeline_since"]}],
    "list_news": [
        {"required": ["security_codes"]},
        {"required": ["macro_tags"]},
        {"required": ["timeline_since"]},
    ],
}

ZERO_CREDIT_DOCUMENT_TOOLS: dict[str, dict[str, Any]] = {
    "search_issuers": {
        "description": "Search issuers by company name or security code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Company name or security code."},
                "limit": LIST_LIMIT_SCHEMA,
            },
            "required": ["q"],
            "additionalProperties": False,
        },
    },
    "list_documents": {
        "description": (
            "List document summaries, newest first by timeline_at. "
            "Provide security_codes or timeline_since (required when security_codes is omitted)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "security_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Security code filters. Required unless timeline_since is provided.",
                },
                "document_types": {"type": "array", "items": {"type": "string", "enum": ["yuho", "tanshin", "other"]}},
                "document_families": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["edinet_filing", "timely_disclosure", "ir_material"]},
                },
                "timeline_since": {
                    "type": "string",
                    "description": ("Inclusive start date filter in JST, YYYY-MM-DD. Required when security_codes is omitted."),
                },
                "timeline_until": {"type": "string", "description": "Inclusive end date filter in JST, YYYY-MM-DD."},
                "limit": LIST_LIMIT_SCHEMA,
                "cursor": {
                    "type": "string",
                    "description": "Pagination cursor from the previous response's next_cursor. Use with the same filters.",
                },
            },
            "additionalProperties": False,
        },
    },
    "get_document_metadata": {
        "description": "Get document metadata and availability. Check content_status before content retrieval.",
        "inputSchema": {
            "type": "object",
            "properties": {"document_id": {"type": "string"}},
            "required": ["document_id"],
            "additionalProperties": False,
        },
    },
    "get_document_toc": {
        "description": "Get content section IDs, heading paths, and character counts for content_status=ready documents.",
        "inputSchema": {
            "type": "object",
            "properties": {"document_id": {"type": "string"}},
            "required": ["document_id"],
            "additionalProperties": False,
        },
    },
    "list_document_page_images": {
        "description": "List page numbers available for image retrieval.",
        "inputSchema": {
            "type": "object",
            "properties": {"document_id": {"type": "string"}},
            "required": ["document_id"],
            "additionalProperties": False,
        },
    },
    "list_document_originals": {
        "description": "List original files available for retrieval.",
        "inputSchema": {
            "type": "object",
            "properties": {"document_id": {"type": "string"}},
            "required": ["document_id"],
            "additionalProperties": False,
        },
    },
}

CREDIT_TOOLS: dict[str, dict[str, Any]] = {
    "list_news": {
        "description": (
            "List news statements with references. Provide at least one of security_codes, macro_tags, or timeline_since."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "security_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Security code filters.",
                },
                "macro_tags": {
                    "type": "array",
                    "items": {"type": "string", "enum": MACRO_TAGS},
                    "description": "Macro tag filters. At least one filter field is required.",
                },
                "timeline_since": {
                    "type": "string",
                    "description": (
                        "Inclusive start date filter in JST, YYYY-MM-DD. "
                        "At least one of security_codes, macro_tags, or timeline_since is required."
                    ),
                },
                "timeline_until": {"type": "string", "description": "Inclusive end date filter in JST, YYYY-MM-DD."},
                "limit": LIST_LIMIT_SCHEMA,
                "cursor": {
                    "type": "string",
                    "description": "Pagination cursor from the previous response's next_cursor. Use with the same filters.",
                },
            },
            "additionalProperties": False,
        },
    },
    "get_document_content": {
        "description": (
            "Retrieve selected document sections. Only use after get_document_toc or search_documents returns section IDs. "
            "Returns at most the MCP runtime character limit per call; use next_offset with the same single section_id to continue."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "section_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 5,
                    "description": (
                        "Required section IDs from get_document_toc or search_documents. "
                        "API maximum is 5; MCP default runtime limit is 3."
                    ),
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "description": (
                        "Character offset for continuing a truncated section. "
                        "Omit unless a previous response returned next_offset. "
                        "When offset is greater than 0, pass exactly one section_id."
                    ),
                },
                "return_content": {
                    "type": "boolean",
                    "description": "Whether to include retrieved content in the tool response. Defaults to true.",
                },
            },
            "required": ["document_id", "section_ids"],
            "additionalProperties": False,
        },
    },
    "get_document_original": {
        "description": "Download one original file to the local cache. Requires allow_file_download=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "original_id": {"type": "string"},
                "allow_file_download": {"type": "boolean"},
            },
            "required": ["document_id", "original_id", "allow_file_download"],
            "additionalProperties": False,
        },
    },
    "get_document_page_image": {
        "description": "Download one page image to the local cache. Requires allow_file_download=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "page_number": {"type": "integer", "minimum": 1},
                "allow_file_download": {"type": "boolean"},
            },
            "required": ["document_id", "page_number", "allow_file_download"],
            "additionalProperties": False,
        },
    },
    "search_documents": {
        "description": "Search document content. Use short topic terms or evidence-focused questions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "security_codes": {"type": "array", "items": {"type": "string"}},
                "document_types": {"type": "array", "items": {"type": "string", "enum": ["yuho", "tanshin", "other"]}},
                "document_families": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["edinet_filing", "timely_disclosure"]},
                },
                "timeline_since": {"type": "string", "description": "Inclusive start date filter in JST, YYYY-MM-DD."},
                "timeline_until": {"type": "string", "description": "Inclusive end date filter in JST, YYYY-MM-DD."},
                "match_type": {
                    "type": "string",
                    "enum": ["semantic", "lexical"],
                    "description": "Search mode. Use lexical for short keyword matching.",
                },
                "top_k": TOP_K_SCHEMA,
                "include_snippet": {
                    "type": "boolean",
                    "description": "Whether to include short matching excerpts in search results.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "search_news": {
        "description": "Search news statements. Keep news separate from document search in the MVP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "security_codes": {"type": "array", "items": {"type": "string"}},
                "macro_tags": {"type": "array", "items": {"type": "string", "enum": MACRO_TAGS}},
                "timeline_since": {"type": "string", "description": "Inclusive start date filter in JST, YYYY-MM-DD."},
                "timeline_until": {"type": "string", "description": "Inclusive end date filter in JST, YYYY-MM-DD."},
                "match_type": {
                    "type": "string",
                    "enum": ["semantic", "lexical"],
                    "description": "Search mode. Use lexical for short keyword matching.",
                },
                "top_k": TOP_K_SCHEMA,
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

SKILL_HELPER_TOOLS: dict[str, dict[str, Any]] = {
    "list_skills": {
        "description": "Return the lightweight skill index as a fallback when resource discovery is weak.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    "get_skill": {
        "description": "Return a workflow skill detail resource by skill id.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Skill id from skill://index.json or list_skills."}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    "list_cached_resources": {
        "description": (
            "List cached Momonga resources with optional filters. "
            "Use document_id and resource_type to find cached document TOCs, sections, page metadata, or originals."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Filter to cached resources under one document_id."},
                "resource_type": {
                    "type": "string",
                    "enum": ["toc", "section", "page", "original"],
                    "description": "Filter by cached resource kind.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "description": "Maximum cached resources to return. API schema maximum is 50; MCP default is 20.",
                },
            },
            "additionalProperties": False,
        },
    },
}


def tool_definitions() -> list[dict[str, Any]]:
    tools = {**ZERO_CREDIT_DOCUMENT_TOOLS, **CREDIT_TOOLS, **SKILL_HELPER_TOOLS}
    return [
        {
            "name": name,
            "title": TOOL_TITLES[name],
            "description": definition["description"],
            "inputSchema": definition["inputSchema"],
            "outputSchema": _tool_output_schema(name),
            "annotations": TOOL_ANNOTATIONS[name],
        }
        for name, definition in tools.items()
    ]


def _tool_output_schema(tool_name: str) -> dict[str, Any]:
    properties: dict[str, Any] = dict(BASE_OUTPUT_PROPERTIES)
    required = ["ok"]

    if tool_name in {"search_issuers", "list_documents", "list_news", "search_documents", "search_news"}:
        properties["results"] = {"type": "array", "items": {"type": "object", "additionalProperties": True}}
        properties["next_cursor"] = {"type": "string"}

    if tool_name == "get_document_metadata":
        properties.update(
            {
                "document_id": {"type": "string"},
                "document_family": {"type": "string"},
                "title": {"type": "string"},
                "document_type": {"type": "string"},
                "issuers": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "timeline_at": {"type": "string"},
                "content_status": {"type": "string"},
                "reference_url": {"type": "string"},
            }
        )

    if tool_name == "list_document_page_images":
        properties.update(
            {
                "document_id": {"type": "string"},
                "page_count": {"type": "integer"},
                "page_image_count": {"type": "integer"},
                "page_images": {"type": "array", "items": {"type": "integer"}},
            }
        )

    if tool_name == "list_document_originals":
        properties.update(
            {
                "document_id": {"type": "string"},
                "originals": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            }
        )

    if tool_name == "get_document_toc":
        properties.update(
            {
                "document_id": {"type": "string"},
                "toc": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                **RESOURCE_OUTPUT_PROPERTIES,
            }
        )

    if tool_name == "get_document_content":
        properties.update(
            {
                "document_id": {"type": "string"},
                "content_sections": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "max_characters": {"type": "integer"},
                "character_limit_reached": {"type": "boolean"},
                **RESOURCE_OUTPUT_PROPERTIES,
            }
        )

    if tool_name in {"get_document_page_image", "get_document_original"}:
        properties.update(
            {
                "document_id": {"type": "string"},
                "file_path": {"type": "string"},
                "media_type": {"type": "string"},
                "page_number": {"type": "integer"},
                "original_id": {"type": "string"},
                "filename": {"type": "string"},
                **RESOURCE_OUTPUT_PROPERTIES,
            }
        )

    if tool_name == "list_cached_resources":
        properties["resources"] = {"type": "array", "items": {"type": "object", "additionalProperties": True}}

    if tool_name == "list_skills":
        properties["skills"] = {"type": "array", "items": {"type": "object", "additionalProperties": True}}

    if tool_name == "get_skill":
        properties.update(
            {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "resource_uri": {"type": "string"},
                "content": {"type": "string"},
            }
        )

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }

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
    "maximum": 25,
    "description": "Number of items to return. MCP runtime limit is 25.",
}

TOP_K_SCHEMA = {
    "type": "integer",
    "minimum": 1,
    "maximum": 25,
    "description": "Number of search results to return. MCP runtime limit is 25.",
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
    "search_section_contents": "Search Section Contents",
    "get_section_window": "Get Section Window",
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
    "search_section_contents": LOCAL_READ_ONLY_ANNOTATIONS,
    "get_section_window": LOCAL_READ_ONLY_ANNOTATIONS,
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

DOCUMENT_LOOKUP_TOOLS: dict[str, dict[str, Any]] = {
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
        "description": "Get a compact TOC outline or a focused subtree for content_status=ready documents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "path_prefix": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional heading path prefix used to return only the matching TOC subtree.",
                },
                "max_depth": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 6,
                    "description": "Maximum heading depth to expand in the returned outline. Defaults to 2.",
                },
                "include_sections": {
                    "type": "boolean",
                    "description": "Whether to include leaf section selectors under returned outline nodes. Defaults to false.",
                },
            },
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

RETRIEVAL_TOOLS: dict[str, dict[str, Any]] = {
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
            "Retrieve selected document sections, or cache the full document as one synthetic section only when intentional. "
            "For section retrieval, use section IDs from get_document_toc or search_documents. "
            "Small sections may be returned inline; large sections are cached and returned as manifests."
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
                        "Optional section IDs from get_document_toc or search_documents. "
                        "Omit only with allow_full_document=true when retrieving the full document as a synthetic cached section is intentional. "
                        "MCP runtime limit is 5."
                    ),
                },
                "return_content": {
                    "type": "boolean",
                    "description": "Whether to include retrieved content in the tool response. Defaults to true.",
                },
                "allow_full_document": {
                    "type": "boolean",
                    "description": (
                        "Whether to allow full-document retrieval when section_ids is omitted. "
                        "Defaults to false. Use only when caching the full document as one synthetic section is intentional."
                    ),
                },
            },
            "required": ["document_id"],
            "additionalProperties": False,
        },
    },
    "search_section_contents": {
        "description": (
            "Search within one cached document section with NFKC/casefold normalization and return short excerpts with original offsets. "
            "Call get_document_content first if the section is not cached."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "section_id": {"type": "string"},
                "query": {"type": "string"},
                "match_type": {
                    "type": "string",
                    "enum": ["lexical"],
                    "description": "Search mode. Cached section search currently supports lexical matching.",
                },
                "context_chars": {
                    "type": "integer",
                    "minimum": 50,
                    "maximum": 500,
                    "description": "Characters of context to include on each side of the match. Defaults to 300.",
                },
                "max_matches": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 15,
                    "description": "Maximum matches to return. Defaults to 5.",
                },
            },
            "required": ["document_id", "section_id", "query"],
            "additionalProperties": False,
        },
    },
    "get_section_window": {
        "description": (
            "Return a bounded text window around an offset in one cached document section. "
            "Use offsets returned by search_section_contents when possible."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "section_id": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "max_characters": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5000,
                    "description": "Maximum characters to return. Defaults to 1500.",
                },
            },
            "required": ["document_id", "section_id", "offset"],
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
                    "maximum": 25,
                    "description": "Maximum cached resources to return. MCP runtime limit is 25.",
                },
            },
            "additionalProperties": False,
        },
    },
}


def tool_definitions() -> list[dict[str, Any]]:
    tools = {**DOCUMENT_LOOKUP_TOOLS, **RETRIEVAL_TOOLS, **SKILL_HELPER_TOOLS}
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
                "published_at": {"type": "string"},
                "timeline_at": {"type": "string"},
                "content_status": {"type": "string"},
                "character_count": {"type": "integer"},
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
                "toc_mode": {"type": "string"},
                "path_prefix": {"type": "array", "items": {"type": "string"}},
                "max_depth": {"type": "integer"},
                "include_sections": {"type": "boolean"},
                "selection_policy": {"type": "object", "additionalProperties": True},
                "toc": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "next_action_template": {"type": "object", "additionalProperties": True},
                **RESOURCE_OUTPUT_PROPERTIES,
            }
        )

    if tool_name == "get_document_content":
        properties.update(
            {
                "document_id": {"type": "string"},
                "content_sections": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "max_inline_section_characters": {"type": "integer"},
                **RESOURCE_OUTPUT_PROPERTIES,
            }
        )

    if tool_name == "search_section_contents":
        properties.update(
            {
                "document_id": {"type": "string"},
                "section_id": {"type": "string"},
                "section_title": {"type": "string"},
                "heading_path": {"type": "array", "items": {"type": "string"}},
                "match_type": {"type": "string"},
                "query": {"type": "string"},
                "context_chars": {"type": "integer"},
                "max_matches": {"type": "integer"},
                "matches": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "source_resource_uri": {"type": "string"},
                "cache_hit": {"type": "boolean"},
            }
        )

    if tool_name == "get_section_window":
        properties.update(
            {
                "document_id": {"type": "string"},
                "section_id": {"type": "string"},
                "section_title": {"type": "string"},
                "heading_path": {"type": "array", "items": {"type": "string"}},
                "offset": {"type": "integer"},
                "start_offset": {"type": "integer"},
                "end_offset": {"type": "integer"},
                "actual_characters": {"type": "integer"},
                "max_characters": {"type": "integer"},
                "content": {"type": "string"},
                "truncated": {"type": "boolean"},
                "source_resource_uri": {"type": "string"},
                "cache_hit": {"type": "boolean"},
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

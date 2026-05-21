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
            "List news statements with references. Consumes 1 credit per API call. "
            "Provide at least one of security_codes, macro_tags, or timeline_since."
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
            "Consumes up to 8 credits per API call; cache hits consume 0 credits. "
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
        "description": (
            "Download one original file to the local cache. Consumes 8 credits on cache miss. Requires allow_file_download=true."
        ),
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
        "description": (
            "Download one page image to the local cache. Consumes 1 credit on cache miss. Requires allow_file_download=true."
        ),
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
        "description": (
            "Search document content. Consumes 1 credit per API call. Use short topic terms or evidence-focused questions."
        ),
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
        "description": (
            "Search news statements. Consumes 1 credit per API call. Keep news separate from document search in the MVP."
        ),
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
        {"name": name, "description": definition["description"], "inputSchema": definition["inputSchema"]}
        for name, definition in tools.items()
    ]

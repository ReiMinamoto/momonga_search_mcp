"""MCP tool catalog definitions."""

from __future__ import annotations

from typing import Any

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

SECURITY_CODES_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
}

TIMELINE_SINCE_SCHEMA = {
    "type": "string",
    "description": "Inclusive start date filter in JST, YYYY-MM-DD.",
}

TIMELINE_UNTIL_SCHEMA = {
    "type": "string",
    "description": "Inclusive end date filter in JST, YYYY-MM-DD.",
}

MATCH_TYPE_SCHEMA = {
    "type": "string",
    "enum": ["semantic", "lexical"],
    "description": "Search mode (API default: semantic). Use a natural-language question for semantic, or short keywords for lexical.",
}

DOCUMENT_TYPES_SCHEMA = {
    "type": "array",
    "items": {"type": "string", "enum": ["yuho", "tanshin", "other"]},
}

LATEST_ONLY_SCHEMA = {
    "type": "boolean",
    "description": (
        "When false, include older yuho/tanshin documents replaced by newer disclosures. "
        "API default is true. Use false together with timeline_until for point-in-time searches."
    ),
}

SEARCH_FILTER_PROPERTIES = {
    "security_codes": SECURITY_CODES_SCHEMA,
    "timeline_since": TIMELINE_SINCE_SCHEMA,
    "timeline_until": TIMELINE_UNTIL_SCHEMA,
    "match_type": MATCH_TYPE_SCHEMA,
}

FILTER_ARGUMENT_ALTERNATIVES = [
    {"required": ["security_codes"]},
    {"required": ["timeline_since"]},
]


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
    "diagnose_setup": "Diagnose Setup",
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
    "diagnose_setup": LOCAL_READ_ONLY_ANNOTATIONS,
    "list_cached_resources": LOCAL_READ_ONLY_ANNOTATIONS,
}

# OpenAI/Codex-compatible tool schemas cannot use top-level anyOf. Enforce these at runtime instead.
TOOL_ARGUMENT_ALTERNATIVES: dict[str, list[dict[str, list[str]]]] = {
    "list_documents": FILTER_ARGUMENT_ALTERNATIVES,
    "list_news": FILTER_ARGUMENT_ALTERNATIVES,
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
            "List document metadata by issuer, date and document type/family, newest first by timeline_at. This includes documents whose body is not indexed, pending_release/external_only documents, and IR materials (v1 metadata/external links only; no API body, originals or images). Use it to discover documents or check existence/availability when body search has no hits. Returns document_id, content_status, character_count and reference_url. Provide security_codes or timeline_since (required when security_codes is omitted)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "security_codes": {
                    **SECURITY_CODES_SCHEMA,
                    "description": "Security code filters. Required unless timeline_since is provided.",
                },
                "document_types": DOCUMENT_TYPES_SCHEMA,
                "document_families": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["edinet_filing", "timely_disclosure", "ir_material"]},
                },
                "timeline_since": {
                    **TIMELINE_SINCE_SCHEMA,
                    "description": "Inclusive start date filter in JST, YYYY-MM-DD. Required when security_codes is omitted.",
                },
                "timeline_until": TIMELINE_UNTIL_SCHEMA,
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
        "description": "Get metadata, content_status and document-level character_count for a document_id returned by listing/search. Do not construct or guess document IDs. ready permits body retrieval; pending_release is not yet available; external_only has no API body and requires the external reference, not retries. published_at is official; timeline_at can be inferred or observed (see timeline_basis/precision). reference_url is not a stable file download URL. Use get_document_content for ready document text.",
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
        "description": "List available page images with page_number, source_route and image_role. Not every PDF page is available. source_route=vision means VLM-transcribed text; text_layer means embedded text. image_role=ocr_fallback means text extraction failed; vlm_evidence does not imply a chart is present.",
        "inputSchema": {
            "type": "object",
            "properties": {"document_id": {"type": "string"}},
            "required": ["document_id"],
            "additionalProperties": False,
        },
    },
    "list_document_originals": {
        "description": "List available original files. Select by kind, media_type and role; download using the returned original_id. reference_url is not a stable original-file download URL.",
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
        "description": "List news newest first by updated_at; date filters apply to updated_at. Revisions keep news_id and change updated_at. body is 1-3 sentences based on sources, not the detected article text. references contain URLs or document_id values. Provide security_codes or timeline_since.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "security_codes": {
                    **SECURITY_CODES_SCHEMA,
                    "description": "Security code filters.",
                },
                "timeline_since": {
                    **TIMELINE_SINCE_SCHEMA,
                    "description": (
                        "Inclusive start date filter in JST, YYYY-MM-DD. "
                        "At least one of security_codes or timeline_since is required."
                    ),
                },
                "timeline_until": TIMELINE_UNTIL_SCHEMA,
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
            "Retrieve body text for a known document_id. Section IDs come from get_document_toc or search_documents. Omitting section_ids requires allow_full_document=true; full documents up to 10000 characters can be returned inline. For larger documents select needed sections, at most 5 per call. Sections up to 3000 characters are inline; larger sections return manifests after caching the body. Read them with search_section_contents/get_section_window. resource URIs identify evidence and resources/read returns manifests, not full body text. Content is cached even with return_content=false."
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
            "Search one cached section for a single literal substring, with NFKC/casefold normalization. This is contiguous text matching, not semantic search or independent matching of multiple keywords. Use a short term present in the source; returned excerpts and offsets support get_section_window. Call get_document_content first if the section is not cached."
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
                    "maximum": 300,
                    "description": "Characters of context to include on each side of the match. Defaults to 150.",
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
        "description": "Download an original_id returned by list_document_originals to the local cache. Requires allow_file_download=true.",
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
        "description": "Download an available page_number from list_document_page_images or a search match with has_visual=true. has_visual indicates image availability, not VLM transcription. Requires allow_file_download=true.",
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
        "description": "Search indexed document body text for topics/keywords; it is not a complete metadata or title search. Unindexed bodies and unreleased documents may be absent; v1 IR materials are never body-searchable or API-retrievable. Use list_documents for issuer/date/type discovery and availability. Document IDs are retrieval identifiers, not body search terms: use get_document_content for a known document_id. Older replaced disclosures are excluded by default: set latest_only=false for historical searches, even with date filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                **SEARCH_FILTER_PROPERTIES,
                "document_types": DOCUMENT_TYPES_SCHEMA,
                "document_families": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["edinet_filing", "timely_disclosure"]},
                },
                "latest_only": LATEST_ONLY_SCHEMA,
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
        "description": "Search news title/body separately from documents. Date filters apply to observed_at (first observation), unlike list_news which filters updated_at. body is a source-based 1-3 sentence news item, not the detected article text; references contain URLs or document_id values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                **SEARCH_FILTER_PROPERTIES,
                "top_k": TOP_K_SCHEMA,
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

HELPER_TOOLS: dict[str, dict[str, Any]] = {
    "diagnose_setup": {
        "description": "Diagnose local MCP server setup without returning secrets or contacting the Momonga Search API.",
        "inputSchema": {
            "type": "object",
            "properties": {},
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
    tools = {**DOCUMENT_LOOKUP_TOOLS, **RETRIEVAL_TOOLS, **HELPER_TOOLS}
    return [
        {
            "name": name,
            "title": TOOL_TITLES[name],
            "description": definition["description"],
            "inputSchema": definition["inputSchema"],
            "annotations": TOOL_ANNOTATIONS[name],
        }
        for name, definition in tools.items()
    ]

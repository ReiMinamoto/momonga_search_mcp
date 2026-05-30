from __future__ import annotations

from pathlib import Path
import unittest

from momonga_search_mcp.cache import CachedResource
from momonga_search_mcp.tools.definitions import TOOL_ARGUMENT_ALTERNATIVES, tool_definitions
from momonga_search_mcp.tools.response import get_document_content_response, get_document_toc_response, success_response


class ToolDefinitionTests(unittest.TestCase):
    def test_tool_definitions_include_document_and_news_tools(self) -> None:
        tool_names = [tool["name"] for tool in tool_definitions()]

        self.assertEqual(
            tool_names,
            [
                "search_issuers",
                "list_documents",
                "get_document_metadata",
                "get_document_toc",
                "list_document_page_images",
                "list_document_originals",
                "list_news",
                "get_document_content",
                "search_section_contents",
                "get_section_window",
                "get_document_original",
                "get_document_page_image",
                "search_documents",
                "search_news",
                "list_skills",
                "get_skill",
                "diagnose_setup",
                "list_cached_resources",
            ],
        )

    def test_list_tool_schemas_are_openai_compatible(self) -> None:
        schemas = {tool["name"]: tool["inputSchema"] for tool in tool_definitions()}

        for tool_name, schema in schemas.items():
            self.assertEqual(schema["type"], "object")
            for key in ("anyOf", "oneOf", "allOf", "not"):
                self.assertNotIn(key, schema, msg=f"{tool_name} must not use top-level {key}")

    def test_tool_definitions_include_latest_mcp_metadata(self) -> None:
        tools = {tool["name"]: tool for tool in tool_definitions()}

        for tool_name, tool in tools.items():
            self.assertIsInstance(tool["title"], str, msg=tool_name)
            self.assertTrue(tool["title"], msg=tool_name)
            self.assertEqual(tool["annotations"]["readOnlyHint"], True, msg=tool_name)
            self.assertEqual(tool["annotations"]["destructiveHint"], False, msg=tool_name)
            self.assertEqual(tool["outputSchema"]["type"], "object", msg=tool_name)
            self.assertEqual(tool["outputSchema"]["additionalProperties"], False, msg=tool_name)
            self.assertIn("ok", tool["outputSchema"]["properties"], msg=tool_name)
            self.assertIn("error", tool["outputSchema"]["properties"], msg=tool_name)

        self.assertEqual(tools["search_documents"]["annotations"]["openWorldHint"], True)
        self.assertEqual(tools["list_cached_resources"]["annotations"]["openWorldHint"], False)
        self.assertEqual(tools["diagnose_setup"]["annotations"]["openWorldHint"], False)
        self.assertIn("issuers", tools["get_document_metadata"]["outputSchema"]["properties"])
        self.assertIn("published_at", tools["get_document_metadata"]["outputSchema"]["properties"])
        self.assertIn("character_count", tools["get_document_metadata"]["outputSchema"]["properties"])
        self.assertIn("next_action", tools["get_document_metadata"]["outputSchema"]["properties"])
        self.assertIn("page_images", tools["list_document_page_images"]["outputSchema"]["properties"])
        self.assertIn("originals", tools["list_document_originals"]["outputSchema"]["properties"])
        self.assertIn("content_sections", tools["get_document_content"]["outputSchema"]["properties"])
        self.assertIn("cache_hit", tools["get_document_content"]["outputSchema"]["properties"])
        self.assertIn("requested_section_ids", tools["get_document_content"]["outputSchema"]["properties"])
        self.assertIn("missing_section_ids", tools["get_document_content"]["outputSchema"]["properties"])
        self.assertNotIn("resource_uri", tools["get_document_content"]["outputSchema"]["properties"])
        self.assertNotIn("cached", tools["get_document_content"]["outputSchema"]["properties"])
        self.assertIn("matches", tools["search_section_contents"]["outputSchema"]["properties"])
        self.assertIn("start_offset", tools["get_section_window"]["outputSchema"]["properties"])

    def test_list_tool_argument_alternatives_are_enforced_at_runtime(self) -> None:
        self.assertEqual(
            TOOL_ARGUMENT_ALTERNATIVES["list_documents"],
            [{"required": ["security_codes"]}, {"required": ["timeline_since"]}],
        )
        self.assertEqual(
            TOOL_ARGUMENT_ALTERNATIVES["list_news"],
            [{"required": ["security_codes"]}, {"required": ["macro_tags"]}, {"required": ["timeline_since"]}],
        )

    def test_result_count_schemas_use_mcp_runtime_limits(self) -> None:
        schemas = {tool["name"]: tool["inputSchema"] for tool in tool_definitions()}

        self.assertEqual(schemas["search_issuers"]["properties"]["limit"]["maximum"], 25)
        self.assertEqual(schemas["list_documents"]["properties"]["limit"]["maximum"], 25)
        self.assertEqual(schemas["list_news"]["properties"]["limit"]["maximum"], 25)
        self.assertEqual(schemas["search_documents"]["properties"]["top_k"]["maximum"], 25)
        self.assertEqual(schemas["search_news"]["properties"]["top_k"]["maximum"], 25)

    def test_get_document_content_schema_allows_optional_bounded_sections_without_offset(self) -> None:
        schemas = {tool["name"]: tool["inputSchema"] for tool in tool_definitions()}
        schema = schemas["get_document_content"]

        self.assertEqual(schema["required"], ["document_id"])
        self.assertEqual(schema["properties"]["section_ids"]["minItems"], 1)
        self.assertEqual(schema["properties"]["section_ids"]["maxItems"], 5)
        self.assertEqual(schema["properties"]["allow_full_document"]["type"], "boolean")
        self.assertNotIn("max_chars", schema["properties"])
        self.assertNotIn("offset", schema["properties"])

    def test_cached_section_reader_schemas_are_bounded(self) -> None:
        schemas = {tool["name"]: tool["inputSchema"] for tool in tool_definitions()}

        search_schema = schemas["search_section_contents"]
        self.assertEqual(search_schema["required"], ["document_id", "section_id", "query"])
        self.assertEqual(search_schema["properties"]["match_type"]["enum"], ["lexical"])
        self.assertEqual(search_schema["properties"]["context_chars"]["minimum"], 50)
        self.assertEqual(search_schema["properties"]["context_chars"]["maximum"], 500)
        self.assertEqual(search_schema["properties"]["max_matches"]["minimum"], 1)
        self.assertEqual(search_schema["properties"]["max_matches"]["maximum"], 15)

        window_schema = schemas["get_section_window"]
        self.assertEqual(window_schema["required"], ["document_id", "section_id", "offset"])
        self.assertEqual(window_schema["properties"]["offset"]["minimum"], 0)
        self.assertEqual(window_schema["properties"]["max_characters"]["maximum"], 5000)

    def test_get_document_toc_schema_allows_outline_options(self) -> None:
        schemas = {tool["name"]: tool["inputSchema"] for tool in tool_definitions()}
        schema = schemas["get_document_toc"]

        self.assertEqual(schema["required"], ["document_id"])
        self.assertEqual(schema["properties"]["path_prefix"]["items"]["type"], "string")
        self.assertEqual(schema["properties"]["max_depth"]["minimum"], 2)
        self.assertEqual(schema["properties"]["max_depth"]["maximum"], 6)
        self.assertEqual(schema["properties"]["include_sections"]["type"], "boolean")

    def test_file_download_schemas_require_explicit_flags(self) -> None:
        schemas = {tool["name"]: tool["inputSchema"] for tool in tool_definitions()}

        self.assertEqual(
            schemas["get_document_page_image"]["required"],
            ["document_id", "page_number", "allow_file_download"],
        )
        self.assertEqual(schemas["get_document_page_image"]["properties"]["page_number"]["minimum"], 1)
        self.assertEqual(
            schemas["get_document_original"]["required"],
            ["document_id", "original_id", "allow_file_download"],
        )

    def test_skill_helper_schemas(self) -> None:
        schemas = {tool["name"]: tool["inputSchema"] for tool in tool_definitions()}

        self.assertEqual(schemas["list_skills"]["properties"], {})
        self.assertNotIn("required", schemas["list_skills"])
        self.assertEqual(schemas["diagnose_setup"]["properties"], {})
        self.assertNotIn("required", schemas["diagnose_setup"])
        self.assertEqual(schemas["list_cached_resources"]["properties"]["limit"]["maximum"], 25)
        self.assertEqual(
            schemas["list_cached_resources"]["properties"]["resource_type"]["enum"],
            ["toc", "section", "page", "original"],
        )
        self.assertEqual(schemas["get_skill"]["required"], ["id"])

    def test_representative_structured_content_matches_output_schemas(self) -> None:
        schemas = {tool["name"]: tool["outputSchema"] for tool in tool_definitions()}

        for tool_name, payload in _representative_success_payloads().items():
            with self.subTest(tool_name=tool_name):
                _assert_matches_top_level_schema(self, payload, schemas[tool_name])

        error_payload = {
            "ok": False,
            "error": {
                "code": "server_setup_error",
                "status": None,
                "message": "MOMONGA_SEARCH_API_KEY is required for Momonga Search API tools",
                "next_action": "Stop and report this to the MCP operator as a server setup error.",
            },
        }
        for tool_name, schema in schemas.items():
            with self.subTest(tool_name=f"{tool_name}:error"):
                _assert_matches_top_level_schema(self, error_payload, schema)


def _representative_success_payloads() -> dict[str, dict[str, object]]:
    return {
        "search_issuers": success_response(
            "search_issuers",
            {"results": [{"security_code": "8058", "edinet_code": "E02529", "name": "Issuer"}]},
        ),
        "list_documents": success_response(
            "list_documents",
            {
                "results": [
                    {
                        "document_id": "doc_123",
                        "document_family": "edinet_filing",
                        "title": "Report",
                        "document_type": "yuho",
                        "published_at": "2026-05-01T00:00:00Z",
                        "timeline_at": "2026-05-01T00:00:00Z",
                        "content_status": "ready",
                    }
                ],
                "next_cursor": "cursor_1",
            },
        ),
        "get_document_metadata": success_response(
            "get_document_metadata",
            {"document_id": "doc_123", "title": "Report", "content_status": "ready"},
        ),
        "get_document_toc": get_document_toc_response(
            {
                "document_id": "doc_123",
                "toc": [
                    {
                        "section_id": "sec_1",
                        "section_title": "Risk",
                        "heading_path": ["Business", "Risk"],
                        "character_count": 100,
                        "page_number": 2,
                    }
                ],
            },
            CachedResource(resource_uri="momonga://documents/doc_123/toc", path=Path("toc.json")),
            cache_hit=False,
        ),
        "list_document_page_images": success_response(
            "list_document_page_images",
            {"document_id": "doc_123", "page_count": 2, "page_image_count": 1, "page_images": [{"page_number": 1}]},
        ),
        "list_document_originals": success_response(
            "list_document_originals",
            {
                "document_id": "doc_123",
                "originals": [{"original_id": "pdf", "filename": "report.pdf", "media_type": "application/pdf"}],
            },
        ),
        "list_news": success_response(
            "list_news",
            {
                "results": [
                    {
                        "news_id": "news_123",
                        "statement": "Company announced...",
                        "observed_at": "2026-05-01T00:00:00Z",
                        "related_issuers": [],
                        "macro_tags": ["Monetary Policy"],
                        "references": [],
                    }
                ],
            },
        ),
        "get_document_content": get_document_content_response(
            "doc_123",
            [
                (
                    {"section_id": "sec_1", "section_title": "Risk", "character_count": 4, "content": "body"},
                    "momonga://documents/doc_123/sections/sec_1",
                )
            ],
            cache_hit=False,
            cached_sections=False,
            return_content=True,
            requested_section_ids=["sec_1"],
        ),
        "search_section_contents": {
            "ok": True,
            "document_id": "doc_123",
            "section_id": "sec_1",
            "section_title": "Risk",
            "heading_path": ["Business", "Risk"],
            "match_type": "lexical",
            "query": "risk",
            "context_chars": 300,
            "max_matches": 5,
            "matches": [],
            "source_resource_uri": "momonga://documents/doc_123/sections/sec_1",
            "cache_hit": True,
        },
        "get_section_window": {
            "ok": True,
            "document_id": "doc_123",
            "section_id": "sec_1",
            "section_title": "Risk",
            "heading_path": ["Business", "Risk"],
            "offset": 0,
            "start_offset": 0,
            "end_offset": 4,
            "actual_characters": 4,
            "max_characters": 1500,
            "content": "body",
            "truncated": False,
            "source_resource_uri": "momonga://documents/doc_123/sections/sec_1",
            "cache_hit": True,
        },
        "get_document_original": {
            "ok": True,
            "document_id": "doc_123",
            "original_id": "pdf",
            "filename": "report.pdf",
            "media_type": "application/pdf",
            "file_path": "/tmp/report.pdf",
            "resource_uri": "momonga://documents/doc_123/originals/pdf",
            "cached": False,
        },
        "get_document_page_image": {
            "ok": True,
            "document_id": "doc_123",
            "page_number": 1,
            "media_type": "image/jpeg",
            "file_path": "/tmp/page.jpg",
            "resource_uri": "momonga://documents/doc_123/pages/1",
            "cached": False,
        },
        "search_documents": success_response(
            "search_documents",
            {
                "results": [
                    {
                        "document_id": "doc_123",
                        "title": "Report",
                        "content_status": "ready",
                        "matches": [{"section_id": "sec_1", "score": 9.2, "snippet": "risk"}],
                    }
                ]
            },
        ),
        "search_news": success_response(
            "search_news",
            {
                "results": [
                    {
                        "news_id": "news_123",
                        "statement": "Company announced...",
                        "observed_at": "2026-05-01T00:00:00Z",
                        "related_issuers": [],
                        "macro_tags": [],
                        "references": [],
                    }
                ]
            },
        ),
        "list_skills": {"ok": True, "skills": []},
        "get_skill": {
            "ok": True,
            "id": "document-research",
            "title": "Document Research",
            "resource_uri": "skill://skills/document-research.md",
            "content": "# Document Research Skill",
        },
        "diagnose_setup": {
            "ok": True,
            "api_key_configured": True,
            "base_url": "https://api.momongasearch.com/v1",
            "cache_dir": "/tmp/momonga-search-mcp",
            "cache_writable": True,
            "server_name": "momonga-search-mcp",
            "server_version": "1.0.0",
            "protocol_version": "2025-11-25",
        },
        "list_cached_resources": {"ok": True, "resources": []},
    }


def _assert_matches_top_level_schema(
    test_case: unittest.TestCase,
    payload: dict[str, object],
    schema: dict[str, object],
) -> None:
    properties = schema["properties"]
    assert isinstance(properties, dict)
    required = schema.get("required", [])
    assert isinstance(required, list)

    for field in required:
        test_case.assertIn(field, payload)

    if schema.get("additionalProperties") is False:
        test_case.assertEqual(set(payload) - set(properties), set())

    for field, value in payload.items():
        field_schema = properties[field]
        assert isinstance(field_schema, dict)
        _assert_value_matches_schema_type(test_case, field, value, field_schema)


def _assert_value_matches_schema_type(
    test_case: unittest.TestCase,
    field: str,
    value: object,
    schema: dict[str, object],
) -> None:
    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        if value is None and "null" in expected_type:
            return
        expected_type = next(item for item in expected_type if item != "null")

    if expected_type == "boolean":
        test_case.assertIs(type(value), bool, msg=field)
    elif expected_type == "integer":
        test_case.assertIs(type(value), int, msg=field)
    elif expected_type == "string":
        test_case.assertIsInstance(value, str, msg=field)
    elif expected_type == "array":
        test_case.assertIsInstance(value, list, msg=field)
    elif expected_type == "object":
        test_case.assertIsInstance(value, dict, msg=field)


if __name__ == "__main__":
    unittest.main()

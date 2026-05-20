from __future__ import annotations

import unittest

from momonga_search_mcp.tools.definitions import TOOL_ARGUMENT_ALTERNATIVES, tool_definitions


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
                "get_document_original",
                "get_document_page_image",
                "search_documents",
                "search_news",
            ],
        )

    def test_list_tool_schemas_are_openai_compatible(self) -> None:
        schemas = {tool["name"]: tool["inputSchema"] for tool in tool_definitions()}

        for tool_name, schema in schemas.items():
            self.assertEqual(schema["type"], "object")
            for key in ("anyOf", "oneOf", "allOf", "not"):
                self.assertNotIn(key, schema, msg=f"{tool_name} must not use top-level {key}")

    def test_list_tool_argument_alternatives_are_enforced_at_runtime(self) -> None:
        self.assertEqual(
            TOOL_ARGUMENT_ALTERNATIVES["list_documents"],
            [{"required": ["security_codes"]}, {"required": ["timeline_since"]}],
        )
        self.assertEqual(
            TOOL_ARGUMENT_ALTERNATIVES["list_news"],
            [{"required": ["security_codes"]}, {"required": ["macro_tags"]}, {"required": ["timeline_since"]}],
        )

    def test_result_count_schemas_include_api_maximums(self) -> None:
        schemas = {tool["name"]: tool["inputSchema"] for tool in tool_definitions()}

        self.assertEqual(schemas["search_issuers"]["properties"]["limit"]["maximum"], 50)
        self.assertEqual(schemas["list_documents"]["properties"]["limit"]["maximum"], 50)
        self.assertEqual(schemas["list_news"]["properties"]["limit"]["maximum"], 50)
        self.assertEqual(schemas["search_documents"]["properties"]["top_k"]["maximum"], 50)
        self.assertEqual(schemas["search_news"]["properties"]["top_k"]["maximum"], 50)

    def test_get_document_content_schema_requires_bounded_sections_and_offset(self) -> None:
        schemas = {tool["name"]: tool["inputSchema"] for tool in tool_definitions()}
        schema = schemas["get_document_content"]

        self.assertEqual(schema["required"], ["document_id", "section_ids"])
        self.assertEqual(schema["properties"]["section_ids"]["minItems"], 1)
        self.assertEqual(schema["properties"]["section_ids"]["maxItems"], 5)
        self.assertNotIn("max_chars", schema["properties"])
        self.assertEqual(schema["properties"]["offset"]["minimum"], 0)

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


if __name__ == "__main__":
    unittest.main()

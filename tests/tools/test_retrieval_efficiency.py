from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from momonga_search_mcp.cache import CacheManager
from momonga_search_mcp.tools.definitions import tool_definitions
from momonga_search_mcp.tools.handlers import call_tool
from tests.tools.fakes import FakeApiClient


def decode(result):
    return json.loads(result["content"][0]["text"])


class RetrievalEfficiencyTests(unittest.TestCase):
    def test_empty_search_returns_results_without_exploration_guidance(self):
        for filters in ({}, {"security_codes": ["7203"], "latest_only": False}):
            with self.subTest(filters=filters):
                client = FakeApiClient()
                result = decode(call_tool(client, {"name": "search_documents", "arguments": {"query": "営業利益", **filters}}))
                self.assertEqual(result, {"ok": True, "results": []})
                self.assertEqual(len(client.calls), 1)

    def test_empty_catalog_returns_results_without_exploration_guidance(self):
        client = FakeApiClient()
        result = decode(call_tool(client, {"name": "list_documents", "arguments": {"security_codes": ["7203"]}}))
        self.assertEqual(result, {"ok": True, "results": []})
        self.assertEqual(len(client.calls), 1)

    def test_search_hits_do_not_trigger_catalog_fallback(self):
        client = FakeApiClient()
        client.response = {"results": [{"document_id": "d", "matches": []}]}
        result = decode(call_tool(client, {"name": "search_documents", "arguments": {"query": "利益"}}))
        self.assertNotIn("next_action", result)
        self.assertEqual(len(client.calls), 1)

    def test_partial_cache_fetches_only_missing_section_and_preserves_order(self):
        client = FakeApiClient()
        client.response = {"content_sections": [{"section_id": "b", "content": "new B"}]}
        with TemporaryDirectory() as tmp:
            cache = CacheManager(Path(tmp))
            cache.store_document_section("d", "a", {"section_id": "a", "content": "cached A"})
            result = decode(
                call_tool(
                    client,
                    {"name": "get_document_content", "arguments": {"document_id": "d", "section_ids": ["b", "a"]}},
                    cache_manager_getter=lambda cache=cache: cache,
                )
            )
            self.assertEqual(client.calls, [("GET", "/documents/d/content", {"sections": ["b"]})])
            self.assertFalse(result["cache_hit"])
            self.assertEqual([s["section_id"] for s in result["content_sections"]], ["b", "a"])
            self.assertEqual([s["cached"] for s in result["content_sections"]], [False, True])
            self.assertEqual([s["content"] for s in result["content_sections"]], ["new B", "cached A"])
            client.calls.clear()
            result = decode(
                call_tool(
                    client,
                    {"name": "get_document_content", "arguments": {"document_id": "d", "section_ids": ["b", "a"]}},
                    cache_manager_getter=lambda cache=cache: cache,
                )
            )
            self.assertTrue(result["cache_hit"])
            self.assertEqual(client.calls, [])

    def test_partial_api_response_keeps_cached_evidence_and_reports_missing_section(self):
        client = FakeApiClient()
        client.response = {"content_sections": []}
        with TemporaryDirectory() as tmp:
            cache = CacheManager(Path(tmp))
            cache.store_document_section("d", "a", {"section_id": "a", "content": "cached A"})
            result = decode(
                call_tool(
                    client,
                    {"name": "get_document_content", "arguments": {"document_id": "d", "section_ids": ["a", "b"]}},
                    cache_manager_getter=lambda cache=cache: cache,
                )
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["missing_section_ids"], ["b"])
        self.assertTrue(result["content_sections"][0]["cached"])

    def test_missing_or_invalid_cached_section_is_refetched(self):
        for corrupt in (None, "broken json", "[]", '{"section_id":"wrong","content":"wrong text"}'):
            with self.subTest(corrupt=corrupt), TemporaryDirectory() as tmp:
                cache = CacheManager(Path(tmp))
                resource = cache.store_document_section("d", "a", {"section_id": "a", "content": "old A"})
                if corrupt is None:
                    resource.path.unlink()
                else:
                    resource.path.write_text(corrupt)
                client = FakeApiClient()
                client.response = {"content_sections": [{"section_id": "a", "content": "new A"}]}
                result = decode(
                    call_tool(
                        client,
                        {"name": "get_document_content", "arguments": {"document_id": "d", "section_ids": ["a"]}},
                        cache_manager_getter=lambda cache=cache: cache,
                    )
                )
                self.assertEqual(result["content_sections"][0]["content"], "new A")
                self.assertTrue(result["ok"])
                self.assertEqual(len(client.calls), 1)

    def test_missing_or_corrupt_toc_is_refetched(self):
        for corrupt in (None, "broken json"):
            with self.subTest(corrupt=corrupt), TemporaryDirectory() as tmp:
                cache = CacheManager(Path(tmp))
                resource = cache.store_document_toc("d", {"document_id": "d", "toc": []})
                if corrupt is None:
                    resource.path.unlink()
                else:
                    resource.path.write_text(corrupt)
                client = FakeApiClient()
                client.response = {"document_id": "d", "toc": []}
                result = decode(
                    call_tool(
                        client,
                        {"name": "get_document_toc", "arguments": {"document_id": "d"}},
                        cache_manager_getter=lambda cache=cache: cache,
                    )
                )
                self.assertTrue(result["ok"])
                self.assertEqual(len(client.calls), 1)

    def test_pruning_keeps_all_sections_needed_by_current_request(self):
        for cached_a in (False, True):
            with self.subTest(cached_a=cached_a), TemporaryDirectory() as tmp:
                cache = CacheManager(Path(tmp), max_bytes=6000)
                cache.store_document_section("old", "x", {"section_id": "x", "content": "old"})
                sections = [{"section_id": "a", "content": "a" * 4000}, {"section_id": "b", "content": "b" * 4000}]
                if cached_a:
                    cache.store_document_section("d", "a", sections[0])
                client = FakeApiClient()
                client.response = {"content_sections": sections[1:] if cached_a else sections}
                result = decode(
                    call_tool(
                        client,
                        {"name": "get_document_content", "arguments": {"document_id": "d", "section_ids": ["a", "b"]}},
                        cache_manager_getter=lambda cache=cache: cache,
                    )
                )
                for section in result["content_sections"]:
                    resource = cache.get_document_section("d", section["section_id"])
                    self.assertIsNotNone(resource)
                    self.assertTrue(resource.path.exists())
                self.assertIsNone(cache.get_document_section("old", "x"))

    def test_atomic_write_failure_preserves_previous_cached_content(self):
        with TemporaryDirectory() as tmp:
            cache = CacheManager(Path(tmp))
            resource = cache.store_document_section("d", "a", {"section_id": "a", "content": "old A"})
            with patch.object(Path, "replace", side_effect=OSError("replacement failed")):
                with self.assertRaises(OSError):
                    cache.store_document_section("d", "a", {"section_id": "a", "content": "new A"})
            self.assertEqual(cache.read_json(resource)["content"], "old A")
            self.assertEqual(list(resource.path.parent.iterdir()), [resource.path])

    def test_tool_catalog_excludes_removed_batch_tool(self):
        self.assertNotIn("batch_tools", {tool["name"] for tool in tool_definitions()})

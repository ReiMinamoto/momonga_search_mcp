"""Command line helpers for Momonga Search MCP operations."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from momonga_search_mcp.cache import CacheManager
from momonga_search_mcp.config import resolve_cache_dir


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="momonga-search-mcp-cache")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help=("Cache directory. Defaults to MOMONGA_SEARCH_MCP_CACHE_DIR, then the OS standard user cache directory."),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    clear_parser = subparsers.add_parser("clear", help="Delete cached document resources.")
    clear_parser.add_argument("--document-id", help="Delete only resources under one document_id.")
    clear_parser.add_argument(
        "--resource-type",
        choices=("toc", "section", "page", "original"),
        help="Delete only one resource kind.",
    )

    args = parser.parse_args()
    if args.command == "clear":
        cache_dir = _resolve_cache_dir(args.cache_dir)
        result = CacheManager(cache_dir).clear_resources(
            document_id=args.document_id,
            resource_type=args.resource_type,
        )
        print(
            f"Deleted {result['resources_deleted']} cached resource(s) and "
            f"{result['files_deleted']} file(s) from {result['cache_dir']}."
        )
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


def _resolve_cache_dir(cache_dir: Path | None) -> Path:
    if cache_dir is not None:
        return cache_dir.expanduser()
    return resolve_cache_dir()

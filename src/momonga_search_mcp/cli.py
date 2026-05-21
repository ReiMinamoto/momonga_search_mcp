"""Command line helpers for Momonga Search MCP operations."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from momonga_search_mcp.cache import CacheManager
from momonga_search_mcp.config import DEFAULT_CACHE_DIR


def main() -> int:
    load_dotenv()
    default_cache_dir = Path(os.environ.get("MOMONGA_MCP_CACHE_DIR", str(DEFAULT_CACHE_DIR))).expanduser()
    parser = argparse.ArgumentParser(prog="momonga-search-mcp-cache")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=default_cache_dir,
        help="Cache directory. Defaults to MOMONGA_MCP_CACHE_DIR or ~/.cache/momonga-search-mcp.",
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
    cache_dir = Path(args.cache_dir).expanduser()
    if args.command == "clear":
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

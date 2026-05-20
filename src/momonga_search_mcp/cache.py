"""SQLite-backed local cache for Momonga Search MCP resources."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import quote

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CachedResource:
    resource_uri: str
    path: Path


class CacheManager:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_root = cache_dir / "cache"
        self.db_path = cache_dir / "index.sqlite"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def document_uri(self, document_id: str) -> str:
        return f"momonga://documents/{_uri_segment(document_id)}"

    def document_toc_uri(self, document_id: str) -> str:
        return f"{self.document_uri(document_id)}/toc"

    def document_section_uri(self, document_id: str, section_id: str) -> str:
        return f"{self.document_uri(document_id)}/sections/{_uri_segment(section_id)}"

    def document_page_uri(self, document_id: str, page_number: int) -> str:
        return f"{self.document_uri(document_id)}/pages/{page_number}"

    def document_original_uri(self, document_id: str, original_id: str) -> str:
        return f"{self.document_uri(document_id)}/originals/{_uri_segment(original_id)}"

    def store_document_toc(self, document_id: str, toc: dict[str, Any]) -> CachedResource:
        path = self._write_json(("documents", document_id, "toc.json"), toc)
        resource_uri = self.document_toc_uri(document_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO document_tocs (document_id, resource_uri, toc_path, cached_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    resource_uri = excluded.resource_uri,
                    toc_path = excluded.toc_path,
                    cached_at = excluded.cached_at
                """,
                (document_id, resource_uri, _relative_path(path, self.cache_dir), _now_iso()),
            )
        return CachedResource(resource_uri=resource_uri, path=path)

    def get_document_toc(self, document_id: str) -> CachedResource | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT resource_uri, toc_path
                FROM document_tocs
                WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return CachedResource(resource_uri=row["resource_uri"], path=self.cache_dir / row["toc_path"])

    def store_document_section(
        self,
        document_id: str,
        section_id: str,
        section: dict[str, Any],
    ) -> CachedResource:
        path = self._write_json(("documents", document_id, "sections", f"{section_id}.json"), section)
        resource_uri = self.document_section_uri(document_id, section_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO document_sections (document_id, section_id, resource_uri, content_path, cached_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(document_id, section_id) DO UPDATE SET
                    resource_uri = excluded.resource_uri,
                    content_path = excluded.content_path,
                    cached_at = excluded.cached_at
                """,
                (
                    document_id,
                    section_id,
                    resource_uri,
                    _relative_path(path, self.cache_dir),
                    _now_iso(),
                ),
            )
        return CachedResource(resource_uri=resource_uri, path=path)

    def get_document_section(self, document_id: str, section_id: str) -> CachedResource | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT resource_uri, content_path
                FROM document_sections
                WHERE document_id = ? AND section_id = ?
                """,
                (document_id, section_id),
            ).fetchone()
        if row is None:
            return None
        return CachedResource(resource_uri=row["resource_uri"], path=self.cache_dir / row["content_path"])

    def store_page_image(
        self,
        document_id: str,
        page_number: int,
        content: bytes,
        *,
        media_type: str = "image/jpeg",
        metadata: dict[str, Any] | None = None,
    ) -> CachedResource:
        suffix = ".jpg" if media_type == "image/jpeg" else ".bin"
        path = self._write_bytes(("documents", document_id, "pages", f"{page_number}{suffix}"), content)
        stored_metadata = {**(metadata or {}), "media_type": media_type}
        metadata_path = self._write_json(("documents", document_id, "pages", f"{page_number}.json"), stored_metadata)
        resource_uri = self.document_page_uri(document_id, page_number)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO document_page_images (
                    document_id, page_number, resource_uri, file_path,
                    metadata_path, cached_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id, page_number) DO UPDATE SET
                    resource_uri = excluded.resource_uri,
                    file_path = excluded.file_path,
                    metadata_path = excluded.metadata_path,
                    cached_at = excluded.cached_at
                """,
                (
                    document_id,
                    page_number,
                    resource_uri,
                    _relative_path(path, self.cache_dir),
                    _relative_path(metadata_path, self.cache_dir),
                    _now_iso(),
                ),
            )
        return CachedResource(resource_uri=resource_uri, path=path)

    def get_page_image(self, document_id: str, page_number: int) -> CachedResource | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT resource_uri, file_path
                FROM document_page_images
                WHERE document_id = ? AND page_number = ?
                """,
                (document_id, page_number),
            ).fetchone()
        if row is None:
            return None
        return CachedResource(resource_uri=row["resource_uri"], path=self.cache_dir / row["file_path"])

    def store_original_file(
        self,
        document_id: str,
        original_id: str,
        content: bytes,
        *,
        filename: str,
        media_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> CachedResource:
        path = self._write_bytes(("documents", document_id, "originals", original_id, _safe_segment(filename)), content)
        stored_metadata = {**(metadata or {}), "filename": filename, "media_type": media_type}
        metadata_path = self._write_json(("documents", document_id, "originals", original_id, "metadata.json"), stored_metadata)
        resource_uri = self.document_original_uri(document_id, original_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO document_originals (
                    document_id, original_id, resource_uri, file_path,
                    metadata_path, cached_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id, original_id) DO UPDATE SET
                    resource_uri = excluded.resource_uri,
                    file_path = excluded.file_path,
                    metadata_path = excluded.metadata_path,
                    cached_at = excluded.cached_at
                """,
                (
                    document_id,
                    original_id,
                    resource_uri,
                    _relative_path(path, self.cache_dir),
                    _relative_path(metadata_path, self.cache_dir),
                    _now_iso(),
                ),
            )
        return CachedResource(resource_uri=resource_uri, path=path)

    def get_original_file(self, document_id: str, original_id: str) -> CachedResource | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT resource_uri, file_path
                FROM document_originals
                WHERE document_id = ? AND original_id = ?
                """,
                (document_id, original_id),
            ).fetchone()
        if row is None:
            return None
        return CachedResource(resource_uri=row["resource_uri"], path=self.cache_dir / row["file_path"])

    def read_json(self, resource: CachedResource) -> dict[str, Any]:
        return self._read_json(resource.path)

    def record_api_call(
        self,
        *,
        tool_name: str,
        endpoint: str,
        cache_hit: bool,
        credits_used: int = 0,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO api_calls (tool_name, endpoint, cache_hit, credits_used, called_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (tool_name, endpoint, int(cache_hit), credits_used, _now_iso()),
            )

    def record_session_credits(self, session_id: str, credits: int) -> None:
        now = _now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO credit_sessions (session_id, credits_used, started_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    credits_used = credit_sessions.credits_used + excluded.credits_used,
                    updated_at = excluded.updated_at
                """,
                (session_id, credits, now, now),
            )

    def get_session_credits_used(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT credits_used
                FROM credit_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return 0
        return int(row["credits_used"])

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS document_tocs (
                    document_id TEXT PRIMARY KEY,
                    resource_uri TEXT NOT NULL,
                    toc_path TEXT NOT NULL,
                    cached_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS document_sections (
                    document_id TEXT NOT NULL,
                    section_id TEXT NOT NULL,
                    resource_uri TEXT NOT NULL,
                    content_path TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (document_id, section_id)
                );

                CREATE TABLE IF NOT EXISTS document_page_images (
                    document_id TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    resource_uri TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    metadata_path TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (document_id, page_number)
                );

                CREATE TABLE IF NOT EXISTS document_originals (
                    document_id TEXT NOT NULL,
                    original_id TEXT NOT NULL,
                    resource_uri TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    metadata_path TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (document_id, original_id)
                );

                CREATE TABLE IF NOT EXISTS api_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    cache_hit INTEGER NOT NULL,
                    credits_used INTEGER NOT NULL,
                    called_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS credit_sessions (
                    session_id TEXT PRIMARY KEY,
                    credits_used INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (version, applied_at)
                VALUES (?, ?)
                """,
                (SCHEMA_VERSION, _now_iso()),
            )

    def _write_json(self, parts: tuple[str, ...], payload: dict[str, Any]) -> Path:
        path = self.cache_root.joinpath(*(_safe_segment(part) for part in parts))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def _read_json(self, path: Path) -> dict[str, Any]:
        resolved = path.resolve()
        root = self.cache_dir.resolve()
        if root not in resolved.parents and resolved != root:
            raise ValueError("cache path must stay under cache_dir")
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("cached JSON payload must be an object")
        return payload

    def _write_bytes(self, parts: tuple[str, ...], payload: bytes) -> Path:
        path = self.cache_root.joinpath(*(_safe_segment(part) for part in parts))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _uri_segment(value: str) -> str:
    return quote(_safe_segment(value), safe="-_.~")


def _safe_segment(value: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError("cache path segment must be non-empty and must not contain path separators")
    return value

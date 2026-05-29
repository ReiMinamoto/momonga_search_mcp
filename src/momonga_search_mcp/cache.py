"""SQLite-backed local cache for Momonga Search MCP resources."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any
from urllib.parse import quote, unquote

SCHEMA_VERSION = 1
PRUNE_TARGET_DIVISOR = 2


@dataclass(frozen=True)
class CachedResource:
    resource_uri: str
    path: Path


class CacheManager:
    def __init__(self, cache_dir: Path, *, max_bytes: int | None = None) -> None:
        self.cache_dir = cache_dir
        self.max_bytes = max_bytes
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
                INSERT INTO document_tocs (document_id, resource_uri, toc_path, size_bytes, cached_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    resource_uri = excluded.resource_uri,
                    toc_path = excluded.toc_path,
                    size_bytes = excluded.size_bytes,
                    cached_at = excluded.cached_at
                """,
                (document_id, resource_uri, _relative_path(path, self.cache_dir), _file_size(path), _now_iso()),
            )
        self._register_json_resource_path(
            resource_uri,
            path,
            name=f"Document TOC {document_id}",
            description=f"Cached table of contents for document {document_id}.",
        )
        self.prune(protected_resource_uris={resource_uri})
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
                INSERT INTO document_sections (document_id, section_id, resource_uri, content_path, size_bytes, cached_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id, section_id) DO UPDATE SET
                    resource_uri = excluded.resource_uri,
                    content_path = excluded.content_path,
                    size_bytes = excluded.size_bytes,
                    cached_at = excluded.cached_at
                """,
                (
                    document_id,
                    section_id,
                    resource_uri,
                    _relative_path(path, self.cache_dir),
                    _file_size(path),
                    _now_iso(),
                ),
            )
        self._register_json_resource_path(
            resource_uri,
            path,
            name=f"Document Section {section_id}",
            description=f"Cached section {section_id} for document {document_id}.",
        )
        self.prune(protected_resource_uris={resource_uri})
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
        resource_uri = self.document_page_uri(document_id, page_number)
        stored_metadata = {
            **(metadata or {}),
            "document_id": document_id,
            "page_number": page_number,
            "file_path": str(path),
            "resource_uri": resource_uri,
            "media_type": media_type,
        }
        metadata_path = self._write_json(("documents", document_id, "pages", f"{page_number}.json"), stored_metadata)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO document_page_images (
                    document_id, page_number, resource_uri, file_path,
                    metadata_path, size_bytes, cached_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id, page_number) DO UPDATE SET
                    resource_uri = excluded.resource_uri,
                    file_path = excluded.file_path,
                    metadata_path = excluded.metadata_path,
                    size_bytes = excluded.size_bytes,
                    cached_at = excluded.cached_at
                """,
                (
                    document_id,
                    page_number,
                    resource_uri,
                    _relative_path(path, self.cache_dir),
                    _relative_path(metadata_path, self.cache_dir),
                    _file_size(path) + _file_size(metadata_path),
                    _now_iso(),
                ),
            )
        self._register_json_resource_path(
            resource_uri,
            metadata_path,
            name=f"Document Page {page_number}",
            description=f"Cached page image metadata for document {document_id}, page {page_number}.",
        )
        self.prune(protected_resource_uris={resource_uri})
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
        safe_filename = filename.replace("/", "_").replace("\\", "_").strip()
        if not safe_filename or safe_filename in {".", ".."}:
            safe_filename = "file"
        path = self._write_bytes(("documents", document_id, "originals", original_id, safe_filename), content)
        resource_uri = self.document_original_uri(document_id, original_id)
        stored_metadata = {
            **(metadata or {}),
            "document_id": document_id,
            "original_id": original_id,
            "file_path": str(path),
            "resource_uri": resource_uri,
            "filename": filename,
            "media_type": media_type,
        }
        metadata_path = self._write_json(("documents", document_id, "originals", original_id, "metadata.json"), stored_metadata)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO document_originals (
                    document_id, original_id, resource_uri, file_path,
                    metadata_path, size_bytes, cached_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id, original_id) DO UPDATE SET
                    resource_uri = excluded.resource_uri,
                    file_path = excluded.file_path,
                    metadata_path = excluded.metadata_path,
                    size_bytes = excluded.size_bytes,
                    cached_at = excluded.cached_at
                """,
                (
                    document_id,
                    original_id,
                    resource_uri,
                    _relative_path(path, self.cache_dir),
                    _relative_path(metadata_path, self.cache_dir),
                    _file_size(path) + _file_size(metadata_path),
                    _now_iso(),
                ),
            )
        self._register_json_resource_path(
            resource_uri,
            metadata_path,
            name=f"Document Original {original_id}",
            description=f"Cached original file metadata for document {document_id}, original {original_id}.",
        )
        self.prune(protected_resource_uris={resource_uri})
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

    def list_json_resources(
        self,
        *,
        limit: int = 20,
        document_id: str | None = None,
        resource_type: str | None = None,
    ) -> list[dict[str, Any]]:
        filters = []
        params: list[Any] = []
        if document_id is not None:
            filters.append("resource_uri LIKE ?")
            params.append(f"{self.document_uri(document_id)}%")
        if resource_type is not None:
            if resource_type == "toc":
                filters.append("resource_uri LIKE ?")
                params.append("%/toc")
            elif resource_type == "section":
                filters.append("resource_uri LIKE ?")
                params.append("%/sections/%")
            elif resource_type == "page":
                filters.append("resource_uri LIKE ?")
                params.append("%/pages/%")
            elif resource_type == "original":
                filters.append("resource_uri LIKE ?")
                params.append("%/originals/%")
            else:
                raise ValueError(f"Unknown resource_type: {resource_type}")
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT resource_uri, name, description, mime_type
                FROM json_resources
                {where}
                ORDER BY cached_at DESC, resource_uri ASC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        return [
            _json_resource_response(
                row["resource_uri"],
                name=row["name"],
                description=row["description"],
                mime_type=row["mime_type"],
            )
            for row in rows
        ]

    def get_json_resource(self, resource_uri: str) -> tuple[CachedResource, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT json_path, mime_type
                FROM json_resources
                WHERE resource_uri = ?
                """,
                (resource_uri,),
            ).fetchone()
        if row is None:
            return None
        return CachedResource(resource_uri=resource_uri, path=self.cache_dir / row["json_path"]), row["mime_type"]

    def clear_resources(
        self,
        *,
        document_id: str | None = None,
        resource_type: str | None = None,
    ) -> dict[str, Any]:
        if resource_type is not None and resource_type not in {"toc", "section", "page", "original"}:
            raise ValueError(f"Unknown resource_type: {resource_type}")

        resources = self._resources_to_clear(document_id=document_id, resource_type=resource_type)
        resource_uris = {item["resource_uri"] for item in resources}
        file_paths = {self.cache_dir / path for item in resources for path in item["paths"]}

        with self._connect() as connection:
            if resource_uris:
                placeholders = ", ".join("?" for _ in resource_uris)
                connection.execute(f"DELETE FROM json_resources WHERE resource_uri IN ({placeholders})", tuple(resource_uris))
            self._delete_resource_rows(connection, document_id=document_id, resource_type=resource_type)

        files_deleted = 0
        for path in file_paths:
            if path.exists() and path.is_file():
                path.unlink()
                files_deleted += 1
        self._prune_empty_cache_dirs()

        return {
            "resources_deleted": len(resources),
            "files_deleted": files_deleted,
            "cache_dir": str(self.cache_dir),
        }

    def prune(
        self,
        *,
        max_bytes: int | None = None,
        protected_resource_uris: set[str] | None = None,
    ) -> dict[str, Any]:
        effective_max_bytes = self.max_bytes if max_bytes is None else max_bytes
        if effective_max_bytes is None:
            return {
                "resources_deleted": 0,
                "files_deleted": 0,
                "bytes_deleted": 0,
                "cache_dir": str(self.cache_dir),
            }

        protected = protected_resource_uris or set()
        total_size = self._cache_size_bytes()
        if total_size <= effective_max_bytes:
            return {
                "resources_deleted": 0,
                "files_deleted": 0,
                "bytes_deleted": 0,
                "cache_dir": str(self.cache_dir),
            }

        target_size = effective_max_bytes // PRUNE_TARGET_DIVISOR
        victims = []
        bytes_to_delete = 0
        for resource in self._resources_for_prune():
            if resource["resource_uri"] in protected:
                continue
            victims.append(resource)
            bytes_to_delete += resource["size_bytes"]
            if total_size - bytes_to_delete <= target_size:
                break

        return self._delete_resources(victims)

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
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    cached_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS document_sections (
                    document_id TEXT NOT NULL,
                    section_id TEXT NOT NULL,
                    resource_uri TEXT NOT NULL,
                    content_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (document_id, section_id)
                );

                CREATE TABLE IF NOT EXISTS document_page_images (
                    document_id TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    resource_uri TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    metadata_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (document_id, page_number)
                );

                CREATE TABLE IF NOT EXISTS document_originals (
                    document_id TEXT NOT NULL,
                    original_id TEXT NOT NULL,
                    resource_uri TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    metadata_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (document_id, original_id)
                );

                CREATE TABLE IF NOT EXISTS json_resources (
                    resource_uri TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    json_path TEXT NOT NULL,
                    cached_at TEXT NOT NULL
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
            self._ensure_column(connection, "document_tocs", "size_bytes", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "document_sections", "size_bytes", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "document_page_images", "size_bytes", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "document_originals", "size_bytes", "INTEGER NOT NULL DEFAULT 0")

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

    def _register_json_resource_path(
        self,
        resource_uri: str,
        path: Path,
        *,
        name: str,
        description: str,
        mime_type: str = "application/json",
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO json_resources (resource_uri, name, description, mime_type, json_path, cached_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(resource_uri) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    mime_type = excluded.mime_type,
                    json_path = excluded.json_path,
                    cached_at = excluded.cached_at
                """,
                (resource_uri, name, description, mime_type, _relative_path(path, self.cache_dir), _now_iso()),
            )

    def _resources_to_clear(self, *, document_id: str | None, resource_type: str | None) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        types = [resource_type] if resource_type is not None else ["toc", "section", "page", "original"]
        with self._connect() as connection:
            if "toc" in types:
                resources.extend(
                    {"resource_uri": row["resource_uri"], "paths": [row["toc_path"]]}
                    for row in connection.execute(
                        "SELECT resource_uri, toc_path FROM document_tocs" + _document_where(document_id),
                        (() if document_id is None else (document_id,)),
                    )
                )
            if "section" in types:
                resources.extend(
                    {"resource_uri": row["resource_uri"], "paths": [row["content_path"]]}
                    for row in connection.execute(
                        "SELECT resource_uri, content_path FROM document_sections" + _document_where(document_id),
                        (() if document_id is None else (document_id,)),
                    )
                )
            if "page" in types:
                resources.extend(
                    {"resource_uri": row["resource_uri"], "paths": [row["file_path"], row["metadata_path"]]}
                    for row in connection.execute(
                        "SELECT resource_uri, file_path, metadata_path FROM document_page_images" + _document_where(document_id),
                        (() if document_id is None else (document_id,)),
                    )
                )
            if "original" in types:
                resources.extend(
                    {"resource_uri": row["resource_uri"], "paths": [row["file_path"], row["metadata_path"]]}
                    for row in connection.execute(
                        "SELECT resource_uri, file_path, metadata_path FROM document_originals" + _document_where(document_id),
                        (() if document_id is None else (document_id,)),
                    )
                )
        return resources

    def _resources_for_prune(self) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        with self._connect() as connection:
            resources.extend(
                {
                    "resource_uri": row["resource_uri"],
                    "paths": [row["toc_path"]],
                    "cached_at": row["cached_at"],
                    "size_bytes": row["size_bytes"],
                }
                for row in connection.execute("SELECT resource_uri, toc_path, size_bytes, cached_at FROM document_tocs")
            )
            resources.extend(
                {
                    "resource_uri": row["resource_uri"],
                    "paths": [row["content_path"]],
                    "cached_at": row["cached_at"],
                    "size_bytes": row["size_bytes"],
                }
                for row in connection.execute("SELECT resource_uri, content_path, size_bytes, cached_at FROM document_sections")
            )
            resources.extend(
                {
                    "resource_uri": row["resource_uri"],
                    "paths": [row["file_path"], row["metadata_path"]],
                    "cached_at": row["cached_at"],
                    "size_bytes": row["size_bytes"],
                }
                for row in connection.execute(
                    "SELECT resource_uri, file_path, metadata_path, size_bytes, cached_at FROM document_page_images"
                )
            )
            resources.extend(
                {
                    "resource_uri": row["resource_uri"],
                    "paths": [row["file_path"], row["metadata_path"]],
                    "cached_at": row["cached_at"],
                    "size_bytes": row["size_bytes"],
                }
                for row in connection.execute(
                    "SELECT resource_uri, file_path, metadata_path, size_bytes, cached_at FROM document_originals"
                )
            )
        return sorted(resources, key=lambda item: (item["cached_at"], item["resource_uri"]))

    def _delete_resources(self, resources: list[dict[str, Any]]) -> dict[str, Any]:
        resource_uris = {item["resource_uri"] for item in resources}
        file_paths = {self.cache_dir / path for item in resources for path in item["paths"]}

        with self._connect() as connection:
            if resource_uris:
                placeholders = ", ".join("?" for _ in resource_uris)
                params = tuple(resource_uris)
                connection.execute(f"DELETE FROM json_resources WHERE resource_uri IN ({placeholders})", params)
                for table in ("document_tocs", "document_sections", "document_page_images", "document_originals"):
                    connection.execute(f"DELETE FROM {table} WHERE resource_uri IN ({placeholders})", params)

        files_deleted = 0
        actual_bytes_deleted = 0
        for path in file_paths:
            if path.exists() and path.is_file():
                actual_bytes_deleted += path.stat().st_size
                path.unlink()
                files_deleted += 1
        self._prune_empty_cache_dirs()

        return {
            "resources_deleted": len(resources),
            "files_deleted": files_deleted,
            "bytes_deleted": actual_bytes_deleted,
            "cache_dir": str(self.cache_dir),
        }

    def _delete_resource_rows(
        self,
        connection: sqlite3.Connection,
        *,
        document_id: str | None,
        resource_type: str | None,
    ) -> None:
        tables = {
            "toc": "document_tocs",
            "section": "document_sections",
            "page": "document_page_images",
            "original": "document_originals",
        }
        types = [resource_type] if resource_type is not None else list(tables)
        for item_type in types:
            table = tables[item_type]
            if document_id is None:
                connection.execute(f"DELETE FROM {table}")
            else:
                connection.execute(f"DELETE FROM {table} WHERE document_id = ?", (document_id,))

    def _ensure_column(self, connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _prune_empty_cache_dirs(self) -> None:
        if not self.cache_root.exists():
            return
        for path in sorted((item for item in self.cache_root.rglob("*") if item.is_dir()), reverse=True):
            try:
                path.rmdir()
            except OSError:
                pass
        if self.cache_root.exists() and not any(self.cache_root.iterdir()):
            shutil.rmtree(self.cache_root)

    def _cache_size_bytes(self) -> int:
        with self._connect() as connection:
            return sum(
                connection.execute(f"SELECT COALESCE(SUM(size_bytes), 0) FROM {table}").fetchone()[0]
                for table in ("document_tocs", "document_sections", "document_page_images", "document_originals")
            )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _json_resource_response(
    resource_uri: str,
    *,
    name: str,
    description: str,
    mime_type: str,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "uri": resource_uri,
        "name": name,
        "description": description,
        "mimeType": mime_type,
    }
    response.update(_json_resource_identifiers(resource_uri))
    return response


def _json_resource_identifiers(resource_uri: str) -> dict[str, Any]:
    prefix = "momonga://documents/"
    if not resource_uri.startswith(prefix):
        return {}
    segments = [unquote(segment) for segment in resource_uri[len(prefix) :].split("/")]
    if len(segments) < 2 or not segments[0]:
        return {}
    identifiers: dict[str, Any] = {"document_id": segments[0]}
    if segments[1] == "toc" and len(segments) == 2:
        identifiers["resource_type"] = "toc"
    elif segments[1] == "sections" and len(segments) == 3:
        identifiers.update({"resource_type": "section", "section_id": segments[2]})
    elif segments[1] == "pages" and len(segments) == 3:
        identifiers["resource_type"] = "page"
        try:
            identifiers["page_number"] = int(segments[2])
        except ValueError:
            identifiers["page_number"] = segments[2]
    elif segments[1] == "originals" and len(segments) == 3:
        identifiers.update({"resource_type": "original", "original_id": segments[2]})
    return identifiers


def _document_where(document_id: str | None) -> str:
    return "" if document_id is None else " WHERE document_id = ?"


def _uri_segment(value: str) -> str:
    return _safe_segment(value)


def _safe_segment(value: str) -> str:
    if not value or value in {".", ".."}:
        raise ValueError("cache path segment must be non-empty and must not be . or ..")
    return quote(value, safe="-_.~")


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() and path.is_file() else 0

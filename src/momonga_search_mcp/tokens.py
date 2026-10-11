"""Server-side issuance and revocation of independently scoped MCP bearer credentials."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import tempfile
from uuid import uuid4


class TokenStore:
    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> list[dict]:
        records = json.loads(self.path.read_text(encoding="utf-8"))["tokens"]
        if not isinstance(records, list) or any(
            not isinstance(row, dict)
            or not isinstance(row.get("id"), str)
            or not isinstance(row.get("sha256"), str)
            or len(row["sha256"]) != 64
            or not isinstance(row.get("label"), str)
            or not isinstance(row.get("revoked"), bool)
            for row in records
        ):
            raise ValueError("invalid token store")
        if len({row["id"] for row in records}) != len(records):
            raise ValueError("duplicate token identifiers")
        return records

    def authenticate(self, token: str) -> str | None:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        for row in self._read():
            if not row["revoked"] and hmac.compare_digest(row["sha256"], digest):
                return row["id"]
        return None

    @contextmanager
    def _edit(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # A separate lock file survives atomic replacement and serializes CLI edits.
        with self.path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            rows = self._read() if self.path.exists() else []
            yield rows
            descriptor, temporary = tempfile.mkstemp(dir=self.path.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump({"tokens": rows}, stream, ensure_ascii=False)
                os.chmod(temporary, 0o600)
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def issue(self, label: str) -> tuple[str, str]:
        if not label.strip():
            raise ValueError("label must not be empty")
        token_id, token = uuid4().hex, secrets.token_urlsafe(32)
        with self._edit() as rows:
            rows.append(
                {
                    "id": token_id,
                    "label": label.strip(),
                    "sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                    "revoked": False,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
        return token_id, token

    def revoke(self, token_id: str) -> None:
        with self._edit() as rows:
            for row in rows:
                if row["id"] == token_id:
                    row["revoked"] = True
                    break
            else:
                raise ValueError("token identifier not found")

    def list(self) -> list[dict]:
        return [{key: value for key, value in row.items() if key != "sha256"} for row in self._read()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    issue = sub.add_parser("issue", help="Print a new credential once; store only its hash")
    issue.add_argument("--label", required=True)
    revoke = sub.add_parser("revoke")
    revoke.add_argument("--token-id", required=True)
    sub.add_parser("list")
    args = parser.parse_args(argv)
    store = TokenStore(args.store)
    if args.action == "issue":
        token_id, token = store.issue(args.label)
        print(json.dumps({"id": token_id, "token": token}))
    elif args.action == "revoke":
        store.revoke(args.token_id)
        print(json.dumps({"id": args.token_id, "revoked": True}))
    else:
        print(json.dumps(store.list(), ensure_ascii=False))
    return 0

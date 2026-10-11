"""Client token issuance persists only hashes and revokes individual access."""

import json
import stat

import pytest

from momonga_search_mcp.tokens import TokenStore, main


def test_issue_list_and_revoke_are_independent_and_never_persist_plaintext(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    first_id, first = store.issue("department-a")
    second_id, second = store.issue("agent-b")
    assert first not in store.path.read_text() and second not in store.path.read_text()
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert store.authenticate(first) == first_id
    assert store.authenticate(second) == second_id
    assert store.authenticate("invalid") is None
    assert [row["label"] for row in store.list()] == ["department-a", "agent-b"]
    assert all("sha256" not in row for row in store.list())
    store.revoke(first_id)
    assert store.authenticate(first) is None
    assert store.authenticate(second) == second_id


def test_cli_prints_new_token_once_and_list_only_contains_metadata(tmp_path, capsys):
    path = tmp_path / "tokens.json"
    assert main(["--store", str(path), "issue", "--label", "department-a"]) == 0
    issued = json.loads(capsys.readouterr().out)
    assert TokenStore(path).authenticate(issued["token"]) == issued["id"]
    assert main(["--store", str(path), "list"]) == 0
    assert issued["token"] not in capsys.readouterr().out
    assert main(["--store", str(path), "revoke", "--token-id", issued["id"]]) == 0
    assert TokenStore(path).authenticate(issued["token"]) is None


def test_unknown_revocation_and_empty_labels_fail_without_changing_store(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    store.issue("department-a")
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="not found"):
        store.revoke("unknown")
    with pytest.raises(ValueError, match="empty"):
        store.issue("  ")
    assert store.path.read_bytes() == before

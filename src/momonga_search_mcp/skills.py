"""Workflow skill resources and helper lookup."""

from __future__ import annotations

from importlib import resources
import json
from typing import Any

SKILL_INDEX_URI = "skill://index.json"
SKILL_PACKAGE = "momonga_search_mcp.skill_resources"
SKILL_DETAIL_PACKAGE = "momonga_search_mcp.skill_resources.skills"


def skill_index() -> dict[str, Any]:
    return json.loads(resources.files(SKILL_PACKAGE).joinpath("index.json").read_text(encoding="utf-8"))


def skill_resources() -> list[dict[str, Any]]:
    resources_list = [
        {
            "uri": SKILL_INDEX_URI,
            "name": "Momonga Search Skill Index",
            "description": "Lightweight index of workflow skills. Safe to read before substantive research tasks.",
            "mimeType": "application/json",
        }
    ]
    for skill in skill_index()["skills"]:
        resources_list.append(
            {
                "uri": skill["resource_uri"],
                "name": skill["title"],
                "description": skill["description"],
                "mimeType": "text/markdown",
            }
        )
    return resources_list


def read_skill_resource(uri: str) -> tuple[str, str]:
    if uri == SKILL_INDEX_URI:
        return json.dumps(skill_index(), ensure_ascii=False, separators=(",", ":")), "application/json"

    for skill in skill_index()["skills"]:
        if skill["resource_uri"] == uri:
            return _read_skill_markdown(skill["id"]), "text/markdown"
    raise ValueError(f"Unknown skill resource URI: {uri}")


def list_skills() -> list[dict[str, Any]]:
    return [
        {
            "id": skill["id"],
            "title": skill["title"],
            "resource_uri": skill["resource_uri"],
            "description": skill["description"],
            "triggers": skill.get("triggers", []),
            "recommended_first_tools": skill.get("recommended_first_tools", []),
        }
        for skill in skill_index()["skills"]
    ]


def get_skill(skill_id: str) -> dict[str, Any]:
    for skill in skill_index()["skills"]:
        if skill["id"] == skill_id:
            return {
                "id": skill["id"],
                "title": skill["title"],
                "resource_uri": skill["resource_uri"],
                "content": _read_skill_markdown(skill["id"]),
            }
    raise ValueError(f"Unknown skill id: {skill_id}")


def _read_skill_markdown(skill_id: str) -> str:
    return resources.files(SKILL_DETAIL_PACKAGE).joinpath(f"{skill_id}.md").read_text(encoding="utf-8")

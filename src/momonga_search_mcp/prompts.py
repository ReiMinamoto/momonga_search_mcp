"""Representative MCP prompts."""

from __future__ import annotations

from typing import Any

PROMPTS: dict[str, dict[str, Any]] = {
    "use_document_research": {
        "description": "Launch document research with the document-research skill.",
        "arguments": [
            {"name": "target", "description": "Company, issuer, security code, or filing target.", "required": True},
            {"name": "theme", "description": "Research theme or question.", "required": True},
        ],
        "template": (
            "Read skill://skills/document-research.md first.\n"
            "Then research {target} regarding {theme} using Momonga Search document tools.\n"
            "Retrieve only the minimum necessary sections.\n"
            "Answer with document_id, section_id, and reference_url."
        ),
    },
    "use_news_research": {
        "description": "Launch news research with the news-research skill.",
        "arguments": [{"name": "theme", "description": "News theme, event, issuer, or macro topic.", "required": True}],
        "template": (
            "Read skill://skills/news-research.md first.\n"
            "Then research news updates about {theme}.\n"
            "Use list_news or search_news.\n"
            "Return statement, news_id, and references[].\n"
            "Do not mix document ranking unless explicitly requested."
        ),
    },
    "use_evidence_answering": {
        "description": "Produce a grounded answer from already retrieved evidence.",
        "arguments": [],
        "template": (
            "Read skill://skills/evidence-answering.md first.\n"
            "Produce a grounded answer from already retrieved resources.\n"
            "Separate facts from interpretation.\n"
            "Preserve evidence identifiers."
        ),
    },
}


def prompt_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": prompt["description"],
            "arguments": prompt["arguments"],
        }
        for name, prompt in PROMPTS.items()
    ]


def get_prompt(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if name not in PROMPTS:
        raise ValueError(f"Unknown prompt: {name}")
    arguments = {} if arguments is None else arguments
    prompt = PROMPTS[name]
    required_names = [argument["name"] for argument in prompt["arguments"] if argument.get("required")]
    for required_name in required_names:
        value = arguments.get(required_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{required_name} is required")

    text = prompt["template"].format(**{name: arguments.get(name, "") for name in _argument_names(prompt)})
    return {
        "description": prompt["description"],
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": text,
                },
            }
        ],
    }


def _argument_names(prompt: dict[str, Any]) -> list[str]:
    return [argument["name"] for argument in prompt["arguments"]]

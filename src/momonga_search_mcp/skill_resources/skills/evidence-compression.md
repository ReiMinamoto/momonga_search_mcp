# Evidence Compression Skill

## Use When

Use this skill after document sections, section search excerpts, section windows, or comparable evidence snippets have been retrieved and the final answer would otherwise require carrying raw section text forward.

Use it before `evidence-answering` when the task involves synthesis, comparison, multiple sections, large sections, or any `content_mode=manifest` section that must be inspected through `search_section_contents` or `get_section_window`.

Skip this skill for a simple answer grounded in one short inline section. In that case, answer directly with `evidence-answering` and preserve the section identifiers.

## Goal

Compress retrieved document evidence into short structured `evidence_notes`. The notes should be sufficient for final answering without reintroducing raw long section bodies into the main context.

## Entry Rules

- Enter only after `document-content-retrieval`, `search_section_contents`, or `get_section_window` has returned relevant evidence in the current session.
- Do not use `resources/read` to load cached section bodies. Treat section resource URIs as provenance IDs.
- If a section was returned as `content_mode=manifest`, inspect only the needed parts with `search_section_contents` and `get_section_window`.
- If `source_resource_uri` is missing, treat the note as incomplete and do not rely on it for final answering unless the limitation is explicit.

## Workflow

1. Select the evidence to compress.
   - Prefer `search_section_contents.matches[]` and `get_section_window.content` over raw section bodies.
   - Keep each note focused on one claim from one document section.
   - For comparisons, create notes per document first, then compare the notes.

2. Produce `evidence_notes` only.
   - Return concise structured notes, not prose summaries and not raw long sections.
   - Keep `supporting_excerpt` short. Use only the minimum excerpt needed to support the claim.
   - Include `excerpt_offset` when an offset is available from section search or window retrieval.
   - Preserve `source_resource_uri` for every note.

3. Hand off to `evidence-answering`.
   - Use the compressed `evidence_notes` as the primary answer material.
   - Do not compare raw long sections directly.
   - If evidence is missing, mark the note or comparison as incomplete rather than filling gaps.

## Evidence Note Format

Return notes in this shape:

```json
{
  "evidence_notes": [
    {
      "document_id": "doc_...",
      "document_title": "有価証券報告書 2026年3月期",
      "section_id": "sec_...",
      "section_title": "事業等のリスク",
      "heading_path": ["事業の状況", "事業等のリスク"],
      "claim": "このセクションで確認できる事実",
      "supporting_excerpt": "短い抜粋",
      "excerpt_offset": 1234,
      "reference_url": "https://...",
      "source_resource_uri": "momonga://documents/doc_.../sections/sec_...",
      "confidence": "high"
    }
  ]
}
```

Required fields:

- `document_id`
- `section_id`
- `claim`
- `supporting_excerpt`
- `source_resource_uri`

Use `confidence` as `high`, `medium`, or `low`. Mark confidence `low` when the excerpt is indirect, incomplete, or lacks stable source metadata.

## Local Compression Path

Use this path by default:

1. Retrieve or cache target sections with `get_document_content`.
2. For manifest sections, search with `search_section_contents`.
3. Read only needed offsets with `get_section_window`.
4. Convert retrieved snippets/windows into `evidence_notes`.
5. Continue to `evidence-answering`.

## Subagent Summarization Path

When the host/client runtime provides subagents, large section inspection or multi-document evidence collection may be delegated to isolated subagents. The MCP server does not expose a subagent capability or subagent orchestration tool.

Do not delegate simple short-section answers to a subagent. Keep the evidence in the main context and answer directly.

The main agent should:

1. Select target `document_id`, `section_id`, and `heading_path`.
2. Delegate each document or section group to a subagent.
3. Require the subagent to return only structured `evidence_notes`.
4. Reject or re-compress raw full section text returned by the subagent.
5. Use returned `evidence_notes` for final answering.

Subagent outputs must still include `source_resource_uri` for every note. Missing source metadata makes the note incomplete.

## Avoid

- Do not paste full section bodies into `evidence_notes`.
- Do not create broad essay summaries as notes.
- Do not merge claims from multiple sections into one note unless the source fields remain unambiguous.
- Do not cite an `evidence_note` as a standalone source when `document_id`, `section_id`, or `source_resource_uri` is missing.

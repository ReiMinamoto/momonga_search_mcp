# Evidence Answering Skill

## Use When

Use this skill when producing final answers from `evidence_notes`, retrieved document sections, news statements, references, downloaded metadata, or cached resource URIs. Enter this skill only after at least one retrieval or compression step has returned usable evidence in the current session. If no such result exists yet, switch to the matching retrieval skill first.

## Goal

Produce concise grounded answers that separate retrieved facts from interpretation and preserve evidence identifiers.

## Entry Rules

- Use this skill after retrieval or when composing a final answer from tool outputs.
- If more evidence is needed, switch to the matching retrieval skill first: `document-research`, `document-content-retrieval`, `news-research`, or `file-download`.
- For document synthesis or comparison, prefer `evidence_notes` produced by `evidence-compression` over raw section bodies.
- Do not invent citations. Use only identifiers and fields present in tool results or cached resources that were actually returned.

## Workflow

1. Inventory available evidence.
   - Evidence notes: prefer notes with `document_id`, `section_id`, `claim`, `supporting_excerpt`, `source_resource_uri`, and `confidence`.
   - Documents: keep `document_id`, `section_id`, `heading_path`, `resource_uri`, and `reference_url`.
   - Document sections: keep `section_title`, `character_count`, `content_mode`, `content_available_in_cache`, and `recommended_tools` when relevant.
   - News: keep `news_id`, `statement`, `observed_at`, `related_issuers`, `macro_tags`, and `references[]`.
   - Files: keep `document_id`, `file_path`, `resource_uri`, `media_type`, and page/original identifiers.

2. Answer only from retrieved evidence.
   - State when evidence is partial.
   - State when content was not retrieved because it was `pending_release`, `external_only`, unavailable, or outside limits.
   - If snippets or news references were used only for discovery and sections were not retrieved, say that clearly.
   - If a content section was returned as `content_mode=manifest`, do not treat the unavailable body as read. Switch back to `document-content-retrieval` and use `search_section_contents` / `get_section_window` when the missing body matters.
   - If `evidence_notes` are available, answer from the notes instead of reusing raw section text.

3. Separate facts and interpretation.
   - Present directly supported facts first.
   - Label analysis, inference, or comparison as interpretation.
   - For comparisons, create or use one or more `evidence_notes` per compared document before comparing. Make sure each compared point has evidence from each side or mark the comparison as incomplete.

4. Keep citations useful.
   - Include exact identifiers in the answer or a compact evidence list.
   - When citing document evidence, include `document_id` and `section_id` when available.
   - When citing news evidence, include `news_id`.
   - Do not cite an `evidence_note` alone if `source_resource_uri`, `document_id`, or `section_id` is missing.
   - Do not paste long content when a summary plus identifiers is enough.
   - Use `published_at` as the document publication time when present, `timeline_at` for document listing/search timing, and `observed_at` for news timing. Do not call `timeline_at` or `observed_at` an official publication time unless the retrieved evidence says so.

## Avoid

- Do not claim unsupported facts.
- Do not imply that unrequested documents or references were read.
- Do not mix documents and news unless the user requested both or the workflow explicitly switched skills.
- Do not hide uncertainty caused by limited retrieved sections.
- Do not compare raw long sections directly when `evidence_notes` can be produced first.
- Do not present local `file_path` as a public source URL. Use it only as the local cached artifact location.

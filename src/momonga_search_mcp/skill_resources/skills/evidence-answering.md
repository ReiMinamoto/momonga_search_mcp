# Evidence Answering Skill

## Use When

Use this skill when producing final answers from retrieved document sections, news statements, references, downloaded metadata, or cached resource URIs. Enter this skill only after at least one of `list_documents`, `search_documents`, `get_document_toc`, `get_document_content`, `list_news`, `search_news`, `list_document_page_images`, `list_document_originals`, `get_document_page_image`, or `get_document_original` has returned an `ok` response in the current session. If no such tool result exists yet, switch to the matching retrieval skill first.

## Goal

Produce concise grounded answers that separate retrieved facts from interpretation and preserve evidence identifiers.

## Entry Rules

- Use this skill after retrieval or when composing a final answer from tool outputs.
- If more evidence is needed, switch to the matching retrieval skill first: `document-research`, `document-content-retrieval`, `news-research`, or `file-download`.
- Do not invent citations. Use only identifiers and fields present in tool results or cached resources that were actually returned.

## Workflow

1. Inventory available evidence.
   - Documents: keep `document_id`, `section_id`, `heading_path`, `resource_uri`, and `reference_url`.
   - Document sections: keep `section_title`, `character_count`, `content_mode`, `content_available_in_cache`, and `recommended_tools` when relevant.
   - News: keep `news_id`, `statement`, `observed_at`, `related_issuers`, `macro_tags`, and `references[]`.
   - Files: keep `document_id`, `file_path`, `resource_uri`, `media_type`, and page/original identifiers.
   - Retrieval context: keep `cache_hit` and `cached` when they affect what was or was not retrieved. `cache_hit` (top-level) means the whole call was served from cache; `cached` (per section/file) means that specific item was served from cache. Do not conflate them when reporting.

2. Answer only from retrieved evidence.
   - State when evidence is partial.
   - State when content was not retrieved because it was `pending_release`, `external_only`, unavailable, or outside limits.
   - If snippets or news references were used only for discovery and sections were not retrieved, say that clearly.
   - If a content section was returned as `content_mode=manifest`, do not treat the unavailable body as read. Switch back to `document-content-retrieval` and use `search_section_contents` / `get_section_window` when the missing body matters.

3. Separate facts and interpretation.
   - Present directly supported facts first.
   - Label analysis, inference, or comparison as interpretation.
   - For comparisons, make sure each compared point has evidence from each side or mark the comparison as incomplete.

4. Keep citations useful.
   - Include exact identifiers in the answer or a compact evidence list.
   - Do not paste long content when a summary plus identifiers is enough.
   - Use `published_at` as the document publication time when present, `timeline_at` for document listing/search timing, and `observed_at` for news timing. Do not call `timeline_at` or `observed_at` an official publication time unless the retrieved evidence says so.

## Avoid

- Do not claim unsupported facts.
- Do not imply that unrequested documents or references were read.
- Do not mix documents and news unless the user requested both or the workflow explicitly switched skills.
- Do not hide uncertainty caused by limited retrieved sections.
- Do not present local `file_path` as a public source URL. Use it only as the local cached artifact location.

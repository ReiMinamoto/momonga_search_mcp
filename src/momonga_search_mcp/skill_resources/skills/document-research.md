# Document Research Skill

## Use When

Use this skill for company disclosures, securities reports, earnings releases, IR documents, EDINET filings, timely disclosures, and comparisons that need document-based evidence.

## Goal

Find the minimum necessary document evidence and preserve identifiers needed for later verification: `document_id`, `section_id`, `heading_path`, `reference_url`, `timeline_at`, and issuer/security code when available.

## Entry Rules

- Before calling `search_issuers`, `list_documents`, `search_documents`, or `get_document_content`, the client must have read `skill://index.json` or called `list_skills`.
- Keep documents and news as separate result sets. If the user wants both, run document and news workflows separately and merge only in the final answer with clear labels.
- Use the MCP tool response fields as the source of truth. Do not assume unavailable API fields are hidden somewhere else in the MCP response.
- Steps 2 (`list_documents`) and 3 (`search_documents`) are independent discovery paths. Use either or both depending on the user's request; do not call both reflexively when one is enough.

## Workflow

1. Identify the issuer.
   - Use `search_issuers` when the company name, security code, or issuer identity is ambiguous.
   - Keep the selected `security_code` visible in subsequent calls when the task is issuer-specific.

2. List candidate documents.
   - Use this step when the user wants coverage by issuer, document family/type, or date range. Skip this step when a specific topic keyword is enough and Step 3 alone will work.
   - Use `list_documents` with `security_codes`, document family/type filters, or timeline filters.
   - `list_documents` requires either `security_codes` or `timeline_since`; for broad market discovery without a security code, always provide `timeline_since`.
   - MCP runtime result limit is 25.
   - Use `next_cursor` only with the same filters from the previous response.
   - Prefer `security_codes` for company-specific work.
   - Do not use document listing as a full synchronization API.

3. Search within documents.
   - Use this step when the user is asking about a topic/keyword that should be located inside document bodies. Skip if Step 2 already produced enough candidates and the user did not ask for content lookup.
   - Use `search_documents` for topic discovery.
   - Prefer short topic terms or specific keywords over long judgment-style questions.
   - Use `lexical` for exact terms and `semantic` for concept lookup. If unsure, pass `match_type="semantic"` explicitly.
   - MCP runtime `top_k` limit is 25.
   - Results are returned with `matches[]` ordered by `score` (highest first). Pick the top 1–3 matches whose `section_title` / `snippet` clearly align with the question; do not blindly pass every `section_id` to Step 6.
   - If `include_snippet=true`, treat snippets as discovery aids. Retrieve the section before using it as final evidence unless the user only asked for candidate locations.

4. Check document availability.
   - If the user only asked for document summaries, candidate documents, or candidate locations, skip Steps 4-6 and switch directly to `evidence-answering` using the listing/search results. Do not retrieve content just because a candidate document is `ready`.
   - If `content_status` is `ready`, continue to the table of contents.
   - If `content_status` is `pending_release`, do not retrieve content; report the retry timing if provided.
   - If `content_status` is `external_only`, do not retrieve content; report `reference_url`.
   - For any other value (or if `content_status` is missing after `get_document_metadata`), do not retrieve content. Report the unknown status to the user and stop document retrieval for this document.
   - `content_status` is normally returned by `list_documents` and `search_documents`. Only call `get_document_metadata` first when it is genuinely missing from those responses.

5. Read the table of contents.
   - Use `get_document_toc` before selecting sections unless section metadata was already returned by search.
   - Inspect `section_id`, `heading_path`, and `character_count`.
   - `get_document_toc` is cache-backed. A `cache_hit=true` result is enough to select sections.

6. Retrieve only relevant sections.
   - Use `get_document_content` with selected `section_ids`.
   - Keep each call within MCP section and character limits.
   - MCP runtime section limit is 5 per content call.
   - The content response may be truncated at the runtime character limit. To continue a truncated section, call again with that section's `next_offset` and exactly one `section_id` (the same one that was truncated). If a later section has `content_omitted=true`, retrieve that section in a new single-section call instead.
   - Use `return_content=false` when the user only needs a reusable resource URI or when content is too large for the immediate answer.
   - Treat cache hits and storage as MCP behavior; as the agent, reuse returned `resource_uri` values when helpful.

7. Switch to `evidence-answering` for the final response.
   - Once retrieval is sufficient, follow the `evidence-answering` skill before composing the answer.
   - Cite the specific `document_id`, `section_id`, `heading_path`, and `reference_url` where applicable.
   - Separate facts retrieved from documents from your interpretation.

## Avoid

- Do not claim a filing or section was read unless it was retrieved or explicitly present in a tool result.
- Do not mix news ranking with document ranking unless the user asks for both.
- Do not fetch broad document content when a TOC or search hit can narrow the section choice.
- Do not treat `timeline_at` as the official publication time; it is the normalized timeline field used for listing and filtering.

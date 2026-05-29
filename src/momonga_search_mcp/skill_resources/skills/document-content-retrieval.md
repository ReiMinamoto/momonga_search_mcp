# Document Content Retrieval Skill

## Use When

Use this skill when `document_id` is already known, the user asks to read specific document content, or section IDs need validation.

## Goal

Retrieve only the document sections needed for the task while preserving `resource_uri` values for reuse. MCP handles local caching; the agent should focus on choosing the right sections and respecting visible limits.

## Entry Rules

- Before calling `get_document_content`, the client must have read `skill://index.json` or called `list_skills`.
- `get_document_toc` and `get_document_content` require the MCP cache manager at runtime. If the tool reports that the cache manager is unavailable, stop and surface that setup error instead of retrying.
- Only use this skill when a `document_id` is known. If the user gives only an issuer, topic, or date range, start with `document-research`.

## Workflow

1. Confirm the target document.
   - If only a company or topic is known, use `document-research` first.
   - Call `get_document_metadata` only when this session has not already produced a response containing `content_status` for this `document_id`. Do not call it reflexively.
   - Proceed only when `content_status=ready`. For `pending_release`, report retry timing if available. For `external_only`, do not retry content retrieval through Momonga; if `reference_url` is present, read that external URL with the available browsing/fetch tool before answering. If no `reference_url` is present or it cannot be read, report that limitation. For any other value or a missing `content_status`, stop content retrieval and report the status.

2. Read or reuse the table of contents.
   - If document metadata shows `character_count` is 10,000 characters or fewer, retrieve the full document by calling `get_document_content` with only `document_id` instead of selecting sections.
   - Call `get_document_toc` unless you already have reliable `section_id`, `heading_path`, and `character_count` from a previous tool result.
   - Interpret `get_document_toc.toc_mode` before selecting sections:
     - `sections`: `toc` already contains section selectors. Choose the relevant `section_id` values directly.
     - `outline`: `toc` contains heading nodes, not section selectors. Inspect the returned nodes, choose the relevant node's `heading_path`, then call `get_document_toc` again with `path_prefix` set to that `heading_path`. Add `include_sections=true` when section selectors are needed inside that subtree.
     - `subtree`: use the returned subtree to narrow the section set. If section selectors are still absent and needed, call `get_document_toc` again with the same `path_prefix` and `include_sections=true`.
   - Use `heading_path` and `character_count` to choose a narrow section set.
   - A cached TOC response with `cache_hit=true` is valid. Do not refresh it unless the user explicitly asks.

3. Retrieve selected sections.
   - For larger documents, call `get_document_content` with one to a few relevant `section_ids`.
   - When multiple relevant sections are needed, sum their `character_count`; if the total is comfortably below 10,000 characters, retrieve them together in one call.
   - MCP runtime section limit is 5 per call.
   - If more than 5 relevant sections are needed, split them into multiple `get_document_content` calls. Keep each call focused and within the 10,000 character response cap; retrieve the most relevant batch first.
   - The MCP response is capped by the runtime character limit, 10,000 characters per call.
   - Use `offset` only to continue a single truncated section.
   - Do not pass multiple section IDs with `offset`.
   - When a section response has `truncated=true`, continue with that section's `next_offset` and the same single `section_id`.
   - If a later section has `content_omitted=true` with `omitted_reason=character_limit_reached`, retrieve that section in a new call with that single `section_id`; do not treat it as a continuation from `next_offset`.
   - If multiple sections in the same response are `truncated=true` or `content_omitted=true`, continue them one at a time (first the section the user needs most), each in its own follow-up call with a single `section_id`.
   - Use `return_content=false` when the content should be stored and referenced later but not injected into the current response.
   - Retrieved sections are stored locally even when `return_content=false`.

4. Reuse returned resources.
   - Preserve returned `resource_uri` values.
   - Preserve `cache_hit`, per-section `cached`, and continuation fields when they affect the next step.
   - `cache_hit` (top-level) is true when this whole call was served from cache without an API request. `cached` (per section) is true when that specific section was returned from cache rather than freshly fetched. Report them with that distinction; never claim "served from cache" if `cache_hit=false`.
   - A cached response is authoritative for reuse; do not call again just to refresh unless the user explicitly asks.

5. Report limits clearly.
   - If a section is too large, truncated, or omitted by the call limit, tell the user which section was partial or omitted and whether a section-level `next_offset` is available.
   - If a limit prevents retrieval, reduce section count or ask for a narrower target.

6. Switch to `evidence-answering` for the final response.
   - Once the required sections are retrieved (or known to be unavailable), follow the `evidence-answering` skill before composing the answer.

## Required Evidence Fields

When content is used in an answer, keep `document_id`, `section_id`, `section_title`, `heading_path`, `character_count`, `resource_uri`, and `reference_url` when available. `heading_path` usually comes from the TOC, while `section_title` and `character_count` come from content responses.

## Avoid

- Do not infer section IDs from headings by hand when TOC is available.
- Do not retrieve all sections by default.
- Do not describe MCP cache implementation details to the user; only expose returned `cached` and `resource_uri` when relevant.
- Do not use `offset` for pagination across different sections; it is only a character offset within one section.

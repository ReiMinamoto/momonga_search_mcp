# Document Content Retrieval Skill

## Use When

Use this skill when `document_id` is already known, the user asks to read specific document content, or section IDs need validation.

## Goal

Retrieve only the document sections needed for the task while preserving `resource_uri` values for reuse. MCP handles local caching; the agent should focus on choosing the right sections and respecting visible limits.

## Entry Rules

- Only use this skill when a `document_id` is known. If the user gives only an issuer, topic, or date range, start with `document-research`.

## Workflow

1. Confirm the target document.
   - If only a company or topic is known, use `document-research` first.
   - Call `get_document_metadata` when this session has not already produced a response containing both `content_status` and document-level `character_count` for this `document_id`.
   - Proceed only when `content_status=ready`. For `pending_release`, report retry timing if available. For `external_only`, do not retry content retrieval through Momonga; if `reference_url` is present, read that external URL with the available browsing/fetch tool before answering. If no `reference_url` is present or it cannot be read, report that limitation. For any other value or a missing `content_status`, stop content retrieval and report the status.

2. Read or reuse the table of contents.
   - If the confirmed document-level `character_count` is 10,000 or less, skip `get_document_toc` and call `get_document_content` with `allow_full_document=true` unless the task already has specific `section_id` values. The synthetic full-document section is inline up to 10,000 characters.
   - For larger documents, retrieve the full document by omitting `section_ids` only when the user explicitly needs the whole document cached as one synthetic section; in that case pass `allow_full_document=true`. Otherwise select sections from the TOC.
   - Call `get_document_toc` unless you already have reliable `section_id`, `heading_path`, and `character_count` from a previous tool result.
   - Interpret `get_document_toc.toc_mode` before selecting sections:
     - `sections`: `toc` already contains section selectors. Choose the relevant `section_id` values directly.
     - `outline`: `toc` contains heading nodes, not section selectors. Inspect the returned nodes, choose the relevant node's `heading_path`, then call `get_document_toc` again with `path_prefix` set to that `heading_path`. Add `include_sections=true` when section selectors are needed inside that subtree.
     - `subtree`: use the returned subtree to narrow the section set. If section selectors are still absent and needed, call `get_document_toc` again with the same `path_prefix` and `include_sections=true`.
   - Use `heading_path` and `character_count` to choose a narrow section set.

3. Retrieve selected sections.
   - For larger documents, call `get_document_content` with one to a few relevant `section_ids`.
   - When multiple relevant sections are needed, retrieve up to 5 selected sections in one call. Each section is independently returned inline or as a manifest based on the inline section threshold.
   - MCP runtime section limit is 5 per call.
   - If more than 5 relevant sections are needed, split them into multiple `get_document_content` calls only to cache the selected sections. `get_document_content` does not paginate section text; use `search_section_contents` and `get_section_window` for long section bodies.
   - When a section response has `content_mode=manifest`, do not try to read the section through `resources/read`. Use `search_section_contents` to find relevant excerpts and `get_section_window` to read only the needed offset range.
   - When a section is over the inline threshold, `get_document_content` returns a manifest instead of partial text. Use search/window retrieval for the section body.
   - Use `return_content=false` when the content should be stored and referenced later but not injected into the current response.
   - Retrieved sections are stored locally even when `return_content=false`.

4. Reuse returned resources.
   - Preserve returned `resource_uri` values.
   - Treat section `resource_uri` values as provenance IDs, not as a path to load full cached text through `resources/read`.
   - For cached section text, use `search_section_contents` for short excerpts or `get_section_window` for a bounded offset range.
   - Preserve `content_mode` when it affects the next step.

5. Report limits clearly.
   - If a section is returned as `content_mode=manifest`, tell the user which section still needs search/window retrieval when its body matters.
   - If a limit prevents retrieval, reduce section count or ask for a narrower target.

6. Switch to final answering, with compression only when it helps.
   - Once the required sections, excerpts, or windows are retrieved, follow the `evidence-compression` skill when the answer requires synthesis, comparison, multiple sections, or any large section.
   - The compression step should produce structured `evidence_notes`.
   - For a simple answer from one short inline section, skip compression and go directly to `evidence-answering`.
   - After compression, follow the `evidence-answering` skill before composing the answer.

## Required Evidence Fields

When content is used in an answer, keep `document_id`, `section_id`, `section_title`, `heading_path`, `character_count`, `resource_uri`, and `reference_url` when available. `heading_path` usually comes from the TOC, while `section_title` and `character_count` come from content responses.

## Avoid

- Do not infer section IDs from headings by hand when TOC is available.
- Do not retrieve all sections by default.
- Do not describe MCP cache implementation details to the user; preserve returned identifiers instead.

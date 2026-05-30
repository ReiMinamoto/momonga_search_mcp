# File Download Skill

## Use When

Use this skill when the user asks to download page images, original PDFs, XBRL, ZIP files, or other original document files.

## Goal

Download only files the API reports as available, with explicit user/tool permission, and return local file metadata without analyzing file contents in the MVP.

## Entry Rules

- Only use this skill when `document_id` is known. If the user gives only an issuer, company name, topic, date range, or document title, switch to `document-research` first to identify the document.
- Download tools retrieve exactly one target per call: one page image or one original file.
- The explicit permission flag is a tool argument: `allow_file_download=true`. Without that exact boolean value, download tools must not be called.
- `allow_file_download` is a tool-level safety flag, not a chat-level consent prompt. If the user's request already implies "download" or "save the file", set the flag without asking them again. Ask only when intent is ambiguous (e.g. the user asked about availability, not retrieval).

## Workflow

1. List availability first.
   - For page images, call `list_document_page_images`.
   - For original files, call `list_document_originals`.
   - Only request page numbers or `original_id` values returned by those tools.
   - `list_document_page_images` returns `page_images` as the allowed page number list.
   - `list_document_originals` returns `originals[].original_id`, `filename`, and `media_type`.

2. Require explicit download permission.
   - Call `get_document_page_image` or `get_document_original` only with `allow_file_download=true`.
   - Do not download automatically just because a URL or document ID exists.
   - If the user asked only whether files exist, stop after the list tool.

3. Download narrow targets.
   - Download one page or one original per tool call.
   - Download only the pages or originals needed for the user request.
   - If many pages are requested, list availability and ask for a narrower range unless the user has already specified exact pages.

4. Return download metadata.
   - Preserve `file_path`, `resource_uri`, `media_type`, `document_id`, and `page_number` or `original_id`.
   - For originals, preserve `filename` when returned.
   - Do not expect the MCP response to include file bytes or full manifest metadata.

5. Hand off when the user wants more than the file.
   - If the user also wants the content read or summarized, switch to `document-content-retrieval` (when `document_id` is known) or `document-research` (when discovery is still needed). File contents are not analyzed by this skill in the MVP.
   - For citing the downloaded file in a final answer, switch to `evidence-answering` with the returned `file_path` and `resource_uri`.

## Avoid

- Do not treat `reference_url` as a direct original file URL.
- Do not guess available originals from document type or filename.
- Do not analyze images, PDFs, or XBRL contents in the MVP unless a separate tool explicitly supports analysis.
- Do not expose local cache internals beyond returned paths and resource URIs.
- Do not call download tools with a page number or `original_id` that was not returned by the corresponding list tool, even if the endpoint might accept it.

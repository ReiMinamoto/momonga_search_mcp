# News Research Skill

## Use When

Use this skill for recent updates, news statements, market events, macroeconomic or policy updates, geopolitical events, and normalized update streams.

## Goal

Find relevant Momonga news statements and preserve `news_id`, `statement`, `observed_at`, macro/security tags, related issuers, and `references[]`.

## Entry Rules

- Before calling `list_news` or `search_news`, the client must have read `skill://index.json` or called `list_skills`.
- News responses are not cached at the API level in the MVP, so repeat calls may return updated results.
- News results are normalized statements with references, not article bodies and not document sections.
- `macro_tags` is a closed enum of English labels. Allowed values are exactly: `Economic Indicators`, `Monetary Policy`, `Fiscal Policy`, `Regulatory Policy`, `Trade & Geopolitical Events`, `Financial Stability`, `External Shocks`. Do not invent or translate values (e.g. `金融政策` or `monetary policy` will be rejected).

## Workflow

1. Choose discovery mode.
   - Use `list_news` for timeline-style browsing by security code, macro tag, or date range.
   - Use `search_news` for semantic or keyword lookup.
   - `list_news` requires at least one of `security_codes`, `macro_tags`, or `timeline_since`.
   - Use `timeline_since` and `timeline_until` as filters over news `observed_at`.
   - Default runtime `limit` is 20 for `list_news` (overridable via `MOMONGA_MCP_MAX_LIST_LIMIT`), and default runtime `top_k` is 10 for `search_news` (overridable via `MOMONGA_MCP_MAX_SEARCH_TOP_K`).
   - Use `next_cursor` only with the same list filters from the previous response.

2. Keep news separate from documents.
   - Treat news as normalized statements with references, not article bodies.
   - Do not combine document search and news search rankings into one list.
   - If the user asks for "latest" or "recent", state the concrete date range you queried.

3. Preserve references.
   - Return `news_id` and `references[]`.
   - If a referenced document must be inspected, explicitly switch to `document-research`.
   - Do not imply that `references[]` were opened unless document tools were actually used.

4. Switch to `evidence-answering` for the final response.
   - Once relevant news statements are gathered, follow the `evidence-answering` skill before composing the answer.
   - State the date or timeline range used.
   - Distinguish reported news statements from your interpretation of market impact.
   - Keep `related_issuers` and `macro_tags` when they explain why a result matched.

## Avoid

- Do not imply that `references[]` were opened unless document tools were used.
- Do not use news tools as a substitute for securities report content.
- Do not fetch document content unless the user asks for evidence beyond the news statement.
- Do not report a news `observed_at` value as an official corporate publication timestamp.

# News Research Skill

## Use When

Use this skill for recent updates, news items, market events, macroeconomic or policy updates, geopolitical events, and normalized update streams.

## Goal

Find relevant Momonga news items and preserve `news_id`, `title`, `body`, `observed_at`, related issuers, and `references[]`.

## Entry Rules

- News responses are not cached at the API level in the MVP, so repeat calls may return updated results.
- Each news item is a `title` and a one-to-three-sentence `body` written from the sources in `references[]`. It is not the text of a press article and not a document section.

## Workflow

1. Choose discovery mode.
   - Use `list_news` for timeline-style browsing by security code or date range.
   - Use `search_news` for semantic or keyword lookup.
   - `list_news` requires at least one of `security_codes` or `timeline_since`.
   - Use `timeline_since` and `timeline_until` as filters over news `observed_at`.
   - MCP runtime `limit` is 25 for `list_news`, and MCP runtime `top_k` is 25 for `search_news`.
   - Use `next_cursor` only with the same list filters from the previous response.

2. Keep news separate from documents.
   - Treat `body` as the full news text. There is no longer article behind it to fetch.
   - Do not combine document search and news search rankings into one list.
   - If the user asks for "latest" or "recent", state the concrete date range you queried.

3. Preserve references.
   - Return `news_id` and `references[]`.
   - When quoting or summarizing a news `body`, explicitly keep the cited `news_id` with it.
   - Treat `references[]` as external reference URLs.
   - Do not imply that `references[]` were opened unless an external browsing or fetch workflow actually opened them.

4. Switch to `evidence-answering` for the final response.
   - Once relevant news items are gathered, follow the `evidence-answering` skill before composing the answer.
   - State the date or timeline range used.
   - Distinguish reported news from your interpretation of market impact.
   - Keep `related_issuers` when they explain why a result matched.

## Avoid

- Do not imply that `references[]` were opened unless an external browsing or fetch workflow actually opened them.
- Do not use news tools as a substitute for securities report content.
- Do not fetch document content unless the user asks for evidence beyond the news body.
- Do not report a news `observed_at` value as an official corporate publication timestamp.

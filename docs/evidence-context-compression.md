# Evidence / Context Compression Layer

## 目的

Momonga MCP では、取得済みの文書根拠を再利用できるようにしつつ、cache済みの全文がそのまま大きなコンテキストとして再注入される経路を避ける。

cache 自体には section 本文を保持してよい。ただし `resources/read` で `momonga://...` URI を読む場合、その URI は「全文を読むための入口」ではなく「根拠の所在を示すID」として扱う。resource read は compact な manifest または metadata を返し、cache済み本文そのものは返さない。

MCP server は data provider に徹する。文書、TOC、section、検索excerpt、bounded window、`document_id`、`section_id`、`source_resource_uri` などの根拠IDを安定して返すことが責務であり、subagent起動、section分配、要約統合、final answer construction は host / client / agent runtime 側の責務とする。

## Resource Policy

- `momonga://documents/{document_id}/sections/{section_id}` は、cache済み section の根拠所在を表す。
- section resource を読むと、section metadata、`content_available_in_cache`、`read_policy`、`source_resource_uri` を返す。
- section resource read では `content`、`text`、`raw_content` などの全文フィールドを返さない。
- TOC resource read は compact な manifest を返す。TOC の outline や subtree が必要な場合は `get_document_toc` を使う。
- page / original resource read は metadata のみを返す。binary file の取得は、明示的な download tool と `allow_file_download=true` を必要とする。

## Progressive Disclosure

tool response では、MCP 側がサイズを見て「短いものはその場で返す / 長いものは段階的に開かせる」を自動判断する。agent に毎回サイズ判断や次 tool 選択を任せず、tool response の `*_mode`、`reason`、閾値、次 action template で判断理由と次の導線を明示する。

`resources/read` は例外で、短い resource であっても原則として manifest / metadata のみを返す。resource URI は全文取得の裏口ではなく、`source_resource_uri` として根拠所在を指す ID として扱う。

| 対象 | 短い場合 | 長い場合 |
| --- | --- | --- |
| `get_document_toc` | TOC entries を直接返す | outline / subtree / aggregate を返す |
| `get_document_content` | section を cache に保存し、小さい section 本文を直接返す | section を cache に保存したうえで本文は返さず manifest と次 tool 導線を返す |
| `resources/read(section)` | manifest のみ | manifest のみ |
| `search_section_contents` | 短い excerpt を返す | 固定 match 上限で打ち切り、refine 用の `next_action` を返す |
| `get_section_window` | 指定 window を返す | `max_characters` で制限する |

現在の固定閾値と default は次の通り。

- TOC direct: `toc` item count が 50 以下なら `toc_mode=sections`、超える場合は `toc_mode=outline`。
- section inline: 通常 section は `character_count` が 3000 以下なら inline、超える場合は manifest。
- full document inline: `allow_full_document=true` の synthetic section は `character_count` が 10000 以下なら inline、超える場合は manifest。
- call section limit: `get_document_content.section_ids` は1回5件まで。
- section window: default 1500 文字、hard max 5000 文字。
- search excerpt: default `context_chars=150`、hard max 300、match count は 15 固定。16件目が存在する場合は `matches_truncated=true` と refine 用の `next_action` を返す。

返却形式も固定する。

- TOC は `toc_mode` と `selection_policy.reason` を返す。大きい TOC の場合は、特定の枝を勝手に選ぶのではなく、返却された outline から relevant な `heading_path` を選ぶ `next_action_template` を返す。
- section は `content_mode` と必要に応じて `reason` を返す。inline の場合だけ `content` を含め、manifest の場合は `source_resource_uri`、`content_available_in_cache`、`recommended_tools`、`next_action` を返す。

本文取得の通常ルートも固定する。

- document-level `character_count` が 10000 以下で確認できる文書は、特定の `section_id` が既に必要な場合を除き、TOC を省略して `get_document_content(allow_full_document=true)` で1つの synthetic section として読む。
- 10000 を超える文書、または document-level `character_count` が確認できない文書は、`get_document_toc`、section selection、`get_document_content(section_ids=...)` の順に取得する。
- `section_ids` を省略した full document retrieval は `allow_full_document=true` を必須にする。10000 を超える本文は manifest にし、本文確認は `search_section_contents` / `get_section_window` へ進める。

## 本文取得の導線

section 本文を model context に入れる場合は、上限付きの retrieval tool を使う。

- `search_section_contents` は cache済み section 内を NFKC + casefold 正規化で検索し、元本文基準の offset と短い抜粋だけを返す。
- `get_section_window` は指定 offset 周辺の bounded window だけを返す。
- `get_document_content` は section の取得と cache 保存に使える。小さい本文は直接返してよいが、大きい section は search/window retrieval へ誘導する。

この方針により、`source_resource_uri` による根拠追跡を維持しつつ、main context に入る本文量を抑える。

## Evidence Notes

最終回答では、タスクが synthesis、comparison、multiple sections、large section を含む場合に、raw section body よりも `evidence_notes` を優先する。短い単一sectionからの単純回答では、圧縮せず `evidence-answering` へ直接進んでよい。

`evidence_note` は MCP tool response や永続 resource ではなく、回答直前に host/model workflow が作る非永続の中間生成物である。`docs/tool_responses.md` には載せず、workflow/design contract として `evidence-compression.md` とこの設計文書に定義する。

`evidence_note` は以下を保持する。

- document / section の identifier
- document title / section title / heading path
- 簡潔な claim
- 短い supporting excerpt
- 取得できる場合は excerpt offset
- `source_resource_uri`
- `reference_url`
- confidence または limitation

`supporting_excerpt` は長文化を避けるため、workflow上の短い抜粋として扱う。`evidence_note` 自体が context compression の出力なので、raw section body の代替として肥大化させない。

local path では、大section、複数section、複数文書比較のときに section を取得または検索し、必要箇所を `evidence_notes` に圧縮してから回答する。

subagent が使える環境でも同じ方針を守る。section の調査を subagent に委譲してよいが、main agent に返すのは structured な `evidence_notes` のみにする。subagent output から raw full section を main context に持ち込まない。

MCP server 側には `subagents` capability、subagent起動tool、subagent request/response schema、subagent validation tool は追加しない。subagent実行は host / client 側の orchestration であり、MCP は同じ bounded retrieval API と provenance ID を提供する。

`evidence_notes` も永続化しない。`create_evidence_note` tool、`momonga://evidence-notes/...` resource、`list_cached_resources` の `evidence_note` type は追加しない。根拠を再確認する場合は、`source_resource_uri` と `search_section_contents` / `get_section_window` で元sectionへ戻る。

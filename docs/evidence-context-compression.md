# Evidence / Context Compression Layer

## 目的

Momonga MCP では、取得済みの文書根拠を再利用できるようにしつつ、cache済みの全文がそのまま大きなコンテキストとして再注入される経路を避ける。

cache 自体には section 本文を保持してよい。ただし `resources/read` で `momonga://...` URI を読む場合、その URI は「全文を読むための入口」ではなく「根拠の所在を示すID」として扱う。resource read は compact な manifest または metadata を返し、cache済み本文そのものは返さない。

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
| `search_section_contents` | 短い excerpt を返す | `max_matches` と `context_chars` で制限する |
| `get_section_window` | 指定 window を返す | `max_characters` で制限する |

初期閾値は固定値でよいが、具体値は実装時に定数または config として定義する。

- TOC direct: `toc` item count が `MAX_DIRECT_TOC_SECTIONS` 以下。
- section inline: `character_count` が inline threshold 以下、かつ response 全体が hard cap に収まる。
- section manifest: inline threshold を超える section。
- full document inline: `section_ids` なしの場合は full document inline threshold 以下の document だけ許可する。超える場合は `get_document_toc` に誘導する。
- response hard cap: section 単体の上限とは別に tool response 全体の serialized size cap を持つ。
- window: default と hard max を分けて持つ。
- search excerpt: `context_chars` と `max_matches` の上限を持つ。

返却形式は自動判断でも固定する。

- TOC は `toc_mode` と `selection_policy.reason` を返す。大きい TOC の場合は、特定の枝を勝手に選ぶ `recommended_next_action` ではなく、返却された outline から relevant な `heading_path` を選ぶ `next_action_template` を返す。
- section は `content_mode` と `reason` を返す。inline の場合だけ `content` を含め、manifest の場合は `source_resource_uri`、`content_available_in_cache`、`recommended_tools` を返す。

`get_document_content` の full document fetch は section fetch と分けて扱う。`section_ids` が省略された場合、metadata の `character_count` が full document inline threshold 以下のときだけ full document retrieval を許可する。threshold を超える document は、巨大 document を丸ごと取得してから切るのではなく、`get_document_toc`、section selection、`get_document_content(section_ids=...)` の順に誘導する。

少なくとも、tool response 全体の hard cap、section inline threshold、full document inline threshold、TOC direct threshold、section window default / hard max、search excerpt limits、evidence excerpt max は分けて持つ。

## 本文取得の導線

section 本文を model context に入れる場合は、上限付きの retrieval tool を使う。

- `search_section_contents` は cache済み section 内を検索し、短い抜粋だけを返す。
- `get_section_window` は指定 offset 周辺の bounded window だけを返す。
- `get_document_content` は section の取得と cache 保存に使える。小さい本文は直接返してよいが、大きい section は search/window retrieval へ誘導する。

この方針により、`source_resource_uri` による根拠追跡を維持しつつ、main context に入る本文量を抑える。

## Evidence Notes

最終回答では、raw section body よりも `evidence_note` を優先する。

`evidence_note` は以下を保持する。

- document / section の identifier
- document title / section title / heading path
- 簡潔な claim
- 短い supporting excerpt
- 取得できる場合は excerpt offset
- `source_resource_uri`
- `reference_url`
- confidence または limitation

`supporting_excerpt` は長文化を避けるため、固定の文字数上限を持つ。`evidence_note` 自体が context compression の出力なので、raw section body の代替として肥大化させない。

local path では、section を取得または検索し、必要箇所を `evidence_note` に圧縮してから回答する。

subagent が使える環境でも同じ方針を守る。section の調査を subagent に委譲してよいが、main agent に返すのは structured な `evidence_notes` のみにする。subagent output から raw full section を main context に持ち込まない。

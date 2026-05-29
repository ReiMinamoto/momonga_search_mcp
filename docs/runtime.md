# Runtime Behavior

この文書は Momonga Search MCP の実行時仕様、固定ガードレール、cache方針をまとめます。tool response のfieldや API endpoint 対応表は `docs/tool_responses.md` を参照してください。

## 対応範囲

- MCP transport: stdio
- MCP protocolVersion: `2025-11-25`
- Python: `>=3.13`
- tool response: full payloadは `structuredContent` にJSON objectとして返し、`content[].text` は短いsummaryだけを返します。
- tool metadata: `tools/list` は `title`、`annotations`、主要fieldの `outputSchema` を返します。`outputSchema` はMCP tool responseのトップレベル契約を示すもので、API由来のネストした構造は後方互換性のため緩く扱います。

## 固定ガードレール

MCP側では、巨大なtool responseを避けるために実行時上限を固定しています。

| 対象 | 固定上限 |
| --- | ---: |
| list系toolの `limit` | `25` |
| search系toolの `top_k` | `25` |
| `get_document_content` 1回あたりの `section_ids` | `5`。小さい文書の全文取得時は省略可 |
| `get_document_content` inline section 文字数 | `3000`。超える section は本文を返さず manifest を返す |
| `search_section_contents.context_chars` | `500` |
| `search_section_contents.max_matches` | `15` |
| `get_section_window.max_characters` | `5000` |
| Momonga Search APIへのHTTP request timeout | `15` 秒 |

`get_document_content` は取得した本文を cache に保存しますが、inline で返すのは小さい section だけです。`character_count` が inline threshold を超える section は、`content_mode=manifest`、`content_available_in_cache=true`、`recommended_tools` を返し、本文は返しません。長い section の確認は、cache済み本文に対して `search_section_contents` で短い抜粋を探し、必要箇所だけ `get_section_window` で読みます。

## キャッシュ方針

MCP cache は必須です。本文、TOC、page image、original file はローカル resource として保存し、LLM/Agent には必要なID、短い文脈、明示的に要求された本文範囲だけを返します。

cache可否の基準は、取得対象が不変または実質不変かどうかです。

キャッシュするもの:

| 対象 | 理由 |
| --- | --- |
| document toc | `document_id` に紐づくsection構造で、content ready後は実質不変として扱えるため。 |
| document section本文 | `document_id + section_id` で固定される本文で、同じsectionの再取得を避けるべきため。 |
| page image実体 | `document_id + page_number` に紐づく文書ページの実体で、実質不変として扱えるため。 |
| original file実体 | `document_id + original_id` に紐づく元ファイル実体で、実質不変として扱えるため。 |

キャッシュしないもの:

| 対象 | 理由 |
| --- | --- |
| issuer search結果 | issuer情報、上場状態、検索結果の並びが変わりうるため。 |
| document list結果 | 新規開示、訂正、availability、並びが変わりうるため。 |
| document metadata / status | `content_status`、`content_available`、`image_available` などが変わりうるため。 |
| document search結果 | 検索index、ranking、hit内容が更新されうるため。 |
| news list/search結果 | 最新性そのものが価値で、古い結果を返すリスクが高いため。 |
| page image / original list結果 | 取得可否や一覧内容を都度APIで確認すべきため。 |

キャッシュ保存先は `MOMONGA_SEARCH_MCP_CACHE_DIR`、OS標準のuser cache directoryの順に解決します。Linuxでは `$XDG_CACHE_HOME/momonga-search-mcp` または `~/.cache/momonga-search-mcp`、macOSでは `~/Library/Caches/momonga-search-mcp`、Windowsでは `%LOCALAPPDATA%\\momonga-search-mcp\\Cache` が標準です。`MOMONGA_SEARCH_MCP_CACHE_DIR` は絶対pathで指定してください。

```sh
export MOMONGA_SEARCH_MCP_CACHE_DIR=/home/user/.cache/momonga-search-mcp
```

cache容量上限は `MOMONGA_SEARCH_MCP_CACHE_MAX_GB` で指定します。デフォルトは `1` GBです。serverはcache書き込み後に上限を超えている場合、今回書き込んだresourceを保護しつつ、古いcached resourceから上限の半分以下になるまで自動pruneします。

キャッシュを削除する場合:

```sh
momonga-search-mcp-cache clear
```

特定文書や種類だけを削除する場合:

`--resource-type` には次のいずれかを指定できます。

| 値 | 削除対象 |
| --- | --- |
| `toc` | document toc |
| `section` | document section本文 |
| `page` | page image実体 |
| `original` | original file実体 |

```sh
momonga-search-mcp-cache clear --document-id doc_123 --resource-type section
```

APIから取り直したい場合は、対象のcacheを削除してから再取得します。

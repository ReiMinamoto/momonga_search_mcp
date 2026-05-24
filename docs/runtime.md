# Runtime Behavior

この文書は Momonga Search MCP の実行時仕様、内部利用量記録、cache方針をまとめます。tool response のfieldや API endpoint 対応表は `docs/tool_responses.md` を参照してください。

## 対応範囲

- MCP transport: stdio
- MCP protocolVersion: `2025-11-25`
- Python: `>=3.13`
- tool response: full payloadは `structuredContent` にJSON objectとして返し、`content[].text` は短いsummaryだけを返します。
- tool metadata: `tools/list` は `title`、`annotations`、主要fieldの `outputSchema` を返します。`outputSchema` はMCP tool responseのトップレベル契約を示すもので、API由来のネストした構造は後方互換性のため緩く扱います。

## 内部利用量記録

MCP側では、API利用量の観測用にtoolごとのcredit目安を内部記録します。この情報はtool responseには含めず、モデルの取得判断には使わせません。

| tool | MCP側のcredit扱い |
| --- | --- |
| `list_news` | API callごとに1 credit |
| `search_documents` | API callごとに1 credit |
| `search_news` | API callごとに1 credit |
| `get_document_content` | API callごとに2 / 4 / 8 credits。実消費を推定できない場合は最大8 creditsとして会計 |
| `get_document_page_image` | cache missごとに1 credit |
| `get_document_original` | cache missごとに8 credits |

`get_document_content` はMomonga Search API側の実消費が本文量で 2 / 4 / 8 credits に変わります。MCP側では、APIレスポンスヘッダーの `x-quota-compute-remaining` 差分から実消費を推定できる場合は内部記録に実値を使います。直接の実消費fieldがないため、差分が取れない場合や 2 / 4 / 8 以外の差分になった場合は最大値の8 creditsとして記録します。

## キャッシュ方針

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

デフォルトのキャッシュ保存先は `~/.cache/momonga-search-mcp` です。workspace内に置く場合は、誤commitを避けるため `.cache/` や `momonga-search-mcp-cache/` のようなignore済みdirectoryを指定してください。

```sh
export MOMONGA_MCP_CACHE_DIR=.cache/momonga-search-mcp
```

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

cache hitを使わず常にAPIから取り直したい場合は、次のどちらかを指定します。

```sh
export MOMONGA_MCP_CACHE_ENABLED=false
# または
export MOMONGA_MCP_DISABLE_CACHE=1
```

このモードではTOC/本文のcache hitと保存を無効化します。page image / original file は明示的なdownload toolなので、file_path返却のため取得した実体ファイルは引き続き保存します。

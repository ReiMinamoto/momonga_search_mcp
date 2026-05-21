# Runtime Behavior

この文書は Momonga Search MCP の実行時仕様、credit accounting、cache方針をまとめます。tool response のfieldや API endpoint 対応表は `docs/tool_responses.md` を参照してください。

## 対応範囲

- MCP transport: stdio
- MCP protocolVersion: `2024-11-05`
- Python: `>=3.13`
- Streamable HTTP: 未対応
- client別E2E確認: 未整備です。stdio MCP clientから `initialize`、`tools/list`、`resources/list`、`prompts/list` を呼べることを前提にしています。

## Credit accounting

MCP側ではcredit消費を保守的に事前会計します。cache hitは `credits_used=0` です。

| tool | MCP側のcredit扱い |
| --- | --- |
| `list_news` | API callごとに1 credit |
| `search_documents` | API callごとに1 credit |
| `search_news` | API callごとに1 credit |
| `get_document_content` | API callごとに最大8 creditsとして会計 |
| `get_document_page_image` | cache missごとに1 credit |
| `get_document_original` | cache missごとに8 credits |

`get_document_content` はMomonga Search API側の実消費が本文量で 2 / 4 / 8 credits に変わる場合でも、このMCPでは最大値の8 creditsとしてsession limitを判定します。APIレスポンスまたはヘッダーから実消費creditを安定して取得できるようになった場合は、実値会計へ変更する予定です。

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
rm -rf ~/.cache/momonga-search-mcp
```

workspace内へ向けた場合は、指定した `MOMONGA_MCP_CACHE_DIR` を削除してください。

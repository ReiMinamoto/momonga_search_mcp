# Momonga Search MCP

Momonga Search APIをMCP経由で使うためのstdioサーバーです。

## 機能

このMCPは、Momonga Search APIを単純にproxyするのではなく、LLM/Agentが企業公表資料・ニュースを安全に調査するためのworkflow基盤として提供します。

- transportはstdioです。
- documents系toolとnews系toolは分けて提供します。
- documents/newsの統合検索や統合ランキングは行いません。
- Server Instructions、Skill風Resources、Prompts、Helper Toolsで調査workflowを案内します。
- `skill://index.json` と用途別Skill Resourceを提供します。
- 本文、page image、original fileの取得はcredit、文字数、section数、件数の上限で制御します。
- 画像・元ファイル・大量取得は明示フラグを要求します。
- 実質不変な取得済みresourceだけをローカルに保存し、再取得時はcacheを優先します。
- ローカル保存された情報は `momonga://...` URIで参照できるようにします。

主なtool:

| 分類 | tool |
| --- | --- |
| issuer/document | `search_issuers`, `list_documents`, `get_document`, `search_documents`, `get_document_toc`, `get_document_content` |
| news | `list_news`, `search_news` |
| file | `list_document_page_images`, `get_document_page_image`, `list_document_originals`, `get_document_original` |
| skill helper | `find_skill`, `get_skill` |

Skill Resource:

| URI | 用途 |
| --- | --- |
| `skill://index.json` | 利用可能なSkillの一覧と使い分け |
| `skill://skills/document-research.md` | 文書調査のworkflow |
| `skill://skills/document-content-retrieval.md` | 本文取得のworkflow |
| `skill://skills/news-research.md` | ニュース調査のworkflow |
| `skill://skills/file-download.md` | page image / original file取得のworkflow |
| `skill://skills/evidence-answering.md` | 根拠付き回答のworkflow |

Prompts:

| prompt | 用途 |
| --- | --- |
| `use_document_research` | 文書調査を開始する |
| `use_news_research` | ニュース調査を開始する |
| `use_evidence_answering` | 根拠付き回答を作成する |

## 設定

設定は環境変数で指定します。コピーして使うための雛形は `.env.example` を参照してください。

| 環境変数 | 必須 | デフォルト | 意味 |
| --- | --- | --- | --- |
| `MOMONGA_SEARCH_API_KEY` | はい | なし | Momonga Search APIキーです。未設定の場合、サーバーは起動しません。 |
| `MOMONGA_BASE_URL` | いいえ | `https://api.momongasearch.com/v1` | Momonga Search APIのbase URLです。ステージング環境や専用エンドポイントを使う場合に上書きします。 |
| `MOMONGA_MCP_CACHE_DIR` | いいえ | `~/.cache/momonga-search-mcp` | MCP側のキャッシュ保存先ディレクトリです。 |
| `MOMONGA_MCP_API_TIMEOUT_SECONDS` | いいえ | `30` | Momonga Search APIへのHTTPリクエストtimeout秒数です。 |
| `MOMONGA_MCP_LOG_LEVEL` | いいえ | `INFO` | ログレベルです。`DEBUG`、`INFO`、`WARNING`、`ERROR` などを指定できます。ログはstderrに出力します。 |
| `MOMONGA_MCP_MAX_CREDITS_PER_TOOL_CALL` | いいえ | `8` | tool呼び出し1回あたりの最大credit消費量です。 |
| `MOMONGA_MCP_MAX_CREDITS_PER_SESSION` | いいえ | `30` | サーバーセッション単位の最大credit消費量です。 |
| `MOMONGA_MCP_MAX_SECTIONS_PER_CONTENT_CALL` | いいえ | `3` | 本文取得1回あたりの最大section数です。 |
| `MOMONGA_MCP_MAX_CHARACTERS_PER_CONTENT_CALL` | いいえ | `30000` | 本文取得1回あたりの最大文字数です。 |
| `MOMONGA_MCP_MAX_PAGE_IMAGES_PER_CALL` | いいえ | `3` | page image取得1回あたりの最大件数です。 |
| `MOMONGA_MCP_MAX_ORIGINAL_FILES_PER_CALL` | いいえ | `1` | original file取得1回あたりの最大件数です。 |

最小構成:

```sh
export MOMONGA_SEARCH_API_KEY=ms_live_xxx
```

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

## ローカル実行

```sh
PYTHONPATH=src python -m momonga_search_mcp.server
```

## MCPクライアント設定例

```json
{
  "mcpServers": {
    "momonga-search": {
      "command": "uv",
      "args": ["run", "momonga-search-mcp"],
      "env": {
        "MOMONGA_SEARCH_API_KEY": "ms_live_xxx",
        "MOMONGA_BASE_URL": "https://api.momongasearch.com/v1"
      }
    }
  }
}
```

uvがデフォルトのcache directoryに書き込めない環境では、次のようにworkspace内へcacheを向けます。

```sh
export UV_CACHE_DIR=.uv-cache
```

## チェック

```sh
UV_CACHE_DIR=.uv-cache uv run ruff check .
UV_CACHE_DIR=.uv-cache uv run ruff format --check .
PYTHONPATH=src python -m unittest discover -s tests
```

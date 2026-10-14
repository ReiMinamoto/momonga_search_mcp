# Momonga Search MCP

Momonga Search MCP は、企業公表資料・経済ニュースを LLM/Agent が安全に検索・取得・根拠提示するための MCP server です。汎用Web検索MCPではありません。

> 初心者向けのセットアップ記事を用意しています。`uv` のインストールから Claude Desktop / Claude Code / Codex への登録まで手順を追って解説しているので、まずはこちらを参照してください: [【初心者向け】Momonga Search MCP を Claude / Codex で使えるようにしよう！](https://zenn.dev/ray000/articles/momonga-search-mcp-setup)

## 機能

このMCPは、Momonga Search APIを単純にproxyするのではなく、LLM/Agentが企業公表資料・ニュースを安全に調査するための検索・取得基盤として提供します。

- transportはstdioです。
- documents系toolとnews系toolは分けて提供します。
- documents/newsの統合検索や統合ランキングは行いません。
- 本文、page image、original fileの取得は文字数、section数、件数の上限で制御します。
- `get_document_content` はsectionをcacheし、小さいsectionだけinline返却します。大きいsectionはmanifestを返し、`search_section_contents` / `get_section_window` で必要箇所だけ読む導線にします。
- `momonga://...` resource URIは根拠所在IDとして扱います。`resources/read` はcache済みsection本文の全文を返しません。
- subagent実行が使える場合も、起動・分配・統合はhost/client側の責務です。MCP serverはbounded retrievalと根拠ID提供に集中します。
- 画像・元ファイル・大量取得は明示フラグを要求します。
- 実質不変な取得済みresourceだけをローカルに保存し、再取得時はcacheを優先します。
- ローカル保存された情報は `momonga://...` URIで参照できるようにします。

## MCP対応範囲

- 対応 protocol version: `2025-11-25`
- transport: stdio
- tool response: full payloadは `content[].text` にJSON textとして返します。Claude Desktop互換性のため `structuredContent` は返しません。
- tool metadata: `tools/list` で `title` と `annotations` を返します。Claude Desktop互換性のため `outputSchema` は返しません。

## 金融・開示データ利用上の注意

このMCPは、企業開示・ニュース・関連資料の一次情報や根拠候補を取得するための検索・取得基盤です。投資助言、売買推奨、将来収益の保証、法務・会計判断は提供しません。取得結果を使った最終判断、一次情報との照合、投資判断は利用者側で行ってください。

このMCPのtool responseでは、根拠、時刻、出典を以下の意味で扱います。

- `published_at` がある場合は文書の公表時刻として扱います。`timeline_at` は一覧・検索・時系列整理のための正規化時刻であり、公表時刻として扱わないでください。
- `content_status=ready` は本文取得可能、`pending_release` は公開待ち、`external_only` はAPI本文ではなく外部参照先で確認する文書です。
- `reference_url` は根拠確認用の参照URLであり、元ファイルの直接download URLとは限りません。元ファイルが必要な場合は `list_document_originals` と `get_document_original` を使ってください。
- news系toolは見出し `title`、1〜3文の本文 `body`、根拠の `references[]` を返します。`body` は根拠資料をもとに書かれたもので、報道記事の本文ではありません。
- documents系toolとnews系toolは別の検索対象です。統合ランキングは行わず、必要な場合は最終回答で根拠種別を分けて扱ってください。
- coverageには制約があります。v1の `ir_material` はメタデータ・外部リンクのみで、本文検索・本文取得・元ファイル・画像の配信はありません。

主なtool:

| 分類 | tool |
| --- | --- |
| main | `search_issuers`, `list_documents`, `get_document_metadata`, `get_document_toc`, `list_document_page_images`, `list_document_originals`, `list_news`, `get_document_content`, `search_section_contents`, `get_section_window`, `search_documents`, `search_news` |
| file download | `get_document_page_image`, `get_document_original` |

| helper | `diagnose_setup`, `list_cached_resources` |

詳細:

- `docs/tool_responses.md`: MCP tool / API endpoint 対応表、tool response field
- `docs/runtime.md`: MCP protocol version、固定ガードレール、cache方針

## 設定

設定は環境変数で指定します。コピーして使うための雛形は `.env.example` を参照してください。

| 環境変数 | 必須 | デフォルト | 意味 |
| --- | --- | --- | --- |
| `MOMONGA_SEARCH_API_KEY` | API tool利用時 | なし | Momonga Search APIキーです。未設定でもMCP serverは起動しますが、`search_issuers` などのAPI toolは `server_setup_error` を返します。`diagnose_setup` で設定状態を確認できます。 |
| `MOMONGA_BASE_URL` | いいえ | `https://api.momongasearch.com/v1` | Momonga Search APIのbase URLです。ステージング環境や専用エンドポイントを使う場合に上書きします。 |
| `MOMONGA_SEARCH_MCP_CACHE_DIR` | いいえ | OS標準のuser cache directory | MCP側の必須キャッシュ保存先ディレクトリです。 |
| `MOMONGA_SEARCH_MCP_CACHE_MAX_GB` | いいえ | `1` | cache書き込み後に古いresourceを自動pruneする容量上限です。単位はGBです。 |
| `MOMONGA_MCP_LOG_LEVEL` | いいえ | `INFO` | ログレベルです。`DEBUG`、`INFO`、`WARNING`、`ERROR` などを指定できます。ログはstderrに出力します。 |

最小構成:

```sh
export MOMONGA_SEARCH_API_KEY=ms_live_xxx
```

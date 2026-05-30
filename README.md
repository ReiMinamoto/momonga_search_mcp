# Momonga Search MCP

Momonga Search MCP は、企業公表資料・経済ニュースを LLM/Agent が安全に検索・取得・根拠提示するための workflow MCP server です。汎用Web検索MCPではありません。

## 機能

このMCPは、Momonga Search APIを単純にproxyするのではなく、LLM/Agentが企業公表資料・ニュースを安全に調査するためのworkflow基盤として提供します。

- transportはstdioです。
- documents系toolとnews系toolは分けて提供します。
- documents/newsの統合検索や統合ランキングは行いません。
- Server Instructions、Skill風Resources、Prompts、Helper Toolsで調査workflowを案内します。
- `skill://index.json` と用途別Skill Resourceを提供します。
- 本文、page image、original fileの取得は文字数、section数、件数の上限で制御します。
- `get_document_content` はsectionをcacheし、小さいsectionだけinline返却します。大きいsectionはmanifestを返し、`search_section_contents` / `get_section_window` で必要箇所だけ読む導線にします。
- `momonga://...` resource URIは根拠所在IDとして扱います。`resources/read` はcache済みsection本文の全文を返しません。
- synthesisや比較では、retrieved excerpt/windowを非永続の `evidence_notes` に圧縮してから回答します。`evidence_notes` はMCP resourceではなくworkflow上の中間生成物です。
- subagent実行が使える場合も、起動・分配・統合はhost/client側の責務です。MCP serverはbounded retrievalと根拠ID提供に集中します。
- 画像・元ファイル・大量取得は明示フラグを要求します。
- 実質不変な取得済みresourceだけをローカルに保存し、再取得時はcacheを優先します。
- ローカル保存された情報は `momonga://...` URIで参照できるようにします。

## MCP対応範囲

- 対応 protocol version: `2025-11-25`
- transport: stdio
- tool response: full payloadは `structuredContent` にJSON objectとして返し、`content[].text` は短いsummaryだけを返します。
- tool metadata: `tools/list` で `title`、`annotations`、主要fieldの `outputSchema` を返します。`outputSchema` はMCP tool responseのトップレベル契約を示すもので、API由来のネストした構造は後方互換性のため緩く扱います。

## 金融・開示データ利用上の注意

このMCPは、企業開示・ニュース・関連資料の一次情報や根拠候補を取得するためのworkflow基盤です。投資助言、売買推奨、将来収益の保証、法務・会計判断は提供しません。取得結果を使った最終判断、一次情報との照合、投資判断は利用者側で行ってください。

このMCPのtool responseでは、根拠、時刻、出典を以下の意味で扱います。

- `published_at` がある場合は文書の公表時刻として扱います。`timeline_at` は一覧・検索・時系列整理のための正規化時刻であり、公表時刻として扱わないでください。
- `content_status=ready` は本文取得可能、`pending_release` は公開待ち、`external_only` はAPI本文ではなく外部参照先で確認する文書です。
- `reference_url` は根拠確認用の参照URLであり、元ファイルの直接download URLとは限りません。元ファイルが必要な場合は `list_document_originals` と `get_document_original` を使ってください。
- news系toolは記事全文ではなく、正規化された `statement` と `references[]` を返します。ニュース本文そのものとして引用しないでください。
- documents系toolとnews系toolは別の検索対象です。統合ランキングは行わず、必要な場合は最終回答で根拠種別を分けて扱ってください。
- coverageには制約があります。例えばv1では `ir_material` がmetadata一覧に出ても、本文検索対象外の場合があります。

主なtool:

| 分類 | tool |
| --- | --- |
| main | `search_issuers`, `list_documents`, `get_document_metadata`, `get_document_toc`, `list_document_page_images`, `list_document_originals`, `list_news`, `get_document_content`, `search_section_contents`, `get_section_window`, `search_documents`, `search_news` |
| file download | `get_document_page_image`, `get_document_original` |
| cache/skill helper | `list_skills`, `get_skill`, `list_cached_resources` |

Skill Resource:

| URI | 用途 |
| --- | --- |
| `skill://index.json` | 利用可能なSkillの一覧と使い分け |
| `skill://skills/document-research.md` | 文書調査のworkflow |
| `skill://skills/document-content-retrieval.md` | 本文取得のworkflow |
| `skill://skills/news-research.md` | ニュース調査のworkflow |
| `skill://skills/file-download.md` | page image / original file取得のworkflow |
| `skill://skills/evidence-compression.md` | 長文・複数根拠を短い `evidence_notes` に圧縮するworkflow |
| `skill://skills/evidence-answering.md` | 根拠付き回答のworkflow |

Prompts:

| prompt | 用途 |
| --- | --- |
| `use_document_research` | 文書調査を開始する |
| `use_news_research` | ニュース調査を開始する |
| `use_evidence_answering` | 根拠付き回答を作成する |

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

## インストール

`uv` を使う前提のローカル実行手順です。

`uv` が未インストールの場合:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```sh
git clone https://github.com/ReiMinamoto/momonga_search_mcp.git
cd momonga_search_mcp
uv sync --dev
cp .env.example .env
```

https://momongasearch.com/ でMomonga Search APIキーを発行し、`.env` の `MOMONGA_SEARCH_API_KEY` を実際のAPIキーに置き換えます。APIキーはrepositoryへcommitしないでください。

動作確認:

```sh
set -a
. ./.env
set +a
PYTHONPATH=src python -m momonga_search_mcp.server
```

上のコマンドはstdio serverとして待機します。手動確認を終える場合は `Ctrl-C` で停止してください。

## MCPクライアント登録

### Claude Code

Claude Codeでは、project共有設定としてrepository rootの `.mcp.json` に登録できます。

```json
{
  "mcpServers": {
    "momonga-search": {
      "command": "uv",
      "args": [
        "--directory",
        "${CLAUDE_PROJECT_DIR:-.}",
        "run",
        "momonga-search-mcp"
      ]
    }
  }
}
```

CLIで登録する場合:

```sh
claude mcp add --scope project --transport stdio momonga-search -- \
  uv --directory /absolute/path/to/momonga-search-mcp run momonga-search-mcp
```

登録後、Claude Code内で `/mcp` を実行して接続状態を確認します。project scopeの `.mcp.json` は共有設定としてversion管理できますが、Claude Codeは利用前に承認を求めます。

### Codex

Codexでは `~/.codex/config.toml`、またはtrusted projectの `.codex/config.toml` に登録します。

```toml
[mcp_servers.momonga-search]
command = "uv"
args = ["run", "momonga-search-mcp"]
cwd = "/absolute/path/to/momonga-search-mcp"
```

CLIで登録する場合:

```sh
codex mcp add momonga-search -- uv --directory /absolute/path/to/momonga-search-mcp run momonga-search-mcp
```

登録後、Codex TUI内で `/mcp` を実行して接続状態を確認します。Codex CLIとIDE extensionは同じ設定layerを参照します。

server起動時に repository directory の `.env` を読み込むため、上記のようにrepository directoryで起動できる場合は、MCP client設定へAPIキーを書く必要はありません。

`cwd` を指定できないMCP clientでは、`command` に絶対パスのwrapper scriptを指定するか、client側の起動directoryをこのrepositoryに合わせてください。`.env` を使わない運用では、client側の `env` で `MOMONGA_SEARCH_API_KEY` を渡してください。

## ローカル実行

```sh
PYTHONPATH=src python -m momonga_search_mcp.server
```

uvがデフォルトのcache directoryに書き込めない環境では、次のようにworkspace内へcacheを向けます。

```sh
export UV_CACHE_DIR=.uv-cache
```

## チェック

```sh
UV_CACHE_DIR=.uv-cache uv run ruff check .
UV_CACHE_DIR=.uv-cache uv run ruff format --check .
UV_CACHE_DIR=.uv-cache uv run pytest
```

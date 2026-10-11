# Momonga Search MCP

Momonga Search MCP は、企業公表資料・経済ニュースを LLM/Agent が安全に検索・取得・根拠提示するための workflow MCP server です。汎用Web検索MCPではありません。

> 初心者向けのセットアップ記事を用意しています。`uv` のインストールから Claude Desktop / Claude Code / Codex への登録まで手順を追って解説しているので、まずはこちらを参照してください: [【初心者向け】Momonga Search MCP を Claude / Codex で使えるようにしよう！](https://zenn.dev/ray000/articles/momonga-search-mcp-setup)

## 機能

このMCPは、Momonga Search APIを単純にproxyするのではなく、LLM/Agentが企業公表資料・ニュースを安全に調査するためのworkflow基盤として提供します。

- transportは従来のstdioと、社内共用サーバー向けStreamable HTTPです。
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
- transport: stdio / Streamable HTTP（JSON応答、GETによるSSEは405）
- tool response: full payloadは `content[].text` にJSON textとして返します。Claude Desktop互換性のため `structuredContent` は返しません。
- tool metadata: `tools/list` で `title` と `annotations` を返します。Claude Desktop互換性のため `outputSchema` は返しません。

## 金融・開示データ利用上の注意

このMCPは、企業開示・ニュース・関連資料の一次情報や根拠候補を取得するためのworkflow基盤です。投資助言、売買推奨、将来収益の保証、法務・会計判断は提供しません。取得結果を使った最終判断、一次情報との照合、投資判断は利用者側で行ってください。

このMCPのtool responseでは、根拠、時刻、出典を以下の意味で扱います。

- `published_at` がある場合は文書の公表時刻として扱います。`timeline_at` は一覧・検索・時系列整理のための正規化時刻であり、公表時刻として扱わないでください。
- `content_status=ready` は本文取得可能、`pending_release` は公開待ち、`external_only` はAPI本文ではなく外部参照先で確認する文書です。
- `reference_url` は根拠確認用の参照URLであり、元ファイルの直接download URLとは限りません。元ファイルが必要な場合は `list_document_originals` と `get_document_original` を使ってください。
- news系toolは見出し `title`、1〜3文の本文 `body`、根拠の `references[]` を返します。`body` は根拠資料をもとに書かれたもので、報道記事の本文ではありません。
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

## 端末ごと（stdio）

各端末にインストールし、その端末の環境変数にMomonga APIキーを設定します。

```sh
uv tool install .
momonga-search-mcp --transport stdio
```

MCPホストには `momonga-search-mcp` を起動コマンドとして登録し、必要な環境変数を渡します。引数を省略した起動も従来どおりstdioです。標準入力・標準出力はMCPのJSON-RPC専用、ログは標準エラーです。

## 社内共用（HTTP）

社内VM 1台で起動し、複数の利用者・エージェントから `https://<社内ホスト名>/mcp` に接続します。**Momonga APIキーはサーバーの環境変数だけに置き、端末には配りません。** 各端末には独立したMCP接続用Bearerトークンを発行します。同一契約で利用を許諾された利用者向けで、複数法人のキャッシュ分離は提供しません。

### VMと利用者トークンの準備

VMでリポジトリをチェックアウトし、サーバーだけで使う `.env` に次を設定します。実際のキー・トークンをGitに保存しないでください。

```dotenv
MOMONGA_SEARCH_API_KEY=<server-only Momonga API key>
MOMONGA_MCP_HOSTNAME=mcp.example.internal
```

社内DNSでこの名前をVMへ向け、443への接続を許諾された社内利用者に限定します。Docker Compose配布物はTLS用CaddyとMCPを起動し、MCPの8000番を外部に公開しません。

```sh
docker compose build mcp
docker compose run --rm token-admin --store /run/momonga-tokens/client-tokens.json issue --label department-a
docker compose up -d mcp tls
```

`issue` のJSON出力に含まれる `token` はその1回だけ表示します。部署・利用者ごとに同じ発行コマンドを繰り返し、安全な経路で対象利用者へ渡します。保存ファイルにはトークンのSHA-256とラベル等だけを保存します。管理用・MCP用コンテナは同じUIDで、MCP側にはトークン保存ディレクトリを読み取り専用でマウントします。

一覧・個別失効:

```sh
docker compose run --rm token-admin --store /run/momonga-tokens/client-tokens.json list
docker compose run --rm token-admin --store /run/momonga-tokens/client-tokens.json revoke --token-id <id>
```

一覧には秘密値やハッシュを返しません。失効は新規・既存セッションの次のリクエストから反映され、他の利用者のトークンは有効です。処理中のリクエストを中断する機能はありません。トークン用volumeを維持して運用してください。

### TLSとクライアント設定

配布物のCaddyは社内向けCAでTLS証明書を発行します。公開CA証明書を取り出し、利用する端末・MCPクライアントの信頼ストアへ登録します。社内の既存TLS基盤を使う場合はCaddyfileの証明書設定をそれに合わせます。

```sh
docker compose cp tls:/data/caddy/pki/authorities/local/root.crt ./momonga-mcp-root.crt
```

Streamable HTTPと固定Bearerヘッダーに対応したMCPクライアントへ、URL `https://mcp.example.internal/mcp` とヘッダー `Authorization: Bearer <その利用者のMCPトークン>` を設定します。Momonga APIキーは指定しません。OAuthの自動登録・認可フローは提供しません。

HTTPリクエストは `Accept: application/json, text/event-stream` とJSONを使います。初期化応答の `MCP-Session-Id` を後続リクエストに付け、`MCP-Protocol-Version: 2025-11-25` を送ります。通知は202・空本文、JSON-RPC要求にはJSONで応答し、GETでのSSEは405、DELETEは自分のセッションを終了します。セッションは利用者トークンに紐づき、1時間の無通信で失効します。上限は128セッションです。

### キャッシュ・制限・運用

- cache volumeを全セッションで共用。既存の `limit 25` / `top_k 25` / 通常section3,000字超はmanifestというガードレールは共通です（full document synthetic sectionは既存どおり10,000字）。tool定義、`content[].text` のJSON形式、Resources、Promptsはstdioと同じです。
- 現在のキャッシュの書込みとpruneの競合を防ぐため、1 workerでtool処理を直列化します。複数クライアントは独立したセッションで接続できますが、遅いAPI処理は待ち時間になります。高負荷運用前に同時利用数で負荷確認してください。
- `file_path` はサーバー内のパスです。端末のローカルパスではありません。画像・元ファイルもサーバーのキャッシュに保存され、追加のダウンロード配信APIは提供しません。
- Originヘッダーがある要求は、`MOMONGA_MCP_ALLOWED_ORIGINS` に完全一致する場合のみ許可します（既定は空）。Originを送らないネイティブクライアントもBearer認証が必要です。Hostも `MOMONGA_MCP_ALLOWED_HOSTS` で制限し、Composeでは社内ホスト名に固定します。
- アクセスログは無効で、キー・Bearer・要求本文をログに出しません。トークン保存ファイルが読めない場合は503で拒否します。

VM以外で確認する場合は、サーバーに `MOMONGA_MCP_TOKEN_FILE`（絶対パス）、必要なら `MOMONGA_MCP_ALLOWED_HOSTS`（カンマ区切り）を設定し、`momonga-search-mcp --transport streamable-http --host 127.0.0.1 --port 8000` で起動します。トークン管理CLIはLinux/macOS向けです。HTTP transportの根拠: [MCP 2025-11-25 Transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)。

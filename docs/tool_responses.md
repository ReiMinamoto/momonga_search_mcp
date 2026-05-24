# MCP Tool Responses

この文書は、Momonga Search MCP の tool が返す JSON payload の仕様をまとめます。

MCP は Momonga Search API のレスポンスを常にそのまま返すわけではありません。LLM / Agent のコンテキスト消費を抑えるため、tool response は以下の方針で最小化します。

- 後続 tool 呼び出しに必要な ID は残す
- 次の行動判断に必要な短い文脈は残す
- 根拠や取得対象へ戻るための field は残す
- モデルの判断に通常不要な API metadata は落とす

すべての full tool response は、MCP `structuredContent` に JSON object として入ります。`content[].text` はコンテキスト圧迫を避けるため短いsummaryだけを返します。`tools/list` は主要fieldの `outputSchema` を返します。

`outputSchema` は Momonga Search API のレスポンススキーマではなく、MCP tool response のスキーマです。このMCPでは、tool response のトップレベル主要fieldを契約として示します。一方で、`results[]`、`toc[]`、`content_sections[]`、`references[]` など一部のネストした構造は Momonga Search API の構造を採用しているため、後方互換なfield追加に備えて緩く扱い、未知fieldを許容します。厳密な型生成やバリデーションよりも、LLM / Agent とMCPクライアントが主要な返り値を把握できる自己記述性を優先します。

tool input parameter は、原則として対応エンドポイントの request parameter と同じ名前・意味にします。MCP 側だけで使う parameter や、API parameter 名と異なるものがある場合は各 tool の「パラメータ差分」に明記します。

## MCP tool / API endpoint 対応表

MCPは、0-credit APIで候補・取得可否・取得単位を確認し、必要な本文・画像・元ファイルだけcredit APIで取得する前提でtoolを分けています。

| MCP tool | API endpoint | API credits | MCP cache | 主な注意 |
| --- | --- | --- | --- | --- |
| `search_issuers` | `GET /v1/issuers/search` | 0 | no | issuer特定に使います。 |
| `list_documents` | `GET /v1/documents` | 0 | no | `security_codes` なしの場合は `timeline_since` が必須です。 |
| `get_document_metadata` | `GET /v1/documents/{document_id}` | 0 | no | `content_status` や取得可否の確認に使います。 |
| `get_document_toc` | `GET /v1/documents/{document_id}/toc` | 0 | yes | `content_status=ready` の文書で、section IDと取得単位を確認します。 |
| `list_document_page_images` | `GET /v1/documents/{document_id}/page-images` | 0 | no | page image取得前に利用可能pageを確認します。 |
| `list_document_originals` | `GET /v1/documents/{document_id}/originals` | 0 | no | original file取得前に `original_id` を確認します。 |
| `list_news` | `GET /v1/news` | 1/API call | no | newsは記事全文ではなく `statement` + `references[]` です。 |
| `get_document_content` | `GET /v1/documents/{document_id}/content` | 2/4/8/API call | yes | API実消費は本文量で変わります。MCP側は `x-quota-compute-remaining` 差分から実値を推定し、取れない場合は最大8 creditsとして保守的に会計します。 |
| `search_documents` | `POST /v1/search/documents` | 1/API call | no | 検索結果は候補です。必要なsection本文は `get_document_content` で取得します。 |
| `search_news` | `POST /v1/search/news` | 1/API call | no | documents検索とは統合rankingしません。 |
| `get_document_page_image` | `GET /v1/documents/{document_id}/pages/{page_number}/image` | 1/page | yes | `list_document_page_images` で確認後、必要pageだけ取得します。 |
| `get_document_original` | `GET /v1/documents/{document_id}/originals/{original_id}` | 8/file | yes | `list_document_originals` で確認後、必要fileだけ取得します。 |
| `list_cached_resources` | local cache index | 0 | read | cache済みresource URIを確認します。 |

## 金融・開示データの扱い

このMCPは投資助言・売買判断を提供しません。tool response は一次情報や根拠候補を扱うためのものであり、最終判断や公式情報との照合は利用者側で行います。

- `timeline_at` は時系列整理用の正規化時刻です。公式公表時刻として扱わないでください。
- `content_status=ready` は本文取得可能、`pending_release` は公開待ち、`external_only` はAPI本文ではなく外部参照先で確認する文書です。
- `reference_url` は元ファイルの直接download URLではありません。元ファイル取得には `list_document_originals` / `get_document_original` を使います。
- news系toolは記事全文ではなく、正規化された `statement` と `references[]` を返します。
- coverageには制約があります。例えばv1では `ir_material` がmetadata一覧に出ても、本文検索対象外の場合があります。

## `search_issuers`

会社名または証券コードから issuer を検索します。

文書・ニュース系 tool を呼ぶ前に、会社名から `security_code` を特定するために使います。

対応エンドポイント: `GET /v1/issuers/search`

### 返り値

```json
{
  "ok": true,
  "results": [
    {
      "security_code": "8058",
      "edinet_code": "E02529",
      "name": "三菱商事株式会社",
      "market": "プライム（内国株式）",
      "sector": "卸売業"
    }
  ]
}
```

### 残す field

| Field | 理由 |
| --- | --- |
| `security_code` | 文書・ニュース検索の主要 filter として使う。 |
| `edinet_code` | EDINET filing の issuer 確認に使える。 |
| `name` | issuer の人間向け表示名。 |
| `market` | 同名・類似名 issuer の識別に使える。 |
| `sector` | 同名・類似名 issuer の識別に使える。 |

### 落とす field

なし。issuer response は小さく、返る field は issuer の識別に使えるため、そのまま残します。

## `list_documents`

文書候補を一覧し、後続の metadata / toc / content 取得へ進むために使います。

対応エンドポイント: `GET /v1/documents`

### 返り値

```json
{
  "ok": true,
  "results": [
    {
      "document_id": "doc_123",
      "document_family": "edinet_filing",
      "title": "Annual Securities Report",
      "document_type": "yuho",
      "issuers": [{"security_code": "8058", "name": "三菱商事株式会社"}],
      "timeline_at": "2026-05-01T00:00:00Z",
      "content_status": "ready",
      "reference_url": "https://example.com/report.pdf"
    }
  ],
  "next_cursor": "cursor_1"
}
```

### 残す field

| Field | 理由 |
| --- | --- |
| `document_id` | 後続 tool 呼び出しの対象 ID。 |
| `document_family` | EDINET filing / timely disclosure / IR material の判別。 |
| `title` | 候補文書の識別。 |
| `document_type` | 有報・短信・その他の判別。 |
| `issuers` | issuer filter なし・複数社検索時の文書帰属確認。 |
| `timeline_at` | 時系列で候補を選ぶため。 |
| `content_status` | `get_document_toc` / `get_document_content` に進めるか判断するため。 |
| `reference_url` | `external_only` など本文取得できない文書で外部根拠へ進むため。 |
| `next_cursor` | 続きの一覧取得に必要。 |

### 落とす field

`tags`, `published_at`, `timeline_precision`, `timeline_basis`, `first_observed_at`, `character_count`, `content_available`, `image_available`, `page_count`, `page_image_count`

## `get_document_metadata`

特定文書の識別情報を確認します。

対応エンドポイント: `GET /v1/documents/{document_id}`

### 返り値

```json
{
  "ok": true,
  "document_id": "doc_123",
  "document_family": "edinet_filing",
  "title": "Annual Securities Report",
  "document_type": "yuho",
  "issuers": [{"security_code": "8058", "name": "三菱商事株式会社"}],
  "timeline_at": "2026-05-01T00:00:00Z",
  "content_status": "ready",
  "reference_url": "https://example.com/report.pdf"
}
```

### 残す field

`list_documents` と同じです。文書本文取得に進む判断へ直接使う field だけ残します。

### 落とす field

`list_documents` と同じです。

## `get_document_toc`

文書本文を取得するための section selector を取得します。

返り値の `toc[].section_id` を `get_document_content` の `section_ids` に渡します。

MCP は TOC payload を `document_id` 単位で cache します。`cache_hit` は、この tool call が API を呼ばずローカル cache から返したかどうかを表します。

対応エンドポイント: `GET /v1/documents/{document_id}/toc`

### 返り値

```json
{
  "ok": true,
  "document_id": "doc_123",
  "toc": [
    {
      "section_id": "sec_1",
      "section_title": "Risk Factors",
      "heading_path": ["Business", "Risk Factors"],
      "character_count": 1200,
      "page_number": 5
    }
  ],
  "resource_uri": "momonga://documents/doc_123/toc",
  "cache_hit": false
}
```

### 残す field

| Field | 理由 |
| --- | --- |
| `document_id` | 後続 tool 呼び出しの対象文書を示す。 |
| `toc` | 取得する section を選ぶための目次。 |
| `toc[].section_id` | `get_document_content.section_ids` に渡す必須 selector。 |
| `toc[].section_title` | section 選択用の短い表示名。 |
| `toc[].heading_path` | section の階層文脈。 |
| `toc[].character_count` | 大きすぎる section の取得を避けるための目安。 |
| `toc[].page_number` | 図表・画像確認が必要な場合に page image へ進むための目安。 |
| `resource_uri` | cache 済み TOC を指すローカル resource ID。 |
| `cache_hit` | API call を skip したかどうか。 |

### 落とす field

API response には document metadata も含まれますが、`get_document_toc` は section selector 取得用の tool なので、MCP response では落とします。

`title`, `document_family`, `document_type`, `issuers`, `tags`, `published_at`, `timeline_at`, `timeline_precision`, `timeline_basis`, `first_observed_at`, `content_available`, `content_status`, `image_available`, `page_count`, `page_image_count`, `reference_url`

## `list_document_page_images`

画像取得可能な page を確認します。

対応エンドポイント: `GET /v1/documents/{document_id}/page-images`

### 返り値

```json
{
  "ok": true,
  "document_id": "doc_123",
  "page_count": 17,
  "page_image_count": 3,
  "page_images": [1, 2, 5]
}
```

### 残す field

| Field | 理由 |
| --- | --- |
| `document_id` | 対象文書の確認。 |
| `page_count` | 文書全体のページ数。 |
| `page_image_count` | 画像取得可能なページ数。 |
| `page_images[]` | page image 取得に渡すページ番号。 |

### 落とす field

`image_role`, `source_route`, `width`, `height` などの詳細 metadata。

## `list_document_originals`

取得可能な元ファイルを確認します。

対応エンドポイント: `GET /v1/documents/{document_id}/originals`

### 返り値

```json
{
  "ok": true,
  "document_id": "doc_123",
  "originals": [
    {
      "original_id": "pdf",
      "filename": "report.pdf",
      "media_type": "application/pdf"
    }
  ]
}
```

### 残す field

| Field | 理由 |
| --- | --- |
| `document_id` | 対象文書の確認。 |
| `originals[].original_id` | 元ファイル取得に渡す ID。 |
| `originals[].filename` | 人間向け識別。 |
| `originals[].media_type` | PDF / ZIP などの形式判断。 |

### 落とす field

`content_available`, `content_status`, `original_available`, `kind`, `role`, `size_bytes`, `sha256`, `credit_cost` などの補助 metadata。

## `get_document_original`

元ファイルを1件取得し、ローカル cache に保存します。

この tool は file download を伴うため、`allow_file_download=true` が必須です。cache hit の場合は API の実体取得を行わず、credit も消費しません。

実体レスポンスの `Content-Disposition` から `filename` が取れない場合、または `Content-Type` が `application/octet-stream` の場合だけ、`GET /v1/documents/{document_id}/originals` を確認して `filename` / `media_type` を補完します。

対応エンドポイント:

- 実体取得: `GET /v1/documents/{document_id}/originals/{original_id}`
- fallback manifest 確認: `GET /v1/documents/{document_id}/originals`

### パラメータ差分

| Tool parameter | API parameter | 理由 |
| --- | --- | --- |
| `document_id` | `document_id` | 対象文書 ID。 |
| `original_id` | `original_id` | `/originals` に含まれる元ファイル ID。 |
| `allow_file_download` | なし | ローカルファイル保存を明示許可する MCP 専用 parameter。`true` 以外は拒否します。 |

### 返り値

```json
{
  "ok": true,
  "document_id": "doc_123",
  "original_id": "pdf",
  "file_path": "/home/user/.cache/momonga-search-mcp/cache/documents/doc_123/originals/pdf/report.pdf",
  "resource_uri": "momonga://documents/doc_123/originals/pdf",
  "media_type": "application/pdf",
  "filename": "report.pdf",
  "cached": false
}
```

### 残す field

| Field | 理由 |
| --- | --- |
| `document_id` | 対象文書の確認。 |
| `original_id` | 取得した元ファイルの確認。 |
| `file_path` | ローカルに保存した実体ファイルの場所。 |
| `resource_uri` | cache 済み元ファイルを指すローカル resource ID。 |
| `media_type` | PDF / ZIP などファイル種別の判断。実体レスポンスヘッダを優先し、不明な場合は `/originals` manifest を fallback に使います。 |
| `filename` | 保存ファイル名。実体レスポンスヘッダを優先し、不明な場合は `/originals` manifest を fallback に使います。 |
| `cached` | 実体取得 API を呼ばず cache から返したかどうか。 |

### 落とす field

実体ファイルの bytes は MCP response に載せません。`list_document_originals` で落としている `kind`, `role`, `size_bytes`, `sha256` などの manifest metadata も返しません。

## `get_document_page_image`

ページ画像を1件取得し、ローカル cache に保存します。

この tool は file download を伴うため、`allow_file_download=true` が必須です。cache hit の場合は API の実体取得を行わず、credit も消費しません。

取得可能な page は、先に `list_document_page_images` で確認します。page image は API 仕様上 JPEG なので、MCP response の `media_type` は `image/jpeg` 固定です。

対応エンドポイント: `GET /v1/documents/{document_id}/pages/{page_number}/image`

### パラメータ差分

| Tool parameter | API parameter | 理由 |
| --- | --- | --- |
| `document_id` | `document_id` | 対象文書 ID。 |
| `page_number` | `page_number` | `/page-images` に含まれるページ番号。 |
| `allow_file_download` | なし | ローカルファイル保存を明示許可する MCP 専用 parameter。`true` 以外は拒否します。 |

### 返り値

```json
{
  "ok": true,
  "document_id": "doc_123",
  "page_number": 2,
  "file_path": "/home/user/.cache/momonga-search-mcp/cache/documents/doc_123/pages/2.jpg",
  "resource_uri": "momonga://documents/doc_123/pages/2",
  "media_type": "image/jpeg",
  "cached": false
}
```

### 残す field

| Field | 理由 |
| --- | --- |
| `document_id` | 対象文書の確認。 |
| `page_number` | 取得したページの確認。 |
| `file_path` | ローカルに保存した画像ファイルの場所。 |
| `resource_uri` | cache 済みページ画像を指すローカル resource ID。 |
| `media_type` | API 仕様上 `image/jpeg`。 |
| `cached` | 実体取得 API を呼ばず cache から返したかどうか。 |

### 落とす field

画像 bytes は MCP response に載せません。画像の解析結果もこの tool では返しません。

## `list_news`

条件に合うニュースを一覧します。

対応エンドポイント: `GET /v1/news`

### 返り値

```json
{
  "ok": true,
  "results": [
    {
      "news_id": "news_123",
      "statement": "Company announced...",
      "observed_at": "2026-05-01T00:00:00Z",
      "related_issuers": [{"security_code": "8058", "name": "三菱商事株式会社"}],
      "macro_tags": ["Monetary Policy"],
      "references": []
    }
  ],
  "next_cursor": "cursor_1"
}
```

### 残す field

| Field | 理由 |
| --- | --- |
| `news_id` | ニュース項目の識別。 |
| `statement` | モデルが読む本文。 |
| `observed_at` | 時点の判断。 |
| `related_issuers` | 関連 issuer の確認。 |
| `macro_tags` | マクロ分類の判断。 |
| `references` | 根拠文書や URL へ戻るため。 |
| `next_cursor` | 続きの一覧取得に必要。 |

### 落とす field

`parent_news_id`, `score` など、一覧取得の判断に直接不要な field。

## `get_document_content`

指定した section の本文を取得します。API の `content_sections` を MCP response でも使います。
`section_ids` は必須で、全文取得はこの tool では行いません。

対応エンドポイント: `GET /v1/documents/{document_id}/content`

### パラメータ差分

| Tool parameter | API parameter | 理由 |
| --- | --- | --- |
| `section_ids` | `sections` | 必須。1〜5件。MCP tool 側では ID 配列であることを明確にするため。API 呼び出し時に `sections` query parameter に変換します。 |
| `offset` | なし | `truncated=true` の section の続き取得に使う文字 offset。通常は省略します。指定時は `section_ids` を1件だけ渡します。 |
| `return_content` | なし | MCP response に本文を含めるかを制御する MCP 専用 parameter。API から取得した本文は、返却有無に関係なく cache に保存します。 |

### 返り値

```json
{
  "ok": true,
  "document_id": "doc_123",
  "content_sections": [
    {
      "section_id": "sec_1",
      "section_title": "Risk Factors",
      "character_count": 1200,
      "content": "Risk Factors...",
      "truncated": false,
      "offset": 0,
      "resource_uri": "momonga://documents/doc_123/sections/sec_1",
      "cached": false
    }
  ],
  "max_characters": 30000,
  "character_limit_reached": false,
  "cache_hit": false
}
```

`return_content=false` の場合、`content_sections[].content` は返しません。取得した本文は返却有無に関係なく cache に保存します。
MCP response に含める本文は、サーバ側固定上限の 30000 文字で切り詰めます。
`content_sections[].truncated=true` の場合は、その section に `next_offset` を返します。続きは同じ `document_id`、同じ単一 `section_id`、`offset=content_sections[].next_offset` で取得します。
複数 section 取得時に tool call 全体の文字数上限へ達し、後続 section の本文を開始できない場合、その section は `content_omitted=true` / `omitted_reason=character_limit_reached` になり、`truncated` と `next_offset` は返しません。その section を読むには、同じ `document_id` とその単一 `section_id` で改めて取得します。
### 残す field

| Field | 理由 |
| --- | --- |
| `document_id` | 対象文書の確認。 |
| `content_sections[].section_id` | 取得した section の確認。 |
| `content_sections[].section_title` | 取得した section の表示名。 |
| `content_sections[].character_count` | 本文量の確認。 |
| `content_sections[].content` | `return_content=true` の場合の本文。 |
| `content_sections[].truncated` | `content` がサーバ側固定上限で切り詰められたかどうか。 |
| `content_sections[].offset` | 返却した `content` の開始位置。 |
| `content_sections[].next_offset` | `truncated=true` の場合、続き取得に使う offset。 |
| `content_sections[].content_omitted` | tool call 全体の文字数上限により、この section の本文を返さなかったかどうか。 |
| `content_sections[].omitted_reason` | `content_omitted=true` の理由。 |
| `content_sections[].resource_uri` | cache 済み section を指すローカル resource ID。 |
| `content_sections[].cached` | その section が今回 cache 由来かどうか。 |
| `max_characters` | この tool call で返す本文文字数の MCP 側上限。 |
| `character_limit_reached` | tool call 全体で文字数上限に達したかどうか。 |
| `cache_hit` | tool call 全体が API call を skip したかどうか。 |

### 落とす field

top-level `content`, `sections_returned`, `content_format`, document metadata 系。

## `search_documents`

文書本文を検索し、該当 section を `get_document_content` で取得するために使います。

対応エンドポイント: `POST /v1/search/documents`

### 返り値

```json
{
  "ok": true,
  "results": [
    {
      "document_id": "doc_123",
      "document_family": "edinet_filing",
      "title": "Annual Securities Report",
      "document_type": "yuho",
      "issuers": [{"security_code": "8058", "name": "三菱商事株式会社"}],
      "timeline_at": "2026-05-01T00:00:00Z",
      "content_status": "ready",
      "reference_url": "https://example.com/report.pdf",
      "matches": [
        {
          "section_id": "sec_1",
          "section_title": "Risk Factors",
          "score": 9.2,
          "snippet": "Commodity price risk...",
          "page_number": 5,
          "has_visual": true
        }
      ]
    }
  ]
}
```

### 残す field

| Field | 理由 |
| --- | --- |
| `document_id` | `get_document_content` の対象 ID。 |
| `document_family` | EDINET filing / timely disclosure / IR material の判別。 |
| `title` | 検索結果の文書識別。 |
| `document_type` | 文書種別の判断。 |
| `issuers` | issuer filter なし・複数社検索時の文書帰属確認。 |
| `timeline_at` | 時点の判断。 |
| `content_status` | 本文取得に進めるか判断するため。 |
| `reference_url` | `external_only` など本文取得できない文書で外部根拠へ進むため。 |
| `matches[].section_id` | `get_document_content.section_ids` に渡す selector。 |
| `matches[].section_title` | match 箇所の短い表示名。 |
| `matches[].score` | 検索結果の順位判断。 |
| `matches[].snippet` | 本文取得前の関連性判断。 |
| `matches[].page_number` | 必要なら page image 確認へ進むため。 |
| `matches[].has_visual` | match 箇所に図表などの視覚情報があるかの判断。 |

### 落とす field

document metadata 系は `list_documents` と同じです。

## `search_news`

ニュースを検索します。

対応エンドポイント: `POST /v1/search/news`

### 返り値

`list_news` と同じ field を返します。

```json
{
  "ok": true,
  "results": [
    {
      "news_id": "news_123",
      "statement": "Company announced...",
      "observed_at": "2026-05-01T00:00:00Z",
      "related_issuers": [{"security_code": "8058", "name": "三菱商事株式会社"}],
      "macro_tags": ["Monetary Policy"],
      "references": []
    }
  ]
}
```

### 残す field

`list_news` と同じです。

### 落とす field

`list_news` と同じです。

## 共通 error response

すべての tool は、API error や MCP 側 validation error をそのまま投げず、model-facing な JSON payload に正規化して返します。

MCP の `tools/call` response では `isError=true` を付け、`structuredContent` に以下の JSON payload を入れます。`content[].text` は短いsummaryだけを返します。

### 返り値

```json
{
  "ok": false,
  "error": {
    "code": "rate_limit_exceeded",
    "status": 429,
    "message": "Rate limit exceeded",
    "next_action": "Wait for retry_after_seconds before retrying this request.",
    "detail": "Please retry later.",
    "retry_after_seconds": 12
  }
}
```

### 残す field

| Field | 理由 |
| --- | --- |
| `ok` | 成功 payload と同じ位置で失敗を判定するため。 |
| `error.code` | programmatic な分岐に使う安定した error code。 |
| `error.status` | HTTP status がある場合の分類に使う。MCP 側 validation error など HTTP response がない場合は `null`。 |
| `error.message` | 人間向けの短い error summary。 |
| `error.next_action` | Agent が同じ失敗を繰り返さないための次アクション。 |
| `error.detail` | API が返す補足説明。存在する場合だけ返す。 |
| `error.retry_after_seconds` | rate limit / pending release など、待機して再試行できる場合の待機秒数。存在する場合だけ返す。 |
| `error.content_status` | `content_not_available` など、文書取得可否の分岐に使える場合だけ返す。 |
| `error.document_id` | 失敗対象の文書を特定できる場合だけ返す。 |
| `error.reference_url` | `external_only` など、API 本文取得から外部根拠確認へ切り替える場合だけ返す。 |

### 落とす field

API error payload のうち、上記以外の metadata、内部 trace、request ID、認証情報、header、body dump は返しません。

### 代表的な `next_action`

| Error | `next_action` |
| --- | --- |
| rate limit | `retry_after_seconds` を待ってから再試行する。 |
| quota exceeded | user が quota / task scope を変えるまで credit-consuming tool を止める。 |
| authentication error | API key 設定を確認する。 |
| timeout | 短い backoff 後に一度だけ再試行し、続く場合は query / 件数を絞る。 |
| content not available | 同じ content request を即時再試行せず、`content_status` を見て metadata / reference に切り替える。 |
| validation error | tool input を修正して再実行する。 |

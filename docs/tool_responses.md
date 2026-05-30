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

MCPは、候補・取得可否・取得単位の確認と、本文・画像・元ファイルの取得を分けています。

| MCP tool | API endpoint | MCP cache | 主な注意 |
| --- | --- | --- | --- |
| `search_issuers` | `GET /v1/issuers/search` | no | issuer特定に使います。 |
| `list_documents` | `GET /v1/documents` | no | `security_codes` なしの場合は `timeline_since` が必須です。 |
| `get_document_metadata` | `GET /v1/documents/{document_id}` | no | `content_status` や取得可否の確認に使います。 |
| `get_document_toc` | `GET /v1/documents/{document_id}/toc` | yes | `content_status=ready` の文書で、section IDと取得単位を確認します。 |
| `list_document_page_images` | `GET /v1/documents/{document_id}/page-images` | no | page image取得前に利用可能pageを確認します。 |
| `list_document_originals` | `GET /v1/documents/{document_id}/originals` | no | original file取得前に `original_id` を確認します。 |
| `list_news` | `GET /v1/news` | no | newsは記事全文ではなく `statement` + `references[]` です。 |
| `get_document_content` | `GET /v1/documents/{document_id}/content` | yes | 小さいsectionだけ本文を返し、大きいsectionはcache保存後にmanifestを返します。 |
| `search_section_contents` | local cache section search | read | cache済みsection内を検索し、短い抜粋とoffsetだけ返します。 |
| `get_section_window` | local cache section window | read | cache済みsectionのoffset周辺だけを上限付きで返します。 |
| `search_documents` | `POST /v1/search/documents` | no | 検索結果は候補です。必要なsection本文は `get_document_content` で取得します。 |
| `search_news` | `POST /v1/search/news` | no | documents検索とは統合rankingしません。 |
| `get_document_page_image` | `GET /v1/documents/{document_id}/pages/{page_number}/image` | yes | `list_document_page_images` で確認後、必要pageだけ取得します。 |
| `get_document_original` | `GET /v1/documents/{document_id}/originals/{original_id}` | yes | `list_document_originals` で確認後、必要fileだけ取得します。 |
| `list_cached_resources` | local cache index | read | cache済みresource URIを確認します。 |

## 金融・開示データの扱い

このMCPは投資助言・売買判断を提供しません。tool response は一次情報や根拠候補を扱うためのものであり、最終判断や公式情報との照合は利用者側で行います。

- `published_at` がある場合は文書の公表時刻として扱います。`timeline_at` は時系列整理用の正規化時刻であり、公式公表時刻として扱わないでください。
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
      "published_at": "2026-05-01T00:00:00Z",
      "timeline_at": "2026-05-01T00:00:00Z",
      "content_status": "ready",
      "character_count": 9000,
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
| `published_at` | 文書の公表時刻として使うため。 |
| `timeline_at` | 時系列で候補を選ぶため。 |
| `content_status` | `get_document_toc` / `get_document_content` に進めるか判断するため。 |
| `character_count` | TOC取得前の本文量見積もりや、section selection の要否判断に使うため。 |
| `reference_url` | `external_only` など本文取得できない文書で外部根拠へ進むため。 |
| `next_cursor` | 続きの一覧取得に必要。 |

### 落とす field

`tags`, `timeline_precision`, `timeline_basis`, `first_observed_at`, `content_available`, `image_available`, `page_count`, `page_image_count`

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
  "published_at": "2026-05-01T00:00:00Z",
  "timeline_at": "2026-05-01T00:00:00Z",
  "content_status": "ready",
  "character_count": 9000,
  "reference_url": "https://example.com/report.pdf",
  "next_action": {
    "status": "ready",
    "recommended_tools": ["get_document_toc", "get_document_content"],
    "argument_hints": {"document_id": "doc_123"}
  }
}
```

### 残す field

`list_documents` と同じです。

### MCP が追加する field

`next_action` は `content_status` に応じて次に使う tool や引数 hint を示す MCP helper field です。`content_status=ready` の場合は `get_document_toc` / `get_document_content`、`pending_release` の場合は待機、`external_only` の場合は外部参照確認へ誘導します。

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
  "toc_mode": "sections",
  "path_prefix": [],
  "max_depth": 2,
  "include_sections": true,
  "selection_policy": {
    "mode": "auto",
    "reason": "toc_is_small",
    "max_direct_toc_sections": 50,
    "selected_toc_entry_count": 1
  },
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
| `toc_mode` | `sections` / `outline` / `subtree` の判別。section selector を直接使えるか、subtree取得が必要かを判断するため。 |
| `path_prefix` | focused subtree 取得時に指定された heading path。 |
| `max_depth` | outline 展開深度。 |
| `include_sections` | section selector を含める指定だったかの確認。トップレベル呼び出しで `include_sections=true` の場合、`toc_mode` は `sections` になります。 |
| `selection_policy` | TOCを直接返すかoutline化したかの判断理由と件数。 |
| `toc` | 取得する section を選ぶための目次。 |
| `toc[].section_id` | `toc_mode=sections` の場合に返ります。`get_document_content.section_ids` に渡す必須 selector。 |
| `toc[].section_title` | `toc_mode=sections` の場合に返ります。section 選択用の短い表示名。 |
| `toc[].heading_path` | `toc_mode=sections` の場合は section の階層文脈、`outline` / `subtree` の場合は outline node の heading path。 |
| `toc[].character_count` | `toc_mode=sections` の場合に返ります。大きすぎる section の取得を避けるための目安。 |
| `toc[].page_number` | `toc_mode=sections` の場合に返ります。図表・画像確認が必要な場合に page image へ進むための目安。 |
| `toc[].heading_title` | `toc_mode=outline` / `subtree` の場合に返ります。outline node の表示名。 |
| `toc[].section_count` | `toc_mode=outline` / `subtree` の場合に返ります。node 配下の section 数。 |
| `toc[].total_character_count` | `toc_mode=outline` / `subtree` の場合に返ります。node 配下の概算文字数。 |
| `toc[].page_range` | `toc_mode=outline` / `subtree` の場合に返ります。node 配下のページ範囲。 |
| `toc[].has_children` | `toc_mode=outline` / `subtree` の場合に返ります。さらに下位 heading があるかどうか。 |
| `toc[].children` | `toc_mode=outline` / `subtree` で depth 内に下位 node がある場合だけ返ります。 |
| `toc[].sections` | `toc_mode=subtree` かつ `include_sections=true` の場合だけ返ります。中身は section selector entry です。トップレベル呼び出しでは `include_sections=true` により `toc_mode=sections` になるため、`toc_mode=outline` と `include_sections=true` の組み合わせでは返りません。 |
| `next_action_template` | `toc_mode=outline` の場合だけ返ります。選んだ `heading_path` で再度 `get_document_toc` を呼ぶための hint。 |
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

`image_role`, `source_route`

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

`content_available`, `content_status`, `original_available`, `kind`, `role`, `size_bytes`, `sha256`

## `get_document_original`

元ファイルを1件取得し、ローカル cache に保存します。

この tool は file download を伴うため、`allow_file_download=true` が必須です。cache hit の場合は API の実体取得を行いません。

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

元ファイル bytes は MCP response に載せません。ファイルの解析結果もこの tool では返しません。

## `get_document_page_image`

ページ画像を1件取得し、ローカル cache に保存します。

この tool は file download を伴うため、`allow_file_download=true` が必須です。cache hit の場合は API の実体取得を行いません。

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

`parent_news_id`

## `get_document_content`

指定した section の本文を取得します。API の `content_sections` を MCP response でも使います。
全文取得は `allow_full_document=true` を明示した場合だけ許可します。この場合、MCP response では全文を `section_id="__mcp_full_document__"` の synthetic section として返します。

対応エンドポイント: `GET /v1/documents/{document_id}/content`

### パラメータ差分

| Tool parameter | API parameter | 理由 |
| --- | --- | --- |
| `section_ids` | `sections` | 任意。指定時は1〜5件。MCP tool 側では ID 配列であることを明確にするため。API 呼び出し時に `sections` query parameter に変換します。省略時は `allow_full_document=true` が必須です。 |
| `return_content` | なし | MCP response に本文を含めるかを制御する MCP 専用 parameter。API から取得した本文は、返却有無に関係なく cache に保存します。 |
| `allow_full_document` | なし | デフォルトは `false`。`section_ids` を省略して全文を1つの synthetic section として cache する場合に必須の MCP 専用 safety flag。 |

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
      "content_mode": "inline",
      "resource_uri": "momonga://documents/doc_123/sections/sec_1",
      "cached": false
    }
  ],
  "max_inline_section_characters": 3000,
  "cache_hit": false,
  "requested_section_ids": ["sec_1"]
}
```

`allow_full_document=true` かつ `section_ids` 省略時は、全文を synthetic section として返します。

```json
{
  "ok": true,
  "document_id": "doc_123",
  "content_sections": [
    {
      "section_id": "__mcp_full_document__",
      "section_title": "Full document",
      "character_count": 9000,
      "content_mode": "manifest",
      "reason": "section_exceeds_inline_threshold",
      "content_available_in_cache": true,
      "recommended_tools": ["search_section_contents", "get_section_window"],
      "resource_uri": "momonga://documents/doc_123/sections/__mcp_full_document__",
      "source_resource_uri": "momonga://documents/doc_123/sections/__mcp_full_document__",
      "cached": false
    }
  ],
  "max_inline_section_characters": 3000,
  "cache_hit": false
}
```

`return_content=false` の場合、`content_sections[].content` は返しません。取得した本文は返却有無に関係なく cache に保存します。
MCP response に本文を inline で含めるのは、`character_count` が `max_inline_section_characters` 以下の section だけです。大きい section は `content_mode=manifest`、`content_available_in_cache=true`、`recommended_tools=["search_section_contents","get_section_window"]` を返し、本文は返しません。
`get_document_content` には別途の総文字数 cap はありません。1回の呼び出しで返りうる inline 本文量は、`max_inline_section_characters` と `section_ids` 上限により bounded です。

### 残す field

| Field | 理由 |
| --- | --- |
| `document_id` | 対象文書の確認。 |
| `content_sections[].section_id` | 取得した section の確認。 |
| `content_sections[].section_title` | 取得した section の表示名。 |
| `content_sections[].character_count` | 本文量の確認。 |
| `content_sections[].content` | `return_content=true` の場合の本文。 |
| `content_sections[].content_mode` | `inline` / `manifest` の返却モード。 |
| `content_sections[].reason` | `content_mode=manifest` の判断理由。 |
| `content_sections[].content_available_in_cache` | 本文が cache に保存済みで、search/window tool で読めるかどうか。 |
| `content_sections[].recommended_tools` | 長い section を短い抜粋または bounded window で読むための次 tool。 |
| `content_sections[].next_action` | `content_mode=manifest` の場合に返ります。`search_section_contents` と fallback の `get_section_window` へ進むための hint。 |
| `content_sections[].resource_uri` | cache 済み section を指すローカル resource ID。 |
| `content_sections[].source_resource_uri` | 根拠所在として使う resource URI。 |
| `content_sections[].cached` | その section が今回 cache 由来かどうか。 |
| `max_inline_section_characters` | section 本文を inline で返すか manifest にするかの閾値。 |
| `cache_hit` | tool call 全体が API call を skip したかどうか。 |
| `requested_section_ids` | 今回要求した section ID。`section_ids` 指定時だけ返ります。 |
| `missing_section_ids` | 要求した section のうち、API response / cache に存在しなかった ID。存在する場合だけ返ります。 |

### 落とす field

top-level `content`, `sections_returned`, `content_format`, document metadata 系。

## `search_section_contents`

cache済み section 本文を lexical 検索し、該当箇所の短い抜粋だけを返します。検索時は NFKC + casefold 正規化を使い、`offset` と `matched_text` は元本文基準で返します。API call は行いません。section が cache にない場合は、先に `get_document_content` で対象 `section_id` を取得します。

対応: local cache

### 返り値

```json
{
  "ok": true,
  "document_id": "doc_123",
  "section_id": "sec_1",
  "section_title": "Risk Factors",
  "match_type": "lexical",
  "query": "価格転嫁",
  "context_chars": 300,
  "max_matches": 5,
  "matches": [
    {
      "offset": 1234,
      "excerpt": "短い前後文脈...",
      "matched_text": "価格転嫁"
    }
  ],
  "source_resource_uri": "momonga://documents/doc_123/sections/sec_1",
  "cache_hit": true
}
```

## `get_section_window`

cache済み section 本文の指定 offset 周辺だけを返します。`search_section_contents.matches[].offset` で見つけた箇所の確認に使います。

対応: local cache

### 返り値

```json
{
  "ok": true,
  "document_id": "doc_123",
  "section_id": "sec_1",
  "section_title": "Risk Factors",
  "offset": 1234,
  "start_offset": 900,
  "end_offset": 2400,
  "actual_characters": 1500,
  "max_characters": 1500,
  "content": "指定offset周辺の本文...",
  "truncated": true,
  "source_resource_uri": "momonga://documents/doc_123/sections/sec_1",
  "cache_hit": true
}
```

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
      "published_at": "2026-05-01T00:00:00Z",
      "timeline_at": "2026-05-01T00:00:00Z",
      "content_status": "ready",
      "character_count": 9000,
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
| `published_at` | 文書の公表時刻として使うため。 |
| `timeline_at` | 時点の判断。 |
| `content_status` | 本文取得に進めるか判断するため。 |
| `character_count` | 本文量見積もりや、section selection の要否判断に使うため。 |
| `reference_url` | `external_only` など本文取得できない文書で外部根拠へ進むため。存在する場合だけ返ります。 |
| `matches[].section_id` | `get_document_content.section_ids` に渡す selector。 |
| `matches[].section_title` | match 箇所の短い表示名。 |
| `matches[].heading_path` | match section の階層文脈。存在する場合だけ返ります。 |
| `matches[].character_count` | match section の本文量。存在する場合だけ返ります。 |
| `matches[].score` | 検索結果の順位判断。 |
| `matches[].snippet` | 本文取得前の関連性判断。`include_snippet=true` の場合だけ返ります。 |
| `matches[].page_number` | 必要なら page image 確認へ進むため。存在する場合だけ返ります。 |
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

`parent_news_id`, `score` など、検索結果の候補確認後に根拠へ戻るためには直接不要な field。

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
| authentication error | API key 設定を確認する。 |
| timeout | 短い backoff 後に一度だけ再試行し、続く場合は query / 件数を絞る。 |
| content not available | 同じ content request を即時再試行せず、`content_status` を見て metadata / reference に切り替える。 |
| validation error | tool input を修正して再実行する。 |

# API 仕様(探索)

いずれもログイン必須(未ログインは `401`)、`POST` のみ、`Content-Type: application/json`、ヘッダー `X-CSRFToken` 必須(値は画面の `<meta name="csrf-token">`)。

## POST /explore/api/scan

カメラがシンボルを検出したときに呼ぶ。レート制限: 60 回/分/利用者。

リクエスト(どちらか):
- QR シンボル: `{"payload": "MIKKE1:<token>"}`
- 画像シンボル: `{"image_symbol": <id>, "patch": "<base64: 映像から射影変換で切り出した 32x32 グレースケール 1024 バイト>"}`
  サーバーが保持する全角度の照合用パッチと比べ、最も高い類似度が 65%(`MIKKE_IMAGE_SIMILARITY_THRESHOLD`)未満なら `404 unknown_symbol`(QR の不一致と区別しない。類似度の値は返さない)

| ステータス | 内容 |
|---|---|
| 200 | `{"status": "ready" \| "cooldown", "symbol": {"name", "spot"}, "next_available_at": RFC3339 \| null, "requires_location": bool, "ticket": string \| null}` |
| 400 | JSON 不正 |
| 404 | `{"error": "unknown_symbol"}` みっけシンボルではない / 非公開 |
| 429 | `{"error": "rate_limited"}` |

## GET /explore/api/image-symbols

カメラ画面が起動時に取得する、公開中の画像シンボルの特徴量一覧(**見え方=撮影角度ごとに 1 件**)。ログイン必須。参照写真・照合用パッチ・除外マスクは含まない。

レスポンス: `{"symbols": [{"id": <シンボル ID>, "view": "front" | "right" | …, "v": 1, "w", "h", "kp": [[x, y], ...], "desc": "<base64: 特徴点数 × 32 バイトの ORB 記述子>"}]}`

角度: `up_left` `up` `up_right` `left` `front` `right` `down_left` `down` `down_right`(最大 9)

## POST /explore/symbols/register/(スタッフのみ・multipart/form-data)

画像シンボルの新規登録。項目: `spot`, `name`, `hint`, `cooldown_hours`, `angles`(カンマ区切りの角度)、角度 `a` ごとに:

| 項目 | 内容 |
|---|---|
| `a_image` | 四角形で切り抜き・補正した JPEG(1.5MB まで、64〜2048px) |
| `a_features` | 上記形式の特徴量 JSON ファイル(30〜900 点) |
| `a_patch` | 32×32 グレースケールの照合用パッチ(base64, 1024 バイト) |
| `a_mask` | 除外マスク(base64, 128 バイト = 1024 ビット、1 = 判定しない)。省略時は除外なし。除外は 75% まで |

成功: `200 {"ok": true, "id", "redirect"}` / 失敗: `400 {"ok": false, "errors": ["【右から】…", ...]}`(どれか 1 角度でも不正なら何も保存しない)

## POST /explore/symbols/<id>/views/(スタッフのみ・multipart/form-data)

既存の画像シンボルの角度を追加・撮り直し・削除する。項目: `angles`(保存する角度)と上表の角度ごとの項目、`delete`(カンマ区切りの削除する角度)。すべての角度を削除する操作は 400。

## GET /maps/tiles/<name>.pmtiles(ログイン必須)

ローカルの地図タイル(PMTiles)。`Range: bytes=start-end` に対応(`206 Partial Content`、1 回 8MB まで)。範囲が不正なら `416`。外部の地図 API は使わない。

## POST /explore/api/collect

AR マークをタップしたときに呼ぶ。レート制限: 20 回/分/利用者。

ヘッダー: `Idempotency-Key: <UUID>` 必須(同じキーの再送には最初の結果を `replay: true` で返す。二重付与しない)

リクエスト: `{"ticket": "<scan で得たチケット>", "location": {"lat": number, "lng": number} | null}`
(`location` は `requires_location` が true のときだけ送る。サーバーは保存しない)

| ステータス | 内容 |
|---|---|
| 200 | `{"reward_kind": "item" \| "coupon" \| "none", "label", "is_new", "item": {...} \| null, "coupon": {...} \| null, "visit_days", "is_revisit_day", "achievements": [...], "replay", "symbol"}` |
| 400 | `invalid_ticket`(期限切れ 5 分 / 改ざん / 他人のチケット)、`error`(キー不正など) |
| 403 | `location_required` / `too_far` |
| 404 | `unknown_symbol` |
| 409 | `{"error": "cooldown", "next_available_at": RFC3339}` |
| 429 | `rate_limited` |

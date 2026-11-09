# API 仕様(探索)

いずれもログイン必須(未ログインは `401`)、`POST` のみ、`Content-Type: application/json`、ヘッダー `X-CSRFToken` 必須(値は画面の `<meta name="csrf-token">`)。

## POST /explore/api/scan

カメラがシンボルを検出したときに呼ぶ。レート制限: 60 回/分/利用者。

リクエスト: `{"payload": "MIKKE1:<token>"}`

| ステータス | 内容 |
|---|---|
| 200 | `{"status": "ready" \| "cooldown", "symbol": {"name", "spot"}, "next_available_at": RFC3339 \| null, "requires_location": bool, "ticket": string \| null}` |
| 400 | JSON 不正 |
| 404 | `{"error": "unknown_symbol"}` みっけシンボルではない / 非公開 |
| 429 | `{"error": "rate_limited"}` |

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

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

## POST /explore/api/nearby(ログイン必須)

現在地の周囲(サイト設定 `camera_radius_m`、既定 100m)にシンボルがあるか。カメラ起動の判定と地図表示に使う。位置は本文で受け取り、保存・ログ出力はしない。GET は 405。レート制限 30 回/分(超えると 429)。

リクエスト: `{"lat": 34.6965, "lng": 135.534}`(範囲外・数値でない場合は 400)

```json
{"radius_m": 100, "has_nearby": true, "nearest": null,
 "nearby": [{"id": 1, "lat": 34.6967, "lng": 135.5342, "distance_m": 38, "secret": false,
             "spot": "京橋 ほたる広場", "name": "ほたるの看板", "hint": "…",
             "items": [{"code": "hair-…", "name": "…", "rarity": 2, "category": "hair", "body_type": "any",
                        "conditions": ["秋限定"], "now": true, "image": "/explore/symbols/1/items/hair-….svg"}]},
            {"id": 2, "secret": true, "name": "？？？", "hint": "", "items": [], "...": "…"}]}
```

周囲にない場合は `has_nearby: false`、`nearest: {"spot", "distance_m"}`(いちばん近いスポット)。シークレットシンボルは名前・ヒント・アイテムを返さない。

## GET /explore/symbols/<id>/items/<code>.svg(ログイン必須)

そのシンボルで手に入るコーデのプレビュー画像(本人の肌・目の色で描画)。シークレット・公開期間外・ドロップに含まれないアイテムは 404。

## GET /explore/finders/<token>/(ログイン必須)

「こんな人が獲得しているよ」の 1 人のコーデ。`token` は受け取り結果の `recent_finders[].token`(見る人に結び付いた署名付き、2 時間有効)。
`{"nickname", "avatar": "<URL>", "items": [{"code", "name", "category", "rarity", "image": "<URL>", "obtained": "さくら坂喫茶でみっけ(冬)"}]}`。
トークンが不正・期限切れ・別の人のもの・相手が表示を OFF にした場合は 404。`avatar.svg`・`items/<code>.svg`(今着ているアイテムだけ)も同じ条件。

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

`recent_finders`: 直近 30 分に同じシンボル(少なければ同じスポット)でみっけした人、最大 6 人。`[{"token", "nickname", "ago": "さっき" | "15分前"}]`(「みっけ仲間に表示する」が ON の利用者だけ。利用者 ID は含めない)。

`item` は `{"code", "name", "category"(表示名), "slot"(部位コード), "rarity", "new"}`。結果画面では次の絵を表示する:

- アイテム: `GET /wardrobe/items/<code>.svg`(全身で身につけた姿)と、くつ・ボトムス・トップス・髪・顔は `?zoom=1`(その部位の拡大図)
- クーポン: `GET /rewards/coupons/<id>.svg`(チケット型の絵。本人のクーポンのみ、他人は 404。引換コードは含めない。使用済みなら印つき)
- 何もなし: なし(ドロップが未設定・条件外のときも、ふだん用のコーデを渡すため通常は起きない)
- 実績のごほうび(アイテム・クーポン)も同じ絵を小さく並べる

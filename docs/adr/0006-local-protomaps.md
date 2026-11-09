# ADR 0006: 地図は Protomaps のタイルをローカル配信する

- 状態: 採用
- 日付: 2026-11-09

## 背景

スポットの地図を表示したい。条件は「Protomaps を使う」「API は利用せず、タイルデータを使ってローカルで動作させる」「範囲は大阪府の京橋付近」。

## 決定

| 要素 | 採用したもの | 理由 |
|---|---|---|
| タイル | Protomaps basemap の公開ビルドから京橋付近だけを切り出した PMTiles 1 ファイル(`maps/tiles/kyobashi.pmtiles`、約 4.2MB) | 1 ファイルで完結し、タイルサーバー不要 |
| 切り出し | `scripts/extract_tiles.py`(pmtiles Python ライブラリ + HTTP Range) | 全世界 約 140GB をダウンロードせず、範囲内 48 タイルだけを取得。Go 製 CLI は、この環境のアプリ制御ポリシーで実行できない可能性があるため Python で実装 |
| 描画 | Leaflet 1.9.4 + protomaps-leaflet 5.1.0(同梱、npm の integrity 照合済み) | 純粋な JavaScript で Canvas 描画。WebGL・Web Worker・eval・外部フォント/スプライトが不要 → 既存の CSP(`script-src 'self'`)を緩めずに動く。MapLibre GL はグリフ・スプライト・Worker の配信が別途必要になるため見送り |
| 配信 | `maps/views.py`(Range 対応・ログイン必須・ファイル名は英小文字のみ許可しパストラバーサルを防止) | protomaps-leaflet は PMTiles を Range リクエストで読む。Django 標準の静的ファイル配信は Range 非対応 |

- 日本語ラベル(`lang: "ja"`)、OS がダークモードのときはダーク表示
- 現在地ボタン: 位置情報は端末内で地図に表示するだけで、サーバーに送らない
- デモ用スポットの座標を京橋付近に移した(名前は架空のまま)

## トレードオフ

- 収録範囲外(京橋付近以外)は表示できない。範囲を広げるとファイルが大きくなる(z15 までで、範囲の面積にほぼ比例)
- 地図データは更新されない。必要に応じてスクリプトで作り直す
- 帰属表示(© OpenStreetMap contributors / Protomaps)は ODbL の条件のため常に表示する

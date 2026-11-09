# 地図タイル (PMTiles)

| ファイル | 範囲 | ズーム | 元データ |
|---|---|---|---|
| `kyobashi.pmtiles` (約 4.2MB / 48 タイル) | 大阪府 京橋付近 経度 135.5150〜135.5500 / 緯度 34.6800〜34.7080(JR 京橋駅・大阪ビジネスパーク・大阪城北側) | 0〜15(表示は 18 まで拡大可) | Protomaps basemap v4.15.2(ビルド 2026-11-08) |

- アプリは `maps/views.py` がこのファイルを HTTP Range で配信し、ブラウザの protomaps-leaflet が描画する。**実行時に外部の地図 API・タイルサーバーへは一切アクセスしない**。
- 作り直す・範囲を変える場合(このときだけ https://build.protomaps.com に Range リクエストを送り、範囲内のタイルだけを取得する):

```bash
.venv\Scripts\python.exe scripts\extract_tiles.py --out maps\tiles\kyobashi.pmtiles --bbox 135.515 34.680 135.550 34.708
```

範囲を変えたら `config/settings.py` の `MIKKE_MAP`(`bounds` / `center`)も合わせる。

## ライセンス・帰属表示

地図データ © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors(ODbL 1.0)。タイル化: [Protomaps](https://protomaps.com)。
地図の右下に帰属表示を出している(消さないこと)。

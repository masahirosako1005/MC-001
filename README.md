# みっけ (Mikke)

観光地にかくれた **みっけシンボル** をスマホのカメラでのぞくと、映像の上に光るマークが現れる(疑似AR)。
タップするとアバターの服・髪型や地域のクーポンが手に入る。
**季節・時間帯・再訪日数で出会えるものが変わる** ため、「一度行けば終わり」のスタンプラリーと違い、何度も訪れたくなる体験を目指す Web アプリです。

| 技術 | 内容 |
|---|---|
| サーバー | Python 3.13 / Django 6.1(ローカルホスト) |
| DB | PostgreSQL 17(TLS 1.3 必須・SCRAM 認証・データチェックサム有効)/ 代替として SQLite |
| 暗号化 | AES-256-GCM のフィールド暗号化 + HMAC ブラインドインデックス(`core/crypto.py`) |
| フロント | Django テンプレート + 素の JavaScript。QR 検出に jsQR 1.4.0、画像認識に jsfeat 0.0.8、地図に Leaflet 1.9.4 + protomaps-leaflet 5.1.0(いずれも同梱・npm の integrity 照合済み) |
| 地図データ | Protomaps basemap(PMTiles、京橋付近 約 4.2MB を同梱)© OpenStreetMap contributors |

## 主な機能

- **みっけ**(`/explore/`、ホームの「みっけに行く」・下のメニュー中央の「みっけ」): 地図とカメラを 1 画面に統合。開くとまず **①現在地を取得 → ②周囲のシンボルを検索** し、近くにあれば **「カメラでみっけ」** が押せるようになる(なければ「ここにはなさそう・・・」)。地図の「現在地」と「近くのシンボルを探す」も同じ順番で動く。スポットのカード一覧は現在非表示(`explore/views.py` の `SHOW_SPOT_CARDS`)。旧 `/explore/camera/` は `/explore/` へ転送。
- **疑似ARカメラ探索**(「みっけ」画面の ②): カメラ映像を canvas に描画し、シンボルを検出すると位置に追従する光るマークを重ねる。マーク(または同じ動作のボタン)をタップで受け取り、**手に入れた物を絵で表示**(アイテムは身につけた姿 + 部位の拡大図、クーポンはチケット型の絵、実績のごほうびも絵つき)。映像はサーバーに送らない。カメラが使えない場合は「写真から読み取る」でも可。
- **アバター着せ替え**(`/wardrobe/`): ちびキャラ風のかわいいアバター。体のタイプ(女の子/男の子、だれでも自由に選べる)、目の色 6 色、肌の色 8 色、顔・髪・トップス・ボトムス・くつ・こもの・エフェクト・背景 の 8 部位。**サンプルパーツは女の子用 50 種類・男の子用 50 種類 + 共通 42 種類(顔 12・背景 20・動くエフェクト 10)**。エフェクトは SVG アニメーション(キラキラ・ハートが浮かぶ など)。**管理者は持っていないパーツや別タイプのパーツも自由に選べる**(全パーツ一覧: `/wardrobe/catalog/`)。登録時に性別は聞かない。[ADR 0004](docs/adr/0004-avatar-rendering.md)
- **UI テーマ(デザイン案 4 種)**: A. スタンダード / B. ゲームホーム(1 画面完結) / C. トラベルマガジン / D. 和モダン。ログイン前・ログイン後・各ページの見た目が変わる。**管理画面「サイト設定」で全員分を切り替え**、管理者は `?ui=game` で自分だけ試し見。ログイン前ページには Claude が作った写真風 CG(仮想写真 5 枚)を使用。[ADR 0008](docs/adr/0008-ui-themes.md)
- **コーデコンテスト**(`/contest/`): ①今のアバターでエントリー → ②評価モード → ③ランダムな 3 体 × 3 回、各回 1 体まで高評価 → ランキング。④表示回数が少ないアバターを優先、⑤参加者 10 人未満の間は BOT も表示(BOT への評価はランキングに反映しない)。評価中は名前を隠す。[ADR 0007](docs/adr/0007-contest.md)
- **再訪の仕掛け**: ドロップ表に「季節」「時間帯(朝/昼/夕/夜)」「解放に必要な訪問日数」を設定でき、同じシンボルでも来るたびに中身が変わる。シンボルごとにクールダウン(既定 20 時間)。
- **クーポン**(`/rewards/coupons/`): 探索・実績で発行。引換コードは暗号化保存。店頭で「使う」を押すと使用済みスタンプ表示(二重使用不可)。
- **やりこみ実績**(`/rewards/achievements/`): 累計みっけ数、訪問スポット数、アイテム種類数、同一スポットの訪問日数、同一スポットで体験した季節数。
- **2 種類のシンボル**:
  - **QR シンボル**: 印刷して掲示する、中央に「み」ロゴ入りの QR 型シンボル
  - **画像シンボル**: スタッフが現地の看板・像・壁画などを**カメラで撮影して登録**(`/explore/symbols/register/`)。写真の中を**四角形で切り抜き**(斜めからの写真も正面に補正)、人や空など**判定しない部分はマウス・指で塗りつぶして除外**、**正面・右から・左から・斜め上からなど最大 9 角度**を登録できる。利用者が実物を写し、登録した見え方と**類似度 65% 以上**なら AR マークが現れる。掲示物は不要。仕組みと検証結果は [ADR 0005](docs/adr/0005-image-symbols.md)
- **スポット地図**(「みっけ」画面の ①): **Protomaps** のタイルを**ローカルで配信**(大阪府 京橋付近を収録、外部の地図 API は不使用)。スポットのピン・ポップアップ・現在地表示。「近くのシンボルを探す」で周囲のシンボルを★で表示し、タップすると**ここで獲得可能なコーデの画像**と条件(季節・時間帯・訪問日数)が見られる。[ADR 0006](docs/adr/0006-local-protomaps.md)、データの作り直しは [maps/tiles/README.md](maps/tiles/README.md)
- **GPS によるカメラ起動判定**: 現在地の周囲 100m(管理画面「サイト設定」で 10〜5000m に変更可)にシンボルがあるときだけカメラを起動。ないときは「ここにはなさそう・・・」と表示。位置情報は判定だけに使い、保存しない。[ADR 0009](docs/adr/0009-spot-period-and-gps-gate.md)
- **シークレットシンボル**: 地図では「？」の画像だけを表示し、名前・ヒント・手に入るコーデは見つけるまで秘密。
- **運営向け**: ヘッダーの「管理」(`/explore/manage/spots/`)で**スポットの追加・編集・削除**(地図で位置を選ぶ・**有効期限を設定 / 無期限**・記録があるスポットは削除の代わりに非公開 / 期限切れ)、QR シンボルの印刷、画像シンボルの撮影登録ができる。Django 管理画面(URL は `.env` の `DJANGO_ADMIN_URL`)ではシンボル・ドロップ・アイテム・クーポン・実績を管理。シンボルの位置(未設定ならスポットの位置)・シークレット・ドロップ(出てくる物)は管理画面の「シンボル」で設定する。

## セットアップ(Windows / ローカル)

前提: Python 3.12 以上、PostgreSQL 17 のバイナリ(`PG_BIN`)。この環境では `%LOCALAPPDATA%\pg17` に配置済み。

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

```bash
.venv\Scripts\python.exe scripts\localdb.py init
```

`init` は `.env` に秘密値をランダム生成し、PostgreSQL を初期化(TLS 証明書・`hostssl` のみの pg_hba・SCRAM)、アプリ用ロールと DB を作成します。

```bash
.venv\Scripts\python.exe manage.py migrate
```

```bash
.venv\Scripts\python.exe manage.py seed_mikke
```

```bash
.venv\Scripts\python.exe manage.py createadmin --email ops@example.com
```

```bash
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

ブラウザで http://localhost:8000/ を開き、「はじめる」からアカウントを作成します。

- PostgreSQL の起動・停止: `python scripts\localdb.py start` / `stop` / `status`
- **PostgreSQL が使えない場合**: `.env` に `DB_ENGINE=sqlite` を書くと SQLite(`mikke.sqlite3`)で動きます。フィールド暗号化はどちらでも有効です。
- アプリ制御ポリシー(WDAC / Smart App Control)が psycopg 同梱 DLL や `.venv\Scripts\*.exe` を拒否する環境では、`settings.py` が PostgreSQL 付属の `libpq.dll` を使う pure-python 実装に自動で切り替えます。コマンドは `python -m ruff` のように `python -m` 経由で実行してください。

### スマートフォンで試すには

カメラ API は「安全なコンテキスト」(HTTPS または localhost)でのみ動きます。PC の localhost では動作しますが、スマホから LAN 経由で開く場合は HTTPS 化(リバースプロキシや開発用証明書)が必要です。

## テスト・品質チェック

```bash
.venv\Scripts\python.exe manage.py test
```

```bash
.venv\Scripts\python.exe -m ruff check .
```

```bash
.venv\Scripts\python.exe -m pip_audit -r requirements.txt
```

## ディレクトリ構成

```
config/      Django 設定 (環境変数から読み込み)
core/        暗号化 (crypto.py / fields.py)、監査ログ、レート制限、季節・時間帯、ホーム
accounts/    利用者 (メール暗号化 + ブラインドインデックス)、登録・ログイン (連続失敗ロック)
explore/     スポット・シンボル (QR / 画像・最大 9 角度)・ドロップ表・訪問記録・みっけ記録、スキャン/受け取り API
maps/        地図タイル (PMTiles) の Range 配信、tiles/kyobashi.pmtiles
contest/     コーデコンテスト (エントリー・評価・ランキング・BOT)
wardrobe/    アイテム、所持品、アバター設定、SVG アバター描画
rewards/     クーポン (引換コード暗号化)、実績
templates/   画面テンプレート
static/      CSS / JS (camera.js = 疑似AR) / jsQR (vendor)
scripts/     ローカル PostgreSQL 管理
docs/        ADR、要件トレーサビリティ
```

## ドキュメント

- [要件とトレーサビリティ](docs/requirements.md)
- [ADR 0001 シンボル検出方式](docs/adr/0001-symbol-detection.md)
- [ADR 0002 DB 暗号化](docs/adr/0002-db-encryption.md)
- [ADR 0003 再訪を促すゲーム設計](docs/adr/0003-revisit-design.md)
- [ADR 0004 アバターの描画方式](docs/adr/0004-avatar-rendering.md)
- [ADR 0005 画像シンボル(撮影した写真をシンボルにする)](docs/adr/0005-image-symbols.md)
- [ADR 0006 地図は Protomaps のタイルをローカル配信](docs/adr/0006-local-protomaps.md)
- [ADR 0007 コーデコンテスト](docs/adr/0007-contest.md)
- [ADR 0008 UI テーマ(デザイン案)の切り替え](docs/adr/0008-ui-themes.md)
- [API 仕様](docs/api.md)

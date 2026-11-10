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
- **疑似ARカメラ探索**(「みっけ」画面の ②): カメラ映像を canvas に描画し、シンボルを検出すると位置に追従する光るマークを重ねる。マーク(または同じ動作のボタン)をタップで受け取り、**必ずコーデがもらえる**(ドロップ未設定・条件外のときは、ふだん用のコーデ。持っているものなら「取得済み」と表示)。**手に入れた物を絵で表示**(アイテムは身につけた姿 + 部位の拡大図、クーポンはチケット型の絵、実績のごほうびも絵つき)。結果画面の下に**「こんな人が獲得しているよ」**(直近 30 分に同じシンボルでみっけした人を最大 6 人。名前を押すとコーデ、コーデを押すとどのスポットで手に入れたか)。表示されるのは「みっけ仲間に表示する」を ON にした人だけ([ADR 0011](docs/adr/0011-recent-finders-and-coupons.md))。映像はサーバーに送らない。カメラが使えない場合は「写真から読み取る」でも可。
- **アバター着せ替え**(`/wardrobe/`): ちびキャラ風のかわいいアバター。体のタイプ(女の子/男の子、だれでも自由に選べる)、目の色 6 色、肌の色 8 色、顔・髪・トップス・ボトムス・くつ・こもの・エフェクト・背景 の 8 部位。**サンプルパーツは女の子用 50 種類・男の子用 50 種類 + 共通 42 種類(顔 12・背景 20・動くエフェクト 10)**。エフェクトは SVG アニメーション(キラキラ・ハートが浮かぶ など)。全パーツの一覧はサイト運営者の画面の「アイテム一覧」で見られる。登録時に性別は聞かない。[ADR 0004](docs/adr/0004-avatar-rendering.md)
- **UI テーマ(デザイン案 4 種)**: A. スタンダード / B. ゲームホーム(1 画面完結) / C. トラベルマガジン / D. 和モダン。ログイン前・ログイン後・各ページの見た目が変わる。**管理画面「サイト設定」で全員分を切り替え**(見え方の確認は利用者のアカウントで)。ログイン前ページには Claude が作った写真風 CG(仮想写真 5 枚)を使用。[ADR 0008](docs/adr/0008-ui-themes.md)
- **コーデコンテスト**(`/contest/`): ①今のアバターでエントリー → ②評価モード → ③ランダムな 3 体 × 3 回、各回 1 体まで高評価 → ランキング。④表示回数が少ないアバターを優先、⑤参加者 10 人未満の間は BOT も表示(BOT への評価はランキングに反映しない)。評価中は名前を隠す。[ADR 0007](docs/adr/0007-contest.md)
- **再訪の仕掛け**: ドロップ表に「季節」「時間帯(朝/昼/夕/夜)」「解放に必要な訪問日数」を設定でき、同じシンボルでも来るたびに中身が変わる。シンボルごとにクールダウン(既定 20 時間)。
- **クーポン**(`/rewards/coupons/`): 探索・実績で発行。引換コードは暗号化保存。店頭で「使う」を押すと使用済みスタンプ表示(二重使用不可)。
- **やりこみ実績**(`/rewards/achievements/`): 累計みっけ数、訪問スポット数、アイテム種類数、同一スポットの訪問日数、同一スポットで体験した季節数。
- **2 種類のシンボル**:
  - **QR シンボル**: 印刷して掲示する、中央に「み」ロゴ入りの QR 型シンボル
  - **画像シンボル**: スタッフが現地の看板・像・壁画などを**カメラで撮影して登録**(管理者の画面の「画像シンボルを登録」)。写真の中を**四角形で切り抜き**(斜めからの写真も正面に補正)、人や空など**判定しない部分はマウス・指で塗りつぶして除外**、**正面・右から・左から・斜め上からなど最大 9 角度**を登録できる。利用者が実物を写し、登録した見え方と**類似度 65% 以上**なら AR マークが現れる。掲示物は不要。仕組みと検証結果は [ADR 0005](docs/adr/0005-image-symbols.md)
- **スポット地図**(「みっけ」画面の ①): **Protomaps** のタイルを**ローカルで配信**(大阪府 京橋付近を収録、外部の地図 API は不使用)。スポットのピン・ポップアップ・現在地表示。「近くのシンボルを探す」で周囲のシンボルを★で表示し、タップすると**ここで獲得可能なコーデの画像**と条件(季節・時間帯・訪問日数)が見られる。[ADR 0006](docs/adr/0006-local-protomaps.md)、データの作り直しは [maps/tiles/README.md](maps/tiles/README.md)
- **GPS によるカメラ起動判定**: 現在地の周囲 100m(管理画面「サイト設定」で 10〜5000m に変更可)にシンボルがあるときだけカメラを起動。ないときは「ここにはなさそう・・・」と表示。位置情報は判定だけに使い、保存しない。[ADR 0009](docs/adr/0009-spot-period-and-gps-gate.md)
- **シークレットシンボル**: 地図では「？」の画像だけを表示し、名前・ヒント・手に入るコーデは見つけるまで秘密。
- **3 つの権限と、完全に分けた画面**([ADR 0010](docs/adr/0010-roles-and-analytics.md)・[ADR 0013](docs/adr/0013-console-separation-and-coupon-amounts.md)):
  - **利用者**: みっけを楽しむ。自分で登録し、「アカウント」から自分で退会できる
  - **管理者**(店舗・会社の担当者): ログインすると**管理者コンソール**(`/manage/`、利用者とは別の見た目・左メニュー)に入る。ホームで担当スポットの利用状況(直近 30 日)と**クーポンの使用枚数・金額**を確認し、**担当のスポット**とシンボルを設定。スポットの追加・編集・削除(地図で位置・**有効期限 / 無期限**)、QR シンボルの追加と印刷、画像シンボルの撮影登録、**シンボルの設定とドロップ(手に入るコーデ・クーポン)**、**クーポンの登録**(内容・**1 枚あたりの金額**・有効期限。クーポンごとに ID `CP-xxxxxx`、配る 1 枚ごとに重ならない引換コードが付き、1 回だけ使える)、**クーポンの実績**(配布・使用枚数・使用率・使用金額・月別グラフ)。利用者の画面(きせかえ・みっけ など)は開けない。管理者 ID(`MK-xxxxxx`)・会社/店舗名・住所(暗号化)などの基本情報を持つ。サイト運営者が追加し、最初のログインでパスワード変更
  - **サイト運営者**: **専用のログイン画面**(`/ops/login/`、`.env` の `MIKKE_OPS_URL` で変更可)と**専用のセッション Cookie**(運営者の画面と Django 管理画面でしか使われない。運営者のまま利用者の画面には入れない)。**運営コンソール**で、**分析**(スポットごとの付近に来たユーザ・PV・カメラ起動・コーデ獲得・**利用割合 = 獲得 ÷ 付近 × 100%**、時間帯・季節別の棒グラフ)、**店舗ごとのクーポン利用**(使用枚数・使用金額)、**利用者管理**(追加できるのは管理者だけ・停止/再開)、すべてのスポット・シンボル・クーポンの設定と担当の割り当て、アイテム一覧、Django 管理画面(`DJANGO_ADMIN_URL`)
- **分析用デモデータ**: `python manage.py seed_analytics` で架空のスポット 100・管理者 12・仮想利用者 1,000 人・1 年分の行動と、店舗ごとのクーポンの配布・使用を投入(DEBUG 時のみ)。確認用に管理者 `manager@test.com`・利用者 `user@test.com` も作成(パスワードは実行のたびにランダムな仮パスワードを生成してコマンドの出力に 1 度だけ表示。初回ログインで変更が必要。固定パスワードは使わない。これらは本番 DB に残さないこと: `manage.py check --deploy` が残存を検出する)

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

### nginx 経由の HTTPS で動かす(https://localhost:8000)

```
ブラウザ ──https://localhost:8000── nginx ──http://127.0.0.1:8080── waitress + Django
```

アプリ本体は 127.0.0.1:8080 だけで待ち受け、nginx が TLS の終端・http→https の転送・静的ファイルの配信・接続数と頻度の上限・`X-Forwarded-For` の上書き(偽装防止)を受け持ちます(設計の理由は [ADR 0012](docs/adr/0012-local-https-reverse-proxy.md))。

1. nginx for Windows を `%LOCALAPPDATA%\nginx-1.28.0` に展開する(別の場所なら `.env` に `NGINX_HOME`)
2. `.env` に次を書く(`DJANGO_DEBUG=0` のとき): `DJANGO_BEHIND_TLS_PROXY=1`、`DJANGO_SSL_REDIRECT=1`、`DJANGO_SECURE_COOKIES=1`、`DJANGO_HSTS_SECONDS=0`、`MIKKE_TRUSTED_PROXIES=127.0.0.1`、`MIKKE_CACHE=db`
3. 起動(Ctrl+C で nginx も止まる。静的ファイルの収集・証明書の作成も自動)

```bash
.venv\Scripts\python.exe scripts\devproxy.py run
```

- 証明書は `localhost` / `127.0.0.1` / `::1` 専用の自己署名(ECDSA、1 年、認証局としては使えない)で、`%LOCALAPPDATA%\mikke\proxy\certs` に作られます(リポジトリには入りません)。作り直しは `scripts\devproxy.py cert`
- **ブラウザの警告を消すには、証明書を自分のユーザーの「信頼されたルート証明機関」に登録します**(システムの設定変更なので各自で実行してください。不要になったら `certmgr.msc` から削除できます):

```bash
certutil -user -addstore Root "%LOCALAPPDATA%\mikke\proxy\certs\localhost.crt"
```

- nginx だけの起動・停止・状態: `scripts\devproxy.py start` / `stop` / `status`。ログは `%LOCALAPPDATA%\mikke\proxy\logs`(アクセスログにクエリ文字列は残しません)

### 公開・デモ・本番で動かすとき(必ず確認)

- **`.env` の `DJANGO_DEBUG=0` にする。** DEBUG のままだと 404 などのエラー画面に内部の URL 構成(管理画面の場所など)が表示されます。DEBUG のときは画面上部に赤い警告帯が出ます。
- **複数のプロセス・サーバーで動かすときは `MIKKE_CACHE` を設定する。** 既定のメモリキャッシュは 1 プロセスの中だけで有効なため、レート制限・ログインのロック・「こんな人が獲得しているよ」の表示 ID がプロセスごとにばらばらになります。`MIKKE_CACHE=db`(`python manage.py createcachetable` が必要)か `MIKKE_CACHE=redis://…` にしてください。
- **リバースプロキシ(ロードバランサー)の内側で動かすときは `MIKKE_TRUSTED_PROXIES` にプロキシの IP / CIDR を書く。** そのときだけ `X-Forwarded-For` から接続元 IP を取ります(書かないと全員がプロキシの IP に見え、IP 単位のロックで全員がログインできなくなるおそれがあります)。IP 単位のロックはアカウント単位(5 回)より緩い 20 回です(`MIKKE_LOGIN_MAX_FAILURES_PER_IP`)。
- パスワードを忘れた人の問い合わせ先を `MIKKE_SUPPORT_CONTACT` に書く(ログイン画面の「パスワードを忘れた方」に表示)。運営者が本人確認のうえ「利用者管理 > 仮パスワード」で発行します。
- 地図の範囲・タイル(`MIKKE_MAP_BOUNDS` など)、スポットのカード一覧の表示(`MIKKE_SHOW_SPOT_CARDS`)も `.env` で変えられます(`.env.example` 参照)。

### スマートフォンで試すには

カメラ API は「安全なコンテキスト」(HTTPS または localhost)でのみ動きます。PC の localhost では動作しますが、スマホから LAN 経由で開く場合は HTTPS 化が必要です。上の nginx 構成は 127.0.0.1 だけで待ち受けるため、LAN に公開するには listen と証明書の SAN を変える必要があります(公開範囲が広がるので要検討)。

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
core/        横断機能: 暗号化・監査ログ・レート制限・権限・ID 生成・接続元 IP・季節/時間帯・UI テーマ・ホーム・シードコマンド
accounts/    アカウント (利用者 / 管理者 / サイト運営者)、管理者の基本情報、登録・ログイン・退会
explore/     スポット・シンボル (QR / 画像・最大 9 角度)・ドロップ・訪問/みっけ記録、読み取り/受け取り/近くの判定 API、
             みっけ仲間、スポット・シンボル・クーポンの設定画面
wardrobe/    アイテム、所持品、アバター設定、SVG アバター描画
rewards/     クーポン (ひな形・発行・使用)、実績
contest/     コーデコンテスト (エントリー・評価・ランキング・BOT)
maps/        地図タイル (PMTiles) の Range 配信、tiles/kyobashi.pmtiles
ops/         サイト運営者: 専用ログイン・分析・店舗ごとのクーポン利用・利用者管理
templates/   画面テンプレート (アプリごと、includes/ は共通部品)
static/      css/ (themes/)、js/ (カメラ・地図・結果画面など)、img/、vendor/ (同梱ライブラリ)
scripts/     ローカル PostgreSQL 管理、nginx + HTTPS の起動 (devproxy.py)、地図タイル切り出し、仮想写真の生成
deploy/      nginx の設定ひな形
docs/        設計書・要件・API・ADR・評価レポート
<app>/tests/ 各アプリのテスト (test_*.py)
```

## ドキュメント

- **[設計書](docs/design.md)**(全体構成・権限・機能・データ・API・セキュリティ・運用)
- [ドキュメント一覧](docs/README.md)(要件とトレーサビリティ・API 仕様・ADR 0001〜0011・評価レポート)

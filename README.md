# みっけ (Mikke)

観光地にかくれた **みっけシンボル** をスマホのカメラでのぞくと、映像の上に光るマークが現れる(疑似AR)。
タップするとアバターの服・髪型や地域のクーポンが手に入る。
**季節・時間帯・再訪日数で出会えるものが変わる** ため、「一度行けば終わり」のスタンプラリーと違い、何度も訪れたくなる体験を目指す Web アプリです。

| 技術 | 内容 |
|---|---|
| サーバー | Python 3.13 / Django 6.1(ローカルホスト) |
| DB | PostgreSQL 17(TLS 1.3 必須・SCRAM 認証・データチェックサム有効)/ 代替として SQLite |
| 暗号化 | AES-256-GCM のフィールド暗号化 + HMAC ブラインドインデックス(`core/crypto.py`) |
| フロント | Django テンプレート + 素の JavaScript。QR 検出に jsQR 1.4.0(同梱・integrity 検証済み) |

## 主な機能

- **疑似ARカメラ探索**(`/explore/camera/`): カメラ映像を canvas に描画し、シンボルを検出すると位置に追従する光るマークを重ねる。マーク(または同じ動作のボタン)をタップで受け取り。映像はサーバーに送らない。カメラが使えない場合は「写真から読み取る」でも可。
- **アバター着せ替え**(`/wardrobe/`): 髪・トップス・ボトムス・くつ・こもの の5部位 + 肌の色(8種、ファンタジー色含む)。性別の選択は求めない。
- **再訪の仕掛け**: ドロップ表に「季節」「時間帯(朝/昼/夕/夜)」「解放に必要な訪問日数」を設定でき、同じシンボルでも来るたびに中身が変わる。シンボルごとにクールダウン(既定 20 時間)。
- **クーポン**(`/rewards/coupons/`): 探索・実績で発行。引換コードは暗号化保存。店頭で「使う」を押すと使用済みスタンプ表示(二重使用不可)。
- **やりこみ実績**(`/rewards/achievements/`): 累計みっけ数、訪問スポット数、アイテム種類数、同一スポットの訪問日数、同一スポットで体験した季節数。
- **運営向け**: Django 管理画面(URL は `.env` の `DJANGO_ADMIN_URL`)でスポット・シンボル・ドロップ・アイテム・クーポン・実績を管理。`/explore/symbols/print/` で掲示用シンボルを印刷。

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
explore/     スポット・シンボル・ドロップ表・訪問記録・みっけ記録、スキャン/受け取り API
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
- [API 仕様](docs/api.md)

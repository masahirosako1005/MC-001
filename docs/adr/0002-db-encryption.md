# ADR 0002: DB 暗号化とセキュリティ強化

- 状態: 採用
- 日付: 2026-11-09
- 参照: OWASP ASVS 5.0 L2 [S21]、OWASP Top 10:2025「暗号化の失敗」[S22]、OWASP Password Storage Cheat Sheet [S24]、NIST SP 800-63B [S25]

## 背景

要求「DB の暗号化を行い、セキュリティ強化をすること」。コミュニティ版 PostgreSQL には透過的データ暗号化(TDE)がないため、多層で対策する。

## 決定

### 1. アプリケーション層のフィールド暗号化(保存データ)
- `core/crypto.py` / `core/fields.py` の `EncryptedTextField` で **AES-256-GCM**(認証付き暗号)
- 保存形式 `enc:<鍵ID>:<base64(nonce12B + 暗号文 + タグ)>`。nonce は毎回ランダム
- **AAD に「モデル.フィールド」を含める** → 暗号文を別カラムへ移し替えても復号できない
- **鍵ローテーション**: `MIKKE_FIELD_KEYS="2:新鍵,1:旧鍵"` で旧鍵でも復号、新規は先頭鍵で暗号化
- 対象: 利用者のメールアドレス、クーポン引換コード
- 暗号化フィールドに対する検索は `FieldError` で禁止(誤った平文比較を防ぐ)

### 2. ブラインドインデックス(検索用)
- メールアドレスは NFC 正規化・小文字化してから **HMAC-SHA256**(暗号鍵とは別の鍵)で `email_hash` に保存し、ログイン照合と一意制約に使う

### 3. 通信路の暗号化と DB サーバーの堅牢化(`scripts/localdb.py`)
- `ssl=on`、`ssl_min_protocol_version=TLSv1.3`、`pg_hba.conf` は `hostssl` のみ(平文 TCP は拒否)
- 認証は `scram-sha-256` のみ。`listen_addresses='localhost'`
- `initdb --data-checksums` でページ破損を検知
- アプリ用ロール `mikke_app` は非スーパーユーザー(テスト DB 作成のため CREATEDB のみ付与。本番では外す)
- Django 側は `sslmode=require`

### 4. 収集しない・残さない(データ最小化)
- 位置情報は判定にだけ使い保存しない。監査ログの IP は HMAC 化して保存
- 登録項目はニックネーム・メール・パスワードのみ(性別・本名なし)

### 5. その他のアプリ対策
- パスワード: Argon2id、15 文字以上、よく使われるパスワードを拒否。連続 5 回失敗で 15 分ロック(アカウント単位 + IP 単位)
- CSP(Django 6 標準)で `script-src 'self'`、インライン script/style なし。`frame-ancestors 'none'`、Permissions-Policy でカメラ・位置情報を自オリジンのみに
- Cookie: HttpOnly / SameSite=Lax / 本番は Secure。CSRF トークンは `<meta>` 経由
- 認可は全てサーバー側で所有者照合(IDOR 対策)、API はレート制限
- 監査ログ(追記のみ)に登録・ログイン・失敗・受け取り・クーポン使用・着せ替えを記録
- 秘密値は `.env`(gitignore 済み)にランダム生成。管理画面 URL もランダム化

## 結果・トレードオフ

- 暗号化フィールドは DB 側で検索・並び替えできない(必要なものだけを対象にした)
- 鍵を失うと復号不能 → `.env` のバックアップを DB バックアップと**別の場所**に保管すること
- ディスク全体の暗号化(BitLocker 等)とバックアップファイルの暗号化は OS / 運用側で実施する(未実施・要対応)
- `HSTS preload` は取り消しが難しいため無効のまま(本番ドメイン確定後に判断)

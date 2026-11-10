# ADR 0012: nginx のリバースプロキシと自己署名証明書でローカルを HTTPS にする

- 状態: 採用
- 日付: 2026-11-09

## 背景
- 外部には公開しないが、本番に近い形 (DEBUG=0・HTTPS・Secure Cookie) で動かして確認したい
- `runserver` は開発用で、TLS も、接続数や遅いリクエストへの備えもない
- アプリを `localhost:8080`、nginx を `localhost:8000` にして、nginx 経由で配信したい

## 決定
- **構成**: ブラウザ ─ `https://localhost:8000` ─ nginx ─ `http://127.0.0.1:8080` ─ waitress + Django
  - アプリ本体は waitress (pure-python の WSGI サーバー。アプリ制御ポリシーで `.exe` が拒否される環境でも `python` から動く) で **127.0.0.1 だけ**で待ち受ける
  - nginx も **127.0.0.1 だけ**で待ち受ける (LAN からは届かない)
  - 起動・停止は `scripts/devproxy.py` (`run` / `start` / `stop` / `status` / `cert`)。設定は `deploy/nginx/nginx.conf.template` から生成する
- **証明書**: 認証局は使わず、`cryptography` で **localhost 専用の自己署名証明書**を作る
  - ECDSA P-256・1 年・SAN は `localhost` / `127.0.0.1` / `::1` だけ
  - `BasicConstraints CA:false`・`KeyUsage digitalSignature` のみ・`EKU serverAuth` のみ。利用者が信頼済みに登録しても、ほかのサイトの証明書を作る認証局としては使えない (mkcert のようにローカル CA を信頼させる方式より影響範囲が狭い)
  - 鍵と証明書は `%LOCALAPPDATA%\mikke\proxy\certs` に置き、リポジトリに入れない
  - 信頼済みへの登録はシステムの設定変更なので、スクリプトでは行わず利用者が自分で実行する (README)
- **nginx が受け持つこと**
  - TLS 1.2 / 1.3 の終端、同じポートへの http を https に転送 (`error_page 497`)
  - `X-Forwarded-For` を `$remote_addr` で**上書き**する (クライアントが送った値を引き継がない = 接続元 IP を偽装できない)、`X-Forwarded-Proto: https` を付ける
  - 静的ファイル (`collectstatic` の結果) の配信、版番号を出さない (`server_tokens off`)
  - 接続数・頻度の上限 (超えたら 429)、本文 20MB まで、遅いリクエストの打ち切り
  - アクセスログにクエリ文字列を残さない
- **Django 側**
  - `DJANGO_BEHIND_TLS_PROXY=1` のときだけ `SECURE_PROXY_SSL_HEADER` を有効にする。プロキシなしで直接公開したときに `X-Forwarded-Proto` を偽装されないよう、既定は無効
  - waitress は既定で `X-Forwarded-*` を消すため `clear_untrusted_proxy_headers=False` で渡す。信じるかどうかは Django 側 (`SECURE_PROXY_SSL_HEADER` と `MIKKE_TRUSTED_PROXIES=127.0.0.1`) の 1 か所で決める
  - HSTS は `DJANGO_HSTS_SECONDS` で変えられるようにし、localhost では 0 にする。HSTS はポートを問わずホスト全体に効くため、ほかのローカル開発 (http://localhost:3000 など) まで https を強制されてしまう

## 結果
- ブラウザとの通信が暗号化され、Secure Cookie・HTTPS リダイレクトなど本番と同じ設定で確認できる。カメラ API の安全なコンテキストの条件も満たす
- アプリ本体に直接届くのは同じ PC の中からだけになる
- 証明書を信頼済みに登録するまで、ブラウザは警告を出す
- スマホなど LAN 内の端末からは使えない。使う場合は listen アドレスと SAN を変える必要があり、公開範囲が広がるので別途検討する

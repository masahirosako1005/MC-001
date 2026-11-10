# ドキュメント一覧

| ドキュメント | 内容 |
|---|---|
| [overview.md](overview.md) | **概要**(何のアプリか・使う人・主な機能・しくみ・セキュリティ・起動・制約を 1 枚で) |
| [設計書.md](../設計書/設計書.md) | **設計書**(全体構成・権限・機能・データ・API・フロントエンド・セキュリティ・運用) |
| [requirements.md](requirements.md) | 要件(R1〜)と実装・テストの対応表(トレーサビリティ) |
| [api.md](api.md) | JSON API・画像エンドポイントの仕様 |
| [adr/](adr/) | 設計判断の記録(ADR 0001〜0015) |
| [reviews/](reviews/) | 評価レポートと対応状況 |

## ADR
| # | タイトル |
|---|---|
| [0001](adr/0001-symbol-detection.md) | シンボル検出方式 |
| [0002](adr/0002-db-encryption.md) | DB 暗号化 |
| [0003](adr/0003-revisit-design.md) | 再訪を促すゲーム設計 |
| [0004](adr/0004-avatar-rendering.md) | アバターの描画方式 |
| [0005](adr/0005-image-symbols.md) | 画像シンボル(撮影した写真をシンボルにする) |
| [0006](adr/0006-local-protomaps.md) | 地図は Protomaps のタイルをローカル配信 |
| [0007](adr/0007-contest.md) | コーデコンテスト |
| [0008](adr/0008-ui-themes.md) | UI テーマ(デザイン案)の切り替え |
| [0009](adr/0009-spot-period-and-gps-gate.md) | スポットの公開期間・GPS によるカメラ起動判定・シークレットシンボル・「みっけ」と「スポット」の統合 |
| [0010](adr/0010-roles-and-analytics.md) | 権限の分離(利用者・管理者・サイト運営者)と運営向け分析 |
| [0011](adr/0011-recent-finders-and-coupons.md) | 「こんな人が獲得しているよ」・管理者のクーポン登録・衣装全振り |
| [0012](adr/0012-local-https-reverse-proxy.md) | nginx のリバースプロキシと自己署名証明書でローカルを HTTPS にする |
| [0013](adr/0013-console-separation-and-coupon-amounts.md) | 利用者 / 管理者 / サイト運営者の画面とセッションの分離・クーポンの使用金額 |
| [0014](adr/0014-public-ranking-and-signage.md) | 「こんな人も獲得しているよ」・ログイン画面のランキング・まちのサイネージ・静的ファイルのハッシュ名 |
| [0015](adr/0015-revisit-rate-and-app-usage.md) | 再訪率 (みっけ・クーポン利用の日数) とアプリ利用率 (日ごと)・1 万人のデモデータ |

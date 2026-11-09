# 要件とトレーサビリティ

優先度は MoSCoW [S4]。状態: ✅ 達成(自動テストあり)/ 🔶 達成(手動確認のみ)/ ⬜ 未達

## 要件一覧

| ID | 優先 | 要件(受け入れ基準 Given/When/Then の要約) |
|---|---|---|
| R1 | Must | Python + Django、ローカルホストで動く |
| R2 | Must | DB は PostgreSQL(使えない場合は SQLite で代替可) |
| R3 | Must | アプリ名「みっけ」。観光地の再訪を促し、スタンプラリーと差別化する |
| R4 | Must | 疑似ARのカメラ探索: カメラ映像上でシンボル(画像)を検知すると印を表示 |
| R5 | Must | 印をタップするとアイテムが手に入る |
| R6 | Must | アバターに髪・服・ズボン・靴などを着せ替えられる(手に入れた物のみ) |
| R7 | Must | 探索でクーポンが得られる |
| R8 | Must | やりこみによる報酬(実績)がある |
| R9 | Must | DB を暗号化しセキュリティを強化する |
| R10 | Should | カメラが使えない人・状況への代替手段 |
| R11 | Should | 運営がスポット・シンボル・報酬を管理し、シンボルを印刷できる |
| R12 | Should | 不正取得の抑止(二重取得、なりすまし、遠隔取得) |

## トレーサビリティ

| 要件 | 実装 | テスト | 状態 |
|---|---|---|---|
| R1 | `config/`, `manage.py`, `.claude/launch.json` | 全テスト(`manage.py test`) | ✅ |
| R2 | `config/settings.py`(`DB_ENGINE`)、`scripts/localdb.py` | 全テストを PostgreSQL 17 で実行 | ✅ |
| R3 | `explore/models.py` DropEntry(季節・時間帯・`min_visit_days`)、SpotVisit、クールダウン | `explore/tests.py` `test_season_and_slot_filter` `test_revisit_unlock` `test_visit_days_counted_per_local_day` `test_cooldown_*` | ✅ |
| R4 | `static/js/camera.js`、`explore/symbols.py`、`explore/services.py:scan` | `test_scan_ready_then_cooldown` `test_parse_payload` `test_scan_and_collect_flow`、ブラウザで検出→マーク表示を確認 | ✅(検出は🔶手動) |
| R5 | `camera.js:collect`、`explore/services.py:collect`、`/explore/api/collect` | `test_collect_grants_item_and_records` `test_idempotent_replay` | ✅ |
| R6 | `wardrobe/`(avatar.py, services.equip, views) | `wardrobe/tests.py` 全般 | ✅ |
| R7 | `rewards/services.issue_coupon`、DropEntry.coupon、`rewards/views` | `test_coupon_drop`、`rewards/tests.py` | ✅ |
| R8 | `rewards/models.Achievement`、`services.evaluate_achievements` | `test_achievement_unlocked_once` | ✅ |
| R9 | `core/crypto.py`、`core/fields.py`、`scripts/localdb.py`(TLS/SCRAM)、settings のセキュリティ設定 | `core/tests.py`(暗号文で保存・改ざん検知・AAD・鍵ローテーション・ヘッダー)、`accounts/tests.py`(Argon2・ロック・CSRF) | ✅ |
| R10 | 「写真から読み取る」、マークと同じ動作のボタン、`prefers-reduced-motion` | ブラウザで写真読み取りを確認 | 🔶 |
| R11 | 各 `admin.py`、`/explore/symbols/print/`、`seed_mikke`、`createadmin` | `test_symbol_print_staff_only` | ✅ |
| R12 | 署名付きチケット、Idempotency-Key、行ロック、クールダウン、位置情報判定、レート制限 | `test_ticket_bound_to_user` `test_forged_ticket_rejected` `test_expired_ticket_rejected` `test_location_required` `test_rate_limit` | ✅ |

## 未達・残課題

- 実機スマートフォンでのカメラ検出は未確認(PC ブラウザで写真読み取り経路のみ確認)。スマホから試すには HTTPS 化が必要
- スクリーンリーダーでの手動確認、axe による自動チェックは未実施
- 画面文言の i18n 外部化(`{% translate %}`)は未対応(日本語のみ)
- ディスク暗号化・バックアップ暗号化は OS / 運用側で要対応

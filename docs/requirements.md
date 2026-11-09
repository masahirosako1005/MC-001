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
| R13 | Must | スタッフがカメラで撮影した写真をシンボルとして登録でき、利用者のカメラがその実物(QR ではない画像)を検出して印を表示する |
| R14 | Must | シンボルは写真全体ではなく、四角形で囲んだ部分だけを使う |
| R15 | Must | 距離・角度は厳密に判定せず、類似度おおむね 65% 以上で一致とする |
| R16 | Must | 判定しない部分をマウスで塗りつぶして除外できる |
| R17 | Must | 1 つのシンボルを最大 9 角度(正面を含む)で登録できる |
| R18 | Must | Protomaps を実装する。API は使わず、京橋付近のタイルデータでローカル動作させる |
| R19 | Must | アバターを参考画像のようなかわいいデザインにする |
| R20 | Must | 女性だけでなく男性のアバターも用意する |
| R21 | Must | サンプルパーツを男女別に 50 種類ずつ用意する |
| R22 | Must | 管理者は(パーツを)自由に選択できる |

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
| R12 | 署名付きチケット、Idempotency-Key、行ロック、クールダウン、位置情報判定、レート制限、画像シンボルの照合用パッチ(サーバーのみ保持) | `test_ticket_bound_to_user` `test_forged_ticket_rejected` `test_expired_ticket_rejected` `test_location_required` `test_rate_limit` `test_scan_with_wrong_patch` `test_catalog_does_not_leak_secrets` | ✅ |
| R13 | `explore/image_symbols.py`、`services.register_image_symbol / scan_image`、`/explore/symbols/register/`、`static/js/imagematch.js`(jsfeat)、`symbol_register.js`、`camera.js:detectImage` | `explore/tests_image.py`、ブラウザで登録 → 合成した街の写真から検出 → 受け取り | ✅(検出精度は🔶手動・実機未確認) |
| R14 | `imagematch.js:cropQuad`(射影変換で正面補正)、`symbol_register.js`(4 隅ドラッグ・矢印キー) | ブラウザで 4 隅のドラッグと切り抜きを確認 | 🔶 |
| R15 | `image_symbols.similarity`(16×16・位置ずれ ±1 マス・最大 NCC)、`MIKKE_IMAGE_SIMILARITY_THRESHOLD=0.65`、端末側の照合条件の緩和 | `SimilarityTests`(位置ずれ許容・無関係は 65% 未満・しきい値変更)、ブラウザで距離・角度を変えた 44 回の検証(ADR 0005) | ✅ |
| R16 | `symbol_register.js`(ブラシ・消しゴム・全消去)、`imagematch.js:extractReference / packMask32`、`SymbolView.verify_mask` | `test_masked_area_is_ignored` `test_too_much_masked` `test_register_multi_angle_with_mask`、ブラウザで塗った部分の特徴点が消えることを確認 | ✅ |
| R17 | `SymbolView`(9 角度・一意制約)、`save_symbol_views`、`/explore/symbols/<id>/views/` | `test_nine_angles_max` `test_save_views_add_replace_delete` `test_cannot_delete_last_view` `test_edit_views` `test_scan_matches_any_registered_angle` | ✅ |
| R19 | `wardrobe/avatar.py`(ちびキャラ風テンプレート・大きな瞳・目の色) | `AvatarRenderTests` `BodyTypeRenderTests`、ブラウザで 100 パーツ全部の見た目を確認 | ✅(見た目は🔶) |
| R20 | `AvatarConfig.body_type`、`Item.body_type`、着せ替え画面のタイプ切り替え | `test_user_can_switch_body_type_freely` `test_user_cannot_wear_other_type_item` `test_starter_kit_matches_body_type` | ✅ |
| R21 | `wardrobe/sample_items.py`(女の子用 50・男の子用 50)、`seed_mikke` | `test_fifty_each_and_valid` | ✅ |
| R22 | `services.can_use_any_item / selectable_items / equip`、`/wardrobe/catalog/` | `test_staff_can_choose_any_item` `test_wardrobe_page_lists_by_role` `test_staff_preview_and_item_svg_for_unowned` `test_catalog_staff_only`、ブラウザで未所持・別タイプのパーツを管理者で保存 | ✅ |
| R18 | `maps/`(Range 配信)、`maps/tiles/kyobashi.pmtiles`、`scripts/extract_tiles.py`、`static/js/spotmap.js`(Leaflet + protomaps-leaflet) | `maps/tests.py`(Range・416・パストラバーサル・ログイン必須・外部 API を CSP で許可していない)、ブラウザで外部への通信がないことを確認 | ✅ |

## 未達・残課題

- 実機スマートフォンでのカメラ検出は未確認(PC ブラウザで写真読み取り経路のみ確認)。スマホから試すには HTTPS 化が必要
- 画像シンボルの実写での検出率(照明・距離・角度別)は未計測(合成写真での結果は ADR 0005)。看板が画面の 1/6 未満・逆光・大きく遮られた状態は苦手
- 地図の収録範囲は京橋付近のみ。管理画面でスポットの座標を地図から選ぶ機能は未実装(緯度経度を数値で入力)
- スクリーンリーダーでの手動確認、axe による自動チェックは未実施
- 画面文言の i18n 外部化(`{% translate %}`)は未対応(日本語のみ)
- ディスク暗号化・バックアップ暗号化は OS / 運用側で要対応

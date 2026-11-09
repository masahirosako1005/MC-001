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
| R23 | Must | 目を顔に対して自然な大きさにする |
| R24 | Must | 顔パーツ(目・口などのセット)を増やす |
| R25 | Must | 背景を 20 種類程度用意する |
| R26 | Must | アバターの周りに動くエフェクト(キラキラ・ハートが浮かぶ等)を付けられる |
| R27 | Must | コンテスト ①エントリー ②評価モードへ遷移 ③3 体×3 回・各回 1 体まで高評価 |
| R28 | Must | コンテスト ④表示回数が少ないアバターを優先 ⑤10 人まで BOT を含む・以降は非表示・BOT 評価はランキング対象外 |
| R29 | Must | ログイン前・ログイン後・その他ページを含む UI 案を複数用意する |
| R30 | Must | ログイン前ページに Claude が生成した仮想の写真画像を使う |
| R31 | Must | UI 案を管理画面から切り替えられる |
| R32 | Must | 参考画像のように 1 画面でまとまった UI を試しに実装する |
| R33 | Must | シンボルが存在するスポットの追加・編集・削除。各スポットに有効期限(無期限も可)を設定できる |
| R34 | Must | GPS で周囲 100m(設定画面で変更可)にシンボルがあるときだけカメラを起動。ないときは「ここにはなさそう・・・」と表示して起動を防ぐ |
| R35 | Should | 地図上で周囲のシンボルをタップすると、ここで獲得可能なコーデの画像を表示 |
| R36 | Must | シークレットシンボルを設定でき、R35 の画像はあえて「？」の画像を表示 |
| R37 | Must | シンボルをタップしたとき、何を手に入れたかを画像で表示する |

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
| R23 | `avatar._eye`(約 65% の面積に縮小) | `test_eyes_are_natural_size`、ブラウザで確認 | ✅ |
| R24 | `avatar.FACE`(12 種類)、`AvatarConfig.face` | `test_all_faces_backgrounds_effects_render`、`CommonItemsTests` | ✅ |
| R25 | `scenes.BACKGROUND`(20 種類)、`AvatarConfig.background` | 同上、ブラウザで全 20 種類を確認 | ✅ |
| R26 | `scenes.EFFECT`(10 種類、SVG の CSS アニメーション)、`AvatarConfig.effect` | `test_effect_is_animated_and_respects_reduced_motion`、ブラウザで 2 コマ比較し動作を確認 | ✅ |
| R27 | `contest/`(`enter` / `current_round` / `vote`、評価画面) | `EntryTests` `EvaluationTests` `test_full_flow_via_http`、ブラウザでエントリー→3 回評価→ランキングを確認 | ✅ |
| R28 | `contest.services.pick_candidates / bots_visible`、`vote` の BOT 除外 | `SelectionTests`(低表示回数優先・偏り 2 以内・層内ランダム)、`BotTests`(9 人で BOT あり・10 人で BOT なし・BOT 評価は加算しない) | ✅ |
| R29 | `core/themes.py`(4 案)、`static/css/themes/*.css`、`templates/core/landing_* / home_*` | `test_each_theme_switches_landing_home_and_css`、ブラウザで 4 案のログイン前・ホーム・きせかえを確認 | ✅(見た目は🔶) |
| R30 | `static/img/photos/*.svg`(`scripts/make_photos.py`)、各ログイン前テンプレート | `test_landing_uses_virtual_photos_with_disclaimer` `test_photos_exist_and_are_safe_svgs` | ✅ |
| R31 | `core.models.SiteSetting`、`SiteSettingAdmin`、`UiThemeMiddleware`(管理者の試し見) | `test_admin_switches_theme_for_everyone` `test_staff_can_preview_only_for_themselves` `test_non_staff_cannot_preview` `test_admin_singleton`、ブラウザで管理画面から切り替えを確認 | ✅ |
| R32 | `templates/core/home_game.html`、`themes/game.css`、`/wardrobe/me.svg?layer=` | `test_game_home_is_one_screen_with_status` `test_avatar_layers`、ブラウザでスクロールなし(縦 812 = 画面 812)を確認 | ✅ |
| R33 | `Spot.starts_at / expires_at`、`spot_available_q`、`explore/manage_views.py`、`SpotForm`、`templates/explore/manage/`、`static/js/spotpicker.js` | `SpotPeriodTests`(期限切れはどこからも見えない・無期限・制約)、`SpotManageTests`(スタッフのみ・無期限・期限付き・入力チェック・記録があると削除不可→非公開/期限切れ) | ✅ |
| R34 | `SiteSetting.camera_radius_m`、`/explore/api/nearby`、`services.nearby_symbols`、`camera.js:gpsGate` | `NearbyApiTests`(範囲内・範囲外といちばん近いスポット・設定変更・不正入力・GET 不可・レート制限・位置を記録しない)、`SiteSettingRadiusTests`、`test_admin_switches_theme_for_everyone`(距離の変更) | ✅ |
| R35 | `services.obtainable_items`、`/explore/symbols/<id>/items/<code>.svg`、`spotmap.js`(★マーカー・ポップアップ・一覧) | `test_within_radius` `test_preview_image` `test_secret_and_unrelated_items_are_404` | ✅ |
| R36 | `Symbol.is_secret`、`static/img/secret.svg`、API でのマスク、スポット一覧の「？？？」 | `test_secret_is_masked`(名前・ヒント・アイテムを応答に含めない) `SecretSpotListTests` | ✅ |
| R37 | `camera.js:showReward`(全身 + 拡大図・NEW・レア度)、`wardrobe.services.item_zoom_svg`(`?zoom=1`)、`rewards/coupon_art.py` + `/rewards/coupons/<id>.svg`、`static/img/nothing.svg` | `test_collect_grants_item_and_records`(`slot`) `test_item_zoom_crops_to_part` `CouponImageTests`(本人のみ・XSS エスケープ・使用済み・長文の切り詰め)、ブラウザで実際にみっけ → アイテムの絵、クーポン・何もなしの絵を確認 | ✅ |
| R18 | `maps/`(Range 配信)、`maps/tiles/kyobashi.pmtiles`、`scripts/extract_tiles.py`、`static/js/spotmap.js`(Leaflet + protomaps-leaflet) | `maps/tests.py`(Range・416・パストラバーサル・ログイン必須・外部 API を CSP で許可していない)、ブラウザで外部への通信がないことを確認 | ✅ |

## 未達・残課題

- 実機スマートフォンでのカメラ検出は未確認(PC ブラウザで写真読み取り経路のみ確認)。スマホから試すには HTTPS 化が必要
- 画像シンボルの実写での検出率(照明・距離・角度別)は未計測(合成写真での結果は ADR 0005)。看板が画面の 1/6 未満・逆光・大きく遮られた状態は苦手
- 地図の収録範囲は京橋付近のみ(範囲外のスポットは緯度経度を数値で入力)
- シンボル個別の位置は Django 管理画面で数値入力(地図で選ぶのはスポットのみ)。有効期限はスポット単位
- GPS 判定は実機未確認(ブラウザで位置を模擬して確認)。屋内など精度が悪い場所では判定距離の調整が必要
- スクリーンリーダーでの手動確認、axe による自動チェックは未実施
- 画面文言の i18n 外部化(`{% translate %}`)は未対応(日本語のみ)
- ディスク暗号化・バックアップ暗号化は OS / 運用側で要対応

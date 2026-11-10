"""利用者 / 管理者 / サイト運営者の画面の分離 (セッション・画面) と、クーポンの使用枚数・金額のテスト。"""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.urls import reverse
from django.utils import timezone

from core.testing import ops_login
from rewards import stats
from rewards.models import CouponTemplate, UserCoupon
from rewards.services import issue_coupon, use_coupon

from .test_ops import PW, Base


class SessionSeparationTests(Base):
    def test_operator_and_user_sessions_are_independent(self):
        # 同じブラウザで、運営側は運営者・利用者側は利用者としてログインしておける
        self.client.post(reverse("ops:login"), {"username": "op@example.com", "password": PW})
        self.client.post(reverse("accounts:login"), {"username": "u@example.com", "password": PW})
        user_key = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        ops_key = self.client.cookies[settings.OPS_SESSION_COOKIE_NAME].value
        self.assertNotEqual(user_key, ops_key)
        self.assertEqual(SessionStore(user_key).get("_auth_user_id"), str(self.user.pk))
        self.assertEqual(SessionStore(ops_key).get("_auth_user_id"), str(self.op.pk))
        self.assertEqual(self.client.get(reverse("wardrobe:index")).status_code, 200)  # 利用者として
        self.assertEqual(self.client.get(reverse("ops:dashboard")).status_code, 200)  # 運営者として
        # 運営側でログアウトしても、利用者側のログインはそのまま
        self.client.post(reverse("ops:logout"))
        self.assertTrue(self.client.get(reverse("ops:dashboard"))["Location"].startswith(reverse("ops:login")))
        self.assertEqual(self.client.get(reverse("wardrobe:index")).status_code, 200)

    def test_operator_session_left_on_user_side_is_discarded(self):
        # 以前の版で利用者側に残った運営者のログインは、利用者の画面を開くとログアウトさせて運営の画面へ
        self.client.force_login(self.op)
        res = self.client.get(reverse("core:home"))
        self.assertRedirects(res, reverse("ops:dashboard"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        api = self.client.post(reverse("explore:api_nearby"), "{}", content_type="application/json")
        self.assertIn(api.status_code, (401, 403))

    def test_non_operator_in_ops_session_is_logged_out(self):
        ops_login(self.client, self.manager)  # 通常は起きないが、運営側のセッションに運営者以外がいたら捨てる
        res = self.client.get(reverse("ops:dashboard"))
        self.assertTrue(res["Location"].startswith(reverse("ops:login")))

    def test_ops_forced_password_change_stays_on_ops_side(self):
        self.op.must_change_password = True
        self.op.save()
        ops_login(self.client, self.op)
        self.assertRedirects(self.client.get(reverse("ops:dashboard")), reverse("ops:password_change"))
        new = "another long passphrase 42"
        res = self.client.post(reverse("ops:password_change"),
                               {"old_password": PW, "new_password1": new, "new_password2": new})
        self.assertRedirects(res, reverse("ops:dashboard"))
        self.assertEqual(self.client.get(reverse("ops:dashboard")).status_code, 200)


class ManagerAreaTests(Base):
    def test_manager_login_goes_to_manager_home(self):
        res = self.client.post(reverse("accounts:login"), {"username": "m@example.com", "password": PW})
        self.assertRedirects(res, reverse("manage:home"))
        page = self.client.get(reverse("manage:home"))
        self.assertContains(page, "管理者コンソール")
        self.assertContains(page, "京橋商店")
        self.assertNotContains(page, 'class="tabbar"')  # 利用者のタブバー (きせかえ・みっけ…) は出さない
        self.assertNotContains(page, reverse("wardrobe:index"))

    def test_manager_cannot_open_user_features(self):
        self.client.force_login(self.manager)
        for name in ("core:home", "wardrobe:index", "explore:mikke", "contest:list", "rewards:coupons",
                     "accounts:account", "accounts:withdraw", "explore:history"):
            res = self.client.get(reverse(name))
            self.assertRedirects(res, reverse("manage:home"), fetch_redirect_response=False, msg_prefix=name)
        api = self.client.post(reverse("explore:api_nearby"), "{}", content_type="application/json")
        self.assertEqual((api.status_code, api.json()["error"]), (403, "wrong_area"))
        # パスワード変更・ログアウトは使える (管理者の画面の見た目で)
        page = self.client.get(reverse("accounts:password_change"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "管理者コンソール")

    def test_manager_pages_and_account(self):
        self.client.force_login(self.manager)
        for name in ("manage:home", "manage:account", "manage:spots", "manage:symbols", "manage:coupons",
                     "manage:coupon_stats"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        page = self.client.get(reverse("manage:account"))
        self.assertContains(page, self.profile.manager_code)
        self.assertContains(page, "大阪市城東区0-0-1")  # 暗号化した住所も本人には見える
        self.assertNotContains(page, "運営メモ")

    def test_user_sees_user_ui_only(self):
        self.client.force_login(self.user)
        page = self.client.get(reverse("core:home"))
        self.assertContains(page, 'class="tabbar"')
        self.assertNotContains(page, "管理者コンソール")
        self.assertEqual(self.client.get(reverse("manage:home")).status_code, 403)

    def test_operator_console_nav(self):
        ops_login(self.client, self.op)
        page = self.client.get(reverse("ops:dashboard"))
        self.assertContains(page, "運営コンソール")
        for name in ("ops:coupons", "ops:users", "ops_manage:spots", "ops_manage:coupons", "ops:item_catalog",
                     "ops:password_change"):
            self.assertContains(page, reverse(name), msg_prefix=name)
        self.assertNotContains(page, reverse("wardrobe:index"))
        # 運営者の設定画面は運営側の URL で、リンクも運営側を指す
        spots = self.client.get(reverse("ops_manage:spots"))
        self.assertContains(spots, reverse("ops_manage:spot_create"))
        self.assertNotContains(spots, 'href="/manage/')
        # 運営側から管理者のホーム・アカウントを開くと運営の画面へ
        self.assertRedirects(self.client.get(reverse("ops_manage:home")), reverse("ops:dashboard"))


class CouponAmountTests(Base):
    def setUp(self):
        super().setUp()
        self.mine_cp = CouponTemplate.objects.create(code="m", title="ドリンク 100 円引き", shop_name="わたしの店",
                                                     benefit="100 円引き", value_yen=100, owner=self.manager)
        self.spot_cp = CouponTemplate.objects.create(code="s", title="スポットのクーポン", shop_name="わたしの店",
                                                     benefit="-", value_yen=50, spot=self.mine)  # 担当スポット経由
        self.their_cp = CouponTemplate.objects.create(code="t", title="よそのクーポン", shop_name="よその店",
                                                      benefit="-", value_yen=300, owner=self.other_manager)
        self.ops_cp = CouponTemplate.objects.create(code="o", title="運営のクーポン", shop_name="運営", benefit="-",
                                                    value_yen=0)

    def give(self, tpl, n_used, n_unused=0, days_ago=1):
        now = timezone.now()
        for i in range(n_used + n_unused):
            c = issue_coupon(self.user, tpl, source="test", now=now - dt.timedelta(days=days_ago))
            if i < n_used:
                use_coupon(c, now=now - dt.timedelta(days=days_ago) + dt.timedelta(hours=1))

    def test_value_is_snapshotted_at_use(self):
        self.give(self.mine_cp, 2)
        self.mine_cp.value_yen = 999  # あとから金額を変えても、使った分の金額は変わらない
        self.mine_cp.save()
        self.give(self.mine_cp, 1)
        self.assertEqual(sorted(UserCoupon.objects.filter(template=self.mine_cp, used_at__isnull=False)
                                .values_list("used_value_yen", flat=True)), [100, 100, 999])

    def test_coupon_rows_and_store_rows(self):
        self.give(self.mine_cp, 3, 1)
        self.give(self.spot_cp, 2)
        self.give(self.their_cp, 1, 3)
        self.give(self.ops_cp, 1)
        self.give(self.mine_cp, 5, days_ago=60)  # 30 日より前
        period = stats.Period(30)
        rows = {r["coupon"].code: r for r in stats.coupon_rows(CouponTemplate.objects.all(), period)}
        self.assertEqual((rows["m"]["issued"], rows["m"]["used"], rows["m"]["amount"], rows["m"]["rate"]),
                         (4, 3, 300, 75.0))
        stores = {r["key"]: r for r in stats.store_rows(period)}
        mine = stores[self.manager.pk]  # 自分で登録したものと、担当スポットのものをまとめて数える
        self.assertEqual((mine["coupons"], mine["used"], mine["amount"], mine["label"]), (2, 5, 400, "京橋商店"))
        self.assertEqual((stores[self.other_manager.pk]["used"], stores[self.other_manager.pk]["amount"]), (1, 300))
        self.assertEqual((stores["none"]["label"], stores["none"]["amount"]), ("サイト運営者", 0))
        all_time = {r["key"]: r for r in stats.store_rows(stats.Period(0))}
        self.assertEqual(all_time[self.manager.pk]["amount"], 900)
        months = stats.monthly(CouponTemplate.objects.filter(pk=self.mine_cp.pk))
        self.assertEqual(len(months), 12)
        self.assertEqual(sum(m["used"] for m in months), 8)
        self.assertEqual(sum(m["amount"] for m in months), 800)

    def test_manager_sees_only_own_coupon_stats(self):
        self.give(self.mine_cp, 2)
        self.give(self.their_cp, 4)
        self.client.force_login(self.manager)
        page = self.client.get(reverse("manage:coupon_stats"))
        self.assertContains(page, "ドリンク 100 円引き")
        self.assertContains(page, "スポットのクーポン")
        self.assertNotContains(page, "よそのクーポン")
        self.assertContains(page, "200 円")
        # 店舗の絞り込み (owner) は運営者だけ。管理者が付けても無視され、よその店は見えない
        page = self.client.get(reverse("manage:coupon_stats"), {"owner": self.other_manager.pk})
        self.assertNotContains(page, "よそのクーポン")
        home = self.client.get(reverse("manage:home"))
        self.assertContains(home, "200<small>円</small>")

    def test_operator_store_page(self):
        self.give(self.mine_cp, 2)
        self.give(self.their_cp, 1)
        ops_login(self.client, self.op)
        page = self.client.get(reverse("ops:coupons"), {"days": "30"})
        self.assertContains(page, "京橋商店")
        self.assertContains(page, "別商店")
        self.assertContains(page, "500<small>円</small>")  # 100 × 2 + 300 × 1
        self.assertContains(page, "<svg")
        detail = self.client.get(reverse("ops_manage:coupon_stats"), {"owner": self.other_manager.pk})
        self.assertContains(detail, "よそのクーポン")
        self.assertNotContains(detail, "ドリンク 100 円引き")
        self.assertEqual(self.client.get(reverse("ops:coupons"), {"days": "abc"}).status_code, 200)  # 不正値は既定に

    def test_coupon_form_value(self):
        self.client.force_login(self.manager)
        data = {"title": "新しいクーポン", "shop_name": "わたしの店", "benefit": "200 円引き", "value_yen": "200",
                "description": "", "spot": "", "valid_days": "30", "no_expiry": "on", "is_active": "on"}
        self.assertEqual(self.client.post(reverse("manage:coupon_create"), data).status_code, 302)
        self.assertEqual(CouponTemplate.objects.get(title="新しいクーポン").value_yen, 200)
        bad = self.client.post(reverse("manage:coupon_create"), {**data, "title": "高すぎ", "value_yen": "2000000"})
        self.assertEqual(bad.status_code, 200)
        self.assertFalse(CouponTemplate.objects.filter(title="高すぎ").exists())

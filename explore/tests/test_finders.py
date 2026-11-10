"""「こんな人が獲得しているよ」と、管理者のクーポン登録のテスト。"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ManagerProfile, User
from explore import finders, services
from explore.models import Discovery, DropEntry, Spot, Symbol
from rewards.models import CouponTemplate, UserCoupon, redeem_hash_of
from rewards.services import CouponNotDistributable, CouponUnavailable, issue_coupon, use_coupon
from wardrobe.models import AvatarConfig, Item

PW = "correct horse battery staple"


def found(user, symbol, minutes_ago, item=None, kind="item"):
    return Discovery.objects.create(user=user, symbol=symbol, reward_kind=kind if item else "none",
                                    reward_label=item.name if item else "", reward_ref=item.code if item else "",
                                    idempotency_key=uuid.uuid4(),
                                    found_at=timezone.now() - dt.timedelta(minutes=minutes_ago))


class FinderBase(TestCase):
    def setUp(self):
        cache.clear()
        self.viewer = User.objects.create_user("v@example.com", PW, "みるひと")
        self.spot = Spot.objects.create(slug="s", name="森の社", latitude=Decimal("34.69"), longitude=Decimal("135.53"),
                                        require_location=False)  # 受け取りの流れだけを見るテスト
        self.symbol = Symbol.objects.create(spot=self.spot, name="灯籠")
        self.other_symbol = Symbol.objects.create(spot=self.spot, name="狛犬")
        self.secret = Symbol.objects.create(spot=self.spot, name="ひみつ", is_secret=True)
        self.hat = Item.objects.create(code="hair-x", name="ふわふわ髪", category="hair", style="bob", color="#AA5500")
        self.top = Item.objects.create(code="top-x", name="法被", category="top", style="happi", color="#C0392B")
        self.people = []
        for i in range(8):
            u = User.objects.create_user(f"p{i}@example.com", PW, f"なかま{i}", share_activity=True)
            AvatarConfig.objects.create(user=u, hair=self.hat, top=self.top)
            self.people.append(u)


class RecentFindersTests(FinderBase):
    def test_recent_same_symbol_max_six(self):
        for i, u in enumerate(self.people):
            found(u, self.symbol, minutes_ago=i * 3)
        names = [f["nickname"] for f in finders.recent_finders(self.symbol, self.viewer)]
        self.assertEqual(len(names), 6)
        self.assertEqual(names[0], "なかま0")  # 新しい順

    def test_window_privacy_and_roles(self):
        found(self.people[0], self.symbol, 10)
        found(self.people[1], self.symbol, 31)  # 30 分より前
        found(self.viewer, self.symbol, 1)  # 自分は出さない
        self.people[2].share_activity = False  # 表示しない設定
        self.people[2].save()
        found(self.people[2], self.symbol, 2)
        self.people[3].is_active = False
        self.people[3].save()
        found(self.people[3], self.symbol, 2)
        mgr = User.objects.create_user("m@example.com", PW, "店長", role=User.ROLE_MANAGER)
        found(mgr, self.symbol, 2)
        names = [f["nickname"] for f in finders.recent_finders(self.symbol, self.viewer)]
        self.assertEqual(names, ["なかま0"])

    def test_fill_from_same_spot_when_few(self):
        found(self.people[0], self.symbol, 5)
        found(self.people[1], self.other_symbol, 5)
        found(self.people[1], self.other_symbol, 6)  # 同じ人は 1 回だけ
        found(self.people[2], self.other_symbol, 7)
        names = [f["nickname"] for f in finders.recent_finders(self.symbol, self.viewer)]
        self.assertEqual(names, ["なかま0", "なかま1", "なかま2"])

    def test_ago_is_rough(self):
        self.assertEqual(finders.ago_label(dt.timedelta(minutes=3)), "さっき")
        self.assertEqual(finders.ago_label(dt.timedelta(minutes=17)), "15分前")

    def test_collect_response_includes_finders(self):
        found(self.people[0], self.symbol, 5)
        self.client.force_login(self.viewer)
        ticket = services.make_ticket(self.viewer, self.symbol)
        res = self.client.post(reverse("explore:api_collect"), data=json.dumps({"ticket": ticket}),
                               content_type="application/json", headers={"Idempotency-Key": str(uuid.uuid4())})
        data = res.json()
        self.assertEqual([f["nickname"] for f in data["recent_finders"]], ["なかま0"])
        self.assertNotIn("symbol_id", data)
        self.assertNotIn("user_id", json.dumps(data))
        self.assertNotIn(str(self.people[0].pk) + ",", json.dumps(data))


class FinderProfileTests(FinderBase):
    def setUp(self):
        super().setUp()
        self.target = self.people[0]
        found(self.target, self.symbol, 5, item=self.hat)
        found(self.target, self.secret, 400, item=self.top)
        self.token = finders.recent_finders(self.symbol, self.viewer)[0]["token"]
        self.client.force_login(self.viewer)

    def test_profile_shows_outfit_and_where(self):
        res = self.client.get(reverse("explore:api_finder", args=[self.token]))
        data = res.json()
        self.assertEqual(data["nickname"], "なかま0")
        items = {i["code"]: i for i in data["items"]}
        self.assertEqual(set(items), {"hair-x", "top-x"})
        self.assertIn("森の社でみっけ", items["hair-x"]["obtained"])
        # シークレットシンボルで手に入れたものは、見る人が見つけていなければ場所を伏せる
        self.assertIn("シークレットシンボル", items["top-x"]["obtained"])
        self.assertNotIn("森の社", items["top-x"]["obtained"])
        self.assertNotIn(":", items["hair-x"]["obtained"])  # 時刻は出さない
        # 「これをみっけに行く」用のスポット情報 (シークレット由来は伏せる)
        self.assertEqual(items["hair-x"]["spot"], {"id": self.spot.pk, "name": "森の社", "lat": 34.69, "lng": 135.53})
        self.assertIsNone(items["top-x"]["spot"])
        for url in (data["avatar"], items["hair-x"]["image"]):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            self.assertIn("sandbox", r["Content-Security-Policy"])

    def test_no_map_link_for_unavailable_spot(self):
        self.spot.expires_at = timezone.now() - dt.timedelta(minutes=1)
        self.spot.save()
        items = {i["code"]: i for i in self.client.get(reverse("explore:api_finder", args=[self.token])).json()["items"]}
        self.assertIsNone(items["hair-x"]["spot"])  # 期限切れのスポットには案内しない
        self.assertIn("森の社でみっけ", items["hair-x"]["obtained"])

    def test_item_not_worn_is_404(self):
        Item.objects.create(code="shoes-y", name="下駄", category="shoes", style="geta", color="#333333")
        self.assertEqual(self.client.get(reverse("explore:finder_item_svg", args=[self.token, "shoes-y"])).status_code, 404)

    def test_token_bound_to_viewer_and_settings(self):
        other = User.objects.create_user("o@example.com", PW, "べつのひと")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("explore:api_finder", args=[self.token])).status_code, 404)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("explore:api_finder", args=["forged:token"])).status_code, 404)
        self.target.share_activity = False  # あとから表示をやめたら見られない
        self.target.save()
        self.assertEqual(self.client.get(reverse("explore:api_finder", args=[self.token])).status_code, 404)

    def test_token_expires(self):
        import time

        later = time.time() + finders.TOKEN_TTL_SECONDS + 5
        with mock.patch("django.core.cache.backends.locmem.time.time", return_value=later):
            self.assertEqual(self.client.get(reverse("explore:api_finder", args=[self.token])).status_code, 404)

    def test_token_is_opaque(self):
        # ID はランダムな 24 文字だけ (署名付き JSON のように中身を取り出せる形ではない)。2 回作ると別の値になる
        self.assertRegex(self.token, r"^[A-Za-z0-9_-]{24}$")
        self.assertNotEqual(finders.make_token(self.target.pk, self.viewer.pk), self.token)

    def test_rate_limit_is_429(self):
        with mock.patch("explore.views.ratelimit.hit", return_value=False):
            self.assertEqual(self.client.get(reverse("explore:api_finder", args=[self.token])).status_code, 429)
            self.assertEqual(self.client.get(reverse("explore:finder_avatar_svg", args=[self.token])).status_code, 429)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("explore:api_finder", args=[self.token])).status_code, 401)


class SharingSettingTests(TestCase):
    def test_default_is_opt_in(self):
        self.assertFalse(User.objects.create_user("x@example.com", PW, "x").share_activity)
        from accounts.forms import SignupForm

        self.assertFalse(SignupForm().fields["share_activity"].initial)

    def test_signup_choice_and_account_toggle(self):
        self.client.post(reverse("accounts:signup"), {
            "nickname": "あたらしい", "email": "n@example.com", "password1": PW, "password2": PW})
        user = User.objects.get(nickname="あたらしい")
        self.assertFalse(user.share_activity)  # チェックしなければ表示しない
        self.client.post(reverse("accounts:account"), {"nickname": "あたらしい", "share_activity": "on"})
        user.refresh_from_db()
        self.assertTrue(user.share_activity)


class CouponIdTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("c@example.com", PW, "くー")
        self.other = User.objects.create_user("d@example.com", PW, "でぃー")
        self.tpl = CouponTemplate.objects.create(code="c1", title="饅頭", shop_name="茶屋", benefit="1個", valid_days=30)

    def test_coupon_template_has_own_id(self):
        tpl2 = CouponTemplate.objects.create(code="c2", title="団子", shop_name="茶屋", benefit="1本")
        self.assertRegex(self.tpl.coupon_id, r"^CP-[A-HJKMNP-Z2-9]{6}$")
        self.assertNotEqual(self.tpl.coupon_id, tpl2.coupon_id)

    def test_redeem_codes_never_collide(self):
        a = issue_coupon(self.user, self.tpl, source="t")
        b = issue_coupon(self.other, self.tpl, source="t")
        self.assertNotEqual(a.redeem_code, b.redeem_code)
        self.assertEqual(a.redeem_hash, redeem_hash_of(a.redeem_code))
        # 同じ引換コードは DB の一意制約で作れない
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserCoupon.objects.create(user=self.other, template=self.tpl, redeem_code=a.redeem_code,
                                      expires_at=timezone.now() + dt.timedelta(days=1))

    def test_issue_retries_on_collision(self):
        a = issue_coupon(self.user, self.tpl, source="t")
        codes = iter([a.redeem_code, "MK-ZZZZ-ZZZZ"])
        with mock.patch("rewards.services.new_redeem_code", side_effect=lambda: next(codes)):
            b = issue_coupon(self.other, self.tpl, source="t")
        self.assertEqual(b.redeem_code, "MK-ZZZZ-ZZZZ")

    def test_single_use(self):
        c = issue_coupon(self.user, self.tpl, source="t")
        use_coupon(c)
        first = c.used_at
        use_coupon(c)  # 再送しても使用日時は変わらない (2 回目の使用にはならない)
        c.refresh_from_db()
        self.assertEqual(c.used_at, first)

    def test_expiry_caps_and_stops(self):
        now = timezone.now()
        self.tpl.available_until = now + dt.timedelta(days=3)
        self.tpl.save()
        c = issue_coupon(self.user, self.tpl, source="t", now=now)
        self.assertEqual(c.expires_at, self.tpl.available_until)  # 30 日より早い
        self.tpl.available_until = now - dt.timedelta(minutes=1)
        self.tpl.save()
        with self.assertRaises(CouponNotDistributable):
            issue_coupon(self.user, self.tpl, source="t")
        c.refresh_from_db()
        self.assertEqual(c.status, "expired")
        with self.assertRaises(CouponUnavailable):
            use_coupon(c)

    def test_expired_coupon_not_dropped(self):
        spot = Spot.objects.create(slug="sp", name="店")
        sym = Symbol.objects.create(spot=spot, name="看板")
        DropEntry.objects.create(symbol=sym, coupon=self.tpl)
        self.assertEqual(len(services.candidate_drops(sym, season="autumn", slot="day", visit_days=1)), 1)
        self.tpl.is_active = False
        self.tpl.save()
        self.assertEqual(len(services.candidate_drops(sym, season="autumn", slot="day", visit_days=1)), 0)


class ManagerCouponTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user("m@example.com", PW, "店長", role=User.ROLE_MANAGER)
        ManagerProfile.objects.create(user=self.manager, organization="京橋商店", store_name="本店", contact_name="田中")
        self.other = User.objects.create_user("m2@example.com", PW, "別店", role=User.ROLE_MANAGER)
        self.spot = Spot.objects.create(slug="mine", name="わたしの店", owner=self.manager)
        self.their_coupon = CouponTemplate.objects.create(code="x", title="よそのクーポン", shop_name="別", benefit="-",
                                                          owner=self.other)
        self.client.force_login(self.manager)

    def data(self, **over):
        d = {"title": "ドリンク割引", "shop_name": "京橋商店 本店", "benefit": "50 円引き", "description": "1 回限り",
             "spot": str(self.spot.pk), "valid_days": "14", "available_until": "", "no_expiry": "on", "is_active": "on"}
        d.update(over)
        return {k: v for k, v in d.items() if v is not None}

    def test_create_with_expiry(self):
        until = (timezone.localtime() + dt.timedelta(days=60)).strftime("%Y-%m-%dT%H:%M")
        res = self.client.post(reverse("manage:coupon_create"), self.data(no_expiry=None, available_until=until))
        self.assertRedirects(res, reverse("manage:coupons"))
        tpl = CouponTemplate.objects.get(title="ドリンク割引")
        self.assertEqual(tpl.owner, self.manager)
        self.assertIsNotNone(tpl.available_until)
        self.assertTrue(tpl.code.startswith("cp-"))
        self.assertRegex(tpl.coupon_id, r"^CP-")

    def test_unlimited_and_validation(self):
        self.client.post(reverse("manage:coupon_create"), self.data(available_until="2030-01-01T00:00"))
        self.assertIsNone(CouponTemplate.objects.get(title="ドリンク割引").available_until)  # 無期限が優先
        past = (timezone.localtime() - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        for bad in ({"no_expiry": None, "available_until": past}, {"valid_days": "0"}, {"title": ""}):
            res = self.client.post(reverse("manage:coupon_create"), self.data(title="ちがう", **bad)
                                   if "title" not in bad else self.data(**bad))
            self.assertEqual(res.status_code, 200, bad)

    def test_manager_sees_only_own_coupons(self):
        res = self.client.get(reverse("manage:coupons"))
        self.assertNotContains(res, "よそのクーポン")
        self.assertEqual(self.client.get(reverse("manage:coupon_edit", args=[self.their_coupon.pk])).status_code, 404)
        # ドロップの選択肢にも出ない
        sym = Symbol.objects.create(spot=self.spot, name="看板")
        res = self.client.get(reverse("manage:symbol_edit", args=[sym.pk]))
        self.assertNotContains(res, "よそのクーポン")

    def test_users_cannot_register_coupons(self):
        user = User.objects.create_user("u@example.com", PW, "ゆーざ")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("manage:coupons")).status_code, 403)


class CouponRegressionTests(TestCase):
    """レビューで見つかった不具合の回帰テスト。"""

    def setUp(self):
        self.manager = User.objects.create_user("m@example.com", PW, "店長", role=User.ROLE_MANAGER)
        self.spot = Spot.objects.create(slug="mine", name="わたしの店", owner=self.manager)
        self.symbol = Symbol.objects.create(spot=self.spot, name="看板")
        self.item = Item.objects.create(code="hair-r", name="髪R", category="hair", style="bob", color="#222222")
        # サイト運営者が設定した (管理者のものではない) クーポン。いまは配布停止
        self.ops_coupon = CouponTemplate.objects.create(code="ops", title="運営のクーポン", shop_name="運営",
                                                        benefit="-", is_active=False)
        self.drop = DropEntry.objects.create(symbol=self.symbol, coupon=self.ops_coupon)

    def test_symbol_with_unselectable_coupon_can_still_be_saved(self):
        self.client.force_login(self.manager)
        res = self.client.post(reverse("manage:symbol_edit", args=[self.symbol.pk]), {
            "spot": str(self.spot.pk), "name": "看板(改)", "hint": "", "cooldown_hours": "20", "is_active": "on",
            "latitude": "", "longitude": "",
            "drops-TOTAL_FORMS": "2", "drops-INITIAL_FORMS": "1", "drops-MIN_NUM_FORMS": "0", "drops-MAX_NUM_FORMS": "60",
            "drops-0-id": str(self.drop.pk), "drops-0-item": "", "drops-0-coupon": str(self.ops_coupon.pk),
            "drops-0-weight": "10", "drops-0-season": "any", "drops-0-time_slot": "any", "drops-0-min_visit_days": "1",
            "drops-1-item": str(self.item.pk), "drops-1-coupon": "", "drops-1-weight": "5", "drops-1-season": "any",
            "drops-1-time_slot": "any", "drops-1-min_visit_days": "1"})
        self.assertEqual(res.status_code, 302)
        self.symbol.refresh_from_db()
        self.assertEqual(self.symbol.name, "看板(改)")
        self.assertEqual(self.symbol.drops.count(), 2)
        # 新しい行では、選べないクーポンは選べないまま
        other = Symbol.objects.create(spot=self.spot, name="別の看板")
        res = self.client.get(reverse("manage:symbol_edit", args=[other.pk]))
        self.assertNotContains(res, "運営のクーポン")

    def test_regenerate_token_only_for_own_symbols(self):
        other_manager = User.objects.create_user("m2@example.com", PW, "別の管理者", role="manager")
        self.client.force_login(other_manager)
        res = self.client.post(reverse("manage:symbol_token", args=[self.symbol.pk]))
        self.assertEqual(res.status_code, 404)
        before = self.symbol.token
        self.client.force_login(self.manager)
        res = self.client.post(reverse("manage:symbol_token", args=[self.symbol.pk]))
        self.assertEqual(res.status_code, 302)
        self.symbol.refresh_from_db()
        self.assertNotEqual(self.symbol.token, before)
        self.assertEqual(self.client.get(reverse("manage:symbol_token", args=[self.symbol.pk])).status_code, 405)

    def test_coupon_stopped_between_draw_and_issue_is_not_500(self):
        viewer = User.objects.create_user("u@example.com", PW, "ゆーざ")
        with mock.patch("explore.services.candidate_drops", return_value=[self.drop]):
            res = services.collect(viewer, services.make_ticket(viewer, self.symbol), str(uuid.uuid4()))
        # クーポンの代わりに、ふだん用のコーデを渡す
        self.assertEqual((res.reward_kind, res.item["code"]), ("item", "hair-r"))
        self.assertEqual(Discovery.objects.get(user=viewer).reward_kind, "item")
        self.assertFalse(UserCoupon.objects.filter(user=viewer).exists())

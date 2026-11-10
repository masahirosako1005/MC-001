"""評価レポート (docs/review-2026-11-09.md) の指摘に対応した箇所のテスト。"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ManagerProfile, User
from core import net
from core.testing import ops_login
from core.views import rank_info, season_countdown
from explore import services
from explore.models import Discovery, DropEntry, Spot, Symbol
from rewards.models import CouponTemplate
from rewards.services import issue_coupon
from wardrobe.models import AvatarConfig, Item
from wardrobe.services import get_config

PW = "correct horse battery staple"


class CorrectnessTests(TestCase):
    """フェーズ 1: 正確性・データ完全性。"""

    def setUp(self):
        self.manager = User.objects.create_user("m@example.com", PW, "店長", role=User.ROLE_MANAGER)
        self.other = User.objects.create_user("m2@example.com", PW, "別店", role=User.ROLE_MANAGER)
        self.op = User.objects.create_user("op@example.com", PW, "運営", role=User.ROLE_OPERATOR)
        self.spot = Spot.objects.create(slug="mine", name="わたしの店", owner=self.manager)

    def coupon_data(self, **over):
        d = {"title": "割引", "shop_name": "店", "benefit": "-", "description": "", "spot": "", "valid_days": "7",
             "available_until": "", "no_expiry": "on", "is_active": "on"}
        d.update(over)
        return d

    def test_editing_operator_coupon_keeps_owner(self):  # C3
        tpl = CouponTemplate.objects.create(code="ops", title="運営のクーポン", shop_name="運営", benefit="-",
                                            spot=self.spot)  # 担当スポットに紐づくので管理者も編集できる
        self.client.force_login(self.manager)
        res = self.client.post(reverse("manage:coupon_edit", args=[tpl.pk]), self.coupon_data(title="改"))
        self.assertEqual(res.status_code, 302)
        tpl.refresh_from_db()
        self.assertEqual(tpl.title, "改")
        self.assertIsNone(tpl.owner)  # 持ち主は管理者に移らない

    def test_manager_cannot_post_other_managers_coupon_but_operator_can(self):  # M1
        tpl = CouponTemplate.objects.create(code="b", title="Bのクーポン", shop_name="B", benefit="-", owner=self.other)
        url = reverse("manage:coupon_edit", args=[tpl.pk])
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(url, self.coupon_data(title="のっとり")).status_code, 404)
        tpl.refresh_from_db()
        self.assertEqual(tpl.title, "Bのクーポン")
        ops_login(self.client, self.op)  # 運営者は運営側の URL で同じ画面を使う
        ops_url = reverse("ops_manage:coupon_edit", args=[tpl.pk])
        self.assertEqual(self.client.post(ops_url, self.coupon_data(title="運営が修正")).status_code, 302)
        tpl.refresh_from_db()
        self.assertEqual((tpl.title, tpl.owner), ("運営が修正", self.other))

    def test_cooldown_uses_given_now(self):  # C4
        user = User.objects.create_user("u@example.com", PW, "ゆーざ")
        sym = Symbol.objects.create(spot=self.spot, name="看板", cooldown_hours=20)
        t0 = timezone.now() - dt.timedelta(days=3)
        Discovery.objects.create(user=user, symbol=sym, reward_kind="none", idempotency_key=uuid.uuid4(), found_at=t0)
        self.assertIsNotNone(services.next_available_at(user, sym, now=t0 + dt.timedelta(hours=1)))
        self.assertIsNone(services.next_available_at(user, sym, now=t0 + dt.timedelta(hours=21)))

    def test_coupon_id_regenerated_on_collision(self):  # I3
        first = CouponTemplate.objects.create(code="a", title="A", shop_name="A", benefit="-")
        with mock.patch("rewards.models.new_coupon_id", side_effect=[first.coupon_id, "CP-ZZZZZZ"]):
            second = CouponTemplate(code="b", title="B", shop_name="B", benefit="-", coupon_id=first.coupon_id)
            second.save()
        self.assertEqual(second.coupon_id, "CP-ZZZZZZ")

    def test_manager_code_regenerated_on_collision(self):
        a = ManagerProfile.objects.create(user=self.manager, organization="A", contact_name="a")
        b = ManagerProfile(user=self.other, organization="B", contact_name="b", manager_code=a.manager_code)
        b.save()
        self.assertNotEqual(a.manager_code, b.manager_code)

    def test_effective_expiry_is_single_source(self):  # I5
        user = User.objects.create_user("u2@example.com", PW, "u2")
        tpl = CouponTemplate.objects.create(code="c", title="C", shop_name="C", benefit="-", valid_days=30)
        c = issue_coupon(user, tpl, source="t")
        self.assertEqual(c.effective_expires_at(), c.expires_at)
        tpl.available_until = timezone.now() + dt.timedelta(days=1)
        tpl.save()
        c.refresh_from_db()
        self.assertEqual(c.effective_expires_at(), tpl.available_until)
        self.assertEqual(c.status, "available")
        tpl.available_until = timezone.now() - dt.timedelta(seconds=1)
        tpl.save()
        c.refresh_from_db()
        self.assertEqual(c.status, "expired")


class SecurityTests(TestCase):
    """フェーズ 3: セキュリティ。"""

    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()

    def test_client_ip_ignores_forwarded_without_trusted_proxy(self):  # S4
        req = self.rf.get("/", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="1.2.3.4")
        self.assertEqual(net.client_ip(req), "10.0.0.5")

    def test_client_ip_uses_forwarded_from_trusted_proxy(self):
        import ipaddress

        with override_settings(MIKKE_TRUSTED_PROXIES=[ipaddress.ip_network("10.0.0.0/8")]):
            req = self.rf.get("/", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.7")
            self.assertEqual(net.client_ip(req), "203.0.113.9")
            spoof = self.rf.get("/", REMOTE_ADDR="198.51.100.1", HTTP_X_FORWARDED_FOR="1.2.3.4")
            self.assertEqual(net.client_ip(spoof), "198.51.100.1")  # 信頼済みでない接続元のヘッダーは使わない

    def test_ip_lock_is_looser_than_account_lock(self):  # S4
        User.objects.create_user("a@example.com", PW, "a")
        url = reverse("accounts:login")
        # 別々のアカウントで 6 回失敗しても、同じ IP の別の人はロックされない (IP の上限は 20 回)
        for i in range(6):
            self.client.post(url, {"username": f"x{i}@example.com", "password": "wrong"})
        res = self.client.post(url, {"username": "a@example.com", "password": PW})
        self.assertEqual(res.status_code, 302)

    def test_temp_password_strength(self):  # S7
        from ops.views import _temp_password

        pw = _temp_password()
        self.assertRegex(pw, r"^([A-HJKMNP-Z2-9]{5}-){3}[A-HJKMNP-Z2-9]{5}$")
        self.assertNotEqual(pw, _temp_password())

    def test_forced_password_change_returns_json_for_api(self):  # S8
        user = User.objects.create_user("t@example.com", PW, "t", must_change_password=True)
        self.client.force_login(user)
        res = self.client.post(reverse("explore:api_nearby"), data=json.dumps({"lat": 34.69, "lng": 135.53}),
                               content_type="application/json")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"], "password_change_required")
        self.assertRedirects(self.client.get(reverse("explore:mikke")), reverse("accounts:password_change"))

    def test_debug_banner_only_in_debug(self):  # S1
        self.assertNotContains(self.client.get(reverse("accounts:login")), "開発モード(DEBUG)")
        with override_settings(DEBUG=True):
            self.assertContains(self.client.get(reverse("accounts:login")), "開発モード(DEBUG)")


class UsabilityTests(TestCase):
    """フェーズ 2: ユーザビリティ・多様性。"""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("u@example.com", PW, "ゆーざ")
        self.client.force_login(self.user)

    def test_header_menu_groups_buttons(self):  # U1
        res = self.client.get(reverse("explore:history"))
        self.assertContains(res, 'class="site-menu"')
        body = res.content.decode()
        header = body.split('class="site-header"', 1)[1].split("</header>", 1)[0]
        self.assertIn("ログアウト", header.split("site-menu-panel", 1)[1])  # ボタンはメニューの中

    def test_tables_have_card_labels(self):  # U2
        spot = Spot.objects.create(slug="s", name="森の社")
        sym = Symbol.objects.create(spot=spot, name="灯籠")
        Discovery.objects.create(user=self.user, symbol=sym, reward_kind="none", idempotency_key=uuid.uuid4())
        res = self.client.get(reverse("explore:history"))
        self.assertContains(res, 'class="table table-cards"')
        self.assertContains(res, 'data-label="場所"')

    def test_bare_avatar_is_dressed(self):  # U3
        for cat, body in [("hair", "girl"), ("top", "girl"), ("bottom", "girl"), ("shoes", "girl")]:
            Item.objects.create(code=f"st-{cat}", name=cat, category=cat, style={"hair": "bob", "top": "tshirt",
                                "bottom": "skirt", "shoes": "sneakers"}[cat], color="#333333", is_starter=True,
                                body_type=body)
        AvatarConfig.objects.filter(user=self.user).delete()
        AvatarConfig.objects.create(user=self.user)  # 何も着ていない古いアカウント
        cfg = get_config(self.user)
        self.assertEqual((cfg.hair.code, cfg.top.code, cfg.bottom.code, cfg.shoes.code),
                         ("st-hair", "st-top", "st-bottom", "st-shoes"))
        # 何か 1 つでも着ていれば本人の選択とみなして変えない
        cfg.top = None
        cfg.save()
        self.assertIsNone(get_config(self.user).top)

    def test_rank_and_season_info(self):  # U5 / ホームの動的な情報
        self.assertEqual(rank_info(5), {"rank": "D", "next": "C", "remaining": 5,
                                        "table": rank_info(5)["table"]})
        self.assertIsNone(rank_info(100)["next"])
        self.assertEqual(season_countdown(dt.date(2026, 11, 9)), {"days": 22, "next": "冬"})
        self.assertEqual(season_countdown(dt.date(2026, 12, 31)), {"days": 60, "next": "春"})

    def test_home_shows_rank_help_and_limited(self):
        spot = Spot.objects.create(slug="s", name="森の社", latitude=Decimal("34.69"), longitude=Decimal("135.53"))
        sym = Symbol.objects.create(spot=spot, name="灯籠")
        item = Item.objects.create(code="lim", name="限定", category="hair", style="bob", color="#123456")
        from core.timeutil import local_now, season_of

        DropEntry.objects.create(symbol=sym, item=item, season=season_of(local_now().date()))
        from core.models import SiteSetting

        s = SiteSetting.current()
        s.ui_theme = "game"
        s.save()
        res = self.client.get(reverse("core:home"))
        self.assertContains(res, "gh-rank-panel")
        self.assertContains(res, "いまだけのコーデ")
        self.assertContains(res, reverse("explore:symbol_item_svg", args=[sym.pk, "lim"]))

    def test_password_help_and_reissue_for_users(self):  # U8
        self.client.logout()
        self.assertContains(self.client.get(reverse("accounts:login")), reverse("accounts:password_help"))
        self.assertContains(self.client.get(reverse("accounts:password_help")), "仮パスワード")
        op = User.objects.create_user("op@example.com", PW, "運営", role=User.ROLE_OPERATOR)
        ops_login(self.client, op)
        res = self.client.post(reverse("ops:user_reset_password", args=[self.user.pk]))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(res.context["password"]))
        self.assertTrue(self.user.must_change_password)
        self.assertEqual(self.client.post(reverse("ops:user_reset_password", args=[op.pk])).status_code, 404)

    def test_landing_explains_three_steps(self):  # U9
        self.client.logout()
        res = self.client.get(reverse("core:home"))
        for word in ("見つける", "着せかえる", "クーポンをもらう"):
            self.assertContains(res, word)

    def test_coupon_use_needs_confirmation(self):  # U10
        tpl = CouponTemplate.objects.create(code="c", title="C", shop_name="C", benefit="-")
        c = issue_coupon(self.user, tpl, source="t")
        res = self.client.get(reverse("rewards:coupon_detail", args=[c.pk]))
        self.assertContains(res, "data-confirm=")
        self.assertContains(res, "js/confirm.js")

    def test_japanese_404(self):  # U12
        res = self.client.get("/no-such-page/")
        self.assertEqual(res.status_code, 404)
        self.assertContains(res, "ページが見つかりません", status_code=404)

    def test_field_aria_describedby(self):  # D1
        self.client.logout()
        res = self.client.post(reverse("accounts:signup"), {"nickname": "", "email": "bad", "password1": "x",
                                                            "password2": "y"})
        body = res.content.decode()
        self.assertIn('aria-describedby="id_nickname_help id_nickname_errors"', body)
        self.assertIn('aria-invalid="true"', body)

    def test_contest_steps_use_check_not_strikethrough(self):  # U11
        css = (self._static("css/mikke.css"))
        self.assertNotIn("contest-steps li.is-done { color: var(--muted); text-decoration: line-through", css)

    def test_no_tiny_fonts(self):  # D2
        import re

        for path in ("css/mikke.css", "css/themes/game.css"):
            self.assertFalse(re.search(r"font-size: 0\.(5|6|65|7)rem", self._static(path)), path)

    @staticmethod
    def _static(path):
        from django.conf import settings

        return (settings.BASE_DIR / "static" / path).read_text(encoding="utf-8")

"""スポットの公開期間・管理画面、近くのシンボル判定 (GPS)、シークレットシンボルのテスト。"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from decimal import Decimal

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from core.models import AuditLog, SiteSetting
from explore import services
from explore.models import Discovery, DropEntry, Spot, SpotVisit, Symbol
from wardrobe.models import Item

PW = "correct horse battery staple"
# 基準点 (35.0, 139.0) から北へ 0.0005 度 ≒ 56m、0.01 度 ≒ 1.1km
NEAR = {"lat": 35.0005, "lng": 139.0}
FAR = {"lat": 35.01, "lng": 139.0}


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("u@example.com", PW, "ゆーざ")
        self.staff = User.objects.create_user("staff@example.com", PW, "すたっふ")
        self.staff.role = "operator"
        self.staff.save()
        self.spot = Spot.objects.create(slug="s", name="テスト温泉", latitude=Decimal("35.0"), longitude=Decimal("139.0"))
        self.symbol = Symbol.objects.create(spot=self.spot, name="かっぱ", hint="足湯のそば", cooldown_hours=20)
        self.item = Item.objects.create(code="hair-a", name="髪A", category="hair", style="bob", color="#222222")
        DropEntry.objects.create(symbol=self.symbol, item=self.item, weight=10)
        self.secret = Symbol.objects.create(spot=self.spot, name="ひみつの狐", hint="夜の石段", is_secret=True,
                                            latitude=Decimal("35.0003"), longitude=Decimal("139.0"))
        self.secret_item = Item.objects.create(code="acc-fox", name="狐のお面", category="accessory",
                                               style="foxmask", color="#CC2222")
        DropEntry.objects.create(symbol=self.secret, item=self.secret_item, weight=10)

    def nearby(self, coords, client=None):
        c = client or self.client
        return c.post(reverse("explore:api_nearby"), data=json.dumps(coords), content_type="application/json")


class SpotPeriodTests(Base):
    def test_status_and_availability(self):
        now = timezone.now()
        self.assertEqual(self.spot.status(now), "active")
        self.spot.starts_at = now + dt.timedelta(days=1)
        self.assertEqual(self.spot.status(now), "scheduled")
        self.spot.starts_at, self.spot.expires_at = None, now - dt.timedelta(seconds=1)
        self.assertEqual(self.spot.status(now), "expired")
        self.spot.expires_at, self.spot.is_active = None, False
        self.assertEqual(self.spot.status(now), "hidden")

    def test_expired_spot_is_hidden_everywhere(self):
        self.spot.expires_at = timezone.now() - dt.timedelta(minutes=1)
        self.spot.save()
        self.assertFalse(Spot.objects.available().exists())
        self.assertFalse(services.available_symbols().exists())
        with self.assertRaises(services.UnknownSymbol):
            services.scan(self.user, self.symbol.payload)
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(reverse("explore:mikke")), "テスト温泉")
        self.assertFalse(self.nearby(NEAR).json()["has_nearby"])

    def test_no_expiry_is_forever(self):
        far_future = timezone.now() + dt.timedelta(days=365 * 50)
        self.assertTrue(Spot.objects.available(far_future).filter(pk=self.spot.pk).exists())

    def test_period_constraint(self):
        now = timezone.now()
        self.spot.starts_at, self.spot.expires_at = now, now - dt.timedelta(hours=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.spot.save()

    def test_symbol_coords_must_be_pair(self):
        self.symbol.latitude = Decimal("35.0")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.symbol.save()

    def test_symbol_location_falls_back_to_spot(self):
        self.assertEqual(self.symbol.location, (35.0, 139.0))
        self.assertEqual(self.secret.location, (35.0003, 139.0))


class NearbyApiTests(Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_within_radius(self):
        data = self.nearby(NEAR).json()
        self.assertEqual(data["radius_m"], 100)
        self.assertTrue(data["has_nearby"])
        self.assertEqual(len(data["nearby"]), 2)
        self.assertIsNone(data["nearest"])
        normal = next(s for s in data["nearby"] if not s["secret"])
        self.assertEqual(normal["name"], "かっぱ")
        self.assertEqual([i["code"] for i in normal["items"]], ["hair-a"])
        self.assertIn("now", normal["items"][0])
        self.assertTrue(normal["items"][0]["image"].endswith("/items/hair-a.svg"))

    def test_secret_is_masked(self):
        res = self.nearby(NEAR)
        secret = next(s for s in res.json()["nearby"] if s["secret"])
        self.assertEqual(secret["name"], "？？？")
        self.assertEqual(secret["hint"], "")
        self.assertEqual(secret["items"], [])
        body = res.content.decode()
        for leaked in ("ひみつの狐", "夜の石段", "acc-fox", "狐のお面"):
            self.assertNotIn(leaked, body)

    def test_outside_radius_returns_nearest(self):
        data = self.nearby(FAR).json()
        self.assertFalse(data["has_nearby"])
        self.assertEqual(data["nearby"], [])
        self.assertEqual(data["nearest"]["spot"], "テスト温泉")
        self.assertGreater(data["nearest"]["distance_m"], 1000)

    def test_radius_follows_site_setting(self):
        s = SiteSetting.current()
        s.camera_radius_m = 2000
        s.save()
        data = self.nearby(FAR).json()
        self.assertEqual(data["radius_m"], 2000)
        self.assertTrue(data["has_nearby"])

    def test_bad_input_and_methods(self):
        for bad in ({}, {"lat": "x", "lng": 1}, {"lat": 91, "lng": 0}, {"lat": 0, "lng": 181}):
            self.assertEqual(self.nearby(bad).status_code, 400)
        self.assertEqual(self.client.get(reverse("explore:api_nearby")).status_code, 405)
        # 位置は URL に載せない (GET のクエリでは受け付けない)
        self.assertEqual(self.client.get(reverse("explore:api_nearby"), NEAR).status_code, 405)

    def test_login_required(self):
        self.client.logout()
        self.assertIn(self.nearby(NEAR).status_code, (401, 403))

    def test_rate_limited(self):
        codes = [self.nearby(NEAR).status_code for _ in range(31)]
        self.assertEqual(codes[-1], 429)

    def test_location_not_recorded(self):
        before = AuditLog.objects.count()
        self.nearby(NEAR)
        self.assertEqual(AuditLog.objects.count(), before)


class SymbolItemImageTests(Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def url(self, symbol, code):
        return reverse("explore:symbol_item_svg", args=[symbol.pk, code])

    def test_preview_image(self):
        res = self.client.get(self.url(self.symbol, "hair-a"))
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res["Content-Type"].startswith("image/svg+xml"))
        self.assertIn("sandbox", res["Content-Security-Policy"])

    def test_secret_and_unrelated_items_are_404(self):
        self.assertEqual(self.client.get(self.url(self.secret, "acc-fox")).status_code, 404)
        self.assertEqual(self.client.get(self.url(self.symbol, "acc-fox")).status_code, 404)
        self.spot.expires_at = timezone.now() - dt.timedelta(minutes=1)
        self.spot.save()
        self.assertEqual(self.client.get(self.url(self.symbol, "hair-a")).status_code, 404)


class MikkePageTests(Base):
    """「みっけ」画面: 地図で近くのシンボルをさがす → カメラでみっけ (スポット一覧とカメラを統合)。"""

    def test_search_first_then_camera(self):
        self.client.force_login(self.user)
        res = self.client.get(reverse("explore:mikke"))
        self.assertTemplateUsed(res, "explore/mikke.html")
        body = res.content.decode()
        # 地図・検索ボタン・カメラ・写真読み取りが 1 画面にある
        for part in ('id="spot-map"', 'id="btn-nearby"', 'id="mikke-camera"', 'id="ar-video"', 'id="reward-dialog"',
                     reverse("explore:api_nearby"), reverse("explore:api_scan"), "js/nearby.js", "js/camera.js"):
            self.assertIn(part, body)
        # 近くにシンボルがあると分かるまで、カメラと写真読み取りは押せない
        self.assertRegex(body, r'id="btn-start" disabled')
        self.assertRegex(body, r'id="file-input"[^>]*disabled')
        # スクリプトは nearby.js → spotmap.js → camera.js の順 (検索結果を地図とカメラが受け取る)
        self.assertLess(body.index("js/nearby.js"), body.index("js/spotmap.js"))
        self.assertLess(body.index("js/spotmap.js"), body.index("js/camera.js"))

    def test_spot_cards_hidden_and_secret_not_leaked(self):
        Discovery.objects.create(user=self.user, symbol=self.secret, reward_kind="none", reward_label="",
                                 idempotency_key=uuid.uuid4())
        self.client.force_login(self.user)
        res = self.client.get(reverse("explore:mikke"))
        self.assertNotContains(res, 'class="spot-card"')
        for hidden in ("ひみつの狐", "夜の石段", "かっぱ", "足湯のそば"):
            self.assertNotContains(res, hidden)

    def test_spot_cards_can_be_shown_again(self):
        self.client.force_login(self.user)
        with self.settings(MIKKE_SHOW_SPOT_CARDS=True):
            res = self.client.get(reverse("explore:mikke"))
        self.assertContains(res, 'class="spot-card"')
        self.assertContains(res, "？？？(シークレットシンボル)")  # 見つけるまでは隠す
        self.assertNotContains(res, "ひみつの狐")

    def test_old_camera_url_redirects(self):
        self.client.force_login(self.user)
        res = self.client.get("/explore/camera/")
        self.assertRedirects(res, reverse("explore:mikke"), status_code=301)

    def test_nav_has_single_mikke_tab(self):
        self.client.force_login(self.user)
        res = self.client.get(reverse("core:home"))
        nav = res.content.decode().split('class="tabbar"', 1)[1].split("</nav>", 1)[0]
        self.assertIn(reverse("explore:mikke"), nav)
        self.assertNotIn("スポット", nav)
        self.assertNotIn("/explore/camera/", nav)


class SpotManageTests(Base):
    def form(self, **over):
        data = {"name": "新しい公園", "area": "京橋", "description": "", "latitude": "34.6965", "longitude": "135.5340",
                "radius_m": "300", "is_active": "on", "starts_at": "", "expires_at": "", "no_expiry": "on"}
        data.update(over)
        return {k: v for k, v in data.items() if v is not None}

    def test_staff_only(self):
        urls = [reverse("explore:manage_spots"), reverse("explore:manage_spot_create"),
                reverse("explore:manage_spot_edit", args=[self.spot.pk]),
                reverse("explore:manage_spot_delete", args=[self.spot.pk])]
        for u in urls:
            self.assertEqual(self.client.get(u).status_code, 302)
        self.client.force_login(self.user)
        for u in urls:
            self.assertEqual(self.client.get(u).status_code, 403)  # 利用者には設定画面を使わせない
        self.client.force_login(self.staff)
        for u in urls:
            self.assertEqual(self.client.get(u).status_code, 200)

    def test_create_unlimited(self):
        self.client.force_login(self.staff)
        res = self.client.post(reverse("explore:manage_spot_create"), self.form(expires_at="2030-01-01T10:00"))
        self.assertRedirects(res, reverse("explore:manage_spots"))
        spot = Spot.objects.get(name="新しい公園")
        self.assertIsNone(spot.expires_at)  # 「無期限」が優先される
        self.assertTrue(spot.slug.startswith("spot-"))
        self.assertTrue(AuditLog.objects.filter(action="spot.create").exists())

    def test_create_with_expiry(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("explore:manage_spot_create"),
                         self.form(no_expiry=None, starts_at="2030-01-01T10:00", expires_at="2030-02-01T10:00"))
        spot = Spot.objects.get(name="新しい公園")
        self.assertEqual(timezone.localtime(spot.expires_at).date(), dt.date(2030, 2, 1))
        self.assertEqual(spot.status(), "scheduled")

    def test_validation(self):
        self.client.force_login(self.staff)
        cases = [
            self.form(no_expiry=None, starts_at="2030-02-01T10:00", expires_at="2030-01-01T10:00"),
            self.form(longitude=""),
            self.form(latitude="", longitude="", require_location="on"),
            self.form(radius_m="5"),
        ]
        for data in cases:
            res = self.client.post(reverse("explore:manage_spot_create"), data)
            self.assertEqual(res.status_code, 200, data)
        self.assertFalse(Spot.objects.filter(name="新しい公園").exists())

    def test_edit(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("explore:manage_spot_edit", args=[self.spot.pk]),
                         self.form(name="改名した温泉", no_expiry=None, expires_at="2031-01-01T00:00"))
        self.spot.refresh_from_db()
        self.assertEqual(self.spot.name, "改名した温泉")
        self.assertIsNotNone(self.spot.expires_at)

    def test_delete_without_records(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("explore:manage_spot_delete", args=[self.spot.pk]), {"action": "delete"})
        self.assertFalse(Spot.objects.filter(pk=self.spot.pk).exists())
        self.assertFalse(Symbol.objects.filter(spot_id=self.spot.pk).exists())

    def test_delete_blocked_by_records_then_hide_or_expire(self):
        SpotVisit.objects.create(user=self.user, spot=self.spot, visit_date=timezone.localdate(), season="autumn")
        self.client.force_login(self.staff)
        url = reverse("explore:manage_spot_delete", args=[self.spot.pk])
        self.assertContains(self.client.get(url), "訪問記録")
        self.client.post(url, {"action": "delete"})
        self.assertTrue(Spot.objects.filter(pk=self.spot.pk).exists())
        self.client.post(url, {"action": "expire"})
        self.spot.refresh_from_db()
        self.assertEqual(self.spot.status(), "expired")
        self.client.post(url, {"action": "hide"})
        self.spot.refresh_from_db()
        self.assertFalse(self.spot.is_active)


class SiteSettingRadiusTests(TestCase):
    def test_radius_range(self):
        s = SiteSetting.current()
        for bad in (5, 5001):
            s.camera_radius_m = bad
            with self.assertRaises(IntegrityError), transaction.atomic():
                s.save()

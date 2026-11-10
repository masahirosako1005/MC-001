"""権限 (利用者 / 管理者 / サイト運営者)・専用ログイン・利用者管理・分析のテスト。"""

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

from accounts.models import ManagerProfile, User
from core.models import AuditLog
from core.testing import ops_login
from explore import services
from explore.models import Discovery, DropEntry, NearbyVisit, Spot, SpotVisit, Symbol
from ops import analytics, charts
from wardrobe.models import Item

PW = "correct horse battery staple"


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("u@example.com", PW, "ゆーざ")
        self.manager = User.objects.create_user("m@example.com", PW, "店長", role=User.ROLE_MANAGER)
        self.profile = ManagerProfile.objects.create(user=self.manager, organization="京橋商店", contact_name="田中",
                                                     address="大阪市城東区0-0-1", phone="06-0000-0001")
        self.other_manager = User.objects.create_user("m2@example.com", PW, "別の店", role=User.ROLE_MANAGER)
        ManagerProfile.objects.create(user=self.other_manager, organization="別商店", contact_name="佐藤")
        self.op = User.objects.create_user("op@example.com", PW, "運営", role=User.ROLE_OPERATOR)
        self.mine = Spot.objects.create(slug="mine", name="わたしの店", latitude=Decimal("34.69"),
                                        longitude=Decimal("135.53"), owner=self.manager)
        self.theirs = Spot.objects.create(slug="theirs", name="よその店", latitude=Decimal("34.70"),
                                          longitude=Decimal("135.54"), owner=self.other_manager)
        self.ops_spot = Spot.objects.create(slug="ops", name="運営のスポット", latitude=Decimal("34.695"),
                                            longitude=Decimal("135.535"))
        self.sym_mine = Symbol.objects.create(spot=self.mine, name="看板")
        self.sym_theirs = Symbol.objects.create(spot=self.theirs, name="よその看板")
        self.item = Item.objects.create(code="hair-z", name="髪Z", category="hair", style="bob", color="#222222")


class RoleModelTests(Base):
    def test_is_staff_follows_role(self):
        self.assertTrue(self.op.is_staff)
        self.assertFalse(self.manager.is_staff)
        self.manager.is_staff = True  # 直接いじっても role から決まる
        self.manager.save()
        self.manager.refresh_from_db()
        self.assertFalse(self.manager.is_staff)

    def test_superuser_must_be_operator(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("x@example.com", PW, "x", is_superuser=True)

    def test_manager_profile_encrypts_and_has_unique_code(self):
        self.assertRegex(self.profile.manager_code, r"^MK-[2-9A-HJKMNP-Z]{6}$")
        from django.db import connection

        with connection.cursor() as c:
            c.execute("SELECT address, phone FROM accounts_managerprofile WHERE id=%s", [self.profile.pk])
            raw = c.fetchone()
        self.assertNotIn("城東区", raw[0])
        self.assertNotIn("06-0000", raw[1])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.address, "大阪市城東区0-0-1")


class LoginSeparationTests(Base):
    def login(self, url, email):
        return self.client.post(url, {"username": email, "password": PW})

    def test_user_and_manager_use_normal_login(self):
        for email in ("u@example.com", "m@example.com"):
            res = self.login(reverse("accounts:login"), email)
            self.assertEqual(res.status_code, 302, email)
            self.client.logout()

    def test_operator_cannot_use_normal_login(self):
        res = self.login(reverse("accounts:login"), "op@example.com")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "メールアドレスまたはパスワードが違います")  # 運営者かどうかを明かさない
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_operator_login_page(self):
        from django.conf import settings
        from django.contrib.sessions.backends.db import SessionStore

        res = self.login(reverse("ops:login"), "op@example.com")
        self.assertRedirects(res, reverse("ops:dashboard"))
        # 運営者のログインは運営側専用の Cookie にだけ入る (利用者側のセッション Cookie は作らない)
        self.assertNotIn(settings.SESSION_COOKIE_NAME, res.cookies)
        ops_session = SessionStore(self.client.cookies[settings.OPS_SESSION_COOKIE_NAME].value)
        self.assertEqual(ops_session.get("_auth_user_id"), str(self.op.pk))
        self.assertLessEqual(ops_session.get_expiry_age(), 4 * 3600)
        self.assertTrue(AuditLog.objects.filter(action="ops.login").exists())
        # そのまま利用者の画面を開いても、ログインしていない状態 (利用者の機能は使えない)
        res = self.client.get(reverse("wardrobe:index"))
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res["Location"].startswith(reverse("accounts:login")))

    def test_others_cannot_use_operator_login(self):
        for email in ("u@example.com", "m@example.com"):
            res = self.login(reverse("ops:login"), email)
            self.assertEqual(res.status_code, 200)
            self.assertNotIn("_auth_user_id", self.client.session)

    def test_operator_login_locks_sooner(self):
        for _ in range(5):
            self.client.post(reverse("ops:login"), {"username": "op@example.com", "password": "wrong"})
        res = self.login(reverse("ops:login"), "op@example.com")
        self.assertContains(res, "しばらくログインできません")

    def test_admin_login_redirects_to_ops_login(self):
        from django.conf import settings

        res = self.client.get("/" + settings.ADMIN_URL + "login/")
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res["Location"].startswith(reverse("ops:login")))


class PermissionTests(Base):
    def test_ops_pages(self):
        urls = [reverse("ops:dashboard"), reverse("ops:users"), reverse("ops:manager_create"),
                reverse("ops:manager_edit", args=[self.manager.pk])]
        for u in urls:
            res = self.client.get(u)
            self.assertEqual(res.status_code, 302)
            self.assertTrue(res["Location"].startswith(reverse("ops:login")))
        for who in (self.user, self.manager):
            # 利用者側のログインは運営側では読まれない (未ログインと同じく運営者のログインへ)
            self.client.force_login(who)
            for u in urls:
                res = self.client.get(u)
                self.assertEqual(res.status_code, 302, (who, u))
                self.assertTrue(res["Location"].startswith(reverse("ops:login")))
            self.client.logout()
        ops_login(self.client, self.op)
        for u in urls:
            self.assertEqual(self.client.get(u).status_code, 200, u)

    def test_user_cannot_manage_spots(self):
        self.client.force_login(self.user)
        for u in (reverse("manage:spots"), reverse("manage:symbol_register"), reverse("manage:symbols"),
                  reverse("manage:symbol_create")):
            self.assertEqual(self.client.get(u).status_code, 403)

    def test_manager_sees_only_own_spots(self):
        self.client.force_login(self.manager)
        res = self.client.get(reverse("manage:spots"))
        self.assertContains(res, "わたしの店")
        self.assertNotContains(res, "よその店")
        self.assertNotContains(res, "運営のスポット")
        self.assertEqual(self.client.get(reverse("manage:spot_edit", args=[self.theirs.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("manage:spot_delete", args=[self.theirs.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("manage:symbol_edit", args=[self.sym_theirs.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("manage:symbol_svg", args=[self.sym_theirs.pk])).status_code, 404)
        res = self.client.get(reverse("manage:symbols"))
        self.assertContains(res, "看板")
        self.assertNotContains(res, "よその看板")
        # 画像シンボル登録で選べるのも自分のスポットだけ
        res = self.client.get(reverse("manage:symbol_register"))
        self.assertContains(res, "わたしの店")
        self.assertNotContains(res, "よその店")

    def test_manager_creates_spot_as_owner(self):
        self.client.force_login(self.manager)
        res = self.client.post(reverse("manage:spot_create"), {
            "name": "新店舗", "area": "", "description": "", "latitude": "34.69", "longitude": "135.53",
            "radius_m": "200", "is_active": "on", "no_expiry": "on", "owner": str(self.other_manager.pk)})
        self.assertEqual(res.status_code, 302)
        self.assertEqual(Spot.objects.get(name="新店舗").owner, self.manager)  # 担当は自分 (ほかの人にはできない)

    def test_operator_assigns_owner(self):
        ops_login(self.client, self.op)
        self.client.post(reverse("ops_manage:spot_edit", args=[self.ops_spot.pk]), {
            "name": "運営のスポット", "area": "", "description": "", "latitude": "34.695", "longitude": "135.535",
            "radius_m": "300", "is_active": "on", "no_expiry": "on", "owner": str(self.manager.pk)})
        self.ops_spot.refresh_from_db()
        self.assertEqual(self.ops_spot.owner, self.manager)

    def test_manager_symbol_settings_with_drops(self):
        self.client.force_login(self.manager)
        url = reverse("manage:symbol_create")
        data = {"spot": str(self.mine.pk), "name": "新しい看板", "hint": "入口", "cooldown_hours": "20",
                "is_active": "on", "is_secret": "on", "latitude": "", "longitude": "",
                "drops-TOTAL_FORMS": "2", "drops-INITIAL_FORMS": "0", "drops-MIN_NUM_FORMS": "0",
                "drops-MAX_NUM_FORMS": "60",
                "drops-0-item": str(self.item.pk), "drops-0-coupon": "", "drops-0-weight": "10",
                "drops-0-season": "any", "drops-0-time_slot": "night", "drops-0-min_visit_days": "1",
                "drops-1-item": "", "drops-1-coupon": "", "drops-1-weight": "10", "drops-1-season": "any",
                "drops-1-time_slot": "any", "drops-1-min_visit_days": "1"}
        res = self.client.post(url, data)
        sym = Symbol.objects.get(name="新しい看板")
        self.assertRedirects(res, reverse("manage:symbol_edit", args=[sym.pk]))
        self.assertTrue(sym.is_secret)
        self.assertEqual(sym.kind, Symbol.KIND_QR)
        self.assertEqual(list(sym.drops.values_list("item__code", "time_slot")), [("hair-z", "night")])
        # ほかの店のスポットには作れない
        data["spot"] = str(self.theirs.pk)
        data["name"] = "のっとり"
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.assertFalse(Symbol.objects.filter(name="のっとり").exists())

    def test_drop_requires_exactly_one_reward(self):
        self.client.force_login(self.manager)
        res = self.client.post(reverse("manage:symbol_edit", args=[self.sym_mine.pk]), {
            "spot": str(self.mine.pk), "name": "看板", "hint": "", "cooldown_hours": "20", "is_active": "on",
            "latitude": "", "longitude": "",
            "drops-TOTAL_FORMS": "1", "drops-INITIAL_FORMS": "0", "drops-MIN_NUM_FORMS": "0", "drops-MAX_NUM_FORMS": "60",
            "drops-0-item": "", "drops-0-coupon": "", "drops-0-weight": "10", "drops-0-season": "any",
            "drops-0-time_slot": "any", "drops-0-min_visit_days": "1"})
        # 空行は無視される (何も選ばなければ追加しない)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.sym_mine.drops.count(), 0)


class UserManagementTests(Base):
    def setUp(self):
        super().setUp()
        ops_login(self.client, self.op)

    def manager_data(self, **over):
        data = {"email": "new@example.com", "nickname": "新しい店", "organization": "新商店", "store_name": "本店",
                "industry": "food", "contact_name": "鈴木", "postal_code": "5340024", "address": "大阪市(架空)0-1",
                "phone": "06-0000-1234", "website": "https://example.com/", "note": ""}
        data.update(over)
        return data

    def test_create_manager_shows_temp_password_once(self):
        res = self.client.post(reverse("ops:manager_create"), self.manager_data())
        self.assertEqual(res.status_code, 200)
        user = User.objects.get(nickname="新しい店")
        self.assertEqual(user.role, User.ROLE_MANAGER)
        self.assertTrue(user.must_change_password)
        self.assertEqual(user.manager_profile.postal_code, "534-0024")
        password = res.context["password"]
        self.assertTrue(user.check_password(password))
        self.assertContains(res, password)
        self.assertContains(res, user.manager_profile.manager_code)
        log = AuditLog.objects.get(action="ops.manager_create")
        self.assertNotIn(password, json.dumps(log.detail, ensure_ascii=False))  # 仮パスワードはログに残さない

    def test_only_managers_can_be_added(self):
        # フォームに権限を選ぶ項目はなく、何を送っても管理者になる
        self.client.post(reverse("ops:manager_create"), self.manager_data(role="operator"))
        self.assertEqual(User.objects.get(nickname="新しい店").role, User.ROLE_MANAGER)

    def test_validation(self):
        for bad in ({"email": "m@example.com"}, {"phone": "abc"}, {"postal_code": "12-34"}, {"organization": ""}):
            res = self.client.post(reverse("ops:manager_create"), self.manager_data(**bad))
            self.assertEqual(res.status_code, 200)
            self.assertFalse(User.objects.filter(nickname="新しい店").exists(), bad)

    def test_forced_password_change(self):
        res = self.client.post(reverse("ops:manager_create"), self.manager_data())
        password = res.context["password"]
        self.client.logout()
        self.client.post(reverse("accounts:login"), {"username": "new@example.com", "password": password})
        self.assertRedirects(self.client.get(reverse("manage:spots")), reverse("accounts:password_change"))
        new = "kawa-sora-hoshi-umi-2026"
        self.client.post(reverse("accounts:password_change"),
                         {"old_password": password, "new_password1": new, "new_password2": new})
        self.assertEqual(self.client.get(reverse("manage:spots")).status_code, 200)

    def test_edit_manager_and_reset_password(self):
        res = self.client.post(reverse("ops:manager_edit", args=[self.manager.pk]),
                               self.manager_data(email="m@example.com", nickname="店長", organization="改名商店"))
        self.assertRedirects(res, reverse("ops:users"))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.organization, "改名商店")
        res = self.client.post(reverse("ops:manager_reset_password", args=[self.manager.pk]))
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.check_password(res.context["password"]))
        self.assertTrue(self.manager.must_change_password)
        # 管理者以外は編集・再発行できない
        self.assertEqual(self.client.get(reverse("ops:manager_edit", args=[self.user.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("ops:manager_reset_password", args=[self.op.pk])).status_code, 404)

    def test_suspend_and_resume(self):
        url = reverse("ops:user_toggle", args=[self.user.pk])
        self.client.post(url)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.client.post(url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.client.post(reverse("ops:user_toggle", args=[self.op.pk]))
        self.op.refresh_from_db()
        self.assertTrue(self.op.is_active)  # 運営者は止められない

    def test_user_list_and_search(self):
        res = self.client.get(reverse("ops:users"), {"role": "manager"})
        self.assertContains(res, "京橋商店")
        self.assertNotContains(res, "ゆーざ")
        res = self.client.get(reverse("ops:users"), {"q": "u@example.com"})  # メールは完全一致で探せる
        self.assertContains(res, "ゆーざ")
        res = self.client.get(reverse("ops:users"), {"q": self.profile.manager_code})
        self.assertContains(res, "京橋商店")
        self.assertNotContains(res, "大阪市城東区")  # 一覧に住所は出さない


class WithdrawTests(Base):
    def test_user_can_withdraw(self):
        Discovery.objects.create(user=self.user, symbol=self.sym_mine, reward_kind="none", idempotency_key=uuid.uuid4())
        self.client.force_login(self.user)
        res = self.client.post(reverse("accounts:withdraw"), {"password": "wrong", "confirm": "on"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        res = self.client.post(reverse("accounts:withdraw"), {"password": PW})  # 確認のチェックなし
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        uid = self.user.pk
        res = self.client.post(reverse("accounts:withdraw"), {"password": PW, "confirm": "on"})
        self.assertRedirects(res, reverse("core:home"), fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(pk=uid).exists())
        self.assertFalse(Discovery.objects.filter(user_id=uid).exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        log = AuditLog.objects.get(action="account.withdraw")
        self.assertEqual(log.detail, {"user_id": uid})

    def test_manager_and_operator_cannot_withdraw_themselves(self):
        # 管理者・運営者は利用者の画面 (退会を含む) を開けず、それぞれの画面に戻される
        for who, home in ((self.manager, reverse("manage:home")), (self.op, reverse("ops:dashboard"))):
            self.client.force_login(who)
            res = self.client.post(reverse("accounts:withdraw"), {"password": PW, "confirm": "on"})
            self.assertRedirects(res, home, fetch_redirect_response=False)
            self.assertTrue(User.objects.filter(pk=who.pk).exists())


class TrackingTests(Base):
    def test_nearby_records_spot_not_coordinates(self):
        self.client.force_login(self.user)
        url = reverse("explore:api_nearby")
        for _ in range(3):
            self.client.post(url, data=json.dumps({"lat": 34.69, "lng": 135.53}), content_type="application/json")
        nv = NearbyVisit.objects.get(user=self.user)
        self.assertEqual((nv.spot, nv.page_views, nv.camera_starts), (self.mine, 3, 0))
        field_names = {f.name for f in NearbyVisit._meta.fields}
        self.assertFalse({"lat", "lng", "latitude", "longitude"} & field_names)
        # 遠くで探しても記録しない
        self.client.post(url, data=json.dumps({"lat": 35.5, "lng": 139.5}), content_type="application/json")
        self.assertEqual(NearbyVisit.objects.count(), 1)

    def test_camera_start_counts_recent_nearby(self):
        now = timezone.now()
        services.record_nearby_visit(self.user, {self.mine.pk}, now=now - dt.timedelta(minutes=5))
        services.record_nearby_visit(self.user, {self.theirs.pk}, now=now - dt.timedelta(hours=2))
        self.client.force_login(self.user)
        res = self.client.post(reverse("explore:api_camera_start"), data="{}", content_type="application/json")
        self.assertEqual(res.json()["counted"], 1)
        self.assertEqual(NearbyVisit.objects.get(spot=self.mine).camera_starts, 1)
        self.assertEqual(NearbyVisit.objects.get(spot=self.theirs).camera_starts, 0)
        self.assertEqual(self.client.get(reverse("explore:api_camera_start")).status_code, 405)


class AnalyticsTests(Base):
    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        users = [User.objects.create_user(f"a{i}@example.com", PW, f"a{i}") for i in range(10)]
        # わたしの店: 10 人来て、6 人がカメラ、3 人がコーデ獲得 (1 人は 2 回)、1 人はなし
        for i, u in enumerate(users):
            NearbyVisit.objects.create(user=u, spot=self.mine, date=today, slot="day", season="autumn",
                                       page_views=2, camera_starts=1 if i < 6 else 0)
        drop = DropEntry.objects.create(symbol=self.sym_mine, item=self.item)
        noon = timezone.make_aware(dt.datetime.combine(today, dt.time(12, 0)))
        for u in users[:3]:
            Discovery.objects.create(user=u, symbol=self.sym_mine, drop=drop, reward_kind="item",
                                     idempotency_key=uuid.uuid4(), found_at=noon)
        Discovery.objects.create(user=users[0], symbol=self.sym_mine, drop=drop, reward_kind="item",
                                 idempotency_key=uuid.uuid4(), found_at=noon)
        Discovery.objects.create(user=users[3], symbol=self.sym_mine, reward_kind="none",
                                 idempotency_key=uuid.uuid4(), found_at=noon)
        # よその店: 4 人来て 1 人獲得。users[0] は両方に来ている
        for u in users[:4]:
            NearbyVisit.objects.create(user=u, spot=self.theirs, date=today, slot="night", season="autumn")
        Discovery.objects.create(user=users[0], symbol=self.sym_theirs, reward_kind="item",
                                 idempotency_key=uuid.uuid4(), found_at=noon)
        # 期間外の古いデータ
        NearbyVisit.objects.create(user=users[9], spot=self.theirs, date=today - dt.timedelta(days=200),
                                   slot="morning", season="spring")
        SpotVisit.objects.create(user=users[0], spot=self.mine, visit_date=today, season="autumn")

    def test_funnel_and_rate(self):
        data = analytics.compute(analytics.Filters(days=30))
        rows = {r["spot"].slug: r for r in data["spots"]}
        mine = rows["mine"]
        self.assertEqual((mine["visitors"], mine["page_views"], mine["camera"], mine["finders"], mine["coord"],
                          mine["coord_count"]), (10, 20, 6, 4, 3, 4))
        self.assertEqual(mine["rate"], 30.0)  # 3 ÷ 10 × 100
        self.assertEqual(rows["theirs"]["rate"], 25.0)
        self.assertIsNone(rows["ops"]["rate"])  # 来訪なしは割合を出さない
        # 全体は重複なしで数える
        self.assertEqual(data["total"]["visitors"], 10)
        self.assertEqual(data["total"]["coord"], 3)
        self.assertEqual(data["spots"][0]["spot"].slug, "mine")  # 付近に来た人が多い順

    def test_filters(self):
        data = analytics.compute(analytics.Filters(days=0))
        self.assertEqual({r["spot"].slug: r["visitors"] for r in data["spots"]}["theirs"], 5)
        data = analytics.compute(analytics.Filters(days=30, slot="night"))
        rows = {r["spot"].slug: r for r in data["spots"]}
        self.assertEqual(rows["mine"]["visitors"], 0)
        self.assertEqual(rows["theirs"]["visitors"], 4)
        data = analytics.compute(analytics.Filters(days=30, owner=str(self.manager.pk)))
        self.assertEqual([r["spot"].slug for r in data["spots"]], ["mine"])
        data = analytics.compute(analytics.Filters(days=30, owner="none"))
        self.assertEqual([r["spot"].slug for r in data["spots"]], ["ops"])
        by_slot = {r["key"]: r for r in analytics.compute(analytics.Filters(days=30))["by_slot"]}
        self.assertEqual(by_slot["day"]["visitors"], 10)
        self.assertEqual(by_slot["night"]["visitors"], 4)

    def test_filters_from_query_are_validated(self):
        f = analytics.Filters.from_query({"days": "9999", "season": "<x>", "slot": "night", "owner": "1 OR 1=1",
                                          "sort": "rate"})
        self.assertEqual((f.days, f.season, f.slot, f.owner, f.sort), (30, "", "night", "", "rate"))

    def test_dashboard_renders_charts_and_tables(self):
        ops_login(self.client, self.op)
        res = self.client.get(reverse("ops:dashboard"), {"days": "30"})
        self.assertContains(res, '<svg class="chart"', count=5)
        self.assertContains(res, "わたしの店")
        self.assertContains(res, "30.0%")
        self.assertContains(res, "表で見る")

    def test_chart_escapes_labels(self):
        svg = charts.grouped_hbar([{"label": '<script>"x"</script>', "visitors": 3, "camera": 1, "coord": 1}],
                                  [("visitors", "付近"), ("camera", "カメラ"), ("coord", "コーデ")], title="t")
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)

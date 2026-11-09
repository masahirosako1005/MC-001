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

from accounts.models import User
from explore import services
from explore.models import Discovery, DropEntry, Spot, SpotVisit, Symbol
from explore.symbols import render_symbol_svg
from rewards.models import Achievement, CouponTemplate, UserCoupon
from wardrobe.models import Item, UserItem

PW = "correct horse battery staple"
JST = dt.timezone(dt.timedelta(hours=9))


def at(y, m, d, h=12):
    return dt.datetime(y, m, d, h, 0, tzinfo=JST)


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("e@example.com", PW, "えくす")
        self.other = User.objects.create_user("o@example.com", PW, "おーさー")
        self.spot = Spot.objects.create(slug="s", name="テスト温泉", latitude=Decimal("35.0"), longitude=Decimal("139.0"))
        self.symbol = Symbol.objects.create(spot=self.spot, name="かっぱ", cooldown_hours=20)
        self.item = Item.objects.create(code="hair-a", name="髪A", category="hair", style="bob", color="#222222")
        self.drop = DropEntry.objects.create(symbol=self.symbol, item=self.item, weight=10)

    def ticket(self, user=None):
        return services.make_ticket(user or self.user, self.symbol)


class ServiceTests(Base):
    def test_parse_payload(self):
        self.assertEqual(services.parse_payload(self.symbol.payload), self.symbol.token)
        for bad in ["", "https://evil.example/", "MIKKE1:", "MIKKE1:../../etc", "MIKKE1:" + "a" * 100, None]:
            self.assertIsNone(services.parse_payload(bad))

    def test_scan_ready_then_cooldown(self):
        res = services.scan(self.user, self.symbol.payload)
        self.assertEqual(res["status"], "ready")
        self.assertTrue(res["ticket"])
        services.collect(self.user, res["ticket"], str(uuid.uuid4()))
        res2 = services.scan(self.user, self.symbol.payload)
        self.assertEqual(res2["status"], "cooldown")
        self.assertIsNone(res2["ticket"])

    def test_scan_unknown(self):
        with self.assertRaises(services.UnknownSymbol):
            services.scan(self.user, "MIKKE1:" + "x" * 24)

    def test_inactive_symbol_hidden(self):
        self.symbol.is_active = False
        self.symbol.save()
        with self.assertRaises(services.UnknownSymbol):
            services.scan(self.user, self.symbol.payload)

    def test_collect_grants_item_and_records(self):
        r = services.collect(self.user, self.ticket(), str(uuid.uuid4()))
        self.assertEqual(r.reward_kind, "item")
        self.assertTrue(r.is_new)
        # 結果画面で絵 (全身 + 部位の拡大図) を出すための情報
        self.assertEqual((r.item["code"], r.item["slot"]), ("hair-a", "hair"))
        self.assertTrue(UserItem.objects.filter(user=self.user, item=self.item).exists())
        self.assertEqual(Discovery.objects.filter(user=self.user).count(), 1)
        self.assertEqual(SpotVisit.objects.filter(user=self.user).count(), 1)

    def test_idempotent_replay(self):
        key = str(uuid.uuid4())
        t = self.ticket()
        r1 = services.collect(self.user, t, key)
        r2 = services.collect(self.user, t, key)
        self.assertFalse(r1.replay)
        self.assertTrue(r2.replay)
        self.assertEqual(r2.label, r1.label)
        self.assertEqual(Discovery.objects.count(), 1)
        self.assertEqual(UserItem.objects.get(user=self.user).obtained_count, 1)

    def test_cooldown_blocks_second_collect(self):
        services.collect(self.user, self.ticket(), str(uuid.uuid4()))
        with self.assertRaises(services.Cooldown):
            services.collect(self.user, self.ticket(), str(uuid.uuid4()))

    def test_cooldown_expires(self):
        t0 = timezone.now() - dt.timedelta(hours=21)
        services.collect(self.user, self.ticket(), str(uuid.uuid4()), now=t0)
        r = services.collect(self.user, self.ticket(), str(uuid.uuid4()))
        self.assertEqual(r.reward_kind, "item")
        self.assertEqual(UserItem.objects.get(user=self.user).obtained_count, 2)

    def test_ticket_bound_to_user(self):
        with self.assertRaises(services.InvalidTicket):
            services.collect(self.other, self.ticket(self.user), str(uuid.uuid4()))

    def test_forged_ticket_rejected(self):
        with self.assertRaises(services.InvalidTicket):
            services.collect(self.user, "forged:ticket", str(uuid.uuid4()))

    def test_expired_ticket_rejected(self):
        with self.settings(MIKKE_SCAN_TICKET_MAX_AGE=-1):
            with self.assertRaises(services.InvalidTicket):
                services.collect(self.user, self.ticket(), str(uuid.uuid4()))

    def test_bad_idempotency_key(self):
        with self.assertRaises(services.ExploreError):
            services.collect(self.user, self.ticket(), "not-a-uuid")

    def test_location_required(self):
        self.spot.require_location = True
        self.spot.radius_m = 300
        self.spot.save()
        with self.assertRaises(services.LocationRequired):
            services.collect(self.user, self.ticket(), str(uuid.uuid4()))
        with self.assertRaises(services.TooFar):
            services.collect(self.user, self.ticket(), str(uuid.uuid4()), coords=(35.1, 139.0))  # 約11km
        r = services.collect(self.user, self.ticket(), str(uuid.uuid4()), coords=(35.001, 139.0))  # 約111m
        self.assertEqual(r.reward_kind, "item")

    def test_distance(self):
        self.assertAlmostEqual(services.distance_m(35.0, 139.0, 35.001, 139.0), 111.2, delta=1)

    def test_season_and_slot_filter(self):
        winter = Item.objects.create(code="w", name="冬", category="accessory", style="scarf", color="#B3262E")
        night = Item.objects.create(code="n", name="夜", category="accessory", style="foxmask", color="#C0392B")
        DropEntry.objects.create(symbol=self.symbol, item=winter, season="winter")
        DropEntry.objects.create(symbol=self.symbol, item=night, time_slot="night")
        codes = lambda **kw: {d.item.code for d in services.candidate_drops(self.symbol, visit_days=1, **kw)}  # noqa: E731
        self.assertEqual(codes(season="summer", slot="day"), {"hair-a"})
        self.assertEqual(codes(season="winter", slot="day"), {"hair-a", "w"})
        self.assertEqual(codes(season="summer", slot="night"), {"hair-a", "n"})

    def test_revisit_unlock(self):
        rare = Item.objects.create(code="r", name="再訪", category="top", style="happi", color="#2D4A8A")
        DropEntry.objects.create(symbol=self.symbol, item=rare, min_visit_days=2)
        codes = lambda v: {d.item.code for d in services.candidate_drops(self.symbol, season="spring", slot="day", visit_days=v)}  # noqa: E731
        self.assertNotIn("r", codes(1))
        self.assertIn("r", codes(2))

    def test_visit_days_counted_per_local_day(self):
        services.collect(self.user, self.ticket(), str(uuid.uuid4()), now=at(2026, 4, 1, 9))
        r = services.collect(self.user, self.ticket(), str(uuid.uuid4()), now=at(2026, 4, 3, 9))
        self.assertEqual(r.visit_days, 2)
        self.assertTrue(r.is_revisit_day)
        self.assertEqual(set(SpotVisit.objects.values_list("season", flat=True)), {"spring"})

    def test_coupon_drop(self):
        self.drop.delete()
        tpl = CouponTemplate.objects.create(code="c", title="饅頭", shop_name="茶屋", benefit="1個", valid_days=10)
        DropEntry.objects.create(symbol=self.symbol, coupon=tpl)
        r = services.collect(self.user, self.ticket(), str(uuid.uuid4()))
        self.assertEqual(r.reward_kind, "coupon")
        c = UserCoupon.objects.get(user=self.user)
        self.assertTrue(c.redeem_code.startswith("MK-"))

    def test_no_drop_still_gives_outfit(self):
        # 衣装全振り: ドロップが未設定でも「何もなし」にはせず、ふだん用のコーデを渡す
        self.drop.delete()
        r = services.collect(self.user, self.ticket(), str(uuid.uuid4()))
        self.assertEqual(r.reward_kind, "item")
        self.assertEqual(r.item["code"], "hair-a")
        self.assertTrue(UserItem.objects.filter(user=self.user, item=self.item).exists())
        self.assertIsNone(Discovery.objects.get(user=self.user).drop)

    def test_fallback_outfit_choice(self):
        # 条件外 (秋の夜限定) のときは、限定アイテムではなく、ふだん用 (レア度 2 まで・体のタイプが合う・未所持) を渡す
        now = at(2026, 4, 10, 12)  # 春の昼
        limited = Item.objects.create(code="hair-limited", name="限定髪", category="hair", style="bob", color="#111111",
                                      rarity=5)
        self.drop.item, self.drop.season, self.drop.time_slot = limited, "autumn", "night"
        self.drop.save()
        Item.objects.create(code="boy-top", name="男の子用", category="top", style="tshirt", color="#222222",
                            body_type="boy")
        Item.objects.create(code="rare-top", name="レア", category="top", style="tshirt", color="#333333", rarity=4)
        Item.objects.create(code="starter", name="初期", category="top", style="tshirt", color="#444444",
                            is_starter=True)
        r = services.collect(self.user, self.ticket(), str(uuid.uuid4()), now=now)
        self.assertEqual(r.item["code"], "hair-a")
        self.assertTrue(r.item["new"])

    def test_fallback_when_everything_owned_is_marked_owned(self):
        self.drop.delete()
        UserItem.objects.create(user=self.user, item=self.item)
        r = services.collect(self.user, self.ticket(), str(uuid.uuid4()))
        self.assertEqual((r.reward_kind, r.item["code"], r.item["new"]), ("item", "hair-a", False))

    def test_achievement_unlocked_once(self):
        bonus = Item.objects.create(code="b", name="ごほうび", category="accessory", style="glasses", color="#B8892B")
        Achievement.objects.create(code="a1", name="はじめて", description="1回", kind="total_discoveries",
                                   threshold=1, reward_item=bonus)
        r1 = services.collect(self.user, self.ticket(), str(uuid.uuid4()), now=timezone.now() - dt.timedelta(days=2))
        self.assertEqual([a["name"] for a in r1.achievements], ["はじめて"])
        self.assertTrue(UserItem.objects.filter(user=self.user, item=bonus).exists())
        r2 = services.collect(self.user, self.ticket(), str(uuid.uuid4()))
        self.assertEqual(r2.achievements, [])

    def test_weighted_pick_respects_weights(self):
        a = DropEntry(weight=1)
        b = DropEntry(weight=1000)
        with mock.patch.object(services._rng, "uniform", return_value=0.5):
            self.assertIs(services.pick_weighted([a, b]), a)
        with mock.patch.object(services._rng, "uniform", return_value=500):
            self.assertIs(services.pick_weighted([a, b]), b)
        self.assertIsNone(services.pick_weighted([]))


class ConstraintTests(Base):
    def test_drop_must_have_exactly_one_reward(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DropEntry.objects.create(symbol=self.symbol)
        tpl = CouponTemplate.objects.create(code="c2", title="t", shop_name="s", benefit="b")
        with self.assertRaises(IntegrityError), transaction.atomic():
            DropEntry.objects.create(symbol=self.symbol, item=self.item, coupon=tpl)

    def test_location_required_needs_coords(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Spot.objects.create(slug="x", name="x", require_location=True)

    def test_one_visit_per_day(self):
        SpotVisit.objects.create(user=self.user, spot=self.spot, visit_date=dt.date(2026, 1, 1), season="winter")
        with self.assertRaises(IntegrityError), transaction.atomic():
            SpotVisit.objects.create(user=self.user, spot=self.spot, visit_date=dt.date(2026, 1, 1), season="winter")


class ApiTests(Base):
    def api(self, name, body, client=None, **headers):
        c = client or self.client
        return c.post(reverse(f"explore:{name}"), data=json.dumps(body), content_type="application/json", headers=headers)

    def test_anonymous_gets_401(self):
        res = self.api("api_scan", {"payload": self.symbol.payload})
        self.assertEqual(res.status_code, 401)

    def test_csrf_enforced(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.user)
        res = self.api("api_scan", {"payload": self.symbol.payload}, client=client)
        self.assertEqual(res.status_code, 403)

    def test_scan_and_collect_flow(self):
        self.client.force_login(self.user)
        scan = self.api("api_scan", {"payload": self.symbol.payload})
        self.assertEqual(scan.status_code, 200)
        ticket = scan.json()["ticket"]
        key = str(uuid.uuid4())
        res = self.api("api_collect", {"ticket": ticket}, **{"Idempotency-Key": key})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["item"]["code"], "hair-a")
        again = self.api("api_collect", {"ticket": ticket}, **{"Idempotency-Key": key})
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.json()["replay"])
        other_key = self.api("api_collect", {"ticket": ticket}, **{"Idempotency-Key": str(uuid.uuid4())})
        self.assertEqual(other_key.status_code, 409)

    def test_unknown_payload_404(self):
        self.client.force_login(self.user)
        self.assertEqual(self.api("api_scan", {"payload": "hello"}).status_code, 404)

    def test_bad_json_400(self):
        self.client.force_login(self.user)
        res = self.client.post(reverse("explore:api_scan"), data="not json", content_type="application/json")
        self.assertEqual(res.status_code, 400)

    def test_rate_limit(self):
        self.client.force_login(self.user)
        codes = [self.api("api_scan", {"payload": self.symbol.payload}).status_code for _ in range(61)]
        self.assertEqual(codes[-1], 429)

    def test_get_not_allowed(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("explore:api_scan")).status_code, 405)


class PageTests(Base):
    def test_pages_render(self):
        self.client.force_login(self.user)
        for name in ["explore:mikke", "explore:mikke", "explore:history", "core:home", "rewards:coupons",
                     "rewards:achievements", "wardrobe:index"]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_symbol_print_staff_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("explore:symbol_svg", args=[self.symbol.pk])).status_code, 403)
        staff = User.objects.create_user("s@example.com", PW, "スタッフ", role="operator")
        self.client.force_login(staff)
        res = self.client.get(reverse("explore:symbol_svg", args=[self.symbol.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"<svg", res.content)

    def test_symbol_svg_escapes_names(self):
        self.spot.name = '<script>alert(1)</script>'
        self.spot.save()
        svg = render_symbol_svg(Symbol.objects.select_related("spot").get(pk=self.symbol.pk))
        self.assertNotIn("<script>", svg)

"""再訪率 (みっけ・クーポンの利用) と、日ごとのアプリ利用率のテスト。"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from core.models import DailyActivity
from core.testing import ops_login
from explore.models import Discovery, Spot, Symbol
from ops import engagement
from rewards.models import CouponTemplate
from rewards.services import issue_coupon, use_coupon

PW = "correct horse battery staple"


def at(day: dt.date, hour: int = 12) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour), tzinfo=timezone.get_current_timezone())


class RevisitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.today = timezone.localdate()
        spot = Spot.objects.create(slug="s", name="森の社", latitude=Decimal("34.69"), longitude=Decimal("135.53"))
        self.symbol = Symbol.objects.create(spot=spot, name="灯籠")
        self.coupon = CouponTemplate.objects.create(code="c", title="100 円引き", shop_name="店", benefit="-",
                                                    value_yen=100, valid_days=60)
        self.u = [User.objects.create_user(f"u{i}@example.com", PW, f"u{i}") for i in range(4)]
        self.manager = User.objects.create_user("m@example.com", PW, "店長", role=User.ROLE_MANAGER)

    def find(self, user, days_ago, hour=12):
        Discovery.objects.create(user=user, symbol=self.symbol, reward_kind="none", idempotency_key=uuid.uuid4(),
                                 found_at=at(self.today - dt.timedelta(days=days_ago), hour))

    def test_revisit_counts_distinct_days_of_mikke_or_coupon_use(self):
        a, b, c, d = self.u
        self.find(a, 1, 9)
        self.find(a, 1, 18)  # 同じ日に 2 回は 1 日
        self.find(b, 2)
        self.find(b, 10)  # 別の日 → 再訪
        self.find(c, 3)
        coupon = issue_coupon(c, self.coupon, source="t", now=at(self.today - dt.timedelta(days=3)))
        use_coupon(coupon, now=at(self.today - dt.timedelta(days=1)))  # 別の日にクーポンを使った → 再訪
        self.find(d, 40)  # 30 日より前
        self.find(d, 5)
        self.find(self.manager, 1)
        self.find(self.manager, 2)  # 管理者は数えない
        r = engagement.revisit(engagement.Window.last(30, self.today))
        self.assertEqual((r["visitors"], r["revisitors"], r["rate"]), (4, 2, 50.0))
        self.assertEqual({b["key"]: b["users"] for b in r["buckets"]}, {"1": 2, "2": 2, "3-4": 0, "5+": 0})
        year = engagement.revisit(engagement.Window.last(365, self.today))
        self.assertEqual((year["visitors"], year["revisitors"]), (4, 3))

    def test_login_only_is_not_a_visit(self):
        for days_ago in (1, 2, 3):
            DailyActivity.objects.create(user=self.u[0], date=self.today - dt.timedelta(days=days_ago))
        r = engagement.revisit(engagement.Window.last(30, self.today))
        self.assertEqual((r["visitors"], r["rate"]), (0, None))

    def test_monthly_revisit(self):
        rows = engagement.monthly_revisit(12, self.today)
        self.assertEqual(len(rows), 12)
        self.find(self.u[0], 0)
        self.find(self.u[0], 0, 20)
        rows = engagement.monthly_revisit(12, self.today)
        self.assertEqual((rows[-1]["visitors"], rows[-1]["revisitors"]), (1, 0))


class DailyUsageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.today = timezone.localdate()

    def test_daily_rate_uses_users_registered_by_that_day(self):
        old = [User.objects.create_user(f"o{i}@example.com", PW, f"o{i}") for i in range(4)]
        for u in old:
            u.date_joined = timezone.now() - dt.timedelta(days=40)
            u.save(update_fields=["date_joined"])
        new = User.objects.create_user("n@example.com", PW, "n")  # 今日登録
        User.objects.create_user("op@example.com", PW, "運営", role=User.ROLE_OPERATOR)  # 数えない
        yesterday = self.today - dt.timedelta(days=1)
        DailyActivity.objects.create(user=old[0], date=yesterday)
        DailyActivity.objects.create(user=old[1], date=yesterday)
        DailyActivity.objects.create(user=new, date=self.today)
        rows = engagement.daily_usage(30, self.today)
        self.assertEqual(len(rows), 30)
        self.assertEqual((rows[-2]["active"], rows[-2]["registered"], rows[-2]["rate"]), (2, 4, 50.0))
        self.assertEqual((rows[-1]["active"], rows[-1]["registered"], rows[-1]["rate"]), (1, 5, 20.0))

    def test_middleware_records_users_once_per_day_only(self):
        user = User.objects.create_user("u@example.com", PW, "ゆーざ")
        self.client.force_login(user)
        self.client.get(reverse("core:home"))
        self.client.get(reverse("wardrobe:index"))
        self.assertEqual(list(DailyActivity.objects.values_list("user_id", "date")), [(user.pk, self.today)])
        # 管理者・運営者・未ログインは数えない
        manager = User.objects.create_user("m@example.com", PW, "店長", role=User.ROLE_MANAGER)
        self.client.force_login(manager)
        self.client.get(reverse("manage:home"))
        op = User.objects.create_user("op@example.com", PW, "運営", role=User.ROLE_OPERATOR)
        self.client.logout()
        ops_login(self.client, op)
        self.client.get(reverse("ops:dashboard"))
        self.client.cookies.clear()
        self.client.get(reverse("accounts:login"))
        self.assertEqual(DailyActivity.objects.count(), 1)


class EngagementPageTests(TestCase):
    def test_operator_page(self):
        cache.clear()
        op = User.objects.create_user("op@example.com", PW, "運営", role=User.ROLE_OPERATOR)
        user = User.objects.create_user("u@example.com", PW, "ゆーざ")
        DailyActivity.objects.create(user=user, date=timezone.localdate())
        ops_login(self.client, op)
        page = self.client.get(reverse("ops:engagement"))
        self.assertContains(page, "再訪率")
        self.assertContains(page, "アプリ利用率")
        self.assertContains(page, "<svg", count=3)
        self.assertContains(page, "100.0<small>%</small>")  # 今日の利用率 1 / 1
        self.assertEqual(self.client.get(reverse("ops:engagement"), {"days": "999"}).status_code, 200)
        dash = self.client.get(reverse("ops:dashboard"))
        self.assertContains(dash, reverse("ops:engagement"))  # 左メニューから開ける

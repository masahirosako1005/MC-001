from __future__ import annotations

import datetime as dt

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from rewards.models import CouponTemplate, UserCoupon
from rewards.services import CouponUnavailable, issue_coupon, new_redeem_code, use_coupon

PW = "correct horse battery staple"


class CouponTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("c@example.com", PW, "くー")
        self.other = User.objects.create_user("d@example.com", PW, "でぃー")
        self.tpl = CouponTemplate.objects.create(code="c", title="饅頭", shop_name="茶屋", benefit="1個", valid_days=7)
        self.coupon = issue_coupon(self.user, self.tpl, source="test")

    def test_code_format(self):
        code = new_redeem_code()
        self.assertRegex(code, r"^MK-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$")

    def test_use_is_idempotent(self):
        c1 = use_coupon(self.coupon)
        used_at = c1.used_at
        c2 = use_coupon(self.coupon)
        self.assertEqual(c2.used_at, used_at)

    def test_expired_cannot_be_used(self):
        past = timezone.now() - dt.timedelta(days=30)
        old = issue_coupon(self.user, self.tpl, source="old", now=past)
        with self.assertRaises(CouponUnavailable):
            use_coupon(old)
        self.assertEqual(old.status, "expired")

    def test_other_users_coupon_is_404(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("rewards:coupon_detail", args=[self.coupon.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("rewards:coupon_use", args=[self.coupon.pk])).status_code, 404)
        self.coupon.refresh_from_db()
        self.assertIsNone(self.coupon.used_at)

    def test_use_via_view(self):
        self.client.force_login(self.user)
        res = self.client.post(reverse("rewards:coupon_use", args=[self.coupon.pk]), follow=True)
        self.assertContains(res, "使用済み")
        self.coupon.refresh_from_db()
        self.assertIsNotNone(self.coupon.used_at)

    def test_use_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("rewards:coupon_use", args=[self.coupon.pk])).status_code, 405)

    def test_detail_shows_decrypted_code(self):
        self.client.force_login(self.user)
        res = self.client.get(reverse("rewards:coupon_detail", args=[self.coupon.pk]))
        self.assertContains(res, self.coupon.redeem_code)

    def test_db_constraint_expiry(self):
        now = timezone.now()
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserCoupon.objects.create(user=self.user, template=self.tpl, redeem_code="x", issued_at=now, expires_at=now)

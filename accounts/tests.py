from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from core.models import AuditLog
from wardrobe.models import AvatarConfig, Item

GOOD_PW = "sora-iro kamome shiokaze"


class SignupTests(TestCase):
    def setUp(self):
        Item.objects.create(code="h", name="髪", category="hair", style="short", color="#111111", is_starter=True)
        Item.objects.create(code="t", name="服", category="top", style="tshirt", color="#EEEEEE", is_starter=True)

    def post(self, **over):
        data = {"nickname": "たびびと", "email": "Traveler@Example.com", "password1": GOOD_PW, "password2": GOOD_PW}
        data.update(over)
        return self.client.post(reverse("accounts:signup"), data)

    def test_signup_creates_user_with_starter_kit(self):
        res = self.post()
        self.assertRedirects(res, reverse("wardrobe:index"))
        user = User.objects.get()
        self.assertEqual(user.email, "traveler@example.com")
        cfg = AvatarConfig.objects.get(user=user)
        self.assertEqual(cfg.hair.code, "h")
        self.assertEqual(user.items.count(), 2)
        self.assertTrue(AuditLog.objects.filter(action="account.signup").exists())

    def test_short_password_rejected(self):
        res = self.post(password1="short-pass", password2="short-pass")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_duplicate_email_case_insensitive(self):
        self.post()
        self.client.logout()
        res = self.post(email="TRAVELER@example.com", nickname="べつ")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_password_is_argon2(self):
        self.post()
        self.assertTrue(User.objects.get().password.startswith("argon2"))


class LoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("login@example.com", GOOD_PW, "ろぐ")

    def login(self, pw, email="LOGIN@example.com"):
        return self.client.post(reverse("accounts:login"), {"username": email, "password": pw})

    def test_login_with_email(self):
        res = self.login(GOOD_PW)
        self.assertRedirects(res, reverse("core:home"), fetch_redirect_response=False)

    def test_lockout_after_failures(self):
        for _ in range(5):
            self.assertEqual(self.login("wrong-password-xxxx").status_code, 200)
        res = self.login(GOOD_PW)  # 正しいパスワードでもロック中
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "しばらくログインできません")
        self.assertGreaterEqual(AuditLog.objects.filter(action="auth.login_failed").count(), 5)

    def test_login_page_requires_csrf(self):
        client = self.client_class(enforce_csrf_checks=True)
        res = client.post(reverse("accounts:login"), {"username": "login@example.com", "password": GOOD_PW})
        self.assertEqual(res.status_code, 403)

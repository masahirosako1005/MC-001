"""2026-11-09 セキュリティレビュー 優先度 A の改修に対するテスト。

- A-2: 開発用シードの確認用アカウントに固定パスワードを使わない
- A-3: /wardrobe/catalog/ の権限 (wardrobe/tests)
- A-4: 本番で LocMemCache を使わせない (settings の起動時エラーと check --deploy)
"""

from __future__ import annotations

from io import StringIO
from unittest import mock

from django.test import TestCase, override_settings

from accounts.models import User, email_hash_of
from core import checks
from core.ids import temp_password


class DeployCheckTests(TestCase):
    def test_locmem_cache_is_an_error(self):
        locmem = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "x"}}
        with override_settings(CACHES=locmem):
            self.assertEqual([e.id for e in checks.check_cache_backend(None)], ["mikke.E001"])
        dbcache = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "t"}}
        with override_settings(CACHES=dbcache):
            self.assertEqual(checks.check_cache_backend(None), [])

    def test_leftover_test_accounts_are_an_error(self):
        self.assertEqual(checks.check_test_accounts(None, databases=["default"]), [])
        User.objects.create_user("manager@test.com", temp_password(), "m", role="manager")
        errors = checks.check_test_accounts(None, databases=["default"])
        self.assertEqual([e.id for e in errors], ["mikke.E002"])
        self.assertIn("manager@test.com", errors[0].msg)
        # DB を見ない呼び出し (databases なし) では判定しない
        self.assertEqual(checks.check_test_accounts(None), [])

    def test_settings_refuse_locmem_when_not_debug(self):
        """settings.py を DEBUG=False・MIKKE_CACHE 未設定で読み込むと ImproperlyConfigured になる。"""
        import importlib
        import os
        import sys

        from django.core.exceptions import ImproperlyConfigured

        env = {**os.environ, "DJANGO_DEBUG": "0", "MIKKE_CACHE": "", "MIKKE_ALLOW_LOCMEM_CACHE": ""}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("dotenv.load_dotenv", lambda *a, **k: None):
            sys.modules.pop("config.settings", None)
            with self.assertRaises(ImproperlyConfigured):
                importlib.import_module("config.settings")
            sys.modules.pop("config.settings", None)
            with mock.patch.dict(os.environ, {"MIKKE_ALLOW_LOCMEM_CACHE": "1"}):
                importlib.import_module("config.settings")
        sys.modules.pop("config.settings", None)


class SeedTestAccountTests(TestCase):
    def _run(self):
        from core.management.commands.seed_analytics import Command

        cmd = Command()
        cmd.stdout = StringIO()
        cmd.style = mock.Mock(WARNING=lambda s: s, SUCCESS=lambda s: s)
        return cmd._test_accounts(), cmd.stdout.getvalue()

    def test_temp_password_is_random_and_must_be_changed(self):
        accounts, out = self._run()
        for key in ("manager", "user"):
            u = accounts[key]
            self.assertTrue(u.must_change_password)
            self.assertFalse(u.check_password("test1234"))
            self.assertIn(u.groups.first().name, ("デモ管理者", "デモ利用者"))
        self.assertIn("仮パスワード", out)
        # 2 回目はパスワードを表示しない (変えない)
        accounts2, out2 = self._run()
        self.assertEqual(accounts2["user"].password, accounts["user"].password)
        self.assertNotIn("仮パスワード", out2)

    def test_legacy_fixed_password_is_rotated(self):
        legacy = User.objects.create_user("user@test.com", "test1234", "古い", role="user")
        legacy.must_change_password = False
        legacy.save()
        accounts, out = self._run()
        legacy.refresh_from_db()
        self.assertFalse(legacy.check_password("test1234"))
        self.assertTrue(legacy.must_change_password)
        self.assertIn("user@test.com", out)
        self.assertEqual(User.objects.get(email_hash=email_hash_of("user@test.com")).pk, legacy.pk)

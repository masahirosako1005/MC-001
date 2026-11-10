"""ログイン画面の「いま、まちで手に入るコーデ」と、証明書の信頼登録の案内のテスト。"""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.timeutil import local_now, season_of, slot_of
from explore.models import DropEntry, Spot, Symbol
from wardrobe.models import Item


class LoginShowcaseTests(TestCase):
    def setUp(self):
        cache.clear()
        now = local_now()
        self.season, self.slot = season_of(now.date()), slot_of(now)
        self.spot = Spot.objects.create(slug="s", name="ほたる公園", latitude=Decimal("34.69"), longitude=Decimal("135.53"))
        self.symbol = Symbol.objects.create(spot=self.spot, name="看板")
        for code, cat, style in (("st-hair", "hair", "bob"), ("st-top", "top", "tshirt"),
                                 ("st-bottom", "bottom", "skirt"), ("st-shoes", "shoes", "sneakers")):
            Item.objects.create(code=code, name=code, category=cat, style=style, color="#445566", is_starter=True)
        self.coat = Item.objects.create(code="coat", name="もみじコート", category="top", style="tshirt",
                                        color="#C0392B", rarity=4)
        DropEntry.objects.create(symbol=self.symbol, item=self.coat, season=self.season)

    def test_login_page_shows_limited_coords(self):
        res = self.client.get(reverse("accounts:login"))
        self.assertContains(res, "いま、まちで手に入るコーデ")
        self.assertContains(res, "もみじコート")
        self.assertContains(res, "ほたる公園")
        self.assertContains(res, reverse("core:showcase_svg", args=[0]))
        svg = self.client.get(reverse("core:showcase_svg", args=[0]))  # ログインしていなくても見られる
        self.assertEqual(svg.status_code, 200)
        self.assertEqual(svg["Content-Type"], "image/svg+xml; charset=utf-8")
        self.assertIn(b"#C0392B", svg.content)  # 主役のアイテムを着ている
        self.assertIn(b"#445566", svg.content)  # ほかは初期アイテム
        self.assertEqual(self.client.get(reverse("core:showcase_svg", args=[1])).status_code, 404)

    def test_secret_hidden_and_off_season_items_are_not_shown(self):
        secret_sym = Symbol.objects.create(spot=self.spot, name="ひみつ", is_secret=True)
        secret = Item.objects.create(code="fox", name="狐のお面", category="accessory", style="ribbon", color="#CC2222",
                                     rarity=5)
        DropEntry.objects.create(symbol=secret_sym, item=secret, season=self.season)
        hidden_spot = Spot.objects.create(slug="h", name="非公開の店", is_active=False)
        hidden = Item.objects.create(code="hid", name="非公開のぼうし", category="accessory", style="ribbon",
                                     color="#123456", rarity=5)
        DropEntry.objects.create(symbol=Symbol.objects.create(spot=hidden_spot, name="x"), item=hidden,
                                 season=self.season)
        other = next(s for s in ("spring", "summer", "autumn", "winter") if s != self.season)
        off = Item.objects.create(code="off", name="季節はずれ", category="top", style="tshirt", color="#000000",
                                  rarity=5)
        DropEntry.objects.create(symbol=self.symbol, item=off, season=other)
        page = self.client.get(reverse("accounts:login"))
        for name in ("狐のお面", "非公開のぼうし", "季節はずれ", "ひみつ"):
            self.assertNotContains(page, name)
        self.assertContains(page, "もみじコート")

    def test_no_limited_items_hides_section(self):
        DropEntry.objects.all().delete()
        page = self.client.get(reverse("accounts:login"))
        self.assertNotContains(page, "いま、まちで手に入るコーデ")
        self.assertEqual(self.client.get(reverse("core:showcase_svg", args=[0])).status_code, 404)


class TrustHelpTests(SimpleTestCase):
    def load(self):
        spec = importlib.util.spec_from_file_location("devproxy", settings.BASE_DIR / "scripts" / "devproxy.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_help_uses_project_relative_path(self):
        # PowerShell では %LOCALAPPDATA% が展開されないため、どちらのシェルでも使える相対パスで案内する
        text = self.load().trust_help()
        self.assertIn('certutil -user -addstore Root "certs\\localhost.crt"', text)
        self.assertNotIn("%LOCALAPPDATA%", text)

    def test_export_writes_public_cert_only(self):
        import tempfile
        from pathlib import Path

        dp = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            dp.CERT, dp.KEY = Path(tmp) / "p" / "localhost.crt", Path(tmp) / "p" / "localhost.key"
            dp.EXPORT_CERT = Path(tmp) / "project" / "certs" / "localhost.crt"
            with mock.patch("builtins.print"):
                dp.write_cert()  # 作ると同時に書き出す
                self.assertEqual(dp.EXPORT_CERT.read_bytes(), dp.CERT.read_bytes())
                self.assertFalse(dp.export_cert())  # 同じ中身なら書かない
                self.assertEqual(sorted(p.name for p in dp.EXPORT_CERT.parent.iterdir()), ["localhost.crt"])
                self.assertNotIn(b"PRIVATE KEY", dp.EXPORT_CERT.read_bytes())

    def test_is_trusted_uses_current_user_root_store(self):
        dp = self.load()
        with mock.patch.object(dp, "CERT") as cert, mock.patch.object(dp, "cert_thumbprint", return_value="AB12"), \
                mock.patch.object(dp.os, "name", "nt"), mock.patch.object(dp.subprocess, "run") as run:
            cert.exists.return_value = True
            run.return_value.returncode = 0
            self.assertTrue(dp.is_trusted())
            self.assertEqual(run.call_args.args[0], ["certutil", "-user", "-store", "Root", "AB12"])
            run.return_value.returncode = 1
            self.assertFalse(dp.is_trusted())

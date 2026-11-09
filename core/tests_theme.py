"""UI テーマ (デザイン案) の切り替えと、仮想写真・1 画面ホームのテスト。"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from contest.models import Contest
from core.models import AuditLog, SiteSetting
from core.themes import THEMES
from core.views import PHOTOS, travel_rank
from wardrobe.models import Item
from wardrobe.services import ensure_starter_kit

PW = "correct horse battery staple"


def set_theme(key: str) -> None:
    s = SiteSetting.current()
    s.ui_theme = key
    s.save()


class ThemeSwitchTests(TestCase):
    def setUp(self):
        cache.clear()
        Item.objects.create(code="h", name="髪", category="hair", style="bob", color="#6B4226", body_type="girl", is_starter=True)
        Item.objects.create(code="bg", name="背景", category="background", style="stage", color="#E85A9A", is_starter=True)
        self.user = User.objects.create_user("u@example.com", PW, "ゆーざー")
        ensure_starter_kit(self.user)
        self.staff = User.objects.create_user("s@example.com", PW, "すたっふ", is_staff=True, is_superuser=True)
        ensure_starter_kit(self.staff)

    def test_default_is_standard(self):
        res = self.client.get("/")
        self.assertTemplateUsed(res, "core/landing_standard.html")
        self.assertContains(res, "theme-standard")
        self.assertNotContains(res, "/css/themes/")

    def test_each_theme_switches_landing_home_and_css(self):
        for key, theme in THEMES.items():
            with self.subTest(theme=key):
                set_theme(key)
                self.client.logout()
                res = self.client.get("/")
                self.assertTemplateUsed(res, f"core/landing_{theme.landing}.html")
                self.assertContains(res, f"theme-{key}")
                if theme.css:
                    self.assertContains(res, f"/static/css/themes/{theme.css}")
                self.client.force_login(self.user)
                res = self.client.get("/")
                self.assertTemplateUsed(res, f"core/home_{theme.home}.html")
                # ほかのページにもテーマが効く
                self.assertContains(self.client.get(reverse("wardrobe:index")), f"theme-{key}")

    def test_landing_uses_virtual_photos_with_disclaimer(self):
        for key in ("standard", "game", "magazine"):
            with self.subTest(theme=key):
                set_theme(key)
                res = self.client.get("/")
                self.assertContains(res, "/static/img/photos/")
                self.assertContains(res, "CGによるイメージ")

    def test_game_home_is_one_screen_with_status(self):
        now = timezone.now()
        Contest.objects.create(title="テスト大会", starts_at=now - dt.timedelta(hours=1), ends_at=now + dt.timedelta(days=1))
        set_theme("game")
        self.client.force_login(self.user)
        res = self.client.get("/")
        for text in ("旅ランク", "イベント開催中!", "テスト大会", "みっけに行く", "メニュー", "ゆーざーさん", "?layer=avatar", "?layer=bg"):
            self.assertContains(res, text)
        self.assertNotContains(res, 'class="site-header"')  # 1 画面ホームは上部ステータスバーに置き換え

    def test_staff_can_preview_only_for_themselves(self):
        self.client.force_login(self.staff)
        res = self.client.get("/?ui=magazine")
        self.assertTemplateUsed(res, "core/home_magazine.html")
        self.assertContains(res, "管理者プレビュー")
        self.assertTemplateUsed(self.client.get("/"), "core/home_magazine.html")  # セッションに残る
        self.assertEqual(SiteSetting.current().ui_theme, "standard")  # 全体設定は変わらない
        self.assertTemplateUsed(self.client.get("/?ui=reset"), "core/home_standard.html")

    def test_non_staff_cannot_preview(self):
        self.client.force_login(self.user)
        res = self.client.get("/?ui=game")
        self.assertTemplateUsed(res, "core/home_standard.html")
        self.assertNotContains(res, "管理者プレビュー")
        self.client.logout()
        self.assertTemplateUsed(self.client.get("/?ui=game"), "core/landing_standard.html")

    def test_unknown_theme_param_ignored(self):
        self.client.force_login(self.staff)
        self.assertTemplateUsed(self.client.get("/?ui=../../evil"), "core/home_standard.html")

    def test_admin_switches_theme_for_everyone(self):
        self.client.force_login(self.staff)
        url = reverse("admin:core_sitesetting_change", args=[SiteSetting.current().pk])
        page = self.client.get(url)
        self.assertContains(page, "ゲームホーム")
        self.assertContains(page, "自分だけ試す")
        res = self.client.post(url, {"ui_theme": "game"})
        self.assertEqual(res.status_code, 302)
        self.assertEqual(SiteSetting.current().ui_theme, "game")
        self.assertEqual(SiteSetting.current().updated_by, self.staff)
        self.assertTrue(AuditLog.objects.filter(action="site.ui_theme").exists())
        self.client.logout()
        self.assertTemplateUsed(self.client.get("/"), "core/landing_game.html")  # 未ログインの人にも反映

    def test_admin_singleton(self):
        self.client.force_login(self.staff)
        SiteSetting.current()
        self.assertEqual(self.client.get(reverse("admin:core_sitesetting_add")).status_code, 403)
        changelist = self.client.get(reverse("admin:core_sitesetting_changelist"))
        self.assertEqual(changelist.status_code, 302)  # 一覧ではなく設定画面へ
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("admin:core_sitesetting_changelist")).status_code, 302)  # 一般利用者は入れない

    def test_db_constraint(self):
        SiteSetting.current()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SiteSetting.objects.filter(pk=1).update(ui_theme="nope")

    def test_avatar_layers(self):
        self.client.force_login(self.user)
        bg = self.client.get(reverse("wardrobe:avatar_svg"), {"layer": "bg"}).content.decode()
        self.assertIn("xMidYMid slice", bg)
        self.assertNotIn("<ellipse cx=\"82\" cy=\"104\"", bg)  # 背景だけ (顔なし)
        av = self.client.get(reverse("wardrobe:avatar_svg"), {"layer": "avatar"}).content.decode()
        self.assertIn("<ellipse cx=\"82\" cy=\"104\"", av)
        self.assertNotIn("bg-stage", av)  # 背景なし


class PhotoTests(TestCase):
    def test_photos_exist_and_are_safe_svgs(self):
        base = Path(settings.BASE_DIR) / "static" / "img" / "photos"
        for key, _title, _ in PHOTOS:
            with self.subTest(photo=key):
                text = (base / f"{key}.svg").read_text(encoding="utf-8")
                self.assertTrue(text.startswith("<svg"))
                self.assertIn("CG によるイメージ", text)  # 実写ではないことを明記
                self.assertNotIn("<script", text)
                self.assertNotIn("http://", text.replace("http://www.w3.org/2000/svg", ""))  # 外部参照なし
                self.assertLess(len(text), 60_000)

    def test_travel_rank(self):
        self.assertEqual([travel_rank(n) for n in (0, 3, 10, 25, 50, 100, 500)], ["E", "D", "C", "B", "A", "S", "S"])

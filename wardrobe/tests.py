from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.models import User
from wardrobe.avatar import Part, render_svg, safe_color, shade
from wardrobe.models import AvatarConfig, Item, UserItem
from wardrobe.services import EquipError, VersionConflict, ensure_starter_kit, equip


class AvatarRenderTests(SimpleTestCase):
    def test_renders_all_styles(self):
        from wardrobe.avatar import STYLES

        for cat, styles in STYLES.items():
            for style in styles:
                svg = render_svg("tone3", {cat: Part(cat, style, "#123456", "x")})
                self.assertTrue(svg.startswith("<svg"))
                self.assertIn("#123456", svg)

    def test_invalid_color_is_neutralized(self):
        evil = '#000"/><script>alert(1)</script>'
        svg = render_svg("tone3", {"top": Part("top", "tshirt", evil, "x")})
        self.assertNotIn("<script", svg)
        self.assertEqual(safe_color(evil), "#888888")

    def test_label_is_escaped(self):
        svg = render_svg("tone3", {"top": Part("top", "tshirt", "#111111", '<img onerror=x>')})
        self.assertNotIn("<img", svg)

    def test_shade(self):
        self.assertEqual(shade("#FFFFFF", 0.5), "#7F7F7F")


class WardrobeTests(TestCase):
    def setUp(self):
        self.hair = Item.objects.create(code="h1", name="髪1", category="hair", style="short", color="#111111", is_starter=True)
        self.top = Item.objects.create(code="t1", name="服1", category="top", style="tshirt", color="#EEEEEE", is_starter=True)
        self.rare = Item.objects.create(code="t2", name="法被", category="top", style="happi", color="#C0392B", rarity=3)
        self.user = User.objects.create_user("w@example.com", "correct horse battery staple", "わ")
        self.other = User.objects.create_user("o@example.com", "correct horse battery staple", "お")
        ensure_starter_kit(self.user)
        ensure_starter_kit(self.other)

    def sel(self, **kw):
        base = {"hair": self.hair.pk, "top": self.top.pk, "bottom": None, "shoes": None, "accessory": None}
        base.update(kw)
        return base

    def test_equip_owned(self):
        UserItem.objects.create(user=self.user, item=self.rare)
        cfg = equip(self.user, expected_version=1, skin_tone="tone5", selections=self.sel(top=self.rare.pk))
        self.assertEqual(cfg.top, self.rare)
        self.assertEqual(cfg.version, 2)

    def test_cannot_equip_unowned(self):
        with self.assertRaises(EquipError):
            equip(self.user, expected_version=1, skin_tone="tone3", selections=self.sel(top=self.rare.pk))

    def test_cannot_equip_wrong_category(self):
        with self.assertRaises(EquipError):
            equip(self.user, expected_version=1, skin_tone="tone3", selections=self.sel(hair=self.top.pk))

    def test_optimistic_lock(self):
        equip(self.user, expected_version=1, skin_tone="tone2", selections=self.sel())
        with self.assertRaises(VersionConflict):
            equip(self.user, expected_version=1, skin_tone="tone4", selections=self.sel())

    def test_view_rejects_unowned_item(self):
        self.client.force_login(self.user)
        res = self.client.post(reverse("wardrobe:index"), {
            "version": 1, "skin_tone": "tone3", "hair": self.hair.pk, "top": self.rare.pk,
            "bottom": "none", "shoes": "none", "accessory": "none"}, follow=True)
        self.assertContains(res, "持っていないアイテム")
        self.assertEqual(AvatarConfig.objects.get(user=self.user).top, self.top)

    def test_item_svg_requires_ownership(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("wardrobe:item_svg", args=["t2"])).status_code, 404)
        res = self.client.get(reverse("wardrobe:item_svg", args=["t1"]))
        self.assertEqual(res.status_code, 200)
        self.assertIn("sandbox", res.headers["Content-Security-Policy"])

    def test_db_rejects_bad_color(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Item.objects.create(code="bad", name="x", category="top", style="tshirt", color="red")

    def test_db_rejects_bad_rarity(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Item.objects.create(code="bad2", name="x", category="top", style="tshirt", color="#000000", rarity=9)

    def test_avatar_svg_not_cached(self):
        """着せ替え保存直後に古いアバターが表示されないこと (回帰テスト)。"""
        self.client.force_login(self.user)
        res = self.client.get(reverse("wardrobe:avatar_svg"))
        self.assertIn("no-store", res.headers["Cache-Control"])
        self.assertIn("no-store", self.client.get(reverse("wardrobe:preview_svg")).headers["Cache-Control"])

    def test_requires_login(self):
        res = self.client.get(reverse("wardrobe:index"))
        self.assertEqual(res.status_code, 302)

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


class BodyTypeRenderTests(SimpleTestCase):
    def test_both_body_types_and_eye_colors(self):
        from wardrobe.avatar import EYE_COLORS

        for bt in ("girl", "boy"):
            for eye, hexcolor in EYE_COLORS.items():
                with self.subTest(bt=bt, eye=eye):
                    svg = render_svg("tone3", {}, body_type=bt, eye_color=eye)
                    self.assertIn(f"iris-{hexcolor[1:]}", svg)

    def test_girl_has_lashes_boy_does_not(self):
        girl = render_svg("tone3", {}, body_type="girl")
        boy = render_svg("tone3", {}, body_type="boy")
        self.assertEqual(girl.count("<path") - boy.count("<path"), 4)  # まつ毛 2 本 × 両目

    def test_unknown_values_fall_back(self):
        svg = render_svg("nope", {}, body_type="<x>", eye_color="<y>")
        self.assertNotIn("<x>", svg)
        self.assertNotIn("<y>", svg)


class SampleItemsTests(SimpleTestCase):
    """サンプルパーツは女の子用・男の子用それぞれ 50 種類。"""

    def test_fifty_each_and_valid(self):
        from collections import Counter

        from wardrobe.avatar import STYLES
        from wardrobe.sample_items import BOY_ITEMS, GIRL_ITEMS, SAMPLE_ITEMS

        self.assertEqual(len(GIRL_ITEMS), 50)
        self.assertEqual(len(BOY_ITEMS), 50)
        codes = [row[0] for row in SAMPLE_ITEMS]
        self.assertEqual(len(codes), len(set(codes)), "コードが重複しています")
        for code, _name, cat, style, color, rarity, _starter, _desc, _body in SAMPLE_ITEMS:
            with self.subTest(code=code):
                self.assertIn(style, STYLES[cat])
                self.assertRegex(color, r"^#[0-9A-Fa-f]{6}$")
                self.assertTrue(1 <= rarity <= 5)
        for rows in (GIRL_ITEMS, BOY_ITEMS):
            starters = Counter(r[2] for r in rows if r[6])
            self.assertEqual(set(starters), {"hair", "top", "bottom", "shoes"})  # 各タイプに初期セット


class BodyTypeEquipTests(TestCase):
    def setUp(self):
        mk = lambda code, cat, style, body, **kw: Item.objects.create(  # noqa: E731
            code=code, name=code, category=cat, style=style, color="#336699", body_type=body, **kw)
        self.g_hair = mk("gh", "hair", "twintail", "girl", is_starter=True)
        self.b_hair = mk("bh", "hair", "spiky", "boy", is_starter=True)
        self.any_top = mk("at", "top", "tshirt", "any", is_starter=True)
        self.rare = mk("rare", "top", "idol", "girl", rarity=5)
        self.user = User.objects.create_user("u@example.com", "correct horse battery staple", "ゆーざー")
        self.staff = User.objects.create_user("s@example.com", "correct horse battery staple", "すたっふ", is_staff=True)
        ensure_starter_kit(self.user, body_type="girl")
        ensure_starter_kit(self.staff, body_type="boy")

    def sel(self, **kw):
        base = {"hair": None, "top": None, "bottom": None, "shoes": None, "accessory": None}
        base.update(kw)
        return base

    def test_starter_kit_matches_body_type(self):
        self.assertEqual(AvatarConfig.objects.get(user=self.user).hair, self.g_hair)
        self.assertEqual(AvatarConfig.objects.get(user=self.staff).hair, self.b_hair)
        self.assertEqual(self.user.items.count(), 3)  # 両タイプの初期アイテムを持つ

    def test_user_can_switch_body_type_freely(self):
        cfg = equip(self.user, expected_version=1, skin_tone="tone3", body_type="boy", eye_color="green",
                    selections=self.sel(hair=self.b_hair.pk, top=self.any_top.pk))
        self.assertEqual((cfg.body_type, cfg.eye_color, cfg.hair), ("boy", "green", self.b_hair))

    def test_user_cannot_wear_other_type_item(self):
        with self.assertRaisesMessage(EquipError, "男の子用"):
            equip(self.user, expected_version=1, skin_tone="tone3", body_type="girl", selections=self.sel(hair=self.b_hair.pk))

    def test_user_cannot_wear_unowned(self):
        with self.assertRaises(EquipError):
            equip(self.user, expected_version=1, skin_tone="tone3", selections=self.sel(top=self.rare.pk))

    def test_staff_can_choose_any_item(self):
        """管理者は持っていないパーツも、別のタイプのパーツも自由に選べる。"""
        cfg = equip(self.staff, expected_version=1, skin_tone="tone3", body_type="boy",
                    selections=self.sel(hair=self.g_hair.pk, top=self.rare.pk))
        self.assertEqual((cfg.hair, cfg.top), (self.g_hair, self.rare))
        self.assertFalse(UserItem.objects.filter(user=self.staff, item=self.rare).exists())  # 付与はしない

    def test_staff_still_cannot_use_wrong_category(self):
        with self.assertRaises(EquipError):
            equip(self.staff, expected_version=1, skin_tone="tone3", selections=self.sel(hair=self.rare.pk))

    def test_invalid_body_or_eye_rejected(self):
        for kw in ({"body_type": "robot"}, {"eye_color": "red"}):
            with self.subTest(kw=kw), self.assertRaises(EquipError):
                equip(self.user, expected_version=1, skin_tone="tone3", selections=self.sel(), **kw)

    def test_db_constraints(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Item.objects.create(code="x", name="x", category="top", style="tshirt", color="#000000", body_type="cat")
        cfg = AvatarConfig.objects.get(user=self.user)
        cfg.eye_color = "red"
        with self.assertRaises(IntegrityError), transaction.atomic():
            cfg.save()

    def test_wardrobe_page_lists_by_role(self):
        self.client.force_login(self.user)
        page = self.client.get(reverse("wardrobe:index"))
        self.assertNotContains(page, "管理者モード")
        self.assertNotContains(page, "/items/rare.svg")  # 未所持は出ない
        self.client.force_login(self.staff)
        page = self.client.get(reverse("wardrobe:index"))
        self.assertContains(page, "管理者モード")
        self.assertContains(page, "/items/rare.svg")
        self.assertContains(page, "未所持")

    def test_staff_preview_and_item_svg_for_unowned(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("wardrobe:item_svg", args=["rare"])).status_code, 200)
        res = self.client.get(reverse("wardrobe:preview_svg"), {"top": self.rare.pk, "body_type": "girl", "eye_color": "pink"})
        self.assertIn(b"#336699", res.content)
        self.client.force_login(self.user)
        res = self.client.get(reverse("wardrobe:preview_svg"), {"top": self.rare.pk})
        self.assertNotIn(b"#336699", res.content)  # 一般利用者は未所持を反映しない

    def test_catalog_staff_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("wardrobe:catalog")).status_code, 302)
        self.client.force_login(self.staff)
        res = self.client.get(reverse("wardrobe:catalog"))
        self.assertContains(res, "女の子用")
        self.assertContains(res, "男の子用")

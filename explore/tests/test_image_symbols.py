"""画像シンボル (撮影した写真をシンボルにする機能) のテスト。

- 四角形で切り抜いた写真・塗りつぶしマスク・最大 9 角度の見え方
- 類似度 65% 以上で一致とするゆるやかな判定
"""

from __future__ import annotations

import base64
import json
import random
import uuid

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from core.models import AuditLog
from explore import services
from explore.image_symbols import (
    MASK_BYTES,
    ImageSymbolError,
    decode_mask,
    jpeg_dimensions,
    ncc,
    parse_features,
    similarity,
    validate_jpeg,
    validate_reference,
)
from explore.models import ANGLES, DropEntry, Spot, Symbol, SymbolView
from explore.services import ViewUpload
from wardrobe.models import Item

PW = "correct horse battery staple"


def fake_jpeg(w: int = 640, h: int = 480) -> bytes:
    """SOF0 を持つ最小の JPEG バイト列 (ヘッダー解析のテスト用)。"""
    sof = (b"\xff\xc0" + (17).to_bytes(2, "big") + b"\x08" + h.to_bytes(2, "big") + w.to_bytes(2, "big")
           + b"\x03" + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01")
    app0 = b"\xff\xe0" + (16).to_bytes(2, "big") + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


def fake_features(n: int = 60, w: int = 480, h: int = 320, seed: int = 1) -> dict:
    rnd = random.Random(seed)
    kp = [[round(rnd.uniform(0, w), 1), round(rnd.uniform(0, h), 1)] for _ in range(n)]
    desc = bytes(rnd.getrandbits(8) for _ in range(n * 32))
    return {"v": 1, "w": w, "h": h, "kp": kp, "desc": base64.b64encode(desc).decode()}


def blocky_patch(seed: int = 7, block: int = 4) -> bytes:
    """看板の写真に近い「ある程度まとまった模様」の 32x32 パッチ。"""
    rnd = random.Random(seed)
    n = 32 // block
    cells = [[rnd.randrange(256) for _ in range(n)] for _ in range(n)]
    return bytes(cells[y // block][x // block] for y in range(32) for x in range(32))


def shifted(p: bytes, dx: int, dy: int) -> bytes:
    """パッチを dx, dy ピクセルずらす (はみ出した部分は端の値で埋める)。"""
    out = bytearray(1024)
    for y in range(32):
        for x in range(32):
            sx, sy = min(max(x - dx, 0), 31), min(max(y - dy, 0), 31)
            out[y * 32 + x] = p[sy * 32 + sx]
    return bytes(out)


def mask_bits(pred) -> bytes:
    """pred(x, y) が True のセルを除外するマスク。"""
    bits = bytearray(MASK_BYTES)
    for i in range(1024):
        if pred(i % 32, i // 32):
            bits[i >> 3] |= 0x80 >> (i & 7)
    return bytes(bits)


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def upload(seed: int = 7, mask: bytes | None = None, n: int = 60) -> ViewUpload:
    return ViewUpload(jpeg=fake_jpeg(), features_raw=json.dumps(fake_features(n=n, seed=seed)).encode(),
                      patch_b64=b64(blocky_patch(seed)), mask_b64=b64(mask) if mask else None)


class JpegTests(TestCase):
    def test_dimensions(self):
        self.assertEqual(jpeg_dimensions(fake_jpeg(900, 600)), (900, 600))

    def test_not_jpeg(self):
        for bad in [b"", b"\x89PNG\r\n\x1a\n" + b"0" * 20, b"<svg></svg>", b"\xff\xd8\xff"]:
            with self.subTest(bad=bad[:8]), self.assertRaises(ImageSymbolError):
                jpeg_dimensions(bad)

    def test_size_limits(self):
        for bad in [fake_jpeg(4000, 3000), fake_jpeg(32, 32), fake_jpeg() + b"\x00" * 1_600_000]:
            with self.subTest(len=len(bad)), self.assertRaises(ImageSymbolError):
                validate_jpeg(bad)


class FeatureParseTests(TestCase):
    def test_valid(self):
        f = parse_features(json.dumps(fake_features()).encode())
        self.assertEqual((len(f["kp"]), f["w"]), (60, 480))

    def test_too_few_keypoints(self):
        with self.assertRaisesMessage(ImageSymbolError, "特徴が少なすぎます"):
            parse_features(json.dumps(fake_features(n=10)).encode())

    def test_malformed(self):
        f = fake_features()
        f["desc"] = b64(b"\x00" * 31)
        bad_desc = json.dumps(f).encode()
        f = fake_features()
        f["kp"][0] = [9999, 1]
        out_of_range = json.dumps(f).encode()
        nan = json.dumps(fake_features()).replace("[", "[NaN, 0], [", 2).encode()
        for raw in [bad_desc, out_of_range, nan, b"not json", b"[]", b'{"v": 2}']:
            with self.subTest(raw=raw[:20]), self.assertRaises(ImageSymbolError):
                parse_features(raw)


class SimilarityTests(TestCase):
    """類似度 (0〜1) と 65% のしきい値。"""

    def test_identical_and_lighting(self):
        p = blocky_patch()
        self.assertAlmostEqual(similarity(p, bytes(MASK_BYTES), p), 1.0, places=5)
        darker = bytes(min(255, int(v * 0.6) + 20) for v in p)
        self.assertGreater(similarity(p, bytes(MASK_BYTES), darker), 0.95)

    def test_tolerates_small_misalignment(self):
        """距離・角度のずれで少し位置がずれても 65% 以上になる。"""
        p = blocky_patch(block=8)
        for dx, dy in [(2, 0), (0, 2), (-2, 2), (1, -1)]:
            with self.subTest(dx=dx, dy=dy):
                self.assertGreaterEqual(similarity(p, bytes(MASK_BYTES), shifted(p, dx, dy)), 0.65)

    def test_unrelated_is_below_threshold(self):
        for a, b in [(1, 2), (3, 4), (5, 6), (7, 8)]:
            with self.subTest(a=a, b=b):
                self.assertLess(similarity(blocky_patch(a), bytes(MASK_BYTES), blocky_patch(b)), 0.65)

    def test_masked_area_is_ignored(self):
        """塗りつぶした部分 (例: 通行人) が違っていても、残りが同じなら一致する。"""
        ref = blocky_patch(10)
        noise = blocky_patch(99)
        observed = bytes(noise[i] if (i % 32) >= 20 else ref[i] for i in range(1024))  # 右側だけ別物
        mask = mask_bits(lambda x, y: x >= 20)
        self.assertGreaterEqual(similarity(ref, mask, observed), 0.95)
        self.assertLess(similarity(ref, bytes(MASK_BYTES), observed), similarity(ref, mask, observed))

    def test_plain_ncc(self):
        p = blocky_patch()
        self.assertAlmostEqual(ncc(p, bytes(255 - v for v in p)), -1.0, places=5)
        self.assertEqual(ncc(bytes(1024), p), 0.0)


class MaskValidationTests(TestCase):
    def test_decode_mask(self):
        self.assertEqual(decode_mask(None), bytes(MASK_BYTES))
        for bad in ["%%", b64(b"\x00" * 10)]:
            with self.subTest(bad=bad), self.assertRaises(ImageSymbolError):
                decode_mask(bad)

    def test_too_much_masked(self):
        with self.assertRaisesMessage(ImageSymbolError, "塗りつぶした部分が多すぎます"):
            validate_reference(blocky_patch(), mask_bits(lambda x, y: x >= 6))  # 約 81% 除外

    def test_low_contrast_visible_part(self):
        flat_left = bytes(128 if (i % 32) < 16 else blocky_patch()[i] for i in range(1024))
        with self.assertRaisesMessage(ImageSymbolError, "メリハリ"):
            validate_reference(flat_left, mask_bits(lambda x, y: x >= 16))  # 見える部分が無地


class ImageSymbolServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("u@example.com", PW, "ゆーざー")
        self.staff = User.objects.create_user("s@example.com", PW, "すたっふ", role="operator")
        self.spot = Spot.objects.create(slug="s", name="テスト温泉")
        self.symbol = services.register_image_symbol(
            spot=self.spot, name="看板", hint="", cooldown_hours=20,
            uploads={"front": upload(7), "right": upload(8)}, created_by=self.staff,
        )
        item = Item.objects.create(code="i", name="法被", category="top", style="happi", color="#C0392B")
        DropEntry.objects.create(symbol=self.symbol, item=item)

    def test_registered_with_views(self):
        self.assertEqual(self.symbol.kind, Symbol.KIND_IMAGE)
        self.assertEqual(sorted(self.symbol.views.values_list("angle", flat=True)), ["front", "right"])
        v = self.symbol.views.get(angle="front")
        self.assertEqual((v.width, v.height, v.keypoint_count, bytes(v.verify_mask)), (640, 480, 60, bytes(MASK_BYTES)))

    def test_requires_at_least_one_view(self):
        with self.assertRaises(ImageSymbolError):
            services.register_image_symbol(spot=self.spot, name="空", hint="", cooldown_hours=20, uploads={},
                                           created_by=self.staff)

    def test_error_names_the_angle_and_rolls_back(self):
        with self.assertRaisesMessage(ImageSymbolError, "【右から】"):
            services.register_image_symbol(
                spot=self.spot, name="失敗", hint="", cooldown_hours=20,
                uploads={"front": upload(1), "right": upload(2, n=5)}, created_by=self.staff,
            )
        self.assertFalse(Symbol.objects.filter(name="失敗").exists())

    def test_scan_matches_any_registered_angle(self):
        rnd = random.Random(3)
        for seed in (7, 8):  # 正面・右から どちらの見え方でも一致
            with self.subTest(seed=seed):
                cache.clear()
                p = blocky_patch(seed)
                observed = bytes(max(0, min(255, int(v * 0.7) + 30 + rnd.randint(-15, 15))) for v in p)
                res = services.scan_image(self.user, self.symbol.pk, b64(observed))
                self.assertEqual(res["status"], "ready")
        r = services.collect(self.user, res["ticket"], str(uuid.uuid4()))
        self.assertEqual(r.reward_kind, "item")

    def test_scan_rejects_unrelated_or_malformed(self):
        for bad in [b64(blocky_patch(99)), b64(b"\x00" * 10), "%%%", ""]:
            with self.subTest(bad=bad[:10]), self.assertRaises(services.UnknownSymbol):
                services.scan_image(self.user, self.symbol.pk, bad)
        for bad_id in [None, "abc", 999999]:
            with self.subTest(bad_id=bad_id), self.assertRaises(services.UnknownSymbol):
                services.scan_image(self.user, bad_id, b64(blocky_patch(7)))

    @override_settings(MIKKE_IMAGE_SIMILARITY_THRESHOLD=0.999)
    def test_threshold_is_configurable(self):
        observed = shifted(blocky_patch(7), 1, 0)  # 1px ずれ = 完全一致ではない (約 0.9)
        with self.assertRaises(services.UnknownSymbol):
            services.scan_image(self.user, self.symbol.pk, b64(observed))

    def test_image_symbol_not_reachable_via_qr_payload(self):
        with self.assertRaises(services.UnknownSymbol):
            services.scan(self.user, self.symbol.payload)

    def test_inactive_hidden(self):
        self.symbol.is_active = False
        self.symbol.save()
        with self.assertRaises(services.UnknownSymbol):
            services.scan_image(self.user, self.symbol.pk, b64(blocky_patch(7)))
        self.assertEqual(services.image_symbol_catalog(), [])

    def test_catalog_per_view_without_secrets(self):
        cat = services.image_symbol_catalog()
        self.assertEqual([(c["id"], c["view"]) for c in cat], [(self.symbol.pk, "front"), (self.symbol.pk, "right")])
        self.assertEqual(set(cat[0]), {"id", "view", "v", "w", "h", "kp", "desc"})
        self.assertNotIn(b64(blocky_patch(7)), json.dumps(cat))

    def test_save_views_add_replace_delete(self):
        services.save_symbol_views(self.symbol, {"up": upload(11), "front": upload(12)}, ["right"], self.staff)
        self.assertEqual(sorted(self.symbol.views.values_list("angle", flat=True)), ["front", "up"])
        self.assertEqual(bytes(self.symbol.views.get(angle="front").verify_patch), blocky_patch(12))

    def test_cannot_delete_last_view(self):
        with self.assertRaisesMessage(ImageSymbolError, "少なくとも 1 つ"):
            services.save_symbol_views(self.symbol, {}, ["front", "right"], self.staff)
        self.assertEqual(self.symbol.views.count(), 2)  # 巻き戻る

    def test_nine_angles_max(self):
        services.save_symbol_views(self.symbol, {a: upload(i) for i, a in enumerate(ANGLES)}, [], self.staff)
        self.assertEqual(self.symbol.views.count(), 9)
        with self.assertRaises(ImageSymbolError):
            services.save_symbol_views(self.symbol, {"back": upload(1)}, [], self.staff)


class ImageSymbolViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("u@example.com", PW, "ゆーざー")
        self.staff = User.objects.create_user("s@example.com", PW, "すたっふ", role="operator")
        self.spot = Spot.objects.create(slug="s", name="テスト温泉")

    def view_files(self, angle: str, seed: int = 7, features=None, jpeg=None, mask=None) -> dict:
        data = {
            f"{angle}_image": SimpleUploadedFile(f"{angle}.jpg", jpeg or fake_jpeg(), content_type="image/jpeg"),
            f"{angle}_features": SimpleUploadedFile(f"{angle}.json", json.dumps(features or fake_features(seed=seed)).encode(),
                                                    content_type="application/json"),
            f"{angle}_patch": b64(blocky_patch(seed)),
        }
        if mask is not None:
            data[f"{angle}_mask"] = b64(mask)
        return data

    def post_register(self, angles=("front",), **kw):
        data = {"spot": self.spot.pk, "name": "看板", "hint": "入口", "cooldown_hours": 20, "angles": ",".join(angles)}
        for i, a in enumerate(angles):
            data.update(self.view_files(a, seed=7 + i, **kw))
        return self.client.post(reverse("explore:symbol_register"), data)

    def test_register_requires_staff(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("explore:symbol_register")).status_code, 403)
        self.assertEqual(self.post_register().status_code, 403)
        self.assertFalse(Symbol.objects.filter(kind="image").exists())

    def test_register_multi_angle_with_mask(self):
        self.client.force_login(self.staff)
        page = self.client.get(reverse("explore:symbol_register"))
        self.assertContains(page, "右上から")
        mask = mask_bits(lambda x, y: x >= 24)
        res = self.post_register(angles=("front", "left", "up_right"), mask=mask)
        self.assertEqual(res.status_code, 200, res.content)
        sym = Symbol.objects.get(kind="image")
        self.assertEqual(sorted(sym.views.values_list("angle", flat=True)), ["front", "left", "up_right"])
        self.assertEqual(bytes(sym.views.get(angle="left").verify_mask), mask)
        self.assertTrue(AuditLog.objects.filter(action="symbol.register_image").exists())

    def test_register_rejects_bad_input(self):
        self.client.force_login(self.staff)
        cases = {
            "few_features": dict(features=fake_features(n=5)),
            "not_jpeg": dict(jpeg=b"\x89PNG\r\n\x1a\n" + b"x" * 100),
            "over_masked": dict(mask=mask_bits(lambda x, y: True)),
        }
        for name, kw in cases.items():
            with self.subTest(name):
                res = self.post_register(**kw)
                self.assertEqual(res.status_code, 400)
                self.assertTrue(res.json()["errors"])
        bad_angle = self.client.post(reverse("explore:symbol_register"), {
            "spot": self.spot.pk, "name": "看板", "cooldown_hours": 20, "angles": "behind", **self.view_files("behind")})
        self.assertEqual(bad_angle.status_code, 400)
        no_views = self.client.post(reverse("explore:symbol_register"), {
            "spot": self.spot.pk, "name": "看板", "cooldown_hours": 20, "angles": ""})
        self.assertEqual(no_views.status_code, 400)
        self.assertFalse(Symbol.objects.filter(kind="image").exists())

    def test_register_requires_csrf(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.staff)
        self.assertEqual(client.post(reverse("explore:symbol_register"), {"spot": self.spot.pk}).status_code, 403)

    def test_edit_views(self):
        self.client.force_login(self.staff)
        self.post_register(angles=("front", "right"))
        sym = Symbol.objects.get(kind="image")
        url = reverse("explore:symbol_views", args=[sym.pk])
        page = self.client.get(url)
        self.assertContains(page, "撮り直")
        self.assertContains(page, 'data-existing="1"', count=2)
        res = self.client.post(url, {"angles": "down", "delete": "right", **self.view_files("down", seed=30)})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(sorted(sym.views.values_list("angle", flat=True)), ["down", "front"])
        last = self.client.post(url, {"angles": "", "delete": "front,down"})
        self.assertEqual(last.status_code, 400)
        self.assertEqual(sym.views.count(), 2)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_qr_symbol_has_no_views_page(self):
        self.client.force_login(self.staff)
        qr = Symbol.objects.create(spot=self.spot, name="QR")
        self.assertEqual(self.client.get(reverse("explore:symbol_views", args=[qr.pk])).status_code, 404)

    def test_catalog_api(self):
        self.client.force_login(self.staff)
        self.post_register(angles=("front", "right"))
        self.assertEqual(self.client_class().get(reverse("explore:api_image_symbols")).status_code, 401)
        self.client.force_login(self.user)
        res = self.client.get(reverse("explore:api_image_symbols"))
        self.assertEqual([s["view"] for s in res.json()["symbols"]], ["front", "right"])

    def test_scan_api_with_image(self):
        self.client.force_login(self.staff)
        self.post_register()
        sym = Symbol.objects.get(kind="image")
        self.client.force_login(self.user)
        api = reverse("explore:api_scan")
        ok = self.client.post(api, data=json.dumps({"image_symbol": sym.pk, "patch": b64(shifted(blocky_patch(7), 1, 1))}),
                              content_type="application/json")
        self.assertEqual(ok.status_code, 200)
        self.assertNotIn("similarity", ok.json())  # 類似度の値は返さない
        ng = self.client.post(api, data=json.dumps({"image_symbol": sym.pk, "patch": b64(blocky_patch(42))}),
                              content_type="application/json")
        self.assertEqual(ng.status_code, 404)

    def test_view_photo_is_staff_only(self):
        self.client.force_login(self.staff)
        self.post_register()
        sym = Symbol.objects.get(kind="image")
        url = reverse("explore:symbol_view_image", args=[sym.pk, "front"])
        res = self.client.get(url)
        self.assertEqual((res.status_code, res["Content-Type"]), (200, "image/jpeg"))
        self.assertEqual(self.client.get(reverse("explore:symbol_view_image", args=[sym.pk, "left"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("explore:symbol_svg", args=[sym.pk])).status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_print_page_lists_both_kinds(self):
        self.client.force_login(self.staff)
        self.post_register(angles=("front", "left"))
        Symbol.objects.create(spot=self.spot, name="QR")
        res = self.client.get(reverse("explore:symbol_print"))
        self.assertContains(res, "画像シンボル・2 角度")
        self.assertContains(res, "QR シンボル")


class SymbolViewModelTests(TestCase):
    def test_unique_angle_per_symbol(self):
        from django.db import IntegrityError, transaction

        spot = Spot.objects.create(slug="x", name="x")
        sym = Symbol.objects.create(spot=spot, name="s", kind=Symbol.KIND_IMAGE)
        kw = dict(jpeg=b"x", width=100, height=100, features={}, keypoint_count=30, verify_patch=b"", verify_mask=b"")
        SymbolView.objects.create(symbol=sym, angle="front", **kw)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SymbolView.objects.create(symbol=sym, angle="front", **kw)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SymbolView.objects.create(symbol=sym, angle="behind", **kw)

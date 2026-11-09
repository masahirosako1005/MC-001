from __future__ import annotations

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from maps.views import parse_range


class ParseRangeTests(TestCase):
    def test_ranges(self):
        self.assertEqual(parse_range("bytes=0-126", 1000), (0, 126))
        self.assertEqual(parse_range("bytes=990-", 1000), (990, 999))
        self.assertEqual(parse_range("bytes=-10", 1000), (990, 999))
        self.assertEqual(parse_range("bytes=900-5000", 1000), (900, 999))

    def test_invalid(self):
        for bad in ["bytes=", "bytes=-0", "bytes=5-1", "bytes=1000-", "items=0-1", "bytes=0-1,5-9"]:
            with self.subTest(bad=bad):
                self.assertIsNone(parse_range(bad, 1000))

    def test_too_large_range_rejected(self):
        self.assertIsNone(parse_range("bytes=0-99999999", 10**9))  # 1 回 8MB まで


class PmtilesViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("m@example.com", "correct horse battery staple", "まっぷ")
        self.url = reverse("maps:pmtiles", args=[settings.MIKKE_MAP["tiles"]])
        self.path = settings.MIKKE_TILES_DIR / f"{settings.MIKKE_MAP['tiles']}.pmtiles"

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_range_request_returns_exact_bytes(self):
        self.client.force_login(self.user)
        res = self.client.get(self.url, headers={"Range": "bytes=0-126"})
        self.assertEqual(res.status_code, 206)
        body = res.content
        self.assertEqual(len(body), 127)
        self.assertTrue(body.startswith(b"PMTiles"))  # PMTiles v3 ヘッダー
        self.assertEqual(body, self.path.read_bytes()[:127])
        size = self.path.stat().st_size
        self.assertEqual(res["Content-Range"], f"bytes 0-126/{size}")
        self.assertEqual(res["Accept-Ranges"], "bytes")
        self.assertTrue(res["ETag"])

    def test_full_and_invalid(self):
        self.client.force_login(self.user)
        full = self.client.get(self.url)
        self.assertEqual(full.status_code, 200)
        self.assertEqual(b"".join(full.streaming_content)[:7], b"PMTiles")
        bad = self.client.get(self.url, headers={"Range": "bytes=999999999-"})
        self.assertEqual(bad.status_code, 416)

    def test_unknown_or_traversal_names(self):
        self.client.force_login(self.user)
        for name in ["nothere", "..%2Fsettings", "KYOBASHI"]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(f"/maps/tiles/{name}.pmtiles").status_code, 404)

    def test_spot_page_embeds_local_map(self):
        self.client.force_login(self.user)
        res = self.client.get(reverse("explore:spots"))
        self.assertContains(res, 'id="spot-map"')
        self.assertContains(res, self.url)
        self.assertContains(res, "protomaps-leaflet-5.1.0.js")
        csp = res.headers["Content-Security-Policy"]
        self.assertNotIn("protomaps.com", csp)  # 外部の地図 API を許可していない

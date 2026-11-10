"""結果画面の「こんな人も獲得しているよ」、ログイン画面のランキング (流れる表示)、まちのサイネージのテスト。"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from contest import services as contest_services
from contest.models import Contest, ContestEntry
from core.models import AuditLog
from core.testing import ops_login
from explore import finders
from explore.models import Spot, Symbol
from explore.tests.test_finders import PW, found
from signage.models import Signage
from wardrobe.models import Item

AVATAR = {"body_type": "girl", "skin_tone": "tone3", "eye_color": "brown",
          "parts": {"top": {"style": "tshirt", "color": "#ABCDEF", "name": "見本"}}}


def make_contest(**kw):
    now = timezone.now()
    return Contest.objects.create(title=kw.pop("title", "秋のコーデ大会"), starts_at=kw.pop("starts", now - dt.timedelta(days=1)),
                                  ends_at=kw.pop("ends", now + dt.timedelta(days=1)), **kw)


class ItemFindersTests(TestCase):
    def setUp(self):
        cache.clear()
        self.viewer = User.objects.create_user("v@example.com", PW, "みるひと")
        spot = Spot.objects.create(slug="s", name="森の社", latitude=Decimal("34.69"), longitude=Decimal("135.53"))
        self.symbol = Symbol.objects.create(spot=spot, name="灯籠")
        self.item = Item.objects.create(code="coat", name="もみじコート", category="top", style="tshirt", color="#C0392B")
        self.other = Item.objects.create(code="hat", name="ぼうし", category="hair", style="bob", color="#222222")

    def person(self, i, share=True):
        return User.objects.create_user(f"p{i}@example.com", PW, f"なかま{i}", share_activity=share)

    def test_same_item_latest_three_with_privacy(self):
        a, b, c, d = (self.person(i) for i in range(4))
        hidden = self.person(9, share=False)
        found(a, self.symbol, 60 * 24 * 3, self.item)  # 3 日前
        found(b, self.symbol, 10, self.item)
        found(c, self.symbol, 2, self.item)
        found(d, self.symbol, 60 * 3, self.item)
        found(d, self.symbol, 1, self.other)  # 別のアイテムは数えない
        found(hidden, self.symbol, 1, self.item)  # 表示 OFF の人は出さない
        found(self.person(5), self.symbol, 60 * 24 * 8, self.item)  # 7 日より前は出さない
        found(self.viewer, self.symbol, 0, self.item)  # 自分は出さない
        rows = finders.item_finders("coat", self.viewer)
        self.assertEqual([(r["nickname"], r["ago"]) for r in rows],
                         [("なかま2", "さっき"), ("なかま1", "10分前"), ("なかま3", "3時間前")])
        self.assertTrue(all("token" in r and "user" not in r for r in rows))
        self.assertEqual(finders.item_finders("", self.viewer), [])

    def test_ago_label(self):
        self.assertEqual(finders.ago_label(dt.timedelta(days=2, hours=5)), "2日前")


class PublicRankingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.contest = make_contest()
        self.users = []
        for i, (likes, share) in enumerate([(9, True), (5, False), (3, True), (1, True)]):
            u = User.objects.create_user(f"c{i}@example.com", PW, f"参加{i}", share_activity=share)
            ContestEntry.objects.create(contest=self.contest, user=u, display_name=f"表示名{i}", avatar=AVATAR, likes=likes)
            self.users.append(u)
        ContestEntry.objects.create(contest=self.contest, is_bot=True, display_name="BOT", avatar=AVATAR, likes=99)

    def test_public_top_hides_names_of_people_who_opted_out(self):
        rows = contest_services.public_top(contest_services.featured_contest(), 3)
        self.assertEqual([(r["rank"], r["label"]) for r in rows],
                         [(1, "表示名0"), (2, "2位のコーデ"), (3, "表示名2")])  # BOT は入らない、順位はそのまま

    def test_featured_contest_falls_back_to_latest_finished(self):
        self.contest.ends_at = timezone.now() - dt.timedelta(hours=1)
        self.contest.save()
        older = make_contest(title="夏", starts=timezone.now() - dt.timedelta(days=60),
                             ends=timezone.now() - dt.timedelta(days=30))
        self.assertEqual(contest_services.featured_contest(), self.contest)
        self.assertNotEqual(contest_services.featured_contest(), older)

    def test_login_page_marquee_and_public_avatar(self):
        page = self.client.get(reverse("accounts:login"))
        self.assertContains(page, 'class="marquee"', html=False)
        self.assertContains(page, "ランキング1位")
        self.assertContains(page, "表示名0")
        self.assertNotContains(page, "表示名1")  # 表示 OFF の人の名前は出さない
        self.assertContains(page, "2位のコーデ")
        self.assertContains(page, "marquee.js")
        self.assertContains(page, 'aria-hidden="true"')  # 流すための 2 つ目以降の複製は読み上げない
        svg = self.client.get(reverse("contest:top_svg", args=[1]))
        self.assertEqual(svg.status_code, 200)
        self.assertIn(b"#ABCDEF", svg.content)
        self.assertEqual(self.client.get(reverse("contest:top_svg", args=[4])).status_code, 404)


class SignageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.op = User.objects.create_user("op@example.com", PW, "運営", role=User.ROLE_OPERATOR)
        contest = make_contest()
        self.winner = User.objects.create_user("w@example.com", PW, "勝者", share_activity=True)
        ContestEntry.objects.create(contest=contest, user=self.winner, display_name="ミケ太郎", avatar=AVATAR, likes=7)

    def form(self, **over):
        data = {"name": "京橋駅 北口", "headline": "いまのコーデ王", "message": "京橋のまちで\nコーデをみっけ!",
                "show_qr": "on", "qr_url": "https://mikke.example.jp/", "refresh_seconds": "60", "is_active": "on"}
        data.update(over)
        return {k: v for k, v in data.items() if v is not None}

    def test_operator_creates_and_previews_signage(self):
        ops_login(self.client, self.op)
        self.assertContains(self.client.get(reverse("ops:signage_list")), "サイネージを作る")
        page = self.client.get(reverse("ops:signage_create"))
        self.assertContains(page, "プレビュー")
        self.assertContains(page, "ミケ太郎")  # いまの 1 位でプレビュー
        res = self.client.post(reverse("ops:signage_create"), self.form())
        sign = Signage.objects.get()
        self.assertRedirects(res, reverse("ops:signage_edit", args=[sign.pk]))
        self.assertEqual((sign.updated_by, sign.message), (self.op, "京橋のまちで\nコーデをみっけ!"))
        self.assertTrue(AuditLog.objects.filter(action="signage.create").exists())
        edit = self.client.get(reverse("ops:signage_edit", args=[sign.pk]))
        self.assertContains(edit, reverse("signage:display", args=[sign.display_key]))
        self.assertEqual(self.client.get(reverse("ops:signage_rank1_svg")).status_code, 200)

    def test_validation(self):
        ops_login(self.client, self.op)
        for bad in ({"qr_url": "javascript:alert(1)"}, {"refresh_seconds": "5"}, {"message": "あ" * 201},
                    {"name": ""}):
            res = self.client.post(reverse("ops:signage_create"), self.form(**bad))
            self.assertEqual(res.status_code, 200, bad)
        self.assertFalse(Signage.objects.exists())

    def test_display_is_public_by_key_and_escapes_message(self):
        sign = Signage.objects.create(name="駅", message="<script>alert(1)</script>\n2 行目",
                                      qr_url="https://mikke.example.jp/")
        url = reverse("signage:display", args=[sign.display_key])
        res = self.client.get(url)  # ログイン不要
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "ミケ太郎")
        self.assertContains(res, "&lt;script&gt;")
        self.assertNotContains(res, "<script>alert(1)</script>")
        self.assertContains(res, "<br>2 行目")
        self.assertContains(res, '<meta http-equiv="refresh" content="60">', html=False)
        self.assertContains(res, "<svg")  # QR コード
        self.assertEqual(res["X-Robots-Tag"], "noindex, nofollow")
        self.assertEqual(self.client.get(reverse("signage:rank1_svg", args=[sign.display_key])).status_code, 200)
        # 推測した URL・止めたサイネージ・作り直す前の URL では表示しない
        self.assertEqual(self.client.get(reverse("signage:display", args=["wrong-key"])).status_code, 404)
        sign.is_active = False
        sign.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_winner_name_follows_sharing_setting(self):
        sign = Signage.objects.create(name="駅")
        url = reverse("signage:display", args=[sign.display_key])
        self.assertContains(self.client.get(url), "ミケ太郎")
        self.winner.share_activity = False
        self.winner.save()
        page = self.client.get(url)
        self.assertNotContains(page, "ミケ太郎")
        self.assertContains(page, "1位のコーデ")

    def test_no_ranking_shows_placeholder(self):
        ContestEntry.objects.all().delete()
        sign = Signage.objects.create(name="駅", show_qr=False)
        page = self.client.get(reverse("signage:display", args=[sign.display_key]))
        self.assertContains(page, "ランキング集計中")
        self.assertNotContains(page, "<svg")
        self.assertEqual(self.client.get(reverse("signage:rank1_svg", args=[sign.display_key])).status_code, 404)

    def test_regenerate_key_and_operator_only(self):
        sign = Signage.objects.create(name="駅")
        old = sign.display_key
        user = User.objects.create_user("u@example.com", PW, "ゆーざ")
        self.client.force_login(user)  # 利用者のログインは運営側では読まれない
        self.assertTrue(self.client.get(reverse("ops:signage_list"))["Location"].startswith(reverse("ops:login")))
        ops_login(self.client, self.op)
        self.client.post(reverse("ops:signage_regenerate", args=[sign.pk]))
        sign.refresh_from_db()
        self.assertNotEqual(sign.display_key, old)
        self.assertEqual(self.client.get(reverse("signage:display", args=[old])).status_code, 404)
        self.client.post(reverse("ops:signage_delete", args=[sign.pk]))
        self.assertFalse(Signage.objects.exists())

    def test_manager_can_open_public_pages(self):
        manager = User.objects.create_user("m@example.com", PW, "店長", role=User.ROLE_MANAGER)
        sign = Signage.objects.create(name="駅")
        self.client.force_login(manager)  # 管理者のログイン中でも、公開の表示は管理者の画面へ戻さない
        self.assertEqual(self.client.get(reverse("signage:display", args=[sign.display_key])).status_code, 200)
        self.assertEqual(self.client.get(reverse("contest:top_svg", args=[1])).status_code, 200)

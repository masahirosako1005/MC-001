"""コンテストの仕様 ①〜⑤ のテスト。"""

from __future__ import annotations

import datetime as dt
import os
from collections import Counter

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from contest import services
from contest.models import Contest, ContestEntry, EvaluationRound
from wardrobe.models import Item
from wardrobe.services import ensure_starter_kit

PW = "correct horse battery staple"


def make_users(n: int, prefix: str = "u") -> list[User]:
    users = []
    for i in range(n):
        u = User.objects.create_user(f"{prefix}{i}@example.com", PW, f"{prefix}{i}")
        ensure_starter_kit(u)
        users.append(u)
    return users


class Base(TestCase):
    def setUp(self):
        Item.objects.create(code="h", name="髪", category="hair", style="bob", color="#6B4226", body_type="girl", is_starter=True)
        Item.objects.create(code="t", name="服", category="top", style="tshirt", color="#F2F2F2", body_type="any", is_starter=True)
        Item.objects.create(code="bg", name="背景", category="background", style="stage", color="#E85A9A", body_type="any")
        now = timezone.now()
        self.contest = Contest.objects.create(title="テスト大会", starts_at=now - dt.timedelta(hours=1),
                                              ends_at=now + dt.timedelta(days=1))
        services.create_bots(self.contest, 12)
        self.me = make_users(1, "me")[0]


class EntryTests(Base):
    def test_entry_snapshots_avatar(self):
        e = services.enter(self.contest, self.me, "  ほし  ")
        self.assertEqual(e.display_name, "ほし")
        self.assertEqual(e.avatar["parts"]["hair"]["style"], "bob")
        # あとで着替えてもエントリーの見た目は変わらない
        cfg = self.me.avatar
        cfg.hair = None
        cfg.save()
        e.refresh_from_db()
        self.assertIn("hair", e.avatar["parts"])

    def test_default_name_and_limits(self):
        e = services.enter(self.contest, self.me, "")
        self.assertRegex(e.display_name, r"^旅人#\d{4}$")
        with self.assertRaises(services.ContestError):
            services.clean_display_name("あ" * 21)
        self.assertEqual(services.clean_display_name("ab\u0000c​"), "abc")

    def test_only_once_and_only_while_open(self):
        services.enter(self.contest, self.me)
        with self.assertRaises(services.ContestError):
            services.enter(self.contest, self.me)
        other = make_users(1, "late")[0]
        with self.assertRaises(services.ContestError):
            services.enter(self.contest, other, now=self.contest.ends_at + dt.timedelta(seconds=1))

    def test_db_constraints(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContestEntry.objects.create(contest=self.contest, user=self.me, is_bot=True, display_name="x", avatar={})
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContestEntry.objects.create(contest=self.contest, user=None, is_bot=False, display_name="x", avatar={})


class EvaluationTests(Base):
    def test_requires_entry_first(self):
        with self.assertRaisesMessage(services.ContestError, "先にエントリー"):
            services.current_round(self.contest, self.me)

    def test_three_rounds_of_three(self):
        """③ 3 体 × 3 回。1 回ごとに 1 体まで。"""
        services.enter(self.contest, self.me)
        shown = []
        for n in range(1, 4):
            rnd = services.current_round(self.contest, self.me)
            self.assertEqual(rnd.round_no, n)
            cands = list(rnd.candidates.all())
            self.assertEqual(len(cands), 3)
            shown += [c.pk for c in cands]
            services.vote(self.contest, self.me, rnd.pk, str(cands[0].pk) if n != 2 else None)
        self.assertIsNone(services.current_round(self.contest, self.me))
        self.assertEqual(len(set(shown)), 9, "同じ人の評価で同じアバターは繰り返さない")
        self.assertEqual(EvaluationRound.objects.filter(voter=self.me).count(), 3)

    def test_vote_must_be_from_shown_candidates_and_idempotent(self):
        services.enter(self.contest, self.me)
        rnd = services.current_round(self.contest, self.me)
        not_shown = ContestEntry.objects.exclude(pk__in=rnd.candidates.all()).exclude(user=self.me).first()
        with self.assertRaises(services.ContestError):
            services.vote(self.contest, self.me, rnd.pk, str(not_shown.pk))
        first = rnd.candidates.first()
        services.vote(self.contest, self.me, rnd.pk, str(first.pk))
        second = rnd.candidates.exclude(pk=first.pk).first()
        again = services.vote(self.contest, self.me, rnd.pk, str(second.pk))  # 再送しても最初の回答のまま
        self.assertEqual(again.chosen, first)

    def test_cannot_answer_other_users_round(self):
        services.enter(self.contest, self.me)
        rnd = services.current_round(self.contest, self.me)
        other = make_users(1, "o")[0]
        services.enter(self.contest, other)
        with self.assertRaises(services.ContestError):
            services.vote(self.contest, other, rnd.pk, None)

    def test_own_entry_never_shown(self):
        users = make_users(12, "p")
        for u in users:
            services.enter(self.contest, u)
        services.enter(self.contest, self.me)
        for _ in range(3):
            rnd = services.current_round(self.contest, self.me)
            self.assertFalse(rnd.candidates.filter(user=self.me).exists())
            services.vote(self.contest, self.me, rnd.pk, None)


class SelectionTests(Base):
    def test_prefers_low_impressions(self):
        """④ 表示回数が少ないアバターが優先される。"""
        services.enter(self.contest, self.me)
        bots = list(ContestEntry.objects.filter(contest=self.contest, is_bot=True))
        for i, b in enumerate(bots):
            b.impressions = 0 if i < 3 else 50
            b.save()
        rnd = services.current_round(self.contest, self.me)
        self.assertEqual({c.pk for c in rnd.candidates.all()}, {b.pk for b in bots[:3]})
        for c in rnd.candidates.all():
            self.assertEqual(c.impressions, 1)  # 表示した分だけ増える

    def test_impressions_stay_balanced(self):
        voters = make_users(8, "v")
        for v in voters:  # 全員がエントリーしてから評価する
            services.enter(self.contest, v)
        for v in voters:
            for _ in range(3):
                rnd = services.current_round(self.contest, v)
                services.vote(self.contest, v, rnd.pk, None)
        imps = list(ContestEntry.objects.filter(contest=self.contest).values_list("impressions", flat=True))
        self.assertLessEqual(max(imps) - min(imps), 2, f"表示回数の偏りが大きい: {sorted(imps)}")

    def test_random_within_same_tier(self):
        counts = Counter()
        services.enter(self.contest, self.me)
        pool_ids = set(ContestEntry.objects.filter(is_bot=True).values_list("pk", flat=True))
        for _ in range(60):
            for e in services.pick_candidates(self.contest, self.me, 3):
                counts[e.pk] += 1
        self.assertEqual(set(counts), pool_ids, "同じ表示回数の中ではまんべんなくランダムに選ばれる")


class BotTests(Base):
    def test_bots_shown_until_ten_real_entries(self):
        """⑤ 参加者が 10 人未満なら BOT も候補。10 人以上なら BOT は出ない。"""
        users = make_users(9, "r")
        for u in users:
            services.enter(self.contest, u)
        self.assertTrue(services.bots_visible(self.contest))  # 9 人
        pool = services.pick_candidates(self.contest, users[0], 50)
        self.assertTrue(any(e.is_bot for e in pool))
        services.enter(self.contest, self.me)  # 10 人目
        self.assertFalse(services.bots_visible(self.contest))
        for _ in range(20):
            self.assertFalse(any(e.is_bot for e in services.pick_candidates(self.contest, users[0], 3)))

    def test_bot_votes_not_counted_in_ranking(self):
        services.enter(self.contest, self.me)
        rnd = services.current_round(self.contest, self.me)
        bot = rnd.candidates.filter(is_bot=True).first()
        services.vote(self.contest, self.me, rnd.pk, str(bot.pk))
        bot.refresh_from_db()
        self.assertEqual(bot.likes, 0)
        self.assertEqual(EvaluationRound.objects.get(pk=rnd.pk).chosen, bot)  # 記録は残す
        self.assertTrue(all(not e.is_bot for e in services.ranking(self.contest)))

    def test_real_votes_counted_and_ranked(self):
        users = make_users(10, "q")
        for u in users:
            services.enter(self.contest, u)
        services.enter(self.contest, self.me)
        target = None
        for _ in range(3):
            rnd = services.current_round(self.contest, self.me)
            target = target or rnd.candidates.first()
            pick = rnd.candidates.filter(pk=target.pk).first() or rnd.candidates.first()
            services.vote(self.contest, self.me, rnd.pk, str(pick.pk))
        top = services.ranking(self.contest)[0]
        self.assertEqual(top.likes, 1)
        self.assertEqual(services.rank_of(self.contest, top), 1)


class ViewTests(Base):
    def test_full_flow_via_http(self):
        self.client.force_login(self.me)
        self.assertEqual(self.client.get(reverse("contest:list")).status_code, 200)
        self.assertContains(self.client.get(reverse("contest:detail", args=[self.contest.pk])), "この服装でエントリー")
        # エントリーしていないと評価できない
        res = self.client.get(reverse("contest:evaluate", args=[self.contest.pk]))
        self.assertRedirects(res, reverse("contest:detail", args=[self.contest.pk]), fetch_redirect_response=False)
        res = self.client.post(reverse("contest:enter", args=[self.contest.pk]), {"display_name": "<b>ほし</b>"})
        self.assertRedirects(res, reverse("contest:evaluate", args=[self.contest.pk]), fetch_redirect_response=False)  # ②
        for n in range(1, 4):
            page = self.client.get(reverse("contest:evaluate", args=[self.contest.pk]))
            self.assertContains(page, f"評価 <strong>{n}</strong>")
            rnd = EvaluationRound.objects.get(voter=self.me, answered_at__isnull=True)
            choice = str(rnd.candidates.first().pk)
            self.client.post(reverse("contest:evaluate", args=[self.contest.pk]), {"round": rnd.pk, "choice": choice})
        self.assertContains(self.client.get(reverse("contest:evaluate", args=[self.contest.pk])), "評価ありがとう")
        ranking = self.client.get(reverse("contest:ranking", args=[self.contest.pk]))
        self.assertContains(ranking, "&lt;b&gt;ほし&lt;/b&gt;")  # 表示名はエスケープされる
        self.assertNotContains(ranking, "みっけBOT")

    def test_entry_svg(self):
        e = services.enter(self.contest, self.me)
        self.client.force_login(self.me)
        res = self.client.get(reverse("contest:entry_svg", args=[e.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertIn("sandbox", res.headers["Content-Security-Policy"])

    def test_login_and_csrf_required(self):
        self.assertEqual(self.client.get(reverse("contest:list")).status_code, 302)
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.me)
        self.assertEqual(client.post(reverse("contest:enter", args=[self.contest.pk])).status_code, 403)


class CommandTests(Base):
    """デモ利用者の投入と、エントリーの取り消し (動作確認用コマンド)。"""

    def test_reset_entry_allows_reentry_and_removes_votes(self):
        from django.core.management import call_command

        others = make_users(10, "c")
        for u in others:
            services.enter(self.contest, u)
        services.enter(self.contest, self.me)
        for _ in range(3):
            rnd = services.current_round(self.contest, self.me)
            services.vote(self.contest, self.me, rnd.pk, str(rnd.candidates.first().pk))
        self.assertEqual(sum(ContestEntry.objects.values_list("likes", flat=True)), 3)
        call_command("contest_reset_entry", email="me0@example.com", contest=self.contest.pk, stdout=open(os.devnull, "w"))
        self.assertIsNone(services.my_entry(self.contest, self.me))
        self.assertFalse(EvaluationRound.objects.filter(voter=self.me).exists())
        self.assertEqual(sum(ContestEntry.objects.values_list("likes", flat=True)), 0)  # 付けた高評価も取り消す
        services.enter(self.contest, self.me)  # もう一度エントリーできる
        self.assertEqual(services.current_round(self.contest, self.me).round_no, 1)

    @override_settings(DEBUG=True)
    def test_seed_demo_users(self):
        from django.core.management import call_command

        call_command("seed_demo_users", users=20, entries=12, contest=self.contest.pk, stdout=open(os.devnull, "w"))
        demo = User.objects.filter(groups__name="デモ利用者")
        self.assertEqual(demo.count(), 20)
        self.assertTrue(all(not u.has_usable_password() for u in demo))
        self.assertEqual(ContestEntry.objects.filter(contest=self.contest, user__in=demo).count(), 12)
        self.assertEqual(EvaluationRound.objects.filter(voter__in=demo, answered_at__isnull=False).count(), 36)
        # 冪等: もう一度実行しても増えない
        call_command("seed_demo_users", users=20, entries=12, contest=self.contest.pk, stdout=open(os.devnull, "w"))
        self.assertEqual(demo.count(), 20)
        call_command("seed_demo_users", delete=True, stdout=open(os.devnull, "w"))
        self.assertEqual(User.objects.filter(groups__name="デモ利用者").count(), 0)
        self.assertTrue(User.objects.filter(pk=self.me.pk).exists())  # デモ以外は消さない

    def test_seed_demo_users_refuses_in_production(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("seed_demo_users", users=1, entries=0, stdout=open(os.devnull, "w"))

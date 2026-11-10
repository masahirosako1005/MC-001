"""動作確認用のデモ利用者を投入する (ローカル開発専用)。

    python manage.py seed_demo_users --users 300 --entries 60
    python manage.py seed_demo_users --delete          # デモ利用者をまとめて削除

- 名前はすべて架空。メールは予約済みのテスト用ドメイン (@demo.mikke.test)
- パスワードは設定しない (ログインできない)。「デモ利用者」グループに入れて、後で一括削除できる
- --entries 人は開催中のコンテストにエントリーし、本物と同じ仕組み (表示回数の少ない順・3 体 × 3 回) で投票する
"""

from __future__ import annotations

import datetime as dt
import secrets
from collections import defaultdict

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from contest import services as contest_services
from contest.models import Contest
from core import audit
from core.demo import DEMO_DOMAIN, DEMO_USER_GROUP
from wardrobe.avatar import CATEGORY_CHOICES, EYE_COLORS, SKIN_TONES
from wardrobe.models import AvatarConfig, Item, UserItem

DEMO_GROUP = DEMO_USER_GROUP
_rng = secrets.SystemRandom()

# 架空のニックネームの素材 (実在の人物とは無関係)
GIVEN = ["さくら", "はると", "ゆい", "そうた", "ひなた", "りく", "めい", "ゆうと", "あおい", "こはる", "かいと", "みお",
         "れん", "つむぎ", "はるき", "ことね", "そら", "いろは", "あさひ", "ゆず", "なぎ", "ほのか", "たいが", "えま",
         "しおん", "りん", "けいた", "まひろ", "ちさと", "あやの", "こうき", "みなみ", "だいち", "ももか", "しゅん", "かえで"]
STYLE = ["{n}", "{n}{num}", "{n}ちゃん", "{n}くん", "旅する{n}", "{n}_trip", "{n}さんぽ", "京橋の{n}", "{n}@休日",
         "{n}{num}号", "おでかけ{n}", "{n}cafe"]
CONTEST_NAME = ["{n}", "{n}コーデ", "{n}の旅支度", "きらきら{n}", "{n}*", "{n}ワールド", "{n}のおでかけ", "{n}{num}"]


def _name(pattern_list: list[str]) -> str:
    return _rng.choice(pattern_list).format(n=_rng.choice(GIVEN), num=_rng.randrange(1, 100))[:20]


class Command(BaseCommand):
    help = "動作確認用のデモ利用者を投入する (ローカル開発専用)"

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=300)
        parser.add_argument("--entries", type=int, default=60, help="開催中コンテストにエントリーして投票する人数")
        parser.add_argument("--contest", type=int, help="対象コンテスト ID (省略時は開催中で最新のもの)")
        parser.add_argument("--delete", action="store_true", help="デモ利用者をすべて削除する")

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("デモ利用者の投入はローカル開発環境 (DEBUG=True) でのみ実行できます。")
        group, _ = Group.objects.get_or_create(name=DEMO_GROUP)
        if opts["delete"]:
            n, _ = User.objects.filter(groups=group, is_staff=False).delete()
            audit.record("demo.users_deleted", count=n)
            self.stdout.write(self.style.SUCCESS(f"デモ利用者を削除しました ({n} 件のデータ)"))
            return

        existing = User.objects.filter(groups=group).count()
        created = self._create_users(group, max(opts["users"] - existing, 0), start=existing)
        self.stdout.write(f"デモ利用者: 既存 {existing} 人 + 新規 {created} 人")

        contest = self._contest(opts.get("contest"))
        if contest and opts["entries"] > 0:
            entered, votes = self._enter_and_vote(contest, group, opts["entries"])
            self.stdout.write(f"コンテスト「{contest.title}」: エントリー {entered} 人 / 投票 {votes} 回")
        if created:
            from django.core.management import call_command

            call_command("link_item_symbols", stdout=self.stdout)  # 持たせたアイテムに「手に入れたシンボル」を付ける
        audit.record("demo.users_seeded", created=created, contest=contest.pk if contest else None)
        self.stdout.write(self.style.SUCCESS("完了"))

    # ------------------------------------------------------------ 利用者
    @transaction.atomic
    def _create_users(self, group: Group, n: int, start: int) -> int:
        items_by = defaultdict(list)
        for it in Item.objects.filter(is_active=True):
            items_by[(it.category, it.body_type)].append(it)
        starters = list(Item.objects.filter(is_starter=True, is_active=True))
        now = timezone.now()
        for i in range(start, start + n):
            # 仮想利用者は「みっけ仲間に表示する」を ON にしておく (こんな人が獲得しているよ の確認用)
            user = User(email=f"demo{i + 1:03d}@{DEMO_DOMAIN}", nickname=_name(STYLE), share_activity=True,
                        date_joined=now - dt.timedelta(days=_rng.randrange(0, 120), minutes=_rng.randrange(0, 1440)))
            user.set_unusable_password()
            user.last_login = user.date_joined + dt.timedelta(days=_rng.randrange(0, 30))
            user.save()
            user.groups.add(group)
            body = _rng.choice(["girl", "boy"])
            cfg = AvatarConfig(user=user, body_type=body, skin_tone=_rng.choice(list(SKIN_TONES)),
                               eye_color=_rng.choice(list(EYE_COLORS)))
            owned = set(starters)
            for cat, _ in CATEGORY_CHOICES:
                pool = items_by[(cat, body)] + items_by[(cat, "any")]
                optional = cat in ("accessory", "effect")
                if pool and not (optional and _rng.random() < 0.45):
                    item = _rng.choice(pool)
                    setattr(cfg, cat, item)
                    owned.add(item)
            # 探索で集めたことにするアイテムも少し持たせる
            extra = [it for lst in items_by.values() for it in lst if it.fits(body)]
            owned.update(_rng.sample(extra, k=min(len(extra), _rng.randrange(3, 15))))
            cfg.save()
            UserItem.objects.bulk_create([UserItem(user=user, item=it) for it in owned], ignore_conflicts=True)
        return n

    # ------------------------------------------------------------ コンテスト
    def _contest(self, pk: int | None) -> Contest | None:
        if pk:
            return Contest.objects.filter(pk=pk).first()
        return next((c for c in Contest.objects.filter(is_active=True).order_by("-starts_at") if c.is_open()), None)

    def _enter_and_vote(self, contest: Contest, group: Group, target: int) -> tuple[int, int]:
        already = set(contest.entries.filter(is_bot=False).values_list("user_id", flat=True))
        candidates = [u for u in User.objects.filter(groups=group).order_by("pk") if u.pk not in already]
        demo_entered = contest.entries.filter(user__groups=group).count()
        new = _rng.sample(candidates, k=max(0, min(target - demo_entered, len(candidates))))
        for u in new:
            contest_services.enter(contest, u, _name(CONTEST_NAME))
        # 「人気の出やすさ」をランダムに決め、それに比例して選ばれやすくする (ランキングに差をつける)
        appeal = {e.pk: _rng.random() ** 2 + 0.05 for e in contest.entries.all()}
        votes = 0
        for u in new:
            for _ in range(contest.rounds):
                rnd = contest_services.current_round(contest, u)
                if rnd is None:
                    break
                cands = list(rnd.candidates.all())
                choice = None
                if _rng.random() > 0.12:  # 1 割ほどは「どれも選ばない」
                    weights = [appeal.get(c.pk, 0.1) for c in cands]
                    choice = _rng.choices(cands, weights=weights, k=1)[0]
                contest_services.vote(contest, u, rnd.pk, str(choice.pk) if choice else None)
                votes += 1
        return len(new), votes

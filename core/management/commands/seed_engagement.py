"""再訪率・アプリ利用率を確かめるための、大きめのデモデータを作る (ローカル開発環境 DEBUG=True のときだけ)。

    python manage.py seed_engagement                      # 利用者 10,000 人、1 年分
    python manage.py seed_engagement --users 10000 --usage 0.4 --revisit 0.2

作るもの (デモ利用者 = グループ「デモ利用者」の人だけを作り直す。本物の利用者のデータには触れない):
- デモ利用者を --users 人まで増やす (seed_demo_users)。登録日は約 13 か月にばらけさせる
- アプリを使った日 (DailyActivity): 日ごとの利用率がおおむね --usage (既定 40%) になるように
- 来た日 (みっけ・クーポンの利用): 1 年で 1 日以上来た人のうち、2 日以上来た人がおおむね --revisit (既定 20%)。
  再訪する人は、前回から数日〜数週間あけて来ることが多いようにする (月ごとの再訪率にも差が出る)
  - 来た日には 1〜3 回みっけ (付近の来訪・カメラ起動・スポット訪問も合わせて作る)。ごほうびはコーデ / クーポン / なし
  - クーポンは、その日か、あとで来た日に使う (使った日も「来た日」なので、来た日数は変わらない)
- コーデコンテスト: 開催中のコンテスト (なければ作る) に約 1,000 人がエントリーし、高評価に差をつける
- 最後に、再訪率 (1 年・30 日) とアプリ利用率 (30 日平均) を計算して表示する
前提: 先に seed_mikke と seed_analytics (デモのスポット) を実行しておくこと。
"""

from __future__ import annotations

import datetime as dt
import random
import uuid
from collections import defaultdict

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from contest import services as contest_services
from contest.models import Contest, ContestEntry, EvaluationRound
from core import audit
from core.demo import DEMO_USER_GROUP
from core.models import DailyActivity
from core.timeutil import season_of, slot_of
from explore.models import Discovery, NearbyVisit, Spot, SpotVisit
from rewards.models import CouponTemplate, UserCoupon, distributable_coupons_q, redeem_hash_of
from rewards.services import new_redeem_code
from wardrobe.models import AvatarConfig, UserItem

from .seed_analytics import DEMO_SPOT_PREFIX
from .seed_demo_users import CONTEST_NAME, GIVEN

BATCH = 5000


class Command(BaseCommand):
    help = "再訪率・アプリ利用率の確認用に、デモ利用者 10,000 人と 1 年分の利用・みっけ・クーポン・ランキングを作る (DEBUG 時のみ)"

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=10000)
        parser.add_argument("--days", type=int, default=365, help="何日前までのデータを作るか")
        parser.add_argument("--usage", type=float, default=0.40, help="日ごとのアプリ利用率の目安 (0〜1)")
        parser.add_argument("--revisit", type=float, default=0.20, help="1 年の再訪率の目安 (0〜1)")
        parser.add_argument("--visit", type=float, default=0.70, help="1 年に 1 日以上みっけ・クーポン利用する人の割合")
        parser.add_argument("--entries", type=int, default=1000, help="コンテストにエントリーする人数")
        parser.add_argument("--seed", type=int, default=20261110, help="乱数の種 (同じ値なら同じデータ)")

    def handle(self, *args, **o):
        if not settings.DEBUG:
            raise CommandError("デモデータの投入はローカル開発環境 (DEBUG=True) でのみ実行できます。")
        for k in ("usage", "revisit", "visit"):
            if not 0 < o[k] < 1:
                raise CommandError(f"--{k} は 0 より大きく 1 より小さい値にしてください。")
        self.rng = random.Random(o["seed"])  # noqa: S311 (デモデータ用。暗号には使わない)
        self.today = timezone.localdate()
        self.start = self.today - dt.timedelta(days=o["days"] - 1)
        spots = list(Spot.objects.filter(slug__startswith=DEMO_SPOT_PREFIX, symbols__isnull=False)
                     .distinct().prefetch_related("symbols__drops__item"))
        if not spots:
            raise CommandError("デモのスポットがありません。先に python manage.py seed_analytics を実行してください。")

        self.stdout.write(f"デモ利用者を {o['users']:,} 人まで増やします (時間がかかります)")
        call_command("seed_demo_users", users=o["users"], entries=0, stdout=self.stdout)
        group = Group.objects.get(name=DEMO_USER_GROUP)
        users = list(User.objects.filter(groups=group, role=User.ROLE_USER).order_by("pk"))[: o["users"]]
        self._spread_join_dates(users)
        self._clear(users)
        usage_days = self._usage(users, o["usage"])
        n_disc, n_used = self._visits(users, usage_days, spots, o["visit"], o["revisit"])
        n_entries = self._contest(users, o["entries"])
        call_command("link_item_symbols", stdout=self.stdout)  # 持たせたアイテムに「手に入れたシンボル」を付ける
        audit.record("demo.engagement_seeded", users=len(users), discoveries=n_disc, coupons_used=n_used,
                     entries=n_entries)
        self._report()

    # ------------------------------------------------------------ 登録日
    def _spread_join_dates(self, users):
        """登録日を約 13 か月にばらけさせる (最近ほど少し多い)。「みっけ仲間に表示する」は 6 割ほどが ON。"""
        now = timezone.now()
        horizon = (self.today - self.start).days + 30
        for u in users:
            ago = int(horizon * (1 - self.rng.random() ** 0.8))
            u.date_joined = now - dt.timedelta(days=ago, minutes=self.rng.randrange(1440))
            u.share_activity = self.rng.random() < 0.6
        User.objects.bulk_update(users, ["date_joined", "share_activity"], batch_size=2000)

    # ------------------------------------------------------------ 作り直す前に消す
    @transaction.atomic
    def _clear(self, users):
        ids = [u.pk for u in users]
        for i in range(0, len(ids), 2000):
            chunk = ids[i:i + 2000]
            Discovery.objects.filter(user_id__in=chunk).delete()
            NearbyVisit.objects.filter(user_id__in=chunk).delete()
            SpotVisit.objects.filter(user_id__in=chunk).delete()
            UserCoupon.objects.filter(user_id__in=chunk).delete()
            DailyActivity.objects.filter(user_id__in=chunk).delete()
            EvaluationRound.objects.filter(voter_id__in=chunk).delete()
            ContestEntry.objects.filter(user_id__in=chunk).delete()

    # ------------------------------------------------------------ アプリを使った日
    def _usage(self, users, target: float) -> dict[int, list[dt.date]]:
        """利用者ごとの「使いやすさ」を決め、日ごとの利用率が target ほどになるように使った日を作る。"""
        dormant = 0.15  # ほとんど使わない人
        mean_active = (target - dormant * 0.02) / (1 - dormant)
        k = 6.0  # ベータ分布の集中度
        out: dict[int, list[dt.date]] = {}
        rows = []
        for u in users:
            joined = timezone.localtime(u.date_joined).date()
            first = max(joined, self.start)
            p = 0.02 if self.rng.random() < dormant else self.rng.betavariate(mean_active * k, (1 - mean_active) * k)
            days = []
            d = first
            while d <= self.today:
                if d == joined or self.rng.random() < p:  # 登録した日は使っている
                    days.append(d)
                d += dt.timedelta(days=1)
            out[u.pk] = days
            rows.extend(DailyActivity(user_id=u.pk, date=d) for d in days)
            if days:
                tz = timezone.get_current_timezone()
                u.last_login = dt.datetime.combine(days[-1], dt.time(self.rng.randrange(7, 22)), tzinfo=tz)
        for i in range(0, len(rows), BATCH):
            DailyActivity.objects.bulk_create(rows[i:i + BATCH], ignore_conflicts=True)
        User.objects.bulk_update([u for u in users if u.last_login], ["last_login"], batch_size=2000)
        self.stdout.write(f"アプリを使った日: {len(rows):,} 件")
        return out

    # ------------------------------------------------------------ 来た日 (みっけ・クーポン)
    def _visit_days(self, usage: list[dt.date], visit: float, revisit: float) -> list[dt.date]:
        """その人の「来た日」。使った日の中から選ぶ。再訪する人は、数日〜数週間あけて次に来ることが多い。"""
        if not usage or self.rng.random() >= visit:
            return []
        first = self.rng.choice(usage)
        if self.rng.random() >= revisit:
            return [first]
        n = 2 + min(int(self.rng.expovariate(1 / 1.6)), 22)
        chosen = {first}
        cursor = first
        for _ in range(n * 4):
            if len(chosen) >= n:
                break
            gap = max(1, int(self.rng.expovariate(1 / 12)))  # 平均 12 日あけて次に来る
            cursor = cursor + dt.timedelta(days=gap) if self.rng.random() < 0.8 else cursor - dt.timedelta(days=gap)
            near = [d for d in usage if abs((d - cursor).days) <= 3 and d not in chosen]
            if near:
                cursor = self.rng.choice(near)
                chosen.add(cursor)
        if len(chosen) < 2:  # 使った日が 1 日しかないなど
            others = [d for d in usage if d != first]
            if not others:
                return [first]
            chosen.add(self.rng.choice(others))
        return sorted(chosen)

    def _visits(self, users, usage_days, spots, visit: float, revisit: float) -> tuple[int, int]:
        tz = timezone.get_current_timezone()
        now = timezone.now()
        weights = [self.rng.paretovariate(1.6) for _ in spots]
        symbols = {s.pk: [sym for sym in s.symbols.all() if sym.is_active] for s in spots}
        coupons_by_owner: dict[int | None, list[CouponTemplate]] = defaultdict(list)
        for c in CouponTemplate.objects.filter(distributable_coupons_q()).select_related("spot"):
            coupons_by_owner[c.owner_id or (c.spot.owner_id if c.spot_id else None)].append(c)
        all_coupons = [c for lst in coupons_by_owner.values() for c in lst]

        nearby: dict[tuple, NearbyVisit] = {}
        visits: dict[tuple, SpotVisit] = {}
        discoveries, coupons, grants = [], [], set()
        used = 0
        for u in users:
            days = self._visit_days(usage_days.get(u.pk, []), visit, revisit)
            pending: list[UserCoupon] = []  # まだ使っていないクーポン (あとで来た日に使う)
            for day in days:
                # 前に受け取ったクーポンを、この日に使う
                for c in [c for c in pending if c.expires_at.date() >= day and self.rng.random() < 0.5]:
                    c.used_at = max(c.issued_at + dt.timedelta(minutes=5),
                                    dt.datetime.combine(day, dt.time(self.rng.randrange(10, 20)), tzinfo=tz))
                    if c.used_at < c.expires_at and c.used_at <= now:
                        c.used_value_yen = c.template.value_yen
                        pending.remove(c)
                        used += 1
                    else:
                        c.used_at = None
                for _ in range(self.rng.choice([1, 1, 1, 2, 2, 3])):
                    spot = self.rng.choices(spots, weights=weights, k=1)[0]
                    syms = symbols.get(spot.pk) or []
                    if not syms:
                        continue
                    hour = self.rng.randrange(7, 22)
                    at = dt.datetime.combine(day, dt.time(hour, self.rng.randrange(60)), tzinfo=tz)
                    if at > now:
                        at = now - dt.timedelta(minutes=self.rng.randrange(5, 120))
                    local = timezone.localtime(at)
                    slot, season = slot_of(local), season_of(local.date())
                    key = (u.pk, spot.pk, local.date(), slot)
                    nv = nearby.get(key) or NearbyVisit(user_id=u.pk, spot_id=spot.pk, date=local.date(), slot=slot,
                                                        season=season, page_views=0, camera_starts=0,
                                                        first_at=at, last_at=at)
                    nearby[key] = nv
                    nv.page_views += self.rng.choice([1, 1, 2, 3])
                    nv.camera_starts += 1
                    visits.setdefault((u.pk, spot.pk, local.date()),
                                      SpotVisit(user_id=u.pk, spot_id=spot.pk, visit_date=local.date(), season=season,
                                                first_seen_at=at))
                    sym = self.rng.choice(syms)
                    found_at = at + dt.timedelta(minutes=self.rng.randrange(1, 15))
                    found_at = min(found_at, now)
                    r = self.rng.random()
                    drops = [d for d in sym.drops.all() if d.item_id]
                    pool = coupons_by_owner.get(spot.owner_id) or all_coupons
                    if r < 0.15 and pool:
                        tpl = self.rng.choice(pool)
                        code = new_redeem_code()
                        c = UserCoupon(id=uuid.uuid4(), user_id=u.pk, template=tpl, redeem_code=code,
                                       redeem_hash=redeem_hash_of(code), source=f"{spot.name}でみっけ",
                                       issued_at=found_at, expires_at=found_at + dt.timedelta(days=tpl.valid_days))
                        if self.rng.random() < 0.45:  # その場ですぐ使う
                            c.used_at = min(found_at + dt.timedelta(minutes=self.rng.randrange(5, 90)), now)
                            if c.used_at < c.expires_at:
                                c.used_value_yen = tpl.value_yen
                                used += 1
                            else:
                                c.used_at = None
                        if c.used_at is None:
                            pending.append(c)
                        coupons.append(c)
                        discoveries.append(Discovery(user_id=u.pk, symbol=sym, reward_kind="coupon",
                                                     reward_label=tpl.title, reward_ref=str(c.id),
                                                     is_new=True, idempotency_key=uuid.uuid4(), found_at=found_at))
                    elif r < 0.9 and drops:
                        d = self.rng.choice(drops)
                        discoveries.append(Discovery(user_id=u.pk, symbol=sym, drop=d, reward_kind="item",
                                                     reward_label=d.item.name, reward_ref=d.item.code,
                                                     is_new=(u.pk, d.item_id) not in grants,
                                                     idempotency_key=uuid.uuid4(), found_at=found_at))
                        grants.add((u.pk, d.item_id))
                    else:
                        discoveries.append(Discovery(user_id=u.pk, symbol=sym, reward_kind="none", reward_label="",
                                                     idempotency_key=uuid.uuid4(), found_at=found_at))
        with transaction.atomic():
            NearbyVisit.objects.bulk_create(nearby.values(), batch_size=BATCH, ignore_conflicts=True)
            SpotVisit.objects.bulk_create(visits.values(), batch_size=BATCH, ignore_conflicts=True)
            Discovery.objects.bulk_create(discoveries, batch_size=BATCH)
            UserCoupon.objects.bulk_create(coupons, batch_size=BATCH)
            UserItem.objects.bulk_create([UserItem(user_id=u, item_id=i) for u, i in grants], batch_size=BATCH,
                                         ignore_conflicts=True)
        self.stdout.write(f"みっけ: {len(discoveries):,} 件 / クーポン: 配布 {len(coupons):,} 枚・使用 {used:,} 枚")
        return len(discoveries), used

    # ------------------------------------------------------------ コンテスト (ランキング)
    def _contest(self, users, n: int) -> int:
        now = timezone.now()
        contest = next((c for c in Contest.objects.filter(is_active=True).order_by("-starts_at") if c.is_open(now)),
                       None)
        if contest is None:
            contest = Contest.objects.create(title="みっけコーデコンテスト(デモ)", theme="まちあるきコーデ",
                                             starts_at=now - dt.timedelta(days=7), ends_at=now + dt.timedelta(days=21))
        configs = {c.user_id: c for c in AvatarConfig.objects.filter(user__in=users).select_related(
            *[f for f in ("face", "hair", "top", "bottom", "shoes", "accessory", "effect", "background")])}
        picked = self.rng.sample([u for u in users if u.pk in configs], k=min(n, len(configs)))
        entries = []
        for u in picked:
            appeal = self.rng.paretovariate(1.25)
            impressions = self.rng.randrange(20, 160)
            likes = min(impressions, int(appeal * self.rng.uniform(1, 6)))
            name = self.rng.choice(CONTEST_NAME).format(n=self.rng.choice(GIVEN), num=self.rng.randrange(1, 100))[:20]
            entries.append(ContestEntry(contest=contest, user=u, display_name=name,
                                        avatar=contest_services.avatar_snapshot(configs[u.pk]),
                                        impressions=impressions, likes=likes,
                                        created_at=contest.starts_at + dt.timedelta(
                                            minutes=self.rng.randrange(max(1, int((now - contest.starts_at)
                                                                                  .total_seconds() // 60))))))
        ContestEntry.objects.bulk_create(entries, batch_size=BATCH, ignore_conflicts=True)
        self.stdout.write(f"コンテスト「{contest.title}」: エントリー {len(entries):,} 人")
        return len(entries)

    # ------------------------------------------------------------ 結果の確認
    def _report(self):
        from ops import engagement

        s = engagement.summary(30)
        y, m = s["year"], s["revisit"]
        self.stdout.write(self.style.SUCCESS(
            f"再訪率: 1 年 {y['rate']}%({y['revisitors']:,} / {y['visitors']:,} 人)・"
            f"30 日 {m['rate']}%({m['revisitors']:,} / {m['visitors']:,} 人) / "
            f"アプリ利用率: 30 日平均 {s['usage_avg']}%"))

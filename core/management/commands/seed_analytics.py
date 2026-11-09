"""分析画面の確認用に、架空のスポット・シンボル・管理者・利用者の行動データを投入する (ローカル開発専用)。

    python manage.py seed_analytics                 # スポット 100・仮想利用者 1000 人・1 年分の行動
    python manage.py seed_analytics --reset         # 投入したデモのスポット・行動データを消してから作り直す
    python manage.py seed_analytics --delete        # デモのスポット・管理者・行動データを削除 (利用者は seed_demo_users --delete)

- スポット名・店名・住所はすべて架空 (住所の番地は「0」始まりの存在しない番号)。座標は収録タイル (京橋付近) の範囲内
- 仮想利用者はパスワードなし (ログインできない)。seed_demo_users と同じ「デモ利用者」グループ
- 行動データ: 付近に来た (NearbyVisit) → カメラ起動 → みっけ (Discovery) を、スポットごとの人気・
  時間帯・季節の傾向をつけてランダムに作る (時間・季節ごとの分析を確認できるように)
- 動作確認用のアカウントも用意する: 管理者 manager@test.com と 利用者 user@test.com
  (パスワードは既存の test@test.com と同じ。test@test.com はサイト運営者)
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import ManagerProfile, User, email_hash_of
from core import audit
from core.timeutil import season_of, slot_of
from explore.models import Discovery, DropEntry, NearbyVisit, Spot, SpotVisit, Symbol
from wardrobe.models import Item, UserItem

DEMO_SPOT_PREFIX = "demo-spot-"
DEMO_MANAGER_GROUP = "デモ管理者"
DEMO_USER_GROUP = "デモ利用者"
DEMO_DOMAIN = "demo.mikke.test"
# ローカル確認用 (test@test.com と同じ)。DEBUG=True のときだけ使われ、本番では投入できない
TEST_PASSWORD = "test1234"  # noqa: S105
_rng = secrets.SystemRandom()

# ---- 架空の名前の素材 (実在の店舗・施設とは無関係)
PLACES = ["ほたる", "しおかぜ", "かもめ", "つきあかり", "こもれび", "さくら坂", "みずべ", "ひだまり", "あかね", "そよかぜ",
          "ほしぞら", "わたぼうし", "かざぐるま", "せせらぎ", "ゆうなぎ", "あおぞら", "ささぶね", "まちかど", "いろは", "はなみずき"]
KINDS = [  # (種類, 時間帯の傾向, 季節の傾向)
    ("公園", {"morning": 3, "day": 4, "evening": 2, "night": 1}, {"spring": 4, "summer": 2, "autumn": 3, "winter": 1}),
    ("商店街", {"morning": 1, "day": 4, "evening": 4, "night": 1}, {"spring": 2, "summer": 2, "autumn": 2, "winter": 3}),
    ("神社", {"morning": 3, "day": 3, "evening": 2, "night": 1}, {"spring": 2, "summer": 1, "autumn": 2, "winter": 4}),
    ("喫茶", {"morning": 2, "day": 4, "evening": 2, "night": 1}, {"spring": 2, "summer": 2, "autumn": 3, "winter": 3}),
    ("雑貨店", {"morning": 1, "day": 4, "evening": 3, "night": 1}, {"spring": 3, "summer": 2, "autumn": 3, "winter": 2}),
    ("古書店", {"morning": 1, "day": 4, "evening": 2, "night": 1}, {"spring": 2, "summer": 2, "autumn": 4, "winter": 2}),
    ("銭湯", {"morning": 1, "day": 1, "evening": 4, "night": 4}, {"spring": 2, "summer": 1, "autumn": 3, "winter": 5}),
    ("船着き場", {"morning": 2, "day": 3, "evening": 4, "night": 2}, {"spring": 3, "summer": 4, "autumn": 2, "winter": 1}),
    ("ギャラリー", {"morning": 1, "day": 5, "evening": 2, "night": 0}, {"spring": 2, "summer": 3, "autumn": 3, "winter": 2}),
    ("展望広場", {"morning": 2, "day": 2, "evening": 4, "night": 3}, {"spring": 3, "summer": 3, "autumn": 3, "winter": 2}),
    ("屋台横丁", {"morning": 0, "day": 1, "evening": 4, "night": 5}, {"spring": 2, "summer": 4, "autumn": 3, "winter": 2}),
    ("パン工房", {"morning": 5, "day": 3, "evening": 1, "night": 0}, {"spring": 3, "summer": 2, "autumn": 3, "winter": 2}),
]
SYMBOL_NAMES = ["看板ねこ", "ふくろうの置物", "青いポスト", "古い時計", "かえるの石像", "ちょうちん", "壁画", "風見どり",
                "灯籠", "ベンチの手形", "のれん", "ステンドグラス", "からくり人形", "鈴", "木彫りのくま", "まねきねこ"]
STORES = [  # (会社・団体名, 店舗・施設名, 業種)
    ("ほたる通り商店会", "", "municipality"), ("合同会社しおかぜ珈琲", "京橋店", "food"), ("こもれび雑貨", "本店", "shop"),
    ("株式会社みずべ観光", "船着き場案内所", "transport"), ("ひだまりベーカリー", "", "food"), ("あかね湯", "", "lodging"),
    ("ほしぞら書房", "京橋店", "shop"), ("一般社団法人まちかど観光協会", "", "municipality"),
    ("かざぐるまギャラリー", "", "sightseeing"), ("ゆうなぎ横丁実行委員会", "", "event"), ("いろは神社 社務所", "", "sightseeing"),
    ("せせらぎ公園管理事務所", "", "municipality"),
]
CONTACTS = ["山田", "佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "中村", "小林", "加藤", "吉田", "山本"]
WARDS = ["大阪市城東区(架空)", "大阪市都島区(架空)", "大阪市中央区(架空)"]


class Command(BaseCommand):
    help = "分析画面の確認用に、架空のスポット 100・仮想利用者 1000 人・1 年分の行動データを投入する (ローカル開発専用)"

    def add_arguments(self, parser):
        parser.add_argument("--spots", type=int, default=100)
        parser.add_argument("--users", type=int, default=1000)
        parser.add_argument("--days", type=int, default=365, help="何日前までの行動を作るか")
        parser.add_argument("--reset", action="store_true", help="投入済みのデモのスポット・行動データを消してから作る")
        parser.add_argument("--delete", action="store_true", help="デモのスポット・管理者・行動データを削除する")

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("デモデータの投入はローカル開発環境 (DEBUG=True) でのみ実行できます。")
        if opts["delete"] or opts["reset"]:
            self._delete(managers=opts["delete"])
            if opts["delete"]:
                self.stdout.write(self.style.SUCCESS("デモのスポット・管理者・行動データを削除しました"))
                return
        accounts = self._test_accounts()
        managers = self._managers()
        spots = self._spots(opts["spots"], managers, accounts["manager"])
        self.stdout.write(f"スポット {len(spots)} 件(シンボル {Symbol.objects.filter(spot__in=spots).count()} 件)")
        call_command("seed_demo_users", users=opts["users"], entries=0, stdout=self.stdout)
        users = list(User.objects.filter(groups__name=DEMO_USER_GROUP).values_list("pk", flat=True))
        n_visits, n_disc = self._behaviour(spots, users, opts["days"])
        audit.record("demo.analytics_seeded", spots=len(spots), users=len(users), visits=n_visits, discoveries=n_disc)
        self.stdout.write(self.style.SUCCESS(f"行動データ: 付近の来訪 {n_visits} 件 / みっけ {n_disc} 件"))

    # ------------------------------------------------------------ 削除
    @transaction.atomic
    def _delete(self, managers: bool):
        spots = Spot.objects.filter(slug__startswith=DEMO_SPOT_PREFIX)
        Discovery.objects.filter(symbol__spot__in=spots).delete()
        SpotVisit.objects.filter(spot__in=spots).delete()
        NearbyVisit.objects.filter(spot__in=spots).delete()
        Symbol.objects.filter(spot__in=spots).delete()
        n = spots.delete()[0]
        if managers:
            User.objects.filter(groups__name=DEMO_MANAGER_GROUP).delete()
        audit.record("demo.analytics_deleted", spots=n, managers=managers)

    # ------------------------------------------------------------ 確認用アカウント
    def _test_accounts(self) -> dict:
        out = {}
        for key, email, nickname, role in [("manager", "manager@test.com", "デモ商店 担当", User.ROLE_MANAGER),
                                           ("user", "user@test.com", "テスト利用者", User.ROLE_USER)]:
            user = User.objects.filter(email_hash=email_hash_of(email)).first()
            if user is None:
                user = User.objects.create_user(email, TEST_PASSWORD, nickname, role=role)
                if role == User.ROLE_USER:
                    from wardrobe.services import ensure_starter_kit

                    ensure_starter_kit(user)
            if role == User.ROLE_MANAGER:
                ManagerProfile.objects.get_or_create(user=user, defaults=dict(
                    organization="デモ商店", store_name="京橋本店", industry="shop", contact_name="デモ 担当",
                    postal_code="534-0000", address="大阪市城東区(架空)0-0-1", phone="06-0000-0001"))
            out[key] = user
        return out

    def _managers(self) -> list[User]:
        group, _ = Group.objects.get_or_create(name=DEMO_MANAGER_GROUP)
        out = []
        for i, (org, store, industry) in enumerate(STORES, start=1):
            email = f"store{i:02d}@{DEMO_DOMAIN}"
            user = User.objects.filter(email_hash=email_hash_of(email)).first()
            if user is None:
                user = User(email=email, nickname=(store or org)[:30], role=User.ROLE_MANAGER)
                user.set_unusable_password()
                user.save()
                user.groups.add(group)
                ManagerProfile.objects.create(
                    user=user, organization=org, store_name=store, industry=industry,
                    contact_name=f"{CONTACTS[i - 1]} (架空)", postal_code=f"534-00{i:02d}",
                    address=f"{WARDS[i % 3]}0-{i}-{_rng.randrange(1, 20)}", phone=f"06-0000-{1000 + i}",
                    website="", note="分析確認用の架空の管理者",
                    created_at=timezone.now() - dt.timedelta(days=_rng.randrange(60, 400)))
            out.append(user)
        return out

    # ------------------------------------------------------------ スポット・シンボル
    @transaction.atomic
    def _spots(self, n: int, managers: list[User], test_manager: User) -> list[Spot]:
        (lat0, lng0), (lat1, lng1) = settings.MIKKE_MAP["bounds"]
        pad_lat, pad_lng = (lat1 - lat0) * 0.08, (lng1 - lng0) * 0.08
        items = list(Item.objects.filter(is_active=True, is_starter=False))
        spots = []
        for i in range(1, n + 1):
            slug = f"{DEMO_SPOT_PREFIX}{i:03d}"
            spot = Spot.objects.filter(slug=slug).first()
            if spot is None:
                # 種類 × 地名の組み合わせで、名前が重ならないようにする
                a, b = divmod(i - 1, len(KINDS))
                kind = KINDS[b][0]
                place = PLACES[(a + b) % len(PLACES)] if a < len(PLACES) else f"{PLACES[b]}{a}"
                owner = test_manager if i <= 3 else (_rng.choice(managers) if _rng.random() < 0.7 else None)
                lat = Decimal(str(round(_rng.uniform(lat0 + pad_lat, lat1 - pad_lat), 6)))
                lng = Decimal(str(round(_rng.uniform(lng0 + pad_lng, lng1 - pad_lng), 6)))
                spot = Spot.objects.create(
                    slug=slug, name=f"{place}{kind}"[:80],
                    area="京橋 (デモ)", description=f"架空の{kind}です(分析確認用のデモデータ)。",
                    latitude=lat, longitude=lng, radius_m=200, owner=owner,
                    # 一部は期間限定・期限切れにして、状態の表示も確認できるようにする
                    expires_at=(timezone.now() - dt.timedelta(days=_rng.randrange(5, 60))) if i % 25 == 0 else
                    (timezone.now() + dt.timedelta(days=_rng.randrange(20, 120))) if i % 10 == 0 else None,
                )
                for j in range(1 + (i % 3 == 0)):  # 3 件に 1 件はシンボル 2 つ
                    sym = Symbol.objects.create(
                        spot=spot, name=_rng.choice(SYMBOL_NAMES), hint=f"{kind}のまわりを探してみよう",
                        is_secret=(i % 9 == 0 and j == 1),
                        latitude=lat + Decimal(str(round(_rng.uniform(-0.0004, 0.0004), 6))),
                        longitude=lng + Decimal(str(round(_rng.uniform(-0.0004, 0.0004), 6))),
                    )
                    for it in _rng.sample(items, k=min(len(items), _rng.randrange(3, 7))):
                        r = _rng.random()
                        DropEntry.objects.create(
                            symbol=sym, item=it, weight=_rng.choice([5, 10, 10, 20]),
                            season=_rng.choice(["spring", "summer", "autumn", "winter"]) if r < 0.25 else "any",
                            time_slot=_rng.choice(["morning", "day", "evening", "night"]) if 0.25 <= r < 0.4 else "any",
                            min_visit_days=2 if r > 0.9 else 1,
                        )
            spots.append(spot)
        return spots

    # ------------------------------------------------------------ 行動データ
    def _behaviour(self, spots: list[Spot], user_ids: list[int], days: int) -> tuple[int, int]:
        tz = timezone.get_current_timezone()
        now = timezone.now()
        kinds = {k[0]: k for k in KINDS}
        # スポットごとの「人気」「カメラを起動する割合」「みっけできる割合」(棒グラフに差が出るように)
        prof = {}
        for s in spots:
            kind = next((k for k in kinds if s.name.endswith(k) or k in s.name), "公園")
            prof[s.pk] = {
                "pop": _rng.paretovariate(1.6),
                "cam": _rng.uniform(0.35, 0.85),
                "find": _rng.uniform(0.45, 0.9),
                "slots": kinds[kind][1], "seasons": kinds[kind][2],
                "symbols": list(s.symbols.prefetch_related("drops__item")),
            }
        spot_ids = [s.pk for s in spots]
        weights = [prof[sid]["pop"] for sid in spot_ids]
        hours = {"morning": range(6, 10), "day": range(10, 16), "evening": range(16, 19), "night": [19, 20, 21, 22]}

        nearby: dict[tuple, NearbyVisit] = {}
        visits: dict[tuple, SpotVisit] = {}
        discoveries: list[Discovery] = []
        grants: set[tuple[int, int]] = set()
        for uid in user_ids:
            # 1 人あたりの来訪回数 (よく来る人・たまに来る人)
            n = min(40, int(_rng.expovariate(1 / 7)) + 1)
            for sid in _rng.choices(spot_ids, weights=weights, k=n):
                p = prof[sid]
                # 季節の傾向に合わせて日付を選ぶ (直近ほど少し多い)
                for _ in range(20):
                    day = timezone.localdate(now) - dt.timedelta(days=int(_rng.betavariate(1, 1.4) * (days - 1)))
                    if _rng.random() < p["seasons"][season_of(day)] / 5:
                        break
                slot = _rng.choices(list(p["slots"]), weights=[w + 0.01 for w in p["slots"].values()], k=1)[0]
                at = dt.datetime.combine(day, dt.time(_rng.choice(list(hours[slot])), _rng.randrange(60)), tzinfo=tz)
                if at > now:
                    continue
                slot, season = slot_of(timezone.localtime(at)), season_of(day)
                key = (uid, sid, day, slot)
                nv = nearby.get(key)
                if nv is None:
                    nv = nearby[key] = NearbyVisit(user_id=uid, spot_id=sid, date=day, slot=slot, season=season,
                                                   page_views=0, camera_starts=0, first_at=at, last_at=at)
                nv.page_views += _rng.choice([1, 1, 1, 2, 2, 3])
                if _rng.random() >= p["cam"]:
                    continue
                nv.camera_starts += 1
                if _rng.random() >= p["find"] or not p["symbols"]:
                    continue
                sym = _rng.choice(p["symbols"])
                drops = [d for d in sym.drops.all() if d.item_id]
                found_at = at + dt.timedelta(minutes=_rng.randrange(2, 25))
                visits.setdefault((uid, sid, day), SpotVisit(user_id=uid, spot_id=sid, visit_date=day, season=season,
                                                            first_seen_at=at))
                if drops and _rng.random() < 0.85:
                    d = _rng.choice(drops)
                    discoveries.append(Discovery(user_id=uid, symbol=sym, drop=d, reward_kind="item",
                                                 reward_label=d.item.name, reward_ref=d.item.code,
                                                 is_new=(uid, d.item_id) not in grants, idempotency_key=uuid.uuid4(),
                                                 found_at=found_at))
                    grants.add((uid, d.item_id))
                else:
                    discoveries.append(Discovery(user_id=uid, symbol=sym, reward_kind="none", reward_label="",
                                                 idempotency_key=uuid.uuid4(), found_at=found_at))
        with transaction.atomic():
            NearbyVisit.objects.bulk_create(nearby.values(), batch_size=2000, ignore_conflicts=True)
            SpotVisit.objects.bulk_create(visits.values(), batch_size=2000, ignore_conflicts=True)
            Discovery.objects.bulk_create(discoveries, batch_size=2000)
            UserItem.objects.bulk_create([UserItem(user_id=u, item_id=i) for u, i in grants], batch_size=2000,
                                         ignore_conflicts=True)
        return len(nearby), len(discoveries)

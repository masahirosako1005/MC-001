"""所持品 (UserItem) に「手に入れたシンボル」を結び付ける。

    python manage.py link_item_symbols            # 実行
    python manage.py link_item_symbols --dry-run  # 件数だけ確認

「こんな人が獲得しているよ」でほかの人のコーデを押したとき、どこで手に入れたかが
「みっけ以外で手に入れたアイテム」と出てしまうもの (デモデータで直接持たせたアイテムなど) をなくす。

1. みっけの記録 (Discovery) があるものは、最初にみっけしたシンボルを結び付ける
2. 記録がないものは、そのアイテムが手に入るシンボル (公開中・シークレットでないものを優先、出やすさで重み付け) を選ぶ。
   手に入れた日も、選んだドロップの季節に合う日 (登録日以降・直近 1 年) にする
3. どのシンボルでも手に入らないアイテムは、公開中のスポットにシンボルを作って、そのアイテムが出るようにする
はじめから持っているアイテム・実績のごほうびは対象外 (それぞれ「はじめから」「実績のごほうび」と出る)。
みっけの記録は作らないので、再訪率などの分析の数は変わらない。
"""

from __future__ import annotations

import datetime as dt
import random
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.timeutil import season_of
from explore.models import Discovery, DropEntry, Spot, Symbol, spot_available_q
from rewards.models import UserAchievement
from wardrobe.models import Item, UserItem

BATCH = 5000


class Command(BaseCommand):
    help = "所持品に「手に入れたシンボル」を結び付ける (みっけ以外で手に入れたアイテムをなくす)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="変更せずに件数だけ表示する")
        parser.add_argument("--seed", type=int, default=20261110, help="乱数の種")

    def handle(self, *args, **o):
        self.rng = random.Random(o["seed"])  # noqa: S311 (どのシンボルにするかを選ぶだけ。暗号には使わない)
        self.dry = o["dry_run"]
        self.today = timezone.localdate()
        with transaction.atomic():
            n1 = self._from_discoveries()
            n2, created = self._from_drops()
            if self.dry:
                transaction.set_rollback(True)
        verb = "結び付けられます" if self.dry else "結び付けました"
        self.stdout.write(self.style.SUCCESS(
            f"みっけの記録から {n1:,} 件、手に入るシンボルから {n2:,} 件を{verb}"
            + (f"(シンボルを {created} 個作成)" if created else "")))

    # ------------------------------------------------------------ 1. みっけの記録から
    def _from_discoveries(self) -> int:
        code_to_id = dict(Item.objects.values_list("code", "pk"))
        first: dict[tuple[int, int], int] = {}
        for uid, code, sid in (Discovery.objects.filter(reward_kind="item").order_by("found_at")
                               .values_list("user_id", "reward_ref", "symbol_id").iterator(chunk_size=BATCH)):
            iid = code_to_id.get(code)
            if iid is not None:
                first.setdefault((uid, iid), sid)
        rows = []
        for ui in UserItem.objects.filter(found_symbol__isnull=True).only("pk", "user_id", "item_id").iterator(
                chunk_size=BATCH):
            sid = first.get((ui.user_id, ui.item_id))
            if sid is not None:
                ui.found_symbol_id = sid
                rows.append(ui)
        if not self.dry:
            UserItem.objects.bulk_update(rows, ["found_symbol"], batch_size=BATCH)
        return len(rows)

    # ------------------------------------------------------------ 2. 手に入るシンボルから
    def _candidates(self) -> dict[int, list[DropEntry]]:
        """アイテムごとの、手に入るドロップ (公開中のシンボル。シークレットでないものがあればそれだけ)。"""
        drops = (DropEntry.objects.filter(item__isnull=False, symbol__is_active=True)
                 .filter(spot_available_q("symbol__spot__")).select_related("symbol"))
        by_item: dict[int, list[DropEntry]] = defaultdict(list)
        for d in drops:
            by_item[d.item_id].append(d)
        for iid, lst in by_item.items():
            public = [d for d in lst if not d.symbol.is_secret]
            if public:
                by_item[iid] = public
        return by_item

    def _create_symbol_for(self, item: Item) -> DropEntry | None:
        """どこでも手に入らないアイテムのために、公開中のスポットにシンボルを作る。スポットがなければ None。"""
        spots = list(Spot.objects.available().filter(latitude__isnull=False).order_by("pk"))
        if not spots:
            return None
        spot = self.rng.choice(spots)
        sym = Symbol.objects.create(
            spot=spot, name=f"{item.name}の看板"[:80], hint=f"{spot.name}のまわりで「{item.name}」が見つかるかも",
            latitude=spot.latitude + Decimal(str(round(self.rng.uniform(-0.0003, 0.0003), 6))),
            longitude=spot.longitude + Decimal(str(round(self.rng.uniform(-0.0003, 0.0003), 6))))
        return DropEntry.objects.create(symbol=sym, item=item, weight=10)

    def _date_for(self, drop: DropEntry, joined: dt.date) -> dt.datetime:
        """手に入れた日: 登録日以降・直近 1 年の中で、ドロップの季節 (指定があれば) に合う日。"""
        lo = max(joined, self.today - dt.timedelta(days=364))
        span = max((self.today - lo).days, 0)
        day = lo
        for _ in range(40):
            day = lo + dt.timedelta(days=self.rng.randint(0, span))
            if drop.season in ("", "any") or season_of(day) == drop.season:
                break
        hour = {"morning": 8, "day": 13, "evening": 17, "night": 20}.get(drop.time_slot, self.rng.randrange(9, 20))
        return dt.datetime.combine(day, dt.time(hour, self.rng.randrange(60)), tzinfo=timezone.get_current_timezone())

    def _from_drops(self) -> tuple[int, int]:  # noqa: C901
        starters = set(Item.objects.filter(is_starter=True).values_list("pk", flat=True))
        rewards = set(UserAchievement.objects.filter(achievement__reward_item__isnull=False)
                      .values_list("user_id", "achievement__reward_item_id"))
        by_item = self._candidates()
        items = Item.objects.in_bulk()
        created = 0
        no_home: set[int] = set()  # シンボルを作れなかったアイテム (公開中のスポットがない)
        rows = []
        qs = (UserItem.objects.filter(found_symbol__isnull=True).exclude(item_id__in=starters)
              .select_related("user").only("pk", "user_id", "item_id", "first_obtained_at", "user__date_joined"))
        for ui in qs.iterator(chunk_size=BATCH):
            if (ui.user_id, ui.item_id) in rewards:
                continue
            lst = by_item.get(ui.item_id)
            if not lst:
                if ui.item_id in no_home:
                    continue
                if self.dry:
                    created += 1
                    rows.append(ui)
                    continue
                drop = self._create_symbol_for(items[ui.item_id])
                if drop is None:
                    no_home.add(ui.item_id)
                    continue
                lst = by_item[ui.item_id] = [drop]
                created += 1
            drop = self.rng.choices(lst, weights=[max(d.weight, 1) for d in lst], k=1)[0]
            ui.found_symbol_id = drop.symbol_id
            ui.first_obtained_at = self._date_for(drop, timezone.localtime(ui.user.date_joined).date())
            rows.append(ui)
        if not self.dry:
            UserItem.objects.bulk_update(rows, ["found_symbol", "first_obtained_at"], batch_size=BATCH)
        if no_home:
            self.stdout.write(self.style.WARNING(
                f"公開中のスポットがないため、{len(no_home)} 種類のアイテムは結び付けられませんでした。"))
        return len(rows), created

"""サイト運営者向けの分析: スポットごとの「付近に来た → カメラ起動 → みっけ → コーデ獲得」。

- 付近に来たユーザ: 「近くのシンボルを探す」でそのスポットのシンボルが周囲にあった人 (NearbyVisit)
- PV: その検索の回数
- カメラ起動ユーザ: 付近に来たあとにカメラ (または写真読み取り) を起動した人
- みっけユーザ: シンボルを撮影して受け取った人 (Discovery)
- コーデ獲得ユーザ: 受け取ったごほうびがアイテム (コーデ) だった人
- 利用割合 = コーデ獲得ユーザ数 ÷ 付近に来たユーザ数 × 100 (%)

人数はすべて「重複なし」。全体の人数は、複数のスポットに行った人も 1 人と数える。
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from django.utils import timezone

from core.timeutil import SEASON_LABELS, SLOT_LABELS, season_of, slot_of
from explore.models import Discovery, NearbyVisit, Spot

PERIODS = [(7, "直近 7 日"), (30, "直近 30 日"), (90, "直近 90 日"), (365, "直近 1 年"), (0, "全期間")]
SEASONS = ["spring", "summer", "autumn", "winter"]
SLOTS = ["morning", "day", "evening", "night"]
SORTS = [("visitors", "付近に来た人が多い順"), ("rate", "利用割合が高い順"), ("coord", "コーデ獲得が多い順"),
         ("name", "名前順")]


@dataclass
class Filters:
    days: int = 30
    season: str = ""
    slot: str = ""
    owner: str = ""  # 管理者のユーザ ID / "none" (サイト運営者のスポット) / "" (すべて)
    sort: str = "visitors"

    @classmethod
    def from_query(cls, q) -> Filters:
        def pick(name, allowed, default):
            v = q.get(name, default)
            return v if v in allowed else default

        days = q.get("days", "30")
        return cls(
            days=int(days) if days in {str(d) for d, _ in PERIODS} else 30,
            season=pick("season", SEASONS, ""),
            slot=pick("slot", SLOTS, ""),
            owner=q.get("owner", "") if (q.get("owner", "").isdigit() or q.get("owner") == "none") else "",
            sort=pick("sort", [k for k, _ in SORTS], "visitors"),
        )


@dataclass
class Funnel:
    visitors: set = field(default_factory=set)
    page_views: int = 0
    camera: set = field(default_factory=set)
    finders: set = field(default_factory=set)
    coord: set = field(default_factory=set)
    coord_count: int = 0  # コーデを受け取った回数 (人数ではなく回数)

    def as_row(self) -> dict:
        v = len(self.visitors)
        c = len(self.coord)
        return {
            "visitors": v, "page_views": self.page_views, "camera": len(self.camera),
            "finders": len(self.finders), "coord": c, "coord_count": self.coord_count,
            "rate": round(c / v * 100, 1) if v else None,
            "camera_rate": round(len(self.camera) / v * 100, 1) if v else None,
        }


def _start(filters: Filters, now: dt.datetime) -> dt.date | None:
    if not filters.days:
        return None
    return timezone.localdate(now) - dt.timedelta(days=filters.days - 1)


def compute(filters: Filters, now: dt.datetime | None = None) -> dict:
    now = now or timezone.now()
    start = _start(filters, now)

    spots = Spot.objects.select_related("owner__manager_profile").order_by("pk")
    if filters.owner == "none":
        spots = spots.filter(owner__isnull=True)
    elif filters.owner:
        spots = spots.filter(owner_id=int(filters.owner))
    spot_list = list(spots)
    spot_ids = {s.pk for s in spot_list}

    per_spot: dict[int, Funnel] = defaultdict(Funnel)
    per_slot: dict[str, Funnel] = defaultdict(Funnel)
    per_season: dict[str, Funnel] = defaultdict(Funnel)
    total = Funnel()

    nv = NearbyVisit.objects.filter(spot_id__in=spot_ids)
    if start:
        nv = nv.filter(date__gte=start)
    if filters.season:
        nv = nv.filter(season=filters.season)
    if filters.slot:
        nv = nv.filter(slot=filters.slot)
    for uid, sid, slot, season, pv, cam in nv.values_list("user_id", "spot_id", "slot", "season", "page_views",
                                                          "camera_starts").iterator(chunk_size=5000):
        for f in (per_spot[sid], per_slot[slot], per_season[season], total):
            f.visitors.add(uid)
            f.page_views += pv
            if cam:
                f.camera.add(uid)

    disc = Discovery.objects.filter(symbol__spot_id__in=spot_ids)
    if start:
        disc = disc.filter(found_at__date__gte=start)
    for uid, sid, found_at, kind in disc.values_list("user_id", "symbol__spot_id", "found_at",
                                                     "reward_kind").iterator(chunk_size=5000):
        local = timezone.localtime(found_at)
        slot, season = slot_of(local), season_of(local.date())
        if (filters.slot and slot != filters.slot) or (filters.season and season != filters.season):
            continue
        if start and local.date() < start:
            continue
        for f in (per_spot[sid], per_slot[slot], per_season[season], total):
            f.finders.add(uid)
            if kind == "item":
                f.coord.add(uid)
                f.coord_count += 1

    rows = []
    for s in spot_list:
        r = per_spot[s.pk].as_row()
        profile = getattr(s.owner, "manager_profile", None) if s.owner_id else None
        rows.append({"spot": s, "owner": profile.display_name if profile else "サイト運営者", **r})
    key = {
        "visitors": lambda r: (-r["visitors"], r["spot"].pk),
        "rate": lambda r: (-(r["rate"] if r["rate"] is not None else -1), -r["visitors"]),
        "coord": lambda r: (-r["coord"], -r["visitors"]),
        "name": lambda r: (r["spot"].name, r["spot"].pk),
    }[filters.sort]
    rows.sort(key=key)

    return {
        "total": total.as_row(),
        "spots": rows,
        "active_spots": sum(1 for r in rows if r["visitors"]),
        "by_slot": [{"key": k, "label": SLOT_LABELS[k], **per_slot[k].as_row()} for k in SLOTS],
        "by_season": [{"key": k, "label": SEASON_LABELS[k], **per_season[k].as_row()} for k in SEASONS],
        "start": start,
        "end": timezone.localdate(now),
    }

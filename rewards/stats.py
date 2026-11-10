"""クーポンの利用実績 (管理者の「クーポン実績」と、サイト運営者の「店舗ごとのクーポン利用」)。

- 配布枚数: 期間内に利用者に配った枚数
- 使用枚数: 期間内に使われた枚数 (いつ配ったものかは問わない)
- 使用金額: 期間内に使われた分の金額の合計。使った時点のクーポンの金額 (UserCoupon.used_value_yen) で数える
- 使用率: 期間内に配った分のうち、使用済みになった割合 (%)
- 店舗: クーポンを登録した管理者 (登録者がいなければ関連スポットの担当の管理者)。どちらもなければ「サイト運営者」
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.db.models import Count, IntegerField, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from .models import CouponTemplate, UserCoupon

PERIODS = [(7, "直近 7 日"), (30, "直近 30 日"), (90, "直近 90 日"), (365, "直近 1 年"), (0, "全期間")]
OPERATOR_STORE = "サイト運営者"


@dataclass
class Period:
    days: int = 30

    @classmethod
    def from_query(cls, q) -> Period:
        days = q.get("days", "30")
        return cls(days=int(days) if days in {str(d) for d, _ in PERIODS} else 30)

    def start(self, now: dt.datetime | None = None) -> dt.datetime | None:
        if not self.days:
            return None
        local = timezone.localtime(now or timezone.now())
        day = local.date() - dt.timedelta(days=self.days - 1)
        return local.replace(year=day.year, month=day.month, day=day.day, hour=0, minute=0, second=0, microsecond=0)

    @property
    def label(self) -> str:
        return dict(PERIODS)[self.days]


def _rate(used: int, issued: int) -> float | None:
    return round(used / issued * 100, 1) if issued else None


def _filters(start, prefix: str = "") -> tuple[Q, Q, Q]:
    issued = Q()
    used = Q(**{f"{prefix}used_at__isnull": False})
    if start is not None:
        issued &= Q(**{f"{prefix}issued_at__gte": start})
        used &= Q(**{f"{prefix}used_at__gte": start})
    used_of_issued = issued & Q(**{f"{prefix}used_at__isnull": False})
    return issued, used, used_of_issued


def coupon_rows(coupons: QuerySet[CouponTemplate], period: Period, now=None) -> list[dict]:
    """クーポンごとの実績 (使用金額の多い順)。"""
    issued, used, used_of_issued = _filters(period.start(now), "issued__")
    qs = coupons.select_related("spot", "owner__manager_profile", "spot__owner__manager_profile").annotate(
        n_issued=Count("issued", filter=issued, distinct=True),
        n_used=Count("issued", filter=used, distinct=True),
        n_used_of_issued=Count("issued", filter=used_of_issued, distinct=True),
        amount=Coalesce(Sum("issued__used_value_yen", filter=used), Value(0), output_field=IntegerField()),
    ).order_by("-amount", "-n_used", "-created_at")
    return [{"coupon": c, "issued": c.n_issued, "used": c.n_used, "amount": c.amount,
             "rate": _rate(c.n_used_of_issued, c.n_issued), "store": store_label(c)} for c in qs]


def store_owner(coupon: CouponTemplate):
    if coupon.owner_id:
        return coupon.owner
    if coupon.spot_id and coupon.spot.owner_id:
        return coupon.spot.owner
    return None


def store_label(coupon: CouponTemplate) -> str:
    owner = store_owner(coupon)
    profile = getattr(owner, "manager_profile", None) if owner else None
    return profile.display_name if profile else (owner.nickname if owner else OPERATOR_STORE)


def store_rows(period: Period, now=None) -> list[dict]:
    """店舗 (管理者) ごとの実績 (使用金額の多い順)。"""
    stores: dict = {}
    for r in coupon_rows(CouponTemplate.objects.all(), period, now):
        owner = store_owner(r["coupon"])
        key = owner.pk if owner else "none"
        row = stores.setdefault(key, {"key": key, "label": r["store"], "owner": owner, "coupons": 0, "active": 0,
                                      "issued": 0, "used": 0, "amount": 0, "_used_of_issued": 0})
        row["coupons"] += 1
        row["active"] += int(r["coupon"].is_distributable())
        row["issued"] += r["issued"]
        row["used"] += r["used"]
        row["amount"] += r["amount"]
        row["_used_of_issued"] += r["coupon"].n_used_of_issued
    rows = []
    for row in stores.values():
        row["rate"] = _rate(row.pop("_used_of_issued"), row["issued"])
        rows.append(row)
    return sorted(rows, key=lambda r: (-r["amount"], -r["used"], r["label"]))


def totals(rows: list[dict]) -> dict:
    return {
        "issued": sum(r["issued"] for r in rows),
        "used": sum(r["used"] for r in rows),
        "amount": sum(r["amount"] for r in rows),
    }


def monthly(coupons: QuerySet[CouponTemplate], months: int = 12, now=None) -> list[dict]:
    """直近 months か月の、月ごとの使用枚数と使用金額 (古い月から順に)。"""
    local = timezone.localtime(now or timezone.now())
    first = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    keys = []
    y, m = first.year, first.month
    for _ in range(months):
        keys.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    keys.reverse()
    start = first.replace(year=keys[0][0], month=keys[0][1])
    data = (UserCoupon.objects.filter(template__in=coupons, used_at__gte=start)
            .annotate(month=TruncMonth("used_at", tzinfo=timezone.get_current_timezone()))
            .values("month").annotate(used=Count("id"), amount=Coalesce(Sum("used_value_yen"), Value(0))))
    by_key = {(d["month"].year, d["month"].month): d for d in data}
    return [{"label": f"{mo}月" if mo != 1 else f"{yr % 100}年1月", "used": by_key.get((yr, mo), {}).get("used", 0),
             "amount": by_key.get((yr, mo), {}).get("amount", 0)} for yr, mo in keys]

"""サイト運営者向けの「再訪率」と「アプリ利用率」。

再訪率 (みっけ・クーポンの利用で数える)
- 「来た日」= その利用者が、みっけした日 (Discovery) か、クーポンを使った日 (UserCoupon.used_at)。日付は日本時間
- 期間 (既定 30 日) の中で、来た日が 1 日以上ある利用者 = 来た人。2 日以上ある利用者 = 再訪した人
- 再訪率 = 再訪した人 ÷ 来た人 × 100 (%)。同じ日に何回みっけしても 1 日
- ログインしただけ・画面を開いただけでは数えない (本当にまちに来たか分からないため)

アプリ利用率 (日ごと)
- その日にアプリを使った利用者 (DailyActivity。ログインしただけ・画面を開いただけも含む) ÷ その日までに登録していた利用者
- 対象は「利用者」だけ (管理者・サイト運営者・停止中の人は数えない)
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import User
from core.models import DailyActivity
from explore.models import Discovery
from rewards.models import UserCoupon

PERIODS = [(7, "直近 7 日"), (30, "直近 30 日"), (90, "直近 90 日"), (365, "直近 1 年")]
DEFAULT_DAYS = 30
USAGE_DAYS = 30
# 来た日数の分布 (棒グラフ・表)
BUCKETS = [("1", "1 日", 1, 1), ("2", "2 日", 2, 2), ("3-4", "3〜4 日", 3, 4), ("5+", "5 日以上", 5, 10**9)]


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole else None


@dataclass
class Window:
    start: dt.date  # この日を含む
    end: dt.date  # この日を含む

    @classmethod
    def last(cls, days: int, today: dt.date | None = None) -> Window:
        today = today or timezone.localdate()
        return cls(today - dt.timedelta(days=days - 1), today)

    def bounds(self) -> tuple[dt.datetime, dt.datetime]:
        tz = timezone.get_current_timezone()
        lo = dt.datetime.combine(self.start, dt.time.min, tzinfo=tz)
        hi = dt.datetime.combine(self.end + dt.timedelta(days=1), dt.time.min, tzinfo=tz)
        return lo, hi


def active_days(window: Window) -> dict[int, set[dt.date]]:
    """利用者ごとの「来た日」(みっけした日・クーポンを使った日) の集合。"""
    lo, hi = window.bounds()
    tz = timezone.get_current_timezone()
    out: dict[int, set[dt.date]] = defaultdict(set)
    disc = (Discovery.objects.filter(found_at__gte=lo, found_at__lt=hi, user__role=User.ROLE_USER)
            .annotate(d=TruncDate("found_at", tzinfo=tz)).values_list("user_id", "d").distinct())
    used = (UserCoupon.objects.filter(used_at__gte=lo, used_at__lt=hi, user__role=User.ROLE_USER)
            .annotate(d=TruncDate("used_at", tzinfo=tz)).values_list("user_id", "d").distinct())
    for qs in (disc, used):
        for uid, d in qs.iterator(chunk_size=5000):
            out[uid].add(d)
    return out


def revisit(window: Window) -> dict:
    """期間の再訪率と、来た日数の分布。"""
    days = active_days(window)
    counts = Counter(len(s) for s in days.values())
    visitors = len(days)
    revisitors = sum(n for k, n in counts.items() if k >= 2)
    buckets = []
    for key, label, lo, hi in BUCKETS:
        n = sum(c for k, c in counts.items() if lo <= k <= hi)
        buckets.append({"key": key, "label": label, "users": n, "share": _rate(n, visitors)})
    return {"visitors": visitors, "revisitors": revisitors, "rate": _rate(revisitors, visitors),
            "buckets": buckets, "start": window.start, "end": window.end}


def monthly_revisit(months: int = 12, today: dt.date | None = None) -> list[dict]:
    """月ごとの再訪率 (その月の中で 2 日以上来た人 ÷ その月に来た人)。古い月から。今月は今日まで。"""
    today = today or timezone.localdate()
    first = today.replace(day=1)
    keys = []
    y, m = first.year, first.month
    for _ in range(months):
        keys.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    rows = []
    for y, m in reversed(keys):
        start = dt.date(y, m, 1)
        nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
        end = min(nxt - dt.timedelta(days=1), today)
        r = revisit(Window(start, end))
        rows.append({"label": f"{m}月" if m != 1 else f"{y % 100}年1月", "rate": r["rate"],
                     "visitors": r["visitors"], "revisitors": r["revisitors"]})
    return rows


def daily_usage(days: int = USAGE_DAYS, today: dt.date | None = None) -> list[dict]:
    """日ごとのアプリ利用率 (古い日から)。"""
    today = today or timezone.localdate()
    start = today - dt.timedelta(days=days - 1)
    active = dict(DailyActivity.objects.filter(date__gte=start, date__lte=today, user__role=User.ROLE_USER,
                                               user__is_active=True)
                  .values_list("date").annotate(n=Count("id")))
    users = User.objects.filter(role=User.ROLE_USER, is_active=True)
    tz = timezone.get_current_timezone()
    joined = sorted(timezone.localtime(j, tz).date() for j in users.values_list("date_joined", flat=True))
    rows, idx = [], 0
    for i in range(days):
        d = start + dt.timedelta(days=i)
        while idx < len(joined) and joined[idx] <= d:
            idx += 1
        n = active.get(d, 0)
        rows.append({"date": d, "label": f"{d.month}/{d.day}", "weekday": "月火水木金土日"[d.weekday()],
                     "active": n, "registered": idx, "rate": _rate(n, idx)})
    return rows


def summary(days: int = DEFAULT_DAYS, today: dt.date | None = None) -> dict:
    today = today or timezone.localdate()
    usage = daily_usage(USAGE_DAYS, today)
    rates = [r["rate"] for r in usage if r["rate"] is not None]
    return {
        "revisit": revisit(Window.last(days, today)),
        "year": revisit(Window.last(365, today)),
        "monthly": monthly_revisit(12, today),
        "usage": usage,
        "usage_avg": round(sum(rates) / len(rates), 1) if rates else None,
        "usage_today": usage[-1] if usage else None,
    }

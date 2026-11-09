"""季節・時間帯の判定。再訪の動機づけ (季節・時間で出現アイテムが変わる) に使う。"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

SEASON_ANY = "any"
SEASON_CHOICES = [
    (SEASON_ANY, "いつでも"),
    ("spring", "春"),
    ("summer", "夏"),
    ("autumn", "秋"),
    ("winter", "冬"),
]
SLOT_CHOICES = [
    (SEASON_ANY, "いつでも"),
    ("morning", "朝 (5-10時)"),
    ("day", "昼 (10-16時)"),
    ("evening", "夕 (16-19時)"),
    ("night", "夜 (19-5時)"),
]
SEASON_LABELS = dict(SEASON_CHOICES)
SLOT_LABELS = {"any": "いつでも", "morning": "朝", "day": "昼", "evening": "夕方", "night": "夜"}


def local_now(now: dt.datetime | None = None) -> dt.datetime:
    return timezone.localtime(now or timezone.now())


def season_of(d: dt.date) -> str:
    m = d.month
    if m in (3, 4, 5):
        return "spring"
    if m in (6, 7, 8):
        return "summer"
    if m in (9, 10, 11):
        return "autumn"
    return "winter"


def slot_of(t: dt.datetime) -> str:
    h = t.hour
    if 5 <= h < 10:
        return "morning"
    if 10 <= h < 16:
        return "day"
    if 16 <= h < 19:
        return "evening"
    return "night"

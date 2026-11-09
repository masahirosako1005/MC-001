from __future__ import annotations

import secrets

from django.shortcuts import render
from django.views.decorators.http import require_GET

from contest.models import Contest, ContestEntry
from explore.models import Discovery, Spot
from rewards.models import UserAchievement, UserCoupon
from rewards.services import metrics_for
from wardrobe.models import Item

from .themes import get_theme
from .timeutil import SEASON_LABELS, local_now, season_of, slot_of

# ログイン前ページの「仮想写真」(scripts/make_photos.py で生成した CG。実在の写真ではない)
PHOTOS = [
    ("riverside", "夕暮れの川べり", "川面に映る夕日。夕方だけ出会えるアイテムも。"),
    ("castle", "桜とお城", "春の再訪で、桜色のアイテムが見つかるかも。"),
    ("lantern", "提灯の灯る路地", "夜にしか現れないシンボルを探そう。"),
    ("onsen", "湯けむりの温泉街", "足湯のそばにかくれたシンボル。"),
    ("harbor", "港のれんが倉庫", "レトロな街並みでコーデの撮影会。"),
]

GREETINGS = {
    "morning": ["おはよう、{n}さん!朝の散歩にぴったりの天気だね。", "{n}さん、おはよう!朝だけ出会えるアイテムがあるみたい。"],
    "day": ["{n}さん、こんにちは!今日はどこへみっけに行く?", "おかえり、{n}さん!{s}の昼は人気のスポットが多いよ。"],
    "evening": ["{n}さん、夕焼けがきれいな時間だね。川べりに行ってみない?", "夕方だけのシンボル、探しに行こうよ、{n}さん!"],
    "night": ["{n}さん、こんばんは。夜の神社には不思議なアイテムが…?", "夜のおでかけは気をつけてね、{n}さん。"],
}
TRAVEL_RANKS = [(0, "E"), (3, "D"), (10, "C"), (25, "B"), (50, "A"), (100, "S")]


def travel_rank(discoveries: int) -> str:
    rank = "E"
    for threshold, name in TRAVEL_RANKS:
        if discoveries >= threshold:
            rank = name
    return rank


def _template(kind: str, variant: str) -> list[str]:
    return [f"core/{kind}_{variant}.html", f"core/{kind}_standard.html"]


@require_GET
def home(request):
    theme = getattr(request, "ui_theme", None) or get_theme(None)
    if not request.user.is_authenticated:
        return render(request, _template("landing", theme.landing), {
            "spots": Spot.objects.available()[:6],
            "photos": PHOTOS,
        })
    user = request.user
    now = local_now()
    available_coupons = [c for c in UserCoupon.objects.filter(user=user, used_at__isnull=True).select_related("template")
                         if c.status == "available"]
    metrics = metrics_for(user)
    open_contest = next((c for c in Contest.objects.filter(is_active=True).order_by("-starts_at") if c.is_open()), None)
    slot = slot_of(now)
    greeting = secrets.choice(GREETINGS[slot]).format(n=user.nickname, s=SEASON_LABELS[season_of(now.date())])
    return render(request, _template("home", theme.home), {
        "metrics": metrics,
        "recent": Discovery.objects.filter(user=user).select_related("symbol__spot")[:5],
        "coupon_count": len(available_coupons),
        "item_total": Item.objects.filter(is_active=True).count(),
        "achievement_count": UserAchievement.objects.filter(user=user).count(),
        "rank": travel_rank(metrics["total_discoveries"]),
        "greeting": greeting,
        "contest": open_contest,
        "contest_entered": bool(open_contest and ContestEntry.objects.filter(contest=open_contest, user=user).exists()),
        "photos": PHOTOS,
    })

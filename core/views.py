from __future__ import annotations

import datetime as dt
import secrets

from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from contest.models import Contest, ContestEntry
from explore.models import Discovery, DropEntry, Spot, spot_available_q
from rewards.models import UserAchievement, UserCoupon
from rewards.services import metrics_for
from wardrobe.models import Item

from .themes import get_theme
from .timeutil import SEASON_LABELS, SLOT_LABELS, local_now, season_of, slot_of

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


def rank_info(discoveries: int) -> dict:
    """旅ランクの説明 (いまのランク、次のランクとあと何回か、ランク表)。"""
    current = travel_rank(discoveries)
    nxt = next(((t, n) for t, n in TRAVEL_RANKS if t > discoveries), None)
    return {
        "rank": current,
        "next": nxt[1] if nxt else None,
        "remaining": nxt[0] - discoveries if nxt else 0,
        "table": [{"rank": n, "from": t, "current": n == current} for t, n in TRAVEL_RANKS],
    }


SEASON_STARTS = [(3, "spring"), (6, "summer"), (9, "autumn"), (12, "winter")]


def season_countdown(today: dt.date) -> dict:
    """次の季節まであと何日か (季節は 3・6・9・12 月の 1 日に変わる)。"""
    for year in (today.year, today.year + 1):
        for month, season in SEASON_STARTS:
            start = dt.date(year, month, 1)
            if start > today:
                return {"days": (start - today).days, "next": SEASON_LABELS[season]}
    return {"days": 0, "next": ""}


def limited_now(now, limit: int = 3) -> list[dict]:
    """いまの季節・時間帯だけに出るコーデ (公開中・シークレットでないシンボルのもの)。ホームでシルエット表示する。"""
    season, slot = season_of(now.date()), slot_of(now)
    drops = (DropEntry.objects.select_related("item", "symbol__spot")
             .filter(spot_available_q("symbol__spot__"), symbol__is_active=True, symbol__is_secret=False,
                     item__isnull=False, item__is_active=True)
             .filter(Q(season=season) | Q(time_slot=slot))
             .order_by("-item__rarity", "pk"))
    out, seen = [], set()
    for d in drops[:60]:
        if d.item_id in seen:
            continue
        seen.add(d.item_id)
        label = f"{SEASON_LABELS[season]}限定" if d.season == season else f"{SLOT_LABELS[slot]}だけ"
        out.append({"name": d.item.name, "spot": d.symbol.spot.name, "label": label,
                    "image": reverse("explore:symbol_item_svg", args=[d.symbol_id, d.item.code])})
        if len(out) >= limit:
            break
    return out


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
        "rank_info": rank_info(metrics["total_discoveries"]),
        "season_countdown": season_countdown(now.date()),
        "limited_now": limited_now(now),
        "greeting": greeting,
        "contest": open_contest,
        "contest_entered": bool(open_contest and ContestEntry.objects.filter(contest=open_contest, user=user).exists()),
        "photos": PHOTOS,
    })


@require_GET
def showcase_svg(request, n: int):
    """ログイン画面の「いまだけ手に入るコーデ」の見本のアバター (ログイン不要。番号でしか取れない)。"""
    from django.http import Http404

    from core.http import svg_response

    from .showcase import showcase_svg as render_showcase

    svg = render_showcase(local_now(), n)
    if svg is None:
        raise Http404
    return svg_response(svg, cache="public, max-age=300")

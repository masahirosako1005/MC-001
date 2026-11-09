"""「こんな人が獲得しているよ」: 直近 30 分 (settings.MIKKE_FINDER_WINDOW_MINUTES) に同じスポットでみっけした人。
同じシンボルの人を先に並べ、足りなければ同じスポットの別のシンボルの人で補う。

プライバシーへの配慮:
- 表示するのは「みっけ仲間に表示する」を ON にしている利用者だけ (既存の利用者は OFF から始まる)
- 出すのはニックネームと今のコーデだけ。時刻は「さっき / ◯分前」(5 分単位) のおおまかな表示
- 他の人のページは、ランダムな ID (中に利用者 ID を含まない) でしか開けない。ID は見る人に結び付き、30 分で切れる
  (利用者 ID を順番に変えて他人を見て回ることはできない)
- コーデをどこで手に入れたかはスポット名と季節まで。日時は出さない。シークレットシンボルで手に入れたものは、
  見る人がそのシンボルをみっけしていなければスポットも伏せる
"""

from __future__ import annotations

import datetime as dt
import re
import secrets

from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from core.timeutil import SEASON_LABELS, season_of
from rewards.models import UserAchievement
from wardrobe.models import CATEGORY_CHOICES
from wardrobe.services import get_config

from .models import Discovery, Symbol

WINDOW = dt.timedelta(minutes=settings.MIKKE_FINDER_WINDOW_MINUTES)
MAX_FINDERS = 6
MIN_FINDERS = 3
# 他の人のコーデを開くための ID は、中身のないランダムな文字列 (利用者 ID は含めない)。
# 対応表はサーバーのキャッシュにだけ置き、30 分で消える
TOKEN_TTL_SECONDS = 30 * 60
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
_CACHE_PREFIX = "finder:"


class FinderNotFound(Exception):
    pass


def _visible_discoveries(viewer, since, now):
    return (Discovery.objects
            .filter(found_at__gte=since, found_at__lte=now, user__share_activity=True, user__is_active=True,
                    user__role="user")
            .exclude(user=viewer))


def ago_label(delta: dt.timedelta) -> str:
    minutes = max(0, int(delta.total_seconds() // 60))
    if minutes < 5:
        return "さっき"
    return f"{minutes // 5 * 5}分前"


def make_token(user_id: int, viewer_id: int) -> str:
    token = secrets.token_urlsafe(18)
    cache.set(_CACHE_PREFIX + token, (user_id, viewer_id), TOKEN_TTL_SECONDS)
    return token


def recent_finders(symbol: Symbol, viewer, now=None) -> list[dict]:
    """直近 30 分に同じスポットでみっけした人 (同じシンボルの人が先。3 人に満たなければ別のシンボルの人も足す、最大 6 人)。"""
    now = now or timezone.now()
    base = _visible_discoveries(viewer, now - WINDOW, now)
    picked: dict[int, dt.datetime] = {}
    for qs in (base.filter(symbol=symbol), base.filter(symbol__spot_id=symbol.spot_id)):
        for uid, found_at in qs.order_by("-found_at").values_list("user_id", "found_at")[:200]:
            if uid not in picked:
                picked[uid] = found_at
            if len(picked) >= MAX_FINDERS:
                break
        if len(picked) >= MIN_FINDERS:
            break
    if not picked:
        return []
    users = User.objects.in_bulk(list(picked))
    return [{"token": make_token(uid, viewer.pk), "nickname": users[uid].nickname, "ago": ago_label(now - t)}
            for uid, t in picked.items() if uid in users]


def read_token(token: str, viewer):
    """ID から相手の利用者を取り出す。見る人が違う・期限切れ・表示 OFF になった場合は FinderNotFound。"""
    if not _TOKEN_RE.match(token or ""):
        raise FinderNotFound
    data = cache.get(_CACHE_PREFIX + token)
    if not data or data[1] != viewer.pk:
        raise FinderNotFound
    user = User.objects.filter(pk=data[0], is_active=True, share_activity=True, role="user").first()
    if user is None:
        raise FinderNotFound
    return user


def obtained_info(target, item, viewer) -> dict:
    """そのコーデをどこで手に入れたか (スポットと季節。日時は出さない)。

    返り値: {"text": 表示文, "spot": {"id", "name", "lat", "lng"} または None, "season": 季節}
    spot は「これをみっけに行く」で地図に出すためのもの。公開中で位置があるスポットのときだけ付ける。
    """
    disc = (Discovery.objects.filter(user=target, reward_kind="item", reward_ref=item.code)
            .select_related("symbol__spot").order_by("-found_at").first())
    if disc is not None:
        season = SEASON_LABELS.get(season_of(timezone.localtime(disc.found_at).date()), "")
        sym = disc.symbol
        if sym.is_secret and not Discovery.objects.filter(user=viewer, symbol=sym).exists():
            return {"text": f"シークレットシンボルでみっけ({season})", "spot": None, "season": season}
        spot = sym.spot
        info = None
        if spot.is_available() and spot.latitude is not None and spot.longitude is not None:
            info = {"id": spot.pk, "name": spot.name, "lat": float(spot.latitude), "lng": float(spot.longitude)}
        return {"text": f"{spot.name}でみっけ({season})", "spot": info, "season": season}
    if item.is_starter:
        return {"text": "はじめから持っているアイテム", "spot": None, "season": ""}
    if UserAchievement.objects.filter(user=target, achievement__reward_item=item).exists():
        return {"text": "実績のごほうび", "spot": None, "season": ""}
    return {"text": "みっけ以外で手に入れたアイテム", "spot": None, "season": ""}


def finder_profile(target, viewer, token: str) -> dict:
    config = get_config(target)
    items = []
    for cat, label in CATEGORY_CHOICES:
        item = getattr(config, cat, None)
        if item is None:
            continue
        info = obtained_info(target, item, viewer)
        items.append({
            "code": item.code, "name": item.name, "category": label, "rarity": item.rarity,
            "image": reverse("explore:finder_item_svg", args=[token, item.code]),
            "obtained": info["text"], "spot": info["spot"], "season": info["season"],
        })
    return {"nickname": target.nickname, "avatar": reverse("explore:finder_avatar_svg", args=[token]), "items": items}

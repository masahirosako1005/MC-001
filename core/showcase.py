"""ログイン画面の「いまだけ手に入るコーデ」。

- いまの季節・時間帯だけに出るアイテム (公開中のスポット・シークレットでないシンボルのドロップ) を最大 3 つ選び、
  そのアイテムを主役にした全身のコーデ (残りは初期アイテム) を見本のアバターで見せる
- ログイン前に見える画面なので、特定の利用者のアバターや持ち物は使わない
- 絵は番号 (0〜2) でしか取れない (アイテムのコードを受け取らないので、シークレットや非公開のアイテムは描けない)
"""

from __future__ import annotations

from django.core.cache import cache
from django.db.models import Q

from explore.models import DropEntry, spot_available_q
from wardrobe.avatar import render_svg
from wardrobe.models import Item
from wardrobe.services import BASIC_SLOTS, CATEGORIES, to_part

from .timeutil import SEASON_LABELS, SLOT_LABELS, season_of, slot_of

LIMIT = 3
CACHE_SECONDS = 300
# 見本のアバターの見た目 (番号ごとに変えて、いろいろな人が遊んでいることを見せる)
LOOKS = [("tone2", "pink"), ("tone4", "blue"), ("tone3", "green")]


def _picks(now) -> list[dict]:
    season, slot = season_of(now.date()), slot_of(now)
    key = f"mikke:showcase:{now.date().isoformat()}:{season}:{slot}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    drops = (DropEntry.objects.select_related("item", "symbol__spot")
             .filter(spot_available_q("symbol__spot__", now), symbol__is_active=True, symbol__is_secret=False,
                     item__isnull=False, item__is_active=True)
             .exclude(item__category="background")
             .filter(Q(season=season) | Q(time_slot=slot))
             .order_by("-item__rarity", "pk"))
    out, seen = [], set()
    for d in drops[:80]:
        if d.item_id in seen:
            continue
        seen.add(d.item_id)
        label = f"{SEASON_LABELS[season]}限定" if d.season == season else f"{SLOT_LABELS[slot]}だけ"
        out.append({"item_id": d.item_id, "name": d.item.name, "spot": d.symbol.spot.name, "label": label})
        if len(out) >= LIMIT:
            break
    cache.set(key, out, CACHE_SECONDS)
    return out


def showcase(now) -> list[dict]:
    """ログイン画面に出すコーデ (番号・アイテム名・スポット・「秋限定」などの札)。"""
    return [{"n": i, **p} for i, p in enumerate(_picks(now))]


def showcase_svg(now, n: int) -> str | None:
    """n 番目のコーデを着た見本のアバター。範囲外なら None。"""
    picks = _picks(now)
    if not 0 <= n < len(picks):
        return None
    item = Item.objects.filter(pk=picks[n]["item_id"], is_active=True).first()
    if item is None:
        return None
    body = item.body_type if item.body_type in ("girl", "boy") else ("girl" if n % 2 == 0 else "boy")
    starters = list(Item.objects.filter(is_starter=True, is_active=True).order_by("rarity", "code"))
    parts = dict.fromkeys(CATEGORIES)
    for cat in (*BASIC_SLOTS, "face"):
        first = next((i for i in starters if i.category == cat and i.fits(body)), None)
        parts[cat] = to_part(first)
    parts[item.category] = to_part(item)
    skin, eye = LOOKS[n % len(LOOKS)]
    return render_svg(skin, parts, body_type=body, eye_color=eye, label=f"「{item.name}」を着たコーデの見本")

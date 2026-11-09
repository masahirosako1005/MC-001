from __future__ import annotations

import datetime as dt
import secrets

from django.db import IntegrityError, transaction
from django.db.models import Count, Max
from django.utils import timezone

from wardrobe.models import UserItem
from wardrobe.services import grant_item

from .models import Achievement, CouponTemplate, UserAchievement, UserCoupon

# 読み間違えやすい文字 (0/O, 1/I/L) を除いた英数字
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_redeem_code() -> str:
    body = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"MK-{body[:4]}-{body[4:]}"


class CouponNotDistributable(Exception):
    """配布停止・有効期限切れのクーポンは発行しない。"""


def issue_coupon(user, template: CouponTemplate, *, source: str, now: dt.datetime | None = None) -> UserCoupon:
    """クーポンを 1 枚発行する。

    - 引換コードはほかの人のものと重ならない (一意制約。万一重なったら作り直す)
    - 有効期限は「受け取ってから有効日数」と「クーポン自体の有効期限」の早いほう
    """
    now = now or timezone.now()
    if not template.is_distributable(now):
        raise CouponNotDistributable(f"クーポン {template.coupon_id} は配布期間外です。")
    expires = now + dt.timedelta(days=template.valid_days)
    if template.available_until and template.available_until < expires:
        expires = template.available_until
    for _ in range(5):
        try:
            with transaction.atomic():
                return UserCoupon.objects.create(user=user, template=template, redeem_code=new_redeem_code(),
                                                 source=source, issued_at=now, expires_at=expires)
        except IntegrityError:  # 引換コードの重複 (31^8 通りなので通常は起きない)
            continue
    raise RuntimeError("引換コードを発行できませんでした。")


class CouponUnavailable(Exception):
    pass


@transaction.atomic
def use_coupon(coupon: UserCoupon, *, now: dt.datetime | None = None) -> UserCoupon:
    """クーポンを使用済みにする。条件付き UPDATE で二重使用を防ぎ、再送には同じ結果を返す (冪等)。"""
    now = now or timezone.now()
    # クーポン自体の有効期限が後から短くされた場合も、期限を過ぎたものは使えない
    tpl = coupon.template
    if tpl.available_until and tpl.available_until <= now and coupon.used_at is None:
        raise CouponUnavailable("このクーポンは有効期限が切れています。")
    updated = UserCoupon.objects.filter(pk=coupon.pk, used_at__isnull=True, expires_at__gt=now).update(used_at=now)
    coupon.refresh_from_db()
    if not updated and coupon.used_at is None:
        raise CouponUnavailable("このクーポンは有効期限が切れています。")
    return coupon


def metrics_for(user) -> dict[str, int]:
    from explore.models import Discovery, SpotVisit  # 循環 import 回避

    visits = SpotVisit.objects.filter(user=user)
    per_spot_days = visits.values("spot").annotate(n=Count("id")).aggregate(m=Max("n"))["m"] or 0
    per_spot_seasons = (
        visits.values("spot").annotate(n=Count("season", distinct=True)).aggregate(m=Max("n"))["m"] or 0
    )
    return {
        "total_discoveries": Discovery.objects.filter(user=user).count(),
        "distinct_spots": visits.values("spot").distinct().count(),
        "distinct_items": UserItem.objects.filter(user=user).count(),
        "spot_visit_days": per_spot_days,
        "seasons_at_spot": per_spot_seasons,
    }


def evaluate_achievements(user) -> list[dict]:
    """未達成の実績を判定し、達成したものを付与する。呼び出し側のトランザクション内で使う。"""
    metrics = metrics_for(user)
    done = set(UserAchievement.objects.filter(user=user).values_list("achievement_id", flat=True))
    unlocked = []
    for ach in Achievement.objects.filter(is_active=True).exclude(pk__in=done).select_related(
        "reward_item", "reward_coupon"
    ):
        if metrics.get(ach.kind, 0) < ach.threshold:
            continue
        UserAchievement.objects.create(user=user, achievement=ach)
        info = {"name": ach.name, "icon": ach.icon, "description": ach.description}
        if ach.reward_item_id:
            _, is_new = grant_item(user, ach.reward_item)
            info["item"] = {"code": ach.reward_item.code, "name": ach.reward_item.name, "new": is_new}
        if ach.reward_coupon_id and ach.reward_coupon.is_distributable():
            c = issue_coupon(user, ach.reward_coupon, source=f"実績「{ach.name}」")
            info["coupon"] = {"id": str(c.pk), "title": ach.reward_coupon.title,
                              "shop": ach.reward_coupon.shop_name}
        unlocked.append(info)
    return unlocked


def achievement_progress(user) -> list[dict]:
    metrics = metrics_for(user)
    done = {ua.achievement_id: ua for ua in UserAchievement.objects.filter(user=user)}
    rows = []
    for ach in Achievement.objects.filter(is_active=True).select_related("reward_item", "reward_coupon"):
        value = metrics.get(ach.kind, 0)
        rows.append({
            "achievement": ach,
            "value": min(value, ach.threshold),
            "achieved": done.get(ach.pk),
        })
    return rows

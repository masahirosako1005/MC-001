from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.timeutil import SEASON_CHOICES, SLOT_CHOICES

SYMBOL_PREFIX = "MIKKE1:"


def new_symbol_token() -> str:
    return secrets.token_urlsafe(18)  # 24 文字・144bit: 推測不可能


class Spot(models.Model):
    """観光スポット。"""

    slug = models.SlugField("スラッグ", max_length=64, unique=True)
    name = models.CharField("名前", max_length=80)
    area = models.CharField("エリア", max_length=80, blank=True)
    description = models.TextField("紹介文", blank=True)
    latitude = models.DecimalField("緯度", max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField("経度", max_digits=9, decimal_places=6, null=True, blank=True)
    radius_m = models.PositiveIntegerField("判定半径(m)", default=300)
    require_location = models.BooleanField(
        "現地確認を必須にする", default=False,
        help_text="ON のとき、受け取り時に端末の位置情報がスポットの判定半径内か確認します",
    )
    is_active = models.BooleanField("公開", default=True)

    class Meta:
        verbose_name = verbose_name_plural = "スポット"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(latitude__isnull=True) | models.Q(latitude__gte=-90, latitude__lte=90),
                name="spot_lat_range",
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__isnull=True) | models.Q(longitude__gte=-180, longitude__lte=180),
                name="spot_lng_range",
            ),
            models.CheckConstraint(condition=models.Q(radius_m__gte=10), name="spot_radius_min"),
            models.CheckConstraint(
                condition=models.Q(require_location=False)
                | models.Q(latitude__isnull=False, longitude__isnull=False),
                name="spot_location_required_has_coords",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Symbol(models.Model):
    """現地に掲示する「みっけシンボル」。カメラで検知すると AR マークが現れる。"""

    spot = models.ForeignKey(Spot, on_delete=models.PROTECT, related_name="symbols", verbose_name="スポット")
    name = models.CharField("名前", max_length=80)
    hint = models.CharField("探すときのヒント", max_length=200, blank=True)
    token = models.CharField("識別トークン", max_length=64, unique=True, default=new_symbol_token, editable=False)
    cooldown_hours = models.PositiveSmallIntegerField(
        "再取得までの時間(時間)", default=20, help_text="同じ人が再びみっけできるまでの時間"
    )
    is_active = models.BooleanField("公開", default=True)

    class Meta:
        verbose_name = verbose_name_plural = "シンボル"
        ordering = ["spot_id", "id"]
        constraints = [models.CheckConstraint(condition=models.Q(cooldown_hours__gte=1), name="symbol_cooldown_pos")]

    def __str__(self) -> str:
        return f"{self.spot.name} / {self.name}"

    @property
    def payload(self) -> str:
        return f"{SYMBOL_PREFIX}{self.token}"


class DropEntry(models.Model):
    """シンボルから出るごほうびの抽選表。季節・時間帯・再訪日数で出現が変わる。"""

    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="drops")
    item = models.ForeignKey("wardrobe.Item", null=True, blank=True, on_delete=models.PROTECT,
                             related_name="drop_entries", verbose_name="アイテム")
    coupon = models.ForeignKey("rewards.CouponTemplate", null=True, blank=True, on_delete=models.PROTECT,
                               related_name="drop_entries", verbose_name="クーポン")
    weight = models.PositiveIntegerField("出やすさ(重み)", default=10)
    season = models.CharField("季節", max_length=8, choices=SEASON_CHOICES, default="any")
    time_slot = models.CharField("時間帯", max_length=8, choices=SLOT_CHOICES, default="any")
    min_visit_days = models.PositiveSmallIntegerField(
        "解放に必要な訪問日数", default=1, help_text="2 なら「2日目の訪問」から出現 (再訪ボーナス)"
    )

    class Meta:
        verbose_name = verbose_name_plural = "ドロップ設定"
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(item__isnull=False, coupon__isnull=True)
                           | models.Q(item__isnull=True, coupon__isnull=False)),
                name="drop_exactly_one_reward",
            ),
            models.CheckConstraint(condition=models.Q(weight__gte=1), name="drop_weight_pos"),
            models.CheckConstraint(condition=models.Q(min_visit_days__gte=1), name="drop_min_visit_pos"),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} → {self.item or self.coupon}"


class SpotVisit(models.Model):
    """スポットへの訪問日 (日本時間の日付単位)。再訪日数・季節の実績判定に使う。"""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="spot_visits")
    spot = models.ForeignKey(Spot, on_delete=models.PROTECT, related_name="visits")
    visit_date = models.DateField("訪問日")
    season = models.CharField("季節", max_length=8, choices=SEASON_CHOICES)
    first_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = verbose_name_plural = "訪問記録"
        constraints = [models.UniqueConstraint(fields=["user", "spot", "visit_date"], name="spotvisit_unique_day")]

    def __str__(self) -> str:
        return f"{self.visit_date} {self.spot_id}"


class Discovery(models.Model):
    """みっけ (受け取り) の記録。ごほうびの内容をスナップショットとして残す (原本性)。"""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="discoveries")
    symbol = models.ForeignKey(Symbol, on_delete=models.PROTECT, related_name="discoveries")
    drop = models.ForeignKey(DropEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reward_kind = models.CharField(max_length=8, choices=[("item", "アイテム"), ("coupon", "クーポン"), ("none", "なし")])
    reward_label = models.CharField(max_length=120, blank=True)
    reward_ref = models.CharField(max_length=64, blank=True)
    is_new = models.BooleanField(default=False)
    idempotency_key = models.UUIDField()
    found_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = verbose_name_plural = "みっけ記録"
        ordering = ["-found_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "idempotency_key"], name="discovery_idempotent"),
        ]
        indexes = [models.Index(fields=["user", "symbol", "-found_at"], name="discovery_cooldown_idx")]

    def __str__(self) -> str:
        return f"{self.found_at:%Y-%m-%d %H:%M} {self.reward_label or '-'}"

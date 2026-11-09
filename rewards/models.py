from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.fields import EncryptedTextField


class CouponTemplate(models.Model):
    """クーポンのひな形 (店舗・特典内容)。探索や実績で利用者ごとに発行される。"""

    code = models.SlugField("コード", max_length=64, unique=True)
    title = models.CharField("タイトル", max_length=80)
    shop_name = models.CharField("店舗名", max_length=80)
    benefit = models.CharField("特典内容", max_length=120)
    description = models.TextField("利用条件", blank=True)
    spot = models.ForeignKey("explore.Spot", null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="coupon_templates", verbose_name="関連スポット")
    valid_days = models.PositiveSmallIntegerField("有効日数", default=30)
    is_active = models.BooleanField("有効", default=True)

    class Meta:
        verbose_name = verbose_name_plural = "クーポン(ひな形)"
        constraints = [
            models.CheckConstraint(condition=models.Q(valid_days__gte=1), name="coupontpl_valid_days_pos"),
        ]

    def __str__(self) -> str:
        return f"{self.shop_name}: {self.title}"


class UserCoupon(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coupons")
    template = models.ForeignKey(CouponTemplate, on_delete=models.PROTECT, related_name="issued")
    redeem_code = EncryptedTextField("引換コード")
    source = models.CharField("入手経路", max_length=120, blank=True)
    issued_at = models.DateTimeField("発行日時", default=timezone.now)
    expires_at = models.DateTimeField("有効期限")
    used_at = models.DateTimeField("使用日時", null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "発行済みクーポン"
        ordering = ["used_at", "expires_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(expires_at__gt=models.F("issued_at")),
                                   name="usercoupon_expiry_after_issue"),
            models.CheckConstraint(
                condition=models.Q(used_at__isnull=True) | models.Q(used_at__gte=models.F("issued_at")),
                name="usercoupon_used_after_issue",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.template_id} ({self.status})"

    @property
    def status(self) -> str:
        if self.used_at:
            return "used"
        if self.expires_at <= timezone.now():
            return "expired"
        return "available"

    @property
    def status_label(self) -> str:
        return {"used": "使用済み", "expired": "期限切れ", "available": "使える"}[self.status]


ACHIEVEMENT_KIND_CHOICES = [
    ("total_discoveries", "みっけた回数の合計"),
    ("distinct_spots", "訪れたスポットの数"),
    ("distinct_items", "集めたアイテムの種類"),
    ("spot_visit_days", "同じスポットに来た日数(最大)"),
    ("seasons_at_spot", "同じスポットで体験した季節の数(最大)"),
]


class Achievement(models.Model):
    """やりこみ報酬 (実績)。条件を満たすと一度だけ付与される。"""

    KIND_CHOICES = ACHIEVEMENT_KIND_CHOICES
    code = models.SlugField("コード", max_length=64, unique=True)
    name = models.CharField("名前", max_length=60)
    description = models.CharField("説明", max_length=200)
    icon = models.CharField("アイコン(絵文字)", max_length=4, default="🏅")
    kind = models.CharField("条件の種類", max_length=32, choices=KIND_CHOICES)
    threshold = models.PositiveIntegerField("達成に必要な値")
    reward_item = models.ForeignKey("wardrobe.Item", null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="+", verbose_name="報酬アイテム")
    reward_coupon = models.ForeignKey(CouponTemplate, null=True, blank=True, on_delete=models.PROTECT,
                                      related_name="+", verbose_name="報酬クーポン")
    sort_order = models.PositiveSmallIntegerField("並び順", default=0)
    is_active = models.BooleanField("有効", default=True)

    class Meta:
        verbose_name = verbose_name_plural = "実績"
        ordering = ["sort_order", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(threshold__gte=1), name="achievement_threshold_pos"),
            models.CheckConstraint(
                condition=models.Q(kind__in=[k for k, _ in ACHIEVEMENT_KIND_CHOICES]), name="achievement_kind_valid"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class UserAchievement(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="achievements")
    achievement = models.ForeignKey(Achievement, on_delete=models.PROTECT, related_name="holders")
    achieved_at = models.DateTimeField("達成日時", default=timezone.now)

    class Meta:
        verbose_name = verbose_name_plural = "達成した実績"
        constraints = [models.UniqueConstraint(fields=["user", "achievement"], name="userachievement_unique")]

    def __str__(self) -> str:
        return f"{self.achievement_id} @ {self.achieved_at:%Y-%m-%d}"

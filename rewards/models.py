from __future__ import annotations

import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.crypto import blind_index
from core.fields import EncryptedTextField

REDEEM_INDEX_PURPOSE = "coupon.redeem"


def redeem_hash_of(code: str) -> str:
    return blind_index(code.strip().upper(), REDEEM_INDEX_PURPOSE)


ID_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 読み間違えやすい文字 (0/O, 1/I/L) を除く


def new_coupon_id() -> str:
    """クーポン (ひな形) そのものの ID。例: CP-7Q4H2Z"""
    return "CP-" + "".join(secrets.choice(ID_ALPHABET) for _ in range(6))


class CouponTemplate(models.Model):
    """クーポンのひな形 (店舗・特典内容)。探索や実績で利用者ごとに発行される。"""

    coupon_id = models.CharField("クーポン ID", max_length=12, unique=True, default=new_coupon_id, editable=False)
    code = models.SlugField("コード", max_length=64, unique=True)
    title = models.CharField("タイトル", max_length=80)
    shop_name = models.CharField("店舗名", max_length=80)
    benefit = models.CharField("特典内容", max_length=120)
    description = models.TextField("利用条件", blank=True)
    spot = models.ForeignKey("explore.Spot", null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="coupon_templates", verbose_name="関連スポット")
    valid_days = models.PositiveSmallIntegerField("有効日数", default=30,
                                                  help_text="受け取ってから使えるまでの日数")
    available_until = models.DateTimeField(
        "有効期限", null=True, blank=True,
        help_text="この日時を過ぎると配布を止め、受け取り済みのクーポンも使えなくなる。空欄なら無期限")
    # 管理者 (店舗・会社) のクーポン。空欄はサイト運営者のクーポン
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="owned_coupons", verbose_name="登録した管理者",
                              limit_choices_to={"role": "manager"})
    is_active = models.BooleanField("配布する", default=True)
    created_at = models.DateTimeField("登録日時", default=timezone.now)

    class Meta:
        verbose_name = verbose_name_plural = "クーポン(ひな形)"
        constraints = [
            models.CheckConstraint(condition=models.Q(valid_days__gte=1), name="coupontpl_valid_days_pos"),
        ]

    def __str__(self) -> str:
        return f"{self.shop_name}: {self.title} ({self.coupon_id})"

    def is_distributable(self, now=None) -> bool:
        now = now or timezone.now()
        return self.is_active and (self.available_until is None or self.available_until > now)

    @property
    def status_label(self) -> str:
        if not self.is_active:
            return "配布停止"
        if self.available_until and self.available_until <= timezone.now():
            return "期限切れ"
        return "配布中"


def distributable_coupons_q(prefix: str = "", now=None) -> models.Q:
    """配布できるクーポン (配布中で、有効期限前)。prefix は "coupon__" など。"""
    now = now or timezone.now()
    return (models.Q(**{f"{prefix}is_active": True})
            & (models.Q(**{f"{prefix}available_until__isnull": True}) | models.Q(**{f"{prefix}available_until__gt": now})))


class UserCoupon(models.Model):
    """利用者ごとに発行したクーポン。

    引換コード (例: MK-ABCD-EFGH) はこの 1 枚だけの ID。暗号化して保存し、重複がないことは
    ブラインドインデックス (redeem_hash) の一意制約で保証する (ほかの人のコードと重ならない)。
    使用は 1 回だけ (services.use_coupon の条件付き UPDATE)。
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coupons")
    template = models.ForeignKey(CouponTemplate, on_delete=models.PROTECT, related_name="issued")
    redeem_code = EncryptedTextField("引換コード")
    redeem_hash = models.CharField("引換コードの照合用ハッシュ", max_length=64, unique=True, editable=False)
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

    def save(self, *args, **kwargs):
        if self.redeem_code:
            self.redeem_hash = redeem_hash_of(self.redeem_code)
        super().save(*args, **kwargs)

    @property
    def status(self) -> str:
        if self.used_at:
            return "used"
        now = timezone.now()
        if self.expires_at <= now:
            return "expired"
        # クーポン自体の有効期限が、受け取り後に短くされた場合
        until = self.template.available_until
        if until is not None and until <= now:
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

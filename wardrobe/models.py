from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .avatar import (
    BODY_TYPE_CHOICES,
    CATEGORY_CHOICES,
    EYE_COLOR_CHOICES,
    ITEM_BODY_CHOICES,
    SKIN_TONE_CHOICES,
    STYLES,
)

HEX_COLOR_RE = r"^#[0-9A-Fa-f]{6}$"


class Item(models.Model):
    """アバター用アイテム。見た目は「形(style)×色」のパラメータで表し、任意 SVG は受け付けない。"""

    code = models.SlugField("コード", max_length=64, unique=True)
    name = models.CharField("名前", max_length=60)
    description = models.CharField("説明", max_length=200, blank=True)
    category = models.CharField("部位", max_length=16, choices=CATEGORY_CHOICES)
    body_type = models.CharField("対象の体のタイプ", max_length=8, choices=ITEM_BODY_CHOICES, default="any",
                                 help_text="女の子用・男の子用・共通。管理者はタイプに関係なく着せられます")
    style = models.CharField("形", max_length=32)
    color = models.CharField("色", max_length=7, help_text="#RRGGBB")
    rarity = models.PositiveSmallIntegerField("レア度", default=1)
    is_starter = models.BooleanField("初期アイテム", default=False)
    is_active = models.BooleanField("有効", default=True)

    class Meta:
        verbose_name = verbose_name_plural = "アイテム"
        ordering = ["category", "rarity", "code"]
        constraints = [
            models.CheckConstraint(condition=models.Q(color__regex=HEX_COLOR_RE), name="item_color_hex"),
            models.CheckConstraint(condition=models.Q(rarity__gte=1, rarity__lte=5), name="item_rarity_1_5"),
            models.CheckConstraint(
                condition=models.Q(category__in=[c for c, _ in CATEGORY_CHOICES]), name="item_category_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(body_type__in=[c for c, _ in ITEM_BODY_CHOICES]), name="item_body_type_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_category_display()})"

    def fits(self, body_type: str) -> bool:
        return self.body_type in ("any", body_type)

    def clean(self):
        if self.style not in STYLES.get(self.category, {}):
            raise ValidationError({"style": f"部位「{self.get_category_display()}」に形「{self.style}」はありません"})

    @property
    def rarity_stars(self) -> str:
        return "★" * self.rarity + "☆" * (5 - self.rarity)


class UserItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="owners")
    obtained_count = models.PositiveIntegerField("入手回数", default=1)
    first_obtained_at = models.DateTimeField("初入手", auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "所持アイテム"
        constraints = [
            models.UniqueConstraint(fields=["user", "item"], name="useritem_unique"),
            models.CheckConstraint(condition=models.Q(obtained_count__gte=1), name="useritem_count_pos"),
        ]

    def __str__(self) -> str:
        return f"{self.item_id} x{self.obtained_count}"


class AvatarConfig(models.Model):
    """現在の着せ替え状態。version による楽観ロックで同時更新を検知する。"""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="avatar")
    body_type = models.CharField("体のタイプ", max_length=8, choices=BODY_TYPE_CHOICES, default="girl",
                                 help_text="だれでも自由に選べる (登録者の性別とは無関係)")
    skin_tone = models.CharField("肌の色", max_length=16, choices=SKIN_TONE_CHOICES, default="tone3")
    eye_color = models.CharField("目の色", max_length=8, choices=EYE_COLOR_CHOICES, default="brown")
    hair = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    top = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    bottom = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    shoes = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    accessory = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "アバター設定"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(skin_tone__in=[c for c, _ in SKIN_TONE_CHOICES]), name="avatar_skin_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(body_type__in=[c for c, _ in BODY_TYPE_CHOICES]), name="avatar_body_type_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(eye_color__in=[c for c, _ in EYE_COLOR_CHOICES]), name="avatar_eye_color_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"avatar v{self.version}"

    def equipped(self) -> dict[str, Item | None]:
        return {c: getattr(self, c) for c, _ in CATEGORY_CHOICES}

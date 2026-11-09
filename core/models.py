from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.db import models

from .themes import DEFAULT_THEME, THEME_CHOICES


class SiteSetting(models.Model):
    """サイト全体の設定 (1 行だけ)。UI テーマを管理画面から切り替える。"""

    ui_theme = models.CharField("UI テーマ", max_length=32, choices=THEME_CHOICES, default=DEFAULT_THEME,
                                help_text="利用者全員に適用されます。管理者は URL に ?ui=テーマ名 を付けると自分だけ試せます")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", verbose_name="更新者")
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    CACHE_KEY = "mikke:site-setting"

    class Meta:
        verbose_name = verbose_name_plural = "サイト設定"
        constraints = [
            models.CheckConstraint(condition=models.Q(ui_theme__in=[k for k, _ in THEME_CHOICES]),
                                   name="sitesetting_theme_valid"),
        ]

    def __str__(self) -> str:
        return "サイト設定"

    def save(self, *args, **kwargs):
        self.pk = 1  # 常に 1 行
        super().save(*args, **kwargs)
        cache.delete(self.CACHE_KEY)

    @classmethod
    def current(cls) -> SiteSetting:
        obj = cache.get(cls.CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(cls.CACHE_KEY, obj, 60)
        return obj


class AuditLog(models.Model):
    """監査ログ (追記のみ)。誰が・いつ・何を・どう変えたかを記録する。

    個人情報は残さない: IP アドレスは HMAC 化した値のみ保存する。
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField("操作", max_length=64, db_index=True)
    target_type = models.CharField("対象種別", max_length=64, blank=True)
    target_id = models.CharField("対象ID", max_length=64, blank=True)
    detail = models.JSONField("詳細", default=dict, blank=True)
    ip_hash = models.CharField("IP(HMAC)", max_length=64, blank=True)
    created_at = models.DateTimeField("記録日時", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = verbose_name_plural = "監査ログ"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("監査ログは更新できません")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("監査ログは削除できません")

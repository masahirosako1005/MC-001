from __future__ import annotations

from django.conf import settings
from django.db import models


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

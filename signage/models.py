"""まちのデジタルサイネージ (ランキング 1 位のコーデ + 運営者が書いた宣伝の文 + QR コード)。

- サイト運営者が「運営コンソール > サイネージ」で作り、表示用の URL (/signage/<表示キー>/) を
  サイネージの端末 (ブラウザ) で開いておく。端末はログイン不要
- 表示キーはランダムで推測できない。漏れたら作り直せる (古い URL は表示されなくなる)
"""

from __future__ import annotations

import secrets

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def new_display_key() -> str:
    return secrets.token_urlsafe(24)  # 32 文字・192bit


class Signage(models.Model):
    name = models.CharField("名前 (設置場所など)", max_length=60, help_text="管理用。画面には出ません。例: 京橋駅 北口")
    headline = models.CharField("見出し", max_length=40, default="いまのコーデ王",
                                help_text="ランキング 1 位の上に大きく出る文字")
    message = models.TextField("宣伝の文", max_length=200, blank=True,
                               help_text="まちの宣伝やイベントの案内など (200 文字まで、改行できます)")
    show_qr = models.BooleanField("QR コードを出す", default=True)
    qr_url = models.URLField("QR コードのリンク先", blank=True,
                             help_text="空欄ならこのサイトのトップ。公開している URL を入れてください")
    refresh_seconds = models.PositiveSmallIntegerField(
        "表示を更新する間隔 (秒)", default=60, validators=[MinValueValidator(15), MaxValueValidator(3600)],
        help_text="ランキングが変わったら、この間隔で表示に反映されます (15〜3600 秒)")
    display_key = models.CharField("表示キー", max_length=64, unique=True, default=new_display_key, editable=False)
    is_active = models.BooleanField("表示する", default=True, help_text="止めると表示用の URL を開いても何も出ません")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", verbose_name="最後に更新したサイト運営者")
    created_at = models.DateTimeField("作成日時", default=timezone.now)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "サイネージ"
        ordering = ["name", "pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(refresh_seconds__gte=15, refresh_seconds__lte=3600),
                                   name="signage_refresh_range"),
        ]

    def __str__(self) -> str:
        return self.name

    def regenerate_key(self) -> None:
        self.display_key = new_display_key()

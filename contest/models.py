from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Contest(models.Model):
    """アバターのコーデコンテスト。"""

    title = models.CharField("タイトル", max_length=80)
    theme = models.CharField("テーマ", max_length=200, blank=True)
    starts_at = models.DateTimeField("開始日時")
    ends_at = models.DateTimeField("終了日時")
    rounds = models.PositiveSmallIntegerField("評価の回数", default=3)
    per_round = models.PositiveSmallIntegerField("1 回に表示する数", default=3)
    bot_cutoff = models.PositiveSmallIntegerField(
        "BOT を表示しなくなる参加人数", default=10,
        help_text="実際の参加者がこの人数に達したら、評価画面に BOT を出さない",
    )
    is_active = models.BooleanField("公開", default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = verbose_name_plural = "コンテスト"
        ordering = ["-starts_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="contest_period_valid"),
            models.CheckConstraint(condition=models.Q(rounds__gte=1, rounds__lte=10), name="contest_rounds_range"),
            models.CheckConstraint(condition=models.Q(per_round__gte=2, per_round__lte=6), name="contest_per_round_range"),
        ]

    def __str__(self) -> str:
        return self.title

    def is_open(self, now=None) -> bool:
        now = now or timezone.now()
        return self.is_active and self.starts_at <= now < self.ends_at


class ContestEntry(models.Model):
    """エントリー。アバターはエントリー時点の見た目を保存する (後で着替えても変わらない)。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE, related_name="entries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                             related_name="contest_entries")
    is_bot = models.BooleanField("BOT", default=False)
    display_name = models.CharField("表示名", max_length=20)
    avatar = models.JSONField("アバター (エントリー時点)")
    impressions = models.PositiveIntegerField("表示回数", default=0)
    likes = models.PositiveIntegerField("高評価数", default=0)
    created_at = models.DateTimeField("エントリー日時", default=timezone.now)

    class Meta:
        verbose_name = verbose_name_plural = "エントリー"
        ordering = ["contest_id", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["contest", "user"], name="contestentry_one_per_user"),
            models.CheckConstraint(
                condition=(models.Q(is_bot=True, user__isnull=True) | models.Q(is_bot=False, user__isnull=False)),
                name="contestentry_bot_has_no_user",
            ),
        ]
        indexes = [models.Index(fields=["contest", "is_bot", "impressions"], name="contestentry_pick_idx")]

    def __str__(self) -> str:
        return f"{self.display_name}{' (BOT)' if self.is_bot else ''}"


class EvaluationRound(models.Model):
    """評価 1 回分。表示した候補 (最大 per_round 体) と、高評価を付けた 1 体 (付けなくてもよい) を記録する。"""

    contest = models.ForeignKey(Contest, on_delete=models.CASCADE, related_name="rounds_log")
    voter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contest_rounds")
    round_no = models.PositiveSmallIntegerField("何回目")
    candidates = models.ManyToManyField(ContestEntry, related_name="shown_in", verbose_name="表示した候補")
    chosen = models.ForeignKey(ContestEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                               verbose_name="高評価した候補")
    created_at = models.DateTimeField(default=timezone.now)
    answered_at = models.DateTimeField("回答日時", null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "評価の記録"
        ordering = ["contest_id", "voter_id", "round_no"]
        constraints = [
            models.UniqueConstraint(fields=["contest", "voter", "round_no"], name="evalround_unique_no"),
            models.CheckConstraint(condition=models.Q(round_no__gte=1), name="evalround_no_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.contest_id}/{self.voter_id}#{self.round_no}"

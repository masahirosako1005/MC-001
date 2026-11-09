from __future__ import annotations

import unicodedata

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from core.crypto import blind_index, normalize_email
from core.fields import EncryptedTextField

EMAIL_INDEX_PURPOSE = "user.email"


def email_hash_of(email: str) -> str:
    return blind_index(normalize_email(email), EMAIL_INDEX_PURPOSE)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, username):
        # ログインフォームにはメールアドレスが入力される → ブラインドインデックスで照合
        return self.get(email_hash=email_hash_of(username))

    def create_user(self, email: str, password: str | None = None, nickname: str = "", **extra):
        if not email:
            raise ValueError("メールアドレスは必須です")
        user = self.model(email=normalize_email(email), nickname=nickname or "たんけんか", **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str, nickname: str = "運営", **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self.create_user(email, password, nickname, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """利用者。メールアドレスは暗号化して保存し、照合はブラインドインデックスで行う。"""

    email = EncryptedTextField("メールアドレス")
    email_hash = models.CharField("メール照合用ハッシュ", max_length=64, unique=True, editable=False)
    nickname = models.CharField("ニックネーム", max_length=30)
    is_active = models.BooleanField("有効", default=True)
    is_staff = models.BooleanField("運営スタッフ", default=False)
    date_joined = models.DateTimeField("登録日時", default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email_hash"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = verbose_name_plural = "利用者"
        constraints = [
            models.CheckConstraint(condition=~models.Q(nickname=""), name="user_nickname_not_empty"),
        ]

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        self.email_hash = email_hash_of(self.email)
        self.nickname = unicodedata.normalize("NFC", self.nickname).strip()
        super().save(*args, **kwargs)

    def get_short_name(self) -> str:
        return self.nickname

    def get_full_name(self) -> str:
        return self.nickname

    def __str__(self) -> str:
        return f"{self.nickname} (#{self.pk})"

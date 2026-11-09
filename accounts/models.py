from __future__ import annotations

import unicodedata

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from core.crypto import blind_index, normalize_email
from core.fields import EncryptedTextField
from core.ids import random_code, unique_code

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
        extra.update(is_staff=True, is_superuser=True, role=User.ROLE_OPERATOR)
        return self.create_user(email, password, nickname, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """みっけのアカウント。メールアドレスは暗号化して保存し、照合はブラインドインデックスで行う。

    権限は 3 種類:
      利用者 (user)      … みっけを楽しむ。自分で登録・退会できる
      管理者 (manager)   … 店舗・会社の担当者。自分のスポットとシンボルを登録・設定できる (サイト運営者が追加)
      サイト運営者 (operator) … 利用者管理・分析。専用のログイン画面からだけログインできる
    """

    ROLE_USER = "user"
    ROLE_MANAGER = "manager"
    ROLE_OPERATOR = "operator"
    ROLE_CHOICES = [(ROLE_USER, "利用者"), (ROLE_MANAGER, "管理者"), (ROLE_OPERATOR, "サイト運営者")]

    email = EncryptedTextField("メールアドレス")
    email_hash = models.CharField("メール照合用ハッシュ", max_length=64, unique=True, editable=False)
    nickname = models.CharField("ニックネーム", max_length=30)
    role = models.CharField("権限", max_length=16, choices=ROLE_CHOICES, default=ROLE_USER, db_index=True)
    is_active = models.BooleanField("有効", default=True)
    # Django 管理画面に入れるのはサイト運営者だけ (role から自動で決まる)
    is_staff = models.BooleanField("サイト運営者(管理画面)", default=False, editable=False)
    must_change_password = models.BooleanField(
        "次回ログイン時にパスワード変更", default=False,
        help_text="サイト運営者が発行した仮パスワードのアカウントは、最初にパスワードを変更してもらう")
    # みっけしたとき「こんな人が獲得しているよ」に、ニックネームとアバターを出してよいか (本人が選ぶ)
    share_activity = models.BooleanField(
        "みっけ仲間に表示する", default=False,
        help_text=f"ON のとき、同じスポットで {settings.MIKKE_FINDER_WINDOW_MINUTES} 分以内にみっけした人に、"
                  "ニックネームと今のコーデが表示されます")
    date_joined = models.DateTimeField("登録日時", default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email_hash"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = verbose_name_plural = "アカウント"
        constraints = [
            models.CheckConstraint(condition=~models.Q(nickname=""), name="user_nickname_not_empty"),
            models.CheckConstraint(condition=models.Q(role__in=["user", "manager", "operator"]), name="user_role_valid"),
            # 特権 (is_superuser) はサイト運営者にしか持たせない
            models.CheckConstraint(condition=models.Q(is_superuser=False) | models.Q(role="operator"),
                                   name="user_superuser_is_operator"),
        ]

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        self.email_hash = email_hash_of(self.email)
        self.nickname = unicodedata.normalize("NFC", self.nickname).strip()
        self.is_staff = self.role == self.ROLE_OPERATOR
        super().save(*args, **kwargs)

    @property
    def is_operator(self) -> bool:
        return self.role == self.ROLE_OPERATOR

    @property
    def is_manager(self) -> bool:
        return self.role == self.ROLE_MANAGER

    @property
    def can_manage_spots(self) -> bool:
        """スポット・シンボルの登録や設定ができるか (管理者は自分のスポットだけ、サイト運営者はすべて)。"""
        return self.is_active and self.role in (self.ROLE_MANAGER, self.ROLE_OPERATOR)

    def get_short_name(self) -> str:
        return self.nickname

    def get_full_name(self) -> str:
        return self.nickname

    def __str__(self) -> str:
        return f"{self.nickname} (#{self.pk})"


def new_manager_code() -> str:
    """管理者のユニーク ID (例: MK-7Q4H2Z)。紛らわしい文字 (0/O, 1/I/L) は使わない。"""
    return "MK-" + random_code(6)


class ManagerProfile(models.Model):
    """管理者 (店舗・会社の担当者) の基本情報。住所・電話番号は暗号化して保存する。"""

    INDUSTRY_CHOICES = [
        ("shop", "小売・物販"), ("food", "飲食"), ("lodging", "宿泊"), ("sightseeing", "観光施設・寺社"),
        ("transport", "交通"), ("municipality", "自治体・観光協会"), ("event", "イベント"), ("other", "その他"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="manager_profile")
    manager_code = models.CharField("管理者 ID", max_length=12, unique=True, default=new_manager_code, editable=False)
    organization = models.CharField("会社・団体名", max_length=100)
    store_name = models.CharField("店舗・施設名", max_length=100, blank=True)
    industry = models.CharField("業種", max_length=16, choices=INDUSTRY_CHOICES, default="shop")
    contact_name = models.CharField("担当者名", max_length=60)
    postal_code = models.CharField("郵便番号", max_length=8, blank=True, help_text="例: 534-0024")
    address = EncryptedTextField("住所", blank=True)
    phone = EncryptedTextField("電話番号", blank=True)
    website = models.URLField("Web サイト", blank=True)
    note = models.TextField("運営メモ", blank=True, help_text="サイト運営者だけが見るメモ")
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                   verbose_name="追加したサイト運営者")
    created_at = models.DateTimeField("登録日時", default=timezone.now)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "管理者の基本情報"
        constraints = [
            models.CheckConstraint(condition=models.Q(postal_code="") | models.Q(postal_code__regex=r"^\d{3}-?\d{4}$"),
                                   name="manager_postal_code_format"),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.manager_code})"

    def save(self, *args, **kwargs):
        if self._state.adding:  # 管理者 ID が既存と重なったら作り直す
            others = ManagerProfile.objects.exclude(pk=self.pk)
            if others.filter(manager_code=self.manager_code).exists():
                self.manager_code = unique_code(new_manager_code, lambda c: others.filter(manager_code=c).exists())
        super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        return f"{self.organization} {self.store_name}".strip()

"""運営管理者を作成する (メールは暗号化保存のため createsuperuser の代わりに使う)。

    python manage.py createadmin --email ops@example.com
パスワードは対話入力 (画面に表示されない) または環境変数 MIKKE_ADMIN_PASSWORD。
"""

from __future__ import annotations

import getpass
import os

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User, email_hash_of


class Command(BaseCommand):
    help = "運営管理者アカウントを作成します"

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--nickname", default="運営")

    def handle(self, *args, **opts):
        email = opts["email"]
        if User.objects.filter(email_hash=email_hash_of(email)).exists():
            raise CommandError("このメールアドレスは登録済みです")
        password = os.environ.get("MIKKE_ADMIN_PASSWORD") or getpass.getpass("パスワード: ")
        try:
            password_validation.validate_password(password)
        except ValidationError as exc:
            raise CommandError(" / ".join(exc.messages)) from exc
        user = User.objects.create_superuser(email, password, opts["nickname"])
        self.stdout.write(self.style.SUCCESS(f"管理者 #{user.pk} を作成しました"))

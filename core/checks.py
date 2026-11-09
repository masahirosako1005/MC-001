"""デプロイ前の確認 (python manage.py check --deploy で実行される)。

- レート制限・ログインロックのキャッシュがプロセス内 (locmem) のままでないか
- 開発用シードが作る確認用アカウント (manager@test.com など) が本番 DB に残っていないか
"""

from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

TEST_ACCOUNT_EMAILS = ("test@test.com", "manager@test.com", "user@test.com")


@register(Tags.security, deploy=True)
def check_cache_backend(app_configs, **kwargs):
    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if backend.endswith("LocMemCache"):
        return [Error(
            "キャッシュがプロセス内 (LocMemCache) です。複数プロセスではログインロック・レート制限が効きません。",
            hint="MIKKE_CACHE=db (createcachetable が必要) または MIKKE_CACHE=redis://… を設定してください。",
            id="mikke.E001",
        )]
    return []


@register(Tags.security, deploy=True)
def check_test_accounts(app_configs, databases=None, **kwargs):
    if not databases:
        return []
    from django.db.utils import DatabaseError

    from accounts.models import User, email_hash_of

    found = []
    try:
        for email in TEST_ACCOUNT_EMAILS:
            if User.objects.filter(email_hash=email_hash_of(email)).exists():
                found.append(email)
    except DatabaseError:  # マイグレーション前など。ここでは判定しない
        return []
    if not found:
        return []
    return [Error(
        f"開発用の確認アカウントが残っています: {', '.join(found)}",
        hint="本番では削除してください (seed_demo_users --delete / seed_analytics --delete、または管理画面)。",
        id="mikke.E002",
    )]


@register(Tags.security, deploy=True)
def check_debug_like_settings(app_configs, **kwargs):
    issues = []
    if not settings.SESSION_COOKIE_SECURE or not settings.CSRF_COOKIE_SECURE:
        issues.append(Warning(
            "DJANGO_SECURE_COOKIES が無効です。HTTPS で配信する本番では有効にしてください。",
            id="mikke.W001",
        ))
    return issues

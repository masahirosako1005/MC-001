from __future__ import annotations

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from . import audit


@receiver(user_logged_in)
def _logged_in(sender, request, user, **kwargs):
    audit.record("auth.login", request=request, actor=user)


@receiver(user_logged_out)
def _logged_out(sender, request, user, **kwargs):
    if user is not None:
        audit.record("auth.logout", request=request, actor=user)


@receiver(user_login_failed)
def _login_failed(sender, credentials, request=None, **kwargs):
    # 入力されたメールアドレスそのものは記録しない
    audit.record("auth.login_failed", request=request, actor=None)

"""テスト用の補助。"""

from __future__ import annotations

from django.conf import settings


def ops_login(client, user) -> None:
    """運営側 (サイト運営者の画面・管理画面) のセッションでログインする。

    Django の force_login は利用者側の Cookie (SESSION_COOKIE_NAME) にセッションを入れるので、
    運営側の Cookie (OPS_SESSION_COOKIE_NAME) に付け替える (core.sessions)。
    """
    client.force_login(user)
    key = client.cookies.pop(settings.SESSION_COOKIE_NAME).value
    client.cookies[settings.OPS_SESSION_COOKIE_NAME] = key

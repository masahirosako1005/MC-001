"""ログインセッションを「利用者側」と「運営側」で分ける。

- 運営側 (サイト運営者の画面 MIKKE_OPS_URL と Django 管理画面 DJANGO_ADMIN_URL) は専用の Cookie
  (OPS_SESSION_COOKIE_NAME) のセッションだけを読む。利用者側はふつうのセッション Cookie だけを読む
- そのため、運営者としてログインしても利用者側の画面ではログインしていない状態になり、利用者の機能は使えない。
  逆に、利用者・管理者のログインで運営側に入ることもできない
- 同じブラウザで、運営側と利用者側に別々のアカウントでログインしておくこともできる
"""

from __future__ import annotations

import time

from django.conf import settings
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils.cache import patch_vary_headers
from django.utils.http import http_date

REALM_USER = "user"
REALM_OPS = "ops"


def ops_prefixes() -> tuple[str, ...]:
    return tuple("/" + p.lstrip("/") for p in (settings.OPS_URL, settings.ADMIN_URL))


def realm_of(path: str) -> str:
    return REALM_OPS if path.startswith(ops_prefixes()) else REALM_USER


def cookie_name(realm: str) -> str:
    return settings.OPS_SESSION_COOKIE_NAME if realm == REALM_OPS else settings.SESSION_COOKIE_NAME


class RealmSessionMiddleware(SessionMiddleware):
    """Django の SessionMiddleware と同じ動きで、URL によって使う Cookie 名だけを切り替える。"""

    def process_request(self, request):
        request.session_realm = realm_of(request.path_info)
        request.session = self.SessionStore(request.COOKIES.get(cookie_name(request.session_realm)))

    def process_response(self, request, response):
        try:
            accessed = request.session.accessed
            modified = request.session.modified
            empty = request.session.is_empty()
        except AttributeError:
            return response
        name = cookie_name(getattr(request, "session_realm", REALM_USER))
        if name in request.COOKIES and empty:
            response.delete_cookie(name, path=settings.SESSION_COOKIE_PATH, domain=settings.SESSION_COOKIE_DOMAIN,
                                   samesite=settings.SESSION_COOKIE_SAMESITE)
            need_vary_cookie = True
        else:
            need_vary_cookie = accessed
            if (modified or settings.SESSION_SAVE_EVERY_REQUEST) and not empty:
                if request.session.get_expire_at_browser_close():
                    max_age = expires = None
                else:
                    max_age = request.session.get_expiry_age()
                    expires = http_date(time.time() + max_age)
                if response.status_code < 500:
                    try:
                        request.session.save()
                    except UpdateError:
                        raise SessionInterrupted(
                            "The request's session was deleted before the request completed.") from None
                    response.set_cookie(
                        name, request.session.session_key, max_age=max_age, expires=expires,
                        domain=settings.SESSION_COOKIE_DOMAIN, path=settings.SESSION_COOKIE_PATH,
                        secure=settings.SESSION_COOKIE_SECURE or None,
                        httponly=settings.SESSION_COOKIE_HTTPONLY or None,
                        samesite=settings.SESSION_COOKIE_SAMESITE,
                    )
                    need_vary_cookie = True
        if need_vary_cookie:
            patch_vary_headers(response, ("Cookie",))
        return response

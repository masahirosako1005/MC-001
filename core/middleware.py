from __future__ import annotations


class UiThemeMiddleware:
    """表示する UI テーマを決める (運営者の「サイト設定」で選ばれたテーマ。利用者全員に共通)。

    以前は管理者が ?ui=<テーマ名> で自分だけ試せたが、運営者・管理者は利用者の画面を開けなくなったため廃止した
    (試すときは利用者のアカウントで見る)。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .models import SiteSetting
        from .themes import get_theme

        request.ui_theme = get_theme(SiteSetting.current().ui_theme)
        return self.get_response(request)


def _url_name(request) -> tuple[str | None, str]:
    """(\"名前空間:名前\", 名前空間)。URL が見つからなければ (None, "")。"""
    from django.urls import Resolver404, resolve

    try:
        match = resolve(request.path_info)
    except Resolver404:
        return None, ""
    return (f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name), match.namespace


def _wants_json(request) -> bool:
    return "/api/" in request.path_info or "application/json" in request.headers.get("Accept", "")


class RoleAreaMiddleware:
    """利用者 / 管理者 / サイト運営者の画面を完全に分ける。

    - 運営側 (core.sessions の REALM_OPS) のセッションに入れるのはサイト運営者だけ
    - 利用者側でサイト運営者としてログインしている状態は作らない (以前の版で残ったログインはここで消す)
    - 管理者が使えるのは管理者の画面 (/manage/) とログアウト・パスワード変更だけ。利用者の画面 (きせかえ・みっけ・
      コンテスト・クーポンなど) を開くと管理者の画面へ戻す。遊ぶときは利用者として別のアカウントを登録する
    - 利用者が管理者・運営者の画面を開いたときは、各画面の権限チェック (403 / 404) が働く
    """

    MANAGER_ALLOWED = {"accounts:logout", "accounts:password_change", "accounts:login", "accounts:password_help"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.contrib.auth import logout

        from .sessions import REALM_OPS

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            if getattr(request, "session_realm", None) == REALM_OPS:
                if not (user.is_active and user.is_operator):
                    logout(request)
            elif user.is_operator:
                logout(request)
                return self._away(request, "ops:dashboard")
            elif user.is_manager:
                name, namespace = _url_name(request)
                if name is not None and namespace != "manage" and name not in self.MANAGER_ALLOWED:
                    return self._away(request, "manage:home")
        return self.get_response(request)

    @staticmethod
    def _away(request, url_name: str):
        from django.http import JsonResponse
        from django.shortcuts import redirect

        if _wants_json(request):
            return JsonResponse({"error": "wrong_area", "message": "この画面は利用者専用です。"}, status=403)
        return redirect(url_name)


class ForcePasswordChangeMiddleware:
    """サイト運営者が発行した仮パスワードでログインした人には、まずパスワードを変えてもらう。"""

    ALLOWED_NAMES = {"accounts:password_change", "accounts:logout", "ops:password_change", "ops:logout"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.must_change_password:
            from django.conf import settings
            from django.shortcuts import redirect

            from .sessions import REALM_OPS

            name, _ = _url_name(request)
            static = request.path_info.startswith("/" + settings.STATIC_URL.lstrip("/"))
            if name not in self.ALLOWED_NAMES and not static:
                # JSON API には画面への転送ではなく 403 JSON を返す (fetch が HTML を受け取らないように)
                if _wants_json(request):
                    from django.http import JsonResponse

                    return JsonResponse({"error": "password_change_required",
                                         "message": "パスワードを変更してから、もう一度お試しください。"}, status=403)
                ops = getattr(request, "session_realm", None) == REALM_OPS
                return redirect("ops:password_change" if ops else "accounts:password_change")
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Django 標準で付かない追加のセキュリティヘッダーを付与する。"""

    PERMISSIONS_POLICY = (
        "camera=(self), geolocation=(self), microphone=(), payment=(), usb=(), "
        "interest-cohort=()"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Permissions-Policy", self.PERMISSIONS_POLICY)
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            # 個人のデータを含むページは共有キャッシュに残さない
            response.headers.setdefault("Cache-Control", "private, no-store")
        return response

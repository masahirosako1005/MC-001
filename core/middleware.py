from __future__ import annotations


class UiThemeMiddleware:
    """表示する UI テーマを決める。

    - 通常: 管理画面の「サイト設定」で選ばれたテーマ (全員共通)
    - 管理者のみ: URL に ?ui=<テーマ名> を付けると、自分のセッションだけでそのテーマを試せる (?ui=reset で解除)
    """

    SESSION_KEY = "ui_preview"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .models import SiteSetting
        from .themes import THEMES, get_theme

        user = getattr(request, "user", None)
        is_staff = bool(user and user.is_authenticated and user.is_staff)
        if is_staff and "ui" in request.GET:
            value = request.GET["ui"]
            if value == "reset":
                request.session.pop(self.SESSION_KEY, None)
            elif value in THEMES:
                request.session[self.SESSION_KEY] = value
        preview = request.session.get(self.SESSION_KEY) if is_staff else None
        request.ui_previewing = bool(preview)
        request.ui_theme = get_theme(preview or SiteSetting.current().ui_theme)
        return self.get_response(request)


class ForcePasswordChangeMiddleware:
    """サイト運営者が発行した仮パスワードでログインした人には、まずパスワードを変えてもらう。"""

    ALLOWED_NAMES = {"accounts:password_change", "accounts:logout"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.must_change_password:
            from django.conf import settings
            from django.shortcuts import redirect
            from django.urls import Resolver404, resolve

            try:
                match = resolve(request.path_info)
                name = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
            except Resolver404:
                name = None
            static = request.path_info.startswith("/" + settings.STATIC_URL.lstrip("/"))
            if name not in self.ALLOWED_NAMES and not static:
                return redirect("accounts:password_change")
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

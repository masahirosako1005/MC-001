from __future__ import annotations


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

"""共通の HTTP 応答。"""

from __future__ import annotations

from django.http import HttpResponse, JsonResponse

# SVG 単体で開かれた場合もスクリプトを実行させない (サンドボックス)
SVG_CSP = "default-src 'none'; style-src 'unsafe-inline'; sandbox"


def svg_response(svg: str, *, cache: str = "private, no-store", filename: str | None = None) -> HttpResponse:
    """サーバーで組み立てた SVG を返す。cache は Cache-Control の値。filename を渡すとダウンロードさせる。"""
    resp = HttpResponse(svg, content_type="image/svg+xml; charset=utf-8")
    resp.headers["Content-Security-Policy"] = SVG_CSP
    resp.headers["Cache-Control"] = cache
    if filename:
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def too_many_requests(*, json: bool = True) -> HttpResponse:
    if json:
        return JsonResponse({"error": "rate_limited", "message": "少し時間をおいてお試しください。"}, status=429)
    return HttpResponse("少し時間をおいてお試しください。", status=429, content_type="text/plain; charset=utf-8")

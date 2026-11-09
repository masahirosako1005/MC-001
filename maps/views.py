"""ローカルの PMTiles ファイルを HTTP Range リクエストで配信する。

protomaps-leaflet は PMTiles の必要な部分だけを Range リクエストで読む (HTTP Byte Serving)。
Django 標準の静的ファイル配信は Range に対応しないため、専用のビューで配信する。
外部の地図 API にはアクセスしない。
"""

from __future__ import annotations

import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_http_methods

NAME_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
MAX_RANGE = 8 * 1024 * 1024


def _tile_path(name: str):
    if not NAME_RE.match(name):
        raise Http404
    path = (settings.MIKKE_TILES_DIR / f"{name}.pmtiles").resolve()
    if path.parent != settings.MIKKE_TILES_DIR.resolve() or not path.is_file():
        raise Http404
    return path


def parse_range(header: str, size: int) -> tuple[int, int] | None:
    """単一の bytes 範囲を (開始, 終了[含む]) で返す。不正なら None。"""
    m = RANGE_RE.match(header.strip())
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return None
    if m.group(1) == "":  # 末尾 n バイト
        n = int(m.group(2))
        if n == 0:
            return None
        start, end = max(size - n, 0), size - 1
    else:
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
    if start > end or start >= size or end - start + 1 > MAX_RANGE:
        return None
    return start, end


@login_required
@require_http_methods(["GET", "HEAD"])
def pmtiles(request, name: str):
    path = _tile_path(name)
    stat = path.stat()
    size = stat.st_size
    etag = f'"{size:x}-{int(stat.st_mtime):x}"'
    common = {"Accept-Ranges": "bytes", "ETag": etag, "Cache-Control": "private, max-age=86400"}

    rng = request.headers.get("Range")
    if not rng:
        resp = FileResponse(path.open("rb"), content_type="application/octet-stream")
        for k, v in common.items():
            resp[k] = v
        return resp

    parsed = parse_range(rng, size)
    if parsed is None:
        resp = HttpResponse(status=416)
        resp["Content-Range"] = f"bytes */{size}"
        return resp
    start, end = parsed
    with path.open("rb") as f:
        f.seek(start)
        data = f.read(end - start + 1)
    resp = HttpResponse(data, status=206, content_type="application/octet-stream")
    resp["Content-Range"] = f"bytes {start}-{end}/{size}"
    for k, v in common.items():
        resp[k] = v
    return resp

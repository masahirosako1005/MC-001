"""サイネージの表示画面 (ログイン不要。表示キーの URL でだけ開ける)。"""

from __future__ import annotations

from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from contest.services import featured_contest, public_top, snapshot_svg
from core.http import svg_response

from . import services
from .models import Signage


def _signage_or_404(key: str) -> Signage:
    signage = Signage.objects.filter(display_key=key, is_active=True).first() if len(key) <= 64 else None
    if signage is None:
        raise Http404
    return signage


@require_GET
def display(request, key: str):
    signage = _signage_or_404(key)
    ctx = services.board(signage, request.build_absolute_uri("/"), reverse("signage:rank1_svg", args=[key]))
    resp = render(request, "signage/display.html", ctx)
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


@require_GET
def rank1_svg(request, key: str):
    _signage_or_404(key)
    rows = public_top(featured_contest(), 1)
    if not rows:
        raise Http404
    return svg_response(snapshot_svg(rows[0]["entry"].avatar, label=f"ランキング1位 {rows[0]['label']}"),
                        cache="no-cache")

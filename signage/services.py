"""サイネージに出す内容をまとめる (表示画面と、運営コンソールのプレビューで共通)。"""

from __future__ import annotations

import segno
from django.utils.safestring import mark_safe

from contest.services import featured_contest, public_top
from core.timeutil import SEASON_LABELS, SLOT_LABELS, local_now, season_of, slot_of

from .models import Signage


def qr_svg(url: str) -> str:
    """リンク先の QR コード (SVG。大きさは表示側の CSS で決める)。"""
    qr = segno.make(url, error="m", micro=False)
    return mark_safe(qr.svg_inline(scale=1, border=2, omitsize=True, dark="#1F2A44", light="#FFFFFF"))  # noqa: S308


def board(signage: Signage, site_url: str, avatar_url: str) -> dict:
    """サイネージ 1 枚分の内容。ランキング 1 位がいなければ top は None (「集計中」を出す)。

    1 位の名前は、本人が「みっけ仲間に表示する」を ON にしているときだけ出す (contest.services.public_top)。
    """
    now = local_now()
    contest = featured_contest()
    rows = public_top(contest, 1)
    url = signage.qr_url or site_url
    return {
        "signage": signage,
        "contest": contest,
        "top": rows[0] if rows else None,
        "avatar_url": avatar_url,
        "qr": qr_svg(url) if signage.show_qr else "",
        "qr_url": url,
        "season": SEASON_LABELS[season_of(now.date())],
        "slot": SLOT_LABELS[slot_of(now)],
    }

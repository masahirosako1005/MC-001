"""クーポンの絵 (チケット型の SVG)。みっけしたときの結果画面やクーポン画面で使う。

文字はすべて XML エスケープし、長さも切り詰める (管理画面で入力された値をそのまま SVG に入れない)。
"""

from __future__ import annotations

import hashlib
from xml.sax.saxutils import escape

# (背景の上, 背景の下, 文字の強調色)
PALETTES = [
    ("#FF9A5A", "#FF5E7E", "#FFF3B0"),
    ("#5AC8FA", "#4A6CF7", "#FFF3B0"),
    ("#6DD58C", "#1E9E6A", "#FFFBE0"),
    ("#B88CFF", "#7A4FB8", "#FFE680"),
    ("#FFC94D", "#FF8A3D", "#FFFFFF"),
]


def _lines(text: str, width: int, max_lines: int) -> list[str]:
    """全角換算でおよそ width 文字ごとに折り返す (日本語は単語の区切りがないため文字数で区切る)。"""
    text = " ".join((text or "").split())
    out: list[str] = []
    cur, cur_w = "", 0.0
    for ch in text:
        w = 0.55 if ch.isascii() else 1.0
        if cur_w + w > width:
            out.append(cur)
            cur, cur_w = "", 0.0
        cur += ch
        cur_w += w
    if cur:
        out.append(cur)
    if len(out) > max_lines:
        out = out[:max_lines]
        out[-1] = out[-1][:-1] + "…"
    return out


def palette_for(code: str) -> tuple[str, str, str]:
    h = int(hashlib.sha256((code or "").encode()).hexdigest()[:8], 16)
    return PALETTES[h % len(PALETTES)]


def coupon_svg(*, code: str, title: str, shop: str, benefit: str, used: bool = False) -> str:
    top, bottom, accent = palette_for(code)
    gid = "cg" + hashlib.sha256((code or "").encode()).hexdigest()[:8]  # インライン表示時の id 衝突を避ける
    title_lines = _lines(title, 9, 2)
    benefit_lines = _lines(benefit, 15, 2)
    shop_line = _lines(shop, 15, 1)
    t_y = 92 if len(title_lines) == 1 else 80
    texts = [
        f'<text x="24" y="44" font-size="14" font-weight="700" fill="#FFFFFF" opacity="0.92">{escape(shop_line[0]) if shop_line else ""}</text>'
    ]
    for i, line in enumerate(title_lines):
        texts.append(f'<text x="24" y="{t_y + i * 28}" font-size="22" font-weight="900" fill="{accent}" '
                     f'stroke="#00000033" stroke-width="3" paint-order="stroke">{escape(line)}</text>')
    for i, line in enumerate(benefit_lines):
        texts.append(f'<text x="24" y="{150 + i * 18}" font-size="13" font-weight="700" fill="#FFFFFF">{escape(line)}</text>')
    stamp = ""
    if used:
        stamp = ('<g transform="rotate(-14 160 100)" opacity="0.85"><rect x="90" y="72" width="140" height="56" rx="10" '
                 'fill="none" stroke="#C0392B" stroke-width="5"/><text x="160" y="110" text-anchor="middle" font-size="26" '
                 'font-weight="900" fill="#C0392B">使用済み</text></g>')
    label = escape(f"クーポン「{(title or '')[:40]}」{(shop or '')[:40]}", {'"': "&quot;"})
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200" width="320" height="200" role="img" aria-label="{label}">'
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{top}"/>'
        f'<stop offset="1" stop-color="{bottom}"/></linearGradient></defs>'
        # チケットの形 (左右に半円の切り欠き)
        f'<path d="M16 8 H304 a8 8 0 0 1 8 8 V84 a16 16 0 0 0 0 32 V184 a8 8 0 0 1 -8 8 H16 a8 8 0 0 1 -8 -8 V116 '
        f'a16 16 0 0 0 0 -32 V16 a8 8 0 0 1 8 -8 Z" fill="url(#{gid})"/>'
        '<g fill="#FFFFFF" opacity="0.18"><circle cx="210" cy="40" r="26"/><circle cx="60" cy="180" r="18"/>'
        '<circle cx="180" cy="170" r="10"/></g>'
        '<line x1="244" y1="20" x2="244" y2="180" stroke="#FFFFFF" stroke-width="2" stroke-dasharray="6 6" opacity="0.8"/>'
        '<g font-family="sans-serif">'
        + "".join(texts)
        + '<text x="278" y="100" text-anchor="middle" font-size="15" font-weight="900" fill="#FFFFFF" letter-spacing="3" '
        'transform="rotate(90 278 100)">COUPON</text>'
        '<text x="264" y="40" font-size="16" fill="#FFFFFF">✦</text><text x="276" y="172" font-size="12" fill="#FFFFFF">✦</text>'
        "</g>" + stamp + "</svg>"
    )

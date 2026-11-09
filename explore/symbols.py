"""印刷・掲示用「みっけシンボル」画像 (SVG) の生成。

QR コード (誤り訂正レベル H) を土台に、中央へ「み」マーク、周囲にスポット名入りの枠を付けたデザイン。
中身は推測不可能なトークンのみで、URL や個人情報は含まない。
"""

from __future__ import annotations

import segno
from django.utils.html import escape

from .models import Symbol


def render_symbol_svg(symbol: Symbol, *, color: str = "#1F2A44") -> str:
    qr = segno.make(symbol.payload, error="h", micro=False)
    matrix = qr.matrix
    n = len(matrix)
    module = 8
    quiet = 4 * module
    qr_px = n * module + quiet * 2
    pad = 24
    header = 64
    footer = 96
    width = qr_px + pad * 2
    height = qr_px + header + footer
    ox, oy = pad, header

    cells = []
    for y, row in enumerate(matrix):
        for x, v in enumerate(row):
            if v:
                cells.append(f"M{ox + quiet + x * module} {oy + quiet + y * module}h{module}v{module}h-{module}z")
    # 中央ロゴ: 面積比 約 6% (誤り訂正 H の復元能力 30% に対して十分小さい)
    logo = int(n * module * 0.24)
    cx = ox + qr_px / 2
    cy = oy + qr_px / 2
    spot_name = escape(symbol.spot.name)
    sym_name = escape(symbol.name)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="みっけシンボル: {spot_name} {sym_name}">
<rect x="2" y="2" width="{width - 4}" height="{height - 4}" rx="28" fill="#FFF6E5" stroke="#F08A24" stroke-width="4"/>
<text x="{width / 2}" y="44" text-anchor="middle" font-family="sans-serif" font-size="26" font-weight="700" fill="#F08A24">✦ みっけシンボル ✦</text>
<rect x="{ox}" y="{oy}" width="{qr_px}" height="{qr_px}" rx="16" fill="#FFFFFF"/>
<path d="{''.join(cells)}" fill="{color}"/>
<rect x="{cx - logo / 2}" y="{cy - logo / 2}" width="{logo}" height="{logo}" rx="{logo / 4}" fill="#F08A24" stroke="#FFFFFF" stroke-width="6"/>
<text x="{cx}" y="{cy + logo * 0.2}" text-anchor="middle" font-family="sans-serif" font-size="{logo * 0.56}" font-weight="700" fill="#FFFFFF">み</text>
<text x="{width / 2}" y="{oy + qr_px + 32}" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="700" fill="#1F2A44">{spot_name}</text>
<text x="{width / 2}" y="{oy + qr_px + 56}" text-anchor="middle" font-family="sans-serif" font-size="15" fill="#1F2A44">{sym_name}</text>
<text x="{width / 2}" y="{oy + qr_px + 80}" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#5A6375">アプリ「みっけ」のカメラでのぞいてね</text>
</svg>"""

"""アバター SVG の組み立て。

安全性: SVG に差し込むのは「固定の形テンプレート」と「#RRGGBB 形式に検証済みの色」だけ。
DB の文字列を SVG/HTML に直接埋め込まないため、スクリプト注入 (XSS) の余地がない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.utils.html import escape

CATEGORY_CHOICES = [
    ("hair", "髪"),
    ("top", "トップス"),
    ("bottom", "ボトムス"),
    ("shoes", "くつ"),
    ("accessory", "こもの"),
]
CATEGORY_LABELS = dict(CATEGORY_CHOICES)

# 多様性への配慮: 現実の幅広い肌の色 + 非現実的な色も選べる。性別の選択は求めない。
SKIN_TONE_CHOICES = [
    ("tone1", "とても明るい"),
    ("tone2", "明るい"),
    ("tone3", "ふつう"),
    ("tone4", "小麦色"),
    ("tone5", "褐色"),
    ("tone6", "深い褐色"),
    ("mint", "ミント(ファンタジー)"),
    ("lavender", "ラベンダー(ファンタジー)"),
]
SKIN_TONES = {
    "tone1": "#FBE3D3", "tone2": "#F3CDB0", "tone3": "#E6B48E", "tone4": "#C98F65",
    "tone5": "#9A6643", "tone6": "#5E3C27", "mint": "#BFE8D6", "lavender": "#D9CCF2",
}

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def safe_color(value: str | None, fallback: str = "#888888") -> str:
    return value if value and _HEX.match(value) else fallback


def shade(color: str, factor: float) -> str:
    """factor<1 で暗く、>1 で明るくする。"""
    c = safe_color(color)
    r, g, b = (int(c[i : i + 2], 16) for i in (1, 3, 5))
    if factor < 1:
        r, g, b = (int(v * factor) for v in (r, g, b))
    else:
        r, g, b = (int(v + (255 - v) * (factor - 1)) for v in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


# ---- 形テンプレート ----------------------------------------------------------------
# {c}=色 {d}=暗い色 {l}=明るい色。座標系は viewBox="0 0 200 270"。
# 髪は "back" (頭の後ろ) と "front" (前髪) の 2 レイヤー。

HAIR = {
    "short": {
        "label": "ショート",
        "back": "",
        "front": '<path d="M63 74 Q60 32 100 30 Q140 32 137 74 Q130 50 100 48 Q70 50 63 74 Z" fill="{c}"/>',
    },
    "bob": {
        "label": "ボブ",
        "back": '<path d="M58 72 Q56 28 100 28 Q144 28 142 72 L142 112 L124 112 L124 78 L76 78 L76 112 L58 112 Z" fill="{c}"/>',
        "front": '<path d="M63 68 Q64 34 100 32 Q136 34 137 68 Q120 54 100 56 Q80 54 63 68 Z" fill="{c}"/>',
    },
    "long": {
        "label": "ロング",
        "back": '<path d="M58 72 Q56 26 100 26 Q144 26 142 72 L146 156 L122 156 L126 82 L74 82 L78 156 L54 156 Z" fill="{c}"/>',
        "front": '<path d="M63 68 Q64 34 100 32 Q136 34 137 68 Q120 54 100 56 Q80 54 63 68 Z" fill="{c}"/>',
    },
    "spiky": {
        "label": "ツンツン",
        "back": "",
        "front": '<path d="M63 72 L58 46 L73 52 L75 28 L90 43 L100 22 L110 43 L125 28 L127 52 L142 46 L137 72 Q122 54 100 54 Q78 54 63 72 Z" fill="{c}"/>',
    },
    "bun": {
        "label": "おだんご",
        "back": '<circle cx="100" cy="26" r="15" fill="{c}"/><circle cx="100" cy="26" r="15" fill="none" stroke="{d}" stroke-width="2"/>',
        "front": '<path d="M63 72 Q60 34 100 34 Q140 34 137 72 Q128 52 100 52 Q72 52 63 72 Z" fill="{c}"/>',
    },
    "ponytail": {
        "label": "ポニーテール",
        "back": '<path d="M132 52 Q160 60 154 118 Q150 132 142 120 Q146 84 128 70 Z" fill="{c}"/>',
        "front": '<path d="M63 72 Q60 32 100 30 Q140 32 137 72 Q130 50 100 50 Q70 50 63 72 Z" fill="{c}"/>',
    },
}

TOP = {
    "tshirt": {
        "label": "Tシャツ",
        "svg": '<path d="M66 118 Q100 110 134 118 L152 140 L138 150 L134 142 L134 178 L66 178 L66 142 L62 150 L48 140 Z" fill="{c}" stroke="{d}" stroke-width="2" stroke-linejoin="round"/>'
               '<path d="M88 116 Q100 126 112 116" fill="none" stroke="{d}" stroke-width="2"/>',
    },
    "hoodie": {
        "label": "パーカー",
        "svg": '<rect x="48" y="118" width="20" height="60" rx="9" fill="{c}" stroke="{d}" stroke-width="2"/>'
               '<rect x="132" y="118" width="20" height="60" rx="9" fill="{c}" stroke="{d}" stroke-width="2"/>'
               '<rect x="64" y="114" width="72" height="66" rx="12" fill="{c}" stroke="{d}" stroke-width="2"/>'
               '<path d="M78 114 Q100 134 122 114" fill="none" stroke="{d}" stroke-width="3"/>'
               '<rect x="80" y="152" width="40" height="18" rx="5" fill="{d}" opacity="0.35"/>',
    },
    "happi": {
        "label": "法被",
        "svg": '<path d="M64 116 L136 116 L156 124 L156 162 L136 162 L136 182 L64 182 L64 162 L44 162 L44 124 Z" fill="{c}" stroke="{d}" stroke-width="2" stroke-linejoin="round"/>'
               '<path d="M92 116 L84 182 M108 116 L116 182" stroke="#FFFFFF" stroke-width="7"/>'
               '<rect x="64" y="160" width="72" height="7" fill="{d}"/>'
               '<path d="M44 150 L64 150 M136 150 L156 150" stroke="{l}" stroke-width="4"/>',
    },
    "jacket": {
        "label": "ジャケット",
        "svg": '<rect x="48" y="118" width="20" height="60" rx="8" fill="{c}" stroke="{d}" stroke-width="2"/>'
               '<rect x="132" y="118" width="20" height="60" rx="8" fill="{c}" stroke="{d}" stroke-width="2"/>'
               '<rect x="64" y="114" width="72" height="68" rx="10" fill="{c}" stroke="{d}" stroke-width="2"/>'
               '<path d="M90 114 L100 146 L110 114 Z" fill="#FFFFFF"/>'
               '<path d="M86 114 L98 150 M114 114 L102 150" stroke="{d}" stroke-width="3"/>'
               '<circle cx="100" cy="160" r="3" fill="{d}"/><circle cx="100" cy="172" r="3" fill="{d}"/>',
    },
    "border": {
        "label": "ボーダーシャツ",
        "svg": '<path d="M66 118 Q100 110 134 118 L152 140 L138 150 L134 142 L134 178 L66 178 L66 142 L62 150 L48 140 Z" fill="#FFFFFF" stroke="{d}" stroke-width="2" stroke-linejoin="round"/>'
               '<path d="M66 132 L134 132 M66 146 L134 146 M66 160 L134 160 M66 174 L134 174" stroke="{c}" stroke-width="6"/>',
    },
}

BOTTOM = {
    "pants": {
        "label": "パンツ",
        "svg": '<rect x="74" y="168" width="52" height="22" rx="4" fill="{c}"/>'
               '<rect x="74" y="178" width="24" height="64" rx="4" fill="{c}" stroke="{d}" stroke-width="2"/>'
               '<rect x="102" y="178" width="24" height="64" rx="4" fill="{c}" stroke="{d}" stroke-width="2"/>',
    },
    "shorts": {
        "label": "ショートパンツ",
        "svg": '<rect x="74" y="168" width="52" height="22" rx="4" fill="{c}"/>'
               '<rect x="74" y="178" width="24" height="28" rx="4" fill="{c}" stroke="{d}" stroke-width="2"/>'
               '<rect x="102" y="178" width="24" height="28" rx="4" fill="{c}" stroke="{d}" stroke-width="2"/>',
    },
    "skirt": {
        "label": "スカート",
        "svg": '<path d="M74 168 L126 168 L138 216 L62 216 Z" fill="{c}" stroke="{d}" stroke-width="2" stroke-linejoin="round"/>'
               '<path d="M88 172 L82 214 M100 172 L100 214 M112 172 L118 214" stroke="{d}" stroke-width="1.5" opacity="0.6"/>',
    },
    "hakama": {
        "label": "袴",
        "svg": '<path d="M72 166 L128 166 L142 244 L58 244 Z" fill="{c}" stroke="{d}" stroke-width="2" stroke-linejoin="round"/>'
               '<path d="M86 170 L78 244 M100 170 L100 244 M114 170 L122 244" stroke="{d}" stroke-width="2" opacity="0.6"/>'
               '<rect x="72" y="164" width="56" height="6" fill="{l}"/>',
    },
}

SHOES = {
    "sneakers": {
        "label": "スニーカー",
        "svg": '<rect x="70" y="238" width="30" height="14" rx="6" fill="{c}" stroke="{d}" stroke-width="2"/>'
               '<rect x="100" y="238" width="30" height="14" rx="6" fill="{c}" stroke="{d}" stroke-width="2"/>'
               '<rect x="70" y="248" width="30" height="4" fill="#FFFFFF"/><rect x="100" y="248" width="30" height="4" fill="#FFFFFF"/>',
    },
    "geta": {
        "label": "下駄",
        "svg": '<rect x="72" y="246" width="26" height="5" fill="#B07A45"/><rect x="102" y="246" width="26" height="5" fill="#B07A45"/>'
               '<rect x="75" y="251" width="5" height="6" fill="#8A5A2E"/><rect x="90" y="251" width="5" height="6" fill="#8A5A2E"/>'
               '<rect x="105" y="251" width="5" height="6" fill="#8A5A2E"/><rect x="120" y="251" width="5" height="6" fill="#8A5A2E"/>'
               '<path d="M78 246 L86 238 L94 246 M108 246 L116 238 L124 246" fill="none" stroke="{c}" stroke-width="3"/>',
    },
    "boots": {
        "label": "ブーツ",
        "svg": '<path d="M76 220 L98 220 L98 252 L68 252 Q68 242 76 240 Z" fill="{c}" stroke="{d}" stroke-width="2"/>'
               '<path d="M102 220 L124 220 L124 240 Q132 242 132 252 L102 252 Z" fill="{c}" stroke="{d}" stroke-width="2"/>',
    },
}

ACCESSORY = {
    "cap": {
        "label": "キャップ",
        "svg": '<path d="M62 58 Q64 26 100 26 Q136 26 138 58 Z" fill="{c}" stroke="{d}" stroke-width="2"/>'
               '<path d="M98 56 L152 58 Q152 66 138 66 L98 62 Z" fill="{d}"/>',
    },
    "glasses": {
        "label": "メガネ",
        "svg": '<circle cx="86" cy="76" r="10" fill="none" stroke="{c}" stroke-width="3"/>'
               '<circle cx="114" cy="76" r="10" fill="none" stroke="{c}" stroke-width="3"/>'
               '<path d="M96 76 L104 76" stroke="{c}" stroke-width="3"/>',
    },
    "flower": {
        "label": "花のかんざし",
        "svg": '<g transform="translate(128 46)">'
               '<circle cx="0" cy="-8" r="6" fill="{c}"/><circle cx="8" cy="0" r="6" fill="{c}"/>'
               '<circle cx="0" cy="8" r="6" fill="{c}"/><circle cx="-8" cy="0" r="6" fill="{c}"/>'
               '<circle cx="0" cy="0" r="4" fill="#FFD84D"/></g>',
    },
    "scarf": {
        "label": "マフラー",
        "svg": '<path d="M78 106 Q100 122 122 106 L124 118 Q100 134 76 118 Z" fill="{c}" stroke="{d}" stroke-width="2"/>'
               '<rect x="110" y="118" width="12" height="30" rx="3" fill="{c}" stroke="{d}" stroke-width="2"/>',
    },
    "foxmask": {
        "label": "きつねのお面",
        "svg": '<g transform="translate(132 44) rotate(18)">'
               '<path d="M-16 -10 L-12 -24 L-4 -12 L4 -12 L12 -24 L16 -10 Q18 10 0 16 Q-18 10 -16 -10 Z" fill="#FFFFFF" stroke="#999999" stroke-width="1.5"/>'
               '<path d="M-10 -2 L-4 0 M10 -2 L4 0" stroke="{c}" stroke-width="2.5"/>'
               '<path d="M-12 -18 L-8 -12 M12 -18 L8 -12" stroke="{c}" stroke-width="2.5"/>'
               '<circle cx="0" cy="8" r="2" fill="{c}"/></g>',
    },
}

STYLES = {"hair": HAIR, "top": TOP, "bottom": BOTTOM, "shoes": SHOES, "accessory": ACCESSORY}


def style_choices(category: str) -> list[tuple[str, str]]:
    return [(k, v["label"]) for k, v in STYLES[category].items()]


@dataclass(frozen=True)
class Part:
    """描画に必要な最小情報 (Item モデルに依存しないので単体テストしやすい)。"""

    category: str
    style: str
    color: str
    name: str = ""


def _fmt(template: str, color: str) -> str:
    c = safe_color(color)
    return template.format(c=c, d=shade(c, 0.7), l=shade(c, 1.45))


def _base_body(skin: str) -> str:
    s, sd = skin, shade(skin, 0.8)
    return (
        # 腕・手・首・脚 (服の下に描く)
        f'<rect x="52" y="120" width="14" height="56" rx="7" fill="{s}"/>'
        f'<rect x="134" y="120" width="14" height="56" rx="7" fill="{s}"/>'
        f'<circle cx="59" cy="180" r="7" fill="{s}"/><circle cx="141" cy="180" r="7" fill="{s}"/>'
        f'<rect x="78" y="170" width="18" height="72" rx="6" fill="{s}"/>'
        f'<rect x="104" y="170" width="18" height="72" rx="6" fill="{s}"/>'
        f'<rect x="92" y="102" width="16" height="16" fill="{sd}"/>'
        # 肌着 (服を着ていないときの既定)
        '<rect x="66" y="116" width="68" height="62" rx="10" fill="#F4F1EC" stroke="#CFC8BD" stroke-width="2"/>'
        '<rect x="74" y="168" width="52" height="24" rx="5" fill="#B9B4AC"/>'
    )


def _head(skin: str) -> str:
    s = skin
    return (
        f'<circle cx="100" cy="72" r="36" fill="{s}"/>'
        f'<circle cx="64" cy="76" r="6" fill="{s}"/><circle cx="136" cy="76" r="6" fill="{s}"/>'
        '<circle cx="88" cy="78" r="3.6" fill="#2B2B2B"/><circle cx="112" cy="78" r="3.6" fill="#2B2B2B"/>'
        '<circle cx="89.2" cy="76.8" r="1.1" fill="#FFFFFF"/><circle cx="113.2" cy="76.8" r="1.1" fill="#FFFFFF"/>'
        '<path d="M92 91 Q100 98 108 91" fill="none" stroke="#7A3B2E" stroke-width="2.4" stroke-linecap="round"/>'
        '<circle cx="80" cy="89" r="5" fill="#F28B8B" opacity="0.45"/><circle cx="120" cy="89" r="5" fill="#F28B8B" opacity="0.45"/>'
    )


def render_svg(skin_tone: str, parts: dict[str, Part | None], *, label: str = "アバター",
               size: int | None = None, background: bool = True) -> str:
    """アバター全体の SVG 文字列を返す。"""
    skin = SKIN_TONES.get(skin_tone, SKIN_TONES["tone3"])

    def layer(category: str, key: str = "svg") -> str:
        p = parts.get(category)
        if p is None or p.style not in STYLES[category]:
            return ""
        return _fmt(STYLES[category][p.style].get(key, ""), p.color)

    described = [f"{CATEGORY_LABELS[c]}: {p.name}" for c, p in parts.items() if p is not None and p.name]
    aria = escape(label + (" (" + "、".join(described) + ")" if described else ""))
    dims = f' width="{int(size)}" height="{int(size * 270 / 200)}"' if size else ""
    bg = '<rect x="0" y="0" width="200" height="270" rx="18" fill="#FFF6E5"/><ellipse cx="100" cy="256" rx="58" ry="8" fill="#000000" opacity="0.08"/>' if background else ""
    body = "".join([
        bg,
        layer("hair", "back"),
        _base_body(skin),
        layer("shoes"),
        layer("bottom"),
        layer("top"),
        _head(skin),
        layer("hair", "front"),
        layer("accessory"),
    ])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 270"{dims} role="img" aria-label="{aria}">'
        f"<title>{aria}</title>{body}</svg>"
    )

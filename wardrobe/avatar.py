"""アバター SVG の組み立て (ちびキャラ風)。

デザイン: 頭身の約 1/3 が頭、きらきらした大きな瞳、前髪・後ろ髪・横髪を重ねた髪型。
体のタイプは「女の子」「男の子」の 2 種類で、だれでも自由に選べる (登録者の性別とは無関係)。

安全性: SVG に差し込むのは「固定の形テンプレート」と「#RRGGBB 形式に検証済みの色」だけ。
DB の文字列を SVG/HTML に直接埋め込まないため、スクリプト注入 (XSS) の余地がない。
座標系は viewBox="0 0 200 300"。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.utils.html import escape

CATEGORY_CHOICES = [
    ("face", "顔"),
    ("hair", "髪"),
    ("top", "トップス"),
    ("bottom", "ボトムス"),
    ("shoes", "くつ"),
    ("accessory", "こもの"),
    ("effect", "エフェクト"),
    ("background", "背景"),
]
CATEGORY_LABELS = dict(CATEGORY_CHOICES)

BODY_TYPE_CHOICES = [("girl", "女の子"), ("boy", "男の子")]
ITEM_BODY_CHOICES = [("girl", "女の子用"), ("boy", "男の子用"), ("any", "共通")]

# 多様性への配慮: 現実の幅広い肌の色 + 非現実的な色も選べる
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
    "tone1": "#FCE8DA", "tone2": "#F7D7C0", "tone3": "#EDBF9C", "tone4": "#D29C74",
    "tone5": "#A26C48", "tone6": "#674330", "mint": "#C6EBDB", "lavender": "#DED2F4",
}
EYE_COLOR_CHOICES = [
    ("brown", "ブラウン"), ("pink", "ピンク"), ("violet", "バイオレット"),
    ("blue", "ブルー"), ("green", "グリーン"), ("amber", "アンバー"),
]
EYE_COLORS = {
    "brown": "#8A5232", "pink": "#D2508E", "violet": "#8656D0",
    "blue": "#3A74D0", "green": "#2F9A6A", "amber": "#C98A1E",
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
        r, g, b = (min(255, int(v + (255 - v) * (factor - 1))) for v in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


# =====================================================================================
# 形テンプレート  {c}=色 {d}=暗い色 {l}=明るい色 {w}=白に近い色
# =====================================================================================

_SHINE = '<path d="M72 54 Q86 46 100 46" fill="none" stroke="{l}" stroke-width="3.5" stroke-linecap="round" opacity="0.8"/>'
_CAP = '<path d="M55 94 Q53 38 100 36 Q147 38 145 94 Z" fill="{c}"/>'

HAIR = {
    # ---------------- 女の子向けに作った髪型 ----------------
    "bob": {
        "label": "ボブ",
        "back": '<path d="M53 92 Q51 36 100 34 Q149 36 147 92 L149 136 Q146 145 133 141 L131 112 L69 112 L67 141 Q54 145 51 136 Z" fill="{c}"/>',
        "front": '<path d="M56 98 Q55 40 100 38 Q145 40 144 98 Q140 78 131 70 Q128 85 117 87 Q119 74 113 66 Q107 81 97 84 Q99 71 93 63 Q85 80 73 84 Q75 73 69 70 Q60 80 56 98 Z" fill="{c}"/>'
                 '<path d="M56 92 Q53 126 64 142 Q71 128 68 100 Z" fill="{c}"/><path d="M144 92 Q147 126 136 142 Q129 128 132 100 Z" fill="{c}"/>'
                 '<path d="M93 63 Q90 74 86 80 M113 66 Q114 76 117 84" fill="none" stroke="{d}" stroke-width="1.2" opacity="0.6"/>' + _SHINE,
    },
    "long": {
        "label": "ロングストレート",
        "back": '<path d="M53 92 Q51 34 100 32 Q149 34 147 92 L153 236 Q141 246 128 236 L126 134 L74 134 L72 236 Q59 246 47 236 Z" fill="{c}"/>'
                '<path d="M60 150 L58 230 M140 150 L142 230" stroke="{d}" stroke-width="1.2" opacity="0.5"/>',
        "front": '<path d="M56 100 Q57 40 100 38 Q143 40 144 100 Q136 76 120 66 Q112 75 102 71 L100 58 L98 71 Q88 75 80 66 Q64 76 56 100 Z" fill="{c}"/>'
                 '<path d="M56 94 Q51 142 61 178 Q70 152 68 106 Z" fill="{c}"/><path d="M144 94 Q149 142 139 178 Q130 152 132 106 Z" fill="{c}"/>' + _SHINE,
    },
    "twintail": {
        "label": "ツインテール",
        "back": _CAP + '<path d="M64 60 Q26 68 28 130 Q30 182 20 230 Q46 220 50 180 Q56 130 62 102 Q66 84 74 70 Z" fill="{c}"/>'
                '<path d="M136 60 Q174 68 172 130 Q170 182 180 230 Q154 220 150 180 Q144 130 138 102 Q134 84 126 70 Z" fill="{c}"/>'
                '<path d="M40 100 Q36 150 30 210 M160 100 Q164 150 170 210" fill="none" stroke="{l}" stroke-width="2" opacity="0.7"/>',
        "front": '<path d="M56 98 Q55 40 100 38 Q145 40 144 98 Q141 90 137 86 L135 79 Q118 84 100 81 Q82 84 65 79 L63 86 Q59 90 56 98 Z" fill="{c}"/>'
                 '<path d="M57 92 Q55 118 61 132 Q67 118 66 96 Z" fill="{c}"/><path d="M143 92 Q145 118 139 132 Q133 118 134 96 Z" fill="{c}"/>' + _SHINE,
    },
    "ponytail": {
        "label": "ポニーテール",
        "back": _CAP + '<path d="M118 44 Q170 42 168 110 Q166 162 180 200 Q146 190 142 142 Q140 98 124 70 Z" fill="{c}"/>'
                '<path d="M150 70 Q156 130 168 186" fill="none" stroke="{l}" stroke-width="2" opacity="0.7"/>',
        "front": '<path d="M56 98 Q55 40 100 38 Q145 40 144 98 Q138 74 120 62 Q104 77 80 81 Q65 83 56 98 Z" fill="{c}"/>'
                 '<path d="M57 92 Q55 120 63 134 Q68 118 66 98 Z" fill="{c}"/><circle cx="124" cy="48" r="5" fill="{d}"/>' + _SHINE,
    },
    "bun": {
        "label": "おだんご",
        "back": _CAP + '<circle cx="100" cy="30" r="18" fill="{c}"/><path d="M88 28 Q100 18 112 30 Q104 40 92 34" fill="none" stroke="{d}" stroke-width="1.5" opacity="0.6"/>',
        "front": '<path d="M56 98 Q55 40 100 38 Q145 40 144 98 Q140 82 132 76 Q124 86 114 84 Q110 74 100 72 Q90 74 86 84 Q76 86 68 76 Q60 82 56 98 Z" fill="{c}"/>'
                 '<path d="M57 92 Q55 116 61 128 Q67 116 66 96 Z" fill="{c}"/><path d="M143 92 Q145 116 139 128 Q133 116 134 96 Z" fill="{c}"/>' + _SHINE,
    },
    "wavy": {
        "label": "ゆるふわロング",
        "back": '<path d="M53 92 Q51 34 100 32 Q149 34 147 92 Q160 120 149 150 Q162 182 147 212 Q152 234 132 232 Q139 204 128 182 Q137 152 126 132 L74 132 Q63 152 72 182 Q61 204 68 232 Q48 234 53 212 Q38 182 51 150 Q40 120 53 92 Z" fill="{c}"/>'
                '<path d="M56 160 Q48 186 58 208 M144 160 Q152 186 142 208" fill="none" stroke="{l}" stroke-width="2" opacity="0.7"/>',
        "front": '<path d="M56 100 Q55 40 100 38 Q145 40 144 100 Q140 80 128 72 Q124 82 112 80 Q108 70 98 70 Q90 72 86 82 Q74 84 70 74 Q60 82 56 100 Z" fill="{c}"/>'
                 '<path d="M56 94 Q48 130 60 160 Q54 172 62 182 Q70 160 68 104 Z" fill="{c}"/><path d="M144 94 Q152 130 140 160 Q146 172 138 182 Q130 160 132 104 Z" fill="{c}"/>' + _SHINE,
    },
    # ---------------- 男の子向けに作った髪型 ----------------
    "short": {
        "label": "ショート",
        "back": '<path d="M55 98 Q53 40 100 38 Q147 40 145 98 L143 118 L57 118 Z" fill="{c}"/>',
        "front": '<path d="M56 96 Q54 42 100 40 Q146 42 144 96 Q139 83 131 79 L127 89 L119 77 L111 87 L103 75 L95 87 L87 77 L79 89 L73 79 Q62 85 56 96 Z" fill="{c}"/>'
                 '<path d="M57 92 L59 112 L66 104 Z M143 92 L141 112 L134 104 Z" fill="{c}"/>' + _SHINE,
    },
    "spiky": {
        "label": "ツンツン",
        "back": '<path d="M55 98 Q53 40 100 38 Q147 40 145 98 L143 116 L57 116 Z" fill="{c}"/>',
        "front": '<path d="M55 96 L48 64 L63 68 L60 40 L79 52 L85 26 L100 45 L115 26 L121 52 L140 40 L137 68 L152 64 L145 96 Q139 83 131 81 L125 91 L117 79 L109 89 L101 77 L93 89 L85 79 L77 91 L71 81 Q62 85 55 96 Z" fill="{c}"/>'
                 '<path d="M85 26 L90 48 M115 26 L110 48" stroke="{l}" stroke-width="2" opacity="0.7"/>',
    },
    "mash": {
        "label": "マッシュ",
        "back": '<path d="M54 100 Q52 38 100 36 Q148 38 146 100 L144 120 L56 120 Z" fill="{c}"/>',
        "front": '<path d="M54 98 Q53 38 100 36 Q147 38 146 98 Q143 92 138 89 Q130 92 122 88 Q112 92 100 87 Q88 92 78 88 Q70 92 62 89 Q57 92 54 98 Z" fill="{c}"/>'
                 '<path d="M78 60 Q76 76 78 88 M100 56 L100 86 M122 60 Q124 76 122 88" fill="none" stroke="{d}" stroke-width="1.2" opacity="0.5"/>' + _SHINE,
    },
    "sidepart": {
        "label": "七三わけ",
        "back": '<path d="M55 98 Q53 40 100 38 Q147 40 145 98 L143 118 L57 118 Z" fill="{c}"/>',
        "front": '<path d="M56 98 Q54 40 100 38 Q146 40 144 98 Q140 80 128 70 Q110 60 90 72 Q76 82 64 82 Q58 88 56 98 Z" fill="{c}"/>'
                 '<path d="M118 44 Q110 58 112 66" fill="none" stroke="{d}" stroke-width="1.5" opacity="0.6"/>'
                 '<path d="M57 92 L59 112 L66 104 Z M143 92 L141 112 L134 104 Z" fill="{c}"/>' + _SHINE,
    },
    "wolf": {
        "label": "ウルフ",
        "back": '<path d="M55 98 Q53 40 100 38 Q147 40 145 98 L149 134 L139 126 L141 148 L127 134 L73 134 L59 148 L61 126 L51 134 Z" fill="{c}"/>',
        "front": '<path d="M55 98 Q54 40 100 38 Q146 40 145 98 Q140 84 133 80 L130 92 L122 78 L116 90 L108 76 L100 90 L92 76 L84 90 L78 78 L70 92 L67 80 Q60 86 55 98 Z" fill="{c}"/>'
                 '<path d="M56 94 L55 124 L64 110 Z M144 94 L145 124 L136 110 Z" fill="{c}"/>' + _SHINE,
    },
    "curly": {
        "label": "くせっ毛",
        "back": '<path d="M54 100 Q46 76 58 62 Q54 42 74 40 Q82 28 98 32 Q112 24 124 36 Q144 36 144 56 Q156 70 146 100 L144 118 L56 118 Z" fill="{c}"/>',
        "front": '<path d="M55 96 Q49 74 60 62 Q58 46 74 44 Q81 32 97 36 Q110 28 121 38 Q139 38 140 54 Q152 64 145 96 Q141 85 133 86 Q128 94 118 89 Q112 97 102 91 Q94 98 86 90 Q76 96 70 87 Q61 88 55 96 Z" fill="{c}"/>'
                 '<path d="M72 54 Q78 48 84 54 M96 46 Q102 40 108 46 M120 52 Q126 46 132 54" fill="none" stroke="{l}" stroke-width="2" opacity="0.7"/>',
    },
}

# ---- トップス ----
_TORSO = '<path d="M78 146 Q100 138 122 146 L125 202 L75 202 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
_SLEEVE_S = ('<path d="M80 145 L71 149 L66 174 L78 177 L81 160 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
             '<path d="M120 145 L129 149 L134 174 L122 177 L119 160 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>')
_SLEEVE_L = ('<path d="M80 145 L71 149 L63 198 L76 201 L81 162 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
             '<path d="M120 145 L129 149 L137 198 L124 201 L119 162 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>')
_PUFF = ('<ellipse cx="74" cy="154" rx="10" ry="9" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
         '<ellipse cx="126" cy="154" rx="10" ry="9" fill="{c}" stroke="{d}" stroke-width="1.2"/>')

TOP = {
    "tshirt": {"label": "Tシャツ", "svg": _SLEEVE_S + _TORSO + '<path d="M91 143 Q100 151 109 143" fill="none" stroke="{d}" stroke-width="1.5"/>'},
    "hoodie": {
        "label": "パーカー",
        "svg": '<path d="M82 144 Q100 158 118 144 Q118 132 100 130 Q82 132 82 144 Z" fill="{d}"/>' + _SLEEVE_L + _TORSO
               + '<path d="M86 180 L114 180 L117 198 L83 198 Z" fill="{d}" opacity="0.35"/>'
               + '<path d="M95 148 L94 166 M105 148 L106 166" stroke="#FFFFFF" stroke-width="1.5"/>',
    },
    "happi": {
        "label": "法被",
        "svg": '<path d="M80 145 L60 150 L58 186 L77 186 L81 160 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
               '<path d="M120 145 L140 150 L142 186 L123 186 L119 160 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>' + _TORSO
               + '<path d="M93 141 L86 202 M107 141 L114 202" stroke="#FFFFFF" stroke-width="6"/>'
               + '<rect x="75" y="186" width="50" height="6" fill="{d}"/><path d="M58 178 L77 178 M142 178 L123 178" stroke="{l}" stroke-width="3"/>',
    },
    "jacket": {
        "label": "ジャケット",
        "svg": _SLEEVE_L + _TORSO + '<path d="M92 142 L100 170 L108 142 Z" fill="#FFFFFF"/>'
               + '<path d="M88 142 L98 174 M112 142 L102 174" stroke="{d}" stroke-width="2.5"/>'
               + '<circle cx="100" cy="182" r="2.4" fill="{d}"/><circle cx="100" cy="192" r="2.4" fill="{d}"/>',
    },
    "border": {
        "label": "ボーダーシャツ",
        "svg": _SLEEVE_S.replace("{c}", "#FFFFFF") + _TORSO.replace("{c}", "#FFFFFF")
               + ''.join(f'<rect x="77" y="{y}" width="46" height="4" fill="{{c}}"/>' for y in (154, 164, 174, 184, 194))
               + '<path d="M68 162 L79 164 M67 170 L78 172 M132 162 L121 164 M133 170 L122 172" stroke="{c}" stroke-width="3"/>',
    },
    "blouse": {
        "label": "リボンブラウス",
        "svg": _PUFF + _TORSO + '<ellipse cx="93" cy="145" rx="8" ry="5" fill="#FFFFFF"/><ellipse cx="107" cy="145" rx="8" ry="5" fill="#FFFFFF"/>'
               + '<path d="M100 150 L89 144 L89 156 Z M100 150 L111 144 L111 156 Z" fill="{d}"/><circle cx="100" cy="150" r="3" fill="{d}"/>'
               + '<path d="M100 153 L96 166 M100 153 L104 166" stroke="{d}" stroke-width="2.5"/>',
    },
    "idol": {
        "label": "アイドル衣装",
        "svg": _PUFF + _TORSO + '<path d="M95 146 L105 146 L106 202 L94 202 Z" fill="#FFFFFF"/>'
               + '<circle cx="100" cy="166" r="2.3" fill="#F2C440"/><circle cx="100" cy="178" r="2.3" fill="#F2C440"/><circle cx="100" cy="190" r="2.3" fill="#F2C440"/>'
               + '<path d="M100 148 L86 141 L87 157 Z M100 148 L114 141 L113 157 Z" fill="{d}"/><circle cx="100" cy="148" r="3.5" fill="{l}"/>'
               + '<path d="M114 160 L116 164 L120 164 L117 167 L118 171 L114 169 L110 171 L111 167 L108 164 L112 164 Z" fill="#F2C440"/>'
               + '<rect x="75" y="198" width="50" height="4" fill="#FFFFFF"/>'
               + '<path d="M64 154 L84 154 M116 154 L136 154" stroke="#FFFFFF" stroke-width="2"/>',
    },
    "sailor": {
        "label": "セーラー服",
        "svg": _SLEEVE_L.replace("{c}", "#FFFFFF") + _TORSO.replace("{c}", "#FFFFFF")
               + '<path d="M79 146 L92 141 L100 164 L108 141 L121 146 L119 160 L100 176 L81 160 Z" fill="{c}"/>'
               + '<path d="M84 150 L100 170 L116 150" fill="none" stroke="#FFFFFF" stroke-width="1.5"/>'
               + '<path d="M100 168 L90 162 L91 174 Z M100 168 L110 162 L109 174 Z" fill="#D6334A"/>'
               + '<path d="M63 192 L76 195 M137 192 L124 195" stroke="{c}" stroke-width="5"/>',
    },
    "kimono": {
        "label": "着物風トップス",
        "svg": '<path d="M80 145 L62 150 L60 198 L78 198 L81 160 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
               '<path d="M120 145 L138 150 L140 198 L122 198 L119 160 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>' + _TORSO
               + '<path d="M92 141 L110 178 M108 141 L100 157" stroke="#FFFFFF" stroke-width="4"/>'
               + '<rect x="75" y="182" width="50" height="14" fill="{d}"/><path d="M75 189 L125 189" stroke="{l}" stroke-width="2"/>'
               + ''.join(f'<circle cx="{x}" cy="{y}" r="3" fill="{{l}}"/>' for x, y in ((84, 166), (116, 160), (68, 176), (132, 184), (70, 158)))
    },
    "shirt_tie": {
        "label": "シャツとネクタイ",
        "svg": _SLEEVE_L + _TORSO + '<path d="M90 141 L100 150 L93 156 Z M110 141 L100 150 L107 156 Z" fill="{l}" stroke="{d}" stroke-width="1"/>'
               + '<path d="M97.5 150 L102.5 150 L104.5 180 L100 187 L95.5 180 Z" fill="#2B3A67"/>'
               + '<path d="M66 192 L76 194 M134 192 L124 194" stroke="{l}" stroke-width="4"/>',
    },
    "sweater": {
        "label": "ニット",
        "svg": _SLEEVE_L + _TORSO + '<path d="M90 142 Q100 150 110 142" fill="none" stroke="{l}" stroke-width="4"/>'
               + '<rect x="75" y="194" width="50" height="8" fill="{d}"/>'
               + '<path d="M92 156 Q96 166 92 176 Q96 186 92 194 M108 156 Q104 166 108 176 Q104 186 108 194" fill="none" stroke="{l}" stroke-width="2"/>'
               + '<path d="M63 194 L76 197 M137 194 L124 197" stroke="{d}" stroke-width="5"/>',
    },
    "parka": {
        "label": "ブルゾン",
        "svg": _SLEEVE_L + _TORSO + '<path d="M100 141 L100 202" stroke="{d}" stroke-width="2"/>'
               + '<path d="M86 141 Q100 136 114 141 L112 148 Q100 144 88 148 Z" fill="{l}"/>'
               + '<rect x="75" y="194" width="50" height="8" fill="{l}"/><rect x="83" y="172" width="10" height="8" rx="2" fill="{d}" opacity="0.5"/>'
               + '<rect x="107" y="172" width="10" height="8" rx="2" fill="{d}" opacity="0.5"/>',
    },
}

# ---- ボトムス ----
BOTTOM = {
    "pants": {"label": "パンツ", "svg": '<path d="M76 196 L124 196 L121 268 L103 268 L100 214 L97 268 L79 268 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
              '<path d="M100 200 L100 214" stroke="{d}" stroke-width="1"/>'},
    "jeans": {"label": "ジーンズ", "svg": '<path d="M76 196 L124 196 L121 266 L103 266 L100 214 L97 266 L79 266 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
              '<rect x="78" y="260" width="20" height="6" fill="{l}"/><rect x="102" y="260" width="20" height="6" fill="{l}"/>'
              '<path d="M82 200 Q86 208 92 204 M118 200 Q114 208 108 204" fill="none" stroke="#E2B04A" stroke-width="1"/>'},
    "shorts": {"label": "ショートパンツ", "svg": '<path d="M76 196 L124 196 L124 230 L102 230 L100 214 L98 230 L76 230 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'},
    "cropped": {"label": "クロップドパンツ", "svg": '<path d="M76 196 L124 196 L122 248 L103 248 L100 214 L97 248 L78 248 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
                '<rect x="78" y="242" width="19" height="6" fill="{l}"/><rect x="103" y="242" width="19" height="6" fill="{l}"/>'},
    "hakama": {"label": "袴", "svg": '<path d="M74 194 L126 194 L142 268 L58 268 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
               '<path d="M88 198 L80 268 M100 198 L100 268 M112 198 L120 268" stroke="{d}" stroke-width="1.5" opacity="0.6"/>'
               '<rect x="74" y="192" width="52" height="6" fill="{l}"/>'},
    "skirt": {"label": "フレアスカート", "svg": '<path d="M78 196 L122 196 L142 244 Q100 254 58 244 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
              + ''.join(f'<path d="M{x} 236 L{x + 4} 240 L{x} 244 L{x - 4} 240 Z" fill="{{l}}"/>' for x in range(66, 138, 9))},
    "pleated": {"label": "チェックプリーツ", "svg": '<path d="M78 196 L122 196 L140 240 L60 240 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
                '<path d="M88 196 L78 240 M100 196 L100 240 M112 196 L122 240" stroke="{d}" stroke-width="1.5"/>'
                '<path d="M70 214 L130 214 M64 228 L136 228" stroke="{l}" stroke-width="2.5" opacity="0.8"/>'
                '<path d="M94 196 L89 240 M106 196 L111 240" stroke="{l}" stroke-width="1.5" opacity="0.7"/>'},
    "frill": {"label": "フリルスカート", "svg": '<path d="M78 196 L122 196 L138 232 L62 232 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
              + ''.join(f'<circle cx="{x}" cy="234" r="5" fill="#FFFFFF" stroke="{{l}}" stroke-width="0.8"/>' for x in range(62, 140, 8))
              + '<rect x="77" y="194" width="46" height="5" fill="{d}"/>'},
    "jumper": {"label": "ジャンパースカート", "svg": '<path d="M80 150 L86 150 L88 196 L112 196 L114 150 L120 150 L122 196 L140 246 Q100 256 60 246 L78 196 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
               '<circle cx="86" cy="154" r="2" fill="{l}"/><circle cx="114" cy="154" r="2" fill="{l}"/>'},
}

# ---- くつ (足の位置: 左 x≈90 / 右 x≈110, y≈272〜284) ----
SHOES = {
    "sneakers": {"label": "スニーカー", "svg": '<rect x="81" y="268" width="17" height="13" rx="6" fill="{c}" stroke="{d}" stroke-width="1"/>'
                 '<rect x="102" y="268" width="17" height="13" rx="6" fill="{c}" stroke="{d}" stroke-width="1"/>'
                 '<rect x="81" y="278" width="17" height="4" rx="2" fill="#FFFFFF"/><rect x="102" y="278" width="17" height="4" rx="2" fill="#FFFFFF"/>'},
    "loafers": {"label": "ローファー", "svg": '<path d="M82 272 Q82 266 90 266 Q98 266 98 274 L98 281 L82 281 Z" fill="{c}"/>'
                '<path d="M102 274 Q102 266 110 266 Q118 266 118 272 L118 281 L102 281 Z" fill="{c}"/>'
                '<circle cx="90" cy="272" r="1.8" fill="#F2C440"/><circle cx="110" cy="272" r="1.8" fill="#F2C440"/>'},
    "boots": {"label": "ブーツ", "svg": '<path d="M85 242 L98 242 L98 282 L80 282 Q80 272 86 270 Z" fill="{c}" stroke="{d}" stroke-width="1"/>'
              '<path d="M102 242 L115 242 L114 270 Q120 272 120 282 L102 282 Z" fill="{c}" stroke="{d}" stroke-width="1"/>'
              '<rect x="85" y="242" width="13" height="4" fill="{l}"/><rect x="102" y="242" width="13" height="4" fill="{l}"/>'},
    "sandals": {"label": "サンダル", "svg": '<ellipse cx="90" cy="281" rx="8.5" ry="2.8" fill="{d}"/><ellipse cx="110" cy="281" rx="8.5" ry="2.8" fill="{d}"/>'
                '<path d="M84 276 Q90 272 96 276 M104 276 Q110 272 116 276" fill="none" stroke="{c}" stroke-width="2.5"/>'
                '<path d="M86 266 Q90 270 96 266 M104 266 Q110 270 114 266" fill="none" stroke="{c}" stroke-width="2"/>'
                '<circle cx="96" cy="266" r="1.8" fill="#F2C440"/><circle cx="104" cy="266" r="1.8" fill="#F2C440"/>'},
    "geta": {"label": "下駄", "svg": '<rect x="82" y="279" width="17" height="4" fill="#B07A45"/><rect x="101" y="279" width="17" height="4" fill="#B07A45"/>'
             '<rect x="84" y="283" width="4" height="4" fill="#8A5A2E"/><rect x="93" y="283" width="4" height="4" fill="#8A5A2E"/>'
             '<rect x="103" y="283" width="4" height="4" fill="#8A5A2E"/><rect x="112" y="283" width="4" height="4" fill="#8A5A2E"/>'
             '<path d="M84 279 L90 271 L97 279 M103 279 L110 271 L116 279" fill="none" stroke="{c}" stroke-width="2.5"/>'},
    "highsocks": {"label": "ハイソックス", "svg": '<rect x="86" y="230" width="12" height="44" rx="5" fill="{c}"/><rect x="102" y="230" width="12" height="44" rx="5" fill="{c}"/>'
                  '<rect x="86" y="232" width="12" height="3" fill="#FFFFFF"/><rect x="102" y="232" width="12" height="3" fill="#FFFFFF"/>'
                  '<path d="M82 274 Q82 268 90 268 Q98 268 98 275 L98 282 L82 282 Z" fill="#7A4A2A"/>'
                  '<path d="M102 275 Q102 268 110 268 Q118 268 118 274 L118 282 L102 282 Z" fill="#7A4A2A"/>'},
}

# ---- こもの (髪の上に描く) ----
ACCESSORY = {
    "cap": {"label": "キャップ", "svg": '<path d="M56 68 Q58 32 100 30 Q142 32 144 68 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
            '<path d="M98 64 L158 66 Q158 75 142 75 L98 71 Z" fill="{d}"/><circle cx="100" cy="31" r="3" fill="{d}"/>'},
    "beret": {"label": "ベレー帽", "svg": '<path d="M54 70 Q54 34 102 30 Q148 32 150 58 Q126 50 104 56 Q76 60 54 70 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
              '<path d="M104 30 L106 22" stroke="{d}" stroke-width="3" stroke-linecap="round"/>'},
    "glasses": {"label": "メガネ", "svg": '<rect x="68" y="92" width="28" height="24" rx="10" fill="none" stroke="{c}" stroke-width="2.4"/>'
                '<rect x="104" y="92" width="28" height="24" rx="10" fill="none" stroke="{c}" stroke-width="2.4"/><path d="M96 102 L104 102" stroke="{c}" stroke-width="2.4"/>'},
    "headphones": {"label": "ヘッドホン", "svg": '<path d="M56 92 Q54 30 100 30 Q146 30 144 92" fill="none" stroke="{c}" stroke-width="5"/>'
                   '<rect x="48" y="84" width="13" height="24" rx="6" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
                   '<rect x="139" y="84" width="13" height="24" rx="6" fill="{c}" stroke="{d}" stroke-width="1.2"/>'},
    "ribbon": {"label": "大きなリボン", "svg": '<g transform="translate(128 46) rotate(15)"><path d="M0 0 L-20 -12 L-18 12 Z M0 0 L20 -12 L18 12 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
               '<circle cx="0" cy="0" r="5" fill="{d}"/><path d="M-3 4 L-8 18 M3 4 L8 18" stroke="{c}" stroke-width="3"/></g>'},
    "flower": {"label": "花かざり", "svg": '<g transform="translate(130 48)">'
               + ''.join(f'<circle cx="{x}" cy="{y}" r="6.5" fill="{{c}}" stroke="{{d}}" stroke-width="0.8"/>' for x, y in ((0, -8), (8, -2), (5, 7), (-5, 7), (-8, -2)))
               + '<circle cx="0" cy="0" r="4" fill="#FFE07A"/><path d="M-12 8 L-18 14 M10 10 L16 16" stroke="#6AAE5A" stroke-width="3"/></g>'},
    "star": {"label": "星のヘアピン", "svg": '<g transform="translate(124 60)"><path d="M0 -9 L2.6 -3 L9 -2.8 L4 1.4 L5.6 8 L0 4.4 L-5.6 8 L-4 1.4 L-9 -2.8 L-2.6 -3 Z" fill="{c}" stroke="{d}" stroke-width="1"/></g>'
             '<g transform="translate(138 74) scale(0.6)"><path d="M0 -9 L2.6 -3 L9 -2.8 L4 1.4 L5.6 8 L0 4.4 L-5.6 8 L-4 1.4 L-9 -2.8 L-2.6 -3 Z" fill="{l}"/></g>'},
    "scarf": {"label": "マフラー", "svg": '<path d="M80 136 Q100 152 120 136 L122 150 Q100 166 78 150 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
              '<rect x="108" y="150" width="12" height="30" rx="3" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
              '<path d="M110 176 L110 182 M114 176 L114 182 M118 176 L118 182" stroke="{d}" stroke-width="1.5"/>'},
    "foxmask": {"label": "きつねのお面", "svg": '<g transform="translate(136 50) rotate(18)">'
                '<path d="M-16 -10 L-12 -24 L-4 -12 L4 -12 L12 -24 L16 -10 Q18 10 0 16 Q-18 10 -16 -10 Z" fill="#FFFFFF" stroke="#999999" stroke-width="1.5"/>'
                '<path d="M-10 -2 L-4 0 M10 -2 L4 0" stroke="{c}" stroke-width="2.5"/><path d="M-12 -18 L-8 -12 M12 -18 L8 -12" stroke="{c}" stroke-width="2.5"/>'
                '<circle cx="0" cy="8" r="2" fill="{c}"/></g>'},
    "crown": {"label": "ティアラ", "svg": '<path d="M76 50 L82 36 L90 46 L100 30 L110 46 L118 36 L124 50 Q100 44 76 50 Z" fill="{c}" stroke="{d}" stroke-width="1.2"/>'
              '<circle cx="100" cy="40" r="3" fill="#E8508A"/><circle cx="84" cy="44" r="2" fill="#6AC0E8"/><circle cx="116" cy="44" r="2" fill="#6AC0E8"/>'},
}

# ---- 顔 (目・眉・口・ほお紅のセット)。色はほお紅・口もとの差し色に使う ----
# eyes: open / happy(^^) / wink / sleepy   scale: 目の大きさ   tilt: 目尻の上下 (+ でたれ目)
FACE = {
    "standard": {"label": "ふつう", "eyes": "open", "scale": 1.0, "tilt": 0, "mouth": "smile", "brow": "normal", "blush": 0.4},
    "smile": {"label": "にっこり", "eyes": "open", "scale": 1.0, "tilt": 0, "mouth": "open", "brow": "up", "blush": 0.45},
    "happy": {"label": "うれしい", "eyes": "happy", "scale": 1.0, "tilt": 0, "mouth": "open", "brow": "up", "blush": 0.55},
    "wink": {"label": "ウインク", "eyes": "wink", "scale": 1.0, "tilt": 0, "mouth": "grin", "brow": "normal", "blush": 0.45},
    "tare": {"label": "たれ目", "eyes": "open", "scale": 1.0, "tilt": 2.5, "mouth": "smile", "brow": "tare", "blush": 0.45},
    "tsuri": {"label": "つり目", "eyes": "open", "scale": 0.95, "tilt": -2.5, "mouth": "smile", "brow": "tsuri", "blush": 0.3},
    "round": {"label": "まんまる", "eyes": "open", "scale": 1.12, "tilt": 0, "mouth": "o", "brow": "up", "blush": 0.5},
    "sleepy": {"label": "ねむそう", "eyes": "sleepy", "scale": 1.0, "tilt": 1, "mouth": "smile", "brow": "tare", "blush": 0.35},
    "cat": {"label": "ねこぐち", "eyes": "open", "scale": 1.0, "tilt": -1, "mouth": "cat", "brow": "normal", "blush": 0.45},
    "cool": {"label": "クール", "eyes": "open", "scale": 0.9, "tilt": -1.5, "mouth": "flat", "brow": "tsuri", "blush": 0.15},
    "sparkle": {"label": "キラキラ", "eyes": "open", "scale": 1.06, "tilt": 0, "mouth": "open", "brow": "up", "blush": 0.5, "star": True},
    "shy": {"label": "てれ", "eyes": "open", "scale": 0.96, "tilt": 1.5, "mouth": "small", "brow": "tare", "blush": 0.75, "lines": True},
}

from .scenes import BACKGROUND, EFFECT, EFFECT_CSS  # noqa: E402

STYLES = {"face": FACE, "hair": HAIR, "top": TOP, "bottom": BOTTOM, "shoes": SHOES, "accessory": ACCESSORY,
          "effect": EFFECT, "background": BACKGROUND}


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
    return template.format(c=c, d=shade(c, 0.68), l=shade(c, 1.45), h=c[1:])


# =====================================================================================
# 体・顔
# =====================================================================================

def _body(skin: str) -> str:
    s, sd = skin, shade(skin, 0.85)
    return (
        # 脚・足
        f'<path d="M93 200 L92 274 M107 200 L108 274" stroke="{s}" stroke-width="10.5" stroke-linecap="round"/>'
        f'<ellipse cx="90" cy="278" rx="7" ry="4.5" fill="{s}"/><ellipse cx="110" cy="278" rx="7" ry="4.5" fill="{s}"/>'
        # 肌着 (服を着ていないときの既定)
        '<path d="M78 146 Q100 138 122 146 L124 202 L76 202 Z" fill="#F4F1EC" stroke="#D8D1C6" stroke-width="1.2"/>'
        '<rect x="77" y="196" width="46" height="16" rx="4" fill="#C9C3BA"/>'
        # 腕・手
        f'<path d="M80 152 L70 200 M120 152 L130 200" stroke="{s}" stroke-width="9" stroke-linecap="round"/>'
        f'<circle cx="69" cy="203" r="5.5" fill="{s}"/><circle cx="131" cy="203" r="5.5" fill="{s}"/>'
        f'<rect x="94.5" y="126" width="11" height="20" rx="4" fill="{sd}"/>'
    )


def _head(skin: str) -> str:
    s, sd = skin, shade(skin, 0.88)
    return (
        f'<ellipse cx="59" cy="100" rx="5.5" ry="8" fill="{sd}"/><ellipse cx="141" cy="100" rx="5.5" ry="8" fill="{sd}"/>'
        f'<path d="M59 88 Q59 50 100 48 Q141 50 141 88 Q141 118 123 130 Q111 138 100 138 Q89 138 77 130 Q59 118 59 88 Z" fill="{s}"/>'
    )


LID = "#3B2A2A"
EYE_X = (82, 118)
EYE_Y = 104


def _eye(cx: float, cy: float, iris: str, girl: bool, outer: int, preset: dict, skin: str) -> str:
    """瞳 1 つ。顔の大きさに対して自然な大きさ (以前の約 65% の面積)。outer は目尻の向き (-1 = 左目, 1 = 右目)。"""
    s = preset["scale"]
    rx, ry = ((9.6, 11.4) if girl else (8.8, 10.2))
    rx, ry = rx * s, ry * s
    tilt = preset["tilt"]
    lid_top = cy - ry - (3.6 if girl else 2.4)
    # 目尻側を tilt だけ下げる (たれ目) / 上げる (つり目)
    inner_y, outer_y = cy - 4.5 + tilt * -0.3, cy - 5 + tilt
    x_in, x_out = cx - outer * (rx + 1.2), cx + outer * (rx + 1.2)
    lid_d = f"M{x_in:.1f} {inner_y:.1f} Q{cx:.1f} {lid_top:.1f} {x_out:.1f} {outer_y:.1f}"
    lash = (f'<path d="M{x_out:.1f} {outer_y:.1f} L{x_out + outer * 3.8:.1f} {outer_y - 4:.1f}" stroke="{LID}" stroke-width="2.2" stroke-linecap="round"/>'
            if girl else "")
    hl = (f'<path d="M{cx + 3.2} {cy - 8.4} L{cx + 4.2} {cy - 5.6} L{cx + 7} {cy - 4.6} L{cx + 4.2} {cy - 3.6} L{cx + 3.2} {cy - 0.8} '
          f'L{cx + 2.2} {cy - 3.6} L{cx - 0.6} {cy - 4.6} L{cx + 2.2} {cy - 5.6} Z" fill="#FFFFFF"/>'
          if preset.get("star") else f'<ellipse cx="{cx + 3.1:.1f}" cy="{cy - 4.2:.1f}" rx="{3.1 * s:.1f}" ry="{3.4 * s:.1f}" fill="#FFFFFF"/>')
    eye = (
        f'<ellipse cx="{cx}" cy="{cy}" rx="{rx:.1f}" ry="{ry:.1f}" fill="#FFFFFF"/>'
        f'<ellipse cx="{cx}" cy="{cy + 0.8:.1f}" rx="{rx - 1.5:.1f}" ry="{ry - 1:.1f}" fill="url(#iris-{iris[1:]})"/>'
        f'<ellipse cx="{cx}" cy="{cy + 4.5:.1f}" rx="{rx - 3.4:.1f}" ry="{ry * 0.38:.1f}" fill="{shade(iris, 1.7)}" opacity="0.45"/>'
        f'<ellipse cx="{cx}" cy="{cy + 1.2:.1f}" rx="{3.2 * s:.1f}" ry="{4.8 * s:.1f}" fill="{shade(iris, 0.28)}"/>'
        + hl
        + f'<circle cx="{cx - 3.2:.1f}" cy="{cy + 5:.1f}" r="1.6" fill="#FFFFFF" opacity="0.9"/>'
    )
    if preset["eyes"] == "sleepy":  # まぶたを半分おろす
        eye += (f'<path d="M{cx - rx - 1:.1f} {cy + 0.5:.1f} L{cx - rx - 1:.1f} {cy - ry - 2:.1f} L{cx + rx + 1:.1f} {cy - ry - 2:.1f} '
                f'L{cx + rx + 1:.1f} {cy + 0.5:.1f} Q{cx} {cy - 2:.1f} {cx - rx - 1:.1f} {cy + 0.5:.1f} Z" fill="{skin}"/>')
        lid_d = f"M{x_in:.1f} {cy:.1f} Q{cx:.1f} {cy - 2.6:.1f} {x_out:.1f} {cy + 0.6:.1f}"
    return (
        eye
        + f'<path d="{lid_d}" fill="none" stroke="{LID}" stroke-width="{3.2 if girl else 2.8}" stroke-linecap="round"/>'
        + lash
        + f'<path d="M{cx - 5.5:.1f} {cy + ry - 0.4:.1f} Q{cx} {cy + ry + 1.6:.1f} {cx + 5.5:.1f} {cy + ry - 0.4:.1f}" fill="none" stroke="#B07A6A" stroke-width="1" opacity="0.55"/>'
    )


def _closed_eye(cx: float, cy: float) -> str:
    """にっこり閉じた目 (^)。"""
    return f'<path d="M{cx - 8} {cy + 2} Q{cx} {cy - 7} {cx + 8} {cy + 2}" fill="none" stroke="{LID}" stroke-width="3" stroke-linecap="round"/>'


_MOUTHS = {
    "smile": '<path d="M95 125 Q100 129.5 105 125" fill="none" stroke="#B5524E" stroke-width="1.7" stroke-linecap="round"/>',
    "open": '<path d="M94.5 123.5 Q100 124.5 105.5 123.5 Q104.5 131 100 131 Q95.5 131 94.5 123.5 Z" fill="#C24B52"/>'
            '<path d="M96.6 128.6 Q100 126.6 103.4 128.6 Q102 131 100 131 Q98 131 96.6 128.6 Z" fill="#F08A9A"/>',
    "grin": '<path d="M93.5 123.5 Q100 125 106.5 123.5 Q105 130.5 100 130.5 Q95 130.5 93.5 123.5 Z" fill="#C24B52"/>'
            '<path d="M94.5 124 Q100 125.3 105.5 124 L105 126 Q100 127 95 126 Z" fill="#FFFFFF"/>',
    "cat": '<path d="M95 125 Q97.5 128.5 100 125.5 Q102.5 128.5 105 125" fill="none" stroke="#B5524E" stroke-width="1.6" stroke-linecap="round"/>',
    "o": '<ellipse cx="100" cy="127" rx="3" ry="3.6" fill="#C24B52"/>',
    "flat": '<path d="M96 126.5 L104 126" stroke="#9A5050" stroke-width="1.7" stroke-linecap="round"/>',
    "small": '<path d="M97.5 126 Q100 128 102.5 126" fill="none" stroke="#B5524E" stroke-width="1.5" stroke-linecap="round"/>',
}
_BROWS = {
    "normal": ("M74 84 Q82 80.5 90 83", "M110 83 Q118 80.5 126 84"),
    "up": ("M74 82 Q82 77.5 90 80.5", "M110 80.5 Q118 77.5 126 82"),
    "tare": ("M74 81 Q82 81 90 84", "M110 84 Q118 81 126 81"),
    "tsuri": ("M74 86 Q82 81 90 81", "M110 81 Q118 81 126 86"),
}


def _face(body_type: str, eye_color: str, brow: str, face: Part | None, skin: str) -> str:
    girl = body_type == "girl"
    preset = FACE.get(face.style if face else "standard", FACE["standard"])
    accent = safe_color(face.color, "#FF8FA3") if face else "#FF8FA3"
    iris = EYE_COLORS.get(eye_color, EYE_COLORS["brown"])
    bw = 1.7 if girl else 2.5
    b_left, b_right = _BROWS[preset["brow"]]
    out = (f'<path d="{b_left}" fill="none" stroke="{brow}" stroke-width="{bw}" stroke-linecap="round"/>'
           f'<path d="{b_right}" fill="none" stroke="{brow}" stroke-width="{bw}" stroke-linecap="round"/>')
    (lx, rx_), cy = EYE_X, EYE_Y
    kind = preset["eyes"]
    left = _closed_eye(lx, cy) if kind == "happy" else _eye(lx, cy, iris, girl, -1, preset, skin)
    right = _closed_eye(rx_, cy) if kind in ("happy", "wink") else _eye(rx_, cy, iris, girl, 1, preset, skin)
    out += left + right
    out += '<path d="M99.4 118 L100.4 119.2" stroke="#C99280" stroke-width="1.2" stroke-linecap="round"/>'
    out += _MOUTHS[preset["mouth"]]
    op = preset["blush"]
    out += (f'<ellipse cx="72" cy="119" rx="7.5" ry="3.6" fill="{accent}" opacity="{op}"/>'
            f'<ellipse cx="128" cy="119" rx="7.5" ry="3.6" fill="{accent}" opacity="{op}"/>')
    if preset.get("lines"):  # てれ線
        out += ('<path d="M67 117 L69 121 M71 117 L73 121 M75 117 L77 121 M123 117 L125 121 M127 117 L129 121 M131 117 L133 121" '
                f'stroke="{shade(accent, 0.7)}" stroke-width="1.2" stroke-linecap="round" opacity="0.8"/>')
    return out


def _defs(eye_color: str) -> str:
    iris = EYE_COLORS.get(eye_color, EYE_COLORS["brown"])
    return (
        # id は色ごとに変える (1 つの HTML に複数のアバターを直接埋め込んでも混ざらないように)
        f'<defs><linearGradient id="iris-{iris[1:]}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{shade(iris, 0.42)}"/><stop offset="0.55" stop-color="{iris}"/>'
        f'<stop offset="1" stop-color="{shade(iris, 1.55)}"/></linearGradient>'
        '<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFF7EA"/>'
        '<stop offset="1" stop-color="#FDE7D2"/></linearGradient>'
        '<clipPath id="card"><rect x="0" y="0" width="200" height="300" rx="18"/></clipPath></defs>'
    )


def render_svg(skin_tone: str, parts: dict[str, Part | None], *, body_type: str = "girl", eye_color: str = "brown",
               label: str = "アバター", size: int | None = None, background: bool = True) -> str:
    """アバター全体の SVG 文字列を返す。"""
    skin = SKIN_TONES.get(skin_tone, SKIN_TONES["tone3"])
    body_type = body_type if body_type in dict(BODY_TYPE_CHOICES) else "girl"
    eye_color = eye_color if eye_color in EYE_COLORS else "brown"

    def layer(category: str, key: str = "svg") -> str:
        p = parts.get(category)
        if p is None or p.style not in STYLES[category]:
            return ""
        return _fmt(STYLES[category][p.style].get(key, ""), p.color)

    hair = parts.get("hair")
    brow = shade(safe_color(hair.color), 0.7) if hair else "#6B4A3A"
    described = [f"{CATEGORY_LABELS[c]}: {p.name}" for c, p in parts.items() if p is not None and p.name]
    aria = escape(label + (" (" + "、".join(described) + ")" if described else ""))
    dims = f' width="{int(size)}" height="{int(size * 300 / 200)}"' if size else ""
    bg = ""
    if background:
        bg = layer("background") or '<rect x="0" y="0" width="200" height="300" rx="18" fill="url(#bg)"/>'
        bg += '<ellipse cx="100" cy="286" rx="48" ry="6" fill="#000000" opacity="0.1"/>'
    effect = parts.get("effect")
    body = "".join([
        _defs(eye_color),
        EFFECT_CSS if effect is not None and effect.style in EFFECT else "",
        bg,
        layer("effect", "back"),
        layer("hair", "back"),
        _body(skin),
        layer("shoes"),
        layer("bottom"),
        layer("top"),
        _head(skin),
        _face(body_type, eye_color, brow, parts.get("face"), skin),
        layer("hair", "front"),
        layer("accessory"),
        layer("effect", "front"),
    ])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 300"{dims} role="img" aria-label="{aria}">'
        f"<title>{aria}</title>{body}</svg>"
    )

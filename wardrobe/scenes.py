"""アバターの背景 (20 種類) とアニメーションするエフェクト。

テンプレートには {c}=色 {d}=暗い色 {l}=明るい色 だけを差し込む (avatar._fmt)。
エフェクトは SVG 内の CSS アニメーションで動く (GIF より軽く、拡大してもくっきり)。
OS の「視差効果を減らす」設定 (prefers-reduced-motion) が有効なら動きを止める。
座標系は viewBox="0 0 200 300"。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------------
# 小さな図形の生成 (f-string で座標を埋め、色はテンプレートの {c} 等のまま残す)
# ---------------------------------------------------------------------------------


def _star4(x: float, y: float, r: float) -> str:
    k = r * 0.28
    return (f"M{x} {y - r} L{x + k} {y - k} L{x + r} {y} L{x + k} {y + k} "
            f"L{x} {y + r} L{x - k} {y + k} L{x - r} {y} L{x - k} {y - k} Z")


def _star5(x: float, y: float, r: float) -> str:
    import math

    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.45
        a = math.pi / 5 * i - math.pi / 2
        pts.append(f"{x + rr * math.cos(a):.1f} {y + rr * math.sin(a):.1f}")
    return "M" + " L".join(pts) + " Z"


def _heart(x: float, y: float, s: float) -> str:
    return (f"M{x} {y + s * 0.9} C{x - s * 1.4} {y - s * 0.1} {x - s * 0.6} {y - s * 1.1} {x} {y - s * 0.35} "
            f"C{x + s * 0.6} {y - s * 1.1} {x + s * 1.4} {y - s * 0.1} {x} {y + s * 0.9} Z")


def _petal(x: float, y: float, s: float) -> str:
    return f"M{x} {y - s} Q{x + s} {y} {x} {y + s} Q{x - s * 0.6} {y} {x} {y - s} Z"


def _clip(inner: str) -> str:
    return f'<g clip-path="url(#card)">{inner}</g>'


def _grad(gid: str, top: str, bottom: str, mid: str | None = None) -> str:
    stops = f'<stop offset="0" stop-color="{top}"/>'
    if mid:
        stops += f'<stop offset="0.55" stop-color="{mid}"/>'
    stops += f'<stop offset="1" stop-color="{bottom}"/>'
    return f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">{stops}</linearGradient></defs>'


_FULL = '<rect x="0" y="0" width="200" height="300" fill="url(#{g})"/>'

# 背景の座標の素材
_CLOUDS = ('<g fill="#FFFFFF" opacity="0.9"><ellipse cx="40" cy="60" rx="22" ry="10"/><ellipse cx="56" cy="54" rx="16" ry="11"/>'
           '<ellipse cx="160" cy="92" rx="20" ry="9"/><ellipse cx="146" cy="86" rx="13" ry="9"/></g>')
_SMALL_STARS = "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#FFFFFF" opacity="{o}"/>'
                       for x, y, r, o in ((20, 30, 1.4, .9), (48, 70, 1, .7), (170, 40, 1.6, .9), (150, 120, 1, .6),
                                          (30, 150, 1.2, .8), (182, 180, 1, .7), (90, 24, 1, .6), (120, 60, 1.2, .8),
                                          (12, 220, 1, .6), (188, 250, 1.3, .7)))

BACKGROUND = {
    "cream": {"label": "クリーム", "svg": _grad("bgx", "{l}", "{c}") + _FULL.format(g="bgx")},
    "sky": {"label": "青空", "svg": _grad("bgx", "{c}", "#F2FAFF") + _FULL.format(g="bgx") + _CLOUDS
            + '<path d="M0 262 Q60 246 120 258 Q170 266 200 254 L200 300 L0 300 Z" fill="#9AD27E"/>'},
    "sunset": {"label": "夕焼け", "svg": _grad("bgx", "{d}", "#FFE2A8", "{c}") + _FULL.format(g="bgx")
               + '<circle cx="150" cy="212" r="26" fill="#FFE59A" opacity="0.9"/>'
               + '<path d="M0 248 Q50 226 100 244 Q150 260 200 238 L200 300 L0 300 Z" fill="{d}" opacity="0.8"/>'},
    "night": {"label": "星空", "svg": _grad("bgx", "#0C1238", "{c}") + _FULL.format(g="bgx") + _SMALL_STARS
              + '<path d="M162 34 A16 16 0 1 0 176 58 A12 12 0 1 1 162 34 Z" fill="#FFF3B0"/>'},
    "sakura": {"label": "桜並木", "svg": _grad("bgx", "{l}", "#FFFFFF") + _FULL.format(g="bgx")
               + '<path d="M0 40 Q50 52 90 30 M30 47 Q40 70 30 90 M150 10 Q170 60 200 70" fill="none" stroke="#8A5A44" stroke-width="5" stroke-linecap="round"/>'
               + "".join(f'<path d="{_petal(x, y, 5)}" fill="{{c}}" opacity="0.85"/>'
                         for x, y in ((20, 30), (60, 40), (88, 22), (40, 80), (170, 50), (186, 72), (150, 140), (24, 190), (176, 220), (60, 250)))},
    "autumn": {"label": "紅葉", "svg": _grad("bgx", "#FFF3DA", "{l}") + _FULL.format(g="bgx")
               + "".join(f'<path d="{_star5(x, y, r)}" fill="{fill}" opacity="0.85"/>'
                         for x, y, r, fill in ((24, 40, 10, "{c}"), (170, 30, 12, "{d}"), (40, 140, 8, "{d}"), (176, 120, 9, "{c}"),
                                               (20, 240, 11, "{c}"), (180, 250, 10, "{d}"), (100, 20, 7, "{c}")))},
    "snow": {"label": "雪景色", "svg": _grad("bgx", "{c}", "#EEF6FF") + _FULL.format(g="bgx")
             + '<path d="M0 240 Q50 220 100 236 Q150 252 200 230 L200 300 L0 300 Z" fill="#FFFFFF"/>'
             + "".join(f'<circle cx="{x}" cy="{y}" r="2.2" fill="#FFFFFF"/>' for x, y in ((20, 40), (60, 90), (170, 50), (150, 150), (30, 190), (184, 200), (110, 30)))},
    "beach": {"label": "海辺", "svg": _grad("bgx", "#9EDCFF", "#E9F8FF") + _FULL.format(g="bgx")
              + '<circle cx="160" cy="54" r="18" fill="#FFE07A"/>'
              + '<rect x="0" y="186" width="200" height="50" fill="{c}"/><path d="M0 196 Q25 190 50 196 T100 196 T150 196 T200 196" fill="none" stroke="#FFFFFF" stroke-width="2" opacity="0.7"/>'
              + '<path d="M0 236 Q100 226 200 236 L200 300 L0 300 Z" fill="#F4DDB0"/>'},
    "castle": {"label": "お城", "svg": _grad("bgx", "{l}", "#FFFFFF") + _FULL.format(g="bgx")
               + '<g fill="{d}" opacity="0.75"><rect x="18" y="210" width="164" height="60"/><path d="M30 214 L100 196 L170 214 Z"/>'
               + '<rect x="44" y="168" width="112" height="30"/><path d="M36 172 L100 150 L164 172 Z"/><rect x="62" y="130" width="76" height="24"/>'
               + '<path d="M54 134 L100 112 L146 134 Z"/><rect x="78" y="96" width="44" height="20"/><path d="M70 100 L100 82 L130 100 Z"/></g>'
               + '<path d="M0 270 L200 270 L200 300 L0 300 Z" fill="#B8C8A0"/>'},
    "river": {"label": "川べりの街", "svg": _grad("bgx", "{l}", "#FFFFFF") + _FULL.format(g="bgx")
              + '<g fill="{d}" opacity="0.5"><rect x="4" y="150" width="30" height="90"/><rect x="38" y="120" width="26" height="120"/>'
              + '<rect x="140" y="130" width="24" height="110"/><rect x="168" y="160" width="30" height="80"/></g>'
              + '<rect x="0" y="236" width="200" height="64" fill="{c}"/><path d="M0 250 Q50 244 100 250 T200 250" fill="none" stroke="#FFFFFF" stroke-width="2" opacity="0.6"/>'
              + '<path d="M0 226 Q100 180 200 226" fill="none" stroke="{d}" stroke-width="6"/>'},
    "shrine": {"label": "神社", "svg": _grad("bgx", "#FFF5E6", "{l}") + _FULL.format(g="bgx")
               + '<g fill="{c}"><rect x="10" y="60" width="180" height="12" rx="3"/><rect x="22" y="82" width="156" height="8"/>'
               + '<rect x="36" y="64" width="12" height="210"/><rect x="152" y="64" width="12" height="210"/></g>'
               + '<rect x="0" y="270" width="200" height="30" fill="#D8C8A8"/>'},
    "festival": {"label": "お祭り", "svg": _grad("bgx", "#1C1440", "{d}") + _FULL.format(g="bgx")
                 + '<path d="M0 40 Q100 70 200 40" fill="none" stroke="#3A2A1A" stroke-width="1.5"/>'
                 + "".join(f'<g><line x1="{x}" y1="{y - 8}" x2="{x}" y2="{y}" stroke="#3A2A1A"/><ellipse cx="{x}" cy="{y + 9}" rx="9" ry="11" fill="{{c}}"/>'
                           f'<ellipse cx="{x}" cy="{y + 9}" rx="14" ry="16" fill="{{c}}" opacity="0.25"/></g>'
                           for x, y in ((20, 46), (60, 56), (100, 59), (140, 56), (180, 46)))},
    "onsen": {"label": "温泉", "svg": _grad("bgx", "{l}", "#FFFFFF") + _FULL.format(g="bgx")
              + '<path d="M40 210 Q30 190 42 172 Q54 154 44 136 M100 200 Q88 178 102 160 Q116 142 104 122 M160 210 Q150 190 162 172 Q174 154 164 136" fill="none" stroke="#FFFFFF" stroke-width="7" stroke-linecap="round" opacity="0.9"/>'
              + '<ellipse cx="100" cy="270" rx="110" ry="30" fill="{c}"/><g fill="{d}" opacity="0.6"><ellipse cx="14" cy="250" rx="20" ry="12"/><ellipse cx="188" cy="252" rx="20" ry="12"/></g>'},
    "cafe": {"label": "カフェ", "svg": _grad("bgx", "{l}", "{c}") + _FULL.format(g="bgx")
             + '<rect x="20" y="30" width="70" height="80" rx="6" fill="#DFF1FF" stroke="{d}" stroke-width="4"/><path d="M55 30 L55 110 M20 70 L90 70" stroke="{d}" stroke-width="3"/>'
             + '<rect x="0" y="232" width="200" height="68" fill="{d}"/><rect x="0" y="226" width="200" height="8" fill="#8A5A44"/>'
             + '<g transform="translate(160 206)"><rect x="-10" y="0" width="20" height="20" rx="3" fill="#FFFFFF"/><path d="M10 5 Q18 8 10 15" fill="none" stroke="#FFFFFF" stroke-width="3"/></g>'},
    "stage": {"label": "ステージ", "svg": _grad("bgx", "#1A1030", "#3A2050") + _FULL.format(g="bgx")
              + '<path d="M30 0 L-10 300 L70 300 Z M170 0 L130 300 L210 300 Z" fill="{c}" opacity="0.25"/>'
              + '<path d="M100 0 L70 300 L130 300 Z" fill="#FFFFFF" opacity="0.12"/>'
              + '<rect x="0" y="262" width="200" height="38" fill="#2A1A3A"/><path d="M0 262 L200 262" stroke="{l}" stroke-width="2"/>'},
    "city": {"label": "夜の街", "svg": _grad("bgx", "#101830", "{d}") + _FULL.format(g="bgx")
             + '<g fill="#1A2238"><rect x="0" y="150" width="40" height="150"/><rect x="44" y="110" width="34" height="190"/>'
             + '<rect x="122" y="130" width="36" height="170"/><rect x="162" y="90" width="38" height="210"/></g>'
             + "".join(f'<rect x="{x}" y="{y}" width="5" height="6" fill="{{l}}" opacity="0.9"/>'
                       for x, y in ((8, 166), (24, 186), (52, 126), (64, 150), (52, 190), (130, 146), (144, 172), (170, 106), (184, 130), (170, 160), (186, 196)))},
    "forest": {"label": "森", "svg": _grad("bgx", "#EAF7E4", "{l}") + _FULL.format(g="bgx")
               + "".join(f'<path d="M{x} {y} L{x - w} {y + h} L{x + w} {y + h} Z" fill="{fill}"/>'
                         for x, y, w, h, fill in ((20, 100, 26, 120, "{d}"), (60, 140, 22, 100, "{c}"), (150, 110, 24, 120, "{c}"), (186, 90, 26, 140, "{d}")))
               + '<rect x="0" y="262" width="200" height="38" fill="{d}" opacity="0.5"/>'},
    "rainbow": {"label": "虹", "svg": _grad("bgx", "{l}", "#FFFFFF") + _FULL.format(g="bgx")
                + "".join(f'<path d="M-10 210 A110 110 0 0 1 210 210" fill="none" stroke="{col}" stroke-width="7" transform="translate(0 {i * 7})" opacity="0.7"/>'
                          for i, col in enumerate(("#FF7A7A", "#FFB86B", "#FFE27A", "#8EDB8E", "#7AC7FF", "#A78BFA")))
                + _CLOUDS},
    "dots": {"label": "水玉", "svg": _grad("bgx", "#FFFFFF", "{l}") + _FULL.format(g="bgx")
             + "".join(f'<circle cx="{x}" cy="{y}" r="7" fill="{{c}}" opacity="0.5"/>' for y in range(20, 300, 40) for x in range(20 + (y // 40 % 2) * 20, 200, 40))},
    "hearts": {"label": "ハート柄", "svg": _grad("bgx", "#FFFFFF", "{l}") + _FULL.format(g="bgx")
               + "".join(f'<path d="{_heart(x, y, 7)}" fill="{{c}}" opacity="0.45"/>' for y in range(26, 300, 44) for x in range(22 + (y // 44 % 2) * 22, 200, 44))},
}
for _k, _v in BACKGROUND.items():
    # グラデーションの id は「背景の種類 + 色」で一意にする ({h} = 色の16進数。複数のアバターを同じページに直接埋め込んでも混ざらない)
    _v["svg"] = _clip(_v["svg"].replace("bgx", f"bg-{_k}-{{h}}"))

# ---------------------------------------------------------------------------------
# エフェクト (アニメーション)。"back" はアバターの後ろ、"front" は前に描く
# ---------------------------------------------------------------------------------

EFFECT_CSS = (
    "<style>"
    ".fx-tw{animation:fxTw 1.8s ease-in-out infinite;transform-box:fill-box;transform-origin:center}"
    "@keyframes fxTw{0%,100%{opacity:.15;transform:scale(.4)}50%{opacity:1;transform:scale(1.15)}}"
    ".fx-up{animation:fxUp 3.6s linear infinite;transform-box:fill-box;transform-origin:center}"
    "@keyframes fxUp{0%{opacity:0;transform:translateY(24px) scale(.6)}15%{opacity:1}85%{opacity:.9}100%{opacity:0;transform:translateY(-110px) scale(1.1)}}"
    ".fx-fall{animation:fxFall 5s linear infinite;transform-box:fill-box;transform-origin:center}"
    "@keyframes fxFall{0%{opacity:0;transform:translate(0,-40px) rotate(0deg)}10%{opacity:1}90%{opacity:.9}100%{opacity:0;transform:translate(18px,260px) rotate(260deg)}}"
    ".fx-pulse{animation:fxPulse 2.6s ease-in-out infinite;transform-box:fill-box;transform-origin:center}"
    "@keyframes fxPulse{0%,100%{opacity:.35;transform:scale(.94)}50%{opacity:.85;transform:scale(1.06)}}"
    ".fx-drift{animation:fxDrift 4.6s ease-in-out infinite}"
    "@keyframes fxDrift{0%,100%{transform:translate(0,0);opacity:.2}50%{transform:translate(9px,-16px);opacity:1}}"
    ".fx-spin{animation:fxSpin 4s linear infinite;transform-box:fill-box;transform-origin:center}"
    "@keyframes fxSpin{0%{transform:rotate(0deg) scale(.8);opacity:.4}50%{transform:rotate(180deg) scale(1.1);opacity:1}100%{transform:rotate(360deg) scale(.8);opacity:.4}}"
    "@media (prefers-reduced-motion:reduce){.fx-tw,.fx-up,.fx-fall,.fx-pulse,.fx-drift,.fx-spin{animation:none}}"
    "</style>"
)

# アバターの周り (頭の横・肩の横・足もと) に置く位置と、動き出しのずらし
_AROUND = [(30, 60, 0), (172, 76, -0.6), (24, 150, -1.1), (178, 170, -0.3), (40, 230, -1.5), (164, 250, -0.9), (100, 26, -1.3)]
_RISE = [(34, 220, 0), (166, 236, -1.2), (56, 160, -2.1), (150, 190, -0.6), (24, 120, -2.8), (180, 120, -1.7)]
_FALL = [(20, 0, 0), (60, 0, -1.4), (140, 0, -2.6), (180, 0, -0.7), (100, 0, -3.5), (36, 0, -4.2), (160, 0, -3.0)]


def _delay(d: float) -> str:
    return f' style="animation-delay:{d}s"'


EFFECT = {
    "sparkle": {"label": "キラキラ", "front": "".join(
        f'<path class="fx-tw" d="{_star4(x, y, 7)}" fill="{{l}}" stroke="{{c}}" stroke-width="1"{_delay(d)}/>' for x, y, d in _AROUND)},
    "hearts": {"label": "ふわふわハート", "front": "".join(
        f'<path class="fx-up" d="{_heart(x, y, 7)}" fill="{{c}}" opacity="0.9"{_delay(d)}/>' for x, y, d in _RISE)},
    "stars": {"label": "くるくるスター", "front": "".join(
        f'<path class="fx-spin" d="{_star5(x, y, 7)}" fill="{{c}}" stroke="{{d}}" stroke-width="0.8"{_delay(d)}/>' for x, y, d in _AROUND)},
    "petals": {"label": "花びらの舞", "front": "".join(
        f'<path class="fx-fall" d="{_petal(x, y, 5)}" fill="{{c}}"{_delay(d)}/>' for x, y, d in _FALL)},
    "notes": {"label": "音符", "front": "".join(
        f'<g class="fx-up"{_delay(d)}><ellipse cx="{x}" cy="{y}" rx="4.5" ry="3.5" fill="{{c}}"/><path d="M{x + 4} {y} L{x + 4} {y - 15} L{x + 10} {y - 12}" fill="none" stroke="{{c}}" stroke-width="2"/></g>'
        for x, y, d in _RISE)},
    "bubbles": {"label": "シャボン玉", "front": "".join(
        f'<g class="fx-up"{_delay(d)}><circle cx="{x}" cy="{y}" r="7" fill="{{l}}" fill-opacity="0.35" stroke="{{c}}" stroke-width="1.2"/>'
        f'<circle cx="{x - 2.5}" cy="{y - 2.5}" r="1.8" fill="#FFFFFF"/></g>' for x, y, d in _RISE)},
    "snowfall": {"label": "粉雪", "front": "".join(
        f'<circle class="fx-fall" cx="{x}" cy="{y}" r="3" fill="{{l}}"{_delay(d)}/>' for x, y, d in _FALL)},
    "confetti": {"label": "紙ふぶき", "front": "".join(
        f'<rect class="fx-fall" x="{x}" y="{y}" width="5" height="8" fill="{col}"{_delay(d)}/>'
        for (x, y, d), col in zip(_FALL, ("{c}", "#FFD84D", "#7AC7FF", "{l}", "#FF7A9A", "#8EDB8E", "{d}"), strict=True))},
    "aura": {"label": "オーラ", "back": '<ellipse class="fx-pulse" cx="100" cy="160" rx="80" ry="130" fill="{c}" opacity="0.22"/>'
             '<ellipse class="fx-pulse" cx="100" cy="160" rx="62" ry="110" fill="{l}" opacity="0.3" style="animation-delay:-1.3s"/>'},
    "fireflies": {"label": "ほたる", "front": "".join(
        f'<g class="fx-drift"{_delay(d)}><circle cx="{x}" cy="{y}" r="6" fill="{{l}}" opacity="0.35"/><circle cx="{x}" cy="{y}" r="2.4" fill="{{c}}"/></g>'
        for x, y, d in _AROUND)},
}

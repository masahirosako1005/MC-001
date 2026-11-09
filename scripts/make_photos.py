"""ログイン前ページで使う「仮想写真」(写真風の CG イラスト) を生成する。

    python scripts/make_photos.py        # static/img/photos/*.svg を作り直す

実在の写真ではなく、グラデーション・ぼかし (被写界深度)・光の玉ボケ・フィルム粒子などで
写真らしく見せた SVG イラスト。架空の風景で、特定の実在施設を写したものではない。
乱数のシードを固定しているので、何度実行しても同じ画像になる。
"""

from __future__ import annotations

import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "static" / "img" / "photos"
W, H = 1200, 800


def _common_defs(extra: str = "") -> str:
    return (
        "<defs>"
        '<filter id="b2"><feGaussianBlur stdDeviation="2"/></filter>'
        '<filter id="b6"><feGaussianBlur stdDeviation="6"/></filter>'
        '<filter id="b14"><feGaussianBlur stdDeviation="14"/></filter>'
        '<filter id="b30"><feGaussianBlur stdDeviation="30"/></filter>'
        # フィルムの粒子
        '<filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7"/>'
        '<feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="table" tableValues="0 0.10"/></feComponentTransfer></filter>'
        # 周辺減光
        '<radialGradient id="vig" cx="50%" cy="50%" r="75%"><stop offset="0.55" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#000" stop-opacity="0.55"/></radialGradient>'
        + extra + "</defs>"
    )


def _finish() -> str:
    return (f'<rect width="{W}" height="{H}" fill="url(#vig)"/>'
            f'<rect width="{W}" height="{H}" filter="url(#grain)" opacity="0.9"/>')


def _svg(title: str, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'role="img" aria-label="{title}(CG によるイメージ)"><title>{title}(CG によるイメージ)</title>{body}</svg>\n')


def _bokeh(rng: random.Random, n: int, area: tuple[int, int, int, int], colors: list[str], rmin=8, rmax=34) -> str:
    x0, y0, x1, y1 = area
    out = []
    for _ in range(n):
        r = rng.uniform(rmin, rmax)
        out.append(f'<circle cx="{rng.uniform(x0, x1):.0f}" cy="{rng.uniform(y0, y1):.0f}" r="{r:.0f}" '
                   f'fill="{rng.choice(colors)}" opacity="{rng.uniform(0.25, 0.7):.2f}"/>')
    return f'<g filter="url(#b6)">{"".join(out)}</g>'


# ------------------------------------------------------------------------- 1. 夕暮れの川べり
def riverside() -> str:
    rng = random.Random(1)
    defs = _common_defs(
        '<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#23234F"/>'
        '<stop offset="0.45" stop-color="#8A4E7A"/><stop offset="0.75" stop-color="#F08A5D"/><stop offset="1" stop-color="#FFD08A"/></linearGradient>'
        '<linearGradient id="water" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#D9805F"/>'
        '<stop offset="0.35" stop-color="#5B3F68"/><stop offset="1" stop-color="#191830"/></linearGradient>'
        '<radialGradient id="sun" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#FFF6D8"/>'
        '<stop offset="0.25" stop-color="#FFD58A" stop-opacity="0.9"/><stop offset="1" stop-color="#FF9A5A" stop-opacity="0"/></radialGradient>'
    )
    city = []
    x = 0
    while x < W:
        w = rng.randint(30, 80)
        h = rng.randint(60, 230)
        city.append(f'<rect x="{x}" y="{470 - h}" width="{w}" height="{h}" fill="#3B2E4D"/>')
        for _ in range(rng.randint(2, 9)):
            city.append(f'<rect x="{x + rng.randint(4, max(5, w - 8))}" y="{470 - h + rng.randint(8, max(9, h - 10))}" '
                        f'width="4" height="5" fill="#FFD98A" opacity="{rng.uniform(.5, 1):.2f}"/>')
        x += w + rng.randint(0, 6)
    streaks = "".join(f'<rect x="{rng.randint(640, 1020)}" y="{y}" width="{rng.randint(40, 160)}" height="3" fill="#FFE0A0" opacity="{rng.uniform(.3, .8):.2f}"/>'
                      for y in range(482, 760, 9))
    body = (
        defs
        + f'<rect width="{W}" height="480" fill="url(#sky)"/>'
        + '<circle cx="830" cy="430" r="260" fill="url(#sun)"/>'
        + '<g opacity="0.55" filter="url(#b14)"><ellipse cx="300" cy="200" rx="260" ry="26" fill="#F7A58A"/>'
          '<ellipse cx="900" cy="150" rx="300" ry="20" fill="#E8869A"/></g>'
        + f'<g filter="url(#b2)" opacity="0.92">{"".join(city)}</g>'
        + f'<rect y="470" width="{W}" height="{H - 470}" fill="url(#water)"/>'
        + f'<g filter="url(#b2)">{streaks}</g>'
        # 橋 (アーチ)
        + '<path d="M-20 430 Q600 300 1220 430 L1220 446 Q600 318 -20 446 Z" fill="#241E33"/>'
        + "".join(f'<rect x="{x}" y="{390 - abs(600 - x) * 0.2:.0f}" width="6" height="{60 + abs(600 - x) * 0.2:.0f}" fill="#241E33"/>' for x in range(60, 1180, 90))
        + _bokeh(rng, 26, (0, 360, W, 480), ["#FFD98A", "#FFB86B", "#FFF1C8"], 4, 12)
        # 手前の柵とボケた木 (被写界深度)
        + '<g filter="url(#b14)"><path d="M0 800 L0 610 Q120 560 240 640 Q300 700 260 800 Z" fill="#120E1E"/>'
          '<path d="M1200 800 L1200 580 Q1080 540 1000 620 Q960 700 1000 800 Z" fill="#120E1E"/></g>'
        + '<path d="M0 740 L1200 700 L1200 712 L0 752 Z" fill="#0E0B18"/>'
        + "".join(f'<rect x="{x}" y="{700 + (1200 - x) / 30:.0f}" width="5" height="70" fill="#0E0B18"/>' for x in range(20, 1200, 70))
        + _bokeh(rng, 12, (0, 560, W, 800), ["#FFC27A", "#FF9A6A"], 20, 46)
        + _finish()
    )
    return _svg("夕暮れの川べりの街", body)


# ------------------------------------------------------------------------- 2. 桜とお城
def castle() -> str:
    rng = random.Random(2)
    defs = _common_defs(
        '<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5FA8E8"/>'
        '<stop offset="1" stop-color="#DDEFFF"/></linearGradient>'
        '<linearGradient id="wall" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#F4F2EC"/><stop offset="1" stop-color="#C9CCD4"/></linearGradient>'
    )
    clouds = "".join(f'<ellipse cx="{rng.randint(0, W)}" cy="{rng.randint(60, 260)}" rx="{rng.randint(80, 200)}" ry="{rng.randint(20, 45)}" fill="#FFFFFF" opacity="{rng.uniform(.5, .9):.2f}"/>'
                     for _ in range(9))
    tiers = ""
    cx, base, width = 600, 520, 420
    for i in range(5):
        w = width - i * 70
        top = base - 70 * (i + 1)
        tiers += (f'<rect x="{cx - w / 2 + 30}" y="{top + 20}" width="{w - 60}" height="52" fill="url(#wall)"/>'
                  f'<path d="M{cx - w / 2} {top + 26} L{cx} {top - 6} L{cx + w / 2} {top + 26} Z" fill="#2E4A5A"/>'
                  f'<path d="M{cx - w / 2 - 10} {top + 26} L{cx + w / 2 + 10} {top + 26} L{cx + w / 2 - 6} {top + 32} L{cx - w / 2 + 6} {top + 32} Z" fill="#1E3442"/>')
        for k in range(3 if i < 3 else 2):
            tiers += f'<rect x="{cx - 50 + k * 40 - (10 if i >= 3 else 0)}" y="{top + 38}" width="12" height="16" fill="#3A4A56"/>'
    tiers += f'<path d="M{cx - 30} {base - 356} L{cx - 50} {base - 372} M{cx + 30} {base - 356} L{cx + 50} {base - 372}" stroke="#C9A227" stroke-width="5"/>'
    stone = "".join(f'<rect x="{x}" y="{y}" width="58" height="22" fill="#8A877E" stroke="#6E6B63" stroke-width="2"/>'
                    for y in range(540, 640, 22) for x in range(330 - (y // 22 % 2) * 29, 870, 58))
    petals = "".join(f'<ellipse cx="{rng.randint(0, W)}" cy="{rng.randint(0, H)}" rx="5" ry="3" transform="rotate({rng.randint(0, 180)} 0 0)" fill="#FFC6D8" opacity="{rng.uniform(.5, 1):.2f}"/>'
                     for _ in range(60))
    blossoms_l = "".join(f'<circle cx="{rng.randint(-60, 330)}" cy="{rng.randint(-40, 360)}" r="{rng.randint(30, 80)}" fill="{rng.choice(["#F7B8CF", "#FBD3E2", "#F29BB8"])}"/>' for _ in range(36))
    blossoms_r = "".join(f'<circle cx="{rng.randint(900, 1260)}" cy="{rng.randint(-40, 300)}" r="{rng.randint(30, 80)}" fill="{rng.choice(["#F7B8CF", "#FBD3E2", "#F29BB8"])}"/>' for _ in range(30))
    body = (
        defs
        + f'<rect width="{W}" height="{H}" fill="url(#sky)"/>'
        + f'<g filter="url(#b14)">{clouds}</g>'
        + f'<g filter="url(#b2)">{tiers}<path d="M300 540 L900 540 L870 640 L330 640 Z" fill="#8A877E"/>{stone}</g>'
        + '<rect y="640" width="1200" height="160" fill="#4E7E8E"/>'
        + '<g opacity="0.35" filter="url(#b6)"><rect x="380" y="650" width="440" height="90" fill="#F4F2EC"/></g>'
        + f'<g filter="url(#b30)">{blossoms_l}{blossoms_r}</g>'
        + '<path d="M-20 120 Q160 160 330 110" stroke="#4A3428" stroke-width="16" fill="none" filter="url(#b14)"/>'
        + f'<g filter="url(#b2)">{petals}</g>'
        + _finish()
    )
    return _svg("桜とお城", body)


# ------------------------------------------------------------------------- 3. 提灯の灯る路地
def lantern_alley() -> str:
    rng = random.Random(3)
    defs = _common_defs(
        '<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0D1030"/><stop offset="1" stop-color="#3A2448"/></linearGradient>'
        '<linearGradient id="road" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3A2A2E"/><stop offset="1" stop-color="#0E0A10"/></linearGradient>'
        '<radialGradient id="glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#FFB86B" stop-opacity="0.9"/><stop offset="1" stop-color="#FF6A3A" stop-opacity="0"/></radialGradient>'
    )
    vx, vy = 600, 420  # 消失点
    left = f'<path d="M0 0 L{vx - 60} {vy - 120} L{vx - 60} {vy + 40} L0 800 Z" fill="#1E1626"/>'
    right = f'<path d="M1200 0 L{vx + 60} {vy - 120} L{vx + 60} {vy + 40} L1200 800 Z" fill="#1E1626"/>'
    windows = ""
    for t in (0.15, 0.3, 0.45, 0.6, 0.75):
        for side in (-1, 1):
            x = vx + side * (60 + (540 * (1 - t)))
            y = vy - 40 - 300 * (1 - t)
            w = 70 * (1 - t) + 10
            windows += f'<rect x="{x - (w if side > 0 else 0):.0f}" y="{y:.0f}" width="{w:.0f}" height="{w * 0.7:.0f}" fill="#FFCF7A" opacity="0.75"/>'
    lanterns = ""
    for i in range(9):
        t = i / 9
        for side in (-1, 1):
            x = vx + side * (90 + 470 * (1 - t))
            y = vy - 150 + 10 * t - 120 * (1 - t)
            s = 1 - t * 0.85
            lanterns += (f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{80 * s:.0f}" fill="url(#glow)"/>'
                         f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{24 * s:.1f}" ry="{32 * s:.1f}" fill="#E8412E"/>'
                         f'<ellipse cx="{x - 6 * s:.0f}" cy="{y - 8 * s:.0f}" rx="{8 * s:.1f}" ry="{14 * s:.1f}" fill="#FF9A6A" opacity="0.7"/>')
    reflections = "".join(f'<rect x="{rng.randint(200, 1000)}" y="{rng.randint(560, 790)}" width="{rng.randint(4, 14)}" height="{rng.randint(20, 60)}" fill="#FF8A4A" opacity="{rng.uniform(.2, .6):.2f}"/>'
                          for _ in range(40))
    body = (
        defs + f'<rect width="{W}" height="{H}" fill="url(#sky)"/>'
        + left + right + f'<g filter="url(#b2)">{windows}</g>'
        + f'<path d="M0 800 L{vx - 60} {vy + 40} L{vx + 60} {vy + 40} L1200 800 Z" fill="url(#road)"/>'
        + f'<g filter="url(#b6)">{reflections}</g>'
        + lanterns
        + '<path d="M0 0 L1200 0" stroke="#000"/>'
        + _bokeh(rng, 18, (0, 0, W, 300), ["#FFB86B", "#FF6A3A", "#FFE0A0"], 14, 40)
        + _finish()
    )
    return _svg("提灯の灯る夜の路地", body)


# ------------------------------------------------------------------------- 4. 湯けむりの温泉街
def onsen() -> str:
    rng = random.Random(4)
    defs = _common_defs(
        '<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2E4470"/><stop offset="1" stop-color="#E9A27A"/></linearGradient>'
        '<filter id="steam" x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="3" seed="4" result="n"/>'
        '<feDisplacementMap in="SourceGraphic" in2="n" scale="140"/><feGaussianBlur stdDeviation="22"/></filter>'
    )
    hills = '<path d="M0 360 Q200 250 420 330 Q640 240 860 320 Q1040 260 1200 330 L1200 520 L0 520 Z" fill="#3A4A5A" opacity="0.8"/>'
    houses = ""
    x = -20
    while x < W:
        w = rng.randint(110, 190)
        h = rng.randint(110, 190)
        y = 600 - h
        houses += (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#4A3426"/>'
                   f'<path d="M{x - 14} {y + 4} L{x + w / 2} {y - 40} L{x + w + 14} {y + 4} Z" fill="#2A2226"/>')
        for k in range(rng.randint(1, 3)):
            houses += f'<rect x="{x + 14 + k * 46}" y="{y + 30}" width="34" height="28" fill="#FFCF7A" opacity="0.9"/>'
        x += w + rng.randint(4, 20)
    steam = "".join(f'<path d="M{x} 600 Q{x - 50} 470 {x + 20} 360 Q{x + 90} 260 {x + 10} 140" stroke="#FFFFFF" stroke-width="{rng.randint(70, 120)}" fill="none" opacity="0.4" stroke-linecap="round"/>'
                    for x in (180, 470, 760, 1030))
    body = (
        defs + f'<rect width="{W}" height="{H}" fill="url(#sky)"/>' + f'<g filter="url(#b6)">{hills}</g>'
        + f'<g filter="url(#b2)">{houses}</g>'
        + '<rect y="600" width="1200" height="200" fill="#3E5A6A"/>'
        + '<path d="M300 640 Q600 590 900 640 L900 652 Q600 602 300 652 Z" fill="#6A3A2A"/>'
        + "".join(f'<rect x="{x}" y="{610 + abs(600 - x) * 0.06:.0f}" width="6" height="40" fill="#6A3A2A"/>' for x in range(320, 900, 60))
        + _bokeh(rng, 30, (0, 600, W, 800), ["#FFCF7A", "#FFE6B0"], 4, 14)
        + f'<g filter="url(#steam)">{steam}</g>'
        + _finish()
    )
    return _svg("湯けむりの温泉街", body)


# ------------------------------------------------------------------------- 5. 港のれんが倉庫
def harbor() -> str:
    rng = random.Random(5)
    defs = _common_defs(
        '<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7EC1F0"/><stop offset="1" stop-color="#FFF1DA"/></linearGradient>'
        '<linearGradient id="sea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4E96C8"/><stop offset="1" stop-color="#1E4E72"/></linearGradient>'
        '<pattern id="brick" width="24" height="12" patternUnits="userSpaceOnUse"><rect width="24" height="12" fill="#A2442E"/>'
        '<path d="M0 0 H24 M0 6 H24 M6 0 V6 M18 6 V12" stroke="#7E3020" stroke-width="1"/></pattern>'
    )
    warehouses = ""
    for i, (x, w) in enumerate(((60, 420), (520, 380), (940, 300))):
        y = 300 + i * 12
        warehouses += (f'<rect x="{x}" y="{y}" width="{w}" height="{560 - y}" fill="url(#brick)"/>'
                       f'<path d="M{x - 10} {y} L{x + w / 2} {y - 60} L{x + w + 10} {y} Z" fill="#5A5E66"/>')
        for k in range(int(w // 70)):
            wx = x + 22 + k * 70
            warehouses += (f'<path d="M{wx} {y + 120} L{wx} {y + 70} Q{wx + 18} {y + 50} {wx + 36} {y + 70} L{wx + 36} {y + 120} Z" fill="#2E3A44"/>'
                           f'<rect x="{wx}" y="{y + 160}" width="36" height="60" fill="#2E3A44"/>')
    gulls = "".join(f'<path d="M{x} {y} q12 -10 24 0 q12 -10 24 0" stroke="#FFFFFF" stroke-width="4" fill="none"/>'
                    for x, y in ((240, 160), (330, 120), (820, 190), (900, 150)))
    waves = "".join(f'<path d="M{x} {y} q30 -8 60 0" stroke="#FFFFFF" stroke-width="3" fill="none" opacity="{rng.uniform(.3, .7):.2f}"/>'
                    for x, y in ((rng.randint(0, 1140), rng.randint(600, 790)) for _ in range(40)))
    body = (
        defs + f'<rect width="{W}" height="{H}" fill="url(#sky)"/>'
        + '<g filter="url(#b14)" opacity="0.8"><ellipse cx="300" cy="100" rx="220" ry="30" fill="#FFFFFF"/><ellipse cx="950" cy="140" rx="180" ry="26" fill="#FFFFFF"/></g>'
        + '<path d="M1080 120 L1100 560 L1112 560 L1094 120 Z M1094 130 L1190 180" stroke="#C0392B" stroke-width="8" fill="none" filter="url(#b2)"/>'
        + f'<g filter="url(#b2)">{warehouses}</g>'
        + '<rect y="560" width="1200" height="40" fill="#8A8A86"/>'
        + '<rect y="600" width="1200" height="200" fill="url(#sea)"/>'
        + f'<g filter="url(#b2)">{waves}</g>' + gulls
        + _finish()
    )
    return _svg("港のれんが倉庫", body)


PHOTOS = {
    "riverside": riverside,
    "castle": castle,
    "lantern": lantern_alley,
    "onsen": onsen,
    "harbor": harbor,
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in PHOTOS.items():
        path = OUT / f"{name}.svg"
        path.write_text(fn(), encoding="utf-8")
        print(f"{path.name}: {path.stat().st_size // 1024} KB")

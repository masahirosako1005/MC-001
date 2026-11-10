"""分析画面の棒グラフ (サーバーで SVG を組み立てる)。

- CSP (script-src 'self'・インラインスタイル不可) のまま描けるよう、外部ライブラリや JS は使わない
- 色は CSS のクラス (.series-1〜3) で付け、ライト/ダーク表示はスタイルシート側で切り替える
- 各棒に <title> を付け、マウスを乗せると値が出る。表 (テーブル) でも同じ値を確認できる
- 文字はすべてエスケープする (スポット名などは管理者が入力した値)
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

from django.utils.safestring import mark_safe

FONT = 12


def _esc(s) -> str:
    return escape(str(s), {'"': "&quot;"})


def _nice_max(v: float) -> float:
    if v <= 0:
        return 1
    exp = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * exp:
            return m * exp
    return 10 * exp


def _ticks(vmax: float, n: int = 4) -> list[float]:
    step = vmax / n
    return [step * i for i in range(n + 1)]


def _fmt(v: float, unit: str = "") -> str:
    if unit == "%":
        return f"{v:.0f}%"
    return f"{int(v):,}" if float(v).is_integer() else f"{v:,.1f}"


def _truncate(label: str, n: int) -> str:
    return label if len(label) <= n else label[: n - 1] + "…"


def grouped_hbar(rows: list[dict], series: list[tuple[str, str]], *, title: str, label_key: str = "label",
                 label_chars: int = 12, width: int = 720, unit: str = "人") -> str:
    """横向きのグループ棒グラフ (行 = スポット、棒 = 段階)。series は (値のキー, 表示名)。"""
    bar_h, gap, group_gap = 9, 2, 14
    group_h = len(series) * bar_h + (len(series) - 1) * gap
    left, right, top = label_chars * FONT + 16, 24, 28
    plot_w = width - left - right
    height = top + len(rows) * (group_h + group_gap) + 8
    vmax = _nice_max(max((r[k] or 0) for r in rows for k, _ in series) if rows else 0)
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" width="100%" role="img" '
             f'aria-label="{_esc(title)}" xmlns="http://www.w3.org/2000/svg">']
    for t in _ticks(vmax):
        x = left + plot_w * t / vmax
        parts.append(f'<line class="chart-grid" x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" y2="{height - 6}"/>')
        parts.append(f'<text class="chart-tick" x="{x:.1f}" y="{top - 12}" text-anchor="middle">{_fmt(t)}</text>')
    for i, r in enumerate(rows):
        y0 = top + i * (group_h + group_gap)
        label = str(r[label_key])
        parts.append(f'<text class="chart-label" x="{left - 8}" y="{y0 + group_h / 2 + 4:.1f}" text-anchor="end">'
                     f'<title>{_esc(label)}</title>{_esc(_truncate(label, label_chars))}</text>')
        for j, (key, name) in enumerate(series):
            v = r[key] or 0
            w = max(plot_w * v / vmax, 0)
            y = y0 + j * (bar_h + gap)
            # 端を 4px 丸めた棒 (基準線側は四角)
            rr = min(4, w / 2, bar_h / 2)
            path = (f"M{left},{y} H{left + w - rr:.1f} Q{left + w:.1f},{y} {left + w:.1f},{y + rr:.1f} "
                    f"V{y + bar_h - rr:.1f} Q{left + w:.1f},{y + bar_h} {left + w - rr:.1f},{y + bar_h} H{left} Z")
            parts.append(f'<path class="chart-bar series-{j + 1}" d="{path}"><title>{_esc(label)} ・ {_esc(name)}: '
                         f'{_fmt(v)} {_esc(unit)}</title></path>')
            # 1 本目の系列 (分析では「付近に来た人」) だけ数値を添える (すべてに数値を付けると読みにくい)
            if j == 0 and v:
                parts.append(f'<text class="chart-value" x="{left + w + 4:.1f}" y="{y + bar_h - 1}">{_fmt(v)}</text>')
    parts.append(f'<line class="chart-axis" x1="{left}" y1="{top - 6}" x2="{left}" y2="{height - 6}"/>')
    parts.append("</svg>")
    return mark_safe("".join(parts))


def grouped_vbar(rows: list[dict], series: list[tuple[str, str]], *, title: str, width: int = 360,
                 height: int = 220, unit: str = "人") -> str:
    """縦向きのグループ棒グラフ (時間帯・季節ごと)。"""
    left, right, top, bottom = 44, 8, 12, 28
    plot_w, plot_h = width - left - right, height - top - bottom
    n = max(len(rows), 1)
    slot_w = plot_w / n
    bar_w = min(16, (slot_w - 16) / len(series) - 2)
    vmax = _nice_max(max((r[k] or 0) for r in rows for k, _ in series) if rows else 0)
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" width="100%" role="img" '
             f'aria-label="{_esc(title)}" xmlns="http://www.w3.org/2000/svg">']
    for t in _ticks(vmax):
        y = top + plot_h - plot_h * t / vmax
        parts.append(f'<line class="chart-grid" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>')
        parts.append(f'<text class="chart-tick" x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{_fmt(t)}</text>')
    for i, r in enumerate(rows):
        group_w = len(series) * bar_w + (len(series) - 1) * 2
        x0 = left + i * slot_w + (slot_w - group_w) / 2
        for j, (key, name) in enumerate(series):
            v = r[key] or 0
            h = plot_h * v / vmax
            x = x0 + j * (bar_w + 2)
            y = top + plot_h - h
            rr = min(4, h / 2, bar_w / 2)
            path = (f"M{x:.1f},{top + plot_h} V{y + rr:.1f} Q{x:.1f},{y:.1f} {x + rr:.1f},{y:.1f} "
                    f"H{x + bar_w - rr:.1f} Q{x + bar_w:.1f},{y:.1f} {x + bar_w:.1f},{y + rr:.1f} "
                    f"V{top + plot_h} Z")
            parts.append(f'<path class="chart-bar series-{j + 1}" d="{path}"><title>{_esc(r["label"])} ・ '
                         f'{_esc(name)}: {_fmt(v)} {_esc(unit)}</title></path>')
        parts.append(f'<text class="chart-label" x="{left + i * slot_w + slot_w / 2:.1f}" y="{height - 8}" '
                     f'text-anchor="middle">{_esc(r["label"])}</text>')
    parts.append(f'<line class="chart-axis" x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}"/>')
    parts.append("</svg>")
    return mark_safe("".join(parts))


def rate_vbar(rows: list[dict], *, key: str, title: str, width: int = 360, height: int = 200) -> str:
    """割合 (%) の棒グラフ (1 系列なので値を直接書く)。"""
    left, right, top, bottom = 40, 8, 18, 28
    plot_w, plot_h = width - left - right, height - top - bottom
    n = max(len(rows), 1)
    slot_w = plot_w / n
    bar_w = min(28, slot_w - 20)
    vmax = _nice_max(max((r[key] or 0) for r in rows) if rows else 0)
    vmax = min(100, vmax) if vmax <= 100 else vmax
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" width="100%" role="img" '
             f'aria-label="{_esc(title)}" xmlns="http://www.w3.org/2000/svg">']
    for t in _ticks(vmax):
        y = top + plot_h - plot_h * t / vmax
        parts.append(f'<line class="chart-grid" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>')
        parts.append(f'<text class="chart-tick" x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{_fmt(t, "%")}</text>')
    for i, r in enumerate(rows):
        v = r[key]
        cx = left + i * slot_w + slot_w / 2
        if v is not None:
            h = plot_h * v / vmax
            x, y = cx - bar_w / 2, top + plot_h - h
            rr = min(4, h / 2, bar_w / 2)
            path = (f"M{x:.1f},{top + plot_h} V{y + rr:.1f} Q{x:.1f},{y:.1f} {x + rr:.1f},{y:.1f} "
                    f"H{x + bar_w - rr:.1f} Q{x + bar_w:.1f},{y:.1f} {x + bar_w:.1f},{y + rr:.1f} "
                    f"V{top + plot_h} Z")
            parts.append(f'<path class="chart-bar series-3" d="{path}"><title>{_esc(r["label"])}: {v}%</title></path>')
            parts.append(f'<text class="chart-value" x="{cx:.1f}" y="{y - 4:.1f}" text-anchor="middle">{v}%</text>')
        else:
            parts.append(f'<text class="chart-tick" x="{cx:.1f}" y="{top + plot_h - 4}" text-anchor="middle">—</text>')
        parts.append(f'<text class="chart-label" x="{cx:.1f}" y="{height - 8}" text-anchor="middle">{_esc(r["label"])}</text>')
    parts.append(f'<line class="chart-axis" x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}"/>')
    parts.append("</svg>")
    return mark_safe("".join(parts))

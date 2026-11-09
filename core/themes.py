"""UI テーマ (デザイン案) の定義。管理画面の「サイト設定」で切り替える。

各テーマは
- 全ページ共通の CSS (static/css/themes/<key>.css。standard は追加 CSS なし)
- ログイン前トップ (templates/core/landing_<variant>.html)
- ログイン後ホーム (templates/core/home_<variant>.html)
の組み合わせ。新しい案は THEMES に 1 行足し、CSS とテンプレートを用意すれば追加できる。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    description: str
    css: str | None  # static/css/themes/ 配下のファイル名
    landing: str     # templates/core/landing_<landing>.html
    home: str        # templates/core/home_<home>.html


THEMES: dict[str, Theme] = {t.key: t for t in [
    Theme("standard", "A. スタンダード",
          "現在のデザイン。カードを縦に並べた、読みやすくて迷わない構成。", None, "standard", "standard"),
    Theme("game", "B. ゲームホーム(1画面完結)",
          "スマホゲームのホーム画面のように、ステータス・アバター・主要ボタンを 1 画面にまとめた案。"
          "ログイン前はタイトル画面風。", "game.css", "game", "game"),
    Theme("magazine", "C. トラベルマガジン",
          "大きな写真と明朝体の見出しで、旅行雑誌のように見せる案。写真で行きたくなる気持ちを高める。",
          "magazine.css", "magazine", "magazine"),
    Theme("wa", "D. 和モダン",
          "藍色と朱色、青海波の模様を使った和の雰囲気の案。構成はスタンダードと同じで、見た目だけを変える。",
          "wa.css", "standard", "standard"),
]}
DEFAULT_THEME = "standard"
THEME_CHOICES = [(t.key, t.label) for t in THEMES.values()]


def get_theme(key: str | None) -> Theme:
    return THEMES.get(key or "", THEMES[DEFAULT_THEME])

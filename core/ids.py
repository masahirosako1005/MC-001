"""人が読み書きする ID (管理者 ID・クーポン ID・引換コード) の生成。

読み間違えやすい文字 (0/O, 1/I/L) を除いた英数字 31 種類を使う。
"""

from __future__ import annotations

import secrets

ID_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def random_code(length: int) -> str:
    return "".join(secrets.choice(ID_ALPHABET) for _ in range(length))


def unique_code(make, exists, attempts: int = 10) -> str:
    """make() で作った値のうち、exists(値) が False のものを返す (衝突したら作り直す)。"""
    for _ in range(attempts):
        value = make()
        if not exists(value):
            return value
    raise RuntimeError("重ならない ID を作れませんでした。")

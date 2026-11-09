"""キャッシュを使った簡易レート制限 (固定ウィンドウ)。"""

from __future__ import annotations

from django.core.cache import cache


def hit(key: str, limit: int, window_seconds: int) -> bool:
    """1 回分カウントし、上限以内なら True を返す。"""
    cache_key = f"rl:{key}"
    if cache.add(cache_key, 1, timeout=window_seconds):
        return True
    try:
        count = cache.incr(cache_key)
    except ValueError:  # 期限切れと競合した場合
        cache.set(cache_key, 1, timeout=window_seconds)
        return True
    return count <= limit


def count(key: str) -> int:
    return int(cache.get(f"rl:{key}", 0))


def reset(key: str) -> None:
    cache.delete(f"rl:{key}")

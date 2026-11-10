"""数値の表示 (3 桁区切り)。"""

from django import template

register = template.Library()


@register.filter
def num(value):
    """1234567 → 1,234,567。数値でなければそのまま返す。"""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return value

from __future__ import annotations

from django.conf import settings

from .themes import THEMES, get_theme
from .timeutil import SEASON_LABELS, SLOT_LABELS, local_now, season_of, slot_of


def mikke(request):
    now = local_now()
    season, slot = season_of(now.date()), slot_of(now)
    return {
        # DEBUG のまま公開すると 404 ページなどで内部の URL 構成が見えてしまうため、画面に警告を出す
        "mikke_debug": settings.DEBUG,
        "mikke_season": season,
        "mikke_season_label": SEASON_LABELS[season],
        "mikke_slot": slot,
        "mikke_slot_label": SLOT_LABELS[slot],
        "ui_theme": getattr(request, "ui_theme", None) or get_theme(None),
        "ui_previewing": getattr(request, "ui_previewing", False),
        "ui_themes": THEMES.values(),
    }

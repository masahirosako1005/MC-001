from __future__ import annotations

from .timeutil import SEASON_LABELS, SLOT_LABELS, local_now, season_of, slot_of


def mikke(request):
    now = local_now()
    season, slot = season_of(now.date()), slot_of(now)
    return {
        "mikke_season": season,
        "mikke_season_label": SEASON_LABELS[season],
        "mikke_slot": slot,
        "mikke_slot_label": SLOT_LABELS[slot],
    }

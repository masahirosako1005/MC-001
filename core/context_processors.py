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
        "ui_themes": THEMES.values(),
    }


def console(request):
    """管理者・サイト運営者の画面 (コンソール) か、利用者の画面か。

    - console_role: "operator" (運営側の URL) / "manager" (管理者がログイン中) / None (利用者の画面)
    - base_template: 共通の画面 (パスワード変更など) が継承する土台のテンプレート
    """
    from .sessions import REALM_OPS

    user = getattr(request, "user", None)
    if getattr(request, "session_realm", None) == REALM_OPS:
        role = "operator"
    elif user is not None and user.is_authenticated and user.is_manager:
        role = "manager"
    else:
        role = None
    from .console import nav_for

    return {"console_role": role, "base_template": "console/base.html" if role else "base.html",
            "console_nav": nav_for(request, role)}

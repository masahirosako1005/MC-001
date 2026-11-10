"""管理者・サイト運営者の画面 (コンソール) の左メニュー。

利用者の画面 (base.html) とは別のメニューで、利用者の機能 (きせかえ・みっけ・コンテストなど) へのリンクは置かない。
"""

from __future__ import annotations

from django.urls import NoReverseMatch, reverse


def _item(current: str, label: str, view: str, *, also: tuple[str, ...] = (), post: bool = False) -> dict | None:
    try:
        url = reverse(view)
    except NoReverseMatch:
        return None
    return {"label": label, "url": url, "active": current == view or current in also, "post": post}


def _groups(current: str, spec) -> list[dict]:
    groups = []
    for title, items in spec:
        built = [i for i in (_item(current, *args, **kw) for args, kw in items) if i]
        if built:
            groups.append({"title": title, "items": built})
    return groups


def manager_nav(current: str) -> list[dict]:
    return _groups(current, [
        ("", [(("ホーム", "manage:home"), {})]),
        ("スポット・シンボル", [
            (("スポット", "manage:spots"), {"also": ("manage:spot_create", "manage:spot_edit", "manage:spot_delete")}),
            (("シンボル一覧", "manage:symbols"), {"also": ("manage:symbol_edit", "manage:symbol_views")}),
            (("QR シンボルを追加", "manage:symbol_create"), {}),
            (("画像シンボルを登録", "manage:symbol_register"), {}),
        ]),
        ("クーポン", [
            (("クーポンの登録・編集", "manage:coupons"), {"also": ("manage:coupon_create", "manage:coupon_edit")}),
            (("クーポンの実績", "manage:coupon_stats"), {}),
        ]),
        ("アカウント", [
            (("店舗・会社の情報", "manage:account"), {}),
            (("パスワードの変更", "accounts:password_change"), {}),
            (("ログアウト", "accounts:logout"), {"post": True}),
        ]),
    ])


def operator_nav(current: str) -> list[dict]:
    return _groups(current, [
        ("分析", [
            (("利用状況", "ops:dashboard"), {}),
            (("店舗ごとのクーポン利用", "ops:coupons"), {"also": ("ops_manage:coupon_stats",)}),
        ]),
        ("利用者", [
            (("利用者管理", "ops:users"), {"also": ("ops:manager_edit", "ops:user_reset_password",
                                                  "ops:manager_reset_password")}),
            (("管理者を追加", "ops:manager_create"), {}),
        ]),
        ("設定", [
            (("スポット", "ops_manage:spots"), {"also": ("ops_manage:spot_create", "ops_manage:spot_edit",
                                                      "ops_manage:spot_delete")}),
            (("シンボル一覧", "ops_manage:symbols"), {"also": ("ops_manage:symbol_edit", "ops_manage:symbol_views",
                                                         "ops_manage:symbol_create", "ops_manage:symbol_register")}),
            (("クーポン", "ops_manage:coupons"), {"also": ("ops_manage:coupon_create", "ops_manage:coupon_edit")}),
            (("アイテム一覧", "ops:item_catalog"), {}),
            (("サイト設定(管理画面)", "admin:index"), {}),
        ]),
        ("アカウント", [
            (("パスワードの変更", "ops:password_change"), {}),
            (("ログアウト", "ops:logout"), {"post": True}),
        ]),
    ])


def nav_for(request, role: str | None) -> list[dict]:
    user = getattr(request, "user", None)
    if not role or user is None or not user.is_authenticated:
        return []
    match = getattr(request, "resolver_match", None)
    current = match.view_name if match else ""
    return operator_nav(current) if role == "operator" else manager_nav(current)

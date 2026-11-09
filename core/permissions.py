"""権限 (利用者 / 管理者 / サイト運営者) の確認。

- manager_required: スポット・シンボルの設定画面。管理者 (自分のスポットだけ) とサイト運営者 (すべて)
- operator_required: 利用者管理・分析画面。サイト運営者だけ。それ以外のログイン中の人には 404 を返して画面の存在を隠す
"""

from __future__ import annotations

from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse


def manager_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        if not user.can_manage_spots:
            raise PermissionDenied("スポット・シンボルの設定は、管理者とサイト運営者だけが使えます。")
        return view(request, *args, **kwargs)

    return wrapper


def operator_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect(f"{reverse('ops:login')}?{urlencode({'next': request.get_full_path()})}")
        if not (user.is_active and user.is_operator):
            raise Http404
        return view(request, *args, **kwargs)

    return wrapper


def managed_spots(user):
    """この人が設定できるスポット。サイト運営者はすべて、管理者は自分が担当のスポットだけ。"""
    from explore.models import Spot

    if getattr(user, "is_operator", False):
        return Spot.objects.all()
    if getattr(user, "is_manager", False):
        return Spot.objects.filter(owner=user)
    return Spot.objects.none()


def managed_symbols(user):
    from explore.models import Symbol

    return Symbol.objects.filter(spot__in=managed_spots(user))


def managed_coupons(user):
    """この人が設定できるクーポン。サイト運営者はすべて、管理者は自分が登録したもの・担当スポットのもの。"""
    from django.db.models import Q

    from rewards.models import CouponTemplate

    if getattr(user, "is_operator", False):
        return CouponTemplate.objects.all()
    if getattr(user, "is_manager", False):
        return CouponTemplate.objects.filter(Q(owner=user) | Q(spot__owner=user)).distinct()
    return CouponTemplate.objects.none()

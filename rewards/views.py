from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from core import audit

from .models import UserCoupon
from .services import CouponUnavailable, achievement_progress, use_coupon


@login_required
@require_GET
def coupon_list(request):
    coupons = list(UserCoupon.objects.select_related("template", "template__spot").filter(user=request.user))
    order = {"available": 0, "used": 1, "expired": 2}
    coupons.sort(key=lambda c: (order[c.status], c.expires_at))
    return render(request, "rewards/coupons.html", {"coupons": coupons})


@login_required
@require_GET
def coupon_detail(request, pk):
    # IDOR 対策: 必ず所有者で絞り込む
    coupon = get_object_or_404(UserCoupon.objects.select_related("template"), pk=pk, user=request.user)
    return render(request, "rewards/coupon_detail.html", {"coupon": coupon})


@login_required
@require_POST
def coupon_use(request, pk):
    coupon = get_object_or_404(UserCoupon, pk=pk, user=request.user)
    already = coupon.used_at is not None
    try:
        use_coupon(coupon)
    except CouponUnavailable as exc:
        messages.error(request, str(exc))
    else:
        if not already:
            audit.record("coupon.use", request=request, target=coupon, template=coupon.template_id)
            messages.success(request, "クーポンを使用済みにしました。お店の方にこの画面を見せてください。")
    return redirect("rewards:coupon_detail", pk=coupon.pk)


@login_required
@require_GET
def achievements(request):
    rows = achievement_progress(request.user)
    return render(request, "rewards/achievements.html", {
        "rows": rows,
        "achieved_count": sum(1 for r in rows if r["achieved"]),
    })

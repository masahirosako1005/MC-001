from __future__ import annotations

from django.shortcuts import render
from django.views.decorators.http import require_GET

from explore.models import Discovery, Spot
from rewards.models import UserCoupon
from rewards.services import metrics_for


@require_GET
def home(request):
    if not request.user.is_authenticated:
        return render(request, "core/landing.html", {"spots": Spot.objects.filter(is_active=True)[:6]})
    user = request.user
    available_coupons = [c for c in UserCoupon.objects.filter(user=user, used_at__isnull=True).select_related("template")
                         if c.status == "available"]
    return render(request, "core/home.html", {
        "metrics": metrics_for(user),
        "recent": Discovery.objects.filter(user=user).select_related("symbol__spot")[:5],
        "coupon_count": len(available_coupons),
    })

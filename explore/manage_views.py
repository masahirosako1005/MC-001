"""運営スタッフ用: シンボルを置くスポットの追加・編集・削除。"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from core import audit

from .forms import SpotForm
from .models import Discovery, Spot, SpotVisit, Symbol
from .views import _map_context


def deletion_blockers(spot: Spot) -> list[str]:
    """削除すると記録が失われる場合の理由。空なら削除してよい。"""
    reasons = []
    if SpotVisit.objects.filter(spot=spot).exists():
        reasons.append("利用者の訪問記録があります")
    if Discovery.objects.filter(symbol__spot=spot).exists():
        reasons.append("このスポットのシンボルで、みっけした記録があります")
    return reasons


@staff_member_required
@require_GET
def spot_list(request):
    spots = Spot.objects.annotate(
        n_symbols=Count("symbols", distinct=True),
        n_secret=Count("symbols", filter=Q(symbols__is_secret=True), distinct=True),
    ).order_by("-is_active", "id")
    return render(request, "explore/manage/spot_list.html", {"spots": spots})


def _edit(request, spot: Spot | None):
    form = SpotForm(request.POST or None, instance=spot)
    if request.method == "POST" and form.is_valid():
        created = spot is None
        saved = form.save()
        audit.record("spot.create" if created else "spot.update", request=request, target=saved,
                     expires_at=saved.expires_at.isoformat() if saved.expires_at else None)
        messages.success(request, f"スポット「{saved.name}」を{'追加' if created else '更新'}しました。")
        return redirect("explore:manage_spots")
    symbols = Symbol.objects.filter(spot=spot).order_by("pk") if spot else []
    return render(request, "explore/manage/spot_form.html",
                  {"form": form, "spot": spot, "symbols": symbols, **_map_context()})


@staff_member_required
@require_http_methods(["GET", "POST"])
def spot_create(request):
    return _edit(request, None)


@staff_member_required
@require_http_methods(["GET", "POST"])
def spot_edit(request, pk: int):
    return _edit(request, get_object_or_404(Spot, pk=pk))


@staff_member_required
@require_http_methods(["GET", "POST"])
def spot_delete(request, pk: int):
    spot = get_object_or_404(Spot, pk=pk)
    blockers = deletion_blockers(spot)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete" and not blockers:
            name = spot.name
            with transaction.atomic():
                audit.record("spot.delete", request=request, target=spot, name=name,
                             symbols=list(spot.symbols.values_list("pk", flat=True)))
                Symbol.objects.filter(spot=spot).delete()  # ドロップ設定・画像の見え方も一緒に消える
                spot.delete()
            messages.success(request, f"スポット「{name}」を削除しました。")
            return redirect("explore:manage_spots")
        if action == "hide":
            spot.is_active = False
            spot.save(update_fields=["is_active"])
            audit.record("spot.hide", request=request, target=spot)
            messages.success(request, f"スポット「{spot.name}」を非公開にしました。記録はそのまま残ります。")
            return redirect("explore:manage_spots")
        if action == "expire":
            now = timezone.now()
            if spot.starts_at and spot.starts_at >= now:
                spot.starts_at = None
            spot.expires_at = now
            spot.save(update_fields=["expires_at", "starts_at"])
            audit.record("spot.expire", request=request, target=spot)
            messages.success(request, f"スポット「{spot.name}」を今すぐ期限切れにしました。")
            return redirect("explore:manage_spots")
        messages.error(request, "このスポットは削除できません。非公開か期限切れにしてください。")
    return render(request, "explore/manage/spot_delete.html", {
        "spot": spot, "blockers": blockers, "symbols": spot.symbols.all(),
    })

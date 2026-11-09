"""スポット・シンボルの設定画面 (管理者とサイト運営者)。

- 管理者 (店舗・会社の担当者) は、自分が担当のスポットとそのシンボルだけを扱える
- サイト運営者は、すべてのスポットを扱え、担当の管理者を割り当てられる
"""

from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core import audit
from core.permissions import managed_coupons, managed_spots, managed_symbols, manager_required
from rewards.models import CouponTemplate, distributable_coupons_q

from . import services
from .forms import CouponForm, DropFormSet, SpotForm, SymbolSettingsForm
from .models import Discovery, NearbyVisit, Spot, SpotVisit, Symbol
from .views import _map_context


def deletion_blockers(spot: Spot) -> list[str]:
    """削除すると記録が失われる場合の理由。空なら削除してよい。"""
    reasons = []
    if SpotVisit.objects.filter(spot=spot).exists():
        reasons.append("利用者の訪問記録があります")
    if Discovery.objects.filter(symbol__spot=spot).exists():
        reasons.append("このスポットのシンボルで、みっけした記録があります")
    return reasons


@manager_required
@require_GET
def spot_list(request):
    spots = managed_spots(request.user).select_related("owner__manager_profile").annotate(
        n_symbols=Count("symbols", distinct=True),
        n_secret=Count("symbols", filter=Q(symbols__is_secret=True), distinct=True),
    ).order_by("-is_active", "id")
    return render(request, "explore/manage/spot_list.html", {"spots": spots})


def _edit(request, spot: Spot | None):
    form = SpotForm(request.POST or None, instance=spot, user=request.user)
    if request.method == "POST" and form.is_valid():
        created = spot is None
        saved = form.save()
        audit.record("spot.create" if created else "spot.update", request=request, target=saved,
                     owner=saved.owner_id, expires_at=saved.expires_at.isoformat() if saved.expires_at else None)
        messages.success(request, f"スポット「{saved.name}」を{'追加' if created else '更新'}しました。")
        return redirect("explore:manage_spots")
    symbols = Symbol.objects.filter(spot=spot).order_by("pk") if spot else []
    return render(request, "explore/manage/spot_form.html",
                  {"form": form, "spot": spot, "symbols": symbols, **_map_context()})


@manager_required
@require_http_methods(["GET", "POST"])
def spot_create(request):
    return _edit(request, None)


@manager_required
@require_http_methods(["GET", "POST"])
def spot_edit(request, pk: int):
    return _edit(request, get_object_or_404(managed_spots(request.user), pk=pk))


@manager_required
@require_http_methods(["GET", "POST"])
def spot_delete(request, pk: int):
    spot = get_object_or_404(managed_spots(request.user), pk=pk)
    blockers = deletion_blockers(spot)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete" and not blockers:
            name = spot.name
            with transaction.atomic():
                audit.record("spot.delete", request=request, target=spot, name=name,
                             symbols=list(spot.symbols.values_list("pk", flat=True)))
                NearbyVisit.objects.filter(spot=spot).delete()
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


# ---------------------------------------------------------------- シンボルの設定
def _coupons_for(user, symbol: Symbol | None = None):
    """ドロップに使えるクーポン。管理者は自分のクーポンだけ。配布停止・期限切れは新しくは選べない。

    ただし、このシンボルのドロップにすでに設定されているクーポンは (配布停止・期限切れ・ほかの登録者の
    ものでも) 選択肢に残す。残さないと既存の行が「正しく選択してください」になり、設定全体が保存できなくなる。
    """
    selectable = managed_coupons(user).filter(distributable_coupons_q()).values("pk")
    cond = Q(pk__in=selectable)
    if symbol is not None and symbol.pk:
        cond |= Q(pk__in=symbol.drops.filter(coupon__isnull=False).values("coupon_id"))
    return CouponTemplate.objects.filter(cond).order_by("shop_name", "title")


def _symbol_form(request, symbol: Symbol | None, initial_spot: int | None = None):
    spots = managed_spots(request.user)
    form = SymbolSettingsForm(request.POST or None, instance=symbol, spots=spots,
                              initial={"spot": initial_spot} if initial_spot else None)
    drops = DropFormSet(request.POST or None, instance=symbol or Symbol(),
                        form_kwargs={"coupons": _coupons_for(request.user, symbol)}, prefix="drops")
    if request.method == "POST" and form.is_valid() and drops.is_valid():
        created = symbol is None
        with transaction.atomic():
            saved = form.save()  # 新規はここで QR シンボルになる (画像シンボルは撮影画面から登録)
            drops.instance = saved
            drops.save()
        audit.record("symbol.create" if created else "symbol.update", request=request, target=saved,
                     spot=saved.spot_id, secret=saved.is_secret, drops=saved.drops.count())
        messages.success(request, f"シンボル「{saved.name}」を{'追加' if created else '保存'}しました。")
        return redirect("explore:manage_symbol_edit", pk=saved.pk)
    return render(request, "explore/manage/symbol_form.html", {
        "form": form, "drops": drops, "symbol": symbol, "is_new": symbol is None,
    })


@manager_required
@require_http_methods(["GET", "POST"])
def symbol_create(request):
    spot = request.GET.get("spot")
    return _symbol_form(request, None, int(spot) if spot and spot.isdigit() else None)


@manager_required
@require_http_methods(["GET", "POST"])
def symbol_edit(request, pk: int):
    return _symbol_form(request, get_object_or_404(managed_symbols(request.user).select_related("spot"), pk=pk))


@manager_required
@require_POST
def symbol_regenerate_token(request, pk: int):
    """QR シンボルの識別トークンを作り直す (掲示物を差し替えるとき。古い QR は使えなくなる)。"""
    symbol = get_object_or_404(managed_symbols(request.user).select_related("spot"), pk=pk, kind=Symbol.KIND_QR)
    services.regenerate_token(symbol)
    audit.record("symbol.token_regenerate", request=request, target=symbol, spot=symbol.spot_id)
    messages.success(request, f"「{symbol.name}」の QR を作り直しました。新しい印刷用 SVG を掲示してください (古い QR は使えません)。")
    return redirect("explore:manage_symbol_edit", pk=symbol.pk)


# ---------------------------------------------------------------- クーポンの登録
@manager_required
@require_GET
def coupon_list(request):
    coupons = managed_coupons(request.user).select_related("spot", "owner__manager_profile").annotate(
        n_issued=Count("issued", distinct=True),
        n_used=Count("issued", filter=Q(issued__used_at__isnull=False), distinct=True),
        n_drops=Count("drop_entries", distinct=True),
    ).order_by("-is_active", "-created_at")
    return render(request, "explore/manage/coupon_list.html", {"coupons": coupons})


def _coupon_form(request, coupon):
    form = CouponForm(request.POST or None, instance=coupon, user=request.user, spots=managed_spots(request.user))
    if request.method == "POST" and form.is_valid():
        created = coupon is None
        saved = form.save()
        audit.record("coupon.create" if created else "coupon.update", request=request, target=saved,
                     coupon_id=saved.coupon_id, available_until=saved.available_until.isoformat()
                     if saved.available_until else None, active=saved.is_active)
        messages.success(request, f"クーポン「{saved.title}」({saved.coupon_id})を{'登録' if created else '保存'}しました。"
                         + ("シンボルの設定で「手に入るもの」に追加すると配布されます。" if created else ""))
        return redirect("explore:manage_coupons")
    stats = None
    if coupon is not None:
        issued = coupon.issued.all()
        stats = {"issued": issued.count(), "used": issued.filter(used_at__isnull=False).count(),
                 "drops": coupon.drop_entries.select_related("symbol__spot")}
    return render(request, "explore/manage/coupon_form.html", {"form": form, "coupon": coupon, "stats": stats})


@manager_required
@require_http_methods(["GET", "POST"])
def coupon_create(request):
    return _coupon_form(request, None)


@manager_required
@require_http_methods(["GET", "POST"])
def coupon_edit(request, pk: int):
    return _coupon_form(request, get_object_or_404(managed_coupons(request.user), pk=pk))

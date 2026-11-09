from __future__ import annotations

import json
import logging
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core import audit, ratelimit

from . import services
from .forms import ImageSymbolInfoForm, collect_view_uploads
from .image_symbols import ImageSymbolError
from .models import ANGLE_CHOICES, Discovery, Spot, SpotVisit, Symbol, SymbolView
from .symbols import render_symbol_svg

logger = logging.getLogger("mikke.explore")


def api_login_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "login_required", "message": "ログインしてください。"}, status=401)
        return view(request, *args, **kwargs)

    return wrapper


def _json_body(request) -> dict:
    if request.content_type != "application/json":
        raise ValueError("content-type")
    data = json.loads(request.body or b"{}")
    if not isinstance(data, dict):
        raise ValueError("body")
    return data


def _error(exc: services.ExploreError, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": exc.code, "message": exc.message, **exc.extra}, status=status)


@login_required
@require_GET
def spot_list(request):
    user = request.user
    spots = list(Spot.objects.filter(is_active=True).prefetch_related("symbols"))
    visit_days = dict(SpotVisit.objects.filter(user=user).values_list("spot").annotate(n=Count("id")))
    last_found = dict(Discovery.objects.filter(user=user).values_list("symbol").annotate(m=Max("found_at")))
    now = timezone.now()
    rows = []
    for spot in spots:
        symbols = []
        for s in spot.symbols.all():
            if not s.is_active:
                continue
            last = last_found.get(s.pk)
            nxt = last + timezone.timedelta(hours=s.cooldown_hours) if last else None
            symbols.append({"symbol": s, "found": last is not None, "next_at": nxt if nxt and nxt > now else None})
        rows.append({"spot": spot, "visit_days": visit_days.get(spot.pk, 0), "symbols": symbols})
    points = [
        {"id": r["spot"].pk, "name": r["spot"].name, "area": r["spot"].area,
         "lat": float(r["spot"].latitude), "lng": float(r["spot"].longitude),
         "visit_days": r["visit_days"], "symbols": len(r["symbols"]),
         "found": sum(1 for s in r["symbols"] if s["found"])}
        for r in rows if r["spot"].latitude is not None and r["spot"].longitude is not None
    ]
    cfg = settings.MIKKE_MAP
    return render(request, "explore/spots.html", {
        "rows": rows,
        "spot_points": points,
        "map_tiles_url": reverse("maps:pmtiles", args=[cfg["tiles"]]),
        "map_config": {k: cfg[k] for k in ("bounds", "center", "zoom", "max_data_zoom")},
    })


@login_required
@require_GET
def camera(request):
    return render(request, "explore/camera.html")


@login_required
@require_GET
def history(request):
    items = Discovery.objects.filter(user=request.user).select_related("symbol__spot")[:100]
    return render(request, "explore/history.html", {"discoveries": items})


@require_POST
@api_login_required
def api_scan(request):
    if not ratelimit.hit(f"scan:{request.user.pk}", 60, 60):
        return JsonResponse({"error": "rate_limited", "message": "少し時間をおいてお試しください。"}, status=429)
    try:
        data = _json_body(request)
        if "image_symbol" in data:
            result = services.scan_image(request.user, data.get("image_symbol"), str(data.get("patch", ""))[:4000])
        else:
            result = services.scan(request.user, str(data.get("payload", ""))[:200])
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "bad_request", "message": "リクエストが正しくありません。"}, status=400)
    except services.UnknownSymbol as exc:
        return _error(exc, 404)
    return JsonResponse(result)


def _coords(data: dict) -> tuple[float, float] | None:
    loc = data.get("location")
    if not isinstance(loc, dict):
        return None
    try:
        lat, lng = float(loc["lat"]), float(loc["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


@require_POST
@api_login_required
def api_collect(request):
    if not ratelimit.hit(f"collect:{request.user.pk}", 20, 60):
        return JsonResponse({"error": "rate_limited", "message": "少し時間をおいてお試しください。"}, status=429)
    key = request.headers.get("Idempotency-Key", "")
    try:
        data = _json_body(request)
        result = services.collect(request.user, str(data.get("ticket", ""))[:1000], key, _coords(data))
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "bad_request", "message": "リクエストが正しくありません。"}, status=400)
    except services.Cooldown as exc:
        return _error(exc, 409)
    except (services.LocationRequired, services.TooFar) as exc:
        return _error(exc, 403)
    except services.UnknownSymbol as exc:
        return _error(exc, 404)
    except services.ExploreError as exc:
        return _error(exc, 400)
    if not result.replay:
        audit.record("explore.collect", request=request, kind=result.reward_kind, label=result.label)
    return JsonResponse(result.as_dict())


@require_GET
@api_login_required
def api_image_symbols(request):
    """画像シンボルの特徴量一覧 (カメラ画面が起動時に取得)。"""
    resp = JsonResponse({"symbols": services.image_symbol_catalog()})
    resp.headers["Cache-Control"] = "private, max-age=300"
    return resp


def _angle_grid(existing: dict[str, SymbolView] | None = None) -> list[dict]:
    existing = existing or {}
    return [{"key": a, "label": label, "view": existing.get(a)} for a, label in ANGLE_CHOICES]


def _json_errors(errors: list[str], status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "errors": errors}, status=status)


@staff_member_required
@require_http_methods(["GET", "POST"])
def symbol_register(request):
    """スタッフがカメラで撮影した写真 (最大 9 角度) を画像シンボルとして登録する。"""
    if request.method == "GET":
        return render(request, "explore/symbol_register.html", {
            "form": ImageSymbolInfoForm(), "angles": _angle_grid(), "mode": "new",
            "api": reverse("explore:symbol_register"),
        })
    form = ImageSymbolInfoForm(request.POST)
    if not form.is_valid():
        return _json_errors([str(e) for errs in form.errors.values() for e in errs])
    cd = form.cleaned_data
    try:
        uploads, _ = collect_view_uploads(request.POST, request.FILES)
        symbol = services.register_image_symbol(
            spot=cd["spot"], name=cd["name"], hint=cd["hint"], cooldown_hours=cd["cooldown_hours"],
            uploads=uploads, created_by=request.user,
        )
    except ImageSymbolError as exc:
        return _json_errors([str(exc)])
    audit.record("symbol.register_image", request=request, target=symbol, spot=symbol.spot_id,
                 angles=sorted(uploads))
    messages.success(request, f"画像シンボル「{symbol.name}」を {len(uploads)} 角度で登録しました。"
                              "ドロップ設定は管理画面で追加してください。")
    return JsonResponse({"ok": True, "id": symbol.pk, "redirect": reverse("explore:symbol_print")})


@staff_member_required
@require_http_methods(["GET", "POST"])
def symbol_views(request, pk: int):
    """既存の画像シンボルに角度を追加・撮り直し・削除する。"""
    symbol = get_object_or_404(Symbol.objects.select_related("spot"), pk=pk, kind=Symbol.KIND_IMAGE)
    if request.method == "GET":
        existing = {v.angle: v for v in symbol.views.only("angle", "keypoint_count", "symbol_id")}
        return render(request, "explore/symbol_register.html", {
            "symbol": symbol, "angles": _angle_grid(existing), "mode": "edit",
            "api": reverse("explore:symbol_views", args=[symbol.pk]),
        })
    try:
        uploads, delete = collect_view_uploads(request.POST, request.FILES)
        if not uploads and not delete:
            raise ImageSymbolError("変更がありません。")
        services.save_symbol_views(symbol, uploads, delete, request.user)
    except ImageSymbolError as exc:
        return _json_errors([str(exc)])
    audit.record("symbol.update_views", request=request, target=symbol, saved=sorted(uploads), deleted=sorted(delete))
    messages.success(request, f"画像シンボル「{symbol.name}」の角度を更新しました。")
    return JsonResponse({"ok": True, "id": symbol.pk, "redirect": reverse("explore:symbol_print")})


@staff_member_required
@require_GET
def symbol_view_image(request, pk: int, angle: str):
    view = get_object_or_404(SymbolView, symbol_id=pk, angle=angle)
    resp = HttpResponse(bytes(view.jpeg), content_type="image/jpeg")
    resp.headers["Cache-Control"] = "private, no-cache"
    if request.GET.get("download") == "1":
        resp.headers["Content-Disposition"] = f'attachment; filename="mikke-image-symbol-{pk}-{angle}.jpg"'
    return resp


@staff_member_required
@require_GET
def symbol_svg(request, pk: int):
    symbol = get_object_or_404(Symbol.objects.select_related("spot"), pk=pk, kind=Symbol.KIND_QR)
    resp = HttpResponse(render_symbol_svg(symbol), content_type="image/svg+xml; charset=utf-8")
    resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    if request.GET.get("download") == "1":
        resp.headers["Content-Disposition"] = f'attachment; filename="mikke-symbol-{symbol.pk}.svg"'
    return resp


@staff_member_required
@require_GET
def symbol_print(request):
    symbols = (
        Symbol.objects.select_related("spot").filter(is_active=True).order_by("kind", "spot_id", "pk")
        .prefetch_related(Prefetch("views", queryset=SymbolView.objects.only("symbol_id", "angle", "keypoint_count")))
    )
    return render(request, "explore/symbol_print.html", {"symbols": symbols})

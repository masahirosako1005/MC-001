from __future__ import annotations

import json
import logging
from functools import wraps

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core import audit, ratelimit

from . import services
from .models import Discovery, Spot, SpotVisit, Symbol
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
    return render(request, "explore/spots.html", {"rows": rows})


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


@staff_member_required
@require_GET
def symbol_svg(request, pk: int):
    symbol = get_object_or_404(Symbol.objects.select_related("spot"), pk=pk)
    resp = HttpResponse(render_symbol_svg(symbol), content_type="image/svg+xml; charset=utf-8")
    resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    if request.GET.get("download") == "1":
        resp.headers["Content-Disposition"] = f'attachment; filename="mikke-symbol-{symbol.pk}.svg"'
    return resp


@staff_member_required
@require_GET
def symbol_print(request):
    symbols = Symbol.objects.select_related("spot").filter(is_active=True)
    return render(request, "explore/symbol_print.html", {"symbols": symbols})

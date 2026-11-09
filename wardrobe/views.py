from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from core import audit

from .avatar import CATEGORY_CHOICES, SKIN_TONE_CHOICES
from .models import Item, UserItem
from .services import EquipError, VersionConflict, config_svg, equip, get_config, item_preview_svg

SKIN_KEYS = {k for k, _ in SKIN_TONE_CHOICES}


def _svg_response(svg: str, *, cacheable: bool = False) -> HttpResponse:
    resp = HttpResponse(svg, content_type="image/svg+xml; charset=utf-8")
    # SVG 単体で開かれた場合もスクリプトを実行させない
    resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    # 着せ替え直後に古い画像が出ないよう、アバター画像はキャッシュさせない
    resp.headers["Cache-Control"] = "private, max-age=300" if cacheable else "private, no-store"
    return resp


def _parse_int(value: str | None) -> int | None:
    if value in (None, "", "none"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise EquipError("選択内容が正しくありません。") from None


@login_required
@require_http_methods(["GET", "POST"])
def index(request):
    config = get_config(request.user)
    if request.method == "POST":
        try:
            skin = request.POST.get("skin_tone", "")
            if skin not in SKIN_KEYS:
                raise EquipError("肌の色の選択が正しくありません。")
            selections = {c: _parse_int(request.POST.get(c)) for c, _ in CATEGORY_CHOICES}
            expected = _parse_int(request.POST.get("version")) or 0
            equip(request.user, expected_version=expected, skin_tone=skin, selections=selections)
        except VersionConflict as exc:
            messages.warning(request, str(exc))
        except EquipError as exc:
            messages.error(request, str(exc))
        else:
            audit.record("avatar.update", request=request, target=config)
            messages.success(request, "着せ替えを保存しました。")
        return redirect("wardrobe:index")

    owned = list(UserItem.objects.select_related("item").filter(user=request.user, item__is_active=True)
                 .order_by("item__rarity", "item__code"))
    total_by_cat = {c: Item.objects.filter(category=c, is_active=True).count() for c, _ in CATEGORY_CHOICES}
    equipped = config.equipped()
    groups = []
    for cat, label in CATEGORY_CHOICES:
        items = [ui for ui in owned if ui.item.category == cat]
        locked = max(total_by_cat[cat] - len(items), 0)
        groups.append({
            "key": cat,
            "label": label,
            "items": items,
            "equipped_id": equipped[cat].pk if equipped[cat] else None,
            "locked": locked,
            "locked_slots": range(min(locked, 6)),
            "can_unequip": True,
        })
    return render(request, "wardrobe/index.html", {
        "config": config,
        "groups": groups,
        "skin_choices": SKIN_TONE_CHOICES,
        "owned_count": len(owned),
        "total_count": sum(total_by_cat.values()),
    })


@login_required
@require_GET
def avatar_svg(request):
    return _svg_response(config_svg(get_config(request.user), label=f"{request.user.nickname}さんのアバター"))


@login_required
@require_GET
def preview_svg(request):
    """着せ替え画面のライブプレビュー。所有アイテムだけを反映する (保存はしない)。"""
    config = get_config(request.user)
    skin = request.GET.get("skin_tone", config.skin_tone)
    if skin in SKIN_KEYS:
        config.skin_tone = skin
    ids = {}
    for cat, _ in CATEGORY_CHOICES:
        try:
            ids[cat] = _parse_int(request.GET.get(cat))
        except EquipError:
            ids[cat] = None
    owned = {ui.item_id: ui.item for ui in UserItem.objects.select_related("item")
             .filter(user=request.user, item_id__in=[v for v in ids.values() if v])}
    for cat, item_id in ids.items():
        item = owned.get(item_id) if item_id else None
        setattr(config, cat, item if item and item.category == cat else None)
    return _svg_response(config_svg(config, label="プレビュー"))


@login_required
@require_GET
def item_svg(request, code: str):
    ui = UserItem.objects.select_related("item").filter(user=request.user, item__code=code).first()
    if ui is None and not request.user.is_staff:
        raise Http404
    item = ui.item if ui else Item.objects.filter(code=code).first()
    if item is None:
        raise Http404
    return _svg_response(item_preview_svg(item, get_config(request.user).skin_tone), cacheable=True)

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from core import audit

from .avatar import (
    BODY_TYPE_CHOICES,
    CATEGORY_CHOICES,
    EYE_COLOR_CHOICES,
    ITEM_BODY_CHOICES,
    SKIN_TONE_CHOICES,
    render_background_svg,
)
from .models import Item, UserItem
from .services import (
    EquipError,
    VersionConflict,
    can_use_any_item,
    config_svg,
    equip,
    get_config,
    item_preview_svg,
    item_zoom_svg,
    selectable_items,
    to_part,
)


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
            selections = {c: _parse_int(request.POST.get(c)) for c, _ in CATEGORY_CHOICES}
            expected = _parse_int(request.POST.get("version")) or 0
            equip(request.user, expected_version=expected, skin_tone=request.POST.get("skin_tone", ""),
                  selections=selections, body_type=request.POST.get("body_type", ""),
                  eye_color=request.POST.get("eye_color", ""))
        except VersionConflict as exc:
            messages.warning(request, str(exc))
        except EquipError as exc:
            messages.error(request, str(exc))
        else:
            audit.record("avatar.update", request=request, target=config)
            messages.success(request, "着せ替えを保存しました。")
        return redirect("wardrobe:index")

    staff = can_use_any_item(request.user)
    owned_ids = set(UserItem.objects.filter(user=request.user).values_list("item_id", flat=True))
    items = list(selectable_items(request.user))
    all_active = list(Item.objects.filter(is_active=True).values_list("category", "body_type"))
    equipped = config.equipped()
    groups = []
    for cat, label in CATEGORY_CHOICES:
        mine = [i for i in items if i.category == cat]
        # 未発見のパーツ数 (体のタイプ別に表示を切り替える)
        locked = {}
        for bt, _ in BODY_TYPE_CHOICES:
            total = sum(1 for c, b in all_active if c == cat and b in (bt, "any"))
            have = sum(1 for i in mine if i.fits(bt) and i.pk in owned_ids)
            locked[bt] = max(total - have, 0)
        groups.append({
            "key": cat,
            "label": label,
            "items": [{"item": i, "owned": i.pk in owned_ids} for i in mine],
            "equipped_id": equipped[cat].pk if equipped[cat] else None,
            "locked": locked,
            "locked_slots": {bt: range(min(n, 6)) for bt, n in locked.items()},
        })
    return render(request, "wardrobe/index.html", {
        "config": config,
        "groups": groups,
        "skin_choices": SKIN_TONE_CHOICES,
        "body_choices": BODY_TYPE_CHOICES,
        "eye_choices": EYE_COLOR_CHOICES,
        "owned_count": len(owned_ids),
        "total_count": len(all_active),
        "staff": staff,
    })


@login_required
@require_GET
def avatar_svg(request):
    """自分のアバター。?layer=avatar で背景なし、?layer=bg で背景だけ (1 画面ホームで重ねて表示する用)。"""
    config = get_config(request.user)
    layer = request.GET.get("layer")
    if layer == "bg":
        return _svg_response(render_background_svg(to_part(config.background)))
    label = f"{request.user.nickname}さんのアバター"
    return _svg_response(config_svg(config, label=label, background=layer != "avatar"))


@login_required
@require_GET
def preview_svg(request):
    """着せ替え画面のライブプレビュー (保存はしない)。選べるアイテムだけを反映する。"""
    config = get_config(request.user)
    if request.GET.get("skin_tone") in {k for k, _ in SKIN_TONE_CHOICES}:
        config.skin_tone = request.GET["skin_tone"]
    if request.GET.get("body_type") in {k for k, _ in BODY_TYPE_CHOICES}:
        config.body_type = request.GET["body_type"]
    if request.GET.get("eye_color") in {k for k, _ in EYE_COLOR_CHOICES}:
        config.eye_color = request.GET["eye_color"]
    ids = {}
    for cat, _ in CATEGORY_CHOICES:
        try:
            ids[cat] = _parse_int(request.GET.get(cat))
        except EquipError:
            ids[cat] = None
    usable = {i.pk: i for i in selectable_items(request.user).filter(pk__in=[v for v in ids.values() if v])}
    for cat, item_id in ids.items():
        item = usable.get(item_id) if item_id else None
        setattr(config, cat, item if item and item.category == cat else None)
    return _svg_response(config_svg(config, label="プレビュー"))


@login_required
@require_GET
def item_svg(request, code: str):
    item = selectable_items(request.user).filter(code=code).first()
    if item is None:
        raise Http404
    cfg = get_config(request.user)
    render = item_zoom_svg if request.GET.get("zoom") == "1" else item_preview_svg  # ?zoom=1 でパーツを大きく
    return _svg_response(render(item, cfg.skin_tone, cfg.eye_color), cacheable=True)


@staff_member_required
@require_GET
def catalog(request):
    """運営向け: 全パーツの一覧 (体のタイプ別・部位別)。"""
    items = list(Item.objects.order_by("category", "rarity", "code"))
    sections = []
    for bt, bt_label in ITEM_BODY_CHOICES:
        cats = []
        for cat, label in CATEGORY_CHOICES:
            rows = [i for i in items if i.body_type == bt and i.category == cat]
            if rows:
                cats.append({"label": label, "items": rows})
        count = sum(len(c["items"]) for c in cats)
        if count:
            sections.append({"key": bt, "label": bt_label, "count": count, "cats": cats})
    return render(request, "wardrobe/catalog.html", {"sections": sections, "total": len(items)})

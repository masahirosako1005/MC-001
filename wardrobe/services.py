from __future__ import annotations

from django.db import transaction
from django.db.models import F

from .avatar import (
    BODY_TYPE_CHOICES,
    CATEGORY_CHOICES,
    EYE_COLOR_CHOICES,
    SKIN_TONE_CHOICES,
    Part,
    render_svg,
)
from .models import AvatarConfig, Item, UserItem

CATEGORIES = [c for c, _ in CATEGORY_CHOICES]
BODY_TYPES = {k for k, _ in BODY_TYPE_CHOICES}
EYE_COLORS = {k for k, _ in EYE_COLOR_CHOICES}
SKIN_TONES = {k for k, _ in SKIN_TONE_CHOICES}


class EquipError(Exception):
    pass


class VersionConflict(EquipError):
    pass


def can_use_any_item(user) -> bool:
    """管理者 (運営スタッフ) は、持っていないパーツや別の体のタイプのパーツも自由に選べる。"""
    return bool(getattr(user, "is_staff", False))


def to_part(item: Item | None) -> Part | None:
    if item is None:
        return None
    return Part(category=item.category, style=item.style, color=item.color, name=item.name)


def grant_item(user, item: Item) -> tuple[UserItem, bool]:
    """アイテムを付与する。既に持っていれば入手回数を加算。戻り値の bool は新規入手か。"""
    ui, created = UserItem.objects.get_or_create(user=user, item=item)
    if not created:
        UserItem.objects.filter(pk=ui.pk).update(obtained_count=F("obtained_count") + 1)
        ui.refresh_from_db()
    return ui, created


@transaction.atomic
def ensure_starter_kit(user, body_type: str = "girl") -> AvatarConfig:
    """初期アイテム (女の子用・男の子用の両方) を配り、指定の体のタイプで着せた状態にする。"""
    starters = list(Item.objects.filter(is_starter=True, is_active=True).order_by("rarity", "code"))
    for item in starters:
        UserItem.objects.get_or_create(user=user, item=item)
    config, created = AvatarConfig.objects.get_or_create(user=user, defaults={"body_type": body_type})
    if created:
        for cat in ("face", "hair", "top", "bottom", "shoes", "background"):
            first = next((i for i in starters if i.category == cat and i.fits(config.body_type)), None)
            setattr(config, cat, first)
        config.save()
    return config


BASIC_SLOTS = ("hair", "top", "bottom", "shoes")


def dress_if_bare(config: AvatarConfig) -> AvatarConfig:
    """髪も服も何も着ていない (「裸のマネキン」に見える) ときだけ、初期アイテムを着せる。

    初期アイテムができる前に作られたアカウントのためのもの。何か 1 つでも着ていれば本人の選択とみなして変えない。
    """
    if any(getattr(config, f"{c}_id") for c in BASIC_SLOTS):
        return config
    starters = list(Item.objects.filter(is_starter=True, is_active=True).order_by("rarity", "code"))
    for item in starters:
        UserItem.objects.get_or_create(user=config.user, item=item)
    changed = False
    for cat in BASIC_SLOTS:
        first = next((i for i in starters if i.category == cat and i.fits(config.body_type)), None)
        if first is not None:
            setattr(config, cat, first)
            changed = True
    if changed:
        config.save()
    return config


def get_config(user) -> AvatarConfig:
    config = AvatarConfig.objects.select_related(*CATEGORIES).filter(user=user).first()
    return dress_if_bare(config) if config else ensure_starter_kit(user)


def selectable_items(user):
    """着せ替え画面に出すアイテム。管理者は全アイテム、それ以外は所持品のみ。"""
    qs = Item.objects.filter(is_active=True)
    if not can_use_any_item(user):
        qs = qs.filter(owners__user=user)
    return qs.order_by("category", "rarity", "code")


@transaction.atomic
def equip(user, *, expected_version: int, skin_tone: str, selections: dict[str, int | None],
          body_type: str | None = None, eye_color: str | None = None) -> AvatarConfig:
    """着せ替えを保存する。サーバー側で次を検証する:
    - 持っていないアイテムは着られない (管理者を除く)
    - 部位が違うアイテムは着られない
    - 体のタイプに合わないアイテムは着られない (管理者を除く)
    """
    config = AvatarConfig.objects.select_for_update().get(user=user)
    if config.version != expected_version:
        raise VersionConflict("別の画面でアバターが更新されています。画面を読み込み直してください。")
    body_type = body_type or config.body_type
    eye_color = eye_color or config.eye_color
    if body_type not in BODY_TYPES or eye_color not in EYE_COLORS or skin_tone not in SKIN_TONES:
        raise EquipError("選択内容が正しくありません。")
    free = can_use_any_item(user)
    ids = [v for v in selections.values() if v]
    usable = {i.pk: i for i in selectable_items(user).filter(pk__in=ids)}
    for cat in CATEGORIES:
        item_id = selections.get(cat)
        if item_id is None:
            setattr(config, cat, None)
            continue
        item = usable.get(item_id)
        if item is None:
            raise EquipError("持っていないアイテムは身につけられません。")
        if item.category != cat:
            raise EquipError("アイテムの部位が正しくありません。")
        if not free and not item.fits(body_type):
            raise EquipError(f"「{item.name}」は{'女の子' if item.body_type == 'girl' else '男の子'}用のアイテムです。")
        setattr(config, cat, item)
    config.skin_tone = skin_tone
    config.body_type = body_type
    config.eye_color = eye_color
    config.version += 1
    config.save()
    return config


def config_svg(config: AvatarConfig, **kw) -> str:
    return render_svg(config.skin_tone, {c: to_part(getattr(config, c)) for c in CATEGORIES},
                      body_type=config.body_type, eye_color=config.eye_color, **kw)


# 手に入れたパーツを大きく見せるための切り抜き範囲 (viewBox 200x300 内の正方形)。
# こもの・エフェクト・背景は形や位置がまちまちなので、全身のまま見せる。
ZOOM_BOXES = {
    "shoes": (74, 252, 52, 52),
    "bottom": (48, 180, 104, 104),
    "top": (52, 124, 96, 96),
    "hair": (30, 4, 140, 140),
    "face": (52, 56, 96, 96),
}


def item_zoom_svg(item: Item, skin_tone: str = "tone3", eye_color: str = "brown") -> str:
    """アイテムを身につけたプレビューを、そのパーツの部分だけ大きく切り抜いたもの。"""
    svg = item_preview_svg(item, skin_tone, eye_color)
    box = ZOOM_BOXES.get(item.category)
    if box is None:
        return svg
    return svg.replace('viewBox="0 0 200 300"', 'viewBox="{} {} {} {}"'.format(*box), 1)


def item_preview_svg(item: Item, skin_tone: str = "tone3", eye_color: str = "brown") -> str:
    """アイテム単体を身につけたプレビュー。体のタイプはアイテムに合わせる。"""
    body = item.body_type if item.body_type in BODY_TYPES else "girl"
    parts = {c: (to_part(item) if c == item.category else None) for c in CATEGORIES}
    if item.category != "hair":  # 髪以外のプレビューは、見本の髪型と服をのせて見やすくする
        parts["hair"] = Part("hair", "bob" if body == "girl" else "short", "#6B4226")
    if item.category in ("face", "effect", "background"):
        parts["top"] = Part("top", "tshirt", "#F2F2F2")
        parts["bottom"] = Part("bottom", "skirt" if body == "girl" else "pants", "#5A7FB5")
    return render_svg(skin_tone, parts, body_type=body, eye_color=eye_color, label=f"アイテム「{item.name}」")

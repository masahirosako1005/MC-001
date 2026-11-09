from __future__ import annotations

from django.db import transaction
from django.db.models import F

from .avatar import CATEGORY_CHOICES, Part, render_svg
from .models import AvatarConfig, Item, UserItem

CATEGORIES = [c for c, _ in CATEGORY_CHOICES]


class EquipError(Exception):
    pass


class VersionConflict(EquipError):
    pass


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
def ensure_starter_kit(user) -> AvatarConfig:
    starters = list(Item.objects.filter(is_starter=True, is_active=True).order_by("rarity", "code"))
    for item in starters:
        UserItem.objects.get_or_create(user=user, item=item)
    config, created = AvatarConfig.objects.get_or_create(user=user)
    if created:
        for cat in ("hair", "top", "bottom", "shoes"):
            first = next((i for i in starters if i.category == cat), None)
            setattr(config, cat, first)
        config.save()
    return config


def get_config(user) -> AvatarConfig:
    config = AvatarConfig.objects.select_related(*CATEGORIES).filter(user=user).first()
    return config or ensure_starter_kit(user)


@transaction.atomic
def equip(user, *, expected_version: int, skin_tone: str, selections: dict[str, int | None]) -> AvatarConfig:
    """着せ替えを保存する。所有していない・部位違いのアイテムはサーバー側で拒否する。"""
    config = AvatarConfig.objects.select_for_update().get(user=user)
    if config.version != expected_version:
        raise VersionConflict("別の画面でアバターが更新されています。画面を読み込み直してください。")
    owned = {
        ui.item_id: ui.item
        for ui in UserItem.objects.select_related("item").filter(user=user, item_id__in=[v for v in selections.values() if v])
    }
    for cat in CATEGORIES:
        item_id = selections.get(cat)
        if item_id is None:
            setattr(config, cat, None)
            continue
        item = owned.get(item_id)
        if item is None:
            raise EquipError("持っていないアイテムは身につけられません。")
        if item.category != cat:
            raise EquipError("アイテムの部位が正しくありません。")
        setattr(config, cat, item)
    config.skin_tone = skin_tone
    config.version += 1
    config.save()
    return config


def config_svg(config: AvatarConfig, **kw) -> str:
    return render_svg(config.skin_tone, {c: to_part(getattr(config, c)) for c in CATEGORIES}, **kw)


def item_preview_svg(item: Item, skin_tone: str = "tone3") -> str:
    """アイテム単体を身につけたマネキン風プレビュー。"""
    return render_svg(skin_tone, {c: (to_part(item) if c == item.category else None) for c in CATEGORIES},
                      label=f"アイテム「{item.name}」")

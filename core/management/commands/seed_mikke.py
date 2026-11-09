"""デモ用の初期データを投入する (何度実行しても同じ状態になる)。

    python manage.py seed_mikke
スポットや店舗はすべて架空のもの。
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from explore.models import DropEntry, Spot, Symbol
from rewards.models import Achievement, CouponTemplate
from wardrobe.models import Item

ITEMS = [
    # code, name, category, style, color, rarity, starter, description
    ("hair-short-brown", "ショート(ブラウン)", "hair", "short", "#6B4226", 1, True, "はじまりの髪型"),
    ("top-tshirt-white", "白Tシャツ", "top", "tshirt", "#F2F2F2", 1, True, "旅のはじまりの一枚"),
    ("bottom-pants-denim", "デニムパンツ", "bottom", "pants", "#3B5B8C", 1, True, "どこへでも行ける"),
    ("shoes-sneakers-gray", "グレーのスニーカー", "shoes", "sneakers", "#8A8F99", 1, True, "歩きやすい"),
    ("hair-bob-black", "ボブ(黒)", "hair", "bob", "#222222", 1, False, "温泉街のそよ風"),
    ("hair-long-chestnut", "ロング(栗色)", "hair", "long", "#8B4A2B", 2, False, "秋の参道の色"),
    ("hair-spiky-blond", "ツンツン(金)", "hair", "spiky", "#E8C14A", 3, False, "港の夕日"),
    ("hair-bun-black", "おだんご(黒)", "hair", "bun", "#2A2A2A", 2, False, "朝の神社で"),
    ("hair-ponytail-sakura", "ポニーテール(さくら)", "hair", "ponytail", "#F2A7C3", 4, False, "春だけの色"),
    ("hair-long-silver", "ロング(月光)", "hair", "long", "#C9CED8", 5, False, "夜の森でだけ出会える"),
    ("top-happi-indigo", "藍の法被", "top", "happi", "#2D4A8A", 2, False, "祭りの名残"),
    ("top-happi-red", "朱の法被", "top", "happi", "#C0392B", 3, False, "夏祭りの主役"),
    ("top-hoodie-mint", "ミントのパーカー", "top", "hoodie", "#7FCFB5", 1, False, "朝の散歩に"),
    ("top-jacket-navy", "ネイビージャケット", "top", "jacket", "#22325A", 2, False, "レトロ通りの喫茶店で"),
    ("top-border-marine", "マリンボーダー", "top", "border", "#1E5AA8", 2, False, "港町の定番"),
    ("top-hoodie-maple", "もみじパーカー", "top", "hoodie", "#D2552B", 4, False, "秋限定"),
    ("bottom-hakama-purple", "紫の袴", "bottom", "hakama", "#5B3A7A", 3, False, "神社の正装"),
    ("bottom-skirt-yellow", "菜の花スカート", "bottom", "skirt", "#F2C230", 2, False, "春の野原"),
    ("bottom-shorts-khaki", "カーキのショートパンツ", "bottom", "shorts", "#A08C5B", 1, False, "夏の冒険に"),
    ("bottom-pants-black", "黒のパンツ", "bottom", "pants", "#2B2B2B", 1, False, "夜の街歩き"),
    ("shoes-geta-red", "赤鼻緒の下駄", "shoes", "geta", "#C0392B", 2, False, "温泉街をカランコロン"),
    ("shoes-boots-brown", "ブラウンブーツ", "shoes", "boots", "#6E4B2A", 2, False, "森の小道に"),
    ("shoes-sneakers-orange", "夕焼けスニーカー", "shoes", "sneakers", "#F08A24", 3, False, "港の夕方に"),
    ("acc-foxmask-red", "きつねのお面", "accessory", "foxmask", "#C0392B", 4, False, "夜の神社のおまつり"),
    ("acc-flower-sakura", "さくらのかんざし", "accessory", "flower", "#F2A7C3", 3, False, "春の再訪のしるし"),
    ("acc-scarf-red", "赤いマフラー", "accessory", "scarf", "#B3262E", 2, False, "冬の湯けむり"),
    ("acc-glasses-gold", "金縁メガネ", "accessory", "glasses", "#B8892B", 2, False, "レトロ喫茶の店主から"),
    ("acc-cap-sea", "マリンキャップ", "accessory", "cap", "#1E5AA8", 2, False, "港のおみやげ"),
    ("acc-flower-gold", "金の花かんざし", "accessory", "flower", "#E0B000", 5, False, "やりこみの証"),
    ("top-happi-gold", "金の法被", "top", "happi", "#C9A227", 5, False, "すべての季節を巡った証"),
]

COUPONS = [
    ("cp-onsen-manju", "湯けむり饅頭 1個サービス", "湯の花茶屋", "お買い上げで饅頭1個プレゼント", "onsen", 30),
    ("cp-retro-coffee", "レトロ喫茶 ドリンク50円引き", "喫茶 ほしぞら", "ドリンク全品 50円引き", "retro", 30),
    ("cp-shrine-omamori", "授与所 ミニ絵馬プレゼント", "森の社 授与所", "ミニ絵馬を1枚プレゼント", "shrine", 60),
    ("cp-revisit-lunch", "再訪感謝 ランチ10%オフ", "港の食堂 しおさい", "ランチ代金 10%オフ", "retro", 45),
]

SPOTS = [
    ("onsen", "湯けむり温泉郷", "みっけ県 ゆのさと町", "川沿いに湯けむりが立つ温泉街。足湯めぐりが人気。", "35.000000", "139.000000"),
    ("retro", "港町レトロ通り", "みっけ県 しおかぜ市", "赤れんが倉庫と古い喫茶店が並ぶ港の通り。", "35.010000", "139.010000"),
    ("shrine", "森の社", "みっけ県 こもれび村", "樹齢数百年の杉に囲まれた静かな神社。季節ごとに表情が変わる。", "35.020000", "139.020000"),
]

SYMBOLS = [
    # spot, name, hint, cooldown, drops[(item_code|coupon_code, weight, season, slot, min_visit)]
    ("onsen", "足湯のかっぱ", "足湯の看板のそば、かっぱの像の足もと", 20, [
        ("hair-bob-black", 30, "any", "any", 1),
        ("top-hoodie-mint", 20, "any", "morning", 1),
        ("shoes-geta-red", 25, "any", "any", 1),
        ("acc-scarf-red", 30, "winter", "any", 1),
        ("cp-onsen-manju", 15, "any", "any", 1),
        ("top-happi-indigo", 25, "any", "any", 2),
    ]),
    ("onsen", "湯の花の石碑", "源泉公園の石碑の裏側", 20, [
        ("bottom-shorts-khaki", 30, "summer", "any", 1),
        ("bottom-pants-black", 25, "any", "night", 1),
        ("hair-long-chestnut", 25, "autumn", "any", 1),
        ("bottom-skirt-yellow", 25, "spring", "any", 1),
        ("bottom-pants-denim", 10, "any", "any", 1),
    ]),
    ("retro", "倉庫のかもめ", "赤れんが倉庫2号館の入口", 20, [
        ("top-border-marine", 30, "any", "any", 1),
        ("acc-cap-sea", 25, "any", "day", 1),
        ("shoes-sneakers-orange", 25, "any", "evening", 1),
        ("hair-spiky-blond", 15, "any", "evening", 1),
        ("cp-retro-coffee", 15, "any", "any", 1),
        ("cp-revisit-lunch", 20, "any", "any", 3),
    ]),
    ("retro", "喫茶店の看板ねこ", "喫茶 ほしぞら の窓辺", 20, [
        ("top-jacket-navy", 30, "any", "any", 1),
        ("acc-glasses-gold", 25, "any", "any", 1),
        ("bottom-pants-black", 20, "any", "night", 1),
        ("top-happi-red", 25, "summer", "any", 2),
    ]),
    ("shrine", "杉の木の木霊", "参道で一番大きな杉の根もと", 20, [
        ("hair-bun-black", 30, "any", "morning", 1),
        ("bottom-hakama-purple", 25, "any", "any", 1),
        ("shoes-boots-brown", 25, "any", "any", 1),
        ("top-hoodie-maple", 30, "autumn", "any", 1),
        ("hair-ponytail-sakura", 30, "spring", "any", 1),
        ("acc-flower-sakura", 30, "spring", "any", 2),
        ("cp-shrine-omamori", 10, "any", "any", 1),
    ]),
    ("shrine", "夜の灯籠", "本殿わきの石灯籠 (夜に訪れると…?)", 20, [
        ("acc-foxmask-red", 30, "any", "night", 1),
        ("hair-long-silver", 10, "any", "night", 2),
        ("bottom-hakama-purple", 20, "any", "any", 1),
        ("top-happi-indigo", 20, "any", "any", 1),
    ]),
]

ACHIEVEMENTS = [
    # code, name, description, icon, kind, threshold, reward_item, reward_coupon, order
    ("first-mikke", "はじめてのみっけ", "シンボルを 1 回みっけする", "🔍", "total_discoveries", 1, None, None, 1),
    ("explorer-3", "さんぽ上手", "3 つのスポットを訪れる", "🗺️", "distinct_spots", 3, "acc-glasses-gold", None, 2),
    ("collector-10", "おしゃれ見習い", "アイテムを 10 種類集める", "👕", "distinct_items", 10, None, "cp-retro-coffee", 3),
    ("revisit-2", "また来たよ", "同じスポットに 2 日訪れる", "🔁", "spot_visit_days", 2, None, "cp-onsen-manju", 4),
    ("revisit-5", "常連さん", "同じスポットに 5 日訪れる", "🏮", "spot_visit_days", 5, "acc-flower-gold", "cp-revisit-lunch", 5),
    ("seasons-4", "四季めぐり", "同じスポットで 4 つの季節を体験する", "🍁", "seasons_at_spot", 4, "top-happi-gold", None, 6),
    ("mikke-30", "みっけマスター", "30 回みっけする", "🏆", "total_discoveries", 30, None, "cp-shrine-omamori", 7),
]


class Command(BaseCommand):
    help = "デモ用のスポット・シンボル・アイテム・クーポン・実績を投入します"

    @transaction.atomic
    def handle(self, *args, **opts):
        items = {}
        for code, name, cat, style, color, rarity, starter, desc in ITEMS:
            item, _ = Item.objects.update_or_create(code=code, defaults=dict(
                name=name, category=cat, style=style, color=color, rarity=rarity,
                is_starter=starter, description=desc, is_active=True))
            item.full_clean()
            items[code] = item

        spots = {}
        for slug, name, area, desc, lat, lng in SPOTS:
            spots[slug], _ = Spot.objects.update_or_create(slug=slug, defaults=dict(
                name=name, area=area, description=desc, latitude=lat, longitude=lng, radius_m=300,
                require_location=False, is_active=True))

        coupons = {}
        for code, title, shop, benefit, spot_slug, days in COUPONS:
            coupons[code], _ = CouponTemplate.objects.update_or_create(code=code, defaults=dict(
                title=title, shop_name=shop, benefit=benefit, spot=spots[spot_slug], valid_days=days,
                description="※デモ用の架空店舗です。お一人様1回限り。", is_active=True))

        for spot_slug, name, hint, cooldown, drops in SYMBOLS:
            symbol, _ = Symbol.objects.update_or_create(spot=spots[spot_slug], name=name, defaults=dict(
                hint=hint, cooldown_hours=cooldown, is_active=True))
            symbol.drops.all().delete()
            for ref, weight, season, slot, min_visit in drops:
                DropEntry.objects.create(
                    symbol=symbol, item=items.get(ref), coupon=coupons.get(ref), weight=weight,
                    season=season, time_slot=slot, min_visit_days=min_visit)

        for code, name, desc, icon, kind, th, item_code, coupon_code, order in ACHIEVEMENTS:
            Achievement.objects.update_or_create(code=code, defaults=dict(
                name=name, description=desc, icon=icon, kind=kind, threshold=th,
                reward_item=items.get(item_code), reward_coupon=coupons.get(coupon_code),
                sort_order=order, is_active=True))

        self.stdout.write(self.style.SUCCESS(
            f"投入完了: アイテム {len(items)} / スポット {len(spots)} / シンボル {len(SYMBOLS)} / "
            f"クーポン {len(coupons)} / 実績 {len(ACHIEVEMENTS)}"))

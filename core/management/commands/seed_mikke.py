"""デモ用の初期データを投入する (何度実行しても同じ状態になる)。

    python manage.py seed_mikke
スポットや店舗はすべて架空のもの。
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from contest.models import Contest
from contest.services import create_bots
from explore.models import DropEntry, Spot, Symbol
from rewards.models import Achievement, CouponTemplate
from wardrobe.models import Item, UserItem
from wardrobe.sample_items import SAMPLE_ITEMS

# 1 枚あたりの金額 (円、分析の使用金額に使う)。割引率のクーポンは平均的な値引き額で換算する
COUPON_VALUES = {"cp-onsen-manju": 150, "cp-retro-coffee": 50, "cp-shrine-omamori": 300,
                 "cp-revisit-lunch": 100}
COUPONS = [
    ("cp-onsen-manju", "湯けむり饅頭 1個サービス", "湯の花茶屋", "お買い上げで饅頭1個プレゼント", "onsen", 30),
    ("cp-retro-coffee", "レトロ喫茶 ドリンク50円引き", "喫茶 ほしぞら", "ドリンク全品 50円引き", "retro", 30),
    ("cp-shrine-omamori", "授与所 ミニ絵馬プレゼント", "森の社 授与所", "ミニ絵馬を1枚プレゼント", "shrine", 60),
    ("cp-revisit-lunch", "再訪感謝 ランチ10%オフ", "港の食堂 しおさい", "ランチ代金 10%オフ", "retro", 45),
]

# 地図上で「？」の画像だけを見せるシークレットシンボル
SECRET_SYMBOLS = {"夜の灯籠"}

# 名前・紹介文は架空。地図表示の確認用に、座標は収録タイル (大阪府 京橋付近) の範囲内に置いている。
SPOTS = [
    ("onsen", "湯けむり温泉郷", "大阪市 京橋 (デモ)", "川沿いに湯けむりが立つ温泉街。足湯めぐりが人気。", "34.698800", "135.535500"),
    ("retro", "港町レトロ通り", "大阪市 京橋 (デモ)", "赤れんが倉庫と古い喫茶店が並ぶ港の通り。", "34.691000", "135.531500"),
    ("shrine", "森の社", "大阪市 京橋 (デモ)", "樹齢数百年の杉に囲まれた静かな神社。季節ごとに表情が変わる。", "34.688000", "135.526500"),
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
        for code, name, cat, style, color, rarity, starter, desc, body in SAMPLE_ITEMS:
            item, _ = Item.objects.update_or_create(code=code, defaults=dict(
                name=name, category=cat, style=style, color=color, rarity=rarity, body_type=body,
                is_starter=starter, description=desc, is_active=True))
            item.full_clean()
            items[code] = item

        spots = {}
        for slug, name, area, desc, lat, lng in SPOTS:
            spots[slug], _ = Spot.objects.update_or_create(slug=slug, defaults=dict(
                name=name, area=area, description=desc, latitude=lat, longitude=lng, radius_m=300,
                require_location=True, is_active=True))

        coupons = {}
        for code, title, shop, benefit, spot_slug, days in COUPONS:
            coupons[code], _ = CouponTemplate.objects.update_or_create(code=code, defaults=dict(
                title=title, shop_name=shop, benefit=benefit, spot=spots[spot_slug], valid_days=days,
                value_yen=COUPON_VALUES.get(code, 0),
                description="※デモ用の架空店舗です。お一人様1回限り。", is_active=True))

        # シンボルはスポット中心から 20〜60m ほど離して置く (地図上で重ならないように)
        offsets = [(0.0002, 0.0002), (-0.0003, 0.0001), (0.0001, -0.0004), (-0.0002, -0.0003), (0.0004, -0.0001)]
        per_spot = {}
        for spot_slug, name, hint, cooldown, drops in SYMBOLS:
            spot = spots[spot_slug]
            n = per_spot[spot_slug] = per_spot.get(spot_slug, -1) + 1
            dlat, dlng = offsets[n % len(offsets)]
            symbol, _ = Symbol.objects.update_or_create(spot=spot, name=name, defaults=dict(
                hint=hint, cooldown_hours=cooldown, is_active=True,
                is_secret=name in SECRET_SYMBOLS,
                latitude=Decimal(str(spot.latitude)) + Decimal(str(dlat)),
                longitude=Decimal(str(spot.longitude)) + Decimal(str(dlng))))
            symbol.drops.all().delete()
            for ref, weight, season, slot, min_visit in drops:
                DropEntry.objects.create(
                    symbol=symbol, item=items.get(ref), coupon=coupons.get(ref), weight=weight,
                    season=season, time_slot=slot, min_visit_days=min_visit)

        # まだどのシンボルからも出ないパーツを、デモ用シンボルに順番に割り当てて探索で手に入るようにする
        demo_symbols = [Symbol.objects.get(spot=spots[s], name=n) for s, n, *_ in SYMBOLS]
        in_drops = set(DropEntry.objects.filter(item__isnull=False).values_list("item__code", flat=True))
        reward_only = {a[6] for a in ACHIEVEMENTS if a[6]}
        extra = [i for c, i in items.items() if not i.is_starter and c not in in_drops and c not in reward_only]
        for n, item in enumerate(extra):
            DropEntry.objects.create(symbol=demo_symbols[n % len(demo_symbols)], item=item,
                                     weight=max(2, 12 - item.rarity * 2))

        # 既存の利用者にも、女の子用・男の子用の初期アイテムを配る
        starters = [i for i in items.values() if i.is_starter]
        for user in User.objects.all():
            for item in starters:
                UserItem.objects.get_or_create(user=user, item=item)

        # デモ用コンテスト (BOT 12 体つき。参加者が 10 人そろうまでの評価相手)
        contest, _ = Contest.objects.get_or_create(
            title="第1回 みっけコーデコンテスト",
            defaults=dict(theme="京橋さんぽで一番かわいいコーデ", starts_at=timezone.now() - dt.timedelta(hours=1),
                          ends_at=timezone.now() + dt.timedelta(days=30)),
        )
        bots_made = create_bots(contest, 12)

        for code, name, desc, icon, kind, th, item_code, coupon_code, order in ACHIEVEMENTS:
            Achievement.objects.update_or_create(code=code, defaults=dict(
                name=name, description=desc, icon=icon, kind=kind, threshold=th,
                reward_item=items.get(item_code), reward_coupon=coupons.get(coupon_code),
                sort_order=order, is_active=True))

        self.stdout.write(self.style.SUCCESS(
            f"投入完了: アイテム {len(items)} (女の子用 {sum(i.body_type == 'girl' for i in items.values())} / "
            f"男の子用 {sum(i.body_type == 'boy' for i in items.values())}) / 追加ドロップ {len(extra)} / "
            f"スポット {len(spots)} / シンボル {len(SYMBOLS)} / "
            f"クーポン {len(coupons)} / 実績 {len(ACHIEVEMENTS)} / コンテスト「{contest.title}」BOT 追加 {bots_made}"))

"""所持品の「手に入れたシンボル」(UserItem.found_symbol) と、それを使った「どこで手に入れたか」の表示。"""

from __future__ import annotations

import uuid
from decimal import Decimal
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from explore import finders
from explore.models import Discovery, DropEntry, Spot, Symbol
from rewards.models import Achievement, UserAchievement
from wardrobe.models import Item, UserItem
from wardrobe.services import grant_item

PW = "correct horse battery staple"


class ItemSymbolBase(TestCase):
    def setUp(self):
        cache.clear()
        self.viewer = User.objects.create_user("v@example.com", PW, "みるひと")
        self.owner = User.objects.create_user("o@example.com", PW, "もちぬし")
        self.spot = Spot.objects.create(slug="s", name="森の社", latitude=Decimal("34.69"), longitude=Decimal("135.53"))
        self.symbol = Symbol.objects.create(spot=self.spot, name="灯籠")
        self.secret = Symbol.objects.create(spot=self.spot, name="ひみつ", is_secret=True)
        self.coat = Item.objects.create(code="coat", name="もみじコート", category="top", style="tshirt", color="#C0392B")
        self.hat = Item.objects.create(code="hat", name="ぼうし", category="hair", style="bob", color="#222222")
        self.starter = Item.objects.create(code="st", name="はじめの服", category="top", style="tshirt",
                                           color="#FFFFFF", is_starter=True)
        DropEntry.objects.create(symbol=self.symbol, item=self.coat, weight=10, season="autumn")
        DropEntry.objects.create(symbol=self.secret, item=self.coat, weight=50)  # シークレットより公開のものを選ぶ


class FoundSymbolTests(ItemSymbolBase):
    def test_grant_records_first_symbol(self):
        other = Symbol.objects.create(spot=self.spot, name="狛犬")
        ui, created = grant_item(self.owner, self.coat, symbol=self.symbol)
        self.assertTrue(created)
        self.assertEqual(ui.found_symbol, self.symbol)
        ui, created = grant_item(self.owner, self.coat, symbol=other)  # 2 回目でも最初のシンボルのまま
        self.assertEqual((created, ui.obtained_count, ui.found_symbol), (False, 2, self.symbol))
        ui, _ = grant_item(self.owner, self.hat)  # みっけ以外 (シンボルなし)
        self.assertIsNone(ui.found_symbol)

    def test_obtained_info_uses_found_symbol_without_discovery(self):
        UserItem.objects.create(user=self.owner, item=self.coat, found_symbol=self.symbol)
        info = finders.obtained_info(self.owner, self.coat, self.viewer)
        self.assertTrue(info["text"].startswith("森の社でみっけ"))
        self.assertEqual(info["spot"]["id"], self.spot.pk)  # 「これをみっけに行く」で地図に出せる
        UserItem.objects.create(user=self.owner, item=self.hat, found_symbol=self.secret)
        info = finders.obtained_info(self.owner, self.hat, self.viewer)  # 見る人が見つけていないシークレットは伏せる
        self.assertTrue(info["text"].startswith("シークレットシンボルでみっけ"))
        self.assertIsNone(info["spot"])

    def test_link_command_backfills_from_discovery_then_drops(self):
        found_by_mikke = User.objects.create_user("m@example.com", PW, "みっけした人")
        Discovery.objects.create(user=found_by_mikke, symbol=self.symbol, reward_kind="item", reward_label="もみじコート",
                                 reward_ref="coat", idempotency_key=uuid.uuid4())
        UserItem.objects.create(user=found_by_mikke, item=self.coat)
        given = UserItem.objects.create(user=self.owner, item=self.coat)  # デモで直接持たせたもの
        orphan = Item.objects.create(code="orphan", name="迷子のリボン", category="accessory", style="ribbon",
                                     color="#FF0000")
        orphan_ui = UserItem.objects.create(user=self.owner, item=orphan)  # どこでも手に入らないアイテム
        starter_ui = UserItem.objects.create(user=self.owner, item=self.starter)
        ach = Achievement.objects.create(code="a", name="実績", description="-", kind="total_discoveries", threshold=1,
                                         reward_item=self.hat)
        UserAchievement.objects.create(user=self.owner, achievement=ach)
        reward_ui = UserItem.objects.create(user=self.owner, item=self.hat)
        self.assertIn("みっけ以外", finders.obtained_info(self.owner, self.coat, self.viewer)["text"])

        out = StringIO()
        call_command("link_item_symbols", "--dry-run", stdout=out)
        self.assertIn("結び付けられます", out.getvalue())
        self.assertFalse(UserItem.objects.filter(found_symbol__isnull=False).exists())  # dry-run は変えない

        call_command("link_item_symbols", stdout=StringIO())
        for ui in (given, orphan_ui, starter_ui, reward_ui):
            ui.refresh_from_db()
        self.assertEqual(UserItem.objects.get(user=found_by_mikke).found_symbol, self.symbol)
        self.assertEqual(given.found_symbol, self.symbol)  # シークレットではなく公開のシンボル
        from django.utils import timezone

        from core.timeutil import season_of

        self.assertEqual(season_of(timezone.localtime(given.first_obtained_at).date()), "autumn")  # ドロップの季節
        self.assertIsNotNone(orphan_ui.found_symbol)  # シンボルを作って結び付ける
        self.assertTrue(DropEntry.objects.filter(symbol=orphan_ui.found_symbol, item=orphan).exists())
        self.assertIsNone(starter_ui.found_symbol)  # はじめから持っているものは対象外
        self.assertIsNone(reward_ui.found_symbol)  # 実績のごほうびも対象外
        self.assertTrue(finders.obtained_info(self.owner, self.coat, self.viewer)["text"].startswith("森の社でみっけ"))
        self.assertEqual(finders.obtained_info(self.owner, self.hat, self.viewer)["text"], "実績のごほうび")
        self.assertEqual(Discovery.objects.count(), 1)  # みっけの記録は増やさない (分析の数は変わらない)


class GoToHintTests(ItemSymbolBase):
    """「これをみっけに行く」で、何を探せばいいか (目印のシンボル・ヒント・出る条件) を出す。"""

    def test_target_symbol_has_name_hint_position_and_conditions(self):
        self.symbol.hint = "鳥居の右の石灯籠"
        self.symbol.latitude, self.symbol.longitude = Decimal("34.6905"), Decimal("135.5305")
        self.symbol.save()
        UserItem.objects.create(user=self.owner, item=self.coat, found_symbol=self.symbol)
        sym = finders.obtained_info(self.owner, self.coat, self.viewer)["spot"]["symbol"]
        self.assertEqual((sym["name"], sym["hint"], sym["lat"], sym["lng"]), ("灯籠", "鳥居の右の石灯籠", 34.6905, 135.5305))
        self.assertEqual(sym["conditions"], ["秋限定"])
        self.assertTrue(sym["drops_here"])
        from core.timeutil import local_now, season_of

        self.assertEqual(sym["now"], season_of(local_now().date()) == "autumn")

    def test_no_conditions_when_drop_removed_and_no_symbol_when_hidden(self):
        UserItem.objects.create(user=self.owner, item=self.coat, found_symbol=self.symbol)
        DropEntry.objects.filter(symbol=self.symbol).delete()
        sym = finders.obtained_info(self.owner, self.coat, self.viewer)["spot"]["symbol"]
        self.assertEqual((sym["drops_here"], sym["conditions"]), (False, []))
        self.symbol.is_active = False  # 非公開のシンボルは目印にしない (スポットだけ案内)
        self.symbol.save()
        spot = finders.obtained_info(self.owner, self.coat, self.viewer)["spot"]
        self.assertIsNone(spot["symbol"])
        self.assertEqual(spot["name"], "森の社")

    def test_finder_api_includes_hint(self):
        self.symbol.hint = "鳥居の右"
        self.symbol.save()
        self.owner.share_activity = True
        self.owner.save()
        from wardrobe.models import AvatarConfig

        AvatarConfig.objects.create(user=self.owner, top=self.coat)
        UserItem.objects.create(user=self.owner, item=self.coat, found_symbol=self.symbol)
        token = finders.make_token(self.owner.pk, self.viewer.pk)
        self.client.force_login(self.viewer)
        from django.urls import reverse

        items = self.client.get(reverse("explore:api_finder", args=[token])).json()["items"]
        coat = next(i for i in items if i["code"] == "coat")
        self.assertEqual(coat["spot"]["symbol"]["hint"], "鳥居の右")

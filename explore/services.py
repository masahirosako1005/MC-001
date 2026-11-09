"""探索のドメインロジック: シンボルのスキャン判定と、ごほうびの受け取り。"""

from __future__ import annotations

import datetime as dt
import math
import re
import secrets
import uuid
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from core.timeutil import local_now, season_of, slot_of
from rewards.services import evaluate_achievements, issue_coupon
from wardrobe.services import grant_item

from .models import SYMBOL_PREFIX, Discovery, DropEntry, SpotVisit, Symbol

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
TICKET_SALT = "mikke.scan-ticket"
_rng = secrets.SystemRandom()


class ExploreError(Exception):
    code = "error"

    def __init__(self, message: str, **extra):
        super().__init__(message)
        self.message = message
        self.extra = extra


class UnknownSymbol(ExploreError):
    code = "unknown_symbol"


class InvalidTicket(ExploreError):
    code = "invalid_ticket"


class Cooldown(ExploreError):
    code = "cooldown"


class LocationRequired(ExploreError):
    code = "location_required"


class TooFar(ExploreError):
    code = "too_far"


def parse_payload(payload: str) -> str | None:
    if not isinstance(payload, str) or not payload.startswith(SYMBOL_PREFIX):
        return None
    token = payload[len(SYMBOL_PREFIX):]
    return token if TOKEN_RE.match(token) else None


def find_symbol(payload: str) -> Symbol:
    token = parse_payload(payload)
    symbol = (
        Symbol.objects.select_related("spot").filter(token=token, is_active=True, spot__is_active=True).first()
        if token else None
    )
    if symbol is None:
        raise UnknownSymbol("みっけシンボルではないようです。")
    return symbol


def next_available_at(user, symbol: Symbol) -> dt.datetime | None:
    last = Discovery.objects.filter(user=user, symbol=symbol).order_by("-found_at").values_list("found_at", flat=True).first()
    if last is None:
        return None
    nxt = last + dt.timedelta(hours=symbol.cooldown_hours)
    return nxt if nxt > timezone.now() else None


def make_ticket(user, symbol: Symbol) -> str:
    return signing.dumps({"u": user.pk, "s": symbol.pk}, salt=TICKET_SALT, compress=True)


def read_ticket(user, ticket: str) -> Symbol:
    try:
        data = signing.loads(ticket, salt=TICKET_SALT, max_age=settings.MIKKE_SCAN_TICKET_MAX_AGE)
    except signing.SignatureExpired as exc:
        raise InvalidTicket("時間がたちすぎました。もう一度シンボルをカメラに写してください。") from exc
    except signing.BadSignature as exc:
        raise InvalidTicket("読み取り情報が正しくありません。もう一度お試しください。") from exc
    if data.get("u") != user.pk:
        raise InvalidTicket("読み取り情報が正しくありません。もう一度お試しください。")
    symbol = Symbol.objects.select_related("spot").filter(pk=data.get("s"), is_active=True, spot__is_active=True).first()
    if symbol is None:
        raise UnknownSymbol("このシンボルは現在お休み中です。")
    return symbol


def scan(user, payload: str) -> dict:
    """カメラがシンボルを検知したときの判定。AR マークの種類と受け取り用チケットを返す。"""
    symbol = find_symbol(payload)
    nxt = next_available_at(user, symbol)
    return {
        "status": "cooldown" if nxt else "ready",
        "symbol": {"name": symbol.name, "spot": symbol.spot.name},
        "next_available_at": nxt.isoformat() if nxt else None,
        "requires_location": symbol.spot.require_location,
        "ticket": None if nxt else make_ticket(user, symbol),
    }


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """2 点間の距離 (ハーバサイン式)。"""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def check_location(symbol: Symbol, coords: tuple[float, float] | None) -> None:
    spot = symbol.spot
    if not spot.require_location:
        return
    if coords is None:
        raise LocationRequired("このスポットでは現地確認のため位置情報が必要です。位置情報の利用を許可してください。")
    d = distance_m(coords[0], coords[1], float(spot.latitude), float(spot.longitude))
    if d > spot.radius_m:
        raise TooFar("スポットから離れているようです。現地でもう一度お試しください。")


def candidate_drops(symbol: Symbol, *, season: str, slot: str, visit_days: int):
    return (
        DropEntry.objects.select_related("item", "coupon")
        .filter(symbol=symbol, season__in=["any", season], time_slot__in=["any", slot], min_visit_days__lte=visit_days)
        .filter(Q(item__isnull=True) | Q(item__is_active=True))
        .filter(Q(coupon__isnull=True) | Q(coupon__is_active=True))
    )


def pick_weighted(entries: list[DropEntry]) -> DropEntry | None:
    total = sum(e.weight for e in entries)
    if total <= 0:
        return None
    r = _rng.uniform(0, total)
    acc = 0.0
    for e in entries:
        acc += e.weight
        if r <= acc:
            return e
    return entries[-1]


@dataclass
class CollectResult:
    reward_kind: str
    label: str
    is_new: bool = False
    item: dict | None = None
    coupon: dict | None = None
    visit_days: int = 1
    is_revisit_day: bool = False
    achievements: list[dict] = field(default_factory=list)
    replay: bool = False
    symbol: dict | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _result_from_discovery(d: Discovery) -> CollectResult:
    res = CollectResult(reward_kind=d.reward_kind, label=d.reward_label, is_new=d.is_new, replay=True,
                        symbol={"name": d.symbol.name, "spot": d.symbol.spot.name})
    if d.reward_kind == "item":
        res.item = {"code": d.reward_ref, "name": d.reward_label}
    elif d.reward_kind == "coupon":
        res.coupon = {"id": d.reward_ref, "title": d.reward_label}
    return res


def collect(user, ticket: str, idempotency_key: str, coords: tuple[float, float] | None = None,
            now: dt.datetime | None = None) -> CollectResult:
    """AR マークをタップしたときの受け取り処理。

    - 同じ Idempotency-Key の再送には最初の結果を返す (二重付与しない)
    - 利用者単位で行ロックを取り、同時タップでもクールダウンをすり抜けない
    """
    try:
        idem = uuid.UUID(str(idempotency_key))
    except ValueError as exc:
        raise ExploreError("リクエストが正しくありません。") from exc
    now = now or timezone.now()

    with transaction.atomic():
        get_user_model().objects.select_for_update().filter(pk=user.pk).first()
        existing = Discovery.objects.select_related("symbol__spot").filter(user=user, idempotency_key=idem).first()
        if existing:
            return _result_from_discovery(existing)

        symbol = read_ticket(user, ticket)
        nxt = next_available_at(user, symbol)
        if nxt and nxt > now:
            raise Cooldown("このシンボルはもうみっけ済みです。時間をおいてまた来てね。",
                           next_available_at=nxt.isoformat())
        check_location(symbol, coords)

        local = local_now(now)
        season, slot = season_of(local.date()), slot_of(local)
        visit, created_visit = SpotVisit.objects.get_or_create(
            user=user, spot=symbol.spot, visit_date=local.date(), defaults={"season": season, "first_seen_at": now}
        )
        visit_days = SpotVisit.objects.filter(user=user, spot=symbol.spot).count()

        drop = pick_weighted(list(candidate_drops(symbol, season=season, slot=slot, visit_days=visit_days)))
        result = CollectResult(reward_kind="none", label="", visit_days=visit_days,
                               is_revisit_day=created_visit and visit_days > 1,
                               symbol={"name": symbol.name, "spot": symbol.spot.name})
        ref = ""
        if drop and drop.item_id:
            _, is_new = grant_item(user, drop.item)
            result.reward_kind, result.label, result.is_new = "item", drop.item.name, is_new
            result.item = {"code": drop.item.code, "name": drop.item.name, "category": drop.item.get_category_display(),
                           "rarity": drop.item.rarity, "new": is_new}
            ref = drop.item.code
        elif drop and drop.coupon_id:
            c = issue_coupon(user, drop.coupon, source=f"{symbol.spot.name}でみっけ", now=now)
            result.reward_kind, result.label, result.is_new = "coupon", drop.coupon.title, True
            result.coupon = {"id": str(c.pk), "title": drop.coupon.title, "shop": drop.coupon.shop_name,
                             "benefit": drop.coupon.benefit}
            ref = str(c.pk)
        try:
            with transaction.atomic():
                Discovery.objects.create(
                    user=user, symbol=symbol, drop=drop, reward_kind=result.reward_kind,
                    reward_label=result.label, reward_ref=ref, is_new=result.is_new,
                    idempotency_key=idem, found_at=now,
                )
        except IntegrityError as exc:  # 同一キーの競合 (ロックにより通常は起きない)
            raise ExploreError("処理が重複しました。もう一度お試しください。") from exc
        result.achievements = evaluate_achievements(user)
    return result

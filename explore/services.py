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
from django.db.models import F, Q
from django.utils import timezone

from core.timeutil import local_now, season_of, slot_of
from rewards.services import CouponNotDistributable, evaluate_achievements, issue_coupon
from wardrobe.services import grant_item

from .models import (
    SYMBOL_PREFIX,
    Discovery,
    DropEntry,
    NearbyVisit,
    SpotVisit,
    Symbol,
    new_symbol_token,
    spot_available_q,
)

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


class NotNearby(ExploreError):
    """受け取りの前に「近くのシンボルを探す」(api_nearby) で付近に来た記録がない。"""

    code = "not_nearby"


class ImplausibleTravel(ExploreError):
    """直前のみっけ地点から、ありえない速さで移動している (位置偽装の疑い)。"""

    code = "implausible_travel"


def parse_payload(payload: str) -> str | None:
    if not isinstance(payload, str) or not payload.startswith(SYMBOL_PREFIX):
        return None
    token = payload[len(SYMBOL_PREFIX):]
    return token if TOKEN_RE.match(token) else None


def find_symbol(payload: str) -> Symbol:
    token = parse_payload(payload)
    symbol = (
        Symbol.objects.select_related("spot")
        .filter(spot_available_q("spot__"), token=token, kind=Symbol.KIND_QR, is_active=True).first()
        if token else None
    )
    if symbol is None:
        raise UnknownSymbol("みっけシンボルではないようです。")
    return symbol


def next_available_at(user, symbol: Symbol, now: dt.datetime | None = None) -> dt.datetime | None:
    """次にみっけできる時刻 (クールダウン中でなければ None)。now は collect(now=) と同じ時刻を渡す。"""
    last = Discovery.objects.filter(user=user, symbol=symbol).order_by("-found_at").values_list("found_at", flat=True).first()
    if last is None:
        return None
    nxt = last + dt.timedelta(hours=symbol.cooldown_hours)
    return nxt if nxt > (now or timezone.now()) else None


def regenerate_token(symbol: Symbol) -> Symbol:
    """QR シンボルの識別トークンを作り直す (掲示物の差し替え)。古い QR は以後「シンボルではない」扱いになる。"""
    if symbol.kind != Symbol.KIND_QR:
        raise ExploreError("画像シンボルにはトークンがありません。")
    symbol.token = new_symbol_token()
    symbol.save(update_fields=["token"])
    return symbol


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
    symbol = (Symbol.objects.select_related("spot")
              .filter(spot_available_q("spot__"), pk=data.get("s"), is_active=True).first())
    if symbol is None:
        raise UnknownSymbol("このシンボルは現在お休み中です。")
    return symbol


def scan(user, payload: str) -> dict:
    """カメラが QR シンボルを検知したときの判定。AR マークの種類と受け取り用チケットを返す。"""
    return _scan_result(user, find_symbol(payload))


NOT_READABLE = "うまく読み取れませんでした。シンボル全体が写るようにしてください。"


def best_view_similarity(symbol: Symbol, observed: bytes) -> float:
    """登録されているすべての見え方のうち、最も近いものとの類似度 (0〜1)。"""
    from .image_symbols import similarity

    return max(
        (similarity(bytes(v.verify_patch), bytes(v.verify_mask), observed) for v in symbol.views.all()),
        default=0.0,
    )


def scan_image(user, symbol_id, patch_b64: str) -> dict:
    """カメラが画像シンボルを検知したときの判定。

    端末が映像から切り出した 32x32 パッチを、サーバーだけが持つ照合用パッチ (最大 9 角度) と比べ、
    類似度が設定値 (既定 65%) 以上なら一致とする。
    一致しなければ「シンボルではない」と同じ扱いにし、類似度の値は返さない (総当たりの手がかりを与えない)。
    """
    from .image_symbols import ImageSymbolError, decode_patch, is_match

    try:
        sid = int(symbol_id)
        observed = decode_patch(patch_b64)
    except (TypeError, ValueError, ImageSymbolError) as exc:
        raise UnknownSymbol(NOT_READABLE) from exc
    symbol = (
        Symbol.objects.select_related("spot").prefetch_related("views")
        .filter(spot_available_q("spot__"), pk=sid, kind=Symbol.KIND_IMAGE, is_active=True).first()
    )
    if symbol is None or not is_match(best_view_similarity(symbol, observed)):
        raise UnknownSymbol(NOT_READABLE)
    return _scan_result(user, symbol)


def image_symbol_catalog() -> list[dict]:
    """利用者の端末に配る画像シンボルの特徴量 (見え方ごと)。参照写真・照合用パッチ・マスクは含めない。"""
    from .models import SymbolView

    rows = (
        SymbolView.objects.filter(spot_available_q("symbol__spot__"), symbol__kind=Symbol.KIND_IMAGE,
                                  symbol__is_active=True)
        .only("symbol_id", "angle", "features").order_by("symbol_id", "angle")
    )
    return [{"id": v.symbol_id, "view": v.angle, **v.features} for v in rows]


@dataclass
class ViewUpload:
    """1 つの見え方の登録データ (スタッフの端末が作って送る)。"""

    jpeg: bytes
    features_raw: bytes
    patch_b64: str
    mask_b64: str | None = None


def _validated_view(angle: str, up: ViewUpload) -> dict:
    from .image_symbols import (
        ImageSymbolError,
        decode_mask,
        decode_patch,
        parse_features,
        validate_jpeg,
        validate_reference,
    )
    from .models import ANGLE_CHOICES

    label = dict(ANGLE_CHOICES)[angle]
    try:
        width, height = validate_jpeg(up.jpeg)
        features = parse_features(up.features_raw)
        patch = decode_patch(up.patch_b64)
        mask = decode_mask(up.mask_b64)
        validate_reference(patch, mask)
    except ImageSymbolError as exc:
        raise ImageSymbolError(f"【{label}】{exc}") from exc
    return dict(jpeg=up.jpeg, width=width, height=height, features=features,
                keypoint_count=len(features["kp"]), verify_patch=patch, verify_mask=mask)


@transaction.atomic
def save_symbol_views(symbol: Symbol, uploads: dict[str, ViewUpload], delete: list[str], created_by) -> Symbol:
    """画像シンボルの見え方を追加・置き換え・削除する。すべて検証してから一括で保存する。"""
    from .image_symbols import ImageSymbolError
    from .models import ANGLES, SymbolView

    unknown = [a for a in [*uploads, *delete] if a not in ANGLES]
    if unknown:
        raise ImageSymbolError("撮影角度の指定が正しくありません。")
    validated = {angle: _validated_view(angle, up) for angle, up in uploads.items()}
    SymbolView.objects.filter(symbol=symbol, angle__in=[a for a in delete if a not in uploads]).delete()
    for angle, data in validated.items():
        SymbolView.objects.update_or_create(symbol=symbol, angle=angle,
                                            defaults={**data, "created_by": created_by})
    if not SymbolView.objects.filter(symbol=symbol).exists():
        raise ImageSymbolError("少なくとも 1 つの角度の写真が必要です。")
    return symbol


@transaction.atomic
def register_image_symbol(*, spot, name: str, hint: str, cooldown_hours: int, uploads: dict[str, ViewUpload],
                          created_by, is_secret: bool = False) -> Symbol:
    """スタッフが撮影した写真 (最大 9 角度) を画像シンボルとして登録する。"""
    from .image_symbols import ImageSymbolError

    if not uploads:
        raise ImageSymbolError("少なくとも 1 つの角度の写真を撮影してください。")
    symbol = Symbol.objects.create(spot=spot, kind=Symbol.KIND_IMAGE, name=name, hint=hint,
                                   cooldown_hours=cooldown_hours, is_secret=is_secret)
    return save_symbol_views(symbol, uploads, [], created_by)


def _scan_result(user, symbol: Symbol) -> dict:
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


# ------------------------------------------------------------------ 現在地の近くのシンボル

def available_symbols(now=None):
    """いま探せるシンボル (シンボルが公開中で、スポットも公開期間内)。"""
    return Symbol.objects.select_related("spot").filter(spot_available_q("spot__", now), is_active=True)


def nearby_symbols(lat: float, lng: float, radius_m: float, now=None):
    """現在地から radius_m 以内のシンボル (近い順) と、いちばん近いシンボル (範囲外でも) を返す。"""
    found: list[tuple[Symbol, float]] = []
    nearest: tuple[Symbol, float] | None = None
    for s in available_symbols(now):
        loc = s.location
        if loc is None:  # 位置が未設定のシンボルは距離で判定できない
            continue
        d = distance_m(lat, lng, loc[0], loc[1])
        if nearest is None or d < nearest[1]:
            nearest = (s, d)
        if d <= radius_m:
            found.append((s, d))
    found.sort(key=lambda x: x[1])
    return found, nearest


CAMERA_ATTRIBUTION_MINUTES = 15  # 付近に来てから何分以内のカメラ起動を、そのスポットの利用と数えるか


def record_nearby_visit(user, spot_ids, now=None) -> None:
    """スポット付近に来たことを記録する (分析用)。同じ人・スポット・日・時間帯は 1 行にまとめて PV を数える。"""
    if not spot_ids:
        return
    now = now or timezone.now()
    local = local_now(now)
    date, slot, season = local.date(), slot_of(local), season_of(local.date())
    for sid in spot_ids:
        updated = NearbyVisit.objects.filter(user=user, spot_id=sid, date=date, slot=slot).update(
            page_views=F("page_views") + 1, last_at=now)
        if not updated:
            try:
                with transaction.atomic():
                    NearbyVisit.objects.create(user=user, spot_id=sid, date=date, slot=slot, season=season,
                                               first_at=now, last_at=now)
            except IntegrityError:  # 同時に作られた場合は加算にまわす
                NearbyVisit.objects.filter(user=user, spot_id=sid, date=date, slot=slot).update(
                    page_views=F("page_views") + 1, last_at=now)


def record_camera_start(user, now=None) -> int:
    """カメラ起動を、直前 (15 分以内) に付近に来たスポットの記録に数える。数えた行数を返す。"""
    now = now or timezone.now()
    since = now - dt.timedelta(minutes=CAMERA_ATTRIBUTION_MINUTES)
    return NearbyVisit.objects.filter(user=user, last_at__gte=since).update(camera_starts=F("camera_starts") + 1)


def drop_conditions(d: DropEntry) -> list[str]:
    """ドロップが出る条件の表示 (例: 「秋限定」「夜だけ」「2日目の訪問から」)。"""
    from core.timeutil import SEASON_LABELS, SLOT_LABELS

    conds = []
    if d.season != "any":
        conds.append(f"{SEASON_LABELS[d.season]}限定")
    if d.time_slot != "any":
        conds.append(f"{SLOT_LABELS[d.time_slot]}だけ")
    if d.min_visit_days > 1:
        conds.append(f"{d.min_visit_days}日目の訪問から")
    return conds


def obtainable_items(symbol: Symbol, now=None) -> list[dict]:
    """このシンボルで手に入るコーデ (アイテム)。季節・時間帯・再訪日数の条件と、いま出るかどうか付き。"""

    local = local_now(now)
    season, slot = season_of(local.date()), slot_of(local)
    items: dict[str, dict] = {}
    drops = (symbol.drops.select_related("item").filter(item__isnull=False, item__is_active=True)
             .order_by("min_visit_days", "item__rarity", "item__code"))
    for d in drops:
        it = d.item
        conds = drop_conditions(d)
        now_ok = d.season in ("any", season) and d.time_slot in ("any", slot)
        prev = items.get(it.code)
        if prev is None or (now_ok and not prev["now"]):
            items[it.code] = {"code": it.code, "name": it.name, "rarity": it.rarity,
                              "category": it.get_category_display(), "body_type": it.body_type,
                              "conditions": conds, "now": now_ok}
    return list(items.values())


def check_location(symbol: Symbol, coords: tuple[float, float] | None) -> float | None:
    """現地確認。端末の位置がシンボル (未設定ならスポット) の判定半径内か。距離 (m) を返す。確認しないスポットは None。"""
    spot = symbol.spot
    if not spot.require_location:
        return None
    loc = symbol.location
    if loc is None:  # 位置のないスポットは Spot.save() で require_location=False になるので通常は来ない
        return None
    if coords is None:
        raise LocationRequired("このスポットでは現地確認のため位置情報が必要です。位置情報の利用を許可してください。")
    d = distance_m(coords[0], coords[1], loc[0], loc[1])
    if d > spot.radius_m:
        raise TooFar("スポットから離れているようです。現地でもう一度お試しください。")
    return d


def check_presence(user, symbol: Symbol, now: dt.datetime) -> None:
    """受け取りの前に、画面の「近くのシンボルを探す」(api_nearby) でこのスポットの付近に来た記録があるか。

    位置そのものは端末の申告なので偽装は可能だが、「探す → 受け取る」の 2 段階を正しい順で踏ませることで
    保存済みの QR 文字列を自宅から送るだけの不正を止め、監査ログで追える形にする。
    """
    if not symbol.spot.require_location:
        return
    since = now - dt.timedelta(minutes=settings.MIKKE_PRESENCE_WINDOW_MINUTES)
    if not NearbyVisit.objects.filter(user=user, spot=symbol.spot, last_at__gte=since).exists():
        raise NotNearby("先に「近くのシンボルを探す」で現在地を確認してから、カメラでみっけしてください。")


def check_travel_speed(user, symbol: Symbol, now: dt.datetime) -> None:
    """直前のみっけ (別のスポット) からの移動速度が非現実的なら拒否する (位置偽装の疑い)。"""
    limit = settings.MIKKE_MAX_TRAVEL_SPEED_KMH
    here = symbol.location
    if not limit or here is None or not symbol.spot.require_location:
        return
    last = (Discovery.objects.filter(user=user, found_at__lte=now).exclude(symbol__spot=symbol.spot)
            .select_related("symbol__spot").order_by("-found_at").first())
    if last is None:
        return
    there = last.symbol.location
    hours = (now - last.found_at).total_seconds() / 3600
    if there is None or hours <= 0:
        return
    km = distance_m(here[0], here[1], there[0], there[1]) / 1000
    if km / hours > limit:
        raise ImplausibleTravel("直前のみっけから移動が速すぎるため、受け取れませんでした。しばらくしてからお試しください。")


def candidate_drops(symbol: Symbol, *, season: str, slot: str, visit_days: int, now=None):
    from rewards.models import distributable_coupons_q

    return (
        DropEntry.objects.select_related("item", "coupon")
        .filter(symbol=symbol, season__in=["any", season], time_slot__in=["any", slot], min_visit_days__lte=visit_days)
        .filter(Q(item__isnull=True) | Q(item__is_active=True))
        # 配布停止・有効期限切れのクーポンは出さない
        .filter(Q(coupon__isnull=True) | distributable_coupons_q("coupon__", now))
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
    symbol_id: int | None = None  # 「こんな人が獲得しているよ」を探すため (応答には含めない)
    spot_id: int | None = None  # 監査ログ用 (応答には含めない)
    distance_m: int | None = None  # 現地確認したときの距離。監査ログ用 (応答には含めない)

    def as_dict(self) -> dict:
        data = self.__dict__.copy()
        for k in ("symbol_id", "spot_id", "distance_m"):
            data.pop(k, None)
        return data


def _result_from_discovery(d: Discovery) -> CollectResult:
    res = CollectResult(reward_kind=d.reward_kind, label=d.reward_label, is_new=d.is_new, replay=True,
                        symbol={"name": d.symbol.name, "spot": d.symbol.spot.name}, symbol_id=d.symbol_id,
                        spot_id=d.symbol.spot_id)
    if d.reward_kind == "item":
        res.item = {"code": d.reward_ref, "name": d.reward_label, "new": d.is_new}
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
        nxt = next_available_at(user, symbol, now)
        if nxt:
            raise Cooldown("このシンボルはもうみっけ済みです。時間をおいてまた来てね。",
                           next_available_at=nxt.isoformat())
        # 現地確認: ①直前に「近くのシンボルを探す」で付近に来ている ②端末の位置が判定半径内 ③移動速度が現実的
        check_presence(user, symbol, now)
        distance = check_location(symbol, coords)
        check_travel_speed(user, symbol, now)

        local = local_now(now)
        season, slot = season_of(local.date()), slot_of(local)
        visit, created_visit = SpotVisit.objects.get_or_create(
            user=user, spot=symbol.spot, visit_date=local.date(), defaults={"season": season, "first_seen_at": now}
        )
        visit_days = SpotVisit.objects.filter(user=user, spot=symbol.spot).count()

        drop = pick_weighted(list(candidate_drops(symbol, season=season, slot=slot, visit_days=visit_days, now=now)))
        result = CollectResult(reward_kind="none", label="", visit_days=visit_days,
                               is_revisit_day=created_visit and visit_days > 1,
                               symbol={"name": symbol.name, "spot": symbol.spot.name}, symbol_id=symbol.pk,
                               spot_id=symbol.spot_id, distance_m=round(distance) if distance is not None else None)
        ref = ""
        item = drop.item if drop and drop.item_id else None
        if drop and drop.coupon_id:
            try:
                c = issue_coupon(user, drop.coupon, source=f"{symbol.spot.name}でみっけ", now=now)
            except CouponNotDistributable:
                # 抽選と発行のあいだに配布停止・期限切れになった場合は、クーポンの代わりにコーデを渡す (500 にしない)
                c, drop = None, None
            if c is not None:
                result.reward_kind, result.label, result.is_new = "coupon", c.template.title, True
                result.coupon = {"id": str(c.pk), "title": c.template.title, "shop": c.template.shop_name,
                                 "benefit": c.template.benefit}
                ref = str(c.pk)
        if drop is None:
            # 衣装全振り: ドロップが未設定・条件外でも「何もなし」にはせず、ふだん用のコーデを 1 つ渡す
            item = fallback_outfit(user)
        if item is not None:
            _, is_new = grant_item(user, item, symbol=symbol)
            result.reward_kind, result.label, result.is_new = "item", item.name, is_new
            result.item = {"code": item.code, "name": item.name, "category": item.get_category_display(),
                           "slot": item.category, "rarity": item.rarity, "new": is_new}
            ref = item.code
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


FALLBACK_MAX_RARITY = 2  # 季節限定などの特別なアイテムの価値を保つため、ふだん用はレア度 2 まで


def fallback_outfit(user):
    """ドロップが出ないときに渡す、ふだん用のコーデ。

    体のタイプに合うもの・まだ持っていないものを優先する。全部持っていたら持っているものから選ぶ
    (結果画面では「取得済み」と表示する)。
    """
    from wardrobe.models import AvatarConfig, Item, UserItem

    body = AvatarConfig.objects.filter(user=user).values_list("body_type", flat=True).first() or "girl"
    pool = Item.objects.filter(is_active=True, is_starter=False, body_type__in=["any", body])
    common = pool.filter(rarity__lte=FALLBACK_MAX_RARITY)
    owned = UserItem.objects.filter(user=user).values("item_id")
    for qs in (common.exclude(pk__in=owned), pool.exclude(pk__in=owned), common, pool):
        ids = list(qs.values_list("pk", flat=True))
        if ids:
            return Item.objects.get(pk=_rng.choice(ids))
    return None

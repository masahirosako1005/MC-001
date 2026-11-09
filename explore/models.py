from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.timeutil import SEASON_CHOICES, SLOT_CHOICES

SYMBOL_PREFIX = "MIKKE1:"


def new_symbol_token() -> str:
    return secrets.token_urlsafe(18)  # 24 文字・144bit: 推測不可能


def spot_available_q(prefix: str = "", now=None) -> models.Q:
    """公開中 (非公開でなく、公開開始後で、有効期限前) のスポットを表す条件。prefix は "spot__" など。"""
    now = now or timezone.now()
    return (models.Q(**{f"{prefix}is_active": True})
            & (models.Q(**{f"{prefix}starts_at__isnull": True}) | models.Q(**{f"{prefix}starts_at__lte": now}))
            & (models.Q(**{f"{prefix}expires_at__isnull": True}) | models.Q(**{f"{prefix}expires_at__gt": now})))


class SpotQuerySet(models.QuerySet):
    def available(self, now=None):
        return self.filter(spot_available_q("", now))


class Spot(models.Model):
    """観光スポット。"""

    slug = models.SlugField("スラッグ", max_length=64, unique=True)
    name = models.CharField("名前", max_length=80)
    area = models.CharField("エリア", max_length=80, blank=True)
    description = models.TextField("紹介文", blank=True)
    latitude = models.DecimalField("緯度", max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField("経度", max_digits=9, decimal_places=6, null=True, blank=True)
    radius_m = models.PositiveIntegerField("判定半径(m)", default=300)
    require_location = models.BooleanField(
        "現地確認を必須にする", default=False,
        help_text="ON のとき、受け取り時に端末の位置情報がスポットの判定半径内か確認します",
    )
    is_active = models.BooleanField("公開", default=True)
    starts_at = models.DateTimeField("公開開始", null=True, blank=True, help_text="空欄ならすぐに公開")
    expires_at = models.DateTimeField("有効期限", null=True, blank=True, help_text="空欄なら無期限")
    # 管理者 (店舗・会社) のスポット。空欄はサイト運営者のスポット。管理者は自分のスポットだけを設定できる
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="owned_spots", verbose_name="担当の管理者",
                              limit_choices_to={"role": "manager"})

    objects = SpotQuerySet.as_manager()

    class Meta:
        verbose_name = verbose_name_plural = "スポット"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(starts_at__isnull=True) | models.Q(expires_at__isnull=True)
                | models.Q(expires_at__gt=models.F("starts_at")),
                name="spot_period_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(latitude__isnull=True) | models.Q(latitude__gte=-90, latitude__lte=90),
                name="spot_lat_range",
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__isnull=True) | models.Q(longitude__gte=-180, longitude__lte=180),
                name="spot_lng_range",
            ),
            models.CheckConstraint(condition=models.Q(radius_m__gte=10), name="spot_radius_min"),
            models.CheckConstraint(
                condition=models.Q(require_location=False)
                | models.Q(latitude__isnull=False, longitude__isnull=False),
                name="spot_location_required_has_coords",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def status(self, now=None) -> str:
        """"active" (公開中) / "scheduled" (公開前) / "expired" (期限切れ) / "hidden" (非公開)。"""
        now = now or timezone.now()
        if not self.is_active:
            return "hidden"
        if self.starts_at and self.starts_at > now:
            return "scheduled"
        if self.expires_at and self.expires_at <= now:
            return "expired"
        return "active"

    def is_available(self, now=None) -> bool:
        return self.status(now) == "active"

    @property
    def status_label(self) -> str:
        return {"active": "公開中", "scheduled": "公開前", "expired": "期限切れ", "hidden": "非公開"}[self.status()]


class Symbol(models.Model):
    """「みっけシンボル」。カメラで検知すると AR マークが現れる。

    - kind="qr":    印刷して掲示する QR 型シンボル
    - kind="image": スタッフが撮影した看板・像などの写真そのもの (SymbolImage に特徴量を保持)
    """

    KIND_QR = "qr"
    KIND_IMAGE = "image"
    KIND_CHOICES = [(KIND_QR, "QR シンボル"), (KIND_IMAGE, "画像シンボル")]

    spot = models.ForeignKey(Spot, on_delete=models.PROTECT, related_name="symbols", verbose_name="スポット")
    kind = models.CharField("種類", max_length=8, choices=KIND_CHOICES, default=KIND_QR, editable=False)
    name = models.CharField("名前", max_length=80)
    hint = models.CharField("探すときのヒント", max_length=200, blank=True)
    token = models.CharField("識別トークン", max_length=64, unique=True, default=new_symbol_token, editable=False)
    cooldown_hours = models.PositiveSmallIntegerField(
        "再取得までの時間(時間)", default=20, help_text="同じ人が再びみっけできるまでの時間"
    )
    is_active = models.BooleanField("公開", default=True)
    is_secret = models.BooleanField(
        "シークレット", default=False,
        help_text="ON のとき、名前・ヒント・手に入るアイテムを「？」で隠す (見つけてからのお楽しみ)",
    )
    latitude = models.DecimalField("緯度", max_digits=9, decimal_places=6, null=True, blank=True,
                                   help_text="空欄ならスポットの位置を使う")
    longitude = models.DecimalField("経度", max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "シンボル"
        ordering = ["spot_id", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(cooldown_hours__gte=1), name="symbol_cooldown_pos"),
            models.CheckConstraint(condition=models.Q(kind__in=["qr", "image"]), name="symbol_kind_valid"),
            models.CheckConstraint(
                condition=(models.Q(latitude__isnull=True, longitude__isnull=True)
                           | models.Q(latitude__isnull=False, longitude__isnull=False,
                                      latitude__gte=-90, latitude__lte=90, longitude__gte=-180, longitude__lte=180)),
                name="symbol_coords_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.spot.name} / {self.name}"

    @property
    def location(self) -> tuple[float, float] | None:
        """シンボルの位置。未設定ならスポットの位置。"""
        if self.latitude is not None and self.longitude is not None:
            return float(self.latitude), float(self.longitude)
        if self.spot.latitude is not None and self.spot.longitude is not None:
            return float(self.spot.latitude), float(self.spot.longitude)
        return None

    @property
    def payload(self) -> str:
        return f"{SYMBOL_PREFIX}{self.token}"


ANGLE_CHOICES = [
    ("up_left", "左上から"), ("up", "上から"), ("up_right", "右上から"),
    ("left", "左から"), ("front", "正面"), ("right", "右から"),
    ("down_left", "左下から"), ("down", "下から"), ("down_right", "右下から"),
]
ANGLES = [a for a, _ in ANGLE_CHOICES]
MAX_VIEWS = len(ANGLES)  # 9 (正面を含む)


class SymbolView(models.Model):
    """画像シンボルの「1 つの見え方」(撮影角度ごとの参照データ)。1 シンボルにつき最大 9 角度。

    - jpeg: 四角形で切り抜き・正面補正した参照写真 (スタッフのみ閲覧可。EXIF なし)
    - features: ORB 特徴量 (塗りつぶした除外部分の点は含まない。利用者の端末に配布)
    - verify_patch / verify_mask: 32x32 の照合用パッチと除外マスク (サーバー内だけで使い、配布しない)
    """

    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="views")
    angle = models.CharField("撮影角度", max_length=12, choices=ANGLE_CHOICES)
    jpeg = models.BinaryField("参照写真 (JPEG)")
    width = models.PositiveIntegerField("幅")
    height = models.PositiveIntegerField("高さ")
    features = models.JSONField("特徴量")
    keypoint_count = models.PositiveIntegerField("特徴点の数")
    verify_patch = models.BinaryField("照合用パッチ")
    verify_mask = models.BinaryField("除外マスク", help_text="32x32 のビット列。1 = 判定しない部分")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", verbose_name="登録者")
    created_at = models.DateTimeField("登録日時", default=timezone.now)

    class Meta:
        verbose_name = verbose_name_plural = "画像シンボルの見え方"
        ordering = ["symbol_id", "angle"]
        constraints = [
            models.UniqueConstraint(fields=["symbol", "angle"], name="symbolview_unique_angle"),
            models.CheckConstraint(condition=models.Q(angle__in=ANGLES), name="symbolview_angle_valid"),
            models.CheckConstraint(condition=models.Q(width__gte=64, height__gte=64), name="symbolview_min_size"),
            models.CheckConstraint(condition=models.Q(keypoint_count__gte=30), name="symbolview_min_keypoints"),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} / {self.get_angle_display()} ({self.keypoint_count} 点)"


class DropEntry(models.Model):
    """シンボルから出るごほうびの抽選表。季節・時間帯・再訪日数で出現が変わる。"""

    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="drops")
    item = models.ForeignKey("wardrobe.Item", null=True, blank=True, on_delete=models.PROTECT,
                             related_name="drop_entries", verbose_name="アイテム")
    coupon = models.ForeignKey("rewards.CouponTemplate", null=True, blank=True, on_delete=models.PROTECT,
                               related_name="drop_entries", verbose_name="クーポン")
    weight = models.PositiveIntegerField("出やすさ(重み)", default=10)
    season = models.CharField("季節", max_length=8, choices=SEASON_CHOICES, default="any")
    time_slot = models.CharField("時間帯", max_length=8, choices=SLOT_CHOICES, default="any")
    min_visit_days = models.PositiveSmallIntegerField(
        "解放に必要な訪問日数", default=1, help_text="2 なら「2日目の訪問」から出現 (再訪ボーナス)"
    )

    class Meta:
        verbose_name = verbose_name_plural = "ドロップ設定"
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(item__isnull=False, coupon__isnull=True)
                           | models.Q(item__isnull=True, coupon__isnull=False)),
                name="drop_exactly_one_reward",
            ),
            models.CheckConstraint(condition=models.Q(weight__gte=1), name="drop_weight_pos"),
            models.CheckConstraint(condition=models.Q(min_visit_days__gte=1), name="drop_min_visit_pos"),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} → {self.item or self.coupon}"


class SpotVisit(models.Model):
    """スポットへの訪問日 (日本時間の日付単位)。再訪日数・季節の実績判定に使う。"""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="spot_visits")
    spot = models.ForeignKey(Spot, on_delete=models.PROTECT, related_name="visits")
    visit_date = models.DateField("訪問日")
    season = models.CharField("季節", max_length=8, choices=SEASON_CHOICES)
    first_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = verbose_name_plural = "訪問記録"
        constraints = [models.UniqueConstraint(fields=["user", "spot", "visit_date"], name="spotvisit_unique_day")]

    def __str__(self) -> str:
        return f"{self.visit_date} {self.spot_id}"


class NearbyVisit(models.Model):
    """スポット付近に来た記録 (分析用)。「近くのシンボルを探す」でスポットのシンボルが周囲にあったときに残す。

    残すのは「どのスポットの付近に、いつ (日付・時間帯・季節) 来たか」だけで、緯度経度は保存しない。
    同じ人・スポット・日・時間帯は 1 行にまとめ、検索回数 (PV) とカメラ起動回数を数える。
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="nearby_visits")
    spot = models.ForeignKey(Spot, on_delete=models.CASCADE, related_name="nearby_visits")
    date = models.DateField("日付 (日本時間)")
    slot = models.CharField("時間帯", max_length=8, choices=SLOT_CHOICES)
    season = models.CharField("季節", max_length=8, choices=SEASON_CHOICES)
    page_views = models.PositiveIntegerField("PV (検索回数)", default=1)
    camera_starts = models.PositiveIntegerField("カメラ起動回数", default=0)
    first_at = models.DateTimeField(default=timezone.now)
    last_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = verbose_name_plural = "スポット付近の来訪 (分析用)"
        constraints = [
            models.UniqueConstraint(fields=["user", "spot", "date", "slot"], name="nearbyvisit_unique_slot"),
        ]
        indexes = [models.Index(fields=["spot", "date"], name="nearbyvisit_spot_date_idx"),
                   models.Index(fields=["user", "-last_at"], name="nearbyvisit_recent_idx")]

    def __str__(self) -> str:
        return f"{self.date} {self.slot} spot={self.spot_id}"


class Discovery(models.Model):
    """みっけ (受け取り) の記録。ごほうびの内容をスナップショットとして残す (原本性)。"""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="discoveries")
    symbol = models.ForeignKey(Symbol, on_delete=models.PROTECT, related_name="discoveries")
    drop = models.ForeignKey(DropEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reward_kind = models.CharField(max_length=8, choices=[("item", "アイテム"), ("coupon", "クーポン"), ("none", "なし")])
    reward_label = models.CharField(max_length=120, blank=True)
    reward_ref = models.CharField(max_length=64, blank=True)
    is_new = models.BooleanField(default=False)
    idempotency_key = models.UUIDField()
    found_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = verbose_name_plural = "みっけ記録"
        ordering = ["-found_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "idempotency_key"], name="discovery_idempotent"),
        ]
        indexes = [models.Index(fields=["user", "symbol", "-found_at"], name="discovery_cooldown_idx")]

    def __str__(self) -> str:
        return f"{self.found_at:%Y-%m-%d %H:%M} {self.reward_label or '-'}"

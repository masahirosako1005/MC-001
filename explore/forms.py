from __future__ import annotations

from django import forms

from .image_symbols import MAX_FEATURES_BYTES, MAX_JPEG_BYTES, ImageSymbolError
from .models import ANGLES, MAX_VIEWS, Spot
from .services import ViewUpload


class ImageSymbolInfoForm(forms.Form):
    """画像シンボルの基本情報 (写真は角度ごとに JavaScript が送る)。"""

    # 公開前のスポットにも、前もってシンボルを登録できるようにする
    spot = forms.ModelChoiceField(label="スポット", queryset=Spot.objects.filter(is_active=True),
                                  empty_label="選んでください")
    name = forms.CharField(label="シンボルの名前", max_length=80,
                           help_text="例: 足湯の看板、駅前のからくり時計")
    hint = forms.CharField(label="探すときのヒント", max_length=200, required=False,
                           help_text="利用者のスポット一覧に表示されます")
    cooldown_hours = forms.IntegerField(label="再取得までの時間(時間)", min_value=1, max_value=24 * 30, initial=20)
    is_secret = forms.BooleanField(label="シークレットシンボルにする", required=False,
                                   help_text="地図やスポット一覧で、名前・ヒント・手に入るコーデを「？」で隠します")


_DT = {"type": "datetime-local"}


class SpotForm(forms.ModelForm):
    """スポットの追加・編集 (運営スタッフ用)。有効期限は空欄または「無期限」で無期限。"""

    no_expiry = forms.BooleanField(label="無期限にする", required=False, initial=True)

    class Meta:
        model = Spot
        fields = ["name", "area", "description", "latitude", "longitude", "radius_m", "require_location",
                  "is_active", "starts_at", "expires_at"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "latitude": forms.NumberInput(attrs={"step": "0.000001", "inputmode": "decimal"}),
            "longitude": forms.NumberInput(attrs={"step": "0.000001", "inputmode": "decimal"}),
            "starts_at": forms.DateTimeInput(attrs=_DT, format="%Y-%m-%dT%H:%M"),
            "expires_at": forms.DateTimeInput(attrs=_DT, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["no_expiry"].initial = self.instance.expires_at is None
        for f in ("starts_at", "expires_at"):
            self.fields[f].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]

    def clean(self):
        data = super().clean()
        if data.get("no_expiry"):
            data["expires_at"] = None
        start, end = data.get("starts_at"), data.get("expires_at")
        if start and end and end <= start:
            self.add_error("expires_at", "有効期限は公開開始より後の日時にしてください。")
        lat, lng = data.get("latitude"), data.get("longitude")
        if (lat is None) != (lng is None):
            self.add_error("longitude", "緯度と経度は両方入力するか、両方空欄にしてください。")
        if data.get("require_location") and (lat is None or lng is None):
            self.add_error("require_location", "現地確認を必須にするには、地図で位置を設定してください。")
        if data.get("radius_m") is not None and data["radius_m"] < 10:
            self.add_error("radius_m", "判定半径は 10 m 以上にしてください。")
        return data

    def save(self, commit=True):
        spot = super().save(commit=False)
        spot.expires_at = self.cleaned_data.get("expires_at")
        if not spot.slug:
            import secrets as _secrets

            spot.slug = f"spot-{_secrets.token_hex(4)}"
        if commit:
            spot.save()
        return spot


def collect_view_uploads(post, files) -> tuple[dict[str, ViewUpload], list[str]]:
    """multipart から角度ごとの登録データと削除指定を取り出す。

    角度 a ごとに: a_image (JPEG), a_features (JSON), a_patch (base64), a_mask (base64, 任意)
    """
    angles = [a for a in post.get("angles", "").split(",") if a]
    delete = [a for a in post.get("delete", "").split(",") if a]
    if len(set(angles)) != len(angles) or len(angles) > MAX_VIEWS or any(a not in ANGLES for a in angles + delete):
        raise ImageSymbolError("撮影角度の指定が正しくありません。")
    uploads: dict[str, ViewUpload] = {}
    for a in angles:
        image, feats, patch = files.get(f"{a}_image"), files.get(f"{a}_features"), post.get(f"{a}_patch", "")
        if image is None or feats is None or not patch:
            raise ImageSymbolError("写真のデータが足りません。撮影し直してください。")
        if image.size > MAX_JPEG_BYTES:
            raise ImageSymbolError("画像が大きすぎます (1.5MB まで)。")
        if feats.size > MAX_FEATURES_BYTES:
            raise ImageSymbolError("特徴量データが大きすぎます。")
        uploads[a] = ViewUpload(jpeg=image.read(), features_raw=feats.read(), patch_b64=patch[:4000],
                                mask_b64=post.get(f"{a}_mask", "")[:400] or None)
    return uploads, delete

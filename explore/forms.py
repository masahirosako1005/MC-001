from __future__ import annotations

from django import forms

from .image_symbols import MAX_FEATURES_BYTES, MAX_JPEG_BYTES, ImageSymbolError
from .models import ANGLES, MAX_VIEWS, Spot
from .services import ViewUpload


class ImageSymbolInfoForm(forms.Form):
    """画像シンボルの基本情報 (写真は角度ごとに JavaScript が送る)。"""

    spot = forms.ModelChoiceField(label="スポット", queryset=Spot.objects.filter(is_active=True),
                                  empty_label="選んでください")
    name = forms.CharField(label="シンボルの名前", max_length=80,
                           help_text="例: 足湯の看板、駅前のからくり時計")
    hint = forms.CharField(label="探すときのヒント", max_length=200, required=False,
                           help_text="利用者のスポット一覧に表示されます")
    cooldown_hours = forms.IntegerField(label="再取得までの時間(時間)", min_value=1, max_value=24 * 30, initial=20)


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

"""画像シンボル (カメラで撮影した看板・像などをそのままシンボルにする) の検証ロジック。

仕組み (docs/adr/0005-image-symbols.md):
- 登録時、スタッフの端末が参照画像から ORB 特徴量と 32x32 の照合用パッチを計算して送る
- 利用者の端末は特徴量だけを受け取り、カメラ映像の中で参照画像を探す (映像は送らない)
- 見つけたら、映像から切り出した 32x32 パッチだけをサーバーに送り、
  サーバーが保存済みパッチと類似度 (粗い解像度・位置ずれ許容の正規化相互相関) で照合する。
  1 シンボルにつき最大 9 角度の見え方を登録でき、最も近い見え方の類似度が 65% 以上なら一致
  → 照合用パッチは利用者に配らないため、現物を写さずに API だけで取得するのは困難

外部の画像処理ライブラリに依存せず (この環境ではネイティブ DLL がブロックされるため)、
JPEG のヘッダー解析と NCC は純粋な Python で行う。
"""

from __future__ import annotations

import base64
import binascii
import json
import math

from django.conf import settings

PATCH_SIZE = 32
PATCH_BYTES = PATCH_SIZE * PATCH_SIZE
MASK_BYTES = PATCH_BYTES // 8
DESC_BYTES = 32
MIN_KEYPOINTS = 30
MIN_VISIBLE_RATIO = 0.25  # 塗りつぶし (除外) は最大 75% まで
MAX_KEYPOINTS = 900
MAX_JPEG_BYTES = 1_500_000
MAX_FEATURES_BYTES = 300_000
MAX_IMAGE_EDGE = 2048
MIN_PATCH_STDDEV = 10.0


class ImageSymbolError(ValueError):
    """利用者・スタッフ向けメッセージを持つ検証エラー。"""


# ---- JPEG ---------------------------------------------------------------------------

_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def jpeg_dimensions(data: bytes) -> tuple[int, int]:
    """JPEG のマーカーを読み、(幅, 高さ) を返す。JPEG でなければ ImageSymbolError。"""
    if len(data) < 4 or data[:3] != b"\xff\xd8\xff":
        raise ImageSymbolError("画像は JPEG 形式である必要があります。")
    i = 2
    n = len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            raise ImageSymbolError("画像ファイルが壊れています。")
        marker = data[i + 1]
        if marker == 0xFF:  # パディング
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg_len = int.from_bytes(data[i + 2 : i + 4], "big")
        if seg_len < 2 or i + 2 + seg_len > n:
            raise ImageSymbolError("画像ファイルが壊れています。")
        if marker in _SOF_MARKERS:
            if seg_len < 7:
                raise ImageSymbolError("画像ファイルが壊れています。")
            h = int.from_bytes(data[i + 5 : i + 7], "big")
            w = int.from_bytes(data[i + 7 : i + 9], "big")
            return w, h
        if marker == 0xDA:  # SOS より前に SOF が無い
            break
        i += 2 + seg_len
    raise ImageSymbolError("画像のサイズを読み取れませんでした。")


def validate_jpeg(data: bytes) -> tuple[int, int]:
    if len(data) > MAX_JPEG_BYTES:
        raise ImageSymbolError("画像が大きすぎます (1.5MB まで)。")
    w, h = jpeg_dimensions(data)
    if not (64 <= w <= MAX_IMAGE_EDGE and 64 <= h <= MAX_IMAGE_EDGE):
        raise ImageSymbolError(f"画像の縦横は 64〜{MAX_IMAGE_EDGE} ピクセルにしてください。")
    return w, h


# ---- 特徴量 -------------------------------------------------------------------------

def parse_features(raw: bytes) -> dict:
    """端末が計算した特徴量 JSON を検証し、正規化した dict を返す。"""
    if len(raw) > MAX_FEATURES_BYTES:
        raise ImageSymbolError("特徴量データが大きすぎます。")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ImageSymbolError("特徴量データの形式が正しくありません。") from exc
    if not isinstance(data, dict) or data.get("v") != 1:
        raise ImageSymbolError("特徴量データの形式が正しくありません。")
    try:
        w, h = int(data["w"]), int(data["h"])
        kps = data["kp"]
        desc = base64.b64decode(data["desc"], validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error) as exc:
        raise ImageSymbolError("特徴量データの形式が正しくありません。") from exc
    if not (64 <= w <= 1024 and 64 <= h <= 1024) or not isinstance(kps, list):
        raise ImageSymbolError("特徴量データの形式が正しくありません。")
    if len(kps) < MIN_KEYPOINTS:
        raise ImageSymbolError(
            "画像の特徴が少なすぎます。模様や文字がはっきりした、平らなものを正面から撮影してください。"
        )
    if len(kps) > MAX_KEYPOINTS or len(desc) != len(kps) * DESC_BYTES:
        raise ImageSymbolError("特徴量データの形式が正しくありません。")
    clean = []
    for p in kps:
        if not (isinstance(p, list) and len(p) == 2):
            raise ImageSymbolError("特徴量データの形式が正しくありません。")
        x, y = float(p[0]), float(p[1])
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= w and 0 <= y <= h):
            raise ImageSymbolError("特徴量データの形式が正しくありません。")
        clean.append([round(x, 1), round(y, 1)])
    return {"v": 1, "w": w, "h": h, "kp": clean, "desc": base64.b64encode(desc).decode()}


# ---- 照合用パッチ ---------------------------------------------------------------------

def decode_patch(value: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise ImageSymbolError("照合データの形式が正しくありません。") from exc
    if len(raw) != PATCH_BYTES:
        raise ImageSymbolError("照合データの形式が正しくありません。")
    return raw


def decode_mask(value: str | None) -> bytes:
    """除外マスク (32x32 ビット、1 = 判定しない) をデコードする。未指定なら除外なし。"""
    if not value:
        return bytes(MASK_BYTES)
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise ImageSymbolError("塗りつぶしデータの形式が正しくありません。") from exc
    if len(raw) != MASK_BYTES:
        raise ImageSymbolError("塗りつぶしデータの形式が正しくありません。")
    return raw


def mask_to_list(mask: bytes) -> list[bool]:
    """True = 判定に使う (除外されていない) セル。"""
    return [not (mask[i >> 3] >> (7 - (i & 7)) & 1) for i in range(PATCH_BYTES)]


def _stats(values: list[float]) -> tuple[float, float]:
    n = len(values)
    mean = sum(values) / n
    return mean, math.sqrt(sum((v - mean) ** 2 for v in values) / n)


def validate_reference(patch: bytes, mask: bytes) -> None:
    use = mask_to_list(mask)
    visible = [patch[i] for i in range(PATCH_BYTES) if use[i]]
    if len(visible) < PATCH_BYTES * MIN_VISIBLE_RATIO:
        raise ImageSymbolError("塗りつぶした部分が多すぎます。判定に使う部分を全体の 1/4 以上残してください。")
    if _stats(visible)[1] < MIN_PATCH_STDDEV:
        raise ImageSymbolError("画像のメリハリが少なすぎます。明るい場所で、模様がはっきり写るように撮影してください。")


def ncc(a: bytes, b: bytes) -> float:
    """マスクなしの正規化相互相関 (-1〜1)。明るさ・コントラストの違いに強い。"""
    if len(a) != PATCH_BYTES or len(b) != PATCH_BYTES:
        return -1.0
    return _ncc(list(a), list(b))


def _ncc(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mx, sx = _stats(xs)
    my, sy = _stats(ys)
    if sx < 1e-6 or sy < 1e-6:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (len(xs) * sx * sy)


def _downsample(patch: bytes, use: list[bool]) -> tuple[list[float | None], list[float]]:
    """32x32 → 16x16。参照側は除外セルを除いた平均 (半分以上除外なら None)、観測側は単純平均。"""
    ref: list[float | None] = []
    obs: list[float] = []
    for by in range(16):
        for bx in range(16):
            idx = [(by * 2 + dy) * PATCH_SIZE + bx * 2 + dx for dy in (0, 1) for dx in (0, 1)]
            vis = [patch[i] for i in idx if use[i]]
            ref.append(sum(vis) / len(vis) if len(vis) >= 2 else None)
            obs.append(sum(patch[i] for i in idx) / 4)
    return ref, obs


def similarity(reference: bytes, mask: bytes, observed: bytes) -> float:
    """登録画像と、映像から切り出した画像の類似度 (0〜1)。

    距離・角度のずれにゆるく対応するため、16x16 に粗くした上で上下左右 1 マス (約 6%) の
    位置ずれを許し、その中の最大の正規化相互相関を返す。除外 (塗りつぶし) 部分は使わない。
    """
    if len(reference) != PATCH_BYTES or len(observed) != PATCH_BYTES:
        return 0.0
    use = mask_to_list(mask)
    ref16, _ = _downsample(reference, use)
    _, obs16 = _downsample(observed, [True] * PATCH_BYTES)
    best = 0.0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            xs: list[float] = []
            ys: list[float] = []
            for y in range(16):
                oy = y + dy
                if not 0 <= oy < 16:
                    continue
                for x in range(16):
                    ox = x + dx
                    r = ref16[y * 16 + x]
                    if r is None or not 0 <= ox < 16:
                        continue
                    xs.append(r)
                    ys.append(obs16[oy * 16 + ox])
            if len(xs) >= 40:
                best = max(best, _ncc(xs, ys))
    return best


def is_match(score: float) -> bool:
    return score >= settings.MIKKE_IMAGE_SIMILARITY_THRESHOLD

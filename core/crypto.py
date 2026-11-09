"""アプリケーション層でのフィールド暗号化 (DB 暗号化) ユーティリティ。

- AES-256-GCM (認証付き暗号) でカラム値を暗号化する。改ざんは復号時に検知される。
- 関連データ (AAD) に「テーブル.カラム」を含め、暗号文を別カラムへ移し替える攻撃を防ぐ。
- 暗号文の先頭に鍵 ID を付け、鍵ローテーションに対応する (複数鍵で復号、先頭鍵で暗号化)。
- 検索が必要な値 (メールアドレス) は HMAC-SHA256 のブラインドインデックスで照合する。

鍵は環境変数 MIKKE_FIELD_KEYS / MIKKE_BLIND_INDEX_KEY から読み込み、コードやDBには置かない。
詳細: docs/adr/0002-db-encryption.md
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import unicodedata
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

PREFIX = "enc"
NONCE_BYTES = 12


class DecryptionError(Exception):
    """暗号文の改ざん・鍵不一致など、復号できない場合に送出する。"""


def _decode_key(raw: str) -> bytes:
    key = base64.urlsafe_b64decode(raw.encode())
    if len(key) != 32:
        raise ImproperlyConfigured("暗号鍵は 32 バイト (AES-256) である必要があります")
    return key


@lru_cache(maxsize=1)
def _keyring() -> tuple[str, dict[str, bytes]]:
    spec = getattr(settings, "MIKKE_FIELD_KEYS", "")
    if not spec:
        raise ImproperlyConfigured("MIKKE_FIELD_KEYS が設定されていません")
    keys: dict[str, bytes] = {}
    order: list[str] = []
    for item in spec.split(","):
        kid, _, raw = item.strip().partition(":")
        if not kid or not raw or not kid.isalnum():
            raise ImproperlyConfigured("MIKKE_FIELD_KEYS の形式は '鍵ID:base64鍵,...' です")
        keys[kid] = _decode_key(raw)
        order.append(kid)
    return order[0], keys


@lru_cache(maxsize=1)
def _blind_key() -> bytes:
    raw = getattr(settings, "MIKKE_BLIND_INDEX_KEY", "")
    if not raw:
        raise ImproperlyConfigured("MIKKE_BLIND_INDEX_KEY が設定されていません")
    return _decode_key(raw)


def reset_key_cache() -> None:
    """テストや鍵ローテーション時に鍵キャッシュを破棄する。"""
    _keyring.cache_clear()
    _blind_key.cache_clear()


def encrypt(plaintext: str, context: str) -> str:
    kid, keys = _keyring()
    nonce = os.urandom(NONCE_BYTES)
    ct = AESGCM(keys[kid]).encrypt(nonce, plaintext.encode("utf-8"), context.encode())
    token = base64.urlsafe_b64encode(nonce + ct).decode()
    return f"{PREFIX}:{kid}:{token}"


def decrypt(stored: str, context: str) -> str:
    try:
        prefix, kid, token = stored.split(":", 2)
    except ValueError as exc:
        raise DecryptionError("暗号文の形式が不正です") from exc
    if prefix != PREFIX:
        raise DecryptionError("暗号文の形式が不正です")
    _, keys = _keyring()
    key = keys.get(kid)
    if key is None:
        raise DecryptionError(f"鍵ID {kid} が見つかりません")
    blob = base64.urlsafe_b64decode(token.encode())
    try:
        pt = AESGCM(key).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], context.encode())
    except Exception as exc:  # cryptography.exceptions.InvalidTag
        raise DecryptionError("暗号文の検証に失敗しました (改ざんまたは鍵不一致)") from exc
    return pt.decode("utf-8")


def needs_rotation(stored: str) -> bool:
    current, _ = _keyring()
    return not stored.startswith(f"{PREFIX}:{current}:")


def normalize_email(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip().lower()


def blind_index(value: str, purpose: str) -> str:
    """検索用の決定的ハッシュ。purpose ごとに異なる値になる。"""
    msg = f"{purpose}\x00{value}".encode()
    return hmac.new(_blind_key(), msg, hashlib.sha256).hexdigest()

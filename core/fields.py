"""暗号化してDBに保存するモデルフィールド。"""

from __future__ import annotations

from django.core.exceptions import FieldError
from django.db import models

from . import crypto


class EncryptedTextField(models.TextField):
    """AES-256-GCM で暗号化して保存するテキストフィールド。

    - DB には ``enc:<鍵ID>:<base64(nonce+暗号文+タグ)>`` 形式で保存される
    - 暗号化は非決定的なので、等価検索・並び替えはできない (isnull のみ許可)
      検索が必要な場合はブラインドインデックス列を別に持つこと
    """

    description = "暗号化テキスト (AES-256-GCM)"

    def _context(self) -> str:
        return f"{self.model._meta.label_lower}.{self.name}"

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return crypto.decrypt(value, self._context())

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None:
            return None
        return crypto.encrypt(str(value), self._context())

    def get_lookup(self, lookup_name):
        if lookup_name != "isnull":
            raise FieldError(f"暗号化フィールド {self.name} では '{lookup_name}' 検索はできません")
        return super().get_lookup(lookup_name)

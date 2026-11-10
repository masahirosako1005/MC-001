from __future__ import annotations

from django import forms

from accounts.models import ManagerProfile, User, email_hash_of
from signage.models import Signage


class ManagerAccountForm(forms.Form):
    """管理者 (店舗・会社の担当者) のアカウント。サイト運営者が追加する。"""

    email = forms.EmailField(label="ログイン用メールアドレス", max_length=254,
                             widget=forms.EmailInput(attrs={"autocomplete": "off"}))
    nickname = forms.CharField(label="画面に表示する名前", max_length=30, help_text="例: 京橋商店 田中")

    def __init__(self, *args, instance: User | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        if instance is not None:
            self.fields["email"].initial = instance.email
            self.fields["nickname"].initial = instance.nickname

    def clean_email(self):
        email = self.cleaned_data["email"]
        qs = User.objects.filter(email_hash=email_hash_of(email))
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("このメールアドレスは、すでにほかのアカウントで使われています。")
        return email


class ManagerProfileForm(forms.ModelForm):
    class Meta:
        model = ManagerProfile
        fields = ["organization", "store_name", "industry", "contact_name", "postal_code", "address", "phone",
                  "website", "note"]
        widgets = {
            "address": forms.TextInput(attrs={"autocomplete": "off"}),
            "phone": forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "off"}),
            "postal_code": forms.TextInput(attrs={"inputmode": "numeric", "placeholder": "534-0024"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        digits = phone.replace("-", "").replace(" ", "")
        if phone and (not digits.isdigit() or not 9 <= len(digits) <= 11):
            raise forms.ValidationError("電話番号は数字とハイフンで入力してください(例: 06-1234-5678)。")
        return phone

    def clean_postal_code(self):
        code = (self.cleaned_data.get("postal_code") or "").strip()
        if code and len(code) == 7 and code.isdigit():
            code = f"{code[:3]}-{code[3:]}"
        return code


class SignageForm(forms.ModelForm):
    """まちのサイネージの内容 (見出し・宣伝の文・QR コード・更新間隔)。"""

    class Meta:
        model = Signage
        fields = ["name", "headline", "message", "show_qr", "qr_url", "refresh_seconds", "is_active"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 4, "maxlength": 200,
                                             "placeholder": "例: 京橋のまちを歩いて、季節のコーデをみっけしよう!"}),
            "qr_url": forms.URLInput(attrs={"placeholder": "https://…"}),
        }

    def clean_qr_url(self):
        url = (self.cleaned_data.get("qr_url") or "").strip()
        if url and not url.lower().startswith(("https://", "http://")):
            raise forms.ValidationError("http:// か https:// で始まる URL を入れてください。")
        return url

    def clean_message(self):
        msg = (self.cleaned_data.get("message") or "").replace("\r\n", "\n").strip()
        if len(msg) > 200:
            raise forms.ValidationError("宣伝の文は 200 文字以内にしてください。")
        return msg

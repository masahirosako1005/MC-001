from __future__ import annotations

from django import forms

from accounts.models import ManagerProfile, User, email_hash_of


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

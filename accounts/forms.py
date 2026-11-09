from __future__ import annotations

from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from core import ratelimit

from .models import User, email_hash_of


class SignupForm(forms.Form):
    nickname = forms.CharField(
        label="ニックネーム", max_length=30,
        help_text="ほかの人には表示されません。あとから変更できます。",
        widget=forms.TextInput(attrs={"autocomplete": "nickname"}),
    )
    email = forms.EmailField(
        label="メールアドレス", max_length=254,
        help_text="ログインに使います。暗号化して保存します。",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "inputmode": "email"}),
    )
    password1 = forms.CharField(
        label="パスワード", strip=False,
        help_text="15文字以上。単語を組み合わせた合言葉(例: そらいろ-かもめ-しおかぜ)が覚えやすく安全です。",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="パスワード(確認)", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email_hash=email_hash_of(email)).exists():
            raise forms.ValidationError("このメールアドレスはすでに登録されています。ログインしてください。")
        return email

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "確認用パスワードが一致しません。もう一度入力してください。")
        if p1:
            probe = User(email=data.get("email", ""), nickname=data.get("nickname", ""))
            try:
                password_validation.validate_password(p1, probe)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return data

    def save(self) -> User:
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            nickname=self.cleaned_data["nickname"],
        )


class ThrottledLoginForm(AuthenticationForm):
    """メールアドレスでログイン。連続失敗でアカウント単位・IP 単位に一時ロックする。"""

    username = forms.EmailField(
        label="メールアドレス",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "メールアドレスまたはパスワードが違います。入力内容を確かめてください。",
        "locked": "ログインの失敗が続いたため、しばらくログインできません。15分ほど待ってからお試しください。",
    }

    def _keys(self) -> list[str]:
        email = self.data.get("username", "")
        ip = self.request.META.get("REMOTE_ADDR", "") if self.request else ""
        return [f"login:acct:{email_hash_of(email)}", f"login:ip:{ip}"]

    def clean(self):
        limit = settings.MIKKE_LOGIN_MAX_FAILURES
        keys = self._keys()
        if any(ratelimit.count(k) >= limit for k in keys):
            raise forms.ValidationError(self.error_messages["locked"], code="locked")
        try:
            return super().clean()
        except forms.ValidationError:
            for k in keys:
                ratelimit.hit(k, limit, settings.MIKKE_LOGIN_LOCK_SECONDS)
            raise

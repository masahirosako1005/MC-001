from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import redirect, render, resolve_url
from django.views.decorators.http import require_GET, require_http_methods

from core import audit
from wardrobe.services import ensure_starter_kit

from .forms import NicknameForm, SignupForm, ThrottledLoginForm, WithdrawForm


class MikkeLoginView(LoginView):
    """利用者・管理者のログイン (サイト運営者は専用のログイン画面を使う)。"""

    template_name = "accounts/login.html"
    authentication_form = ThrottledLoginForm
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        return resolve_url(home_url_name(self.request.user))


@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("core:home")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            ensure_starter_kit(user)
            audit.record("account.signup", request=request, actor=user, target=user)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "ようこそ「みっけ」へ!まずはアバターの服を選んでみましょう。")
        return redirect("wardrobe:index")
    return render(request, "accounts/signup.html", {"form": form})


@require_GET
def password_help(request):
    """パスワードを忘れた方へ。メール送信の仕組みがないため、サイト運営者が本人確認のうえ仮パスワードを発行する。"""
    return render(request, "accounts/password_help.html", {"support": settings.MIKKE_SUPPORT_CONTACT})


@login_required
@require_http_methods(["GET", "POST"])
def account(request):
    """アカウント: ニックネームの変更、パスワード変更・退会への入口。"""
    form = NicknameForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit.record("account.update", request=request, target=request.user,
                     share_activity=request.user.share_activity)
        messages.success(request, "アカウントの設定を保存しました。")
        return redirect("accounts:account")
    return render(request, "accounts/account.html", {"form": form})


def home_url_name(user) -> str:
    """ログイン後・パスワード変更後に戻る画面 (利用者・管理者・サイト運営者で別の画面)。"""
    if user.is_operator:
        return "ops:dashboard"
    if user.is_manager:
        return "manage:home"
    return "core:home"


@login_required
@require_http_methods(["GET", "POST"])
def password_change(request):
    return change_password(request)


def change_password(request):
    """パスワード変更 (利用者側・運営側の両方から使う。権限の確認は呼び出し側で行う)。"""
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        if user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=["must_change_password"])
        update_session_auth_hash(request, user)  # ほかの端末のログインは切れ、この端末はそのまま
        audit.record("account.password_change", request=request, target=user)
        messages.success(request, "パスワードを変更しました。")
        return redirect(home_url_name(user))
    return render(request, "accounts/password_change.html", {
        "form": form, "forced": request.user.must_change_password,
    })


@login_required
@require_http_methods(["GET", "POST"])
def withdraw(request):
    """退会。利用者本人だけができる (管理者・サイト運営者のアカウントはサイト運営者が停止する)。"""
    user = request.user
    if user.role != user.ROLE_USER:
        return render(request, "accounts/withdraw.html", {"blocked": True}, status=403)
    form = WithdrawForm(request.POST or None, user=user)
    if request.method == "POST" and form.is_valid():
        uid = user.pk
        with transaction.atomic():
            # 監査ログには ID だけを残す (メールアドレスなどの個人情報は残さない)
            audit.record("account.withdraw", request=request, actor=None, user_id=uid)
            logout(request)
            user.delete()  # 記録・アイテム・クーポン・コンテスト参加もまとめて削除される
        messages.success(request, "退会しました。ご利用ありがとうございました。")
        return redirect("core:home")
    return render(request, "accounts/withdraw.html", {"form": form})

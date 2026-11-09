from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core import audit
from wardrobe.services import ensure_starter_kit

from .forms import SignupForm, ThrottledLoginForm


class MikkeLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = ThrottledLoginForm
    redirect_authenticated_user = True


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

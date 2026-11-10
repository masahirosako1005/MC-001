"""サイト運営者の画面: 専用ログイン・分析・利用者管理 (追加できるのは管理者だけ)。"""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.forms import OperatorLoginForm
from accounts.models import ManagerProfile, User, email_hash_of
from accounts.views import change_password
from core import audit
from core.ids import temp_password
from core.permissions import operator_required
from core.timeutil import SEASON_LABELS, SLOT_LABELS
from rewards import stats as coupon_stats

from . import analytics, charts
from .forms import ManagerAccountForm, ManagerProfileForm

FUNNEL = [("visitors", "付近に来た"), ("camera", "カメラ起動"), ("coord", "コーデ獲得")]


def _temp_password() -> str:
    return temp_password()


class OperatorLoginView(LoginView):
    """サイト運営者専用のログイン画面 (利用者・管理者はここからはログインできない)。"""

    template_name = "ops/login.html"
    authentication_form = OperatorLoginForm
    redirect_authenticated_user = False

    def get_default_redirect_url(self):
        return reverse("ops:dashboard")

    def get_context_data(self, **kwargs):
        hours = settings.OPS_SESSION_SECONDS / 3600
        return {**super().get_context_data(**kwargs), "ops_hours": int(hours) if hours.is_integer() else round(hours, 1)}

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session.set_expiry(settings.OPS_SESSION_SECONDS)
        audit.record("ops.login", request=self.request, target=form.get_user())
        return response


# ---------------------------------------------------------------- 分析
@operator_required
@require_GET
def dashboard(request):
    f = analytics.Filters.from_query(request.GET)
    data = analytics.compute(f)
    top = [r for r in data["spots"] if r["visitors"] or r["coord"]][:15]
    owners = (User.objects.filter(role=User.ROLE_MANAGER, owned_spots__isnull=False)
              .select_related("manager_profile").distinct().order_by("pk"))
    return render(request, "ops/dashboard.html", {
        "f": f, "data": data, "periods": analytics.PERIODS, "sorts": analytics.SORTS, "owners": owners,
        "seasons": [(k, SEASON_LABELS[k]) for k in analytics.SEASONS],
        "slots": [(k, SLOT_LABELS[k]) for k in analytics.SLOTS],
        "funnel": FUNNEL,
        "spot_chart": charts.grouped_hbar(
            [{"label": r["spot"].name, **r} for r in top], FUNNEL,
            title="スポットごとの、付近に来た人・カメラを起動した人・コーデを獲得した人の数"),
        "slot_chart": charts.grouped_vbar(data["by_slot"], FUNNEL, title="時間帯ごとの人数"),
        "season_chart": charts.grouped_vbar(data["by_season"], FUNNEL, title="季節ごとの人数"),
        "slot_rate_chart": charts.rate_vbar(data["by_slot"], key="rate", title="時間帯ごとの利用割合"),
        "season_rate_chart": charts.rate_vbar(data["by_season"], key="rate", title="季節ごとの利用割合"),
        "chart_count": len(top),
    })


# ---------------------------------------------------------------- 店舗ごとのクーポン利用
@operator_required
@require_GET
def coupons(request):
    """店舗 (管理者) ごとの、クーポンの配布・使用枚数と使用金額。"""
    period = coupon_stats.Period.from_query(request.GET)
    rows = coupon_stats.store_rows(period)
    chart_rows = [r for r in rows if r["amount"] or r["used"]][:15]
    return render(request, "ops/coupons.html", {
        "period": period, "periods": coupon_stats.PERIODS, "rows": rows, "totals": coupon_stats.totals(rows),
        "amount_chart": charts.grouped_hbar(chart_rows, [("amount", "使用金額")], unit="円",
                                            title="店舗ごとのクーポン使用金額"),
        "used_chart": charts.grouped_hbar(chart_rows, [("used", "使用枚数")], unit="枚",
                                          title="店舗ごとのクーポン使用枚数"),
        "chart_count": len(chart_rows),
    })


# ---------------------------------------------------------------- 運営者のアカウント
@operator_required
@require_http_methods(["GET", "POST"])
def password_change(request):
    return change_password(request)


# ---------------------------------------------------------------- 利用者管理
@operator_required
@require_GET
def user_list(request):
    role = request.GET.get("role", "")
    q = request.GET.get("q", "").strip()[:100]
    users = User.objects.select_related("manager_profile").annotate(n_spots=Count("owned_spots")).order_by("-date_joined")
    if role in dict(User.ROLE_CHOICES):
        users = users.filter(role=role)
    if q:
        # メールアドレスは暗号化しているので完全一致 (ブラインドインデックス) で探す
        users = users.filter(Q(nickname__icontains=q) | Q(email_hash=email_hash_of(q))
                             | Q(manager_profile__organization__icontains=q)
                             | Q(manager_profile__store_name__icontains=q)
                             | Q(manager_profile__manager_code__iexact=q))
    page = Paginator(users, 50).get_page(request.GET.get("page"))
    counts = dict(User.objects.values_list("role").annotate(n=Count("id")))
    return render(request, "ops/users.html", {
        "page": page, "role": role, "q": q, "roles": User.ROLE_CHOICES,
        "counts": {k: counts.get(k, 0) for k, _ in User.ROLE_CHOICES},
    })


@operator_required
@require_http_methods(["GET", "POST"])
def manager_create(request):
    account = ManagerAccountForm(request.POST or None)
    profile = ManagerProfileForm(request.POST or None)
    if request.method == "POST" and account.is_valid() and profile.is_valid():
        password = _temp_password()
        with transaction.atomic():
            user = User.objects.create_user(
                email=account.cleaned_data["email"], password=password, nickname=account.cleaned_data["nickname"],
                role=User.ROLE_MANAGER, must_change_password=True,
            )
            prof = profile.save(commit=False)
            prof.user = user
            prof.created_by = request.user
            prof.save()
            audit.record("ops.manager_create", request=request, target=user, manager_code=prof.manager_code)
        # 仮パスワードはこの画面で 1 度だけ表示する (保存も送信もしない)
        return render(request, "ops/manager_issued.html", {"manager": user, "profile": prof, "password": password,
                                                           "created": True})
    return render(request, "ops/manager_form.html", {"account": account, "profile": profile, "manager": None})


def _manager_or_404(pk: int) -> User:
    return get_object_or_404(User.objects.select_related("manager_profile"), pk=pk, role=User.ROLE_MANAGER)


@operator_required
@require_http_methods(["GET", "POST"])
def manager_edit(request, pk: int):
    manager = _manager_or_404(pk)
    prof, _ = ManagerProfile.objects.get_or_create(user=manager, defaults={"organization": manager.nickname,
                                                                           "contact_name": manager.nickname})
    account = ManagerAccountForm(request.POST or None, instance=manager)
    profile = ManagerProfileForm(request.POST or None, instance=prof)
    if request.method == "POST" and account.is_valid() and profile.is_valid():
        with transaction.atomic():
            manager.email = account.cleaned_data["email"]
            manager.nickname = account.cleaned_data["nickname"]
            manager.save()
            profile.save()
            audit.record("ops.manager_update", request=request, target=manager, fields=sorted(profile.changed_data))
        messages.success(request, f"管理者「{prof.display_name}」の情報を保存しました。")
        return redirect("ops:users")
    spots = manager.owned_spots.annotate(n_symbols=Count("symbols")).order_by("name")
    return render(request, "ops/manager_form.html", {"account": account, "profile": profile, "manager": manager,
                                                     "spots": spots})


@operator_required
@require_POST
def user_reset_password(request, pk: int):
    """仮パスワードの再発行 (パスワードを忘れた利用者・管理者から依頼があったとき)。サイト運営者のアカウントは対象外。"""
    target = get_object_or_404(User.objects.select_related("manager_profile"), pk=pk,
                               role__in=[User.ROLE_USER, User.ROLE_MANAGER])
    password = _temp_password()
    target.set_password(password)
    target.must_change_password = True
    target.save()
    audit.record("ops.reset_password", request=request, target=target, role=target.role)
    return render(request, "ops/manager_issued.html", {
        "manager": target, "profile": getattr(target, "manager_profile", None), "password": password, "created": False,
    })


@operator_required
@require_POST
def user_toggle_active(request, pk: int):
    """利用停止 / 再開。サイト運営者のアカウントはここでは止められない (誤操作で締め出されないように)。"""
    target = get_object_or_404(User, pk=pk)
    if target.is_operator:
        messages.error(request, "サイト運営者のアカウントは、ここでは停止できません。")
        return redirect("ops:users")
    target.is_active = not target.is_active
    target.save(update_fields=["is_active"])
    audit.record("ops.user_activate" if target.is_active else "ops.user_suspend", request=request, target=target)
    messages.success(request, f"「{target.nickname}」を{'利用再開' if target.is_active else '利用停止'}にしました。")
    back = request.POST.get("next", "")
    return redirect(back if back.startswith(reverse("ops:users")) else "ops:users")

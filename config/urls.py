from django.conf import settings
from django.contrib import admin
from django.urls import include, path, reverse_lazy
from django.views.generic import RedirectView

admin.site.site_header = "みっけ 運営管理"
admin.site.site_title = "みっけ 運営管理"

urlpatterns = [
    # Django 管理画面のログインは使わず、サイト運営者専用のログイン画面に集約する
    path(settings.ADMIN_URL + "login/", RedirectView.as_view(url=reverse_lazy("ops:login"), query_string=True)),
    path(settings.ADMIN_URL, admin.site.urls),
    # 設定画面 (スポット・シンボル・クーポン): サイト運営者は運営側のセッションのまま使えるよう運営者の URL の下に置く
    path(settings.OPS_URL + "manage/", include("explore.manage_urls", namespace="ops_manage")),
    path(settings.OPS_URL, include("ops.urls")),
    # 管理者 (店舗・会社) の画面
    path("manage/", include("explore.manage_urls", namespace="manage")),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("explore/", include("explore.urls")),
    path("wardrobe/", include("wardrobe.urls")),
    path("rewards/", include("rewards.urls")),
    path("maps/", include("maps.urls")),
    path("contest/", include("contest.urls")),
    # まちのサイネージの表示 (ログイン不要。推測できない表示キーの URL でだけ開ける)
    path("signage/", include("signage.urls")),
]

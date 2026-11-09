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
    path(settings.OPS_URL, include("ops.urls")),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("explore/", include("explore.urls")),
    path("wardrobe/", include("wardrobe.urls")),
    path("rewards/", include("rewards.urls")),
    path("maps/", include("maps.urls")),
    path("contest/", include("contest.urls")),
]

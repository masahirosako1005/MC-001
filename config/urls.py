from django.conf import settings
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "みっけ 運営管理"
admin.site.site_title = "みっけ 運営管理"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("explore/", include("explore.urls")),
    path("wardrobe/", include("wardrobe.urls")),
    path("rewards/", include("rewards.urls")),
    path("maps/", include("maps.urls")),
    path("contest/", include("contest.urls")),
]

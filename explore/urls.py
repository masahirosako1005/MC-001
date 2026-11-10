from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "explore"

urlpatterns = [
    # 「みっけ」: 近くのシンボルをさがす (地図) → カメラでみっけ を 1 画面で行う
    path("", views.mikke, name="mikke"),
    # 以前の「カメラ」画面のブックマーク用
    path("camera/", RedirectView.as_view(pattern_name="explore:mikke", permanent=True), name="camera"),
    path("history/", views.history, name="history"),
    # 設定画面は /manage/ (管理者) と運営者の画面の下 (サイト運営者) に移した (explore/manage_urls.py)
    path("manage/spots/", RedirectView.as_view(pattern_name="manage:spots", permanent=True)),
    path("api/scan", views.api_scan, name="api_scan"),
    path("api/collect", views.api_collect, name="api_collect"),
    path("api/image-symbols", views.api_image_symbols, name="api_image_symbols"),
    path("api/nearby", views.api_nearby, name="api_nearby"),
    path("symbols/<int:pk>/items/<slug:code>.svg", views.symbol_item_svg, name="symbol_item_svg"),
    path("api/camera-start", views.api_camera_start, name="api_camera_start"),
    path("finders/<str:token>/", views.api_finder, name="api_finder"),
    path("finders/<str:token>/avatar.svg", views.finder_avatar_svg, name="finder_avatar_svg"),
    path("finders/<str:token>/items/<slug:code>.svg", views.finder_item_svg, name="finder_item_svg"),
]

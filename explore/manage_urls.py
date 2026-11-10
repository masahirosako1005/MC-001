"""設定画面 (スポット・シンボル・クーポン) の URL。

同じ画面を 2 か所に置く (config/urls.py):
- /manage/ ............ 管理者 (利用者と同じログイン)。インスタンス名前空間 "manage"
- /<運営者の URL>/manage/ サイト運営者 (運営者専用のセッション)。インスタンス名前空間 "ops_manage"

テンプレートの {% url 'manage:…' %} は、表示中の画面と同じ側の URL になる (Django の current_app)。
ビューで URL を作るときは core.permissions.manage_url(request, …) を使う。
"""

from django.urls import path

from maps import views as map_views

from . import manage_views, views

app_name = "manage"

urlpatterns = [
    path("", manage_views.home, name="home"),
    path("account/", manage_views.account, name="account"),
    path("spots/", manage_views.spot_list, name="spots"),
    path("spots/new/", manage_views.spot_create, name="spot_create"),
    path("spots/<int:pk>/edit/", manage_views.spot_edit, name="spot_edit"),
    path("spots/<int:pk>/delete/", manage_views.spot_delete, name="spot_delete"),
    path("symbols/", views.symbol_print, name="symbols"),
    path("symbols/new/", manage_views.symbol_create, name="symbol_create"),
    path("symbols/register/", views.symbol_register, name="symbol_register"),
    path("symbols/<int:pk>/", manage_views.symbol_edit, name="symbol_edit"),
    path("symbols/<int:pk>/token/", manage_views.symbol_regenerate_token, name="symbol_token"),
    path("symbols/<int:pk>/views/", views.symbol_views, name="symbol_views"),
    path("symbols/<int:pk>/views/<slug:angle>.jpg", views.symbol_view_image, name="symbol_view_image"),
    path("symbols/<int:pk>.svg", views.symbol_svg, name="symbol_svg"),
    path("coupons/", manage_views.coupon_list, name="coupons"),
    path("coupons/new/", manage_views.coupon_create, name="coupon_create"),
    path("coupons/stats/", manage_views.coupon_stats, name="coupon_stats"),
    path("coupons/<int:pk>/", manage_views.coupon_edit, name="coupon_edit"),
    # スポットの位置を選ぶ地図のタイル (運営者の側でも同じセッションで読めるように、ここにも置く)
    path("tiles/<str:name>.pmtiles", map_views.pmtiles, name="tiles"),
]

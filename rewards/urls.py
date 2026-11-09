from django.urls import path

from . import views

app_name = "rewards"

urlpatterns = [
    path("coupons/", views.coupon_list, name="coupons"),
    path("coupons/<uuid:pk>/", views.coupon_detail, name="coupon_detail"),
    path("coupons/<uuid:pk>.svg", views.coupon_svg, name="coupon_svg"),
    path("coupons/<uuid:pk>/use/", views.coupon_use, name="coupon_use"),
    path("achievements/", views.achievements, name="achievements"),
]

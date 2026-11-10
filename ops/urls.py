from django.contrib.auth.views import LogoutView
from django.urls import path, reverse_lazy

from wardrobe import views as wardrobe_views

from . import views

app_name = "ops"

urlpatterns = [
    path("login/", views.OperatorLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(next_page=reverse_lazy("ops:login")), name="logout"),
    path("password/", views.password_change, name="password_change"),
    path("", views.dashboard, name="dashboard"),
    path("coupons/", views.coupons, name="coupons"),
    path("engagement/", views.engagement, name="engagement"),
    path("items/", wardrobe_views.catalog, name="item_catalog"),
    path("signage/", views.signage_list, name="signage_list"),
    path("signage/new/", views.signage_edit, name="signage_create"),
    path("signage/<int:pk>/", views.signage_edit, name="signage_edit"),
    path("signage/<int:pk>/regenerate/", views.signage_regenerate, name="signage_regenerate"),
    path("signage/<int:pk>/delete/", views.signage_delete, name="signage_delete"),
    path("signage/rank1.svg", views.signage_rank1_svg, name="signage_rank1_svg"),
    path("items/<slug:code>.svg", wardrobe_views.catalog_item_svg, name="item_svg"),
    path("users/", views.user_list, name="users"),
    path("users/<int:pk>/toggle/", views.user_toggle_active, name="user_toggle"),
    path("managers/new/", views.manager_create, name="manager_create"),
    path("managers/<int:pk>/", views.manager_edit, name="manager_edit"),
    path("users/<int:pk>/password/", views.user_reset_password, name="user_reset_password"),
    path("managers/<int:pk>/password/", views.user_reset_password, name="manager_reset_password"),
]

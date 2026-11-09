from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", views.MikkeLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("", views.account, name="account"),
    path("password/", views.password_change, name="password_change"),
    path("withdraw/", views.withdraw, name="withdraw"),
]

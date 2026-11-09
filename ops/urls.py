from django.urls import path

from . import views

app_name = "ops"

urlpatterns = [
    path("login/", views.OperatorLoginView.as_view(), name="login"),
    path("", views.dashboard, name="dashboard"),
    path("users/", views.user_list, name="users"),
    path("users/<int:pk>/toggle/", views.user_toggle_active, name="user_toggle"),
    path("managers/new/", views.manager_create, name="manager_create"),
    path("managers/<int:pk>/", views.manager_edit, name="manager_edit"),
    path("managers/<int:pk>/password/", views.manager_reset_password, name="manager_reset_password"),
]

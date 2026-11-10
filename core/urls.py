from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("showcase/<int:n>.svg", views.showcase_svg, name="showcase_svg"),
]

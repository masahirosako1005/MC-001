from django.urls import path

from . import views

app_name = "wardrobe"

urlpatterns = [
    path("", views.index, name="index"),
    path("me.svg", views.avatar_svg, name="avatar_svg"),
    path("preview.svg", views.preview_svg, name="preview_svg"),
    path("items/<slug:code>.svg", views.item_svg, name="item_svg"),
]

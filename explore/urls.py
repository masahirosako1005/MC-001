from django.urls import path

from . import manage_views, views

app_name = "explore"

urlpatterns = [
    path("", views.spot_list, name="spots"),
    path("camera/", views.camera, name="camera"),
    path("history/", views.history, name="history"),
    path("api/scan", views.api_scan, name="api_scan"),
    path("api/collect", views.api_collect, name="api_collect"),
    path("api/image-symbols", views.api_image_symbols, name="api_image_symbols"),
    path("api/nearby", views.api_nearby, name="api_nearby"),
    path("symbols/<int:pk>/items/<slug:code>.svg", views.symbol_item_svg, name="symbol_item_svg"),
    path("manage/spots/", manage_views.spot_list, name="manage_spots"),
    path("manage/spots/new/", manage_views.spot_create, name="manage_spot_create"),
    path("manage/spots/<int:pk>/edit/", manage_views.spot_edit, name="manage_spot_edit"),
    path("manage/spots/<int:pk>/delete/", manage_views.spot_delete, name="manage_spot_delete"),
    path("symbols/print/", views.symbol_print, name="symbol_print"),
    path("symbols/register/", views.symbol_register, name="symbol_register"),
    path("symbols/<int:pk>/views/", views.symbol_views, name="symbol_views"),
    path("symbols/<int:pk>/views/<slug:angle>.jpg", views.symbol_view_image, name="symbol_view_image"),
    path("symbols/<int:pk>.svg", views.symbol_svg, name="symbol_svg"),
]

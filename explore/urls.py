from django.urls import path

from . import views

app_name = "explore"

urlpatterns = [
    path("", views.spot_list, name="spots"),
    path("camera/", views.camera, name="camera"),
    path("history/", views.history, name="history"),
    path("api/scan", views.api_scan, name="api_scan"),
    path("api/collect", views.api_collect, name="api_collect"),
    path("symbols/print/", views.symbol_print, name="symbol_print"),
    path("symbols/<int:pk>.svg", views.symbol_svg, name="symbol_svg"),
]

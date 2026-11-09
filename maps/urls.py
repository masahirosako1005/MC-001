from django.urls import path

from . import views

app_name = "maps"

urlpatterns = [
    path("tiles/<str:name>.pmtiles", views.pmtiles, name="pmtiles"),
]

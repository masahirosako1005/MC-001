from django.urls import path

from . import views

app_name = "contest"

urlpatterns = [
    path("", views.contest_list, name="list"),
    path("<int:pk>/", views.contest_detail, name="detail"),
    path("<int:pk>/entry/", views.contest_enter, name="enter"),
    path("<int:pk>/evaluate/", views.contest_evaluate, name="evaluate"),
    path("<int:pk>/ranking/", views.contest_ranking, name="ranking"),
    path("entries/<uuid:entry_id>.svg", views.entry_svg, name="entry_svg"),
]

from django.urls import path

from . import views

app_name = "signage"

urlpatterns = [
    path("<str:key>/", views.display, name="display"),
    path("<str:key>/rank1.svg", views.rank1_svg, name="rank1_svg"),
]

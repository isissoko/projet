from django.urls import path

from . import views

app_name = "recherche"

urlpatterns = [
    path("recherche/", views.ResultatsView.as_view(), name="resultats"),
    path("travaux/<int:pk>/", views.FicheView.as_view(), name="fiche"),
]

"""Routes principales de SIGAPS."""

from django.contrib import admin
from django.urls import include, path

from recherche.views import AccueilView

urlpatterns = [
    path("", AccueilView.as_view(), name="accueil"),
    path("", include("recherche.urls")),
    path("comptes/", include("comptes.urls")),
    path("depots/", include("productions.urls")),
    path("evaluation/", include("productions.urls_evaluation")),
    path("bibliotheque/", include("bibliotheque.urls")),
    path("referentiel/", include("referentiel.urls")),
    path("admin/", admin.site.urls),
]

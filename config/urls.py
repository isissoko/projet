"""Routes principales de SIGAPS."""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    # Page d'accueil provisoire ; remplacée par la recherche en phase 5.
    path("", TemplateView.as_view(template_name="pages/accueil.html"), name="accueil"),
    path("comptes/", include("comptes.urls")),
    path("depots/", include("productions.urls")),
    path("evaluation/", include("productions.urls_evaluation")),
    path("bibliotheque/", include("bibliotheque.urls")),
    path("referentiel/", include("referentiel.urls")),
    path("admin/", admin.site.urls),
]

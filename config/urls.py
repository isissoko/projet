"""Routes principales de SIGAPS."""

from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

urlpatterns = [
    # Page d'accueil provisoire ; remplacée par la recherche en phase 5.
    path("", TemplateView.as_view(template_name="pages/accueil.html"), name="accueil"),
    path("admin/", admin.site.urls),
]

from django.urls import path

from . import views

app_name = "bibliotheque"

urlpatterns = [
    path("a-controler/", views.AControlerView.as_view(), name="a_controler"),
    path("catalogue/", views.CatalogueView.as_view(), name="catalogue"),
    path("travaux/<int:pk>/", views.ControleView.as_view(), name="controle"),
    path("travaux/<int:pk>/metadonnees/", views.MetadonneesView.as_view(), name="metadonnees"),
]

from django.urls import path

from . import views

app_name = "referentiel"

urlpatterns = [
    path("", views.ReferentielAccueilView.as_view(), name="accueil"),
    path("<slug:type>/", views.ElementListeView.as_view(), name="liste"),
    path("<slug:type>/nouveau/", views.ElementCreerView.as_view(), name="creer"),
    path("<slug:type>/<int:pk>/", views.ElementModifierView.as_view(), name="modifier"),
    path(
        "<slug:type>/<int:pk>/<slug:action>/",
        views.ElementActionView.as_view(),
        name="action",
    ),
]

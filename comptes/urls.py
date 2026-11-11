from django.urls import path

from . import views

app_name = "comptes"

urlpatterns = [
    path("connexion/", views.ConnexionView.as_view(), name="connexion"),
    path("deconnexion/", views.DeconnexionView.as_view(), name="deconnexion"),
    path("mot-de-passe-oublie/", views.MotDePasseOublieView.as_view(), name="mot_de_passe_oublie"),
    path(
        "mot-de-passe-oublie/envoye/",
        views.ReinitialisationEnvoyeeView.as_view(),
        name="reinitialisation_envoyee",
    ),
    path(
        "reinitialisation/<uidb64>/<token>/",
        views.ReinitialisationConfirmationView.as_view(),
        name="reinitialisation_confirmation",
    ),
    path(
        "reinitialisation/terminee/",
        views.ReinitialisationTermineeView.as_view(),
        name="reinitialisation_terminee",
    ),
    path("gestion/", views.ComptesListeView.as_view(), name="liste"),
    path("gestion/nouveau/", views.CompteCreerView.as_view(), name="creer"),
    path("gestion/<int:pk>/", views.CompteModifierView.as_view(), name="modifier"),
    path("gestion/<int:pk>/activation/", views.CompteActivationView.as_view(), name="activation"),
]

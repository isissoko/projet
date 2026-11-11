from django.urls import path

from . import views

app_name = "productions"

urlpatterns = [
    path("", views.MesDepotsView.as_view(), name="mes_depots"),
    path("nouveau/", views.NouveauDepotView.as_view(), name="nouveau"),
    path("<int:pk>/", views.DepotDetailView.as_view(), name="detail"),
    path("<int:pk>/supprimer/", views.DepotSupprimerView.as_view(), name="supprimer"),
    path("<int:pk>/etape/1/", views.Etape1View.as_view(), name="etape1"),
    path("<int:pk>/etape/2/", views.Etape2View.as_view(), name="etape2"),
    path("<int:pk>/etape/3/", views.Etape3View.as_view(), name="etape3"),
    path("<int:pk>/etape/4/", views.Etape4View.as_view(), name="etape4"),
    path("<int:pk>/etape/5/", views.Etape5View.as_view(), name="etape5"),
]

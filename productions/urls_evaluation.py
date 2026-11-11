from django.urls import path

from . import views_evaluation

app_name = "evaluation"

urlpatterns = [
    path("", views_evaluation.TravauxAEvaluerView.as_view(), name="liste"),
    path("<int:pk>/", views_evaluation.EvaluationView.as_view(), name="ecran"),
]

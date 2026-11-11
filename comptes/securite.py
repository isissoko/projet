"""Intégration de django-axes."""

from .models import normaliser_email


def identifiant_axes(request, credentials=None) -> str:
    """Identifiant utilisé par axes pour compter les échecs : l'e-mail normalisé.

    Le formulaire de connexion de Django transmet l'e-mail sous la clé « username ».
    """
    valeur = None
    if credentials:
        valeur = credentials.get("username") or credentials.get("email")
    if valeur is None and request is not None and hasattr(request, "POST"):
        valeur = request.POST.get("username") or request.POST.get("email")
    return normaliser_email(valeur or "")

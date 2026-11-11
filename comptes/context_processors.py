"""Menu principal adapté aux rôles de l'utilisateur connecté."""

from django.urls import reverse

from .roles import Role

# (libellé, nom d'URL, rôles autorisés ; None = tout le monde)
ENTREES_MENU = [
    ("Rechercher", "accueil", None),
    ("Mes dépôts", "productions:mes_depots", {Role.ETUDIANT}),
    ("Référentiel", "referentiel:accueil", {Role.BIBLIOTHECAIRE, Role.ADMINISTRATEUR}),
    ("Comptes", "comptes:liste", {Role.ADMINISTRATEUR}),
]


def navigation(request):
    utilisateur = getattr(request, "user", None)
    roles = utilisateur.roles if utilisateur is not None and utilisateur.is_authenticated else set()
    chemin = request.path
    menu = []
    for libelle, nom_url, autorises in ENTREES_MENU:
        if autorises is not None and not roles & autorises:
            continue
        url = reverse(nom_url)
        actif = chemin == url if url == "/" else chemin.startswith(url)
        menu.append({"libelle": libelle, "url": url, "actif": actif})
    return {"menu_principal": menu}

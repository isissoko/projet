"""Menu principal adapté aux rôles de l'utilisateur connecté."""

from django.urls import reverse

from .roles import Role

# (libellé, nom d'URL, rôles autorisés ; None = tout le monde)
ENTREES_MENU = [
    ("Rechercher", "accueil", None),
    ("Mes dépôts", "productions:mes_depots", {Role.ETUDIANT}),
    ("Travaux à évaluer", "evaluation:liste", {Role.ENSEIGNANT}),
    ("À contrôler", "bibliotheque:a_controler", {Role.BIBLIOTHECAIRE}),
    ("Catalogue", "bibliotheque:catalogue", {Role.BIBLIOTHECAIRE}),
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
        menu.append(
            {
                "libelle": libelle,
                "url": url,
                "actif": actif,
                "compteur": _compteur(nom_url, utilisateur),
            }
        )
    return {"menu_principal": menu}


def _compteur(nom_url, utilisateur):
    """Pastille numérique de certaines entrées (travaux en attente)."""
    from productions import acces  # import local : évite un cycle

    if nom_url == "evaluation:liste":
        return acces.nombre_a_evaluer(utilisateur)
    if nom_url == "bibliotheque:a_controler":
        return acces.nombre_a_controler(utilisateur)
    return 0

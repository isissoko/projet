"""Indexation plein texte des productions (BF09).

Le vecteur est stocké dans Production.vecteur_recherche (index GIN) et recalculé par
indexer() à chaque archivage ou modification des métadonnées. Il ne peut pas être une
colonne générée : il dépend des auteurs, des encadrants et des mots-clés (autres tables).
"""

from django.contrib.postgres.search import SearchVector
from django.db.models import Value

from .models import Production

# Copie de la configuration « french » qui retire aussi les accents (migration 0004).
CONFIG_RECHERCHE = "french_sans_accents"


def _texte(morceaux) -> str:
    return " ".join(str(m) for m in morceaux if m)


def textes_ponderes(production) -> dict[str, str]:
    """Textes indexés par poids : A (titre, mots-clés, cote), B (auteurs, encadrants,
    filière, domaine), C (résumé)."""
    auteurs = [
        f"{c.contributeur.prenom} {c.contributeur.nom}"
        for c in production.contributions.select_related("contributeur")
    ]
    encadrants = [
        f"{e.enseignant.utilisateur.first_name} {e.enseignant.utilisateur.last_name}"
        for e in production.encadrements.select_related("enseignant__utilisateur")
    ]
    mots_cles = production.mots_cles.values_list("libelle", flat=True)
    filiere = production.filiere.libelle if production.filiere_id else ""
    domaine = production.domaine.libelle if production.domaine_id else ""
    return {
        "A": _texte([production.titre, *mots_cles, production.cote]),
        "B": _texte([*auteurs, *encadrants, filiere, domaine]),
        "C": production.resume or "",
    }


def vecteur(production):
    textes = textes_ponderes(production)
    expression = None
    for poids, texte in textes.items():
        terme = SearchVector(Value(texte), weight=poids, config=CONFIG_RECHERCHE)
        expression = terme if expression is None else expression + terme
    return expression


def indexer(production) -> None:
    """Recalcule le vecteur de recherche d'une production (une requête UPDATE)."""
    Production.objects.filter(pk=production.pk).update(vecteur_recherche=vecteur(production))


def reindexer(queryset=None) -> int:
    """Recalcule les vecteurs de toutes les productions données (par défaut : toutes)."""
    nombre = 0
    queryset = Production.objects.all() if queryset is None else queryset
    for production in queryset.select_related("filiere", "domaine").iterator(chunk_size=200):
        indexer(production)
        nombre += 1
    return nombre

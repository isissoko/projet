"""Recherche multicritère (BF09) dans les seules productions archivées (RG10).

Texte libre : recherche plein texte (configuration french_sans_accents, syntaxe « web » :
guillemets, signe moins) sur le vecteur indexé, triée par pertinence. Les autres critères
filtrent et se combinent.
"""

from dataclasses import dataclass, fields
from functools import reduce
from operator import and_

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Count, Exists, F, OuterRef, Prefetch, Q

from productions.indexation import CONFIG_RECHERCHE
from productions.models import Contribution, Encadrement, Production, Statut, TypeProduction

TRIS = {
    "pertinence": "Pertinence",
    "recent": "Plus récents",
    "titre": "Titre (A → Z)",
}
NOMBRE_MAX_DE_MOTS = 6


@dataclass
class Criteres:
    texte: str = ""
    titre: str = ""
    auteur: str = ""
    encadreur: str = ""
    annee: int | None = None  # année de soutenance (décision Q2 de la phase 5)
    mot_cle: object = None  # MotCle
    filiere: object = None  # Filiere
    type_production: str = ""
    tri: str = "pertinence"

    def actifs(self) -> bool:
        return any(getattr(self, f.name) for f in fields(self) if f.name != "tri")


def _requete(texte):
    return SearchQuery(texte, search_type="websearch", config=CONFIG_RECHERCHE)


def _mots(texte):
    return texte.split()[:NOMBRE_MAX_DE_MOTS]


def _tous_les_mots(texte, champs):
    """Q : chaque mot apparaît (sans tenir compte des accents ni de la casse) dans au moins
    un des champs."""
    return reduce(
        and_,
        (
            reduce(
                lambda a, b: a | b,
                (Q(**{f"{champ}__unaccent__icontains": mot}) for champ in champs),
            )
            for mot in _mots(texte)
        ),
    )


def productions_publiques():
    """Base de toute recherche publique : uniquement ARCHIVE (RG10)."""
    return Production.objects.filter(statut=Statut.ARCHIVE)


def _avec_auteurs(queryset):
    auteurs = Contribution.objects.select_related("contributeur").order_by("rang")
    return queryset.select_related("filiere", "annee_academique").prefetch_related(
        Prefetch("contributions", queryset=auteurs, to_attr="auteurs_ordonnes")
    )


def rechercher(criteres: Criteres):
    productions = productions_publiques()
    pertinence = False

    if criteres.texte.strip():
        requete = _requete(criteres.texte)
        productions = productions.filter(vecteur_recherche=requete).annotate(
            pertinence=SearchRank(F("vecteur_recherche"), requete)
        )
        pertinence = True
    if criteres.titre.strip():
        productions = productions.annotate(
            vecteur_titre=SearchVector("titre", config=CONFIG_RECHERCHE)
        ).filter(vecteur_titre=_requete(criteres.titre))
    if criteres.auteur.strip():
        contributions = Contribution.objects.filter(
            _tous_les_mots(criteres.auteur, ["contributeur__nom", "contributeur__prenom"]),
            production=OuterRef("pk"),
        )
        productions = productions.filter(Exists(contributions))
    if criteres.encadreur.strip():
        encadrements = Encadrement.objects.filter(
            _tous_les_mots(
                criteres.encadreur,
                ["enseignant__utilisateur__last_name", "enseignant__utilisateur__first_name"],
            ),
            production=OuterRef("pk"),
        )
        productions = productions.filter(Exists(encadrements))
    if criteres.annee:
        productions = productions.filter(date_soutenance__year=criteres.annee)
    if criteres.mot_cle is not None:
        productions = productions.filter(mots_cles=criteres.mot_cle)
    if criteres.filiere is not None:
        productions = productions.filter(filiere=criteres.filiere)
    if criteres.type_production in TypeProduction.values:
        productions = productions.filter(type_production=criteres.type_production)

    if criteres.tri == "titre":
        ordre = ["titre", "pk"]
    elif criteres.tri == "pertinence" and pertinence:
        ordre = ["-pertinence", "-date_archivage", "-pk"]
    else:
        ordre = [F("date_soutenance").desc(nulls_last=True), "-date_archivage", "-pk"]
    return _avec_auteurs(productions).order_by(*ordre)


# Accueil ---------------------------------------------------------------------------------


def derniers_archives(nombre=6):
    return _avec_auteurs(productions_publiques()).order_by("-date_archivage", "-pk")[:nombre]


def chiffres() -> dict:
    """Chiffres de l'accueil, en une requête."""
    return productions_publiques().aggregate(
        total=Count("pk"),
        memoires=Count("pk", filter=Q(type_production=TypeProduction.MEMOIRE)),
        theses=Count("pk", filter=Q(type_production=TypeProduction.THESE)),
        filieres=Count("filiere", distinct=True),
    )


def annees_disponibles() -> list[int]:
    return list(
        productions_publiques()
        .exclude(date_soutenance=None)
        .values_list("date_soutenance__year", flat=True)
        .distinct()
        .order_by("-date_soutenance__year")
    )


# Fiche ---------------------------------------------------------------------------------


def citation(production) -> str:
    """Référence bibliographique simple : Auteurs (année). Titre. Type, filière,
    établissement. Cote."""
    production = production.specifique()
    auteurs = ", ".join(
        f"{c.contributeur.nom.upper()} {c.contributeur.prenom}".strip()
        for c in production.contributions.select_related("contributeur").order_by("rang")
    )
    annee = production.date_soutenance.year if production.date_soutenance else "s. d."
    nature = production.get_type_production_display()
    niveau = getattr(production, "niveau", "")
    if niveau:
        nature += f" de {production.get_niveau_display()}"
    morceaux = [nature]
    if production.filiere_id:
        filiere = production.filiere
        morceaux.append(filiere.libelle)
        etablissement = filiere.departement.etablissement if filiere.departement_id else None
        if etablissement is not None:
            morceaux.append(etablissement.nom)
    reference = f"{auteurs} ({annee}). {production.titre}. {', '.join(morceaux)}."
    if production.cote:
        reference += f" Cote {production.cote}."
    return reference

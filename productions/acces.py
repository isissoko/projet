"""Règles d'accès aux productions (RG11). Aucune vue ne les réimplémente.

Phase 2 : visibilité des productions non archivées et modification des brouillons.
Phase 3 : évaluation et première version de peut_telecharger (travaux non archivés).
Phase 4 : compléter peut_voir_fiche et peut_telecharger (ARCHIVE, RETIRE, niveaux, embargo).
"""

from django.db.models import Exists, OuterRef, Q, Subquery
from django.utils import timezone

from comptes.roles import Role

from .models import (
    AvisEncadrement,
    Contribution,
    Encadrement,
    Production,
    RoleContribution,
    Statut,
    VersionDocument,
)


def aujourd_hui():
    """Date du jour à Bamako (TIME_ZONE) : l'embargo est réévalué à chaque requête."""
    return timezone.localdate()


def _connecte(user) -> bool:
    return bool(user is not None and user.is_authenticated and user.is_active)


def est_personnel(user) -> bool:
    """Bibliothécaire ou administrateur : voit toutes les productions."""
    return _connecte(user) and user.a_un_role(Role.BIBLIOTHECAIRE, Role.ADMINISTRATEUR)


def est_auteur(user, production) -> bool:
    return (
        _connecte(user)
        and Contribution.objects.filter(
            production=production, contributeur__utilisateur=user
        ).exists()
    )


def est_auteur_principal(user, production) -> bool:
    return (
        _connecte(user)
        and Contribution.objects.filter(
            production=production,
            contributeur__utilisateur=user,
            role=RoleContribution.AUTEUR_PRINCIPAL,
        ).exists()
    )


def est_encadrant(user, production) -> bool:
    return (
        _connecte(user)
        and Encadrement.objects.filter(production=production, enseignant__utilisateur=user).exists()
    )


def est_proche(user, production) -> bool:
    """Auteur, encadrant, bibliothécaire ou administrateur."""
    return est_personnel(user) or est_auteur(user, production) or est_encadrant(user, production)


def peut_voir_fiche(user, production) -> bool:
    if production.statut == Statut.ARCHIVE:
        return True  # fiche publique (CLAUDE.md) ; détaillé en phase 4
    return est_proche(user, production)


def peut_modifier_brouillon(user, production) -> bool:
    return production.statut == Statut.BROUILLON and est_auteur_principal(user, production)


def mes_depots(user):
    """Productions dont l'utilisateur est auteur (principal ou co-auteur)."""
    if not _connecte(user):
        return Production.objects.none()
    return Production.objects.filter(contributions__contributeur__utilisateur=user).distinct()


def productions_visibles(user):
    """Queryset des productions dont la fiche est visible : base de toute vue de détail."""
    if est_personnel(user):
        return Production.objects.all()
    filtre = Q(statut=Statut.ARCHIVE)
    if _connecte(user):
        filtre |= Q(contributions__contributeur__utilisateur=user)
        filtre |= Q(encadrements__enseignant__utilisateur=user)
    return Production.objects.filter(filtre).distinct()


# Évaluation et téléchargement (phase 3) ---------------------------------------------------


def peut_evaluer(user, production) -> bool:
    """Encadrant enseignant d'un travail au statut SOUMIS."""
    return (
        production.statut == Statut.SOUMIS
        and _connecte(user)
        and user.a_role(Role.ENSEIGNANT)
        and est_encadrant(user, production)
    )


def peut_telecharger(user, production) -> bool:
    """Droit de télécharger les PDF d'une production.

    Travail non archivé : auteurs, encadrants, bibliothécaires, administrateurs (RG11).
    Travail archivé : provisoirement les mêmes personnes ; la règle complète (LIBRE,
    RESTREINT, CONFIDENTIEL, embargo) arrive en phase 4.
    """
    return est_proche(user, production)


def travaux_encadres(user):
    """Travaux soumis au moins une fois que l'utilisateur encadre, annotés avec :
    - role_encadrement : DIRECTEUR ou CO_DIRECTEUR ;
    - avis_donne : l'utilisateur a déjà donné son avis sur la version courante."""
    if not _connecte(user):
        return Production.objects.none()
    derniere_version = (
        VersionDocument.objects.filter(production=OuterRef(OuterRef("pk")))
        .order_by("-numero")
        .values("pk")[:1]
    )
    avis_sur_courante = AvisEncadrement.objects.filter(
        production=OuterRef("pk"),
        encadrement__enseignant__utilisateur=user,
        version=Subquery(derniere_version),
    )
    role = Encadrement.objects.filter(
        production=OuterRef("pk"), enseignant__utilisateur=user
    ).values("role")[:1]
    return (
        Production.objects.filter(encadrements__enseignant__utilisateur=user)
        .exclude(statut=Statut.BROUILLON)
        .annotate(avis_donne=Exists(avis_sur_courante), role_encadrement=Subquery(role))
        .distinct()
    )


def nombre_a_evaluer(user) -> int:
    """Travaux soumis attendant encore l'avis de cet encadrant (compteur du menu)."""
    return travaux_encadres(user).filter(statut=Statut.SOUMIS, avis_donne=False).count()

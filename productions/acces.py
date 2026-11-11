"""Règles d'accès aux productions (RG11). Aucune vue ne les réimplémente.

Phase 2 : visibilité des productions non archivées et modification des brouillons.
Phase 4 : compléter peut_voir_fiche (ARCHIVE, RETIRE) et ajouter peut_telecharger.
"""

from django.db.models import Q

from comptes.roles import Role

from .models import Contribution, Encadrement, Production, RoleContribution, Statut


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

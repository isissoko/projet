"""Règles d'accès aux productions (RG10, RG11, accès aux fichiers). Aucune vue ne les
réimplémente.

Fiche : publique pour un travail ARCHIVE ; sinon (y compris RETIRE) réservée aux proches
(auteurs, encadrants, bibliothécaires, administrateurs), les autres reçoivent 404.

PDF d'un travail ARCHIVE :
- embargo actif (date_fin_embargo > aujourd'hui) : proches seulement ;
- sinon LIBRE : tout le monde ; RESTREINT : utilisateurs connectés ; CONFIDENTIEL : proches.
Le public n'accède qu'à la version archivée (la version courante) ; les versions
antérieures restent réservées aux proches (décision Q4 de la phase 4).
L'embargo est évalué à chaque appel : il se lève tout seul.
"""

from django.db.models import Exists, OuterRef, Q, Subquery
from django.utils import timezone
from django.utils.formats import date_format

from comptes.roles import Role

from .models import (
    AvisEncadrement,
    Contribution,
    Encadrement,
    NiveauAcces,
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
        return True
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


def embargo_actif(production) -> bool:
    return production.date_fin_embargo is not None and production.date_fin_embargo > aujourd_hui()


def _est_version_archivee(production, version) -> bool:
    if version is None:
        return True
    courante = (
        VersionDocument.objects.filter(production_id=production.pk)
        .order_by("-numero")
        .values_list("numero", flat=True)
        .first()
    )
    return version.production_id == production.pk and version.numero == courante


def peut_telecharger(user, production, version=None) -> bool:
    """Droit d'ouvrir le PDF d'une production : la version donnée, ou la version courante."""
    if est_proche(user, production):
        return True
    if production.statut != Statut.ARCHIVE or embargo_actif(production):
        return False
    if not _est_version_archivee(production, version):
        return False
    if production.niveau_acces == NiveauAcces.LIBRE:
        return True
    if production.niveau_acces == NiveauAcces.RESTREINT:
        return _connecte(user)
    return False  # CONFIDENTIEL (ou niveau absent)


def raison_indisponibilite(user, production) -> str | None:
    """Pourquoi le PDF n'est pas accessible à cet utilisateur (None s'il l'est)."""
    if peut_telecharger(user, production):
        return None
    if production.statut != Statut.ARCHIVE:
        return "Le document n'est pas encore archivé."
    if embargo_actif(production):
        fin = date_format(production.date_fin_embargo, "j F Y")
        return f"Le document est sous embargo jusqu'au {fin}."
    if production.niveau_acces == NiveauAcces.RESTREINT:
        return "Le document est réservé aux utilisateurs connectés : connectez-vous pour l'ouvrir."
    return (
        "Le document est confidentiel : seuls ses auteurs, ses encadrants et la bibliothèque "
        "y ont accès."
    )


def versions_consultables(user, production):
    """Versions listées sur la fiche : toutes pour les proches, la seule version archivée
    pour les autres."""
    versions = production.versions.order_by("-numero")
    if est_proche(user, production):
        return versions
    return versions[:1]


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


# Bibliothèque (phase 4) ----------------------------------------------------------------


def est_bibliothecaire(user) -> bool:
    return _connecte(user) and user.a_role(Role.BIBLIOTHECAIRE)


def productions_a_controler(user):
    """Travaux validés par l'encadreur ou en attente des corrections de la bibliothèque."""
    if not est_bibliothecaire(user):
        return Production.objects.none()
    return Production.objects.filter(statut__in=[Statut.VALIDE, Statut.A_CORRIGER_BIBLIOTHEQUE])


def nombre_a_controler(user) -> int:
    return productions_a_controler(user).filter(statut=Statut.VALIDE).count()


def catalogue(user):
    """Travaux archivés ou retirés, pour la gestion par la bibliothèque."""
    if not est_bibliothecaire(user):
        return Production.objects.none()
    return Production.objects.filter(statut__in=[Statut.ARCHIVE, Statut.RETIRE])

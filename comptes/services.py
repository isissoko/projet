"""Services des comptes : création, rôles, profils, activation.

Toute la logique métier est ici ; les vues ne font que transmettre les données validées.
"""

from dataclasses import dataclass

from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .exceptions import ActionInterdite
from .models import (
    ProfilEnseignant,
    ProfilEtudiant,
    Utilisateur,
    normaliser_email,
    normaliser_matricule,
)
from .roles import Role


@dataclass
class DonneesProfilEtudiant:
    matricule: str
    niveau: str
    filiere: object


@dataclass
class DonneesProfilEnseignant:
    grade: str
    specialite: str
    departement: object


def _verifier_roles(roles) -> set[str]:
    roles = set(roles)
    inconnus = roles - set(Role.values)
    if inconnus:
        raise ActionInterdite(f"Rôle inconnu : {', '.join(sorted(inconnus))}.")
    return roles


def _verifier_profils(roles, profil_etudiant, profil_enseignant):
    if Role.ETUDIANT in roles and profil_etudiant is None:
        raise ActionInterdite("Le rôle Étudiant exige un profil étudiant.")
    if Role.ENSEIGNANT in roles and profil_enseignant is None:
        raise ActionInterdite("Le rôle Enseignant exige un profil enseignant.")


def _appliquer_roles(utilisateur: Utilisateur, roles: set[str]):
    groupes = list(Group.objects.filter(name__in=roles))
    if len(groupes) != len(roles):
        raise ActionInterdite("Groupes de rôles manquants : lancez les migrations.")
    utilisateur.groups.set(groupes)
    utilisateur.oublier_roles()


def _enregistrer_profils(utilisateur, profil_etudiant, profil_enseignant):
    """Crée ou met à jour les profils fournis. Un profil n'est jamais supprimé (historique)."""
    if profil_etudiant is not None:
        matricule = normaliser_matricule(profil_etudiant.matricule)
        doublon = ProfilEtudiant.objects.filter(matricule=matricule).exclude(
            utilisateur=utilisateur
        )
        if doublon.exists():
            raise ActionInterdite("Ce matricule est déjà attribué à un autre étudiant.")
        ProfilEtudiant.objects.update_or_create(
            utilisateur=utilisateur,
            defaults={
                "matricule": matricule,
                "niveau": profil_etudiant.niveau,
                "filiere": profil_etudiant.filiere,
            },
        )
    if profil_enseignant is not None:
        ProfilEnseignant.objects.update_or_create(
            utilisateur=utilisateur,
            defaults={
                "grade": profil_enseignant.grade,
                "specialite": profil_enseignant.specialite,
                "departement": profil_enseignant.departement,
            },
        )


def _verifier_email_libre(email: str, utilisateur: Utilisateur | None = None):
    autres = Utilisateur.objects.filter(email__iexact=email)
    if utilisateur is not None:
        autres = autres.exclude(pk=utilisateur.pk)
    if autres.exists():
        raise ActionInterdite("Cette adresse e-mail est déjà utilisée.")


def envoyer_invitation(utilisateur: Utilisateur, url_base: str):
    """Envoie le lien permettant au nouvel utilisateur de choisir son mot de passe."""
    chemin = reverse(
        "comptes:reinitialisation_confirmation",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(utilisateur.pk)),
            "token": default_token_generator.make_token(utilisateur),
        },
    )
    contexte = {"utilisateur": utilisateur, "lien": url_base.rstrip("/") + chemin}
    send_mail(
        subject="SIGAPS — Activez votre compte",
        message=render_to_string("comptes/emails/invitation.txt", contexte),
        from_email=None,
        recipient_list=[utilisateur.email],
    )


@transaction.atomic
def creer_compte(
    *,
    email: str,
    prenom: str,
    nom: str,
    roles,
    profil_etudiant: DonneesProfilEtudiant | None = None,
    profil_enseignant: DonneesProfilEnseignant | None = None,
    url_base: str | None = None,
) -> Utilisateur:
    """Crée un compte sans mot de passe utilisable et envoie une invitation après validation."""
    roles = _verifier_roles(roles)
    if not roles:
        raise ActionInterdite("Un compte doit avoir au moins un rôle.")
    _verifier_profils(roles, profil_etudiant, profil_enseignant)
    email = normaliser_email(email)
    _verifier_email_libre(email)

    utilisateur = Utilisateur.objects.create_user(
        email=email, password=None, first_name=prenom.strip(), last_name=nom.strip()
    )
    _appliquer_roles(utilisateur, roles)
    _enregistrer_profils(
        utilisateur,
        profil_etudiant if Role.ETUDIANT in roles else None,
        profil_enseignant if Role.ENSEIGNANT in roles else None,
    )
    if url_base:
        transaction.on_commit(lambda: envoyer_invitation(utilisateur, url_base))
    return utilisateur


def verifier_modification_roles(acteur: Utilisateur, cible: Utilisateur, roles) -> set[str]:
    roles = _verifier_roles(roles)
    if not roles:
        raise ActionInterdite("Un compte doit avoir au moins un rôle.")
    if (
        acteur.pk == cible.pk
        and acteur.a_role(Role.ADMINISTRATEUR)
        and Role.ADMINISTRATEUR not in roles
    ):
        raise ActionInterdite("Vous ne pouvez pas retirer votre propre rôle Administrateur.")
    return roles


@transaction.atomic
def modifier_roles(acteur: Utilisateur, cible: Utilisateur, roles) -> None:
    roles = verifier_modification_roles(acteur, cible, roles)
    _appliquer_roles(cible, roles)


@transaction.atomic
def modifier_compte(
    *,
    acteur: Utilisateur,
    utilisateur: Utilisateur,
    email: str,
    prenom: str,
    nom: str,
    roles,
    profil_etudiant: DonneesProfilEtudiant | None = None,
    profil_enseignant: DonneesProfilEnseignant | None = None,
) -> Utilisateur:
    roles = verifier_modification_roles(acteur, utilisateur, roles)
    _verifier_profils(roles, profil_etudiant, profil_enseignant)
    email = normaliser_email(email)
    _verifier_email_libre(email, utilisateur)

    utilisateur.email = email
    utilisateur.first_name = prenom.strip()
    utilisateur.last_name = nom.strip()
    utilisateur.save(update_fields=["email", "first_name", "last_name"])
    _appliquer_roles(utilisateur, roles)
    _enregistrer_profils(
        utilisateur,
        profil_etudiant if Role.ETUDIANT in roles else None,
        profil_enseignant if Role.ENSEIGNANT in roles else None,
    )
    if acteur.pk == utilisateur.pk:
        acteur.oublier_roles()
    return utilisateur


@transaction.atomic
def changer_activation(acteur: Utilisateur, cible: Utilisateur, actif: bool) -> None:
    if acteur.pk == cible.pk and not actif:
        raise ActionInterdite("Vous ne pouvez pas désactiver votre propre compte.")
    cible.is_active = actif
    cible.save(update_fields=["is_active"])


@transaction.atomic
def creer_administrateur(*, email: str, prenom: str, nom: str, mot_de_passe: str) -> Utilisateur:
    """Premier administrateur (commande creer_admin) : rôle ADMINISTRATEUR et accès à l'admin."""
    email = normaliser_email(email)
    _verifier_email_libre(email)
    utilisateur = Utilisateur.objects.create_superuser(
        email=email, password=mot_de_passe, first_name=prenom.strip(), last_name=nom.strip()
    )
    _appliquer_roles(utilisateur, {Role.ADMINISTRATEUR})
    return utilisateur

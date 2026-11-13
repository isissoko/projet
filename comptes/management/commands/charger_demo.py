"""Données de démonstration : un compte par rôle et un référentiel minimal.

Version minimale utilisée par scripts/installer.sh ; elle sera enrichie en phase 10
(travaux déposés, évalués et archivés). Idempotente : peut être relancée sans doublon.
Refusée hors DEBUG, sauf --force : ces comptes ont un mot de passe connu.
"""

import datetime

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from comptes.models import ProfilEnseignant, ProfilEtudiant, Utilisateur
from comptes.roles import Role
from referentiel.models import (
    AnneeAcademique,
    Departement,
    Domaine,
    Etablissement,
    Filiere,
    MotCle,
)

MOT_DE_PASSE_DEMO = "Sigaps2026!"

COMPTES = [
    ("admin@sigaps.local", "Admin", "SIGAPS", [Role.ADMINISTRATEUR]),
    ("bibliothecaire@sigaps.local", "Fatoumata", "Coulibaly", [Role.BIBLIOTHECAIRE]),
    ("enseignant@sigaps.local", "Moussa", "Keïta", [Role.ENSEIGNANT]),
    ("enseignant2@sigaps.local", "Mariam", "Sangaré", [Role.ENSEIGNANT]),
    ("etudiant@sigaps.local", "Aïssata", "Traoré", [Role.ETUDIANT]),
    ("etudiant2@sigaps.local", "Oumar", "Diallo", [Role.ETUDIANT]),
]

MOTS_CLES = ["Irrigation", "Barrage", "Niger", "Hydrologie", "Agriculture", "Climat"]


class Command(BaseCommand):
    help = "Crée un compte de démonstration par rôle et un référentiel minimal (développement)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true", help="Autorise l'exécution même si DEBUG=False."
        )
        parser.add_argument(
            "--mot-de-passe",
            default=MOT_DE_PASSE_DEMO,
            help=f"Mot de passe des comptes (par défaut : {MOT_DE_PASSE_DEMO}).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusé : DEBUG=False. Ces comptes ont un mot de passe connu ; utilisez --force "
                "seulement sur une machine de test."
            )
        filiere, departement = self.referentiel()
        mot_de_passe = options["mot_de_passe"]
        for numero, (email, prenom, nom, roles) in enumerate(COMPTES, start=1):
            utilisateur, _ = Utilisateur.objects.get_or_create(
                email=email, defaults={"first_name": prenom, "last_name": nom}
            )
            administrateur = Role.ADMINISTRATEUR in roles
            utilisateur.is_staff = utilisateur.is_superuser = administrateur
            utilisateur.is_active = True
            utilisateur.set_password(mot_de_passe)
            utilisateur.save()
            utilisateur.groups.set(Group.objects.filter(name__in=roles))
            if Role.ETUDIANT in roles:
                ProfilEtudiant.objects.get_or_create(
                    utilisateur=utilisateur,
                    defaults={
                        "matricule": f"DEMO{numero:03d}",
                        "niveau": "MASTER",
                        "filiere": filiere,
                    },
                )
            if Role.ENSEIGNANT in roles:
                ProfilEnseignant.objects.get_or_create(
                    utilisateur=utilisateur,
                    defaults={"grade": "MAITRE_DE_CONFERENCES", "departement": departement},
                )
            self.stdout.write(f"  {email:32} {', '.join(roles)}")
        self.stdout.write(
            self.style.SUCCESS(f"Comptes de démonstration prêts (mot de passe : {mot_de_passe}).")
        )

    def referentiel(self):
        etablissement, _ = Etablissement.objects.get_or_create(
            code="USTTB",
            defaults={
                "nom": "Université des sciences, des techniques et des technologies de Bamako",
                "sigle": "USTTB",
            },
        )
        departement, _ = Departement.objects.get_or_create(
            etablissement=etablissement, code="GC", defaults={"nom": "Génie civil et hydraulique"}
        )
        filiere, _ = Filiere.objects.get_or_create(
            code="HYD", defaults={"departement": departement, "libelle": "Hydraulique"}
        )
        if not AnneeAcademique.objects.filter(libelle="2025-2026").exists():
            AnneeAcademique.objects.create(
                libelle="2025-2026",
                date_debut=datetime.date(2025, 10, 1),
                date_fin=datetime.date(2026, 7, 31),
                courante=not AnneeAcademique.objects.filter(courante=True).exists(),
            )
        Domaine.objects.get_or_create(code="EAU", defaults={"libelle": "Ressources en eau"})
        for libelle in MOTS_CLES:
            if not MotCle.objects.filter(libelle__iexact=libelle).exists():
                MotCle.objects.create(libelle=libelle)
        return filiere, departement

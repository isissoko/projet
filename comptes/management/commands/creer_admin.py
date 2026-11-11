"""Crée le premier administrateur de SIGAPS, en interactif."""

import getpass

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from comptes.exceptions import ActionInterdite
from comptes.models import Utilisateur
from comptes.services import creer_administrateur


class Command(BaseCommand):
    help = "Crée un administrateur (rôle ADMINISTRATEUR et accès à l'admin Django)."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Adresse e-mail (sinon demandée)")
        parser.add_argument("--prenom", help="Prénom (sinon demandé)")
        parser.add_argument("--nom", help="Nom (sinon demandé)")

    # Méthodes de saisie isolées pour pouvoir les remplacer dans les tests.
    def saisir(self, invite: str) -> str:
        return input(invite).strip()

    def saisir_secret(self, invite: str) -> str:
        return getpass.getpass(invite)

    def demander_email(self, valeur):
        while True:
            email = (valeur or self.saisir("Adresse e-mail : ")).strip().lower()
            valeur = None
            try:
                validate_email(email)
            except ValidationError:
                self.stderr.write("Adresse e-mail invalide.")
                continue
            if Utilisateur.objects.filter(email__iexact=email).exists():
                raise CommandError(f"Un compte existe déjà pour {email}.")
            return email

    def demander_texte(self, valeur, invite):
        while not valeur:
            valeur = self.saisir(invite)
        return valeur

    def demander_mot_de_passe(self, email):
        while True:
            mot_de_passe = self.saisir_secret("Mot de passe : ")
            if mot_de_passe != self.saisir_secret("Mot de passe (confirmation) : "):
                self.stderr.write("Les deux mots de passe ne correspondent pas.")
                continue
            try:
                password_validation.validate_password(mot_de_passe, Utilisateur(email=email))
            except ValidationError as erreur:
                for message in erreur.messages:
                    self.stderr.write(message)
                continue
            return mot_de_passe

    def handle(self, *args, **options):
        email = self.demander_email(options["email"])
        prenom = self.demander_texte(options["prenom"], "Prénom : ")
        nom = self.demander_texte(options["nom"], "Nom : ")
        mot_de_passe = self.demander_mot_de_passe(email)
        try:
            admin = creer_administrateur(
                email=email, prenom=prenom, nom=nom, mot_de_passe=mot_de_passe
            )
        except ActionInterdite as erreur:
            raise CommandError(str(erreur)) from erreur
        self.stdout.write(self.style.SUCCESS(f"Administrateur créé : {admin.email}"))

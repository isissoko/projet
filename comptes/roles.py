"""Rôles de SIGAPS, représentés par des groupes Django du même nom."""

from django.db import models


class Role(models.TextChoices):
    ETUDIANT = "ETUDIANT", "Étudiant"
    ENSEIGNANT = "ENSEIGNANT", "Enseignant"
    BIBLIOTHECAIRE = "BIBLIOTHECAIRE", "Bibliothécaire"
    ADMINISTRATEUR = "ADMINISTRATEUR", "Administrateur"

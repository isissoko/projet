"""Utilisateur personnalisé : connexion par adresse e-mail unique."""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower


def normaliser_email(email: str) -> str:
    """Renvoie l'adresse sans espaces et entièrement en minuscules."""
    return (email or "").strip().lower()


class UtilisateurManager(BaseUserManager):
    use_in_migrations = True

    def _creer(self, email, password, **champs):
        if not email:
            raise ValueError("L'adresse e-mail est obligatoire.")
        utilisateur = self.model(email=normaliser_email(email), **champs)
        utilisateur.set_password(password)
        utilisateur.save(using=self._db)
        return utilisateur

    def create_user(self, email, password=None, **champs):
        champs.setdefault("is_staff", False)
        champs.setdefault("is_superuser", False)
        return self._creer(email, password, **champs)

    def create_superuser(self, email, password=None, **champs):
        champs.setdefault("is_staff", True)
        champs.setdefault("is_superuser", True)
        if champs["is_staff"] is not True or champs["is_superuser"] is not True:
            raise ValueError("Un superutilisateur doit avoir is_staff et is_superuser.")
        return self._creer(email, password, **champs)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=normaliser_email(email))


class Utilisateur(AbstractUser):
    username = None
    email = models.EmailField("adresse e-mail", unique=True)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UtilisateurManager()

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(Lower("email"), name="utilisateur_email_insensible_casse"),
        ]

    def __str__(self):
        return self.get_full_name() or self.email

    def clean(self):
        super().clean()
        self.email = normaliser_email(self.email)

    def save(self, *args, **kwargs):
        self.email = normaliser_email(self.email)
        super().save(*args, **kwargs)

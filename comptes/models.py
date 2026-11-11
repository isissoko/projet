"""Utilisateur personnalisé : connexion par adresse e-mail unique."""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower

from .roles import Role


def normaliser_email(email: str) -> str:
    """Renvoie l'adresse sans espaces et entièrement en minuscules."""
    return (email or "").strip().lower()


def normaliser_matricule(matricule: str) -> str:
    return "".join((matricule or "").split()).upper()


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

    # Rôles -----------------------------------------------------------------

    @property
    def roles(self) -> frozenset[str]:
        """Noms des rôles (groupes) de l'utilisateur, lus une seule fois par instance."""
        if not self.pk:
            return frozenset()
        if not hasattr(self, "_roles_cache"):
            self._roles_cache = frozenset(g.name for g in self.groups.all())
        return self._roles_cache

    def a_role(self, nom: str) -> bool:
        """Vrai si le compte est actif et possède ce rôle."""
        return self.is_active and nom in self.roles

    def a_un_role(self, *noms: str) -> bool:
        return self.is_active and bool(self.roles.intersection(noms))

    def oublier_roles(self):
        """À appeler après une modification des groupes."""
        self.__dict__.pop("_roles_cache", None)
        prefetch = getattr(self, "_prefetched_objects_cache", {})
        prefetch.pop("groups", None)

    def libelles_roles(self) -> list[str]:
        return [Role(r).label for r in Role.values if r in self.roles]


class ProfilEtudiant(models.Model):
    class Niveau(models.TextChoices):
        LICENCE = "LICENCE", "Licence"
        MASTER = "MASTER", "Master"
        DOCTORAT = "DOCTORAT", "Doctorat"

    utilisateur = models.OneToOneField(
        Utilisateur,
        on_delete=models.CASCADE,
        related_name="profil_etudiant",
        verbose_name="utilisateur",
    )
    matricule = models.CharField("matricule", max_length=30, unique=True)
    niveau = models.CharField("niveau", max_length=10, choices=Niveau.choices)
    filiere = models.ForeignKey(
        "referentiel.Filiere",
        on_delete=models.PROTECT,
        related_name="etudiants",
        verbose_name="filière",
    )

    class Meta:
        verbose_name = "profil étudiant"
        verbose_name_plural = "profils étudiants"

    def __str__(self):
        return f"{self.matricule} — {self.utilisateur}"

    def save(self, *args, **kwargs):
        self.matricule = normaliser_matricule(self.matricule)
        super().save(*args, **kwargs)


class ProfilEnseignant(models.Model):
    class Grade(models.TextChoices):
        ASSISTANT = "ASSISTANT", "Assistant"
        MAITRE_ASSISTANT = "MAITRE_ASSISTANT", "Maître-assistant"
        MAITRE_DE_CONFERENCES = "MAITRE_DE_CONFERENCES", "Maître de conférences"
        PROFESSEUR = "PROFESSEUR", "Professeur"

    utilisateur = models.OneToOneField(
        Utilisateur,
        on_delete=models.CASCADE,
        related_name="profil_enseignant",
        verbose_name="utilisateur",
    )
    grade = models.CharField("grade", max_length=25, choices=Grade.choices)
    specialite = models.CharField("spécialité", max_length=200, blank=True)
    departement = models.ForeignKey(
        "referentiel.Departement",
        on_delete=models.PROTECT,
        related_name="enseignants",
        verbose_name="département",
    )

    class Meta:
        verbose_name = "profil enseignant"
        verbose_name_plural = "profils enseignants"

    def __str__(self):
        return f"{self.get_grade_display()} {self.utilisateur}"

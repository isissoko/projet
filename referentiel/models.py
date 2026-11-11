"""Référentiel : établissements, départements, filières, années académiques, domaines, mots-clés.

Les éléments ne sont jamais supprimés lorsqu'ils sont utilisés : ils sont désactivés
(voir referentiel.services.supprimer_ou_desactiver).
"""

import re

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower


def normaliser_code(valeur: str) -> str:
    return (valeur or "").strip().upper()


def normaliser_libelle(valeur: str) -> str:
    """Retire les espaces superflus (début, fin, espaces multiples)."""
    return re.sub(r"\s+", " ", (valeur or "").strip())


class ElementReferentiel(models.Model):
    actif = models.BooleanField("actif", default=True)

    class Meta:
        abstract = True


class Etablissement(ElementReferentiel):
    code = models.CharField("code", max_length=20, unique=True)
    nom = models.CharField("nom", max_length=200)
    sigle = models.CharField("sigle", max_length=30, blank=True)

    class Meta:
        verbose_name = "établissement"
        verbose_name_plural = "établissements"
        ordering = ["nom"]

    def __str__(self):
        return self.sigle or self.nom

    def save(self, *args, **kwargs):
        self.code = normaliser_code(self.code)
        self.nom = normaliser_libelle(self.nom)
        super().save(*args, **kwargs)


class Departement(ElementReferentiel):
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.PROTECT,
        related_name="departements",
        verbose_name="établissement",
    )
    code = models.CharField("code", max_length=20)
    nom = models.CharField("nom", max_length=200)

    class Meta:
        verbose_name = "département"
        verbose_name_plural = "départements"
        ordering = ["nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["etablissement", "code"], name="departement_code_unique_par_etablissement"
            ),
        ]

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        self.code = normaliser_code(self.code)
        self.nom = normaliser_libelle(self.nom)
        super().save(*args, **kwargs)


class Filiere(ElementReferentiel):
    departement = models.ForeignKey(
        Departement,
        on_delete=models.PROTECT,
        related_name="filieres",
        verbose_name="département",
    )
    code = models.CharField("code", max_length=20, unique=True)
    libelle = models.CharField("libellé", max_length=200)

    class Meta:
        verbose_name = "filière"
        verbose_name_plural = "filières"
        ordering = ["libelle"]

    def __str__(self):
        return self.libelle

    def save(self, *args, **kwargs):
        self.code = normaliser_code(self.code)
        self.libelle = normaliser_libelle(self.libelle)
        super().save(*args, **kwargs)


class AnneeAcademique(ElementReferentiel):
    libelle = models.CharField(
        "libellé", max_length=9, unique=True, help_text="Au format 2025-2026."
    )
    date_debut = models.DateField("date de début")
    date_fin = models.DateField("date de fin")
    courante = models.BooleanField("année courante", default=False)

    class Meta:
        verbose_name = "année académique"
        verbose_name_plural = "années académiques"
        ordering = ["-date_debut"]
        constraints = [
            models.UniqueConstraint(
                fields=["courante"],
                condition=Q(courante=True),
                name="annee_academique_une_seule_courante",
            ),
            models.CheckConstraint(
                condition=Q(date_fin__gt=F("date_debut")),
                name="annee_academique_dates_coherentes",
            ),
        ]

    def __str__(self):
        return self.libelle

    def clean(self):
        super().clean()
        erreurs = {}
        correspondance = re.fullmatch(r"(\d{4})-(\d{4})", self.libelle or "")
        if not correspondance:
            erreurs["libelle"] = "Le libellé doit être au format 2025-2026."
        elif int(correspondance.group(2)) != int(correspondance.group(1)) + 1:
            erreurs["libelle"] = "La seconde année doit suivre immédiatement la première."
        if self.date_debut and self.date_fin and self.date_fin <= self.date_debut:
            erreurs["date_fin"] = "La date de fin doit être postérieure à la date de début."
        if self.courante and not self.actif:
            erreurs["actif"] = "L'année courante ne peut pas être désactivée."
        if erreurs:
            raise ValidationError(erreurs)


class Domaine(ElementReferentiel):
    code = models.CharField("code", max_length=20, unique=True)
    libelle = models.CharField("libellé", max_length=200)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="enfants",
        verbose_name="domaine parent",
    )

    class Meta:
        verbose_name = "domaine"
        verbose_name_plural = "domaines"
        ordering = ["libelle"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(parent=F("id")), name="domaine_pas_son_propre_parent"
            ),
        ]

    def __str__(self):
        return self.chemin

    def save(self, *args, **kwargs):
        self.code = normaliser_code(self.code)
        self.libelle = normaliser_libelle(self.libelle)
        super().save(*args, **kwargs)

    @property
    def chemin(self) -> str:
        """Libellé complet, par exemple « Sciences › Informatique »."""
        return " › ".join(d.libelle for d in reversed(list(self.ascendants(inclure_soi=True))))

    def ascendants(self, inclure_soi=False):
        """Parcourt les parents en remontant ; s'arrête si un cycle est détecté."""
        vus = set()
        courant = self if inclure_soi else self.parent
        while courant is not None and courant.pk not in vus:
            if courant.pk is not None:
                vus.add(courant.pk)
            yield courant
            courant = courant.parent

    def clean(self):
        super().clean()
        if self.parent_id is None:
            return
        if self.pk is not None:
            for ancetre in self.parent.ascendants(inclure_soi=True):
                if ancetre.pk == self.pk:
                    raise ValidationError(
                        {
                            "parent": "Un domaine ne peut pas être rangé sous lui-même ou sous un "
                            "de ses sous-domaines."
                        }
                    )


class MotCle(ElementReferentiel):
    libelle = models.CharField("libellé", max_length=100)

    class Meta:
        verbose_name = "mot-clé"
        verbose_name_plural = "mots-clés"
        ordering = ["libelle"]
        constraints = [
            models.UniqueConstraint(
                Lower("libelle"), name="mot_cle_libelle_unique_insensible_casse"
            ),
        ]

    def __str__(self):
        return self.libelle

    def save(self, *args, **kwargs):
        self.libelle = normaliser_libelle(self.libelle)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self.libelle = normaliser_libelle(self.libelle)
        doublon = MotCle.objects.filter(libelle__iexact=self.libelle).exclude(pk=self.pk)
        if self.libelle and doublon.exists():
            raise ValidationError({"libelle": "Ce mot-clé existe déjà."})

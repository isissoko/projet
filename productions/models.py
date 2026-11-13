"""Productions académiques : mémoires, thèses, versions, contributeurs, encadrements.

Règles reprises en base : RG02 (un directeur), RG05 (versions jamais supprimées),
RG06 (format et unicité de la cote), RG07 (motifs), RG12 (niveau des mémoires, mentions
réservées aux thèses).
"""

import re
import uuid

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.core.exceptions import ValidationError
from django.core.files.storage import storages
from django.db import models
from django.db.models import Max, Q

from comptes.exceptions import ActionInterdite


class SuppressionInterdite(ActionInterdite):
    """Une version de document ne peut jamais être supprimée (RG05)."""


# Énumérations -----------------------------------------------------------------


class Statut(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    SOUMIS = "SOUMIS", "Soumis à l'encadreur"
    A_CORRIGER_ENCADREUR = "A_CORRIGER_ENCADREUR", "Corrections demandées par l'encadreur"
    REJETE = "REJETE", "Rejeté"
    VALIDE = "VALIDE", "Validé par l'encadreur"
    A_CORRIGER_BIBLIOTHEQUE = "A_CORRIGER_BIBLIOTHEQUE", "Corrections demandées par la bibliothèque"
    ARCHIVE = "ARCHIVE", "Archivé"
    RETIRE = "RETIRE", "Retiré"


class TypeProduction(models.TextChoices):
    MEMOIRE = "MEMOIRE", "Mémoire"
    THESE = "THESE", "Thèse"


class NiveauAcces(models.TextChoices):
    LIBRE = "LIBRE", "Libre accès"
    RESTREINT = "RESTREINT", "Accès restreint (utilisateurs connectés)"
    CONFIDENTIEL = "CONFIDENTIEL", "Confidentiel"


class Langue(models.TextChoices):
    FRANCAIS = "FRANCAIS", "Français"
    ANGLAIS = "ANGLAIS", "Anglais"
    BAMBARA = "BAMBARA", "Bambara"
    AUTRE = "AUTRE", "Autre"


class Mention(models.TextChoices):
    PASSABLE = "PASSABLE", "Passable"
    ASSEZ_BIEN = "ASSEZ_BIEN", "Assez bien"
    BIEN = "BIEN", "Bien"
    TRES_BIEN = "TRES_BIEN", "Très bien"
    HONORABLE = "HONORABLE", "Honorable"
    TRES_HONORABLE = "TRES_HONORABLE", "Très honorable"


MENTIONS_MEMOIRE = [Mention.PASSABLE, Mention.ASSEZ_BIEN, Mention.BIEN, Mention.TRES_BIEN]
MENTIONS_THESE = [Mention.HONORABLE, Mention.TRES_HONORABLE]


class NiveauMemoire(models.TextChoices):
    LICENCE = "LICENCE", "Licence"
    MASTER = "MASTER", "Master"


# Production -------------------------------------------------------------------

REGEX_COTE = r"^(MEM|THE)-[0-9]{4}-[0-9]{4,}$"


class Production(models.Model):
    """Production concrète (héritage multi-tables) : toujours créée via Memoire ou These."""

    type_production = models.CharField(
        "type", max_length=10, choices=TypeProduction.choices, editable=False
    )
    titre = models.CharField("titre", max_length=500)
    resume = models.TextField("résumé", blank=True)
    langue = models.CharField(
        "langue", max_length=10, choices=Langue.choices, default=Langue.FRANCAIS
    )
    statut = models.CharField(
        "statut", max_length=25, choices=Statut.choices, default=Statut.BROUILLON, editable=False
    )
    # NULL tant que la bibliothèque n'a pas archivé le travail (« pas encore décidé »).
    niveau_acces = models.CharField(  # noqa: DJ001
        "niveau d'accès", max_length=15, choices=NiveauAcces.choices, null=True, blank=True
    )
    date_fin_embargo = models.DateField("fin d'embargo", null=True, blank=True)
    cote = models.CharField("cote", max_length=20, unique=True, null=True, blank=True)
    date_soutenance = models.DateField("date de soutenance", null=True, blank=True)
    # NULL = pas encore de mention ; les CheckConstraint RG12 s'appuient sur cette valeur.
    mention = models.CharField(  # noqa: DJ001
        "mention", max_length=15, choices=Mention.choices, null=True, blank=True
    )
    filiere = models.ForeignKey(
        "referentiel.Filiere",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="productions",
        verbose_name="filière",
    )
    annee_academique = models.ForeignKey(
        "referentiel.AnneeAcademique",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="productions",
        verbose_name="année académique",
    )
    domaine = models.ForeignKey(
        "referentiel.Domaine",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="productions",
        verbose_name="domaine",
    )
    mots_cles = models.ManyToManyField(
        "referentiel.MotCle", blank=True, related_name="productions", verbose_name="mots-clés"
    )
    date_creation = models.DateTimeField("créée le", auto_now_add=True)
    date_modification = models.DateTimeField("modifiée le", auto_now=True)
    date_soumission = models.DateTimeField("soumise le", null=True, blank=True, editable=False)
    date_archivage = models.DateTimeField("archivée le", null=True, blank=True, editable=False)
    motif_retrait = models.TextField("motif du retrait", blank=True, editable=False)
    date_retrait = models.DateTimeField("retirée le", null=True, blank=True, editable=False)
    # Vecteur plein texte (configuration french_sans_accents), tenu à jour par
    # productions.indexation.indexer : titre et mots-clés (A), personnes et classement (B),
    # résumé (C).
    vecteur_recherche = SearchVectorField("vecteur de recherche", null=True, editable=False)

    class Meta:
        verbose_name = "production"
        verbose_name_plural = "productions"
        ordering = ["-date_modification"]
        indexes = [GinIndex(fields=["vecteur_recherche"], name="production_recherche_gin")]
        constraints = [
            models.CheckConstraint(
                condition=Q(type_production__in=TypeProduction.values),
                name="production_type_valide",
            ),
            models.CheckConstraint(
                condition=Q(statut__in=Statut.values), name="production_statut_valide"
            ),
            models.CheckConstraint(
                condition=Q(niveau_acces__isnull=True) | Q(niveau_acces__in=NiveauAcces.values),
                name="production_niveau_acces_valide",
            ),
            # RG06 : {CODE_TYPE}-{ANNEE}-{NUMERO:04d}.
            models.CheckConstraint(
                condition=Q(cote__isnull=True) | Q(cote__regex=REGEX_COTE),
                name="production_cote_format",
            ),
            # Un travail archivé (ou retiré après archivage) a une cote, un niveau d'accès
            # et une date d'archivage.
            models.CheckConstraint(
                condition=~Q(statut__in=[Statut.ARCHIVE, Statut.RETIRE])
                | Q(
                    cote__isnull=False,
                    niveau_acces__isnull=False,
                    date_archivage__isnull=False,
                ),
                name="production_archivee_complete",
            ),
            # RG07 : motif obligatoire pour retirer.
            models.CheckConstraint(
                condition=~Q(statut=Statut.RETIRE)
                | Q(motif_retrait__regex=r"\S", date_retrait__isnull=False),
                name="production_retrait_motive",
            ),
            # RG12 : mentions HONORABLE et TRES_HONORABLE réservées aux thèses.
            models.CheckConstraint(
                condition=~Q(type_production=TypeProduction.MEMOIRE, mention__in=MENTIONS_THESE),
                name="production_mention_these_interdite_pour_memoire",
            ),
            models.CheckConstraint(
                condition=~Q(type_production=TypeProduction.THESE, mention__in=MENTIONS_MEMOIRE),
                name="production_mention_memoire_interdite_pour_these",
            ),
        ]

    TYPE: str | None = None  # défini par Memoire et These

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.TYPE and not self.type_production:
            self.type_production = self.TYPE

    def __str__(self):
        return self.titre

    def delete(self, *args, **kwargs):
        # Seul le service supprimer_brouillon supprime une production (RG05).
        if self.statut != Statut.BROUILLON:
            raise SuppressionInterdite("Seul un brouillon peut être supprimé.")
        return super().delete(*args, **kwargs)

    def clean(self):
        super().clean()
        autorisees = (
            MENTIONS_THESE if self.type_production == TypeProduction.THESE else (MENTIONS_MEMOIRE)
        )
        if self.mention and self.mention not in autorisees:
            raise ValidationError(
                {"mention": f"Cette mention n'est pas possible pour un(e) {self.libelle_type}."}
            )

    def code_type(self) -> str:
        return "THE" if self.type_production == TypeProduction.THESE else "MEM"

    @property
    def libelle_type(self) -> str:
        return TypeProduction(self.type_production).label.lower() if self.type_production else ""

    def specifique(self):
        """Renvoie l'instance Memoire ou These correspondante."""
        if isinstance(self, (Memoire, These)):
            return self
        if self.type_production == TypeProduction.THESE:
            return self.these
        return self.memoire

    def version_courante(self):
        return self.versions.order_by("-numero").first()

    @property
    def est_brouillon(self) -> bool:
        return self.statut == Statut.BROUILLON

    @property
    def est_archive(self) -> bool:
        return self.statut == Statut.ARCHIVE


class Memoire(Production):
    TYPE = TypeProduction.MEMOIRE

    niveau = models.CharField("niveau", max_length=10, choices=NiveauMemoire.choices)

    class Meta:
        verbose_name = "mémoire"
        verbose_name_plural = "mémoires"
        constraints = [
            # RG12 : un mémoire est de niveau Licence ou Master, jamais Doctorat.
            models.CheckConstraint(
                condition=Q(niveau__in=NiveauMemoire.values), name="memoire_niveau_licence_master"
            ),
        ]

    def save(self, *args, **kwargs):
        self.type_production = TypeProduction.MEMOIRE
        super().save(*args, **kwargs)


class These(Production):
    TYPE = TypeProduction.THESE

    class Meta:
        verbose_name = "thèse"
        verbose_name_plural = "thèses"

    def save(self, *args, **kwargs):
        self.type_production = TypeProduction.THESE
        super().save(*args, **kwargs)


# Versions -----------------------------------------------------------------------


def stockage_prive():
    """Stockage hors MEDIA public : les fichiers ne sont servis que par la vue contrôlée."""
    return storages["prive"]


def chemin_version(instance, nom_fichier):
    return f"versions/{uuid.uuid4().hex}.pdf"


class VersionDocumentQuerySet(models.QuerySet):
    def delete(self):
        raise SuppressionInterdite("Les versions de document ne sont jamais supprimées.")

    delete.queryset_only = True

    def _supprimer_versions_d_un_brouillon(self):
        """Seul chemin autorisé (décision Q2 de la phase 2) : appelé par supprimer_brouillon,
        pour un brouillon jamais soumis. Ne pas utiliser ailleurs."""
        return super().delete()


class VersionDocument(models.Model):
    production = models.ForeignKey(
        Production, on_delete=models.PROTECT, related_name="versions", verbose_name="production"
    )
    numero = models.PositiveIntegerField("numéro")
    fichier = models.FileField(
        "fichier", storage=stockage_prive, upload_to=chemin_version, max_length=255
    )
    nom_original = models.CharField("nom d'origine", max_length=255)
    taille = models.PositiveBigIntegerField("taille (octets)")
    empreinte_sha256 = models.CharField("empreinte SHA-256", max_length=64)
    date_depot = models.DateTimeField("déposée le", auto_now_add=True)
    depose_par = models.ForeignKey(
        "comptes.Utilisateur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="versions_deposees",
        verbose_name="déposée par",
    )
    note_corrections = models.TextField(
        "note de corrections",
        blank=True,
        help_text="Ce que l'auteur a corrigé dans cette version (version corrigée).",
    )

    objects = VersionDocumentQuerySet.as_manager()

    class Meta:
        verbose_name = "version de document"
        verbose_name_plural = "versions de document"
        ordering = ["production", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["production", "numero"], name="version_numero_unique_par_production"
            ),
            models.CheckConstraint(condition=Q(numero__gte=1), name="version_numero_positif"),
            models.CheckConstraint(
                condition=Q(empreinte_sha256__regex=r"^[0-9a-f]{64}$"),
                name="version_empreinte_sha256_hexadecimale",
            ),
        ]

    def __str__(self):
        return f"Version {self.numero} — {self.production}"

    def delete(self, *args, **kwargs):
        raise SuppressionInterdite("Les versions de document ne sont jamais supprimées.")

    @staticmethod
    def prochain_numero(production) -> int:
        dernier = VersionDocument.objects.filter(production=production).aggregate(n=Max("numero"))
        return (dernier["n"] or 0) + 1

    @property
    def empreinte_abregee(self) -> str:
        return f"{self.empreinte_sha256[:8]}…{self.empreinte_sha256[-8:]}"


# Contributeurs et encadrements -----------------------------------------------------

ORCID_REGEX = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def valider_orcid(valeur):
    if valeur and not ORCID_REGEX.match(valeur):
        raise ValidationError("L'ORCID doit avoir la forme 0000-0002-1825-0097.")


class Contributeur(models.Model):
    """Auteur d'une production : lié à un compte, ou co-auteur externe sans compte."""

    nom = models.CharField("nom", max_length=150)
    prenom = models.CharField("prénom", max_length=150)
    affiliation = models.CharField("affiliation", max_length=200, blank=True)
    orcid = models.CharField(
        "ORCID", max_length=19, unique=True, null=True, blank=True, validators=[valider_orcid]
    )
    utilisateur = models.OneToOneField(
        "comptes.Utilisateur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contributeur",
        verbose_name="compte",
    )

    class Meta:
        verbose_name = "contributeur"
        verbose_name_plural = "contributeurs"
        ordering = ["nom", "prenom"]

    def __str__(self):
        return f"{self.prenom} {self.nom}".strip()

    def save(self, *args, **kwargs):
        self.orcid = (self.orcid or "").strip().upper() or None
        super().save(*args, **kwargs)


class RoleContribution(models.TextChoices):
    AUTEUR_PRINCIPAL = "AUTEUR_PRINCIPAL", "Auteur principal"
    CO_AUTEUR = "CO_AUTEUR", "Co-auteur"


class Contribution(models.Model):
    production = models.ForeignKey(
        Production, on_delete=models.CASCADE, related_name="contributions"
    )
    contributeur = models.ForeignKey(
        Contributeur, on_delete=models.PROTECT, related_name="contributions"
    )
    rang = models.PositiveSmallIntegerField("rang")
    role = models.CharField("rôle", max_length=20, choices=RoleContribution.choices)

    class Meta:
        verbose_name = "contribution"
        verbose_name_plural = "contributions"
        ordering = ["production", "rang"]
        constraints = [
            models.UniqueConstraint(
                fields=["production", "rang"], name="contribution_rang_unique_par_production"
            ),
            models.UniqueConstraint(
                fields=["production"],
                condition=Q(role=RoleContribution.AUTEUR_PRINCIPAL),
                name="contribution_un_seul_auteur_principal",
            ),
            models.UniqueConstraint(
                fields=["production", "contributeur"],
                name="contribution_contributeur_unique_par_production",
            ),
            models.CheckConstraint(condition=Q(rang__gte=1), name="contribution_rang_positif"),
        ]

    def __str__(self):
        return f"{self.contributeur} ({self.get_role_display()})"


class RoleEncadrement(models.TextChoices):
    DIRECTEUR = "DIRECTEUR", "Directeur"
    CO_DIRECTEUR = "CO_DIRECTEUR", "Co-directeur"


class Encadrement(models.Model):
    production = models.ForeignKey(
        Production, on_delete=models.CASCADE, related_name="encadrements"
    )
    enseignant = models.ForeignKey(
        "comptes.ProfilEnseignant", on_delete=models.PROTECT, related_name="encadrements"
    )
    role = models.CharField("rôle", max_length=15, choices=RoleEncadrement.choices)

    class Meta:
        verbose_name = "encadrement"
        verbose_name_plural = "encadrements"
        ordering = ["production", "role", "id"]
        constraints = [
            # RG02 : exactement un directeur par travail (le « au moins un » est vérifié
            # à la soumission).
            models.UniqueConstraint(
                fields=["production"],
                condition=Q(role=RoleEncadrement.DIRECTEUR),
                name="encadrement_un_seul_directeur",
            ),
            models.UniqueConstraint(
                fields=["production", "enseignant"],
                name="encadrement_enseignant_unique_par_production",
            ),
        ]

    def __str__(self):
        return f"{self.enseignant.utilisateur} ({self.get_role_display()})"


# Avis d'encadrement -------------------------------------------------------------------


class Avis(models.TextChoices):
    FAVORABLE = "FAVORABLE", "Favorable"
    CORRECTIONS_DEMANDEES = "CORRECTIONS_DEMANDEES", "Corrections demandées"
    DEFAVORABLE = "DEFAVORABLE", "Défavorable"


class AvisEncadrementQuerySet(models.QuerySet):
    def delete(self):
        raise SuppressionInterdite("Les avis d'encadrement ne sont jamais supprimés.")

    delete.queryset_only = True


class AvisEncadrement(models.Model):
    """Historique des avis. Seul l'avis du directeur change le statut (RG02)."""

    production = models.ForeignKey(
        Production, on_delete=models.PROTECT, related_name="avis", verbose_name="production"
    )
    encadrement = models.ForeignKey(
        Encadrement, on_delete=models.PROTECT, related_name="avis", verbose_name="encadrant"
    )
    version = models.ForeignKey(
        VersionDocument,
        on_delete=models.PROTECT,
        related_name="avis",
        verbose_name="version évaluée",
    )
    avis = models.CharField("avis", max_length=25, choices=Avis.choices)
    commentaire = models.TextField("commentaire", blank=True)
    date = models.DateTimeField("date", auto_now_add=True)

    objects = AvisEncadrementQuerySet.as_manager()

    class Meta:
        verbose_name = "avis d'encadrement"
        verbose_name_plural = "avis d'encadrement"
        ordering = ["-date", "-id"]
        constraints = [
            # RG07 : motif obligatoire pour demander des corrections ou rejeter.
            models.CheckConstraint(
                condition=Q(avis=Avis.FAVORABLE) | Q(commentaire__regex=r"\S"),
                name="avis_motif_obligatoire_sauf_favorable",
            ),
            models.CheckConstraint(condition=Q(avis__in=Avis.values), name="avis_valeur_valide"),
            models.UniqueConstraint(
                fields=["encadrement", "version"], name="avis_un_seul_par_encadrant_et_version"
            ),
        ]

    def __str__(self):
        return f"{self.get_avis_display()} — {self.encadrement}"

    def delete(self, *args, **kwargs):
        raise SuppressionInterdite("Les avis d'encadrement ne sont jamais supprimés.")

    @property
    def est_du_directeur(self) -> bool:
        return self.encadrement.role == RoleEncadrement.DIRECTEUR


# Contrôle de la bibliothèque et cote ---------------------------------------------------


class DecisionVerification(models.TextChoices):
    CONFORME = "CONFORME", "Conforme"
    A_CORRIGER = "A_CORRIGER", "À corriger"


class VerificationDocumentaireQuerySet(models.QuerySet):
    def delete(self):
        raise SuppressionInterdite("Les vérifications documentaires ne sont jamais supprimées.")

    delete.queryset_only = True


class VerificationDocumentaire(models.Model):
    """Décision de la bibliothèque sur une version (BF07). Historique jamais supprimé."""

    production = models.ForeignKey(
        Production,
        on_delete=models.PROTECT,
        related_name="verifications",
        verbose_name="production",
    )
    version = models.ForeignKey(
        VersionDocument,
        on_delete=models.PROTECT,
        related_name="verifications",
        verbose_name="version contrôlée",
    )
    bibliothecaire = models.ForeignKey(
        "comptes.Utilisateur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verifications",
        verbose_name="bibliothécaire",
    )
    decision = models.CharField("décision", max_length=15, choices=DecisionVerification.choices)
    motif = models.TextField("motif", blank=True)
    date = models.DateTimeField("date", auto_now_add=True)

    objects = VerificationDocumentaireQuerySet.as_manager()

    class Meta:
        verbose_name = "vérification documentaire"
        verbose_name_plural = "vérifications documentaires"
        ordering = ["-date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(decision__in=DecisionVerification.values),
                name="verification_decision_valide",
            ),
            # RG07 : motif obligatoire pour demander des corrections.
            models.CheckConstraint(
                condition=Q(decision=DecisionVerification.CONFORME) | Q(motif__regex=r"\S"),
                name="verification_motif_obligatoire_si_a_corriger",
            ),
        ]

    def __str__(self):
        return f"{self.get_decision_display()} — {self.production}"

    def delete(self, *args, **kwargs):
        raise SuppressionInterdite("Les vérifications documentaires ne sont jamais supprimées.")


class CodeType(models.TextChoices):
    MEM = "MEM", "Mémoire"
    THE = "THE", "Thèse"


class CompteurCote(models.Model):
    """Dernier numéro de cote attribué pour un type et une année (RG06).

    Lu et incrémenté sous verrou (select_for_update) : les productions existantes ne sont
    jamais comptées.
    """

    code_type = models.CharField("type", max_length=3, choices=CodeType.choices)
    annee = models.PositiveSmallIntegerField("année")
    dernier_numero = models.PositiveIntegerField("dernier numéro attribué", default=0)

    class Meta:
        verbose_name = "compteur de cote"
        verbose_name_plural = "compteurs de cote"
        ordering = ["-annee", "code_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["code_type", "annee"], name="compteur_cote_unique_par_type_et_annee"
            ),
            models.CheckConstraint(
                condition=Q(code_type__in=CodeType.values), name="compteur_cote_type_valide"
            ),
            models.CheckConstraint(
                condition=Q(annee__gte=1000, annee__lte=9999),
                name="compteur_cote_annee_sur_quatre_chiffres",
            ),
        ]

    def __str__(self):
        return f"{self.code_type}-{self.annee} : {self.dernier_numero}"

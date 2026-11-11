from django.contrib import admin

from .models import (
    AvisEncadrement,
    CompteurCote,
    Contributeur,
    Contribution,
    Encadrement,
    Memoire,
    Production,
    These,
    VerificationDocumentaire,
    VersionDocument,
)


class VersionDocumentInline(admin.TabularInline):
    model = VersionDocument
    extra = 0
    can_delete = False
    fields = ("numero", "nom_original", "taille", "empreinte_sha256", "date_depot", "depose_par")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class ContributionInline(admin.TabularInline):
    model = Contribution
    extra = 0
    raw_id_fields = ("contributeur",)


class EncadrementInline(admin.TabularInline):
    model = Encadrement
    extra = 0
    raw_id_fields = ("enseignant",)


class ProductionAdminBase(admin.ModelAdmin):
    """Dépannage uniquement : les changements de statut passent par les services."""

    list_display = ("titre", "type_production", "statut", "filiere", "date_modification")
    list_filter = ("type_production", "statut", "filiere")
    search_fields = ("titre", "cote")
    readonly_fields = (
        "type_production",
        "statut",
        "cote",
        "date_soumission",
        "date_archivage",
        "motif_retrait",
        "date_retrait",
    )
    filter_horizontal = ("mots_cles",)
    inlines = (ContributionInline, EncadrementInline, VersionDocumentInline)

    def has_delete_permission(self, request, obj=None):
        return False  # suppression : uniquement par le service supprimer_brouillon


@admin.register(Production)
class ProductionAdmin(ProductionAdminBase):
    def has_add_permission(self, request):
        return False  # toujours créer un mémoire ou une thèse


@admin.register(Memoire)
class MemoireAdmin(ProductionAdminBase):
    list_display = (*ProductionAdminBase.list_display, "niveau")


@admin.register(These)
class TheseAdmin(ProductionAdminBase):
    pass


@admin.register(VersionDocument)
class VersionDocumentAdmin(admin.ModelAdmin):
    list_display = ("production", "numero", "nom_original", "taille", "date_depot")
    search_fields = ("production__titre", "empreinte_sha256", "nom_original")
    readonly_fields = (
        "production",
        "numero",
        "fichier",
        "nom_original",
        "taille",
        "empreinte_sha256",
        "date_depot",
        "depose_par",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # RG05 : versions jamais supprimées


@admin.register(Contributeur)
class ContributeurAdmin(admin.ModelAdmin):
    list_display = ("nom", "prenom", "affiliation", "orcid", "utilisateur")
    search_fields = ("nom", "prenom", "orcid", "utilisateur__email")
    raw_id_fields = ("utilisateur",)


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = ("production", "contributeur", "rang", "role")
    raw_id_fields = ("production", "contributeur")


@admin.register(Encadrement)
class EncadrementAdmin(admin.ModelAdmin):
    list_display = ("production", "enseignant", "role")
    list_filter = ("role",)
    raw_id_fields = ("production", "enseignant")


@admin.register(AvisEncadrement)
class AvisEncadrementAdmin(admin.ModelAdmin):
    """Historique en lecture seule : un avis n'est ni modifié ni supprimé."""

    list_display = ("production", "encadrement", "version", "avis", "date")
    list_filter = ("avis",)
    search_fields = ("production__titre",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VerificationDocumentaire)
class VerificationDocumentaireAdmin(admin.ModelAdmin):
    """Historique en lecture seule : une vérification n'est ni modifiée ni supprimée."""

    list_display = ("production", "version", "decision", "bibliothecaire", "date")
    list_filter = ("decision",)
    search_fields = ("production__titre", "production__cote")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CompteurCote)
class CompteurCoteAdmin(admin.ModelAdmin):
    """Consultation seule : les compteurs ne sont modifiés que par le service d'archivage."""

    list_display = ("code_type", "annee", "dernier_numero")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

from django.contrib import admin

from .models import AnneeAcademique, Departement, Domaine, Etablissement, Filiere, MotCle


@admin.register(Etablissement)
class EtablissementAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "sigle", "actif")
    list_filter = ("actif",)
    search_fields = ("code", "nom", "sigle")


@admin.register(Departement)
class DepartementAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "etablissement", "actif")
    list_filter = ("actif", "etablissement")
    search_fields = ("code", "nom")


@admin.register(Filiere)
class FiliereAdmin(admin.ModelAdmin):
    list_display = ("code", "libelle", "departement", "actif")
    list_filter = ("actif", "departement")
    search_fields = ("code", "libelle")


@admin.register(AnneeAcademique)
class AnneeAcademiqueAdmin(admin.ModelAdmin):
    list_display = ("libelle", "date_debut", "date_fin", "courante", "actif")
    list_filter = ("courante", "actif")


@admin.register(Domaine)
class DomaineAdmin(admin.ModelAdmin):
    list_display = ("code", "libelle", "parent", "actif")
    list_filter = ("actif",)
    search_fields = ("code", "libelle")


@admin.register(MotCle)
class MotCleAdmin(admin.ModelAdmin):
    list_display = ("libelle", "actif")
    list_filter = ("actif",)
    search_fields = ("libelle",)

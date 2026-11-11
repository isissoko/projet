from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import ProfilEnseignant, ProfilEtudiant, Utilisateur


class UtilisateurCreationForm(UserCreationForm):
    class Meta:
        model = Utilisateur
        fields = ("email", "first_name", "last_name")


class UtilisateurChangeForm(UserChangeForm):
    class Meta:
        model = Utilisateur
        fields = "__all__"


class ProfilEtudiantInline(admin.StackedInline):
    model = ProfilEtudiant
    can_delete = False
    extra = 0


class ProfilEnseignantInline(admin.StackedInline):
    model = ProfilEnseignant
    can_delete = False
    extra = 0


@admin.register(ProfilEtudiant)
class ProfilEtudiantAdmin(admin.ModelAdmin):
    list_display = ("matricule", "utilisateur", "niveau", "filiere")
    list_filter = ("niveau", "filiere")
    search_fields = ("matricule", "utilisateur__email", "utilisateur__last_name")
    raw_id_fields = ("utilisateur",)


@admin.register(ProfilEnseignant)
class ProfilEnseignantAdmin(admin.ModelAdmin):
    list_display = ("utilisateur", "grade", "specialite", "departement")
    list_filter = ("grade", "departement")
    search_fields = ("utilisateur__email", "utilisateur__last_name", "specialite")
    raw_id_fields = ("utilisateur",)


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    inlines = (ProfilEtudiantInline, ProfilEnseignantInline)
    list_filter = ("is_active", "is_staff", "groups")
    form = UtilisateurChangeForm
    add_form = UtilisateurCreationForm
    ordering = ("last_name", "first_name")
    list_display = ("email", "first_name", "last_name", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Identité", {"fields": ("first_name", "last_name")}),
        (
            "Droits",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "password1", "password2"),
            },
        ),
    )

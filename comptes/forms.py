from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.db.models import Q

from referentiel.models import Departement, Filiere

from .models import (
    ProfilEnseignant,
    ProfilEtudiant,
    Utilisateur,
    normaliser_email,
    normaliser_matricule,
)
from .roles import Role
from .services import DonneesProfilEnseignant, DonneesProfilEtudiant


class ConnexionForm(AuthenticationForm):
    username = forms.EmailField(
        label="Adresse e-mail",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )
    error_messages = {
        "invalid_login": "Adresse e-mail ou mot de passe incorrect.",
        "inactive": "Ce compte est désactivé.",
    }


class ReinitialisationForm(PasswordResetForm):
    """Comme le formulaire Django, mais accepte aussi les comptes invités sans mot de passe.

    Un utilisateur qui a perdu son e-mail d'invitation peut ainsi définir son mot de passe.
    """

    def get_users(self, email):
        return Utilisateur.objects.filter(email__iexact=normaliser_email(email), is_active=True)


class RechercheComptesForm(forms.Form):
    q = forms.CharField(label="Nom ou e-mail", required=False)
    role = forms.ChoiceField(
        label="Rôle", required=False, choices=[("", "Tous les rôles"), *Role.choices]
    )
    actif = forms.ChoiceField(
        label="État",
        required=False,
        choices=[("", "Tous"), ("1", "Actifs"), ("0", "Désactivés")],
    )


class CompteForm(forms.Form):
    """Création et modification d'un compte, avec les profils selon les rôles cochés."""

    email = forms.EmailField(label="Adresse e-mail")
    prenom = forms.CharField(label="Prénom", max_length=150)
    nom = forms.CharField(label="Nom", max_length=150)
    roles = forms.MultipleChoiceField(
        label="Rôles", choices=Role.choices, widget=forms.CheckboxSelectMultiple
    )

    matricule = forms.CharField(label="Matricule", max_length=30, required=False)
    niveau = forms.ChoiceField(
        label="Niveau", required=False, choices=[("", "—"), *ProfilEtudiant.Niveau.choices]
    )
    filiere = forms.ModelChoiceField(
        label="Filière", required=False, queryset=Filiere.objects.none()
    )

    grade = forms.ChoiceField(
        label="Grade", required=False, choices=[("", "—"), *ProfilEnseignant.Grade.choices]
    )
    specialite = forms.CharField(label="Spécialité", max_length=200, required=False)
    departement = forms.ModelChoiceField(
        label="Département", required=False, queryset=Departement.objects.none()
    )

    CHAMPS_ETUDIANT = ("matricule", "niveau", "filiere")
    CHAMPS_ENSEIGNANT = ("grade", "departement")

    def __init__(self, *args, utilisateur: Utilisateur | None = None, **kwargs):
        self.utilisateur = utilisateur
        if utilisateur is not None:
            # FormView transmet toujours initial={} : on fusionne au lieu de setdefault.
            kwargs["initial"] = {**self.valeurs_initiales(utilisateur), **kwargs.get("initial", {})}
        super().__init__(*args, **kwargs)
        # Seuls les éléments actifs sont proposés, plus la valeur actuelle du compte modifié.
        initial = self.initial
        self.fields["filiere"].queryset = Filiere.objects.filter(
            Q(actif=True) | Q(pk=getattr(initial.get("filiere"), "pk", None))
        )
        self.fields["departement"].queryset = Departement.objects.filter(
            Q(actif=True) | Q(pk=getattr(initial.get("departement"), "pk", None))
        )

    @staticmethod
    def valeurs_initiales(utilisateur: Utilisateur) -> dict:
        valeurs = {
            "email": utilisateur.email,
            "prenom": utilisateur.first_name,
            "nom": utilisateur.last_name,
            "roles": sorted(utilisateur.roles),
        }
        profil = getattr(utilisateur, "profil_etudiant", None)
        if profil:
            valeurs.update(matricule=profil.matricule, niveau=profil.niveau, filiere=profil.filiere)
        profil = getattr(utilisateur, "profil_enseignant", None)
        if profil:
            valeurs.update(
                grade=profil.grade, specialite=profil.specialite, departement=profil.departement
            )
        return valeurs

    def clean_email(self):
        email = normaliser_email(self.cleaned_data["email"])
        autres = Utilisateur.objects.filter(email__iexact=email)
        if self.utilisateur is not None:
            autres = autres.exclude(pk=self.utilisateur.pk)
        if autres.exists():
            raise forms.ValidationError("Cette adresse e-mail est déjà utilisée.")
        return email

    def clean_matricule(self):
        matricule = normaliser_matricule(self.cleaned_data.get("matricule", ""))
        if matricule:
            autres = ProfilEtudiant.objects.filter(matricule=matricule)
            if self.utilisateur is not None:
                autres = autres.exclude(utilisateur=self.utilisateur)
            if autres.exists():
                raise forms.ValidationError("Ce matricule est déjà attribué à un autre étudiant.")
        return matricule

    def clean(self):
        donnees = super().clean()
        roles = set(donnees.get("roles", []))
        obligatoires = []
        if Role.ETUDIANT in roles:
            obligatoires += self.CHAMPS_ETUDIANT
        if Role.ENSEIGNANT in roles:
            obligatoires += self.CHAMPS_ENSEIGNANT
        for champ in obligatoires:
            if not donnees.get(champ) and champ not in self.errors:
                self.add_error(champ, "Ce champ est obligatoire pour le rôle choisi.")
        return donnees

    # Conversion vers les arguments des services -------------------------

    def arguments_service(self) -> dict:
        d = self.cleaned_data
        roles = set(d["roles"])
        return {
            "email": d["email"],
            "prenom": d["prenom"],
            "nom": d["nom"],
            "roles": roles,
            "profil_etudiant": DonneesProfilEtudiant(d["matricule"], d["niveau"], d["filiere"])
            if Role.ETUDIANT in roles
            else None,
            "profil_enseignant": DonneesProfilEnseignant(
                d["grade"], d["specialite"], d["departement"]
            )
            if Role.ENSEIGNANT in roles
            else None,
        }

from django import forms
from django.db.models import Q

from comptes.models import Utilisateur, normaliser_email
from referentiel.models import AnneeAcademique, Domaine, Filiere, MotCle

from .models import (
    MENTIONS_MEMOIRE,
    MENTIONS_THESE,
    Avis,
    Langue,
    Memoire,
    Mention,
    NiveauMemoire,
    RoleEncadrement,
    TypeProduction,
    valider_orcid,
)
from .services import DonneesCoauteur
from .validators import TAILLE_MAX_PDF, valider_pdf


def _actifs(modele, actuel_pk=None, actuels=()):
    """Éléments actifs du référentiel, plus ceux déjà choisis (même s'ils ont été désactivés)."""
    filtre = Q(actif=True)
    if actuel_pk:
        filtre |= Q(pk=actuel_pk)
    if actuels:
        filtre |= Q(pk__in=actuels)
    return modele.objects.filter(filtre)


class MetadonneesForm(forms.Form):
    """Étape 1 : type et métadonnées. Seuls le type, le titre et la langue (et le niveau d'un
    mémoire) sont exigés pour enregistrer le brouillon ; le reste est vérifié à la soumission."""

    type_production = forms.ChoiceField(
        label="Type de travail", choices=TypeProduction.choices, widget=forms.RadioSelect
    )
    titre = forms.CharField(label="Titre", max_length=500)
    resume = forms.CharField(
        label="Résumé", required=False, widget=forms.Textarea(attrs={"rows": 6})
    )
    langue = forms.ChoiceField(label="Langue du document", choices=Langue.choices)
    niveau = forms.ChoiceField(
        label="Niveau du mémoire",
        required=False,
        choices=[("", "—"), *NiveauMemoire.choices],
        help_text="Uniquement pour un mémoire.",
    )
    filiere = forms.ModelChoiceField(label="Filière", required=False, queryset=Filiere.objects)
    annee_academique = forms.ModelChoiceField(
        label="Année académique", required=False, queryset=AnneeAcademique.objects
    )
    domaine = forms.ModelChoiceField(label="Domaine", required=False, queryset=Domaine.objects)
    mots_cles = forms.ModelMultipleChoiceField(
        label="Mots-clés",
        required=False,
        queryset=MotCle.objects,
        widget=forms.CheckboxSelectMultiple,
    )
    date_soutenance = forms.DateField(
        label="Date de soutenance",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Facultative à ce stade.",
    )
    mention = forms.ChoiceField(
        label="Mention",
        required=False,
        choices=[("", "—"), *Mention.choices],
        help_text="Mémoire : Passable à Très bien. Thèse : Honorable ou Très honorable.",
    )

    def __init__(self, *args, production=None, **kwargs):
        self.production = production
        if production is not None:
            # FormView transmet toujours initial={} : on fusionne au lieu de setdefault.
            kwargs["initial"] = {**self.valeurs_initiales(production), **kwargs.get("initial", {})}
        super().__init__(*args, **kwargs)
        initial = self.initial
        self.fields["filiere"].queryset = _actifs(
            Filiere, getattr(initial.get("filiere"), "pk", None)
        )
        self.fields["annee_academique"].queryset = _actifs(
            AnneeAcademique, getattr(initial.get("annee_academique"), "pk", None)
        )
        self.fields["domaine"].queryset = _actifs(
            Domaine, getattr(initial.get("domaine"), "pk", None)
        ).select_related("parent__parent")
        self.fields["mots_cles"].queryset = _actifs(
            MotCle, actuels=[m.pk for m in initial.get("mots_cles", [])]
        )
        if production is None:
            courante = AnneeAcademique.objects.filter(courante=True).first()
            self.fields["annee_academique"].initial = courante
        else:
            # Le type ne change plus après la création (héritage multi-tables).
            self.fields["type_production"].disabled = True
            self.fields[
                "type_production"
            ].help_text = (
                "Le type ne peut plus être modifié : supprimez le brouillon pour changer de type."
            )

    @staticmethod
    def valeurs_initiales(production) -> dict:
        production = production.specifique()
        valeurs = {
            "type_production": production.type_production,
            "titre": production.titre,
            "resume": production.resume,
            "langue": production.langue,
            "filiere": production.filiere,
            "annee_academique": production.annee_academique,
            "domaine": production.domaine,
            "mots_cles": list(production.mots_cles.all()),
            "date_soutenance": production.date_soutenance,
            "mention": production.mention or "",
        }
        if isinstance(production, Memoire):
            valeurs["niveau"] = production.niveau
        return valeurs

    def clean(self):
        donnees = super().clean()
        type_production = donnees.get("type_production")
        mention = donnees.get("mention") or None
        donnees["mention"] = mention
        if type_production == TypeProduction.MEMOIRE:
            if not donnees.get("niveau"):
                self.add_error("niveau", "Indiquez le niveau du mémoire (Licence ou Master).")
            if mention and mention not in MENTIONS_MEMOIRE:
                self.add_error(
                    "mention", "Les mentions Honorable et Très honorable sont réservées aux thèses."
                )
        elif type_production == TypeProduction.THESE:
            donnees["niveau"] = ""
            if mention and mention not in MENTIONS_THESE:
                self.add_error(
                    "mention", "Une thèse reçoit la mention Honorable ou Très honorable."
                )
        return donnees

    def donnees_service(self) -> dict:
        d = dict(self.cleaned_data)
        d.pop("mots_cles", None)
        d.pop("type_production", None)
        if d.get("niveau") == "":
            d.pop("niveau")
        return d


class CoauteurForm(forms.Form):
    nom = forms.CharField(label="Nom", max_length=150)
    prenom = forms.CharField(label="Prénom", max_length=150)
    affiliation = forms.CharField(
        label="Affiliation", max_length=200, required=False, help_text="Établissement, laboratoire…"
    )
    orcid = forms.CharField(
        label="ORCID",
        max_length=19,
        required=False,
        validators=[valider_orcid],
        help_text="Facultatif, par exemple 0000-0002-1825-0097.",
    )
    email = forms.EmailField(
        label="E-mail SIGAPS",
        required=False,
        help_text="Facultatif : si le co-auteur a un compte SIGAPS, il pourra suivre le dépôt.",
    )

    def clean_orcid(self):
        return self.cleaned_data["orcid"].strip().upper() or None

    def clean_email(self):
        email = normaliser_email(self.cleaned_data["email"])
        if not email:
            return None
        utilisateur = Utilisateur.objects.filter(email__iexact=email, is_active=True).first()
        if utilisateur is None:
            raise forms.ValidationError("Aucun compte actif ne correspond à cette adresse.")
        return utilisateur

    def donnees_service(self) -> DonneesCoauteur:
        d = self.cleaned_data
        return DonneesCoauteur(
            nom=d["nom"],
            prenom=d["prenom"],
            affiliation=d["affiliation"],
            orcid=d["orcid"],
            utilisateur=d["email"],
        )


class RechercheEnseignantForm(forms.Form):
    q = forms.CharField(label="Rechercher un enseignant par nom", min_length=2, max_length=100)


class AjoutEncadrantForm(forms.Form):
    role = forms.ChoiceField(choices=RoleEncadrement.choices)


class FichierForm(forms.Form):
    fichier = forms.FileField(
        label="Document PDF",
        validators=[valider_pdf],
        help_text="PDF uniquement, 50 Mo au maximum.",
        widget=forms.FileInput(
            attrs={"accept": ".pdf,application/pdf", "data-taille-max": TAILLE_MAX_PDF}
        ),
    )


class AvisForm(forms.Form):
    avis = forms.ChoiceField(label="Votre avis", choices=Avis.choices, widget=forms.RadioSelect)
    commentaire = forms.CharField(
        label="Commentaire",
        required=False,
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="Obligatoire pour demander des corrections ou rejeter : précisez ce qui doit "
        "être revu.",
    )

    def clean(self):
        donnees = super().clean()
        avis = donnees.get("avis")
        commentaire = (donnees.get("commentaire") or "").strip()
        donnees["commentaire"] = commentaire
        if avis and avis != Avis.FAVORABLE and not commentaire:
            self.add_error(
                "commentaire", "Un motif est obligatoire pour demander des corrections ou rejeter."
            )
        return donnees


class VersionCorrigeeForm(forms.Form):
    fichier = forms.FileField(
        label="PDF corrigé",
        validators=[valider_pdf],
        help_text="PDF uniquement, 50 Mo au maximum. Il deviendra la nouvelle version.",
        widget=forms.FileInput(
            attrs={"accept": ".pdf,application/pdf", "data-taille-max": TAILLE_MAX_PDF}
        ),
    )
    note = forms.CharField(
        label="Ce que vous avez corrigé",
        required=False,
        max_length=5000,
        widget=forms.Textarea(attrs={"rows": 5}),
        help_text="Facultatif, mais utile à votre encadreur.",
    )

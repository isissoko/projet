from django import forms
from django.db.models import Q

from .models import AnneeAcademique, Departement, Domaine, Etablissement, Filiere, MotCle


class ReferentielForm(forms.ModelForm):
    """Ne propose que les éléments actifs dans les listes, plus la valeur actuelle."""

    champs_actifs: tuple[str, ...] = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nom in self.champs_actifs:
            champ = self.fields[nom]
            actuel = getattr(self.instance, f"{nom}_id", None)
            champ.queryset = champ.queryset.filter(Q(actif=True) | Q(pk=actuel))


class EtablissementForm(ReferentielForm):
    class Meta:
        model = Etablissement
        fields = ["code", "nom", "sigle"]


class DepartementForm(ReferentielForm):
    champs_actifs = ("etablissement",)

    class Meta:
        model = Departement
        fields = ["etablissement", "code", "nom"]


class FiliereForm(ReferentielForm):
    champs_actifs = ("departement",)

    class Meta:
        model = Filiere
        fields = ["departement", "code", "libelle"]


class AnneeAcademiqueForm(ReferentielForm):
    class Meta:
        model = AnneeAcademique
        fields = ["libelle", "date_debut", "date_fin", "courante"]
        widgets = {
            "date_debut": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "date_fin": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
        help_texts = {"courante": "Remplace l'année courante actuelle."}

    def _get_validation_exclusions(self):
        # Cocher « année courante » bascule l'ancienne année (service definir_annee_courante) :
        # la contrainte d'unicité ne doit donc pas bloquer le formulaire.
        return super()._get_validation_exclusions() | {"courante"}


class DomaineForm(ReferentielForm):
    champs_actifs = ("parent",)

    class Meta:
        model = Domaine
        fields = ["code", "libelle", "parent"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["parent"].queryset = self.fields["parent"].queryset.exclude(
                pk=self.instance.pk
            )


class MotCleForm(ReferentielForm):
    class Meta:
        model = MotCle
        fields = ["libelle"]

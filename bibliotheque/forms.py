"""Formulaires de la bibliothèque. Les règles sont revérifiées par les services."""

from django import forms

from productions.acces import aujourd_hui
from productions.forms import MetadonneesForm
from productions.models import NiveauAcces


class AccesForm(forms.Form):
    """Niveau d'accès et embargo, à l'archivage ou après (BF08)."""

    niveau_acces = forms.ChoiceField(
        label="Niveau d'accès", choices=NiveauAcces.choices, widget=forms.RadioSelect
    )
    date_fin_embargo = forms.DateField(
        label="Fin d'embargo",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Facultative. Jusqu'à cette date, seuls les auteurs, les encadrants et la "
        "bibliothèque ouvrent le PDF ; l'embargo se lève ensuite tout seul.",
    )

    def __init__(self, *args, embargo_actuel=None, **kwargs):
        self.embargo_actuel = embargo_actuel
        super().__init__(*args, **kwargs)

    def clean_date_fin_embargo(self):
        date = self.cleaned_data["date_fin_embargo"]
        if date is not None and date != self.embargo_actuel and date <= aujourd_hui():
            raise forms.ValidationError(
                "La date de fin d'embargo doit être postérieure à aujourd'hui."
            )
        return date


class MotifForm(forms.Form):
    """Motif obligatoire (RG07) : demande de corrections ou retrait."""

    motif = forms.CharField(
        label="Motif",
        max_length=5000,
        widget=forms.Textarea(attrs={"rows": 4}),
        error_messages={"required": "Un motif est obligatoire."},
    )

    def __init__(self, *args, aide="", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["motif"].help_text = aide


class MetadonneesBibliothequeForm(MetadonneesForm):
    """Métadonnées corrigées par la bibliothèque (BF12) : le type ne change jamais."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            "date_soutenance"
        ].help_text = "Obligatoire pour archiver : son année figure dans la cote."
        self.fields["type_production"].help_text = "Le type d'un travail soumis ne change plus."

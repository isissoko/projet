"""Formulaire de recherche (GET) : une valeur invalide est ignorée, jamais bloquante."""

from django import forms

from productions.models import Statut, TypeProduction
from referentiel.models import Filiere, MotCle

from . import services


class RechercheForm(forms.Form):
    q = forms.CharField(
        label="Rechercher",
        required=False,
        max_length=200,
        help_text="Mots du titre, du résumé, des auteurs… Utilisez des guillemets pour une "
        "expression exacte et le signe moins pour exclure un mot.",
        widget=forms.TextInput(attrs={"type": "search", "placeholder": "ex. irrigation Niger"}),
    )
    titre = forms.CharField(label="Titre", required=False, max_length=200)
    auteur = forms.CharField(label="Auteur", required=False, max_length=100)
    encadreur = forms.CharField(label="Encadreur", required=False, max_length=100)
    annee = forms.TypedChoiceField(
        label="Année de soutenance", required=False, coerce=int, empty_value=None
    )
    mot_cle = forms.ModelChoiceField(
        label="Mot-clé", required=False, queryset=MotCle.objects.none(), empty_label="Tous"
    )
    type = forms.ChoiceField(
        label="Type", required=False, choices=[("", "Tous"), *TypeProduction.choices]
    )
    filiere = forms.ModelChoiceField(
        label="Filière", required=False, queryset=Filiere.objects.none(), empty_label="Toutes"
    )
    tri = forms.ChoiceField(label="Trier par", required=False, choices=list(services.TRIS.items()))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        archives = {"productions__statut": Statut.ARCHIVE}
        self.fields["annee"].choices = [("", "Toutes")] + [
            (a, a) for a in services.annees_disponibles()
        ]
        self.fields["mot_cle"].queryset = (
            MotCle.objects.filter(**archives).distinct().order_by("libelle")
        )
        self.fields["filiere"].queryset = (
            Filiere.objects.filter(**archives).distinct().order_by("libelle")
        )

    def criteres(self) -> services.Criteres:
        """Critères valides ; les champs en erreur sont simplement ignorés."""
        self.is_valid()
        d = self.cleaned_data
        return services.Criteres(
            texte=(d.get("q") or "").strip(),
            titre=(d.get("titre") or "").strip(),
            auteur=(d.get("auteur") or "").strip(),
            encadreur=(d.get("encadreur") or "").strip(),
            annee=d.get("annee"),
            mot_cle=d.get("mot_cle"),
            filiere=d.get("filiere"),
            type_production=d.get("type") or "",
            tri=d.get("tri") or "pertinence",
        )

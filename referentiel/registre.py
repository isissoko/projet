"""Description des six éléments du référentiel, utilisée par les vues génériques."""

from dataclasses import dataclass, field

from django.http import Http404

from . import forms, models


@dataclass(frozen=True)
class TypeElement:
    slug: str
    modele: type
    formulaire: type
    titre: str
    libelle_nouveau: str  # « Nouvelle filière »
    colonnes: list[tuple[str, str]]  # (en-tête, attribut)
    recherche: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)

    @property
    def nom(self) -> str:
        return self.modele._meta.verbose_name

    def queryset(self):
        return self.modele.objects.select_related(*self.relations)


TYPES = {
    t.slug: t
    for t in [
        TypeElement(
            "etablissements",
            models.Etablissement,
            forms.EtablissementForm,
            "Établissements",
            "Nouvel établissement",
            [("Code", "code"), ("Nom", "nom"), ("Sigle", "sigle")],
            ["code", "nom", "sigle"],
        ),
        TypeElement(
            "departements",
            models.Departement,
            forms.DepartementForm,
            "Départements",
            "Nouveau département",
            [("Code", "code"), ("Nom", "nom"), ("Établissement", "etablissement")],
            ["code", "nom"],
            ["etablissement"],
        ),
        TypeElement(
            "filieres",
            models.Filiere,
            forms.FiliereForm,
            "Filières",
            "Nouvelle filière",
            [("Code", "code"), ("Libellé", "libelle"), ("Département", "departement")],
            ["code", "libelle"],
            ["departement"],
        ),
        TypeElement(
            "annees",
            models.AnneeAcademique,
            forms.AnneeAcademiqueForm,
            "Années académiques",
            "Nouvelle année académique",
            [
                ("Libellé", "libelle"),
                ("Début", "date_debut"),
                ("Fin", "date_fin"),
                ("Courante", "courante"),
            ],
            ["libelle"],
        ),
        TypeElement(
            "domaines",
            models.Domaine,
            forms.DomaineForm,
            "Domaines",
            "Nouveau domaine",
            [("Code", "code"), ("Domaine", "chemin")],
            ["code", "libelle"],
            ["parent__parent__parent"],
        ),
        TypeElement(
            "mots-cles",
            models.MotCle,
            forms.MotCleForm,
            "Mots-clés",
            "Nouveau mot-clé",
            [("Libellé", "libelle")],
            ["libelle"],
        ),
    ]
}


def type_element(slug: str) -> TypeElement:
    try:
        return TYPES[slug]
    except KeyError:
        raise Http404("Type d'élément inconnu.") from None

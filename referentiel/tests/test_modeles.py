import datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from referentiel.models import AnneeAcademique, MotCle

from .factories import (
    AnneeAcademiqueFactory,
    DepartementFactory,
    DomaineFactory,
    EtablissementFactory,
    FiliereFactory,
    MotCleFactory,
)

pytestmark = pytest.mark.django_db


def test_une_seule_annee_courante_en_base():
    AnneeAcademiqueFactory(courante=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        AnneeAcademiqueFactory(courante=True)


def test_plusieurs_annees_non_courantes_autorisees():
    AnneeAcademiqueFactory()
    AnneeAcademiqueFactory()
    assert AnneeAcademique.objects.filter(courante=False).count() == 2


def test_dates_incoherentes_refusees_en_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        AnneeAcademiqueFactory(
            date_debut=datetime.date(2026, 10, 1), date_fin=datetime.date(2026, 9, 1)
        )


@pytest.mark.parametrize("libelle", ["2025", "2025-2027", "25-26", "2025/2026"])
def test_libelle_annee_invalide(libelle):
    annee = AnneeAcademiqueFactory.build(libelle=libelle)
    with pytest.raises(ValidationError) as erreur:
        annee.full_clean()
    assert "libelle" in erreur.value.message_dict


def test_mot_cle_unique_insensible_a_la_casse_en_base():
    MotCleFactory(libelle="Agriculture")
    with pytest.raises(IntegrityError), transaction.atomic():
        MotCleFactory(libelle="AGRICULTURE")


def test_mot_cle_doublon_detecte_par_la_validation():
    MotCleFactory(libelle="Énergie solaire")
    doublon = MotCle(libelle="  énergie   SOLAIRE ")
    with pytest.raises(ValidationError):
        doublon.full_clean()


def test_mot_cle_espaces_normalises():
    assert MotCleFactory(libelle="  santé   publique ").libelle == "santé publique"


def test_codes_normalises_en_majuscules():
    assert FiliereFactory(code=" info-l3 ").code == "INFO-L3"
    assert EtablissementFactory(code="usttb").code == "USTTB"


def test_code_filiere_unique():
    FiliereFactory(code="GEO")
    with pytest.raises(IntegrityError), transaction.atomic():
        FiliereFactory(code="geo")


def test_code_departement_unique_par_etablissement():
    etab = EtablissementFactory()
    DepartementFactory(etablissement=etab, code="MATH")
    DepartementFactory(code="MATH")  # autre établissement : autorisé
    with pytest.raises(IntegrityError), transaction.atomic():
        DepartementFactory(etablissement=etab, code="MATH")


def test_domaine_hierarchique_et_chemin():
    sciences = DomaineFactory(libelle="Sciences")
    info = DomaineFactory(libelle="Informatique", parent=sciences)
    ia = DomaineFactory(libelle="Intelligence artificielle", parent=info)
    assert str(ia) == "Sciences › Informatique › Intelligence artificielle"
    assert list(sciences.enfants.all()) == [info]


def test_domaine_cycle_refuse():
    a = DomaineFactory()
    b = DomaineFactory(parent=a)
    c = DomaineFactory(parent=b)
    a.parent = c
    with pytest.raises(ValidationError) as erreur:
        a.full_clean()
    assert "parent" in erreur.value.message_dict


def test_domaine_ne_peut_pas_etre_son_propre_parent_en_base():
    a = DomaineFactory()
    a.parent_id = a.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        a.save()


def test_representations_texte():
    assert str(EtablissementFactory(nom="Université de Ségou", sigle="")) == "Université de Ségou"
    assert str(EtablissementFactory(sigle="USJPB")) == "USJPB"
    assert str(DepartementFactory(nom="Géographie")) == "Géographie"
    assert str(FiliereFactory(libelle="Sociologie")) == "Sociologie"
    assert str(AnneeAcademiqueFactory(debut=2030)) == "2030-2031"

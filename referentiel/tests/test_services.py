import pytest

from comptes.exceptions import ActionInterdite
from comptes.tests.factories import ProfilEnseignantFactory, ProfilEtudiantFactory
from referentiel import services
from referentiel.forms import AnneeAcademiqueForm
from referentiel.models import AnneeAcademique, Filiere, MotCle

from .factories import (
    AnneeAcademiqueFactory,
    DepartementFactory,
    DomaineFactory,
    FiliereFactory,
    MotCleFactory,
)

pytestmark = pytest.mark.django_db


def test_definir_annee_courante_bascule_l_ancienne():
    ancienne = AnneeAcademiqueFactory(courante=True)
    nouvelle = AnneeAcademiqueFactory()
    services.definir_annee_courante(nouvelle)
    ancienne.refresh_from_db()
    nouvelle.refresh_from_db()
    assert not ancienne.courante
    assert nouvelle.courante
    assert AnneeAcademique.objects.filter(courante=True).count() == 1


def test_annee_desactivee_ne_peut_pas_devenir_courante():
    annee = AnneeAcademiqueFactory(actif=False)
    with pytest.raises(ActionInterdite):
        services.definir_annee_courante(annee)


def test_formulaire_annee_courante_bascule_via_le_service():
    ancienne = AnneeAcademiqueFactory(courante=True)
    form = AnneeAcademiqueForm(
        data={
            "libelle": "2026-2027",
            "date_debut": "2026-10-01",
            "date_fin": "2027-07-31",
            "courante": "on",
        }
    )
    assert form.is_valid(), form.errors
    nouvelle = services.enregistrer(form)
    ancienne.refresh_from_db()
    assert nouvelle.courante and not ancienne.courante
    assert AnneeAcademique.objects.filter(courante=True).count() == 1


def test_suppression_element_non_utilise():
    mot = MotCleFactory()
    assert services.supprimer_ou_desactiver(mot) == services.SUPPRIME
    assert not MotCle.objects.filter(pk=mot.pk).exists()


def test_desactivation_filiere_utilisee_par_un_etudiant():
    profil = ProfilEtudiantFactory()
    filiere = profil.filiere
    assert services.supprimer_ou_desactiver(filiere) == services.DESACTIVE
    filiere.refresh_from_db()
    assert not filiere.actif
    assert Filiere.objects.filter(pk=filiere.pk).exists()


def test_desactivation_departement_utilise_par_un_enseignant():
    departement = ProfilEnseignantFactory().departement
    assert services.supprimer_ou_desactiver(departement) == services.DESACTIVE


def test_desactivation_departement_qui_a_des_filieres():
    departement = DepartementFactory()
    FiliereFactory(departement=departement)
    assert services.est_utilise(departement)
    assert services.supprimer_ou_desactiver(departement) == services.DESACTIVE


def test_desactivation_domaine_parent():
    parent = DomaineFactory()
    DomaineFactory(parent=parent)
    assert services.supprimer_ou_desactiver(parent) == services.DESACTIVE


def test_annee_courante_ni_supprimee_ni_desactivee():
    annee = AnneeAcademiqueFactory(courante=True)
    with pytest.raises(ActionInterdite):
        services.supprimer_ou_desactiver(annee)


def test_reactiver():
    filiere = FiliereFactory(actif=False)
    services.reactiver(filiere)
    filiere.refresh_from_db()
    assert filiere.actif

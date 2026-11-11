import pytest
from django.contrib.auth.models import AnonymousUser

from comptes.tests.factories import UtilisateurFactory
from productions import acces, services
from productions.models import Statut

from .factories import depot_complet, forcer_statut

pytestmark = pytest.mark.django_db

STATUTS_NON_ARCHIVES = [s for s in Statut.values if s != Statut.ARCHIVE]


@pytest.fixture
def depot():
    production, etudiant, directeur = depot_complet()
    return production, etudiant, directeur.utilisateur


def _au_statut(production, statut):
    return forcer_statut(production, statut)


@pytest.mark.parametrize("statut", STATUTS_NON_ARCHIVES)
def test_production_non_archivee_visible_par_les_proches(depot, statut):
    production, etudiant, directeur = depot
    production = _au_statut(production, statut)
    coauteur = UtilisateurFactory(roles=["ETUDIANT"])
    services.contributeur_pour_utilisateur(coauteur)
    production.contributions.create(contributeur=coauteur.contributeur, rang=2, role="CO_AUTEUR")
    autorises = [
        etudiant,
        coauteur,
        directeur,
        UtilisateurFactory(roles=["BIBLIOTHECAIRE"]),
        UtilisateurFactory(roles=["ADMINISTRATEUR"]),
    ]
    for utilisateur in autorises:
        assert acces.peut_voir_fiche(utilisateur, production), utilisateur


@pytest.mark.parametrize("statut", STATUTS_NON_ARCHIVES)
def test_production_non_archivee_invisible_pour_les_tiers(depot, statut):
    production, _, _ = depot
    production = _au_statut(production, statut)
    tiers = [
        AnonymousUser(),
        UtilisateurFactory(roles=["ETUDIANT"]),
        UtilisateurFactory(roles=["ENSEIGNANT"]),  # enseignant qui n'encadre pas ce travail
        UtilisateurFactory(roles=["BIBLIOTHECAIRE"], is_active=False),
    ]
    for utilisateur in tiers:
        assert not acces.peut_voir_fiche(utilisateur, production), utilisateur
        assert not acces.productions_visibles(utilisateur).filter(pk=production.pk).exists()


def test_production_archivee_visible_par_tous(depot):
    production, _, _ = depot
    production = _au_statut(production, Statut.ARCHIVE)
    assert acces.peut_voir_fiche(AnonymousUser(), production)
    assert acces.productions_visibles(AnonymousUser()).filter(pk=production.pk).exists()


def test_modification_du_brouillon_reservee_a_l_auteur_principal(depot):
    production, etudiant, directeur = depot
    assert acces.peut_modifier_brouillon(etudiant, production)
    assert not acces.peut_modifier_brouillon(directeur, production)
    assert not acces.peut_modifier_brouillon(
        UtilisateurFactory(roles=["ADMINISTRATEUR"]), production
    )
    production = _au_statut(production, Statut.SOUMIS)
    assert not acces.peut_modifier_brouillon(etudiant, production)


def test_mes_depots_et_productions_visibles(depot):
    production, etudiant, directeur = depot
    autre, _, _ = depot_complet()

    def pks(queryset):
        return set(queryset.values_list("pk", flat=True))

    assert pks(acces.mes_depots(etudiant)) == {production.pk}
    assert pks(acces.mes_depots(AnonymousUser())) == set()
    assert pks(acces.productions_visibles(directeur)) == {production.pk}
    personnel = UtilisateurFactory(roles=["BIBLIOTHECAIRE"])
    assert pks(acces.productions_visibles(personnel)) == {production.pk, autre.pk}

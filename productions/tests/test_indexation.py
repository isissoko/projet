"""Indexation plein texte : configuration french_sans_accents, pondération, mise à jour."""

import re
from io import StringIO

import pytest
from django.contrib.postgres.search import SearchQuery
from django.core.management import call_command

from productions import indexation, services
from productions.models import Production
from referentiel.tests.factories import MotCleFactory

from .factories import bibliothecaire, depot_archive, depot_complet, depot_valide

pytestmark = pytest.mark.django_db


def _trouve(production, texte) -> bool:
    requete = SearchQuery(texte, search_type="websearch", config=indexation.CONFIG_RECHERCHE)
    return Production.objects.filter(pk=production.pk, vecteur_recherche=requete).exists()


def test_archiver_indexe_le_travail():
    production, _, _ = depot_archive(titre="Gestion des barrages hydroélectriques")
    assert _trouve(production, "barrage")  # racinisation française
    assert _trouve(production, "hydroelectrique")  # sans accent
    assert _trouve(production, "HYDROÉLECTRIQUES")
    assert not _trouve(production, "agriculture")


def test_un_brouillon_n_est_pas_indexe():
    production, _, _ = depot_complet()
    production.refresh_from_db()
    assert production.vecteur_recherche is None


def test_personnes_mots_cles_et_resume_sont_indexes():
    production, etudiant, directeur = depot_archive(resume="Étude de l'irrigation goutte à goutte.")
    production.mots_cles.add(MotCleFactory(libelle="Pluviométrie"))
    indexation.indexer(production)
    assert _trouve(production, etudiant.last_name)
    assert _trouve(production, directeur.utilisateur.last_name)
    assert _trouve(production, "irrigations")
    assert _trouve(production, "pluviometrie")
    assert _trouve(production, production.filiere.libelle)


def test_poids():
    production, _, _ = depot_archive(titre="Le mil", resume="Le sorgho")
    textes = indexation.textes_ponderes(production)
    assert "Le mil" in textes["A"] and production.cote in textes["A"]
    assert textes["C"] == "Le sorgho"
    vecteur = str(Production.objects.get(pk=production.pk).vecteur_recherche)
    assert re.search(r"'mil':\d+A", vecteur)
    assert re.search(r"'sorgho':\d+C", vecteur)


def test_modification_des_metadonnees_reindexe():
    production, _, _ = depot_archive(titre="Ancien titre")
    services.modifier_metadonnees(bibliothecaire(), production, {"titre": "Riziculture irriguée"})
    assert _trouve(production, "riziculture")
    assert not _trouve(production, "ancien")


def test_commande_reindexer():
    production, _, _ = depot_archive(titre="Élevage transhumant")
    autre, _, _ = depot_valide(titre="Élevage sédentaire")
    Production.objects.update(vecteur_recherche=None)
    sortie = StringIO()
    call_command("reindexer_recherche", "--archives-seulement", stdout=sortie)
    assert "1 production(s) réindexée(s)." in sortie.getvalue()
    assert _trouve(production, "elevage")
    assert not _trouve(autre, "elevage")
    call_command("reindexer_recherche", stdout=sortie)
    assert _trouve(autre, "sedentaire")

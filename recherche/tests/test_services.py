"""Recherche multicritère (BF09) : RG10, chaque critère, combinaisons, tri, pertinence."""

import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from comptes.tests.factories import UtilisateurFactory
from productions import services as productions_services
from productions.models import Contribution, Statut, TypeProduction
from productions.tests.factories import (
    ContributeurFactory,
    TheseFactory,
    bibliothecaire,
    depot_archive,
    depot_complet,
    depot_soumis,
    depot_valide,
    forcer_statut,
)
from recherche.forms import RechercheForm
from recherche.services import Criteres, annees_disponibles, chiffres, derniers_archives, rechercher
from referentiel.tests.factories import FiliereFactory, MotCleFactory

pytestmark = pytest.mark.django_db


def _pks(criteres):
    return [p.pk for p in rechercher(criteres)]


def _archive(**attributs):
    return depot_archive(**attributs)[0]


# RG10 ----------------------------------------------------------------------------------------


def test_seuls_les_travaux_archives_sont_trouves():
    archive = _archive(titre="Irrigation au Sahel")
    for fabrique in (depot_complet, depot_soumis, depot_valide):
        fabrique(titre="Irrigation au Sahel")
    retire = _archive(titre="Irrigation au Sahel")
    productions_services.retirer(bibliothecaire(), retire, "Doublon.")
    # Un travail réindexé puis repassé à un autre statut reste exclu.
    autre = _archive(titre="Irrigation au Sahel")
    forcer_statut(autre, Statut.RETIRE)

    for criteres in [Criteres(), Criteres(texte="irrigation"), Criteres(titre="sahel")]:
        assert _pks(criteres) == [archive.pk]


# Texte libre ------------------------------------------------------------------------------------


def test_texte_libre_racinisation_et_accents():
    production = _archive(titre="Les barrages hydroélectriques du Niger")
    _archive(titre="Commerce du karité")
    assert _pks(Criteres(texte="barrage")) == [production.pk]
    assert _pks(Criteres(texte="HYDROELECTRIQUE")) == [production.pk]
    assert _pks(Criteres(texte="barrages -niger")) == []
    assert _pks(Criteres(texte='"barrages hydroélectriques"')) == [production.pk]
    assert _pks(Criteres(texte="introuvable")) == []


def test_pertinence_titre_avant_resume():
    dans_le_resume = _archive(titre="Économie rurale", resume="Le coton reste central.")
    dans_le_titre = _archive(titre="La filière coton", resume="Étude économique.")
    assert _pks(Criteres(texte="coton")) == [dans_le_titre.pk, dans_le_resume.pk]
    resultat = list(rechercher(Criteres(texte="coton")))
    assert resultat[0].pertinence > resultat[1].pertinence


def test_syntaxe_invalide_sans_erreur():
    _archive(titre="Coton")
    for texte in ['"', "-", "&|!", "((", "':*"]:
        list(rechercher(Criteres(texte=texte)))  # aucune exception


# Critères -------------------------------------------------------------------------------------


def test_critere_titre():
    production = _archive(titre="Paludisme chez l'enfant", resume="Rien sur le mil.")
    _archive(titre="Culture du mil", resume="Paludisme évoqué.")
    assert _pks(Criteres(titre="paludisme")) == [production.pk]


def test_critere_auteur_sans_accents_et_plusieurs_mots():
    etudiant = UtilisateurFactory(roles=["ETUDIANT"], first_name="Aïssata", last_name="Traoré")
    production = _archive(etudiant=etudiant)
    _archive()
    assert _pks(Criteres(auteur="traore")) == [production.pk]
    assert _pks(Criteres(auteur="Aissata TRAORÉ")) == [production.pk]
    assert _pks(Criteres(auteur="aissata keita")) == []


def test_critere_co_auteur_externe():
    production, _, _ = depot_valide()
    Contribution.objects.create(
        production=production,
        contributeur=ContributeurFactory(nom="Diarra", prenom="Sékou"),
        rang=2,
        role="CO_AUTEUR",
    )
    productions_services.archiver(bibliothecaire(), production, "LIBRE")
    assert _pks(Criteres(auteur="sekou diarra")) == [production.pk]


def test_critere_encadreur():
    production, _, directeur = depot_archive()
    _archive()
    nom = directeur.utilisateur.last_name
    assert _pks(Criteres(encadreur=nom)) == [production.pk]


def test_critere_annee_de_soutenance():
    production = _archive(date_soutenance=datetime.date(2024, 7, 2))
    _archive(date_soutenance=datetime.date(2025, 7, 2))
    assert _pks(Criteres(annee=2024)) == [production.pk]
    assert annees_disponibles() == [2025, 2024]


def test_critere_mot_cle_filiere_et_type():
    mot = MotCleFactory(libelle="Hydrologie")
    filiere = FiliereFactory()
    memoire = _archive(filiere=filiere)
    memoire.mots_cles.add(mot)
    these = _archive(factory_classe=TheseFactory)
    these.mots_cles.add(mot)
    assert set(_pks(Criteres(mot_cle=mot))) == {memoire.pk, these.pk}
    assert _pks(Criteres(filiere=filiere)) == [memoire.pk]
    assert _pks(Criteres(type_production=TypeProduction.THESE)) == [these.pk]
    assert _pks(Criteres(mot_cle=mot, type_production=TypeProduction.MEMOIRE)) == [memoire.pk]


def test_criteres_combines():
    etudiant = UtilisateurFactory(roles=["ETUDIANT"], last_name="Konaté")
    cible = _archive(
        etudiant=etudiant, titre="Irrigation du riz", date_soutenance=datetime.date(2026, 6, 1)
    )
    _archive(titre="Irrigation du riz", date_soutenance=datetime.date(2026, 6, 1))
    _archive(etudiant=UtilisateurFactory(roles=["ETUDIANT"], last_name="Konaté"), titre="Mil")
    criteres = Criteres(texte="riz", auteur="konate", annee=2026)
    assert _pks(criteres) == [cible.pk]


# Tri et performances ---------------------------------------------------------------------------


def test_tris():
    a = _archive(titre="Bêta", date_soutenance=datetime.date(2020, 1, 1))
    b = _archive(titre="Alpha", date_soutenance=datetime.date(2026, 1, 1))
    assert _pks(Criteres(tri="titre")) == [b.pk, a.pk]
    assert _pks(Criteres(tri="recent")) == [b.pk, a.pk]
    assert _pks(Criteres(tri="pertinence")) == [b.pk, a.pk]  # sans texte : les plus récents


def test_nombre_de_requetes_borne():
    for _ in range(5):
        _archive()
    with CaptureQueriesContext(connection) as requetes:
        resultats = list(rechercher(Criteres()))
        for p in resultats:
            _ = [c.contributeur.nom for c in p.auteurs_ordonnes], p.filiere, p.annee_academique
    assert len(resultats) == 5
    assert len(requetes) == 2  # les productions, puis leurs auteurs


# Accueil -------------------------------------------------------------------------------------


def test_chiffres_et_derniers_archives():
    _archive()
    deuxieme = _archive()
    these = _archive(factory_classe=TheseFactory)
    depot_valide()
    assert chiffres() == {"total": 3, "memoires": 2, "theses": 1, "filieres": 3}
    assert [p.pk for p in derniers_archives(2)] == [these.pk, deuxieme.pk]


# Formulaire -----------------------------------------------------------------------------------


def test_formulaire_ignore_les_valeurs_invalides():
    _archive(date_soutenance=datetime.date(2026, 1, 1))
    form = RechercheForm({"q": " irrigation ", "annee": "1850", "mot_cle": "999999", "type": "X"})
    criteres = form.criteres()
    assert criteres.texte == "irrigation"
    assert criteres.annee is None and criteres.mot_cle is None
    assert criteres.type_production == ""
    assert criteres.tri == "pertinence"


def test_formulaire_propose_les_valeurs_utiles():
    mot = MotCleFactory(libelle="Utilisé")
    inutilise = MotCleFactory(libelle="Jamais utilisé")
    production = _archive(date_soutenance=datetime.date(2023, 5, 5))
    production.mots_cles.add(mot)
    depot_valide()[0].mots_cles.add(inutilise)  # utilisé seulement par un travail non archivé
    form = RechercheForm({"annee": "2023", "mot_cle": str(mot.pk)})
    proposes = list(form.fields["mot_cle"].queryset)
    assert mot in proposes and inutilise not in proposes
    assert form.criteres().annee == 2023
    assert form.criteres().mot_cle == mot

"""Matrice d'accès complète : rôle × niveau d'accès × embargo × statut (CLAUDE.md).

Les résultats attendus sont écrits ici en clair, indépendamment de productions/acces.py.
"""

import datetime

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from comptes.tests.factories import UtilisateurFactory
from productions import acces, services
from productions.models import NiveauAcces, Statut

from .factories import (
    ContributeurFactory,
    ajouter_codirecteur,
    bibliothecaire,
    depot_archive,
    depot_complet,
    depot_valide,
    forcer_statut,
)
from .fichiers import pdf_valide

pytestmark = pytest.mark.django_db

# Profils --------------------------------------------------------------------------------

PROCHES = {
    "auteur",
    "coauteur",
    "directeur",
    "codirecteur",
    "bibliothecaire",
    "administrateur",
    "bibliothecaire_et_etudiant",  # le rôle bibliothécaire suffit
}
CONNECTES = PROCHES | {"etudiant_tiers", "enseignant_tiers"}
# Un compte désactivé est traité comme un visiteur, même s'il était co-auteur.
TOUS = CONNECTES | {"visiteur", "ancien_auteur_desactive"}

# Embargo : décalage en jours par rapport à aujourd'hui (None = pas d'embargo).
EMBARGOS = {"aucun": None, "actif": 30, "leve_aujourd_hui": 0, "expire": -1}

# Téléchargement d'un travail ARCHIVE, version archivée.
TELECHARGEMENT_ARCHIVE = {
    (NiveauAcces.LIBRE, "aucun"): TOUS,
    (NiveauAcces.LIBRE, "actif"): PROCHES,
    (NiveauAcces.LIBRE, "leve_aujourd_hui"): TOUS,
    (NiveauAcces.LIBRE, "expire"): TOUS,
    (NiveauAcces.RESTREINT, "aucun"): CONNECTES,
    (NiveauAcces.RESTREINT, "actif"): PROCHES,
    (NiveauAcces.RESTREINT, "leve_aujourd_hui"): CONNECTES,
    (NiveauAcces.RESTREINT, "expire"): CONNECTES,
    (NiveauAcces.CONFIDENTIEL, "aucun"): PROCHES,
    (NiveauAcces.CONFIDENTIEL, "actif"): PROCHES,
    (NiveauAcces.CONFIDENTIEL, "leve_aujourd_hui"): PROCHES,
    (NiveauAcces.CONFIDENTIEL, "expire"): PROCHES,
}


@pytest.fixture
def scenario():
    """Un travail complet et un utilisateur par profil."""
    etudiant_biblio = UtilisateurFactory(roles=["ETUDIANT", "BIBLIOTHECAIRE"])
    production, auteur, directeur = depot_complet()
    coauteur = UtilisateurFactory(roles=["ETUDIANT"])
    services.ajouter_coauteur(
        auteur,
        production,
        services.DonneesCoauteur(nom="Coulibaly", prenom="Awa", utilisateur=coauteur),
    )
    codirecteur = ajouter_codirecteur(production)
    ancien = UtilisateurFactory(roles=["ETUDIANT"])
    services.ajouter_coauteur(
        auteur, production, services.DonneesCoauteur(nom="X", prenom="Y", utilisateur=ancien)
    )
    ancien.is_active = False
    ancien.save()
    ContributeurFactory()  # co-auteur externe sans compte : sans effet
    profils = {
        "visiteur": AnonymousUser(),
        "etudiant_tiers": UtilisateurFactory(roles=["ETUDIANT"]),
        "enseignant_tiers": UtilisateurFactory(roles=["ENSEIGNANT"]),
        "ancien_auteur_desactive": ancien,
        "auteur": auteur,
        "coauteur": coauteur,
        "directeur": directeur.utilisateur,
        "codirecteur": codirecteur.utilisateur,
        "bibliothecaire": UtilisateurFactory(roles=["BIBLIOTHECAIRE"]),
        "administrateur": UtilisateurFactory(roles=["ADMINISTRATEUR"]),
        "bibliothecaire_et_etudiant": etudiant_biblio,
    }
    assert set(profils) == TOUS
    return production, profils


def _configurer(production, niveau, embargo):
    """Niveau et embargo posés en mémoire : les règles d'accès lisent l'instance."""
    decalage = EMBARGOS[embargo]
    production.niveau_acces = niveau
    production.date_fin_embargo = (
        None if decalage is None else timezone.localdate() + datetime.timedelta(days=decalage)
    )
    return production


@pytest.mark.parametrize("statut", Statut.values)
def test_matrice_complete(scenario, statut):
    production, profils = scenario
    production = forcer_statut(production, statut)
    for niveau in NiveauAcces.values:
        for embargo in EMBARGOS:
            _configurer(production, niveau, embargo)
            if statut == Statut.ARCHIVE:
                fiche_attendue = TOUS
                pdf_attendu = TELECHARGEMENT_ARCHIVE[(niveau, embargo)]
            else:
                fiche_attendue = pdf_attendu = PROCHES
            for nom, utilisateur in profils.items():
                cas = f"{statut} / {niveau} / embargo {embargo} / {nom}"
                assert acces.peut_voir_fiche(utilisateur, production) == (nom in fiche_attendue), (
                    f"fiche : {cas}"
                )
                assert acces.peut_telecharger(utilisateur, production) == (nom in pdf_attendu), (
                    f"PDF : {cas}"
                )
                assert (acces.raison_indisponibilite(utilisateur, production) is None) == (
                    nom in pdf_attendu
                ), f"raison : {cas}"


@pytest.mark.parametrize("statut", Statut.values)
def test_productions_visibles_coherent_avec_peut_voir_fiche(scenario, statut):
    production, profils = scenario
    production = forcer_statut(production, statut)
    for nom, utilisateur in profils.items():
        visible = acces.productions_visibles(utilisateur).filter(pk=production.pk).exists()
        assert visible == acces.peut_voir_fiche(utilisateur, production), nom


# Embargo -------------------------------------------------------------------------------


def test_embargo_se_leve_tout_seul(monkeypatch):
    fin = timezone.localdate() + datetime.timedelta(days=10)
    production, _, _ = depot_archive(niveau_acces=NiveauAcces.LIBRE, date_fin_embargo=fin)
    visiteur = AnonymousUser()
    assert not acces.peut_telecharger(visiteur, production)
    assert "embargo jusqu'au" in acces.raison_indisponibilite(visiteur, production)

    monkeypatch.setattr(acces, "aujourd_hui", lambda: fin - datetime.timedelta(days=1))
    assert not acces.peut_telecharger(visiteur, production)
    monkeypatch.setattr(acces, "aujourd_hui", lambda: fin)
    assert acces.peut_telecharger(visiteur, production)  # aucune action nécessaire
    monkeypatch.setattr(acces, "aujourd_hui", lambda: fin + datetime.timedelta(days=365))
    assert acces.peut_telecharger(visiteur, production)


def test_date_d_embargo_affichee_en_francais():
    fin = datetime.date(2099, 10, 25)
    production, _, _ = depot_archive(date_fin_embargo=fin)
    assert acces.raison_indisponibilite(AnonymousUser(), production) == (
        "Le document est sous embargo jusqu'au 25 octobre 2099."
    )


# Versions antérieures (décision Q4) -------------------------------------------------------


def _archive_en_deux_versions():
    production, etudiant, directeur = depot_valide()
    biblio = bibliothecaire()
    services.demander_corrections_bibliotheque(biblio, production, "Page de garde.")
    services.soumettre_version_corrigee(etudiant, production, pdf_valide("v2.pdf"))
    services.archiver(biblio, production, NiveauAcces.LIBRE)
    production.refresh_from_db()
    return production, etudiant, directeur


def test_le_public_n_accede_qu_a_la_version_archivee():
    production, etudiant, _ = _archive_en_deux_versions()
    v1, v2 = production.versions.order_by("numero")
    visiteur = AnonymousUser()
    assert acces.peut_telecharger(visiteur, production, v2)
    assert not acces.peut_telecharger(visiteur, production, v1)
    assert acces.peut_telecharger(etudiant, production, v1)
    assert list(acces.versions_consultables(visiteur, production)) == [v2]
    assert list(acces.versions_consultables(etudiant, production)) == [v2, v1]


def test_version_d_une_autre_production_refusee():
    production, _, _ = depot_archive()
    autre, _, _ = depot_archive()
    assert not acces.peut_telecharger(AnonymousUser(), production, autre.version_courante())


# Listes de la bibliothèque --------------------------------------------------------------------


def test_listes_de_la_bibliotheque_reservees():
    valide, _, _ = depot_valide()
    archive, _, _ = depot_archive()
    biblio = bibliothecaire()
    assert list(acces.productions_a_controler(biblio).values_list("pk", flat=True)) == [valide.pk]
    assert acces.nombre_a_controler(biblio) == 1
    assert list(acces.catalogue(biblio).values_list("pk", flat=True)) == [archive.pk]
    for autre in [AnonymousUser(), UtilisateurFactory(roles=["ADMINISTRATEUR"])]:
        assert not acces.productions_a_controler(autre).exists()
        assert not acces.catalogue(autre).exists()
        assert acces.nombre_a_controler(autre) == 0

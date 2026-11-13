"""Pages publiques : accueil, résultats, fiche (BF09, BF10, RG01, RG10, RG11)."""

import datetime
from html import escape

import pytest
from django.urls import reverse

from comptes.tests.factories import UtilisateurFactory
from productions import services
from productions.models import NiveauAcces
from productions.tests.factories import (
    TheseFactory,
    bibliothecaire,
    depot_archive,
    depot_soumis,
    depot_valide,
)
from productions.tests.fichiers import pdf_valide
from recherche.services import citation

pytestmark = pytest.mark.django_db

RESULTATS = reverse("recherche:resultats")


def _fiche(production):
    return reverse("recherche:fiche", args=[production.pk])


# Accueil --------------------------------------------------------------------------------------


def test_accueil_vide(client):
    contenu = client.get(reverse("accueil")).content.decode()
    assert "Aucun travail archivé pour l" in contenu
    assert 'role="search"' in contenu


def test_accueil_chiffres_et_derniers_archives(client):
    production, _, _ = depot_archive(titre="Pêche artisanale à Mopti")
    depot_archive(factory_classe=TheseFactory)
    depot_valide(titre="Travail non archivé")
    contenu = client.get(reverse("accueil")).content.decode()
    assert "Pêche artisanale à Mopti" in contenu
    assert _fiche(production) in contenu
    assert "Travail non archivé" not in contenu
    assert "Travaux archivés</dt>" in contenu
    assert f'href="{RESULTATS}"' in contenu  # entrée « Rechercher » du menu


# Résultats -------------------------------------------------------------------------------------


def test_recherche_par_un_visiteur(client):
    production, _, _ = depot_archive(titre="Pêche artisanale à Mopti")
    depot_soumis(titre="Pêche industrielle")
    reponse = client.get(RESULTATS, {"q": "peche"})
    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert "1 résultat" in contenu
    assert _fiche(production) in contenu
    assert "industrielle" not in contenu


def test_criteres_actifs_et_retrait_d_un_critere(client):
    depot_archive(titre="Pêche", date_soutenance=datetime.date(2025, 6, 1))
    contenu = client.get(RESULTATS, {"q": "peche", "annee": "2025"}).content.decode()
    assert "Critères actifs" in contenu
    assert "Année de soutenance : 2025" in contenu
    assert 'href="?q=peche"' in contenu  # retirer l'année garde le texte
    assert '<details class="carte" open>' in contenu  # critère avancé actif : filtres ouverts


def test_valeurs_invalides_ignorees(client):
    production, _, _ = depot_archive()
    reponse = client.get(RESULTATS, {"annee": "abc", "mot_cle": "-1", "tri": "x", "page": "1"})
    assert reponse.status_code == 200
    assert _fiche(production) in reponse.content.decode()


def test_aucun_resultat(client):
    depot_archive()
    contenu = client.get(RESULTATS, {"q": "xylophone"}).content.decode()
    assert "Aucun travail ne correspond" in contenu


def test_pagination_conserve_les_criteres(client):
    for _ in range(11):
        depot_archive(titre="Hydrologie urbaine")
    contenu = client.get(RESULTATS, {"q": "hydrologie"}).content.decode()
    assert "11 résultats" in contenu
    assert 'href="?q=hydrologie&amp;page=2"' in contenu
    page2 = client.get(RESULTATS, {"q": "hydrologie", "page": "2"}).content.decode()
    assert page2.count('class="carte flex h-full') == 1


def test_nombre_de_requetes_des_resultats(client, django_assert_max_num_queries):
    for _ in range(4):
        depot_archive()
    with django_assert_max_num_queries(10):
        client.get(RESULTATS, {"q": "agriculture"})


# Fiche ----------------------------------------------------------------------------------------


def test_fiche_libre_acces_pour_un_visiteur(client):
    production, _, directeur = depot_archive(niveau_acces=NiveauAcces.LIBRE)
    contenu = client.get(_fiche(production)).content.decode()
    url_pdf = reverse("productions:telecharger", args=[production.pk, 1])
    assert escape(production.titre) in contenu
    assert f"Cote {production.cote}" in contenu
    assert "Consulter le PDF" in contenu and f"{url_pdf}?telecharger=1" in contenu
    assert str(directeur.utilisateur) in contenu
    assert "Citer ce travail" in contenu
    assert "suivi interne" not in contenu


def test_fiche_acces_restreint_pour_un_visiteur(client):
    production, _, _ = depot_archive(niveau_acces=NiveauAcces.RESTREINT)
    contenu = client.get(_fiche(production)).content.decode()
    assert "Consulter le PDF" not in contenu
    assert "réservé aux utilisateurs connectés" in contenu
    assert f"?next=/travaux/{production.pk}/" in contenu


def test_fiche_sous_embargo(connecter):
    fin = datetime.date(2099, 1, 31)
    production, _, _ = depot_archive(date_fin_embargo=fin)
    client, _ = connecter("ETUDIANT")
    contenu = client.get(_fiche(production)).content.decode()
    assert "sous embargo jusqu&#x27;au 31 janvier 2099" in contenu
    assert "Consulter le PDF" not in contenu


def test_fiche_pour_l_auteur_et_la_bibliotheque(client):
    production, etudiant, _ = depot_archive(niveau_acces=NiveauAcces.CONFIDENTIEL)
    client.force_login(etudiant)
    contenu = client.get(_fiche(production)).content.decode()
    assert "Consulter le PDF" in contenu and "suivi interne" in contenu
    assert "Gérer dans le catalogue" not in contenu
    client.force_login(bibliothecaire())
    assert "Gérer dans le catalogue" in client.get(_fiche(production)).content.decode()


def test_travail_non_archive_404_ou_redirection(client):
    production, etudiant, _ = depot_valide()
    assert client.get(_fiche(production)).status_code == 404
    client.force_login(UtilisateurFactory(roles=["ETUDIANT"]))
    assert client.get(_fiche(production)).status_code == 404
    client.force_login(etudiant)
    reponse = client.get(_fiche(production))
    assert reponse.status_code == 302
    assert reponse.url == reverse("productions:detail", args=[production.pk])


def test_travail_retire_404_pour_le_public(client):
    production, etudiant, _ = depot_archive()
    services.retirer(bibliothecaire(), production, "Doublon.")
    assert client.get(_fiche(production)).status_code == 404
    client.force_login(etudiant)
    assert client.get(_fiche(production)).status_code == 302


def test_fiche_inexistante(client):
    assert client.get(reverse("recherche:fiche", args=[999999])).status_code == 404


def test_citation():
    etudiant = UtilisateurFactory(roles=["ETUDIANT"], first_name="Awa", last_name="Diallo")
    production, _, _ = depot_archive(
        etudiant=etudiant, titre="Le mil au Sahel", date_soutenance=datetime.date(2026, 6, 15)
    )
    texte = citation(production)
    assert texte.startswith("DIALLO Awa (2026). Le mil au Sahel. Mémoire de Master, ")
    assert texte.endswith(f"Cote {production.cote}.")
    assert production.filiere.departement.etablissement.nom in texte


# Téléchargement --------------------------------------------------------------------------------


def test_telechargement_en_piece_jointe_nomme_par_la_cote(client):
    production, _, _ = depot_archive(niveau_acces=NiveauAcces.LIBRE)
    url = reverse("productions:telecharger", args=[production.pk, 1])
    reponse = client.get(url, {"telecharger": "1"})
    assert reponse.status_code == 200
    assert reponse["Content-Disposition"].startswith("attachment")
    assert f'filename="{production.cote}.pdf"' in reponse["Content-Disposition"]
    assert client.get(url)["Content-Disposition"].startswith("inline")


def test_nom_d_une_ancienne_version_archivee(client):
    production, etudiant, _ = depot_valide()
    biblio = bibliothecaire()
    services.demander_corrections_bibliotheque(biblio, production, "Page de garde.")
    services.soumettre_version_corrigee(etudiant, production, pdf_valide("v2.pdf"))
    services.archiver(biblio, production, NiveauAcces.LIBRE)
    client.force_login(etudiant)
    reponse = client.get(reverse("productions:telecharger", args=[production.pk, 1]))
    assert f'filename="{production.cote}-version-1.pdf"' in reponse["Content-Disposition"]

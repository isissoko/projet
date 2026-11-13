"""Téléchargement et fiche d'un travail archivé ou retiré, selon les droits."""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from productions import services
from productions.models import NiveauAcces

from .factories import bibliothecaire, depot_archive, depot_valide
from .fichiers import pdf_valide

pytestmark = pytest.mark.django_db

DANS_UN_MOIS = timezone.localdate() + datetime.timedelta(days=30)


def _url(production, numero=None):
    numero = numero or production.version_courante().numero
    return reverse("productions:telecharger", args=[production.pk, numero])


def _detail(production):
    return reverse("productions:detail", args=[production.pk])


def test_libre_acces_telechargeable_par_un_visiteur(client):
    production, _, _ = depot_archive(niveau_acces=NiveauAcces.LIBRE)
    reponse = client.get(_url(production))
    assert reponse.status_code == 200
    assert reponse["Content-Type"] == "application/pdf"


def test_acces_restreint_invite_le_visiteur_a_se_connecter(client, connecter):
    production, _, _ = depot_archive(niveau_acces=NiveauAcces.RESTREINT)
    reponse = client.get(_url(production))
    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("comptes:connexion"))
    assert "next=" in reponse.url
    client_connecte, _ = connecter("ETUDIANT")
    assert client_connecte.get(_url(production)).status_code == 200


@pytest.mark.parametrize(
    ("niveau", "embargo"),
    [(NiveauAcces.CONFIDENTIEL, None), (NiveauAcces.LIBRE, DANS_UN_MOIS)],
)
def test_confidentiel_ou_sous_embargo_404_pour_un_tiers(connecter, niveau, embargo):
    production, etudiant, _ = depot_archive(niveau_acces=niveau, date_fin_embargo=embargo)
    client, _ = connecter("ENSEIGNANT")
    assert client.get(_url(production)).status_code == 404
    client.force_login(etudiant)
    assert client.get(_url(production)).status_code == 200


def test_ancienne_version_404_pour_le_public(connecter):
    production, etudiant, _ = depot_valide()
    biblio = bibliothecaire()
    services.demander_corrections_bibliotheque(biblio, production, "Page de garde.")
    services.soumettre_version_corrigee(etudiant, production, pdf_valide("v2.pdf"))
    services.archiver(biblio, production, NiveauAcces.LIBRE)
    client, _ = connecter("ETUDIANT")
    assert client.get(_url(production, 2)).status_code == 200
    assert client.get(_url(production, 1)).status_code == 404
    contenu = client.get(_detail(production), follow=True).content.decode()  # fiche publique
    assert _url(production, 2) in contenu
    assert _url(production, 1) not in contenu
    client.force_login(etudiant)
    assert client.get(_url(production, 1)).status_code == 200


def test_travail_retire_404_pour_un_tiers(connecter):
    production, etudiant, _ = depot_archive()
    services.retirer(bibliothecaire(), production, "Plagiat avéré.")
    client, _ = connecter("ETUDIANT")
    assert client.get(_detail(production)).status_code == 404
    assert client.get(_url(production)).status_code == 404
    client.force_login(etudiant)
    contenu = client.get(_detail(production)).content.decode()
    assert "Travail retiré le" in contenu and "Plagiat avéré." in contenu


def test_fiche_archivee_pour_un_tiers(connecter):
    production, _, _ = depot_archive(
        niveau_acces=NiveauAcces.CONFIDENTIEL, date_soutenance=datetime.date(2026, 6, 15)
    )
    client, _ = connecter("ETUDIANT")
    reponse = client.get(_detail(production))
    assert reponse.status_code == 302
    assert reponse.url == reverse("recherche:fiche", args=[production.pk])
    contenu = client.get(reponse.url).content.decode()
    assert "Cote MEM-2026-0001" in contenu
    assert "Le document est confidentiel" in contenu
    assert "Chronologie" not in contenu  # historique interne réservé aux proches
    assert "Avis des encadrants" not in contenu


def test_fiche_archivee_pour_l_auteur(client):
    production, etudiant, _ = depot_archive(date_fin_embargo=DANS_UN_MOIS)
    client.force_login(etudiant)
    contenu = client.get(_detail(production)).content.decode()
    assert "Jusqu&#x27;au" in contenu or "Jusqu'au" in contenu
    assert "Archivé sous la cote" in contenu
    assert "Contrôle de la bibliothèque : conforme" in contenu
    assert _url(production) in contenu

"""Espace bibliothèque : listes, écran de contrôle, archivage, accès, retrait, catalogue."""

import datetime
from html import escape

import pytest
from django.urls import reverse
from django.utils import timezone

from comptes.tests.factories import UtilisateurFactory
from productions import services
from productions.models import DecisionVerification, NiveauAcces, Statut
from productions.tests.factories import (
    TheseFactory,
    depot_archive,
    depot_soumis,
    depot_valide,
)
from productions.tests.fichiers import pdf_valide

pytestmark = pytest.mark.django_db

DEMAIN = timezone.localdate() + datetime.timedelta(days=1)


@pytest.fixture
def biblio(client):
    utilisateur = UtilisateurFactory(roles=["BIBLIOTHECAIRE"])
    client.force_login(utilisateur)
    return utilisateur


def _controle(production):
    return reverse("bibliotheque:controle", args=[production.pk])


# Droits ----------------------------------------------------------------------------------


@pytest.mark.parametrize("nom", ["a_controler", "catalogue"])
@pytest.mark.parametrize("roles", [["ETUDIANT"], ["ENSEIGNANT"], ["ADMINISTRATEUR"]])
def test_listes_reservees_aux_bibliothecaires(connecter, nom, roles):
    client, _ = connecter(*roles)
    assert client.get(reverse(f"bibliotheque:{nom}")).status_code == 403


def test_visiteur_redirige(client):
    production, _, _ = depot_valide()
    for url in [reverse("bibliotheque:a_controler"), _controle(production)]:
        reponse = client.get(url)
        assert reponse.status_code == 302
        assert reponse.url.startswith(reverse("comptes:connexion"))


@pytest.mark.parametrize("roles", [["ETUDIANT"], ["ENSEIGNANT"]])
def test_ecran_de_controle_refuse_aux_autres_roles(connecter, roles):
    production, _, _ = depot_valide()
    client, _ = connecter(*roles)
    assert client.get(_controle(production)).status_code == 403
    reponse = client.post(
        _controle(production), {"action": "archiver", "archivage-niveau_acces": "LIBRE"}
    )
    assert reponse.status_code == 403
    url = reverse("bibliotheque:metadonnees", args=[production.pk])
    assert client.get(url).status_code == 403
    production.refresh_from_db()
    assert production.statut == Statut.VALIDE


def test_ecran_de_controle_404_hors_perimetre(client, biblio):
    """Un travail encore chez l'encadreur n'est pas géré par la bibliothèque."""
    production, _, _ = depot_soumis()
    assert client.get(_controle(production)).status_code == 404
    url = reverse("bibliotheque:metadonnees", args=[production.pk])
    assert client.get(url).status_code == 404


# Listes ------------------------------------------------------------------------------------


def test_a_controler_et_compteur_du_menu(client, biblio):
    depot_valide(titre="Travail validé")
    depot_soumis(titre="Travail soumis")
    contenu = client.get(reverse("bibliotheque:a_controler")).content.decode()
    assert "Travail validé" in contenu
    assert "Travail soumis" not in contenu
    assert '1<span class="sr-only"> en attente</span>' in contenu
    contenu = client.get(
        reverse("bibliotheque:a_controler"), {"onglet": "corrections"}
    ).content.decode()
    assert "Travail validé" not in contenu


def test_catalogue_recherche_et_filtres(client, biblio):
    memoire, _, _ = depot_archive(titre="Hydrologie du fleuve Niger")
    these, _, _ = depot_archive(factory_classe=TheseFactory, titre="Grammaire du bambara")
    services.retirer(UtilisateurFactory(roles=["BIBLIOTHECAIRE"]), these, "Doublon.")
    depot_valide(titre="Pas encore archivé")
    url = reverse("bibliotheque:catalogue")

    contenu = client.get(url).content.decode()
    assert "Hydrologie" in contenu and "Grammaire" in contenu
    assert "Pas encore archivé" not in contenu
    assert "Hydrologie" in client.get(url, {"q": "niger"}).content.decode()
    contenu = client.get(url, {"q": memoire.cote}).content.decode()
    assert "Hydrologie" in contenu and "Grammaire" not in contenu
    contenu = client.get(url, {"statut": "RETIRE"}).content.decode()
    assert "Grammaire" in contenu and "Hydrologie" not in contenu
    contenu = client.get(url, {"type": "MEMOIRE"}).content.decode()
    assert "Hydrologie" in contenu and "Grammaire" not in contenu
    assert "Aucun travail trouvé" in client.get(url, {"q": "introuvable"}).content.decode()


# Archivage et corrections ----------------------------------------------------------------------


def test_archiver_depuis_l_ecran(client, biblio):
    production, _, _ = depot_valide(date_soutenance=datetime.date(2026, 6, 15))
    contenu = client.get(_controle(production)).content.decode()
    assert "MEM-2026-0001" in contenu  # aperçu de la forme de la cote
    reponse = client.post(
        _controle(production),
        {
            "action": "archiver",
            "archivage-niveau_acces": NiveauAcces.RESTREINT,
            "archivage-date_fin_embargo": DEMAIN.isoformat(),
        },
        follow=True,
    )
    assert "Travail archivé sous la cote MEM-2026-0001." in reponse.content.decode()
    production.refresh_from_db()
    assert production.statut == Statut.ARCHIVE
    assert production.niveau_acces == NiveauAcces.RESTREINT
    assert production.date_fin_embargo == DEMAIN


def test_archivage_avec_embargo_passe_refuse(client, biblio):
    production, _, _ = depot_valide()
    reponse = client.post(
        _controle(production),
        {
            "action": "archiver",
            "archivage-niveau_acces": "LIBRE",
            "archivage-date_fin_embargo": "2020-01-01",
        },
    )
    assert reponse.status_code == 200
    assert "postérieure à aujourd&#x27;hui" in reponse.content.decode()
    production.refresh_from_db()
    assert production.statut == Statut.VALIDE


def test_archivage_sans_date_de_soutenance(client, biblio):
    production, _, _ = depot_valide(date_soutenance=None)
    contenu = client.get(_controle(production)).content.decode()
    assert "La date de soutenance manque" in contenu
    reponse = client.post(
        _controle(production), {"action": "archiver", "archivage-niveau_acces": "LIBRE"}
    )
    assert reponse.status_code == 200
    assert "Renseignez la date de soutenance" in reponse.content.decode()


def test_archiver_deux_fois_renvoie_409(client, biblio):
    production, _, _ = depot_valide()
    donnees = {"action": "archiver", "archivage-niveau_acces": "LIBRE"}
    client.post(_controle(production), donnees)
    # Le formulaire d'archivage n'est plus affiché, mais une requête rejouée est refusée.
    assert client.post(_controle(production), donnees).status_code == 409


def test_demander_des_corrections_puis_reprise(client, biblio):
    production, etudiant, _ = depot_valide()
    reponse = client.post(_controle(production), {"action": "corrections", "corrections-motif": ""})
    assert reponse.status_code == 200
    assert "Un motif est obligatoire" in reponse.content.decode()

    client.post(
        _controle(production),
        {"action": "corrections", "corrections-motif": "Ajouter la page de garde."},
    )
    production.refresh_from_db()
    assert production.statut == Statut.A_CORRIGER_BIBLIOTHEQUE
    assert "En attente de la version corrigée" in client.get(_controle(production)).content.decode()

    client.force_login(etudiant)
    detail = client.get(reverse("productions:detail", args=[production.pk])).content.decode()
    assert "Corrections demandées par la bibliothèque" in detail
    assert "Ajouter la page de garde." in detail
    url = reverse("productions:version_corrigee", args=[production.pk])
    assert "Ajouter la page de garde." in client.get(url).content.decode()
    client.post(url, {"fichier": pdf_valide("v2.pdf"), "note": "Page de garde ajoutée."})
    production.refresh_from_db()
    assert production.statut == Statut.VALIDE

    client.force_login(biblio)
    contenu = client.get(_controle(production)).content.decode()
    assert "Page de garde ajoutée." in contenu
    assert production.verifications.get().decision == DecisionVerification.A_CORRIGER


def test_action_inconnue(client, biblio):
    production, _, _ = depot_valide()
    reponse = client.post(_controle(production), {"action": "detruire"}, follow=True)
    assert "Action inconnue." in reponse.content.decode()


def test_bibliothecaire_auteur_ne_voit_pas_les_decisions(client):
    double = UtilisateurFactory(roles=["ETUDIANT", "BIBLIOTHECAIRE"])
    production, _, _ = depot_valide(etudiant=double)
    client.force_login(double)
    contenu = client.get(_controle(production)).content.decode()
    assert "un autre bibliothécaire doit le traiter" in contenu
    assert 'value="archiver"' not in contenu
    reponse = client.post(
        _controle(production), {"action": "archiver", "archivage-niveau_acces": "LIBRE"}
    )
    assert "auteur" in reponse.content.decode()
    production.refresh_from_db()
    assert production.statut == Statut.VALIDE


# Accès et retrait ----------------------------------------------------------------------------


def test_modifier_l_acces(client, biblio):
    production, _, _ = depot_archive()
    contenu = client.get(_controle(production)).content.decode()
    assert 'value="acces"' in contenu and 'value="retirer"' in contenu
    client.post(
        _controle(production),
        {"action": "acces", "acces-niveau_acces": "CONFIDENTIEL", "acces-date_fin_embargo": ""},
    )
    production.refresh_from_db()
    assert production.niveau_acces == NiveauAcces.CONFIDENTIEL


def test_embargo_expire_conserve(client, biblio):
    production, _, _ = depot_archive()
    production.__class__.objects.filter(pk=production.pk).update(
        date_fin_embargo=datetime.date(2020, 1, 1)
    )
    reponse = client.post(
        _controle(production),
        {
            "action": "acces",
            "acces-niveau_acces": "RESTREINT",
            "acces-date_fin_embargo": "2020-01-01",
        },
    )
    assert reponse.status_code == 302
    production.refresh_from_db()
    assert production.niveau_acces == NiveauAcces.RESTREINT


def test_retirer(client, biblio):
    production, _, _ = depot_archive()
    reponse = client.post(_controle(production), {"action": "retirer", "retrait-motif": "  "})
    assert "Un motif est obligatoire" in reponse.content.decode()
    client.post(_controle(production), {"action": "retirer", "retrait-motif": "Plagiat avéré."})
    production.refresh_from_db()
    assert production.statut == Statut.RETIRE
    contenu = client.get(_controle(production)).content.decode()
    assert "Travail retiré le" in contenu and "Plagiat avéré." in contenu
    assert 'value="retirer"' not in contenu  # définitif
    assert (
        client.post(
            _controle(production), {"action": "retirer", "retrait-motif": "Encore"}
        ).status_code
        == 409
    )


# Métadonnées ----------------------------------------------------------------------------------


def test_modifier_les_metadonnees(client, biblio):
    production, _, _ = depot_archive()
    url = reverse("bibliotheque:metadonnees", args=[production.pk])
    contenu = client.get(url).content.decode()
    assert escape(production.titre) in contenu
    assert "(inchangée)" in contenu
    donnees = {
        "titre": "Titre corrigé par la bibliothèque",
        "resume": production.resume,
        "langue": production.langue,
        "niveau": "MASTER",
        "filiere": production.filiere_id,
        "annee_academique": production.annee_academique_id,
        "domaine": production.domaine_id,
        "mots_cles": list(production.mots_cles.values_list("pk", flat=True)),
        "date_soutenance": "2026-06-15",
        "mention": "BIEN",
    }
    reponse = client.post(url, donnees)
    assert reponse.status_code == 302
    production.refresh_from_db()
    assert production.titre == "Titre corrigé par la bibliothèque"
    assert production.mention == "BIEN"
    assert production.type_production == "MEMOIRE"

    donnees["date_soutenance"] = ""
    reponse = client.post(url, donnees)
    assert reponse.status_code == 200
    assert (
        "date de soutenance d&#x27;un travail archivé est obligatoire" in reponse.content.decode()
    )


def test_metadonnees_d_un_travail_retire_non_modifiables(client, biblio):
    production, _, _ = depot_archive()
    services.retirer(biblio, production, "Doublon.")
    url = reverse("bibliotheque:metadonnees", args=[production.pk])
    reponse = client.get(url)
    assert reponse.status_code == 302
    assert reponse.url == _controle(production)

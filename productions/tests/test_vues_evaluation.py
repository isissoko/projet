import pytest
from django.urls import reverse

from comptes.tests.factories import UtilisateurFactory
from productions import services
from productions.models import Avis, AvisEncadrement, Statut

from .factories import ajouter_codirecteur, depot_complet, depot_soumis
from .fichiers import octets_pdf, pdf_valide

pytestmark = pytest.mark.django_db


def _ecran(production):
    return reverse("evaluation:ecran", args=[production.pk])


# Travaux à évaluer --------------------------------------------------------------------


def test_liste_des_travaux_et_onglets(client):
    _production, _, directeur = depot_soumis(titre="Travail soumis")
    client.force_login(directeur.utilisateur)
    contenu = client.get(reverse("evaluation:liste")).content.decode()
    assert "Travail soumis" in contenu
    assert "Vous dirigez ce travail" in contenu
    assert "En attente de votre avis" in contenu
    contenu = client.get(reverse("evaluation:liste"), {"onglet": "traites"}).content.decode()
    assert "Travail soumis" not in contenu
    assert "Aucun travail dans cette catégorie" in contenu


def test_compteur_dans_le_menu(client):
    _, _, directeur = depot_soumis()
    client.force_login(directeur.utilisateur)
    contenu = client.get(reverse("accueil")).content.decode()
    assert "Travaux à évaluer" in contenu
    assert '1<span class="sr-only"> en attente</span>' in contenu


def test_liste_reservee_aux_enseignants(connecter, client):
    client_etudiant, _ = connecter("ETUDIANT")
    assert client_etudiant.get(reverse("evaluation:liste")).status_code == 403


# Écran d'évaluation ---------------------------------------------------------------------


def test_directeur_valide_depuis_l_ecran(client):
    production, _, directeur = depot_soumis()
    client.force_login(directeur.utilisateur)
    contenu = client.get(_ecran(production)).content.decode()
    assert "Votre avis" in contenu and 'name="avis"' in contenu
    assert reverse("productions:telecharger", args=[production.pk, 1]) in contenu
    reponse = client.post(_ecran(production), {"avis": Avis.FAVORABLE, "commentaire": ""})
    assert reponse.status_code == 302
    production.refresh_from_db()
    assert production.statut == Statut.VALIDE


def test_demande_de_corrections_sans_motif_refusee_par_le_formulaire(client):
    production, _, directeur = depot_soumis()
    client.force_login(directeur.utilisateur)
    reponse = client.post(_ecran(production), {"avis": Avis.CORRECTIONS_DEMANDEES})
    assert reponse.status_code == 200
    assert "Un motif est obligatoire" in reponse.content.decode()
    production.refresh_from_db()
    assert production.statut == Statut.SOUMIS


def test_co_directeur_voit_la_mention_consultative(client):
    production, _, _ = depot_soumis()
    codirecteur = ajouter_codirecteur(production)
    client.force_login(codirecteur.utilisateur)
    assert "avis est consultatif" in client.get(_ecran(production)).content.decode()
    client.post(_ecran(production), {"avis": Avis.DEFAVORABLE, "commentaire": "Trop court."})
    production.refresh_from_db()
    assert production.statut == Statut.SOUMIS
    contenu = client.get(_ecran(production)).content.decode()
    assert "Vous avez donné un avis" in contenu
    assert 'name="avis"' not in contenu


def test_avis_sur_un_travail_deja_evalue_renvoie_409(client):
    production, _, directeur = depot_soumis()
    client.force_login(directeur.utilisateur)
    client.post(_ecran(production), {"avis": Avis.FAVORABLE})
    reponse = client.post(_ecran(production), {"avis": Avis.DEFAVORABLE, "commentaire": "x"})
    assert reponse.status_code == 409
    assert AvisEncadrement.objects.count() == 1


@pytest.mark.parametrize("roles", [["ENSEIGNANT"], ["ETUDIANT"]])
def test_ecran_d_evaluation_404_pour_un_tiers(connecter, roles):
    production, _, _ = depot_soumis()
    client, _ = connecter(*roles)
    attendu = 404 if roles == ["ENSEIGNANT"] else 403  # un étudiant n'a pas le rôle requis
    assert client.get(_ecran(production)).status_code == attendu
    assert client.post(_ecran(production), {"avis": Avis.FAVORABLE}).status_code == attendu
    production.refresh_from_db()
    assert production.statut == Statut.SOUMIS


def test_ecran_d_evaluation_404_pour_un_brouillon(client):
    production, _, directeur = depot_complet()
    client.force_login(directeur.utilisateur)
    assert client.get(_ecran(production)).status_code == 404


def test_visiteur_redirige(client):
    production, _, _ = depot_soumis()
    reponse = client.get(_ecran(production))
    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("comptes:connexion"))


# Version corrigée (étudiant) ---------------------------------------------------------------


def test_parcours_corrections_puis_validation(client):
    production, etudiant, directeur = depot_soumis()

    client.force_login(directeur.utilisateur)
    client.post(
        _ecran(production),
        {"avis": Avis.CORRECTIONS_DEMANDEES, "commentaire": "Ajouter une conclusion."},
    )

    client.force_login(etudiant)
    detail = client.get(reverse("productions:detail", args=[production.pk])).content.decode()
    assert "Ajouter une conclusion." in detail
    assert "Déposer la version corrigée" in detail
    url = reverse("productions:version_corrigee", args=[production.pk])
    page = client.get(url).content.decode()
    assert "Ajouter une conclusion." in page and 'data-taille-max="52428800"' in page
    reponse = client.post(url, {"fichier": pdf_valide("v2.pdf"), "note": "Conclusion ajoutée."})
    assert reponse.status_code == 302
    production.refresh_from_db()
    assert production.statut == Statut.SOUMIS
    assert production.version_courante().numero == 2

    client.force_login(directeur.utilisateur)
    contenu = client.get(_ecran(production)).content.decode()
    assert "Conclusion ajoutée." in contenu
    client.post(_ecran(production), {"avis": Avis.FAVORABLE})
    production.refresh_from_db()
    assert production.statut == Statut.VALIDE


def test_version_corrigee_sans_fichier(client):
    production, etudiant, directeur = depot_soumis()
    services.donner_avis(directeur.utilisateur, production, Avis.CORRECTIONS_DEMANDEES, "x")
    client.force_login(etudiant)
    reponse = client.post(reverse("productions:version_corrigee", args=[production.pk]), {})
    assert reponse.status_code == 200
    production.refresh_from_db()
    assert production.statut == Statut.A_CORRIGER_ENCADREUR


def test_version_corrigee_hors_correction(client):
    production, etudiant, _ = depot_soumis()
    client.force_login(etudiant)
    url = reverse("productions:version_corrigee", args=[production.pk])
    assert client.get(url).status_code == 302  # renvoi vers le détail
    assert client.post(url, {"fichier": pdf_valide()}).status_code == 409
    assert production.versions.count() == 1


def test_version_corrigee_404_pour_un_autre_etudiant(connecter):
    production, _, directeur = depot_soumis()
    services.donner_avis(directeur.utilisateur, production, Avis.CORRECTIONS_DEMANDEES, "x")
    client, _ = connecter("ETUDIANT")
    url = reverse("productions:version_corrigee", args=[production.pk])
    assert client.get(url).status_code == 404
    assert client.post(url, {"fichier": pdf_valide()}).status_code == 404


def test_avis_visibles_par_l_auteur(client):
    production, etudiant, _directeur = depot_soumis()
    codirecteur = ajouter_codirecteur(production)
    services.donner_avis(codirecteur.utilisateur, production, Avis.FAVORABLE, "Très bon travail.")
    client.force_login(etudiant)
    contenu = client.get(reverse("productions:detail", args=[production.pk])).content.decode()
    assert "Très bon travail." in contenu
    assert "avis consultatif" in contenu


# Téléchargement -------------------------------------------------------------------------


def test_telechargement_par_les_proches(client):
    production, etudiant, directeur = depot_soumis()
    attendu = production.version_courante().fichier.open("rb").read()
    url = reverse("productions:telecharger", args=[production.pk, 1])
    proches = [
        etudiant,
        directeur.utilisateur,
        UtilisateurFactory(roles=["BIBLIOTHECAIRE"]),
        UtilisateurFactory(roles=["ADMINISTRATEUR"]),
    ]
    for utilisateur in proches:
        client.force_login(utilisateur)
        reponse = client.get(url)
        assert reponse.status_code == 200, utilisateur
        assert reponse["Content-Type"] == "application/pdf"
        assert 'filename="memoire.pdf"' in reponse["Content-Disposition"]
        assert reponse["Content-Disposition"].startswith("inline")
        assert "no-store" in reponse["Cache-Control"]
        assert b"".join(reponse.streaming_content) == attendu


def test_telechargement_404_pour_un_tiers(connecter):
    production, _, _ = depot_soumis()
    url = reverse("productions:telecharger", args=[production.pk, 1])
    for roles in [["ETUDIANT"], ["ENSEIGNANT"]]:
        client, _ = connecter(*roles)
        assert client.get(url).status_code == 404


def test_telechargement_visiteur_redirige(client):
    production, _, _ = depot_soumis()
    reponse = client.get(reverse("productions:telecharger", args=[production.pk, 1]))
    assert reponse.status_code == 302


def test_telechargement_version_inexistante(client):
    production, etudiant, _ = depot_soumis()
    client.force_login(etudiant)
    assert (
        client.get(reverse("productions:telecharger", args=[production.pk, 9])).status_code == 404
    )


def test_telechargement_d_une_ancienne_version(client):
    production, etudiant, directeur = depot_soumis()
    services.donner_avis(directeur.utilisateur, production, Avis.CORRECTIONS_DEMANDEES, "x")
    services.soumettre_version_corrigee(etudiant, production, pdf_valide("v2.pdf"))
    client.force_login(directeur.utilisateur)
    reponse = client.get(reverse("productions:telecharger", args=[production.pk, 1]))
    assert reponse.status_code == 200
    assert b"".join(reponse.streaming_content) == octets_pdf()


def test_telechargement_via_x_accel_redirect(client, settings):
    settings.X_ACCEL_REDIRECT = True
    settings.X_ACCEL_PREFIXE = "/prive/"
    production, etudiant, _ = depot_soumis()
    client.force_login(etudiant)
    reponse = client.get(reverse("productions:telecharger", args=[production.pk, 1]))
    assert reponse.status_code == 200
    assert reponse["X-Accel-Redirect"] == "/prive/" + production.version_courante().fichier.name
    assert reponse.content == b""


def test_fichier_absent_du_disque(client):
    production, etudiant, _ = depot_soumis()
    version = production.version_courante()
    version.fichier.storage.delete(version.fichier.name)
    client.force_login(etudiant)
    assert (
        client.get(reverse("productions:telecharger", args=[production.pk, 1])).status_code == 404
    )

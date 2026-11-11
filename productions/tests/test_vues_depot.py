import pytest
from django.urls import reverse

from comptes.tests.factories import ProfilEnseignantFactory, UtilisateurFactory
from productions import services
from productions.models import Memoire, Production, Statut, These, VersionDocument
from referentiel.tests.factories import (
    AnneeAcademiqueFactory,
    DomaineFactory,
    FiliereFactory,
    MotCleFactory,
)

from .factories import depot_complet
from .fichiers import docx_renomme_en_pdf, pdf_valide

pytestmark = pytest.mark.django_db

ETAPES = ["etape1", "etape2", "etape3", "etape4", "etape5"]


# Parcours complet ---------------------------------------------------------------------


@pytest.mark.parametrize("type_production", ["MEMOIRE", "THESE"])
def test_parcours_de_depot_en_cinq_etapes(connecter, type_production):
    client, _ = connecter("ETUDIANT")
    filiere, annee, domaine, mot = (
        FiliereFactory(),
        AnneeAcademiqueFactory(courante=True),
        DomaineFactory(),
        MotCleFactory(),
    )
    directeur = ProfilEnseignantFactory(
        utilisateur__first_name="Bourama", utilisateur__last_name="Konaté"
    )

    # Étape 1 : création du brouillon.
    reponse = client.get(reverse("productions:nouveau"))
    assert reponse.status_code == 200
    assert 'aria-current="step"' in reponse.content.decode()
    reponse = client.post(
        reverse("productions:nouveau"),
        {
            "type_production": type_production,
            "titre": "Irrigation goutte-à-goutte à Ségou",
            "resume": "Étude de cas.",
            "langue": "FRANCAIS",
            "niveau": "MASTER" if type_production == "MEMOIRE" else "",
            "filiere": filiere.pk,
            "annee_academique": annee.pk,
            "domaine": domaine.pk,
            "mots_cles": [mot.pk],
        },
    )
    production = Production.objects.get()
    assert reponse.status_code == 302
    assert reponse.url == reverse("productions:etape2", args=[production.pk])
    attendu = Memoire if type_production == "MEMOIRE" else These
    assert isinstance(production.specifique(), attendu)

    # Étape 2 : recherche de l'enseignant par nom, puis ajout comme directeur.
    url2 = reverse("productions:etape2", args=[production.pk])
    contenu = client.get(url2, {"q": "konat"}).content.decode()
    assert "Bourama Konaté" in contenu and "Ajouter comme directeur" in contenu
    client.post(
        url2, {"action": "ajouter_encadrant", "enseignant": directeur.pk, "role": "DIRECTEUR"}
    )
    client.post(
        url2,
        {"action": "ajouter_coauteur", "nom": "Coulibaly", "prenom": "Fatou", "affiliation": ""},
    )
    assert production.encadrements.get().enseignant == directeur
    assert production.contributions.count() == 2

    # Étape 3 : fichier.
    url3 = reverse("productions:etape3", args=[production.pk])
    assert 'data-taille-max="52428800"' in client.get(url3).content.decode()
    reponse = client.post(url3, {"fichier": pdf_valide()})
    assert reponse.status_code == 302
    assert production.versions.count() == 1

    # Étape 4 : récapitulatif complet.
    contenu = client.get(reverse("productions:etape4", args=[production.pk])).content.decode()
    assert "Le dépôt est complet" in contenu
    assert "Bourama Konaté" in contenu

    # Étape 5 : soumission.
    reponse = client.post(reverse("productions:etape5", args=[production.pk]))
    assert reponse.status_code == 302
    production.refresh_from_db()
    assert production.statut == Statut.SOUMIS


def test_retour_en_arriere_conserve_les_donnees(connecter):
    client, etudiant = connecter("ETUDIANT")
    production, _, _ = depot_complet(etudiant=etudiant, titre="Titre conservé")
    contenu = client.get(reverse("productions:etape1", args=[production.pk])).content.decode()
    assert 'value="Titre conservé"' in contenu
    assert "Le type ne peut plus être modifié" in contenu


def test_etape1_refuse_memoire_sans_niveau(connecter):
    client, _ = connecter("ETUDIANT")
    reponse = client.post(
        reverse("productions:nouveau"),
        {"type_production": "MEMOIRE", "titre": "X", "langue": "FRANCAIS", "niveau": ""},
    )
    assert reponse.status_code == 200
    assert "Indiquez le niveau du mémoire" in reponse.content.decode()
    assert not Production.objects.exists()


def test_etape1_refuse_mention_de_these_pour_un_memoire(connecter):
    client, _ = connecter("ETUDIANT")
    reponse = client.post(
        reverse("productions:nouveau"),
        {
            "type_production": "MEMOIRE",
            "titre": "X",
            "langue": "FRANCAIS",
            "niveau": "MASTER",
            "mention": "TRES_HONORABLE",
        },
    )
    assert reponse.status_code == 200
    assert not Production.objects.exists()


def test_etape1_niveau_doctorat_absent_des_choix(connecter):
    client, _ = connecter("ETUDIANT")
    reponse = client.post(
        reverse("productions:nouveau"),
        {"type_production": "MEMOIRE", "titre": "X", "langue": "FRANCAIS", "niveau": "DOCTORAT"},
    )
    assert reponse.status_code == 200
    assert not Production.objects.exists()


def test_etape3_refuse_docx_renomme(connecter):
    client, etudiant = connecter("ETUDIANT")
    production, _, _ = depot_complet(etudiant=etudiant)
    reponse = client.post(
        reverse("productions:etape3", args=[production.pk]), {"fichier": docx_renomme_en_pdf()}
    )
    assert reponse.status_code == 200
    assert "n&#x27;est pas un PDF" in reponse.content.decode()
    assert VersionDocument.objects.filter(production=production).count() == 1


def test_etape5_affiche_ce_qui_manque(connecter):
    client, etudiant = connecter("ETUDIANT")
    production, _, _ = depot_complet(etudiant=etudiant)
    production.encadrements.all().delete()
    reponse = client.post(reverse("productions:etape5", args=[production.pk]))
    assert reponse.status_code == 200
    assert "Un directeur (encadrant principal)" in reponse.content.decode()
    production.refresh_from_db()
    assert production.statut == Statut.BROUILLON


# Mes dépôts et détail -----------------------------------------------------------------


def test_mes_depots_affiche_les_cartes(connecter):
    client, etudiant = connecter("ETUDIANT")
    depot_complet(etudiant=etudiant, titre="Mon mémoire")
    depot_complet(titre="Mémoire d'un autre")
    contenu = client.get(reverse("productions:mes_depots")).content.decode()
    assert "Mon mémoire" in contenu
    assert "Mémoire d&#x27;un autre" not in contenu
    assert "Brouillon" in contenu  # badge de statut


def test_mes_depots_vide(connecter):
    client, _ = connecter("ETUDIANT")
    assert "Aucun dépôt pour l" in client.get(reverse("productions:mes_depots")).content.decode()


def test_detail_affiche_versions_et_actions(connecter):
    client, etudiant = connecter("ETUDIANT")
    production, _, _ = depot_complet(etudiant=etudiant)
    version = production.versions.get()
    contenu = client.get(reverse("productions:detail", args=[production.pk])).content.decode()
    assert version.empreinte_abregee in contenu
    assert "Version 1 déposée" in contenu  # chronologie
    assert "Supprimer" in contenu and "data-confirmation" in contenu


def test_detail_sans_actions_apres_soumission(connecter):
    client, etudiant = connecter("ETUDIANT")
    production, _, _ = depot_complet(etudiant=etudiant)
    client.post(reverse("productions:etape5", args=[production.pk]))
    contenu = client.get(reverse("productions:detail", args=[production.pk])).content.decode()
    assert "Soumis à l&#x27;encadreur" in contenu
    assert reverse("productions:supprimer", args=[production.pk]) not in contenu
    # Les étapes renvoient vers le détail.
    reponse = client.get(reverse("productions:etape1", args=[production.pk]))
    assert reponse.status_code == 302
    assert reponse.url == reverse("productions:detail", args=[production.pk])


# Accès --------------------------------------------------------------------------------


def test_autre_etudiant_recoit_404(connecter):
    production, _, _ = depot_complet()
    client, _ = connecter("ETUDIANT")
    for nom in ["detail", "supprimer", *ETAPES]:
        methode = client.post if nom == "supprimer" else client.get
        assert methode(reverse(f"productions:{nom}", args=[production.pk])).status_code == 404, nom
    assert Production.objects.filter(pk=production.pk).exists()


def test_enseignant_non_encadrant_recoit_404(connecter):
    production, _, _ = depot_complet()
    client, _ = connecter("ENSEIGNANT")
    assert client.get(reverse("productions:detail", args=[production.pk])).status_code == 404


def test_directeur_voit_le_detail_mais_ne_modifie_pas(client):
    production, _, directeur = depot_complet()
    client.force_login(directeur.utilisateur)
    assert client.get(reverse("productions:detail", args=[production.pk])).status_code == 200
    reponse = client.get(reverse("productions:etape1", args=[production.pk]))
    assert reponse.status_code == 302


def test_visiteur_redirige_vers_la_connexion(client):
    production, _, _ = depot_complet()
    for url in [
        reverse("productions:mes_depots"),
        reverse("productions:nouveau"),
        reverse("productions:detail", args=[production.pk]),
        reverse("productions:etape2", args=[production.pk]),
    ]:
        reponse = client.get(url)
        assert reponse.status_code == 302
        assert reponse.url.startswith(reverse("comptes:connexion"))


def test_depot_reserve_aux_etudiants(connecter):
    client, _ = connecter("ENSEIGNANT")
    assert client.get(reverse("productions:nouveau")).status_code == 403
    assert client.get(reverse("productions:mes_depots")).status_code == 403


# Suppression --------------------------------------------------------------------------


def test_suppression_d_un_brouillon(connecter):
    client, etudiant = connecter("ETUDIANT")
    production, _, _ = depot_complet(etudiant=etudiant)
    reponse = client.post(reverse("productions:supprimer", args=[production.pk]))
    assert reponse.status_code == 302
    assert not Production.objects.filter(pk=production.pk).exists()


def test_suppression_hors_brouillon_renvoie_409(connecter):
    client, etudiant = connecter("ETUDIANT")
    production, _, _ = depot_complet(etudiant=etudiant)
    Production.objects.filter(pk=production.pk).update(statut=Statut.SOUMIS)
    reponse = client.post(reverse("productions:supprimer", args=[production.pk]))
    assert reponse.status_code == 409
    assert "Action impossible" in reponse.content.decode()
    assert Production.objects.filter(pk=production.pk).exists()


def test_coauteur_ne_peut_pas_supprimer(client):
    production, _, _ = depot_complet()
    coauteur = UtilisateurFactory(roles=["ETUDIANT"])
    services.contributeur_pour_utilisateur(coauteur)
    production.contributions.create(contributeur=coauteur.contributeur, rang=2, role="CO_AUTEUR")
    client.force_login(coauteur)
    assert client.get(reverse("productions:detail", args=[production.pk])).status_code == 200
    client.post(reverse("productions:supprimer", args=[production.pk]))
    assert Production.objects.filter(pk=production.pk).exists()


def test_menu_mes_depots_pour_un_etudiant(connecter):
    client, _ = connecter("ETUDIANT")
    assert ">Mes dépôts<" in client.get(reverse("accueil")).content.decode()

import re

import pytest
from django.core import mail
from django.db import IntegrityError, transaction
from django.urls import reverse

from comptes.exceptions import ActionInterdite
from comptes.models import ProfilEtudiant, Utilisateur
from comptes.roles import Role
from comptes.services import (
    DonneesProfilEtudiant,
    changer_activation,
    creer_compte,
    modifier_roles,
)
from referentiel.tests.factories import DepartementFactory, FiliereFactory

from .factories import ProfilEtudiantFactory, UtilisateurFactory

pytestmark = pytest.mark.django_db

URL_LISTE = reverse("comptes:liste")
URL_CREER = reverse("comptes:creer")


# Accès ---------------------------------------------------------------------


def test_visiteur_redirige_vers_la_connexion(client):
    for url in [URL_LISTE, URL_CREER, reverse("comptes:modifier", args=[1])]:
        reponse = client.get(url)
        assert reponse.status_code == 302
        assert reponse.url.startswith(reverse("comptes:connexion") + "?next=")


@pytest.mark.parametrize("role", [Role.ETUDIANT, Role.ENSEIGNANT, Role.BIBLIOTHECAIRE])
def test_interface_comptes_refusee_sans_role_administrateur(connecter, role):
    client, _ = connecter(role)
    reponse = client.get(URL_LISTE)
    assert reponse.status_code == 403
    assert "Accès refusé" in reponse.content.decode()  # page 403 stylée
    assert client.get(URL_CREER).status_code == 403


def test_etudiant_recoit_403_meme_pour_un_compte_inexistant(connecter):
    client, _ = connecter(Role.ETUDIANT)
    assert client.get(reverse("comptes:modifier", args=[999999])).status_code == 403
    assert client.post(reverse("comptes:activation", args=[999999])).status_code == 403


def test_utilisateur_a_deux_roles_accede_aux_deux_espaces(connecter):
    client, _ = connecter(Role.BIBLIOTHECAIRE, Role.ADMINISTRATEUR)
    assert client.get(URL_LISTE).status_code == 200
    assert client.get(reverse("referentiel:accueil")).status_code == 200


def test_bibliothecaire_seul_accede_au_referentiel_mais_pas_aux_comptes(connecter):
    client, _ = connecter(Role.BIBLIOTHECAIRE)
    assert client.get(reverse("referentiel:accueil")).status_code == 200
    assert client.get(URL_LISTE).status_code == 403


# Menu ----------------------------------------------------------------------


def test_menu_adapte_aux_roles(client, connecter):
    contenu = client.get(reverse("accueil")).content.decode()
    assert "Se connecter" in contenu
    assert ">Comptes<" not in contenu and ">Référentiel<" not in contenu

    client, _ = connecter(Role.ETUDIANT)
    contenu = client.get(reverse("accueil")).content.decode()
    assert "Se déconnecter" in contenu
    assert ">Comptes<" not in contenu and ">Référentiel<" not in contenu

    client, _ = connecter(Role.BIBLIOTHECAIRE)
    contenu = client.get(reverse("accueil")).content.decode()
    assert ">Référentiel<" in contenu and ">Comptes<" not in contenu

    client, _ = connecter(Role.ADMINISTRATEUR)
    contenu = client.get(URL_LISTE).content.decode()
    assert ">Référentiel<" in contenu and ">Comptes<" in contenu
    assert 'aria-current="page">Comptes<' in contenu


# Liste ---------------------------------------------------------------------


def test_liste_recherche_et_filtre_par_role(admin_connecte):
    client, _ = admin_connecte
    UtilisateurFactory(first_name="Aminata", last_name="Keita", roles=[Role.ETUDIANT])
    UtilisateurFactory(first_name="Bakary", last_name="Coulibaly", roles=[Role.ENSEIGNANT])

    contenu = client.get(URL_LISTE, {"q": "keita"}).content.decode()
    assert "Aminata Keita" in contenu and "Bakary Coulibaly" not in contenu

    contenu = client.get(URL_LISTE, {"role": Role.ENSEIGNANT}).content.decode()
    assert "Bakary Coulibaly" in contenu and "Aminata Keita" not in contenu

    contenu = client.get(URL_LISTE, {"q": "introuvable"}).content.decode()
    assert "Aucun compte ne correspond" in contenu


def test_liste_filtre_par_etat(admin_connecte):
    client, _ = admin_connecte
    UtilisateurFactory(first_name="Ancien", last_name="Compte", is_active=False)
    contenu = client.get(URL_LISTE, {"actif": "0"}).content.decode()
    assert "Ancien Compte" in contenu
    contenu = client.get(URL_LISTE, {"actif": "1"}).content.decode()
    assert "Ancien Compte" not in contenu


# Création ------------------------------------------------------------------


def _donnees_etudiant(filiere_par_defaut, **autres):
    return {
        "email": "nouvel.etudiant@sigaps.test",
        "prenom": "Oumar",
        "nom": "Traoré",
        "roles": [Role.ETUDIANT],
        "matricule": "ml-2026 001",
        "niveau": "MASTER",
        "filiere": filiere_par_defaut.pk,
        **autres,
    }


def test_creation_compte_etudiant_avec_profil_et_invitation(
    admin_connecte, django_capture_on_commit_callbacks
):
    client, _ = admin_connecte
    filiere = FiliereFactory()
    with django_capture_on_commit_callbacks(execute=True):
        reponse = client.post(URL_CREER, _donnees_etudiant(filiere))
    assert reponse.status_code == 302
    compte = Utilisateur.objects.get(email="nouvel.etudiant@sigaps.test")
    assert compte.a_role(Role.ETUDIANT)
    assert not compte.has_usable_password()
    assert compte.profil_etudiant.matricule == "ML-2026001"
    assert compte.profil_etudiant.filiere == filiere
    assert len(mail.outbox) == 1
    assert "Activez votre compte" in mail.outbox[0].subject
    assert "/comptes/reinitialisation/" in mail.outbox[0].body


def test_creation_compte_enseignant_avec_profil(admin_connecte):
    client, _ = admin_connecte
    departement = DepartementFactory()
    reponse = client.post(
        URL_CREER,
        {
            "email": "prof@sigaps.test",
            "prenom": "Mariam",
            "nom": "Sangaré",
            "roles": [Role.ENSEIGNANT, Role.BIBLIOTHECAIRE],
            "grade": "PROFESSEUR",
            "specialite": "Linguistique",
            "departement": departement.pk,
        },
    )
    assert reponse.status_code == 302
    compte = Utilisateur.objects.get(email="prof@sigaps.test")
    assert compte.roles == {Role.ENSEIGNANT, Role.BIBLIOTHECAIRE}
    assert compte.profil_enseignant.departement == departement
    assert not hasattr(compte, "profil_etudiant")


def test_creation_etudiant_sans_profil_refusee(admin_connecte):
    client, _ = admin_connecte
    donnees = _donnees_etudiant(FiliereFactory(), matricule="", filiere="")
    reponse = client.post(URL_CREER, donnees)
    assert reponse.status_code == 200
    assert "Ce champ est obligatoire pour le rôle choisi." in reponse.content.decode()
    assert not Utilisateur.objects.filter(email=donnees["email"]).exists()


def test_creation_sans_role_refusee(admin_connecte):
    client, _ = admin_connecte
    reponse = client.post(URL_CREER, _donnees_etudiant(FiliereFactory(), roles=[]))
    assert reponse.status_code == 200
    assert not Utilisateur.objects.filter(email="nouvel.etudiant@sigaps.test").exists()


# Unicité -------------------------------------------------------------------


def test_email_unique_dans_le_formulaire(admin_connecte):
    client, _ = admin_connecte
    UtilisateurFactory(email="nouvel.etudiant@sigaps.test")
    donnees = _donnees_etudiant(FiliereFactory(), email="NOUVEL.etudiant@sigaps.test")
    reponse = client.post(URL_CREER, donnees)
    assert reponse.status_code == 200
    assert "Cette adresse e-mail est déjà utilisée." in reponse.content.decode()


def test_email_unique_dans_le_service():
    UtilisateurFactory(email="double@sigaps.test")
    with pytest.raises(ActionInterdite):
        creer_compte(email="Double@sigaps.test", prenom="A", nom="B", roles=[Role.ADMINISTRATEUR])


def test_matricule_unique_dans_le_formulaire(admin_connecte):
    client, _ = admin_connecte
    ProfilEtudiantFactory(matricule="ML-2026001")
    reponse = client.post(URL_CREER, _donnees_etudiant(FiliereFactory()))  # « ml-2026 001 »
    assert reponse.status_code == 200
    assert "Ce matricule est déjà attribué" in reponse.content.decode()


def test_matricule_unique_dans_le_service():
    ProfilEtudiantFactory(matricule="MAT-1")
    with pytest.raises(ActionInterdite):
        creer_compte(
            email="autre@sigaps.test",
            prenom="A",
            nom="B",
            roles=[Role.ETUDIANT],
            profil_etudiant=DonneesProfilEtudiant("mat-1", "LICENCE", FiliereFactory()),
        )


def test_matricule_unique_en_base():
    ProfilEtudiantFactory(matricule="MAT-2")
    with pytest.raises(IntegrityError), transaction.atomic():
        ProfilEtudiant.objects.bulk_create(
            [
                ProfilEtudiant(
                    utilisateur=UtilisateurFactory(),
                    matricule="MAT-2",
                    niveau="LICENCE",
                    filiere=FiliereFactory(),
                )
            ]
        )


# Modification des rôles -------------------------------------------------------


def test_administrateur_ne_peut_pas_retirer_son_propre_role_service():
    admin = UtilisateurFactory(roles=[Role.ADMINISTRATEUR, Role.BIBLIOTHECAIRE])
    with pytest.raises(ActionInterdite, match="propre rôle Administrateur"):
        modifier_roles(admin, admin, [Role.BIBLIOTHECAIRE])
    admin.oublier_roles()
    assert admin.a_role(Role.ADMINISTRATEUR)


def test_administrateur_ne_peut_pas_retirer_son_propre_role_vue(admin_connecte):
    client, admin = admin_connecte
    reponse = client.post(
        reverse("comptes:modifier", args=[admin.pk]),
        {
            "email": admin.email,
            "prenom": admin.first_name,
            "nom": admin.last_name,
            "roles": [Role.BIBLIOTHECAIRE],
        },
    )
    assert reponse.status_code == 200
    assert "Vous ne pouvez pas retirer votre propre rôle Administrateur." in (
        reponse.content.decode()
    )
    admin.refresh_from_db()
    admin.oublier_roles()
    assert admin.roles == {Role.ADMINISTRATEUR}


def test_administrateur_peut_ajouter_un_role_a_lui_meme():
    admin = UtilisateurFactory(roles=[Role.ADMINISTRATEUR])
    modifier_roles(admin, admin, [Role.ADMINISTRATEUR, Role.BIBLIOTHECAIRE])
    assert admin.roles == {Role.ADMINISTRATEUR, Role.BIBLIOTHECAIRE}


def test_administrateur_peut_retirer_le_role_d_un_autre_administrateur():
    admin = UtilisateurFactory(roles=[Role.ADMINISTRATEUR])
    autre = UtilisateurFactory(roles=[Role.ADMINISTRATEUR])
    modifier_roles(admin, autre, [Role.BIBLIOTHECAIRE])
    assert autre.roles == {Role.BIBLIOTHECAIRE}


def test_modification_compte_et_ajout_profil(admin_connecte):
    client, _ = admin_connecte
    compte = UtilisateurFactory(roles=[Role.BIBLIOTHECAIRE])
    filiere = FiliereFactory()
    url = reverse("comptes:modifier", args=[compte.pk])
    assert client.get(url).status_code == 200
    reponse = client.post(
        url,
        {
            "email": compte.email,
            "prenom": "Nouveau",
            "nom": "Nom",
            "roles": [Role.BIBLIOTHECAIRE, Role.ETUDIANT],
            "matricule": "MAT-99",
            "niveau": "LICENCE",
            "filiere": filiere.pk,
        },
    )
    assert reponse.status_code == 302
    compte.refresh_from_db()
    compte.oublier_roles()
    assert compte.first_name == "Nouveau"
    assert compte.roles == {Role.BIBLIOTHECAIRE, Role.ETUDIANT}
    assert compte.profil_etudiant.matricule == "MAT-99"


def test_modification_conserve_son_propre_matricule(admin_connecte):
    client, _ = admin_connecte
    profil = ProfilEtudiantFactory(matricule="MAT-7")
    compte = profil.utilisateur
    reponse = client.post(
        reverse("comptes:modifier", args=[compte.pk]),
        {
            "email": compte.email,
            "prenom": compte.first_name,
            "nom": compte.last_name,
            "roles": [Role.ETUDIANT],
            "matricule": "MAT-7",
            "niveau": profil.niveau,
            "filiere": profil.filiere.pk,
        },
    )
    assert reponse.status_code == 302


# Activation ----------------------------------------------------------------


def test_desactivation_et_reactivation(admin_connecte):
    client, _ = admin_connecte
    compte = UtilisateurFactory(roles=[Role.ETUDIANT])
    url = reverse("comptes:activation", args=[compte.pk])
    assert client.get(url).status_code == 405
    client.post(url, {"actif": "0"})
    compte.refresh_from_db()
    assert not compte.is_active
    client.post(url, {"actif": "1", "suivant": URL_LISTE + "?q=x"})
    compte.refresh_from_db()
    assert compte.is_active


def test_redirection_apres_activation_limitee_a_la_liste(admin_connecte):
    client, _ = admin_connecte
    compte = UtilisateurFactory()
    reponse = client.post(
        reverse("comptes:activation", args=[compte.pk]),
        {"actif": "0", "suivant": "https://exemple.com/"},
    )
    assert reponse.url == URL_LISTE


def test_administrateur_ne_peut_pas_se_desactiver(admin_connecte):
    client, admin = admin_connecte
    client.post(reverse("comptes:activation", args=[admin.pk]), {"actif": "0"})
    admin.refresh_from_db()
    assert admin.is_active
    with pytest.raises(ActionInterdite):
        changer_activation(admin, admin, False)


def test_formulaire_de_modification_prerempli(admin_connecte):
    client, _ = admin_connecte
    profil = ProfilEtudiantFactory(
        matricule="MAT-PRE", utilisateur__first_name="Aïssata", utilisateur__email="a@sigaps.test"
    )
    contenu = client.get(reverse("comptes:modifier", args=[profil.utilisateur.pk])).content.decode()
    assert 'value="Aïssata"' in contenu
    assert 'value="a@sigaps.test"' in contenu
    assert 'value="MAT-PRE"' in contenu
    assert re.search(r'<input[^>]*value="ETUDIANT"[^>]*checked', contenu)

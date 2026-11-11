import pytest
from django.urls import reverse

from comptes.roles import Role
from referentiel.models import AnneeAcademique, Filiere, MotCle
from referentiel.registre import TYPES

from .factories import (
    AnneeAcademiqueFactory,
    DepartementFactory,
    FiliereFactory,
    MotCleFactory,
)

pytestmark = pytest.mark.django_db


def test_visiteur_redirige_vers_la_connexion(client):
    reponse = client.get(reverse("referentiel:accueil"))
    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("comptes:connexion"))


@pytest.mark.parametrize("role", [Role.ETUDIANT, Role.ENSEIGNANT])
def test_referentiel_refuse_sans_role(connecter, role):
    client, _ = connecter(role)
    assert client.get(reverse("referentiel:accueil")).status_code == 403
    assert client.get(reverse("referentiel:liste", args=["filieres"])).status_code == 403
    assert client.get(reverse("referentiel:modifier", args=["filieres", 99999])).status_code == 403


@pytest.mark.parametrize("role", [Role.BIBLIOTHECAIRE, Role.ADMINISTRATEUR])
def test_toutes_les_pages_accessibles(connecter, role):
    client, _ = connecter(role)
    assert client.get(reverse("referentiel:accueil")).status_code == 200
    for slug in TYPES:
        assert client.get(reverse("referentiel:liste", args=[slug])).status_code == 200
        assert client.get(reverse("referentiel:creer", args=[slug])).status_code == 200


def test_type_inconnu_404(connecter):
    client, _ = connecter(Role.BIBLIOTHECAIRE)
    assert client.get(reverse("referentiel:liste", args=["inconnu"])).status_code == 404


def test_creation_et_modification_filiere(connecter):
    client, _ = connecter(Role.BIBLIOTHECAIRE)
    departement = DepartementFactory()
    reponse = client.post(
        reverse("referentiel:creer", args=["filieres"]),
        {"departement": departement.pk, "code": "soc", "libelle": "Sociologie"},
    )
    assert reponse.status_code == 302
    filiere = Filiere.objects.get(code="SOC")
    reponse = client.post(
        reverse("referentiel:modifier", args=["filieres", filiere.pk]),
        {"departement": departement.pk, "code": "SOC", "libelle": "Sociologie rurale"},
    )
    assert reponse.status_code == 302
    filiere.refresh_from_db()
    assert filiere.libelle == "Sociologie rurale"


def test_creation_mot_cle_en_double_refusee(connecter):
    client, _ = connecter(Role.BIBLIOTHECAIRE)
    MotCleFactory(libelle="Climat")
    reponse = client.post(reverse("referentiel:creer", args=["mots-cles"]), {"libelle": "CLIMAT"})
    assert reponse.status_code == 200
    assert MotCle.objects.count() == 1


def test_liste_recherche_et_etat(connecter):
    client, _ = connecter(Role.BIBLIOTHECAIRE)
    FiliereFactory(libelle="Histoire")
    FiliereFactory(libelle="Physique", actif=False)
    url = reverse("referentiel:liste", args=["filieres"])
    contenu = client.get(url).content.decode()
    assert "Histoire" in contenu and "Physique" not in contenu
    contenu = client.get(url, {"etat": "inactifs"}).content.decode()
    assert "Physique" in contenu and "Histoire" not in contenu
    contenu = client.get(url, {"etat": "tous", "q": "phys"}).content.decode()
    assert "Physique" in contenu and "Histoire" not in contenu


def test_liste_affiche_les_dates_en_francais(connecter):
    client, _ = connecter(Role.BIBLIOTHECAIRE)
    AnneeAcademiqueFactory(debut=2025)
    contenu = client.get(reverse("referentiel:liste", args=["annees"])).content.decode()
    assert "1 octobre 2025" in contenu


def test_actions_supprimer_reactiver_courante(connecter):
    client, _ = connecter(Role.ADMINISTRATEUR)
    mot = MotCleFactory()
    filiere = FiliereFactory(actif=False)
    annee = AnneeAcademiqueFactory()

    assert (
        client.get(
            reverse("referentiel:action", args=["mots-cles", mot.pk, "supprimer"])
        ).status_code
        == 405
    )
    client.post(reverse("referentiel:action", args=["mots-cles", mot.pk, "supprimer"]))
    assert not MotCle.objects.filter(pk=mot.pk).exists()

    client.post(reverse("referentiel:action", args=["filieres", filiere.pk, "reactiver"]))
    filiere.refresh_from_db()
    assert filiere.actif

    client.post(reverse("referentiel:action", args=["annees", annee.pk, "courante"]))
    assert AnneeAcademique.objects.get(courante=True) == annee


def test_action_interdite_affiche_un_message(connecter):
    client, _ = connecter(Role.ADMINISTRATEUR)
    annee = AnneeAcademiqueFactory(courante=True)
    reponse = client.post(
        reverse("referentiel:action", args=["annees", annee.pk, "supprimer"]), follow=True
    )
    assert "année courante ne peut être ni supprimée ni désactivée." in reponse.content.decode()
    assert AnneeAcademique.objects.filter(pk=annee.pk, actif=True).exists()

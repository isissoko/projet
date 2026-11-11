import re

import pytest
from django.contrib.auth import get_user
from django.core import mail
from django.urls import reverse

from comptes.models import Utilisateur

from .factories import MOT_DE_PASSE, UtilisateurFactory

pytestmark = pytest.mark.django_db

URL_CONNEXION = reverse("comptes:connexion")


def _connexion(client, email, mot_de_passe):
    return client.post(URL_CONNEXION, {"username": email, "password": mot_de_passe})


def test_connexion_par_email_reussie(client):
    u = UtilisateurFactory(email="awa@sigaps.test")
    reponse = _connexion(client, "Awa@Sigaps.test", MOT_DE_PASSE)
    assert reponse.status_code == 302
    assert reponse.url == reverse("accueil")
    assert get_user(client).pk == u.pk


def test_connexion_echouee_mauvais_mot_de_passe(client):
    UtilisateurFactory(email="awa@sigaps.test")
    reponse = _connexion(client, "awa@sigaps.test", "mauvais-mot-de-passe")
    assert reponse.status_code == 200
    assert "Adresse e-mail ou mot de passe incorrect." in reponse.content.decode()
    assert not get_user(client).is_authenticated


def test_connexion_echouee_compte_inconnu(client):
    reponse = _connexion(client, "personne@sigaps.test", MOT_DE_PASSE)
    assert reponse.status_code == 200
    assert not get_user(client).is_authenticated


def test_connexion_refusee_pour_un_compte_desactive(client):
    UtilisateurFactory(email="inactif@sigaps.test", is_active=False)
    _connexion(client, "inactif@sigaps.test", MOT_DE_PASSE)
    assert not get_user(client).is_authenticated


def test_blocage_apres_cinq_echecs(client):
    UtilisateurFactory(email="cible@sigaps.test")
    for _ in range(4):
        assert _connexion(client, "cible@sigaps.test", "mauvais").status_code == 200
    # 5e échec : le blocage est déclenché.
    assert _connexion(client, "cible@sigaps.test", "mauvais").status_code == 429
    # Même le bon mot de passe est refusé pendant le blocage, casse comprise.
    reponse = _connexion(client, "CIBLE@sigaps.test", MOT_DE_PASSE)
    assert reponse.status_code == 429
    assert "Connexion temporairement bloquée" in reponse.content.decode()
    assert not get_user(client).is_authenticated


def test_succes_remet_le_compteur_a_zero(client):
    UtilisateurFactory(email="moussa@sigaps.test")
    for _ in range(4):
        _connexion(client, "moussa@sigaps.test", "mauvais")
    assert _connexion(client, "moussa@sigaps.test", MOT_DE_PASSE).status_code == 302
    client.post(reverse("comptes:deconnexion"))
    for _ in range(4):
        assert _connexion(client, "moussa@sigaps.test", "mauvais").status_code == 200


def test_blocage_limite_au_couple_email_ip(client):
    UtilisateurFactory(email="a@sigaps.test")
    UtilisateurFactory(email="b@sigaps.test")
    for _ in range(5):
        _connexion(client, "a@sigaps.test", "mauvais")
    assert _connexion(client, "b@sigaps.test", MOT_DE_PASSE).status_code == 302


def test_deconnexion_en_post(client):
    u = UtilisateurFactory()
    client.force_login(u)
    assert client.get(reverse("comptes:deconnexion")).status_code == 405
    reponse = client.post(reverse("comptes:deconnexion"))
    assert reponse.status_code == 302
    assert not get_user(client).is_authenticated


def _lien_du_dernier_mail():
    return re.search(r"https?://[^/]+(/\S+)", mail.outbox[-1].body).group(1)


def test_mot_de_passe_oublie_et_reinitialisation(client):
    u = UtilisateurFactory(email="fanta@sigaps.test")
    reponse = client.post(reverse("comptes:mot_de_passe_oublie"), {"email": "Fanta@sigaps.test"})
    assert reponse.status_code == 302
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["fanta@sigaps.test"]
    assert "Réinitialisation" in mail.outbox[0].subject

    lien = _lien_du_dernier_mail()
    reponse = client.get(lien, follow=True)  # Django redirige vers l'URL « set-password »
    assert "Choisir un mot de passe" in reponse.content.decode()
    url_formulaire = reponse.redirect_chain[-1][0]
    nouveau = "Nouveau-mot-de-passe-2026"
    reponse = client.post(url_formulaire, {"new_password1": nouveau, "new_password2": nouveau})
    assert reponse.status_code == 302
    u.refresh_from_db()
    assert u.check_password(nouveau)


def test_mot_de_passe_oublie_adresse_inconnue_sans_fuite(client):
    reponse = client.post(reverse("comptes:mot_de_passe_oublie"), {"email": "x@sigaps.test"})
    assert reponse.status_code == 302  # même réponse : on ne révèle pas l'existence du compte
    assert mail.outbox == []


def test_compte_invite_sans_mot_de_passe_peut_demander_un_lien(client):
    Utilisateur.objects.create_user("invite@sigaps.test", None)
    client.post(reverse("comptes:mot_de_passe_oublie"), {"email": "invite@sigaps.test"})
    assert len(mail.outbox) == 1


def test_pages_authentification_en_francais(client):
    for nom in ["comptes:connexion", "comptes:mot_de_passe_oublie"]:
        contenu = client.get(reverse(nom)).content.decode()
        assert '<html lang="fr">' in contenu
    assert "Adresse e-mail" in client.get(URL_CONNEXION).content.decode()

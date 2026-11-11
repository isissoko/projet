"""Fixtures partagées par tous les tests."""

import pytest

from comptes.tests.factories import UtilisateurFactory


@pytest.fixture
def connecter(client):
    """Crée un utilisateur avec les rôles donnés, le connecte et renvoie (client, utilisateur)."""

    def _connecter(*roles, **attributs):
        utilisateur = UtilisateurFactory(roles=list(roles), **attributs)
        client.force_login(utilisateur)
        return client, utilisateur

    return _connecter


@pytest.fixture
def admin_connecte(connecter):
    return connecter("ADMINISTRATEUR")

import pytest
from django.core.management import CommandError, call_command

from comptes.management.commands.creer_admin import Command
from comptes.models import Utilisateur
from comptes.roles import Role

from .factories import UtilisateurFactory

pytestmark = pytest.mark.django_db


def _commande(monkeypatch, saisies, secrets):
    saisies, secrets = iter(saisies), iter(secrets)
    monkeypatch.setattr(Command, "saisir", lambda self, invite: next(saisies))
    monkeypatch.setattr(Command, "saisir_secret", lambda self, invite: next(secrets))


def test_creer_admin_interactif(monkeypatch, capsys):
    _commande(
        monkeypatch,
        ["pas-un-email", "Chef@SIGAPS.test", "Kadiatou", "Diallo"],
        [
            "court",
            "court",  # trop court : refusé par les validateurs
            "Solide-mot-de-passe-1",
            "different",  # confirmation différente : refusée
            "Solide-mot-de-passe-1",
            "Solide-mot-de-passe-1",
        ],
    )
    call_command("creer_admin")
    admin = Utilisateur.objects.get(email="chef@sigaps.test")
    assert admin.a_role(Role.ADMINISTRATEUR)
    assert admin.is_staff and admin.is_superuser
    assert admin.check_password("Solide-mot-de-passe-1")
    assert admin.get_full_name() == "Kadiatou Diallo"
    sortie = capsys.readouterr()
    assert "Adresse e-mail invalide." in sortie.err
    assert "ne correspondent pas" in sortie.err
    assert "Administrateur créé" in sortie.out


def test_creer_admin_avec_options(monkeypatch):
    _commande(monkeypatch, [], ["Solide-mot-de-passe-1", "Solide-mot-de-passe-1"])
    call_command("creer_admin", email="a@sigaps.test", prenom="A", nom="B")
    assert Utilisateur.objects.get(email="a@sigaps.test").a_role(Role.ADMINISTRATEUR)


def test_creer_admin_email_existant(monkeypatch):
    UtilisateurFactory(email="pris@sigaps.test")
    _commande(monkeypatch, [], [])
    with pytest.raises(CommandError, match="existe déjà"):
        call_command("creer_admin", email="Pris@sigaps.test")

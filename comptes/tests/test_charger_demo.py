from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from comptes.management.commands.charger_demo import COMPTES, MOT_DE_PASSE_DEMO
from comptes.models import Utilisateur
from referentiel.models import AnneeAcademique, Filiere, MotCle

pytestmark = pytest.mark.django_db


def test_refuse_hors_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG=False"):
        call_command("charger_demo", stdout=StringIO())
    assert not Utilisateur.objects.exists()


def test_cree_un_compte_par_role(settings):
    settings.DEBUG = True
    call_command("charger_demo", stdout=StringIO())
    assert Utilisateur.objects.count() == len(COMPTES)
    for email, _, _, roles in COMPTES:
        utilisateur = Utilisateur.objects.get(email=email)
        assert utilisateur.check_password(MOT_DE_PASSE_DEMO)
        assert utilisateur.roles == set(roles)
    assert Utilisateur.objects.get(email="admin@sigaps.local").is_superuser
    assert Utilisateur.objects.get(email="etudiant@sigaps.local").profil_etudiant.filiere
    assert AnneeAcademique.objects.get(courante=True).libelle == "2025-2026"


def test_idempotent_et_force(settings):
    settings.DEBUG = False
    call_command("charger_demo", "--force", "--mot-de-passe", "Autre-mdp-2026", stdout=StringIO())
    call_command("charger_demo", "--force", "--mot-de-passe", "Autre-mdp-2026", stdout=StringIO())
    assert Utilisateur.objects.count() == len(COMPTES)
    assert Filiere.objects.count() == 1
    assert MotCle.objects.count() == 6
    assert Utilisateur.objects.get(email="etudiant@sigaps.local").check_password("Autre-mdp-2026")

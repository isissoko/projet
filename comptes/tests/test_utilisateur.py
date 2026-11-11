import pytest
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction

from comptes.models import Utilisateur

from .factories import UtilisateurFactory

pytestmark = pytest.mark.django_db


def test_modele_utilisateur_personnalise():
    assert get_user_model() is Utilisateur
    assert Utilisateur.USERNAME_FIELD == "email"
    assert "username" not in {f.name for f in Utilisateur._meta.get_fields()}


def test_creer_utilisateur_normalise_email():
    u = Utilisateur.objects.create_user("  Awa.Traore@Exemple.ML ", "motdepasse-solide-42")
    assert u.email == "awa.traore@exemple.ml"
    assert u.check_password("motdepasse-solide-42")
    assert not u.is_staff
    assert not u.is_superuser


def test_creer_utilisateur_sans_email_refuse():
    with pytest.raises(ValueError):
        Utilisateur.objects.create_user("", "x")


def test_creer_superutilisateur():
    admin = Utilisateur.objects.create_superuser("admin@sigaps.test", "motdepasse-solide-42")
    assert admin.is_staff
    assert admin.is_superuser


def test_superutilisateur_sans_droits_refuse():
    with pytest.raises(ValueError):
        Utilisateur.objects.create_superuser("a@sigaps.test", "x", is_staff=False)


def test_email_unique():
    UtilisateurFactory(email="moussa@sigaps.test")
    with pytest.raises(IntegrityError), transaction.atomic():
        UtilisateurFactory(email="moussa@sigaps.test")


def test_email_unique_insensible_a_la_casse():
    UtilisateurFactory(email="moussa@sigaps.test")
    with pytest.raises(IntegrityError), transaction.atomic():
        Utilisateur.objects.create_user("MOUSSA@SIGAPS.TEST", "x")


def test_contrainte_base_insensible_a_la_casse():
    """La contrainte en base protège même si la normalisation est contournée."""
    UtilisateurFactory(email="fanta@sigaps.test")
    with pytest.raises(IntegrityError), transaction.atomic():
        Utilisateur.objects.bulk_create([Utilisateur(email="FANTA@sigaps.test")])


def test_connexion_par_email_insensible_a_la_casse(rf):
    UtilisateurFactory(email="kadia@sigaps.test")
    requete = rf.post("/comptes/connexion/")
    assert (
        authenticate(requete, username="Kadia@SIGAPS.test", password="motdepasse-solide-42")
        is not None
    )
    assert authenticate(requete, username="kadia@sigaps.test", password="mauvais") is None


def test_representation_texte():
    u = UtilisateurFactory(first_name="Awa", last_name="Diarra")
    assert str(u) == "Awa Diarra"
    assert str(Utilisateur(email="x@sigaps.test")) == "x@sigaps.test"

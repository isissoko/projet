"""Vérifications du socle : réglages, base PostgreSQL, gabarit de base."""

import pytest
from django.conf import settings
from django.db import connection
from django.urls import reverse
from django.utils import formats, timezone

from config.settings import base


def test_argon2_premier_hasheur_hors_tests():
    assert base.PASSWORD_HASHERS[0] == "django.contrib.auth.hashers.Argon2PasswordHasher"


def test_langue_et_fuseau():
    assert settings.LANGUAGE_CODE == "fr"
    assert settings.TIME_ZONE == "Africa/Bamako"
    assert settings.USE_TZ is True


def test_format_de_date_francais():
    date = timezone.datetime(2026, 10, 25).date()
    assert formats.date_format(date) == "25 octobre 2026"


def test_stockage_prive_sans_url_publique():
    assert settings.STORAGES["prive"]["OPTIONS"]["base_url"] is None
    assert str(settings.STOCKAGE_PRIVE_RACINE) != str(settings.MEDIA_ROOT)


@pytest.mark.django_db
def test_base_postgresql_avec_configuration_french():
    assert connection.vendor == "postgresql"
    with connection.cursor() as curseur:
        curseur.execute("SELECT to_tsvector('french', 'mémoires archivés')::text")
        assert "archiv" in curseur.fetchone()[0]


@pytest.mark.django_db
def test_accueil_accessible(client):
    reponse = client.get(reverse("accueil"))
    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert '<html lang="fr">' in contenu
    assert 'href="#contenu"' in contenu
    assert '<main id="contenu"' in contenu

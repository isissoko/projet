"""Réglages des tests (PostgreSQL obligatoire : recherche plein texte « french »)."""

import os
import tempfile

os.environ.setdefault("SECRET_KEY", "cle-de-test-non-secrete")
os.environ.setdefault("DATABASE_URL", "postgres://sigaps:sigaps@127.0.0.1:5433/sigaps")

from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]

# Hasheur rapide pour accélérer les tests (Argon2 reste le premier en dev et en prod).
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

STOCKAGE_PRIVE_RACINE = Path(tempfile.mkdtemp(prefix="sigaps-prive-"))  # noqa: F405
STORAGES["prive"]["OPTIONS"]["location"] = STOCKAGE_PRIVE_RACINE  # noqa: F405
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="sigaps-media-"))  # noqa: F405

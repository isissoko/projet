"""Réglages de développement."""

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])  # noqa: F405
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

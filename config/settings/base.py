"""Réglages communs à tous les environnements de SIGAPS."""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "axes",
    # Applications SIGAPS
    "referentiel",
    "comptes",
    "productions",
    "bibliotheque",
    "recherche",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "productions.middleware.TransitionInterditeMiddleware",
    # django-axes doit rester le dernier middleware.
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "comptes.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Base de données : PostgreSQL dans tous les environnements.
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)

# Authentification
AUTH_USER_MODEL = "comptes.Utilisateur"
AUTHENTICATION_BACKENDS = [
    # django-axes en premier : il bloque avant toute vérification du mot de passe.
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
LOGIN_URL = "comptes:connexion"
LOGIN_REDIRECT_URL = "accueil"
LOGOUT_REDIRECT_URL = "accueil"
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24 * 3  # 3 jours (vaut aussi pour l'invitation)

# django-axes : blocage après 5 échecs pour un couple (e-mail, adresse IP), pendant 30 minutes.
AXES_FAILURE_LIMIT = 5
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_COOLOFF_TIME = timedelta(minutes=30)
AXES_RESET_ON_SUCCESS = True
AXES_USERNAME_CALLABLE = "comptes.securite.identifiant_axes"
AXES_LOCKOUT_TEMPLATE = "comptes/compte_bloque.html"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalisation
LANGUAGE_CODE = "fr"
LANGUAGES = [("fr", "Français")]
TIME_ZONE = "Africa/Bamako"
USE_I18N = True
USE_TZ = True

# Fichiers statiques (le CSS Tailwind est compilé dans static/css/)
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Stockage : les documents déposés vont dans un stockage privé, sans URL publique.
# Ils ne sont servis que par la vue de téléchargement (contrôle d'accès).
STOCKAGE_PRIVE_RACINE = BASE_DIR / env("STOCKAGE_PRIVE_RACINE", default="prive")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "prive": {
        "BACKEND": "productions.stockage.StockagePrive",
        "OPTIONS": {"location": STOCKAGE_PRIVE_RACINE},
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "media/"

# Téléchargement délégué à Nginx (X-Accel-Redirect) en production, activé par .env.
X_ACCEL_REDIRECT = env.bool("X_ACCEL_REDIRECT", default=False)
X_ACCEL_PREFIXE = env("X_ACCEL_PREFIXE", default="/prive/")

# E-mail
vars().update(env.email_url("EMAIL_URL", default="consolemail://"))
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="SIGAPS <no-reply@sigaps.local>")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sécurité commune
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

#!/usr/bin/env bash
# Installation complète de SIGAPS sur une nouvelle machine (Linux ou macOS), puis lancement.
#
#   scripts/installer.sh                 installe tout, crée un administrateur, lance le serveur
#   scripts/installer.sh --demo          idem avec des comptes de démonstration (un par rôle)
#   scripts/installer.sh --paquets       installe d'abord les paquets système (apt, avec sudo)
#   scripts/installer.sh --sans-lancer   s'arrête après l'installation
#   scripts/installer.sh --port 8002     port du serveur de développement (8001 par défaut)
#
# Le script peut être relancé sans risque : chaque étape déjà faite est conservée.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RACINE"

DEMO=0
PAQUETS=0
LANCER=1
PORT="${PORT:-8001}"
while [ $# -gt 0 ]; do
  case "$1" in
    --demo) DEMO=1 ;;
    --paquets) PAQUETS=1 ;;
    --sans-lancer) LANCER=0 ;;
    --port) PORT="${2:?--port attend un numéro}"; shift ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Option inconnue : $1 (voir --help)" >&2; exit 1 ;;
  esac
  shift
done

etape() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok() { printf '\033[32m    ✓ %s\033[0m\n' "$*"; }
avertir() { printf '\033[33m    ! %s\033[0m\n' "$*"; }
echec() { printf '\033[31m    ✗ %s\033[0m\n' "$*" >&2; exit 1; }
existe() { command -v "$1" >/dev/null 2>&1; }

# 1. Paquets système (facultatif, Debian/Ubuntu) ------------------------------------------
if [ "$PAQUETS" = 1 ]; then
  etape "Installation des paquets système"
  existe apt-get || echec "--paquets ne fonctionne qu'avec apt (Debian, Ubuntu). Installez les prérequis à la main."
  sudo apt-get update
  sudo apt-get install -y python3 python3-venv python3-pip curl git ca-certificates docker.io
  # Le greffon « docker compose » porte un nom différent selon la distribution.
  sudo apt-get install -y docker-compose-v2 || sudo apt-get install -y docker-compose-plugin \
    || avertir "Greffon docker compose introuvable : voir https://docs.docker.com/compose/install/"
  sudo systemctl enable --now docker 2>/dev/null || true
  if ! id -nG "$USER" | grep -qw docker; then
    sudo usermod -aG docker "$USER"
    avertir "Vous avez été ajouté au groupe docker ; il prendra effet à la prochaine session."
  fi
fi

# 2. Prérequis --------------------------------------------------------------------------------
etape "Vérification des prérequis"
PYTHON=""
for candidat in python3.13 python3.12 python3; do
  if existe "$candidat" && "$candidat" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then
    PYTHON="$(command -v "$candidat")"; break
  fi
done
[ -n "$PYTHON" ] || echec "Python 3.12 ou plus récent est requis (Ubuntu 24.04 : sudo apt install python3 python3-venv ; macOS : brew install python@3.12)."
ok "Python : $("$PYTHON" --version)"
"$PYTHON" -c 'import venv, ensurepip' 2>/dev/null \
  || echec "Le module venv manque (Debian/Ubuntu : sudo apt install python3-venv)."

existe curl || echec "curl est requis (téléchargement de Tailwind CSS)."
ok "curl"
existe docker || echec "Docker est requis pour PostgreSQL : https://docs.docker.com/engine/install/ (ou relancez avec --paquets)."

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  if existe sudo && sudo docker info >/dev/null 2>&1; then
    DOCKER=(sudo docker)
    avertir "Docker demande sudo (ajoutez-vous au groupe docker pour l'éviter)."
  else
    echec "Le démon Docker ne répond pas. Démarrez-le (sudo systemctl start docker, ou Docker Desktop)."
  fi
fi
"${DOCKER[@]}" compose version >/dev/null 2>&1 || echec "Le greffon « docker compose » (v2) est requis."
ok "Docker : $("${DOCKER[@]}" compose version --short 2>/dev/null || echo 'compose v2')"

# 3. Environnement Python ---------------------------------------------------------------------
etape "Environnement Python (.venv)"
if [ ! -x .venv/bin/python ]; then
  "$PYTHON" -m venv .venv
  ok "Environnement créé"
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements/dev.txt
ok "Dépendances installées (versions fixées dans requirements/)"

# 4. Fichier .env -----------------------------------------------------------------------------
etape "Configuration (.env)"
if [ ! -f .env ]; then
  CLE="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(50))')"
  sed "s|^SECRET_KEY=.*|SECRET_KEY=$CLE|" .env.example > .env
  chmod 600 .env
  ok ".env créé avec une clé secrète aléatoire"
else
  ok ".env déjà présent : conservé"
fi
PORT_DB="$(sed -n 's|^DATABASE_URL=.*:\([0-9]\{2,5\}\)/.*|\1|p' .env)"
PORT_DB="${PORT_DB:-5433}"

# 5. PostgreSQL ---------------------------------------------------------------------------------
etape "Base de données PostgreSQL (docker compose, port $PORT_DB)"
if ! "${DOCKER[@]}" compose ps --status running --services 2>/dev/null | grep -qx db; then
  if (exec 3<>"/dev/tcp/127.0.0.1/$PORT_DB") 2>/dev/null; then
    echec "Le port $PORT_DB est déjà occupé par un autre service. Changez le port dans docker-compose.yml et DATABASE_URL (.env)."
  fi
fi
"${DOCKER[@]}" compose up -d --wait db
ok "PostgreSQL prêt"

# 6. Migrations, CSS, contrôle ------------------------------------------------------------------
etape "Migrations"
.venv/bin/python manage.py migrate --no-input
ok "Schéma à jour"

etape "Feuille de style (Tailwind CSS, binaire autonome, sans Node.js)"
scripts/tailwind.sh build
ok "static/css/sigaps.css compilé"

etape "Vérification de la configuration Django"
.venv/bin/python manage.py check
ok "Aucun problème détecté"

# 7. Comptes ----------------------------------------------------------------------------------------
etape "Comptes"
if [ "$DEMO" = 1 ]; then
  .venv/bin/python manage.py charger_demo
else
  NB_ADMINS="$(.venv/bin/python manage.py shell -v0 -c \
    'from comptes.models import Utilisateur; print(Utilisateur.objects.filter(is_superuser=True).count())')"
  if [ "$NB_ADMINS" = 0 ]; then
    if [ -t 0 ]; then
      echo "    Création du premier administrateur :"
      .venv/bin/python manage.py creer_admin
    else
      avertir "Aucun administrateur : lancez « .venv/bin/python manage.py creer_admin » (ou --demo)."
    fi
  else
    ok "Administrateur déjà présent"
  fi
fi

# 8. Lancement ----------------------------------------------------------------------------------------
etape "Installation terminée"
echo "    Lancer plus tard : scripts/lancer.sh   (tests : make test)"
if [ "$LANCER" = 1 ]; then
  echo "    Serveur : http://127.0.0.1:$PORT/   (Ctrl+C pour arrêter)"
  exec .venv/bin/python manage.py runserver "127.0.0.1:$PORT"
fi

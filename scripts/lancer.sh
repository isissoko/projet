#!/usr/bin/env bash
# Lancement quotidien de SIGAPS (après scripts/installer.sh) : démarre PostgreSQL,
# applique les migrations en attente, compile le CSS s'il manque, lance le serveur.
#
#   scripts/lancer.sh              serveur sur http://127.0.0.1:8001/
#   scripts/lancer.sh --port 8002
#   scripts/lancer.sh --css        recompile le CSS à chaque modification (en parallèle)
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RACINE"

PORT="${PORT:-8001}"
CSS_WATCH=0
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="${2:?--port attend un numéro}"; shift ;;
    --css) CSS_WATCH=1 ;;
    -h|--help) sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Option inconnue : $1 (voir --help)" >&2; exit 1 ;;
  esac
  shift
done

if [ ! -x .venv/bin/python ] || [ ! -f .env ]; then
  echo "SIGAPS n'est pas installé : lancez d'abord scripts/installer.sh" >&2
  exit 1
fi

DOCKER=(docker)
docker info >/dev/null 2>&1 || DOCKER=(sudo docker)
"${DOCKER[@]}" compose up -d --wait db
.venv/bin/python manage.py migrate --no-input
[ -f static/css/sigaps.css ] || scripts/tailwind.sh build

if [ "$CSS_WATCH" = 1 ]; then
  scripts/tailwind.sh watch &
  trap 'kill $! 2>/dev/null || true' EXIT
fi

echo "Serveur : http://127.0.0.1:$PORT/   (Ctrl+C pour arrêter)"
.venv/bin/python manage.py runserver "127.0.0.1:$PORT"

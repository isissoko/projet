#!/usr/bin/env bash
# Télécharge (si besoin) le binaire autonome Tailwind CSS v4 puis compile le CSS.
# Aucune dépendance Node.js. Usage : scripts/tailwind.sh [build|watch]
set -euo pipefail

VERSION="v4.3.3"
RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BINAIRE="$RACINE/bin/tailwindcss-$VERSION"
ENTREE="$RACINE/static/src/input.css"
SORTIE="$RACINE/static/css/sigaps.css"

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) CIBLE="linux-x64" ;;
  Linux-aarch64) CIBLE="linux-arm64" ;;
  Darwin-arm64) CIBLE="macos-arm64" ;;
  Darwin-x86_64) CIBLE="macos-x64" ;;
  *) echo "Plateforme non prise en charge : $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

if [ ! -x "$BINAIRE" ]; then
  mkdir -p "$RACINE/bin"
  BASE_URL="https://github.com/tailwindlabs/tailwindcss/releases/download/$VERSION"
  # Téléchargement partiel conservé dans bin/ : une connexion lente peut reprendre où elle s'est arrêtée.
  TMP="$RACINE/bin/telechargement-$VERSION"
  mkdir -p "$TMP"
  echo "Téléchargement de Tailwind CSS $VERSION ($CIBLE)…"
  curl -fL --retry 10 --retry-all-errors --retry-delay 3 -C - \
    -o "$TMP/tailwindcss-$CIBLE" "$BASE_URL/tailwindcss-$CIBLE"
  curl -fsSL --retry 5 --retry-all-errors -o "$TMP/sha256sums.txt" "$BASE_URL/sha256sums.txt"
  if command -v sha256sum >/dev/null 2>&1; then SHA=(sha256sum); else SHA=(shasum -a 256); fi
  (cd "$TMP" && grep " \(\./\)\?tailwindcss-$CIBLE\$" sha256sums.txt | sed 's# \./# #' | "${SHA[@]}" -c -)
  install -m 0755 "$TMP/tailwindcss-$CIBLE" "$BINAIRE"
fi

mkdir -p "$(dirname "$SORTIE")"
case "${1:-build}" in
  build) "$BINAIRE" -i "$ENTREE" -o "$SORTIE" --minify ;;
  watch) "$BINAIRE" -i "$ENTREE" -o "$SORTIE" --watch ;;
  *) echo "Usage : $0 [build|watch]" >&2; exit 1 ;;
esac

#!/usr/bin/env bash
# Lance une commande du dépôt dans le conteneur du banc (étape 8), image d'un commit.
#
#   bash 09_outillage/scripts/lancer_conteneur.sh <réseau> <commande...>    (par make conteneur)
#
# Réseau :
#   aucun   : témoins, tests, rapports, rejeu du gardien ; aucun accès au réseau ;
#   api     : runs dont les modèles sont servis par une API (DeepSeek, juge, simulateur de
#             τ²-bench) ;
#   machine : runs de Qwen servi par make qwen sur 127.0.0.1:30100, le réseau de la machine, sans
#             toucher aux configurations des candidats. Le conteneur voit alors tout ce qui écoute
#             sur 127.0.0.1, dont le serveur de Nimeria (port 30000) quand il tourne.
#
# Image : poa-banc:<commit>, COMMIT=HEAD par défaut, construite d'abord par make image.
# Monté : 99_local/ en écriture ; le .env en lecture seule, comme fichier, jamais versé dans
# l'environnement du conteneur (un candidat hérite de tout l'environnement d'EASE) ;
# 07_taches/prive/ en lecture seule, s'il existe. Les fichiers écrits appartiennent à qui lance.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

if [ $# -lt 2 ]; then
  echo "Usage : make conteneur RESEAU=aucun|api|machine COMMANDE=\"make temoins\" [COMMIT=HEAD]" >&2
  exit 2
fi
RESEAU="$1"
shift
case "$RESEAU" in
  aucun) SERVICE=hors-ligne ;;
  api) SERVICE=api ;;
  machine) SERVICE=machine ;;
  *) echo "Réseau inconnu : $RESEAU (aucun, api ou machine)" >&2; exit 2 ;;
esac

COMPLET="$(git rev-parse "${COMMIT:-HEAD}^{commit}")"
COMMIT="${COMPLET:0:12}"
if ! docker image inspect "poa-banc:$COMMIT" > /dev/null 2>&1; then
  echo "Image poa-banc:$COMMIT absente : la construire d'abord, make image COMMIT=$COMMIT" >&2
  exit 3
fi

# Créé ici, sinon Docker le créerait au nom de root.
mkdir -p 99_local
VOLUMES=()
if [ -f .env ]; then VOLUMES+=(--volume "$PWD/.env:/poa/.env:ro"); fi
if [ -d 07_taches/prive ]; then
  VOLUMES+=(--volume "$PWD/07_taches/prive:/poa/07_taches/prive:ro")
fi

POA_COMMIT="$COMMIT" POA_UID="$(id -u)" POA_GID="$(id -g)" \
  exec docker compose --file 10_deploiement/compose.yaml run --rm "${VOLUMES[@]}" "$SERVICE" "$@"

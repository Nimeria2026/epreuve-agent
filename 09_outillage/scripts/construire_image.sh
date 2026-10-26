#!/usr/bin/env bash
# Construit l'image du banc (étape 8) depuis l'archive git d'un commit. Seuls les fichiers suivis
# entrent dans le contexte : jamais 07_taches/prive/, le .env ni 99_local/. L'image porte le
# commit dans son étiquette, poa-banc:<commit>, et reste figée sur lui comme le poste de mesure.
#
#   bash 09_outillage/scripts/construire_image.sh [COMMIT]    (défaut : HEAD)
#   make image [COMMIT=...] [POA_CA=<certificat d'un proxy qui déchiffre le TLS>]
#
# Les modifications non commitées n'entrent pas dans l'image.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

COMPLET="$(git rev-parse "${1:-HEAD}^{commit}")"
IMAGE="poa-banc:${COMPLET:0:12}"

# Derrière un proxy qui déchiffre le TLS : POA_CA=<certificat>, passé en secret de construction.
SECRET=()
if [ -n "${POA_CA:-}" ]; then SECRET=(--secret "id=ca,src=$POA_CA"); fi

git archive --format=tar "$COMPLET" \
  | docker build --file 10_deploiement/images/banc.dockerfile --build-arg COMMIT="$COMPLET" \
      "${SECRET[@]}" --tag "$IMAGE" -
echo "Image construite : $IMAGE"

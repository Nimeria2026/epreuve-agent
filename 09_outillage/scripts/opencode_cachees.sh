#!/usr/bin/env bash
# La séance des tâches cachées sous opencode, sur Flash-Next servi par Strata sur ce poste : l'agent
# « cachees » d'opencode.json (ADR 0011 ; JOURNAL, entrées 306 et 307). Rien ne sort du poste.
#
#   make opencode-cachees       (Strata lancé avant par make strata, dans un autre terminal)
#
# opencode 2 sert ses séances par un service en arrière-plan, qui ne voit pas l'environnement de ce
# terminal : la séance a son propre serveur (--standalone), seul à recevoir la clé de Strata, lue
# dans .env ; aucune autre clé. Dans opencode, la touche Tab mène à l'agent cachees.
# Les autres modèles admis pour les tâches cachées ont leur agent (cachees-go) et se lancent par
# un simple opencode, sans ce script.
# Codes de refus : 2 opencode ou la clé introuvable, 3 Strata ne répond pas, 4 un run tourne.
set -euo pipefail
cd "$(dirname "$0")/../.."

command -v opencode >/dev/null || { echo "REFUS : opencode introuvable." >&2; exit 2; }
CLE="$(sed -n 's/^STRATA_API_KEY=//p' .env 2>/dev/null | head -1 | tr -d '"'"'")"
[ -n "$CLE" ] || { echo "REFUS : STRATA_API_KEY absente du .env." >&2; exit 2; }

# Un run de mesure sur la carte se partagerait Strata avec la séance et fausserait ses durées.
if pgrep -f 'ease\.(mesure|mesure_tau2|publier)' >/dev/null; then
  echo "REFUS : un run tourne ; la carte n'en sert qu'un à la fois. Attendre sa fin." >&2
  exit 4
fi

CODE="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $CLE" \
  http://127.0.0.1:30001/v1/models || true)"
if [ "$CODE" != "200" ]; then
  echo "REFUS : Strata ne répond pas sur 127.0.0.1:30001 (code ${CODE:-aucun})." >&2
  echo "  Le lancer d'abord, dans un autre terminal : make strata" >&2
  exit 3
fi

echo "Séance des tâches cachées sur Flash-Next : dans opencode, Tab jusqu'à l'agent cachees."
STRATA_API_KEY="$CLE" exec opencode --standalone

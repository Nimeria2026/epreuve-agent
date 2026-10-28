#!/usr/bin/env bash
# Sert Qwen3.8-Flash-Next (IQ3_S) par Strata, en local, pour les candidats *_qwen_flash_next_strata.
#
# Seul domicile de cette commande dans le dépôt (AGENTS.md, « Ajouter un modèle » ; JOURNAL, entrées 287 et 296). Sa fiche
# officielle : 02_ease/src/ease/moteurs/strata_flash_next.md. Elle lance le préréglage « flash-next »
# de Strata, celui de l'essai du 2026-10-25, par strata launch ; Strata exécute alors son moteur, dont
# la commande interne s'écrit dans ~/.local/state/strata/launch/flash-next.engine.log. Les choix qui comptent pour la mesure sont redits ici, pour qu'un préréglage
# modifié ne change rien sans se voir : contexte de 131 072 jetons, images coupées, cache int8, MTP,
# trois créneaux (le préréglage dit « fit to card », trois le 2026-10-25), cet ordinateur seul,
# port 30001, clé d'API du préréglage (celle de STRATA_API_KEY dans le .env).
#
#   bash 09_outillage/scripts/servir_strata.sh            # le plan de Strata, sans rien lancer
#   bash 09_outillage/scripts/servir_strata.sh --lancer   # le lance, avec le moniteur de Strata au premier plan
#   strata launch --status                                # ce qui tourne
#   strata launch --stop --preset flash-next              # l'arrêter
#
# Un run à la fois : en parallèle, l'essai du 2026-10-25 a manqué de mémoire et reçu des refus HTTP 503.
# Codes de refus : 2 programme introuvable, 4 carte déjà occupée, 5 port déjà pris, 6 Strata ou son
# préréglage différents de leur fiche (02_ease/src/ease/moteurs/strata_flash_next.md), 7 mémoire vive
# insuffisante.
set -euo pipefail

STRATA="${POA_STRATA:-strata}"
PRESET=flash-next
PORT=30001
MEMOIRE_LIBRE_MIN_MIO=23000  # relevé du 2026-10-25 : le moteur occupe 23 803 Mio de la carte
# Le moteur réserve une zone de 46 Gio de mémoire vive pour les experts, et son réglage du 2026-10-24
# a culminé à 50 125 Mio. Le 2026-10-26, avec 41,3 Gio disponibles, il s'est arrêté pendant le
# chargement (JOURNAL, entrée 297).
VIVE_LIBRE_MIN_MIO=51200

CHOIX=(
  --preset "$PRESET"
  --context 131072
  --vision off
  --kv int8
  --drafting mtp
  --parallel 3
  --access local
  --port "$PORT"
)

command -v "$STRATA" >/dev/null 2>&1 || { echo "REFUS : programme introuvable : $STRATA (POA_STRATA)" >&2; exit 2; }
# Garde 0 : Strata et son préréglage tels que les dit la fiche (02_ease/src/ease/moteurs/).
python3 "$(dirname "$0")/verifier_strata.py" || exit 6
"$STRATA" launch "${CHOIX[@]}" --plan

if [ "${1:-}" != "--lancer" ]; then
  echo
  echo "(rien lancé : ajouter --lancer pour exécuter)"
  exit 0
fi

# Garde 1 : la carte doit être libre ; un autre modèle chargé ferait échouer le démarrage, ou
# mesurer sous une mémoire amputée.
LIBRE="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1 | tr -d ' ')"
if [ "${LIBRE:-0}" -lt "$MEMOIRE_LIBRE_MIN_MIO" ]; then
  echo "REFUS : ${LIBRE:-?} Mio libres sur la carte, il en faut $MEMOIRE_LIBRE_MIN_MIO." >&2
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader | sed 's/^/    /' >&2
  echo "  Arrête-les toi-même avant de relancer (make qwen tourne-t-il ?)." >&2
  exit 4
fi

# Garde 2 : la mémoire vive disponible doit tenir la zone des experts.
VIVE="$(awk '/^MemAvailable:/ {print int($2 / 1024)}' /proc/meminfo)"
if [ "${VIVE:-0}" -lt "$VIVE_LIBRE_MIN_MIO" ]; then
  echo "REFUS : ${VIVE:-?} Mio de mémoire vive disponibles, il en faut $VIVE_LIBRE_MIN_MIO." >&2
  echo "  Ce qui en prend le plus :" >&2
  ps -eo rss=,comm= --sort=-rss | head -8 | awk '{printf "    %6d Mio  %s\n", $1 / 1024, $2}' >&2
  echo "  Ferme ce qui peut l'être (navigateur, autres modèles, conteneurs), puis relance." >&2
  exit 7
fi

# Garde 3 : un serveur déjà debout sur le port ferait mesurer une autre configuration.
if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$PORT" 2>/dev/null | grep -q LISTEN; then
  echo "REFUS : quelque chose écoute déjà sur le port $PORT (strata launch --status)." >&2
  exit 5
fi

# Avertissement : systemd-oomd ferme tout le terminal quand la pression sur la mémoire de la session
# dépasse 50 % pendant 20 s ; le chargement du moteur l'a déclenché le 2026-10-26 (JOURNAL, entrée
# 298). Ce n'est pas un refus : le 2026-10-25, Strata a tourné avec lui.
if systemctl is-active --quiet systemd-oomd 2>/dev/null; then
  echo "ATTENTION : systemd-oomd est actif ; il peut fermer ce terminal pendant le chargement ou les runs." >&2
  echo "  Pour les mesures : sudo systemctl stop systemd-oomd ; après : sudo systemctl start systemd-oomd" >&2
fi

# Au premier plan, avec le moniteur de Strata, comme le 2026-10-25, dans un terminal à part : le
# serveur se lit sur http://127.0.0.1:$PORT/v1, et le terminal montre ce que fait le moteur.
echo "Strata va servir $PRESET sur http://127.0.0.1:$PORT/v1 ; arrêt : strata launch --stop --preset $PRESET"
exec "$STRATA" launch "${CHOIX[@]}"

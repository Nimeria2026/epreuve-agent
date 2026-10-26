#!/usr/bin/env bash
# Sert Qwen 3.8 Flash-Next (IQ3_S) par le moteur Strata, en local, pour les candidats *_strata.
#
# Seul domicile de cette commande dans le dépôt (ADR 0008 ; JOURNAL, entrée 287). Elle reprend celle
# qu'opencode a relevée le 2026-10-25 dans le journal du moteur (flash-next.engine.log), préréglage
# flash-next : cache int8, trois créneaux (--batch 3), décodage spéculatif (spec 4, min-p 0,5, MTP),
# contexte de 131 072 jetons. L'hôte et le port, 127.0.0.1:30001, sont ceux que ce journal donnait :
# la commande ne les fixe pas, Strata les prend de son préréglage.
#
#   bash 09_outillage/scripts/servir_strata.sh            # affiche la commande, ne lance rien
#   bash 09_outillage/scripts/servir_strata.sh --lancer   # la lance, au premier plan (Ctrl-C pour arrêter)
#
# Chemins réglables pour une autre machine : POA_STRATA (le programme), POA_STRATA_MODELES (packs,
# modèles et MTP), POA_STRATA_PROFIL (profil des experts).
# Un run à la fois : en parallèle, l'essai du 2026-10-25 a manqué de mémoire et reçu des refus HTTP 503.
# Codes de refus : 2 programme ou modèle introuvable, 4 carte déjà occupée, 5 port déjà pris.
set -euo pipefail

STRATA="${POA_STRATA:-strata}"
MODELES="${POA_STRATA_MODELES:-$HOME/Modeles/strata}"
PROFIL="${POA_STRATA_PROFIL:-$HOME/.local/share/strata/terminal/0.1.49.2/data/expert-profile.bin}"
PORT=30001
MEMOIRE_LIBRE_MIN_MIO=23000  # relevé du 2026-10-25 : le moteur occupe 23 803 Mio de la carte
NATIF="$MODELES/models/IQ3_S/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf"
PLE="$MODELES/models/IQ3_S/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf"

COMMANDE=(
  "$STRATA" --serve
  --pack "$MODELES/packs/iq3_s"
  --native "$NATIF"
  --ple-gguf "$PLE"
  --expert-profile "$PROFIL"
  --expert-cache auto
  --prefill auto
  --spec 4
  --spec-min-p 0.5
  --mtp "$MODELES/mtp/rt"
  --max-context 131072
  --kv int8
  --batch 3
)

echo "COMMANDE (port $PORT attendu, contexte de 131 072 jetons) :"
printf '  %s\n' "${COMMANDE[*]}"

if [ "${1:-}" != "--lancer" ]; then
  echo
  echo "(rien lancé : ajouter --lancer pour exécuter)"
  exit 0
fi

command -v "$STRATA" >/dev/null 2>&1 || { echo "REFUS : programme introuvable : $STRATA (POA_STRATA)" >&2; exit 2; }
for fichier in "$NATIF" "$PLE" "$PROFIL"; do
  [ -f "$fichier" ] || { echo "REFUS : fichier introuvable : $fichier" >&2; exit 2; }
done

# Garde 1 : la carte doit être libre ; un autre modèle chargé ferait échouer le démarrage, ou
# mesurer sous une mémoire amputée.
LIBRE="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1 | tr -d ' ')"
if [ "${LIBRE:-0}" -lt "$MEMOIRE_LIBRE_MIN_MIO" ]; then
  echo "REFUS : ${LIBRE:-?} Mio libres sur la carte, il en faut $MEMOIRE_LIBRE_MIN_MIO." >&2
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader | sed 's/^/    /' >&2
  echo "  Arrête-les toi-même avant de relancer (make qwen tourne-t-il ?)." >&2
  exit 4
fi

# Garde 2 : un serveur déjà debout sur le port ferait mesurer une autre configuration.
if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$PORT" 2>/dev/null | grep -q LISTEN; then
  echo "REFUS : quelque chose écoute déjà sur le port $PORT." >&2
  exit 5
fi

exec "${COMMANDE[@]}"

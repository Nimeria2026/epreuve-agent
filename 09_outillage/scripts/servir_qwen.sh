#!/usr/bin/env bash
# Sert Qwen 3.8 27B (W4A16) pour l'agent de l'étape 3, en local, sur le port 30100.
#
# Seul domicile de cette commande dans le dépôt. Les réglages de mémoire viennent de la commande
# de production de Nimeria (module_fds/moteur/serveur/VLLM.md, version du 30/09/2026), éprouvée
# sur la RTX 3090 d'Alexandre. Différences, toutes pour l'agent :
#   - appels d'outils : --enable-auto-tool-choice --tool-call-parser qwen3_xml ;
#   - raisonnement séparé de la réponse : --reasoning-parser qwen3 ;
#   - raisonnement laissé actif, réglage de l'éditeur (Nimeria le coupe pour son extraction) ;
#   - port 30100 et écoute sur 127.0.0.1 seulement : jamais de confusion avec le serveur de
#     Nimeria (30000), et rien d'ouvert au réseau.
# Réglages relevés et sources : 00_docs/sources/2026-10-05_reglages_des_modeles.md.
#
#   bash 09_outillage/scripts/servir_qwen.sh            # affiche la commande, ne lance rien
#   bash 09_outillage/scripts/servir_qwen.sh --lancer   # la lance, au premier plan (Ctrl-C pour arrêter)
#
# Chemins réglables pour une autre machine : POA_QWEN_MODELE, POA_VLLM_VENV.
# Contexte : POA_QWEN_CONTEXTE, 102 400 jetons par défaut, celui du Qwen des publications
# (agent_seul_qwen_local_100k ; JOURNAL, deux-cent-vingt-sixième entrée). Les candidats d'avant le
# demandent plus petit (make qwen CONTEXTE=40960). Le cache de 4,4 Go tient 105 503 jetons : au-delà,
# vLLM refuse de démarrer. Chaque candidat vérifie le contexte annoncé avant son run.
# Codes de refus : 2 modèle ou vLLM introuvable, 4 carte déjà occupée, 5 port déjà pris.
set -euo pipefail

MODELE="${POA_QWEN_MODELE:-$HOME/modeles/Qwen3.8-27B-W4A16-AutoRound}"
VENV="${POA_VLLM_VENV:-$HOME/venv-vllm}"
PORT=30100
CONTEXTE="${POA_QWEN_CONTEXTE:-102400}"
MEMOIRE_LIBRE_MIN_MIO=22000  # le serveur réserve 95 % de la carte

COMMANDE=(
  "$VENV/bin/vllm" serve "$MODELE"
  --served-model-name qwen3.8-27b-w4a16
  --language-model-only
  --max-model-len "$CONTEXTE" --kv-cache-memory 4400000000 --max-num-seqs 64
  --gpu-memory-utilization 0.95 --kv-cache-dtype fp8
  --enable-prefix-caching
  --host 127.0.0.1 --port "$PORT"
  --enable-auto-tool-choice --tool-call-parser qwen3_xml
  --reasoning-parser qwen3
)

echo "COMMANDE (port $PORT, contexte de $CONTEXTE jetons) :"
echo "  PATH=$VENV/bin:\$PATH PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True VLLM_USE_FLASHINFER_SAMPLER=0 \\"
printf '  %s\n' "${COMMANDE[*]}"

if [ "${1:-}" != "--lancer" ]; then
  echo
  echo "(rien lancé : ajouter --lancer pour exécuter)"
  exit 0
fi

[ -d "$MODELE" ] || { echo "REFUS : modèle introuvable : $MODELE (POA_QWEN_MODELE)" >&2; exit 2; }
[ -x "$VENV/bin/vllm" ] || { echo "REFUS : vLLM introuvable : $VENV/bin/vllm (POA_VLLM_VENV)" >&2; exit 2; }

# Garde 1 : la carte doit être libre. Le serveur de Nimeria (cqfds-vllm) ou un autre modèle
# déjà chargé ferait échouer le démarrage, ou pire, mesurer sous une mémoire amputée.
LIBRE="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1 | tr -d ' ')"
if [ "${LIBRE:-0}" -lt "$MEMOIRE_LIBRE_MIN_MIO" ]; then
  echo "REFUS : ${LIBRE:-?} Mio libres sur la carte, il en faut $MEMOIRE_LIBRE_MIN_MIO." >&2
  echo "  Ce qui l'occupe :" >&2
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader | sed 's/^/    /' >&2
  echo "  Arrête-les toi-même avant de relancer (par exemple : sudo systemctl stop cqfds-vllm)." >&2
  exit 4
fi

# Garde 2 : un serveur déjà debout sur le port ferait mesurer une autre configuration.
if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$PORT" 2>/dev/null | grep -q LISTEN; then
  echo "REFUS : quelque chose écoute déjà sur le port $PORT." >&2
  exit 5
fi

# Le dossier bin de l'environnement de vLLM passe en tête du PATH, comme dans la commande de
# Nimeria : FlashInfer y cherche `ninja` pour compiler ses noyaux au premier démarrage. Sans
# lui, le moteur meurt pendant la capture des graphes CUDA (« No such file or directory:
# 'ninja' », constaté le 2026-10-05).
export PATH="$VENV/bin:$PATH"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export VLLM_USE_FLASHINFER_SAMPLER=0
exec "${COMMANDE[@]}"

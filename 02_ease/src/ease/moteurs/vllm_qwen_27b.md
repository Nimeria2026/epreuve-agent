# Fiche du moteur : vLLM, Qwen 3.8 27B (W4A16)

Fiche officielle du serveur de modèle des candidats `agent_seul_qwen_local`,
`agent_seul_qwen_local_100k`, `auteur_relecteur_qwen_local`, `reproduction_tau2_qwen_local` et
`reproduction_tau2_qwen_local_100k`, dont la référence locale du constat v1. Relevée le 2026-10-26
sur le poste de mesure, en lecture seule : versions de l'environnement de vLLM, fichiers du modèle
et leurs métadonnées de téléchargement, `nvidia-smi` (JOURNAL, entrée 301). Le premier démarrage,
le 2026-10-05, est dans `00_docs/sources/2026-10-05_reglages_des_modeles.md`. Ce que `make qwen`
compare avant de lancer est à côté : `vllm_qwen_27b.json`.

## Le modèle

- Qwen 3.8 27B (`Qwen/Qwen3.8-27B`), quantifié en W4A16 par Intel AutoRound : poids en entiers de
  4 bits, par groupes de 128, symétriques ; activations en BF16. Format compressed-tensors
  (`pack-quantized`), que vLLM sert par le noyau Marlin sur une carte Ampere. Restent en BF16,
  d'après la carte du modèle : `in_proj_a` et `in_proj_b` de l'attention linéaire, la tour de
  vision, la tête MTP et `lm_head`.
- Architecture, d'après la carte du modèle : 64 couches, 48 d'attention linéaire (GatedDeltaNet) et
  16 d'attention complète, une tour de vision, 262K jetons de contexte. `config.json` :
  `Qwen3_5ForConditionalGeneration`, type `qwen3_5`.
- Origine : `dbirks/Qwen3.8-27B-W4A16-AutoRound` sur Hugging Face, révision
  `1f05c441c4e64ae0549de44fa9ea5a6d43610314`, téléchargée le 2026-08-18 dans
  `~/modeles/Qwen3.8-27B-W4A16-AutoRound`. La source du 2026-10-05 laissait l'origine à « ? » : les
  métadonnées de chaque fichier et le cache de Hugging Face donnent ce dépôt et cette révision.
- Poids : 8 fichiers `.safetensors`, 19 452 780 008 octets (18,12 Gio). Leurs empreintes SHA-256,
  telles que Hugging Face les annonce, sont dans `vllm_qwen_27b.json`.
- Réglages livrés (`generation_config.json`) : échantillonnage actif, température 1,0, top_p 0,95,
  top_k 20.

## L'environnement et la machine

- `~/venv-vllm`, le même environnement que le serveur de Nimeria (`cqfds-vllm`) : Python 3.12.3,
  vLLM 0.27.1, torch 2.13.0 (CUDA 13.0), transformers 5.15.0, flashinfer-python 0.6.16.post3,
  triton 3.7.1, compressed-tensors 0.17.0.
- Boîte à outils CUDA 13.0 (V13.0.88), `/usr/local/cuda` menant à `/usr/local/cuda-13.0` :
  FlashInfer y trouve `nvcc` pour compiler ses noyaux au premier démarrage.
- Machine : AMD Ryzen 9 7950X3D, 60 Gio de mémoire vive (relevés le même jour pour la fiche de
  Strata) ; NVIDIA GeForce RTX 3090, 24 576 Mio, pilote 595.99.02, puissance limitée à 250 W pour
  350 W par défaut ; noyau Linux 7.0.0-34, Ubuntu 24.04.5.

## La commande

Écrite dans `09_outillage/scripts/servir_qwen.sh`, et nulle part ailleurs :

```
PATH=~/venv-vllm/bin:$PATH PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True VLLM_USE_FLASHINFER_SAMPLER=0 \
~/venv-vllm/bin/vllm serve ~/modeles/Qwen3.8-27B-W4A16-AutoRound \
  --served-model-name qwen3.8-27b-w4a16 --language-model-only \
  --max-model-len 102400 --kv-cache-memory 4400000000 --max-num-seqs 64 \
  --gpu-memory-utilization 0.95 --kv-cache-dtype fp8 --enable-prefix-caching \
  --host 127.0.0.1 --port 30100 \
  --enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3
```

- `--language-model-only` laisse la tour de vision de côté. La tête MTP n'est pas servie : aucune
  option de prédiction de plusieurs jetons (gardée pour plus tard, JOURNAL, entrée 120).
- Le cache de 4,4 Go en FP8 tient 105 503 jetons : au premier démarrage, le modèle a pris 16,59 Gio
  et le cache 4,1 Gio. Le contexte est de 102 400 jetons pour les candidats `_100k`, ceux des
  publications, et de 40 960 pour les candidats d'avant (`make qwen CONTEXTE=40960`).
- Les réglages de mémoire viennent de la commande de production de Nimeria ; s'y ajoutent l'appel
  d'outils, l'analyse du raisonnement, laissé actif, et l'écoute sur 127.0.0.1 seulement.

## Lancer, vérifier, arrêter

```
make qwen                    # vérifie, puis sert Qwen au premier plan, 102 400 jetons
make qwen CONTEXTE=40960     # pour les candidats d'avant
python3 09_outillage/scripts/verifier_qwen.py --modele ~/modeles/Qwen3.8-27B-W4A16-AutoRound \
  --venv ~/venv-vllm --empreintes   # recalcule aussi les poids, quelques minutes
```

Le serveur est prêt quand son journal dit « Application startup complete » ; Ctrl-C l'arrête.
`make qwen` refuse avant de lancer :

- un modèle ou un vLLM introuvables (code 2) ;
- un paquet de l'environnement dans une autre version que la fiche, un fichier du modèle absent,
  d'une autre révision, d'une autre taille, ou un petit fichier au contenu changé (configuration,
  modèle de conversation, jetons) (code 6, `09_outillage/scripts/verifier_qwen.py`) ;
- une carte qui n'a pas 22 000 Mio libres (code 4), un port 30100 déjà pris (code 5).

Au départ de chaque run, EASE lit `/version` et refuse un serveur dont `/v1/models` n'annonce pas le
contexte qu'attend le candidat (code 3).

## Ce que les runs en gardent

- La fiche de chaque run reprend la machine de la déclaration du candidat (« vLLM 0.27.1, contexte
  de 102 400 jetons »), pas un relevé du moment. La version que rend `/version` s'affiche au départ
  du run, sans s'écrire dans sa fiche.
- L'empreinte des consignes compte la configuration de l'agent, pas cette fiche ni
  `vllm_qwen_27b.json`. Ce fichier n'est pas un export des réglages du moteur, qui sont dans la
  commande, mais un relevé de versions ; l'ajouter à l'empreinte séparerait les runs déjà faits des
  suivants.
- L'électricité relevée est celle de la carte seule.

## Limites

- Ce relevé suit les runs du constat v1. vLLM 0.27.1 est attesté par `/version` le 2026-10-05 et le
  2026-10-26 ; les autres paquets ne sont relevés que le 2026-10-26. Le pilote de la carte a changé
  entre-temps, à une date inconnue : 595.91.07 le 2026-09-28 dans les notes de Nimeria, 595.99.02 le
  2026-10-26.
- L'environnement est partagé avec Nimeria : une mise à jour faite pour lui arrête `make qwen`
  (code 6) jusqu'à un nouveau relevé et une fiche nouvelle.
- À chaque lancement, les poids ne sont comparés que par leur taille et leur révision ; leur contenu
  ne se recalcule qu'avec `--empreintes`.
- L'agent n'envoie aucun réglage d'échantillonnage (`parametres: {}`) : ce que vLLM applique alors
  n'est pas relevé. Sur τ²-bench, la configuration fixe la température à 0.
- Les déclarations écrivent le processeur « ? » : le corriger changerait la machine de leurs runs à
  venir, que le rapport compare à celle des runs déjà faits avant de les assembler.
- Un défaut ouvert de l'analyseur Qwen3 de vLLM (issue 58147) peut changer en appel d'outil réel une
  balise d'appel que le modèle cite dans son texte ; rare d'ordinaire, d'après la source du
  2026-10-05.
- vLLM 0.27.1 rend le raisonnement dans le champ `reasoning`, et non `reasoning_content` comme
  DeepSeek.

# 10_deploiement

Le banc de l'Épreuve d'agent en conteneur, pour le relancer sur une autre machine (étape 8) :
EASE, la PME, le gardien, EKE et τ²-bench dans une seule image, lancés comme sur le poste, en
stdio. Le modèle reste dehors : un fournisseur par son API, ou Qwen 3.8 27B servi par `make qwen`
sur la machine. Cadrage et décisions : `00_docs/sources/2026-10-11_cadrage_etape8.md` (JOURNAL,
cent-seizième entrée).

Entrées permises : `README.md`, `compose.yaml`, `images/` (une image par fichier,
`nom.dockerfile`).

- `images/banc.dockerfile` : l'image `poa-banc`, Python 3.12, Node 24, uv et pnpm, l'environnement
  du dépôt installé comme par `make installer` ;
- `compose.yaml` : le lancement, en commandes ponctuelles, selon le réseau.

Les deux scripts qui s'en servent sont dans `09_outillage/scripts/` : `construire_image.sh`
(`make image`) et `lancer_conteneur.sh` (`make conteneur`).

## Ce qu'il faut sur la machine

Docker avec son greffon compose, git et make, et le droit de lancer `docker` sans `sudo`. Ni
Python, ni Node, ni uv. Pour vérifier :

    docker compose version && git --version && make --version

## Pas à pas

Chaque commande se copie telle quelle, depuis n'importe quel dossier : elle commence par se placer
à la racine du clone, `~/poa_banc`. Si ce dossier existe déjà, en choisir un autre et le remplacer
partout.

### 1. Cloner le dépôt

Sur une machine neuve, avec une clé SSH qui a accès au dépôt GitHub (seuls les commits poussés y
sont) :

    git clone git@github.com:Nimeria2026/Nimeria_poa.git ~/poa_banc

Sur le poste, depuis le dépôt de travail, sans passer par GitHub :

    git clone <dépôt de travail> ~/poa_banc

Le clone ne contient que les fichiers suivis : ni le `.env`, ni `07_taches/prive/`, ni `99_local/`.

### 2. Construire l'image

    cd ~/poa_banc && make image

Plusieurs minutes la première fois. La dernière ligne donne l'étiquette de l'image, `poa-banc:`
suivi des 12 premiers caractères du commit.

Le contexte de construction est l'archive git du commit : les tâches cachées, le `.env`,
`99_local/` et les modifications non commitées ne peuvent pas entrer dans l'image. L'image d'un
autre commit : `cd ~/poa_banc && make image COMMIT=<commit>`. Derrière un proxy qui déchiffre le
TLS (réseau d'entreprise, bac à sable d'une séance Claude), son certificat se passe en secret de
construction, sans entrer dans l'image : `cd ~/poa_banc && POA_CA=<fichier> make image`.

### 3. Passer les témoins

    cd ~/poa_banc && make conteneur RESEAU=aucun COMMANDE="make temoins"

Sans modèle ni réseau. La dernière ligne doit être `Le banc mesure ce qu'il doit.` Sans
`07_taches/prive/`, le terrain des tâches cachées est sauté.

### 4. Lancer les tests

La première fois, avec le réseau, qui télécharge les données de τ²-bench dans `99_local/tau2/` :

    cd ~/poa_banc && make conteneur RESEAU=api COMMANDE="make tests"

Les fois suivantes, hors ligne :

    cd ~/poa_banc && make conteneur RESEAU=aucun COMMANDE="make tests"

### 5. Apporter le `.env` et les tâches cachées

Seulement pour les runs avec un modèle et pour les témoins des tâches cachées. Ces fichiers ne
passent jamais par git. Sur le poste :

    cp <dépôt de travail>/.env ~/poa_banc/.env
    cp -r <dépôt de travail>/07_taches/prive ~/poa_banc/07_taches/prive

Sur une autre machine, les apporter du poste sans passer par git.

### 6. Lancer un run

Un modèle servi par une API, ici DeepSeek :

    cd ~/poa_banc && make conteneur RESEAU=api COMMANDE="make mesure CANDIDAT=agent_seul_deepseek_flash TACHES=t01 REPETITIONS=1"

Qwen, sur le poste seulement. D'abord le serveur, dans un autre terminal, depuis le dépôt de
travail (il refuse si la carte est occupée) :

    cd <dépôt de travail> && make qwen

Puis le run :

    cd ~/poa_banc && make conteneur RESEAU=machine COMMANDE="make mesure CANDIDAT=agent_seul_qwen_local TACHES=t01 REPETITIONS=1"

Jamais pendant un autre run de Qwen : les deux se partageraient le serveur et fausseraient leurs
durées. Les runs s'écrivent dans `~/poa_banc/99_local/runs/`.

### 7. Tout retirer

    docker image ls poa-banc
    docker image rm poa-banc:<étiquette>
    rm -rf ~/poa_banc

La dernière commande efface aussi les runs, le `.env` et les tâches cachées copiés dans le clone.

## Réseaux et montages

`COMMIT=<commit>` choisit l'image, celle du commit courant par défaut ; elle doit avoir été
construite. Les trois réseaux :

- `aucun` : témoins, tests, rapports, rejeu du gardien, sans aucun accès au réseau ; sur une
  machine neuve, le premier `make tests` télécharge les données de τ²-bench dans `99_local/tau2/`
  et se lance donc avec `RESEAU=api`, les suivants hors ligne ;
- `api` : runs dont les modèles sont servis par une API (DeepSeek, le juge, le simulateur de
  τ²-bench) ;
- `machine` : runs de Qwen servi par `make qwen` sur 127.0.0.1:30100, par le réseau de la machine,
  sans toucher aux configurations des candidats ni à leur empreinte.

Monté dans le conteneur : `99_local/` en écriture (runs, rapports, verdicts du juge, données de
τ²-bench) ; le `.env` en lecture seule, comme fichier, jamais versé dans l'environnement, parce
qu'un candidat hérite de tout l'environnement d'EASE et ne doit pas recevoir la clé du simulateur
de τ²-bench ; `07_taches/prive/` en lecture seule, s'il existe. Les fichiers écrits appartiennent
à qui lance la commande.

## Ce qu'il faut savoir

- La fiche de run porte le commit de l'image, lu dans `POA_COMMIT_IMAGE` faute de dépôt git dans
  le conteneur, et jamais de modification non commitée.
- Avec `RESEAU=machine`, le conteneur voit tout ce qui écoute sur 127.0.0.1, dont le serveur de
  Nimeria (port 30000) quand il tourne.
- L'énergie de la carte graphique se relève par `nvidia-smi`, absent du conteneur : elle vaut
  « ? » pour un run de Qwen lancé ici. Les runs de mesure de Qwen restent lancés hors conteneur,
  depuis le poste de mesure (`make poste-mesure`).
- Une même image ne rend pas les mêmes réponses d'un modèle : seuls les témoins sont
  déterministes. Reproduire Qwen ailleurs demande aussi la même version de vLLM, les mêmes poids et
  une carte de la même classe.
- Aucune image n'est publiée dans un registre.

# AGENTS.md

Le point d'entrée de ce dépôt, pour toute IA (opencode, Codex, Claude Code) comme pour toute
personne. Si un fichier `ATELIER.md` existe à côté de celui-ci, le lire aussi : ce sont les règles
de l'atelier privé, qui s'ajoutent à celles-ci.

## Ce qu'est ce dépôt

**Épreuve d'agent**, nom de code POA, est un banc de mesure d'agents IA. Une PME fictive française,
Calorelle, expose ses services (messagerie, facturation, planning, dossiers) par des serveurs MCP ;
des orchestrations d'agents y accomplissent des tâches de bureau vérifiables, à travers un gardien.
EASE mesure ce qu'elles réussissent, leur régularité, leur durée et leur coût ; EKE est l'outil
documentaire de la PME. Deux autres sociétés, Domivelle et Négovelle, servent au banc par branche.

La méthode de mesure, ses règles et ses limites : `00_docs/protocole/README.md`, figé par version
(étiquette git `protocole-v1`). Les décisions d'architecture : `00_docs/adr/`.

## Installer et vérifier

Prérequis : Python 3.12 et uv, Node.js 24 et pnpm (activé par Corepack). Toutes les commandes se
tapent à la racine du dépôt ; `make` les liste avec leurs options.

```
make installer      environnements Python (.venv) et TypeScript (node_modules), hors git
make tests          tous les tests, au premier plan
make qualite        ruff, pyright strict, Biome, tsc strict ; make formater corrige la forme
make verifier       le dépôt contre son plan, arborescence.toml
make temoins        les témoins : 100 %, 0 %, 50 % et 0 %, sinon c'est le banc qui se trompe
```

## Où vont les choses

```
<dépôt>/                         le seul dépôt : le code s'y écrit, les runs s'y enregistrent
├── 99_local/runs/               tous les runs de la PME, hors git ; aucun ne se supprime
├── 99_local/runs_tau2/          tous les runs de τ²-bench
├── 99_local/importes/           des runs faits ailleurs, gardés, que le rapport ne lit pas
├── 99_local/travail/            les états de travail des runs (PME, serveurs, verrous)
├── 99_local/publication/        les brouillons des publications
└── 08_publications/<date>_<sujet>/   l'officiel : manifeste, données, runs réduits ; figé
<dépôt>_postes/api, /local       les postes de mesure, seuls points de départ d'un run
```

Un run qu'aucun manifeste de `08_publications/` ne liste est conservé, jamais cité comme résultat.

## Lancer une mesure

Un run part toujours d'un poste de mesure : une copie du dépôt figée sur un commit de `main`, dont le
`99_local` est celui du dépôt. Pendant qu'il tourne, le travail continue dans le dépôt sans rien
changer au run. Deux postes : `api` pour les modèles par API, `local` pour ceux de la carte graphique.

```
make poste-mesure POSTE=api              depuis le dépôt ; COMMIT=<commit> pour un autre que HEAD
cd ../<dépôt>_postes/api
make essai CANDIDAT=<identifiant>        t01, une répétition : sonde, outils, réglages
make mesure CANDIDAT=<identifiant>       les lots : [TACHES=t01,t03] [GARDIEN=1] [CACHEES=1] [JEU=dure]
make mesure-tau2 CANDIDAT=<identifiant>  τ²-bench, compagnie aérienne
```

`make mesure` refuse un run lancé hors d'un poste, d'un poste modifié, ou d'un commit qui n'est pas
dans `main`. Sur la carte, un run à la fois. `make rapport` écrit le rapport HTML d'un ou plusieurs
candidats ; `make journal CHEMIN=<run> TACHE=<préfixe>` montre les traces d'un run, étape par étape.

## Ajouter un modèle

1. Copier la déclaration la plus proche, déjà mesurée et testée, sous un nouvel identifiant :
   - un modèle local : `02_ease/src/ease/candidats/agent_seul_qwen_local_100k.yaml` et sa
     configuration, `03_orchestrations/src/orchestrations/configurations/qwen_local_100k.yaml` ;
   - un modèle par API : `agent_seul_mimo_v26_flash_deepinfra.yaml` et
     `configurations/mimo_v26_flash_deepinfra.yaml` ;
   - sur τ²-bench, la même chose dans `02_ease/src/ease/candidats_tau2/`.
2. Remplir chaque champ ; un réglage, un prix, une version viennent d'une source datée, sinon ils
   s'écrivent `?`. Une clé d'API se lit dans une variable du `.env`, jamais dans un fichier suivi.
3. Un moteur local a sa commande dans `09_outillage/scripts/`, lancée par une cible du `Makefile`
   (`make qwen`, `make strata`), jamais seulement dans le journal du moteur.
4. Commiter dans `main`, préparer le poste à ce commit, lancer `make essai`, puis les lots.
5. Ne jamais déplacer ni renommer les fichiers d'un candidat déjà mesuré : l'empreinte d'un run
   compte leurs chemins, et ses anciens runs ne s'assembleraient plus avec les nouveaux.

## Publier

`make publier SUJET=constat` passe les témoins, calcule les données, écrit le manifeste et copie
chaque run retenu, réduit à ses tâches publiques, dans `08_publications/<date>_<sujet>/`. Il refuse
un code non commité, un commit hors de `main` ou sans étiquette du protocole, et une publication qui
existe déjà. Un chiffre public vient du `donnees.json` d'une publication, et de rien d'autre. Une
publication ne se modifie jamais : une erreur donne une nouvelle publication, qui cite l'ancienne.

`JOURNAL_PUBLIC.md` (dans le dépôt public, `JOURNAL.md`) garde les décisions et les événements qui
comptent pour qui lit les chiffres : une version du protocole, une publication, une correction, un
modèle mesuré. Chacun y ajoute une entrée, écrite pour le public. Les renvois du code à un
« JOURNAL » numéroté désignent les notes internes de l'atelier, qui ne sont pas publiées.

## Les tâches cachées

Une part des tâches reste cachée, pour mesurer ce qu'aucun modèle n'a pu voir : `07_taches/prive/`,
hors git, absent du dépôt public. Une IA ne les ouvre pas, sauf pour les écrire à la demande ; elle
ne lit pas les journaux des runs qui les contiennent, et n'en cite que des comptes, sans leurs noms.
Elles ne partent que chez un fournisseur dont la politique de données dit qu'il ne garde ni
n'entraîne sur les requêtes. Leur copie en ligne, dans `12_coffre/`, est chiffrée ; rien n'y entre
en clair.

## Les règles du banc

- Aucun agent ne touche un système réel pendant les essais : seulement la PME fictive, à travers le
  gardien. Les agents ne voient jamais les contrôles ni les solutions des tâches.
- Pas de chiffre sans fiche de run complète ; un champ inconnu s'écrit `?`. Pas d'amélioration
  annoncée sans intervalle de confiance qui exclut zéro.
- Les contrats de données s'écrivent en JSON Schema dans `01_contrats/` ; les modèles Python et les
  types TypeScript en sont générés (`make contrats`).
- Les frontières passent par MCP ou HTTP. Python pour EASE, les orchestrations et EKE ; TypeScript
  pour la PME et le gardien.
- Les journaux du raisonnement des candidats (`*_candidat.log`) restent dans les runs : ni affichés,
  ni publiés.
- Les tests se lancent au premier plan et leur résultat se dit ; jamais `--no-verify`.
- Le plan du dépôt est `arborescence.toml`, que la garde fait respecter avant chaque commit. Un
  emplacement manque : s'arrêter et le signaler. Le plan ne change que pour un vrai problème, par un
  ADR dans `00_docs/adr/`.
- Textes en français : contenu, commentaires, messages de commit ; noms de fichiers sans accent ni
  espace.

## Arborescence

La référence est `arborescence.toml`.

- `00_docs/` : protocole de mesure, ADR, sources datées
- `01_contrats/` : contrats en JSON Schema
- `02_ease/` : le banc de mesure, Python ; ses candidats déclarés dans `src/ease/candidats/`
- `03_orchestrations/` : les orchestrations d'agents, Python
- `04_eke/` : l'outil documentaire, Python
- `05_pme/` : les serveurs MCP de la PME, son interface web, ses données, TypeScript
- `06_gardien/` : la passerelle MCP qui filtre les gestes des agents, TypeScript
- `07_taches/` : les tâches, `public/` versionné, `prive/` hors git
- `08_publications/` : les publications, figées et datées
- `09_outillage/` : la garde, les crochets git, les scripts
- `10_deploiement/` : l'image du banc et son conteneur
- `11_bancs_publics/` : les bancs écrits par d'autres, aujourd'hui τ²-bench
- `12_coffre/` : la copie en ligne chiffrée de ce qui ne se refait pas
- `99_local/` : hors git, les runs et le travail local

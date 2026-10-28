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
make installer-hooks  les crochets git : la garde avant commit, les tests avant poussée
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

Une mesure (`make essai`, `make mesure`, `make mesure-tau2`) part toujours d'un poste de mesure :
une copie du dépôt figée sur un commit de `main`, dont le `99_local` est celui du dépôt. Pendant
qu'elle tourne, le travail continue dans le dépôt sans rien changer au run. Deux postes : `api`
pour les modèles par API, `local` pour ceux de la carte graphique. Les témoins (`make temoins`), la
publication et le serveur d'un modèle local (`make qwen`, `make strata`, dans un terminal à part,
avant l'essai) se lancent depuis le dépôt.

```
make poste-mesure POSTE=api              depuis le dépôt ; COMMIT=<commit> pour un autre que HEAD
cd ../<dépôt>_postes/api
make essai CANDIDAT=<identifiant>        t01, une répétition : sonde, outils, réglages
make mesure CANDIDAT=<identifiant>       les lots : [TACHES=t01,t03] [GARDIEN=1] [CACHEES=1] [JEU=<jeu>]
make mesure-tau2 CANDIDAT=<identifiant>  τ²-bench, compagnie aérienne
```

`make mesure` refuse un run lancé hors d'un poste, d'un poste modifié, ou d'un commit qui n'est pas
dans `main`. Sur la carte, un run à la fois.

Un modèle mesuré pour un constat passe quatre lots, un run à la fois, depuis son poste : le socle
avec ses cachées, la tranche dure avec ses cachées, le gardien sur les 25 tâches du socle qui
portent un contrôle grave (les clés `graves` de `07_taches/public/gravite.yaml`), τ²-bench.

```
make mesure CANDIDAT=<identifiant> CACHEES=1
make mesure CANDIDAT=<identifiant> JEU=dure CACHEES=1
make mesure CANDIDAT=<identifiant> GARDIEN=1 TACHES=t02,t05,t06,t07,t08,t09,t10,t11,t12,t16,t18,t22,t27,t28,t30,t32,t33,t35,t38,t40,t45,t54,t59,t61,t63
make mesure-tau2 CANDIDAT=<identifiant de sa déclaration sur τ²-bench>
```

 `make rapport` écrit le rapport HTML d'un ou plusieurs
candidats ; `make journal CHEMIN=<run> TACHE=<préfixe>` montre les traces d'un run, étape par étape.

## Ajouter un modèle

1. Copier la déclaration la plus proche, déjà mesurée et testée, sous un nouvel identifiant :
   - un modèle local : `02_ease/src/ease/candidats/agent_seul_qwen_local_100k.yaml` et sa
     configuration, `03_orchestrations/src/orchestrations/configurations/qwen_local_100k.yaml` ;
   - un modèle par API : `agent_seul_mimo_v26_flash_deepinfra.yaml` et
     `configurations/mimo_v26_flash_deepinfra.yaml` ;
   - sur τ²-bench, la déclaration dans `02_ease/src/ease/candidats_tau2/` et sa configuration dans
     `03_orchestrations/src/orchestrations/configurations_tau2/`, sous le même nom que celle de
     l'agent seul.
2. Remplir chaque champ ; un réglage, un prix, une version viennent d'une source datée, sinon ils
   s'écrivent `?`. Une clé d'API se lit dans une variable du `.env`, jamais dans un fichier suivi.
3. Un moteur local a sa commande dans `09_outillage/scripts/`, lancée par une cible du `Makefile`
   (`make qwen`, `make strata`), jamais seulement dans le journal du moteur, et sa fiche officielle
   dans `02_ease/src/ease/moteurs/` : versions, réglages, machine, limites. Le préréglage qu'un
   moteur exporte (celui de Strata) y est rangé et compté dans l'empreinte des déclarations qui s'en
   servent ; un relevé de versions (celui de vLLM) ne l'est pas, pour que les runs déjà faits
   s'assemblent avec les suivants. Sa cible vérifie le moteur contre la fiche avant de le lancer
   (`09_outillage/scripts/verifier_strata.py`, `verifier_qwen.py`).
4. Ajouter le nouvel identifiant aux tests qui listent les déclarations :
   `test_les_candidats_declares_se_lisent` (`02_ease/tests/test_chaine_agent.py`) ; pour τ²-bench,
   ceux de `02_ease/tests/test_mesure_tau2.py` et
   `test_les_configurations_de_reproduction_portent_les_reglages_de_tau2`
   (`03_orchestrations/tests/test_reproduction_tau2.py`) ; si la configuration porte des réglages,
   `test_les_configurations_livrees_se_lisent_et_la_consigne_existe`
   (`03_orchestrations/tests/test_agent_seul.py`). Les lancer au premier plan, puis `make verifier`.
5. Commiter dans `main`, préparer le poste à ce commit, lancer `make essai`, puis les lots.
6. Ne jamais déplacer ni renommer les fichiers d'un candidat déjà mesuré : l'empreinte d'un run
   compte leurs chemins, et ses anciens runs ne s'assembleraient plus avec les nouveaux.

## Écrire ou modifier une tâche

Les règles sont dans `07_taches/README.md` : la nomenclature, le contrat
(`01_contrats/tache.schema.json`, modèle `07_taches/public/modele_tache.yaml`), les vérifications,
les contrôles graves, les compléments d'état. Les données d'une société sont dans
`05_pme/societes/<société>/`, dont le `README.md` dit le format ; `make donnees` régénère ses états
initiaux, les générateurs de `09_outillage/scripts/` ses compléments. Les jeux : `dure` pour
Calorelle, `domivelle`, `domivelle_dure`, `negovelle`, `negovelle_dure`, et leur part v2.
`gabarit`, la société des campagnes, se règle par `05_pme/societes/gabarit/variables.yaml` :
ses tâches `gb01` à `gb10` ne s'écrivent pas à la main, `make gabarit` les régénère ; une tâche du
métier d'une campagne s'ajoute à côté, `gb11` et suivantes.

1. Une tâche modifiée, ou son complément, monte sa version : ses runs d'avant ne s'assemblent plus
   avec les suivants. Un code de tâche ne se renomme jamais.
2. Le témoin parfait a sa solution dans `02_ease/src/ease/solutions_<jeu>.py` : la tâche et sa
   solution changent ensemble.
3. Vérifier au premier plan : `make temoins TERRAIN=<jeu>` (100 %, 0 %, 50 % et 0 %),
   `make couverture` (chaque contrôle testé sur une réponse juste et une fausse),
   `make classement JEU=<jeu> ESTIMER=1` (la durée estimée par la grille), puis les tests de ce qui
   a changé.
4. Un contrôle tranché par le juge (`juge_requis`) prend son critère dans le jeu étalon
   (`07_taches/public/etalon/`) et ne compte qu'une fois le juge étalonné sur lui.
5. Une tâche cachée ne s'écrit que dans une séance dont le fournisseur ne garde ni n'entraîne sur
   les requêtes (« Les tâches cachées »).
6. Une tâche se corrige quand elle est en cause dans un résultat : une consigne ambiguë, un
   contrôle trop étroit, une donnée fausse. Jamais pour qu'un modèle réussisse mieux.

## Publier

`make publier SUJET=constat` passe les témoins, calcule les données, écrit le manifeste et copie
chaque run retenu, réduit à ses tâches publiques, dans `08_publications/<date>_<sujet>/`. Il refuse
un code non commité, un commit hors de `main` ou sans étiquette du protocole, et une publication qui
existe déjà. Un résultat de mesure publié vient du `donnees.json` d'une publication, et de rien
d'autre ; les chiffres de la méthode, comme l'étalonnage du juge, sont ceux du protocole. Une
publication ne se modifie jamais : une erreur donne une nouvelle publication, qui cite l'ancienne.

`JOURNAL_PUBLIC.md` (dans le dépôt public, `JOURNAL.md`) garde les décisions et les événements qui
comptent pour qui lit les chiffres : une version du protocole, une publication, une correction, un
modèle mesuré, le jour où ses chiffres sont publiés. Chacun y ajoute une entrée, écrite pour le
public. Les renvois du code à un
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
- Les tests se lancent au premier plan et leur résultat se dit ; une IA ne passe jamais
  `--no-verify`.
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

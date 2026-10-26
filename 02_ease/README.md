# 02_ease

Le banc de mesure. Langage : Python.

Contient le paquet `ease` : exécuteur des runs, contrôles de l'état final de la PME,
statistiques, fiches de run et génération des rapports, avec ses tests.

N'y met pas le code d'une orchestration, du gardien ou d'EKE. EASE les appelle par MCP ou HTTP,
jamais par import.

Entrées permises : `README.md`, `pyproject.toml`, `src/`, `tests/`.

Contenu actuel :

- `pyproject.toml` : dépendances du paquet, installées par `make installer` ;
- `src/ease/contrats/` : modèles générés depuis `01_contrats/` par `make contrats`, à ne pas
  modifier à la main ;
- `src/ease/chargement.py` : lecture des fichiers JSON ou YAML et contrôle par les schémas ;
- `src/ease/taches.py` : chargement et contrôle des tâches de `07_taches/` ;
- `src/ease/fiches.py` : fiches de run, résultats d'exécution, fiches candidat, sorties de
  candidat, et leurs règles ;
- `src/ease/courriels.py` : lecture d'un courriel de la PME et règles de son contrat ;
- `src/ease/empreintes.py` : empreintes sha256 des données d'un run, pour le rejouer ;
- `src/ease/executeur.py` : lance un candidat sur un jeu de tâches et écrit le run ; le
  candidat reçoit l'énoncé après le préambule de l'environnement, la date et l'heure de la PME
  (`enonce_donne`, JOURNAL, entrée 97) ;
- `src/ease/relais.py` : relais MCP en HTTP sur 127.0.0.1, qui offre les outils de
  l'environnement à un candidat externe ; chaque appel compte une étape, respecte le budget et
  entre au journal ;
- `src/ease/candidat_externe.py` : candidat lancé dans son propre processus (règle 6), avec
  l'adresse du relais, le fichier de l'énoncé et celui de sa sortie ; délai, budget épuisé et
  panne y deviennent un arrêt noté ; avant chaque exécution d'un candidat au tarif des heures
  creuses, le run s'arrête si les heures pleines sont proches ; la carte d'un modèle local est
  relevée pendant l'exécution ;
- `src/ease/creneaux.py` : heures pleines de DeepSeek (1 h à 4 h et 6 h à 10 h UTC, en
  semaine) ; une exécution ne commence pas à moins de 15 minutes d'elles ;
- `src/ease/energie.py` : wattmètre de la carte graphique par nvidia-smi (une mesure toutes les
  500 ms, puissance fois durée) ; un minimum, car la carte seule est vue ; « ? » sans mesure ;
- `src/ease/candidats.py` et `src/ease/candidats/` : les candidats déclarés (fiche,
  configuration, machine, lancement), comme `agent_seul_qwen_local` ;
- `src/ease/mesure.py` : mesure d'un candidat déclaré sur la PME (`make mesure
  CANDIDAT=agent_seul_qwen_local TACHES=t01 REPETITIONS=1`) ; refuse de lancer le run si le
  serveur d'un modèle local ne répond pas à sa sonde, un run DeepSeek en heures pleines, ou un
  second run d'un candidat qui tourne déjà ; avec `GARDIEN=1`, place le gardien entre l'agent et
  la PME et compte ses refus par tâche et par règle ;
  donne l'énergie de la carte en fin de run ;
- `src/ease/rejeu.py` : rejeu d'un run passé (`make rejouer-run CHEMIN=<run>`) : les appels
  réussis de ses journaux, refaits sans modèle devant les tâches d'aujourd'hui, disent ce qu'une
  correction change aux verdicts ; rien n'est écrit dans `99_local/runs`, aucune tâche cachée
  n'est ouverte, et le juge n'est appelé qu'avec `JUGE=1` ;
- `src/ease/statistiques.py` : intervalle de Wilson, pass^k, résumé d'un run ;
- `src/ease/etalon.py` : jeu étalon du juge (`make etalon`, `make etiqueter`) : textes écrits
  par les agents aux destinataires jugés, tirés des runs, et réponses fausses écrites exprès ;
  étiquetage à l'aveugle dans le terminal, une question à la fois ;
- `src/ease/juge.py` : le juge, DeepSeek V4.1 Flash, qui dit si une affirmation est vraie pour
  le texte écrit par un agent (`make etalonner`) ; grille fermée, réponse en JSON, texte jugé
  traité comme une donnée ; verdicts gardés par empreinte dans `99_local/juge/` ; étalonnage
  contre les étiquettes, accord par source et réponses fausses acceptées ; refus en heures
  pleines pour l'étalonnage. Entré au banc le 2026-10-06 : `make mesure` le consulte dès
  qu'une tâche porte une vérification `juge_requis`, à toute heure (un appel en heures pleines
  compté au tarif plein), et la fiche de run le note ;
- `src/ease/fausses_qwen.py` : Qwen, servi en local, écrit des réponses fausses pour le jeu de
  contrôle du juge (`make fausses-qwen`), sans voir les critères ;
- `src/ease/verdicts_temoins.py` : le juge réel tranche une fois les textes des témoins
  (`make verdicts-temoins`, en heures creuses) ; verdicts suivis par git, rejoués sans appel
  par les tests et par `make temoins` ;
- `src/ease/rapport.py` : rapport HTML des candidats déclarés (`make rapport`). Pour chaque
  tâche, les exécutions de sa version courante dans le run le plus récent qui les contient toutes, terminé ou interrompu (d'un run
  interrompu, ses tâches complètes seules) ; refus
  d'assembler des runs dont la configuration, les consignes, la machine ou les règles du
  gardien diffèrent ; runs avec gardien tenus à part (`make rapport GARDIEN=1`) ; marges par
  Wilson et par bootstrap à deux niveaux (tâches, puis exécutions), graine fixe ; plancher
  d'inertie ; coût par tâche réussie en dollars, électricité en euros ; un lien vers le récit de
  l'agent pour chaque exécution ;
- `src/ease/journal.py` : lecture d'un journal d'exécution dans un terminal, étape par étape
  (`make journal CHEMIN=<fichier ou dossier de run> TACHE=t05`) ;
- `src/ease/pme.py` : la PME vue par EASE. Remise à zéro de l'état de travail depuis
  `05_pme/societes/calorelle/` dans `99_local/pme/` (dans `99_local/pme_<candidat>/` pour
  `make mesure`, afin que deux candidats tournent en même temps), empreinte de la version, et
  `EnvironnementPME`, qui lance par Node les serveurs MCP de la tâche pour la personne servie et
  leur parle par le client MCP officiel (paquet `mcp`), en stdio ; EKE (`04_eke`), seul service
  en Python, se lance par le Python du dépôt, pour les seules tâches qui le déclarent ; ce que les serveurs écrivent
  sur leur sortie d'erreur va dans `99_local/pme_serveurs.log` (ou
  `99_local/pme_<candidat>_serveurs.log`). Avec un fichier de règles, `EnvironnementPME` ne
  lance que le gardien (`06_gardien`), qui lance les serveurs ; EASE n'en lit que la version et
  l'empreinte des règles, et compte ses refus dans les journaux d'exécution. Une tâche à
  complément d'état (t06 à t13) reçoit en plus `05_pme/societes/calorelle/complements/<nom>/`, posé sur
  l'état de la tâche ; la fiche de run note l'empreinte du complément, et le rapport ne mêle
  jamais deux compléments différents. Un environnement est d'un seul état (v1, v2 ou v3) et refuse
  une tâche partie d'un autre ; `make mesure` refuse des tâches de deux états (`etat_des_taches`) ;
- `src/ease/etat_pme.py` : instantané de l'état de la PME, fichiers, courriels, facturation
  (avoirs, et devis à partir de v3) et planning (à partir de v2), lu sur le disque sans passer
  par MCP (règle 3) ;
- `src/ease/verification.py` : vérificateur des contrôles, qui compare l'instantané initial et
  l'instantané final ;
- outils : chaque description garde ce que le service déclare, lecture seule ou non (annotation
  MCP `readOnlyHint`), et le relais la transmet au candidat ; une orchestration s'en sert pour
  savoir quoi faire relire (`03_orchestrations/src/orchestrations/auteur_relecteur.py`). Un
  candidat déclaré avec `acces_lecture: true` reçoit aussi `--mcp-lecture` : un second serveur
  du relais, où ne passent que les outils en lecture seule ; ses appels se comptent hors du
  budget de la tâche (au plus trois par étape du budget), dans
  `journaux/<tâche>_r<k>_lectures.jsonl` (entrée 94), et `make journal` les montre ; chacun de
  ses appels porte la marque `poa/lecture_seule` (`_meta` MCP), pour qu'un service n'en garde
  aucune trace, pas même un courriel marqué lu (entrée 95) ;
- `src/ease/jouet.py` : environnement jouet de l'étape 1, ses deux tâches, leurs solutions et
  leurs erreurs ;
- `src/ease/solutions_pme.py` : solutions et erreurs écrites à la main pour les 35 tâches
  publiques, jouées par les témoins à travers les outils MCP de la PME ;
- `src/ease/solutions_documents.py` : celles du jeu « documents » de l'étape 6
  (`07_taches/public/documents/`), dont le témoin parfait lit chaque PDF par EKE ; terrain
  `documents` des témoins (`make temoins TERRAIN=documents`), `make mesure JEU=documents` ;
- `src/ease/cachees.py` : les tâches cachées de `07_taches/prive/`, hors git, leurs compléments
  et leurs témoins ; le module ne connaît que la forme de ces fichiers ;
- `src/ease/temoins.py` : les quatre témoins, sur quatre terrains, le jouet, la PME dans
  l'état v2, où partent les 35 tâches publiques, les tâches cachées et le jeu « documents » (`make temoins`, un peu plus de deux minutes, presque toutes pour la PME ; `make temoins
  TERRAIN=jouet` pour le seul jouet) ; sur la PME, le juge y est rejoué depuis ses verdicts
  gardés ;
- `src/ease/temoin_externe.py` : le même témoin joué depuis un processus séparé, par le relais :
  il vérifie le chemin des vrais candidats ;
- `src/ease/terrain_tau2.py`, `temoins_tau2.py` et `rejeu_tau2.py` : τ²-bench (airline) en
  terrain d'EASE, servi par `11_bancs_publics` (étape 7) ; ses témoins, et le témoin rejoueur des
  conversations publiées par Sierra ;
- `src/ease/mesure_tau2.py` et `src/ease/candidats_tau2/` : mesure d'un candidat déclaré sur
  τ²-bench (`make mesure-tau2 CANDIDAT=reproduction_tau2_deepseek_flash TACHES=0,1 REPETITIONS=1`),
  face au simulateur d'utilisateur gemini-2.5-flash par OpenRouter, clé `OPENROUTER_API_KEY` dans
  `.env` ; runs dans `99_local/runs_tau2/`, simulateur et son coût dans le champ `banc_public` de
  la fiche ; ces candidats ne sont pas ceux de `make mesure` ;
- `tests/` : tests lancés par `make tests`.

# Point d'entrée des commandes du dépôt POA. Taper « make » pour la liste.

PYTHON ?= python3
UV ?= uv
PNPM ?= pnpm
# Tests Python en parallèle (pytest-xdist) : un processus par cœur logique ; make tests TRAVAILLEURS=1
# pour les lancer un par un (JOURNAL, entrée 258).
TRAVAILLEURS ?= auto
GARDE := 09_outillage/garde/verifier_arborescence.py
CONTRATS := 09_outillage/scripts/generer_contrats.py

.DEFAULT_GOAL := aide
.PHONY: publier coffre sauvegarder exporter-public strata essai image conteneur aide installer contrats donnees tests temoins mesure mesure-tau2 humain classement journal qwen qualite formater verifier tests-garde installer-hooks verdicts-temoins controle ecrire-fausses fausses-qwen couverture rejouer-gardien rejouer-run complements

aide: ## Affiche la liste des commandes
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  make %-18s %s\n", $$1, $$2}'

installer: ## Installe les environnements Python (uv) et TypeScript (pnpm), après un clone ou un changement
	@$(UV) sync --all-packages
	@$(PNPM) install --frozen-lockfile

contrats: ## Régénère le code des contrats depuis les schémas de 01_contrats/
	@$(UV) run --all-packages python $(CONTRATS)

donnees: ## Régénère les états initiaux des sociétés : v1, v2 et v3 de Calorelle, v1 de Domivelle, v1 de Négovelle
	@$(UV) run --all-packages python 09_outillage/scripts/generer_donnees_v1.py
	@$(UV) run --all-packages python 09_outillage/scripts/generer_donnees_v2.py
	@$(UV) run --all-packages python 09_outillage/scripts/generer_donnees_v3.py
	@$(UV) run --all-packages python 09_outillage/scripts/generer_domivelle_v1.py
	@$(UV) run --all-packages python 09_outillage/scripts/generer_negovelle_v1.py

complements: ## Régénère les compléments d'état des tâches pièges t06 à t13
	@$(UV) run --all-packages python 09_outillage/scripts/generer_complements.py

tests: ## Lance tous les tests : EASE, contrats, tâches, garde, PME
	@$(UV) run --all-packages pytest -n $(TRAVAILLEURS)
	@$(PYTHON) -m unittest discover -s 09_outillage/garde/tests
	@$(PNPM) --silent test

temoins: ## Passe les quatre témoins sur le jouet, la PME, ses tâches cachées, le jeu documents, la tranche dure et sa part cachée (TERRAIN=jouet, pme, pme_cachees, documents, dure, dure_cachees, domivelle, domivelle_dure, domivelle_cachees, domivelle_dure_cachees, negovelle, negovelle_dure, negovelle_cachees ou negovelle_dure_cachees pour un seul)
	@$(UV) run --all-packages python -m ease.temoins $(TERRAIN)

qwen: ## Sert Qwen 3.8 27B pour l'agent (port 30100), au premier plan ; refuse si la carte est occupée [102 400 jetons par défaut, celui du Qwen des publications ; CONTEXTE=40960 pour les candidats d'avant]
	@$(if $(CONTEXTE),POA_QWEN_CONTEXTE=$(CONTEXTE)) bash 09_outillage/scripts/servir_qwen.sh --lancer

strata: ## Sert Qwen 3.8 Flash-Next (IQ3_S) par le moteur Strata (port 30001), au premier plan ; refuse si la carte est occupée ; un run à la fois
	@bash 09_outillage/scripts/servir_strata.sh --lancer

mesure: ## Mesure un candidat déclaré sur la PME : CANDIDAT=<identifiant> [TACHES=t01,t03] [REPETITIONS=5] [GARDIEN=1] [CACHEES=1 : publiques et cachées | CACHEES=seules ; avec JEU=dure, domivelle, domivelle_dure, negovelle ou negovelle_dure, la part cachée de ce jeu] [JEU=documents : le jeu de l'étape 6, avec EKE | JEU=dure : la tranche dure | JEU=domivelle, domivelle_dure, negovelle ou negovelle_dure : les autres sociétés]
	@$(UV) run --all-packages python -m ease.mesure $(CANDIDAT) $(if $(TACHES),--taches $(TACHES)) $(if $(REPETITIONS),--repetitions $(REPETITIONS)) $(if $(GARDIEN),--gardien) $(if $(filter seules,$(CACHEES)),--cachees-seules,$(if $(CACHEES),--cachees)) $(if $(JEU),--jeu $(JEU))

essai: ## Un essai de contrôle d'un candidat, depuis un poste : t01, une répétition (sonde, outils, réglages), avant ses lots : CANDIDAT=<identifiant>
	@$(MAKE) --no-print-directory mesure CANDIDAT=$(CANDIDAT) TACHES=t01 REPETITIONS=1

humain: ## Poste humain : une personne fait les tâches dans le navigateur, chronométrée, une fois chacune : PERSONNE=p1 TACHES=t19,t04
	@$(if $(PERSONNE),,$(error PERSONNE manque, par exemple PERSONNE=p1))$(if $(TACHES),,$(error TACHES manque, par exemple TACHES=t19,t04))
	@echo "Poste humain : ouvrir http://127.0.0.1:$${POA_POSTE_HUMAIN_PORT:-30200} dans le navigateur, puis « Commencer »."
	@$(UV) run --all-packages python -m ease.mesure humain_$(PERSONNE) --taches $(TACHES) --repetitions 1

classement: ## Classement des tâches publiques : métier, services, contrôle grave, étiquettes, fiche ROME, durées humaines [VERSER=1 : verse les durées du poste humain] [ESTIMER=1 : calcule les durées estimées par la grille] [JEU=dure : la tranche dure | JEU=domivelle ou domivelle_dure : Domivelle | JEU=negovelle ou negovelle_dure : Négovelle] [CACHEES=1 : la part cachée du jeu, pour une séance qui peut la lire]
	@$(UV) run --all-packages python -m ease.classement $(if $(VERSER),--verser) $(if $(ESTIMER),--estimer) $(if $(JEU),--jeu $(JEU)) $(if $(CACHEES),--cachees)

mesure-tau2: ## Mesure un candidat déclaré sur τ²-bench, airline : CANDIDAT=<identifiant> [JEU=verified] [TACHES=0,1,2] [REPETITIONS=5] [SIMULATEUR=gemini_2_5_flash]
	@$(UV) run --all-packages python -m ease.mesure_tau2 $(CANDIDAT) $(if $(JEU),--jeu $(JEU)) $(if $(TACHES),--taches $(TACHES)) $(if $(REPETITIONS),--repetitions $(REPETITIONS)) $(if $(SIMULATEUR),--simulateur $(SIMULATEUR))

poste-mesure: ## Prépare un poste de mesure, copie du dépôt figée sur un commit, seul endroit d'où partent les runs : POSTE=api (modèles par API) ou POSTE=local (la carte), dans ../<dépôt>_postes/ [COMMIT=HEAD]
	@$(PYTHON) 09_outillage/scripts/poste_de_mesure.py --poste $(POSTE) $(if $(COMMIT),--commit $(COMMIT))

image: ## Construit l'image du banc (étape 8) depuis l'archive git d'un commit, poa-banc:<commit> [COMMIT=HEAD]
	@bash 09_outillage/scripts/construire_image.sh $(COMMIT)

conteneur: ## Lance une commande dans le conteneur du banc : RESEAU=aucun|api|machine COMMANDE="make temoins" [COMMIT=HEAD]
	@COMMIT=$(COMMIT) bash 09_outillage/scripts/lancer_conteneur.sh $(RESEAU) $(COMMANDE)

publication: ## Les données et les images d'une publication, dans 99_local/publication/<date>_<sujet>/ : SUJET=premier_post [SANS_PNG=1 : pages HTML seules]
	@d=99_local/publication/$$(date +%Y-%m-%d)_$(SUJET) && $(UV) run --all-packages python -m ease.donnees_publication $(SUJET) --sortie $$d/donnees.json --video $$d/donnees_video.json && $(UV) run --all-packages python -m ease.publication $(SUJET) --donnees $$d/donnees.json --sortie $$d $(if $(SANS_PNG),--sans-png)

publier: ## L'officiel d'une publication, dans 08_publications/<date>_<sujet>/ : SUJET=constat ou premier_post [DATE=AAAA-MM-JJ] ; témoins passés, manifeste écrit, runs réduits à leurs tâches publiques ; refuse un code non commité, hors de main ou sans étiquette du protocole
	@$(UV) run --all-packages python -m ease.publier $(SUJET) $(if $(DATE),--date $(DATE))

coffre: ## Chiffre avec age, dans 12_coffre/, les tâches cachées, les verdicts du juge et les runs publiés entiers qui ont changé ; rien ne s'efface (ADR 0008)
	@$(PYTHON) 09_outillage/scripts/coffre.py

sauvegarder: ## Copie 99_local/, 07_taches/prive/ et la clé age dans le dossier chiffré (gocryptfs) de la clé USB, sans rien y effacer : CLE=/media/<utilisateur>/<clé> [INITIALISER=1 : la première fois]
	@$(PYTHON) 09_outillage/scripts/sauvegarder.py $(CLE) $(if $(INITIALISER),--initialiser)

exporter-public: ## L'export public d'un commit de l'atelier dans un dossier neuf, vérifié (tâches cachées, clés, interdits, garde), sans rien envoyer : [SORTIE=<dossier>] [COMMIT=HEAD]
	@$(PYTHON) 09_outillage/scripts/exporter_public.py $(if $(SORTIE),--sortie $(SORTIE)) $(if $(COMMIT),--commit $(COMMIT))

rapport: ## Rapport HTML des candidats déclarés, versions courantes des tâches, dans 99_local/rapports/ [REPETITIONS=5] [GARDIEN=1] [CANDIDATS=a,b] [JEU=documents | JEU=dure]
	@$(UV) run --all-packages python -m ease.rapport $(if $(REPETITIONS),--repetitions $(REPETITIONS)) $(if $(GARDIEN),--gardien) $(if $(CANDIDATS),--candidats $(CANDIDATS)) $(if $(JEU),--jeu $(JEU))

etalon: ## Construit le jeu étalon du juge (une seule fois) : 07_taches/public/etalon/textes.json [AJOUTER=1 : textes des tâches nouvelles] [JEU=dure : étalon et contrôle des consignes de la tranche]
	@$(UV) run --all-packages python -m ease.etalon construire $(if $(AJOUTER),--ajouter) $(if $(filter dure,$(JEU)),--dure)

etiqueter: ## Étiquette le jeu étalon à l'aveugle, texte par texte ; q pour s'arrêter, on reprend où on en était [QUI=alexandre] [MOITIE=1] [CONTROLE=1] [JEU=dure] [NEUVES=1 : les seules consignes que le contrôle n'a pas étiquetées] [TACHES=t48 : ces seules tâches]
	@$(UV) run --all-packages python -m ease.etalon etiqueter $(if $(QUI),--qui $(QUI)) $(if $(MOITIE),--moitie) $(if $(CONTROLE),--controle) $(if $(filter dure,$(JEU)),--dure) $(if $(NEUVES),--neuves) $(if $(TACHES),--taches $(TACHES))

etalonner: ## Le juge face au jeu étalon étiqueté, en heures creuses de DeepSeek sauf HEURES_PLEINES=1 [QUI=alexandre] [AVEC=<prénom>] [MOITIE=1] [CONTROLE=1] [JEU=dure] [NEUVES=1] [TACHES=t48] [CACHE=<fichier> : verdicts à part, pour un juge neuf] [HEURES_PLEINES=1 : au tarif plein, le double]
	@$(UV) run --all-packages python -m ease.juge etalonner $(if $(QUI),--qui $(QUI)) $(if $(AVEC),--avec $(AVEC)) $(if $(MOITIE),--moitie) $(if $(CONTROLE),--controle) $(if $(filter dure,$(JEU)),--dure) $(if $(NEUVES),--neuves) $(if $(TACHES),--taches $(TACHES)) $(if $(CACHE),--cache $(CACHE)) $(if $(HEURES_PLEINES),--heures-pleines)

fausses-qwen: ## Qwen écrit 4 réponses fausses par tâche jugée pour le jeu de contrôle (make qwen d'abord) [TACHES=t06,t09] [JEU=dure]
	@$(UV) run --all-packages python -m ease.fausses_qwen $(if $(TACHES),--taches $(TACHES)) $(if $(filter dure,$(JEU)),--dure)

ecrire-fausses: ## Taper des réponses fausses pour le jeu de contrôle du juge, 4 par tâche jugée, chacune finie par une ligne « . » [QUI=alexandre] [TACHES=t48]
	@$(UV) run --all-packages python -m ease.etalon ecrire $(if $(QUI),--qui $(QUI)) $(if $(TACHES),--taches $(TACHES))

couverture: ## Vérifie que chaque contrôle des tâches est testé sur une réponse juste et une fausse
	@$(UV) run --all-packages python 09_outillage/scripts/couverture_controles.py

controle: ## Construit le jeu de contrôle du juge : les textes des runs jugés, neufs pour lui (une seule fois) [AJOUTER=1 : tâches nouvelles] [AJOUTER=1 TACHES=t04 : textes neufs de ces tâches]
	@$(UV) run --all-packages python -m ease.etalon construire --controle $(if $(AJOUTER),--ajouter) $(if $(TACHES),--taches $(TACHES))

rejouer-gardien: ## Rejoue les appels des runs passés devant les règles du gardien, sans rien exécuter ni payer [TOUS=1] [DETAIL=1]
	@node 06_gardien/src/rejouer.ts $(if $(TOUS),--tous) $(if $(DETAIL),--detail)

rejouer-run: ## Rejoue sans modèle les gestes d'un run devant les tâches d'aujourd'hui : ce qu'une correction change aux verdicts CHEMIN=<run> [TACHES=dvh03,dvh07] [JUGE=1 : juge appelé, clé dans .env]
	@$(UV) run --all-packages python -m ease.rejeu $(CHEMIN) $(if $(TACHES),--taches $(TACHES)) $(if $(JUGE),--juge)

verdicts-temoins: ## Le juge réel tranche une fois les textes des témoins, en heures creuses ; verdicts gardés pour les tests
	@$(UV) run --all-packages python -m ease.verdicts_temoins

relire: ## Relit un à un les désaccords entre le juge et l'étiquetage, après make etalonner [QUI=alexandre] [CONTROLE=1] [JEU=dure]
	@$(UV) run --all-packages python -m ease.relecture $(if $(QUI),--qui $(QUI)) $(if $(CONTROLE),--controle) $(if $(filter dure,$(JEU)),--dure)

journal: ## Affiche lisiblement un journal d'exécution : CHEMIN=<fichier .jsonl ou dossier de run> [TACHE=t05]
	@$(UV) run --all-packages python -m ease.journal "$(CHEMIN)" $(TACHE)

qualite: ## Contrôle le code : ruff et pyright strict (Python), Biome et tsc strict (TypeScript)
	@$(UV) run --all-packages ruff check
	@$(UV) run --all-packages ruff format --check
	@$(UV) run --all-packages pyright
	@$(PNPM) exec biome check
	@$(PNPM) --silent types

formater: ## Met le code en forme et corrige ce que ruff et Biome savent corriger seuls
	@$(UV) run --all-packages ruff format
	@$(UV) run --all-packages ruff check --fix
	@$(PNPM) exec biome check --write

verifier: ## Compare tout le dépôt au plan arborescence.toml
	@$(PYTHON) $(GARDE)

tests-garde: ## Lance les tests de la garde d'arborescence
	@$(PYTHON) -m unittest discover -s 09_outillage/garde/tests -v

installer-hooks: ## Active les crochets git : la garde avant chaque commit, les tests avant chaque poussée (une fois par clone)
	@chmod +x 09_outillage/hooks/*
	@git config core.hooksPath 09_outillage/hooks
	@echo "Crochets git actifs : 09_outillage/hooks"

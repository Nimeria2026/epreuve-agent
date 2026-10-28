# 09_outillage

Les outils du dépôt lui-même, pas ceux du projet.

- `garde/` : la garde de l'arborescence (`verifier_arborescence.py`) et ses tests.
- `hooks/` : les crochets git ; `pre-commit` contrôle l'arborescence des fichiers ajoutés, en
  quelques secondes ; `pre-push` lance tous les tests avant chaque poussée et la refuse s'ils
  échouent (ADR 0007).
- `scripts/` : scripts d'entretien du dépôt ; `generer_contrats.py` tire le code des contrats de
  `01_contrats/` (`make contrats`) ; `couverture_controles.py` vérifie que chaque contrôle des
  tâches est testé sur une réponse juste et une fausse (`make couverture`) ;
  `generer_donnees_v1.py`, `generer_donnees_v2.py` et `generer_donnees_v3.py` écrivent les
  états v1, v2 et v3 de la PME (`make donnees`), et `generer_complements.py` les compléments d'état des tâches de Calorelle, t06 à t45, d01 à
  d05 et la tranche dure (`make complements`) ; `poste_de_mesure.py` prépare les deux postes de mesure, api et local,
  copies du dépôt figées sur un commit d'où se lancent les runs (`make poste-mesure POSTE=api`) ; `construire_image.sh` construit l'image du
  banc depuis l'archive git d'un commit (`make image`), `lancer_conteneur.sh` y lance une commande
  (`make conteneur`), étape 8 ; `servir_qwen.sh` et `servir_strata.sh` servent les modèles locaux
  (`make qwen`, `make strata`) ; `coffre.py` chiffre la copie en ligne de ce qui ne se refait pas
  (`make coffre`, ADR 0008) et `sauvegarder.py` copie l'atelier dans un dossier chiffré par gocryptfs
  sur la clé USB (`make sauvegarder`) ; `verifier_qwen.py` et `verifier_strata.py` comparent un
  moteur local à sa fiche avant `make qwen` et `make strata` ; `exporter_public.py` écrit et
  vérifie l'export public d'un commit (`make exporter-public`, ADR 0010), avec `export/`, le
  `README` public et la liste des textes interdits ; `preparer_cloud.sh` prépare une séance dans le
  cloud ; `taille_banc.py` calcule combien de tâches il faut pour établir un écart entre deux
  candidats ; `generer_domivelle_v1.py`, `generer_negovelle_v1.py` et leurs
  `generer_complements_*.py` font de même pour les deux autres sociétés ; `generer_gabarit.py`
  écrit la société gabarit des campagnes depuis ses variables (`make gabarit`) ; `campagne.py`
  ouvre une campagne, un clone privé de l'atelier hors de lui, avec sa fiche et sa proposition
  (`make campagne`), et `cloture.py` la clôt : l'attestation de suppression, puis la suppression,
  après le nom retapé (`make cloture`).

Activer les crochets git une fois après chaque clone : `make installer-hooks`.

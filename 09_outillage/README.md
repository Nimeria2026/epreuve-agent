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
  états v1, v2 et v3 de la PME (`make donnees`), et `generer_complements.py` les compléments d'état des tâches, de t06 à t35
  (`make complements`) ; `poste_de_mesure.py` prépare les deux postes de mesure, api et local,
  copies du dépôt figées sur un commit d'où se lancent les runs (`make poste-mesure POSTE=api`) ; `construire_image.sh` construit l'image du
  banc depuis l'archive git d'un commit (`make image`), `lancer_conteneur.sh` y lance une commande
  (`make conteneur`), étape 8 ; `servir_qwen.sh` et `servir_strata.sh` servent les modèles locaux
  (`make qwen`, `make strata`) ; `coffre.py` chiffre la copie en ligne de ce qui ne se refait pas
  (`make coffre`, ADR 0008) et `sauvegarder.py` copie l'atelier dans un dossier chiffré par gocryptfs
  sur la clé USB (`make sauvegarder`).

Activer les crochets git une fois après chaque clone : `make installer-hooks`.

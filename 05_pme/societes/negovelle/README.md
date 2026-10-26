# Négovelle

Les données de Négovelle, troisième PME fictive du banc (ADR 0006) : un grossiste qui vend des
fournitures aux professionnels, à Vaumoreau-sur-Indre, commune inventée de l'Indre, au lundi
6 juillet 2026. Son cadrage est
`00_docs/sources/2026-10-17_cadrage_negoce_de_gros.md`.

Contenu :

- `v1/`, l'état de départ des 20 tâches courtes du socle : `entreprise/` écrit à la main, dont
  `societe.yaml`, qui déclare la société aux services ; `dossiers/`, `messagerie/`, `facturation/`
  et `ventes/` produits par `09_outillage/scripts/generer_negovelle_v1.py` (`make donnees`), d'après
  `v1/inventaire.yaml` ;
- `complements/`, un dossier par tâche, courte ou de la tranche longue, avec ses courriels non lus,
  leurs pièces, et les pièces que la tâche ajoute ou remplace dans l'état (une commande, un bon de
  livraison, une ligne de relevé). Tous sont produits par
  `09_outillage/scripts/generer_complements_negovelle.py`, qui lit v1 pour les chiffrer ;
  `--verifier` dit si un complément écrit diffère de ce qu'il produit.

Les compléments des tâches cachées de Négovelle iront dans
`07_taches/prive/complements/negovelle/`.

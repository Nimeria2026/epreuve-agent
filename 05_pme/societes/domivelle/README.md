# Domivelle

Les données de Domivelle, seconde PME fictive du banc (ADR 0006) : une agence d'administration de
biens, gestion locative et syndic de copropriété, à Montclavel-sur-Cher, commune inventée du Cher,
au lundi 8 juin 2026. Elle fait la contre-épreuve de Calorelle (JOURNAL, quatre-vingt-deuxième
entrée) ; son cadrage est `00_docs/sources/2026-10-15_cadrage_administration_de_biens.md`.

Contenu : `v1/`, l'état de départ des 20 tâches courtes du socle. Viendront `complements/`, un
dossier par tâche qui en a besoin, avec ses courriels non lus et leurs pièces. Le dossier
`entreprise/` de chaque état est écrit à la main, dont `societe.yaml`, qui déclare la société aux
services ; `dossiers/` et `messagerie/` de v1 sont produits par
`09_outillage/scripts/generer_domivelle_v1.py` (`make donnees`), d'après `v1/inventaire.yaml`.
Les compléments des tâches cachées de Domivelle iront dans `07_taches/prive/complements/domivelle/`.

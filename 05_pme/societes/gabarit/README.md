# La société gabarit

La base des campagnes (cadrage des interventions, `00_docs/sources/2026-10-26_cadrage_interventions.md`,
section 11 ; JOURNAL, entrée 312) : une société fictive réglée par un seul fichier,
`variables.yaml`. Une campagne y met le nom, le métier, les personnes, les clients, les
fournisseurs, le tarif et les règles chiffrées de l'entreprise (toujours inventés, domaines en
`.example`), puis `make gabarit` régénère tout le reste ; `make temoins TERRAIN=gabarit` vérifie
que les dix tâches communes restent justes. Les valeurs livrées décrivent une entreprise inventée.

Contenu :

- `variables.yaml`, écrit à la main, lu par `ease.gabarit`, qui refuse une variable manquante ;
  sa section `textes` porte ce que disent les clients dans les mots du métier (le nom du contrat,
  une demande de devis, un prospect, une réclamation), la seule part des tâches qui en dépend. Les
  tâches supposent des clients sous contrat, payés au forfait mensuel ; les dates suivent
  l'horloge (`societe.debut`) ;
- `v1/`, l'état de départ, écrit par `09_outillage/scripts/generer_gabarit.py` : `entreprise/`
  (paramètres, horloge, organigramme, accès aux dossiers, manuel), `dossiers/` (le manuel et
  l'annuaire dans `commun/`, les fiches des clients et des fournisseurs, la comptabilité, le
  commercial, les dossiers du personnel) et `messagerie/` ;
- `complements/gb01_*` à `complements/gb10_*`, les courriels non lus des dix tâches communes, une
  par type du socle commun (`07_taches/public/types_communs.yaml`), écrits par le même script.

Les tâches sont dans `07_taches/public/gabarit/`, avec leur gravité et leur classement ; leurs
gestes, dans `02_ease/src/ease/solutions_gabarit.py` ; les règles du gardien, dans
`06_gardien/regles/gabarit/v1.yaml`. Le script possède `v1/`, les dix compléments, les dix tâches
et les règles du gardien : il les réécrit d'un bloc, et `make gabarit VERIFIER=1` dit si l'un
d'eux diffère de ce que donnent les variables.

Une tâche du métier d'une campagne s'écrit à la main après gb10 (`gb11_nom_parlant.yaml`), avec son
complément dans `complements/` et ses gestes dans `metier()` de `solutions_gabarit.py` ; le script
la laisse, et garde sa gravité et sa fiche de classement. Hors du gabarit : le planning, les ventes
et la facturation, trop liés au métier ; une campagne qui en a besoin les reprend de Calorelle ou
de Négovelle. Les six rôles des variables sont six personnes distinctes ; une entreprise plus
petite en invente pour les rôles qui lui manquent.

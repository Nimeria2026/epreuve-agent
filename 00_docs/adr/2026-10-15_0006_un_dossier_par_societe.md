# ADR 0006 : un dossier par société dans 05_pme

Date : 2026-10-15
Statut : accepté

## Problème rencontré

Le 2026-10-15, une seconde PME fictive en administration de biens est cadrée dans une autre
conversation (`00_docs/sources/2026-10-15_cadrage_administration_de_biens.md`, section 5). Proposée
d'abord sous le nom de Quittelle, elle s'appelle Domivelle, nom vérifié par Alexandre à l'INPI le
2026-10-15.
Le plan en version 5 n'a qu'un dossier de données, `05_pme/donnees_initiales/`, celui de Calorelle :
le cadrage y rangeait l'état de la nouvelle société, `05_pme/donnees_initiales/quittelle_v1/`, à
côté de `v1/`, `v2/` et `v3/` de Calorelle, et ses compléments d'état dans le même `complements/`
que les 52 compléments de Calorelle. Les compléments des tâches cachées, eux, se rangent dans
`07_taches/prive/complements/`. Les deux sociétés se mélangeraient dans un seul dossier, et rien ne
dirait à quelle société appartient un état ou un complément. Alexandre demande de ranger
`05_pme/` pour que les nouvelles sociétés ne se mélangent pas, un dossier par société.

## Décision

Les données de chaque société vont dans `05_pme/societes/<société>/`, avec ses états initiaux
versionnés (`v1/`, `v2/` et les suivants) et ses compléments d'état (`complements/<tâche>/`), et
rien d'autre. `05_pme/donnees_initiales/` devient `05_pme/societes/calorelle/`, sans autre
changement : mêmes fichiers, mêmes empreintes d'état et de compléments, mêmes versions de tâches.
Les services restent où ils sont, communs à toutes les sociétés. Choix d'Alexandre du 2026-10-15.

Dans EASE, le chemin d'une société ne s'écrit qu'une fois, dans `dossier_societe()`
(`02_ease/src/ease/chargement.py`) ; `dossier_version()` et `dossier_complement()`
(`02_ease/src/ease/pme.py`) prennent la société, Calorelle par défaut. La façon dont une tâche
désigne sa société n'est pas décidée ici : elle le sera avec la seconde société.

Les compléments des tâches cachées d'une nouvelle société vont dans
`07_taches/prive/complements/<société>/<tâche>/`. Ceux de Calorelle restent à la racine de
`07_taches/prive/complements/`, ni ouverts ni déplacés : les tâches cachées ne s'ouvrent jamais.
Un préfixe d'identifiant propre à chaque société aurait suffi, mais personne ne peut vérifier
qu'aucune tâche cachée ne l'emploie déjà. La recherche dans ce sous-dossier se code avec la
désignation de la société par une tâche, dans `dossier_complement()` et `coherence_pme()`.

## Alternatives écartées

- Ranger aussi les services dans `05_pme/services/` : plus symétrique, mais il faut refaire
  `pnpm-lock.yaml`, les `tsconfig.json` et les `node_modules`, ceux du poste de mesure compris,
  pour un code qui ne change pas.
- Chaque société directement sous `05_pme/` (`05_pme/calorelle/`) : chemins plus courts, mais
  services et sociétés au même niveau, ce qu'Alexandre veut éviter.
- Garder `05_pme/donnees_initiales/` et préfixer les états (`domivelle_v1`) : c'est le mélange
  constaté.

## Conséquences

- `arborescence.toml` passe en version 6 et cite l'ADR 0006. La zone `05_pme` exige `societes/`
  au lieu de `donnees_initiales/`. La zone de noms libres de l'ADR 0003 passe de
  `05_pme/donnees_initiales` à `05_pme/societes`.
- `biome.json` exclut `05_pme/societes` au lieu des dossiers `donnees_initiales`.
- Les chemins changent dans EASE (`chargement.py`, `pme.py`, `taches.py`, `etalon.py`), le gardien
  (`rejouer.ts`), les générateurs de `09_outillage/scripts/`, les tests et la description du
  champ `complement` du contrat de tâche (contrats régénérés).
- Les commentaires des tâches publiques citent le nouveau chemin de leur complément ; ni leur
  version ni leurs contrôles ne changent. Les tâches cachées ne sont pas ouvertes : leurs
  compléments restent dans `07_taches/prive/complements/`.
- `05_pme/README.md`, `05_pme/societes/README.md`, `05_pme/societes/calorelle/README.md` et le
  BRIEF (§6) décrivent le rangement. Le JOURNAL, les ADR et les documents de `00_docs/sources/`
  antérieurs gardent l'ancien chemin : ils disent ce qui était vrai à leur date.
- Le code porte encore quatre choses propres à Calorelle, à rendre réglables avec la seconde
  société : le domaine interne de la messagerie (`DOMAINE_INTERNE`), la mention du PDF
  (`MENTION_FICTIF`), le chemin des fiches fournisseurs (`achats`) et le domaine des adresses
  du personnel dans EASE (`DOMAINE_PERSONNEL`, `02_ease/src/ease/verification.py`).

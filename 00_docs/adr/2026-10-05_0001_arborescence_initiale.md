# ADR 0001 : arborescence initiale du dépôt

Date : 2026-10-05
Statut : accepté

## Problème rencontré

Le dépôt officiel `Projets/Nimeria_poa/` était vide. Alexandre a demandé un dépôt monté comme le
ferait un développeur : agnostique, évolutif, avec un mécanisme qui empêche de dévier de
l'arborescence de départ sauf vrai problème rencontré. Sans plan écrit et vérifié, un projet mené
avec des agents de code accumule des dossiers créés au fil des sessions, et la structure se
dégrade sans que personne ne l'ait décidé.

## Décision

**Un dépôt unique, découpé par composant.** Chaque composant du BRIEF a son dossier de premier
niveau, numéroté selon la convention de `METHODE.md` : la documentation, les contrats, les
composants Python, les composants TypeScript, les données, les publications, l'outillage et le
déploiement. Le dossier `99_local/`, hors git, reçoit tout ce que le travail génère.

**Des contrats indépendants du langage.** Les données échangées entre composants sont décrites en
JSON Schema dans `01_contrats/`. Les modèles Pydantic et les types TypeScript en sont générés.
Avec MCP et HTTP comme seules frontières, un composant peut être réécrit dans un autre langage
sans toucher aux autres. C'est le sens d'« agnostique » dans ce dépôt.

**Deux langages, chacun dans son territoire.** Les extensions permises sont déclarées par zone.
Un fichier `.ts` dans une zone Python, ou l'inverse, est un écart.

**Deux niveaux figés, l'intérieur libre.** Le plan fixe le premier niveau du dépôt et le premier
niveau de chaque zone. En dessous, l'organisation suit les besoins du composant ; seuls le
nommage et les extensions restent contrôlés. Le dépôt grandit sans ADR tant qu'il grandit à
l'intérieur des zones.

**Les fichiers de la racine.** Aux quatre fichiers de pilotage de `METHODE.md` s'ajoutent les
fichiers que les outils exigent à cet endroit (configuration de uv, de pnpm, de git et de
l'éditeur, `Makefile`), le plan `arborescence.toml` et un `README.md` pour qui découvre le dépôt.
C'est une exception assumée à la règle « zéro fichier à la racine », limitée à ce que les outils
imposent et listée dans le plan.

**Les sorties.** Un run écrit dans `99_local/`. Seuls les résultats publiés entrent dans
`08_publications/`, figés et datés ; une correction donne une nouvelle publication, jamais une
modification.

**La garde.** `arborescence.toml` décrit le plan, et `09_outillage/garde/verifier_arborescence.py`
le fait respecter à quatre moments : à chaque écriture d'un agent Claude Code (le crochet bloque
l'écriture), avant chaque commit (crochet git), dans l'intégration continue, et à la demande avec
`make verifier`. Le script n'utilise que la bibliothèque standard de Python et a ses propres
tests (`make tests-garde`).

**La procédure de changement.** Le plan ne change que pour un vrai problème rencontré : un ADR
daté qui décrit ce problème, la mise à jour d'`arborescence.toml` avec une nouvelle version et le
numéro de l'ADR, une entrée au JOURNAL, puis `make verifier`. La garde refuse un plan qui cite un
ADR absent.

## Alternatives écartées

- Un dossier par langage (`python/`, `typescript/`) : l'unité qui évolue est le composant, et un
  composant doit pouvoir changer de langage.
- Un outil de monorepo (Nx, Turborepo, Bazel) : trop lourd pour une personne seule, et une
  dépendance de plus à comprendre.
- Un plan en JSON : pas de commentaires, donc pas d'explication à côté de la règle.
- Une garde au seul moment du commit : un agent de code aurait déjà créé les fichiers. Le crochet
  d'écriture arrête l'écart au moment où il se produit.

## Conséquences

- Plan en version 1, adossé à cet ADR.
- Les espaces de travail Python (uv) et TypeScript (pnpm) se créent aux étapes 1 et 2, dans les
  emplacements déjà prévus à la racine.
- Les outils de génération des contrats restent à choisir à l'étape 1, avec un nouvel ADR s'ils
  exigent un emplacement non prévu.
- Le crochet git s'active une fois par clone : `make installer-hooks`.
- La garde demande Python 3.11 ou plus, pour lire le TOML avec la bibliothèque standard.

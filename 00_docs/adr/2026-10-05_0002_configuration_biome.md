# ADR 0002 : configuration de Biome à la racine

Date : 2026-10-05
Statut : accepté

## Problème rencontré

Le 2026-10-05, à l'ouverture de l'étape 2, Alexandre a validé Biome comme outil de style et de
mise en forme du code TypeScript (JOURNAL du 2026-10-05, seizième entrée). Biome lit sa
configuration dans un fichier `biome.json`, cherché dans le dossier courant puis dans ses
parents : pour couvrir la PME (`05_pme/`) et plus tard le gardien (`06_gardien/`), ce fichier doit
être à la racine. La garde l'a refusé :

    biome.json : fichier non prévu à la racine.

Le plan de l'ADR 0001 prévoyait les fichiers de pnpm et de TypeScript à la racine, mais pas celui
de l'outil de style, choisi après coup.

## Décision

Ajouter `biome.json` aux fichiers permis à la racine. C'est la même exception que celle de
l'ADR 0001 pour uv, pnpm, git et l'éditeur : un fichier que l'outil exige à cet endroit, et rien
d'autre. Un seul fichier de configuration couvre toutes les zones TypeScript.

## Alternatives écartées

- Un `biome.json` dans chaque paquet TypeScript : permis par le plan actuel, mais la même
  configuration recopiée finit par diverger d'un paquet à l'autre.
- Une configuration rangée dans `09_outillage/` et passée à Biome par `--config-path` : il
  faudrait de toute façon permettre l'extension `.json` dans cette zone, et chaque commande
  devrait rappeler le chemin.
- ESLint et Prettier à la place de Biome : deux fichiers de configuration à la racine au lieu
  d'un, et trois dépendances au lieu d'une.
- Aucun outil de style, le compilateur seul : le PLAN demande une vérification du style à
  l'étape 2.

## Conséquences

- `arborescence.toml` passe en version 2 et cite l'ADR 0002 ; `biome.json` rejoint la liste des
  fichiers de la racine.
- Biome ignore les données (`05_pme/donnees_initiales/`) et le code généré depuis `01_contrats/`,
  comme ruff côté Python.

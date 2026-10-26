# ADR 0008 : le coffre chiffré, et une porte d'entrée pour toute IA

Date : 2026-10-26
Statut : accepté

## Problème rencontré

Le 2026-10-25, opencode a mesuré Flash-Next sous Strata depuis un dossier temporaire, hors des
règles de l'atelier : il n'avait lu ni `CLAUDE.md`, que seul Claude Code lit, ni le JOURNAL. Au
redémarrage du PC, ce dossier a disparu avec son commit, sa déclaration et son run de τ²-bench
(JOURNAL, entrées 276 et 281). Le même jour, le relevé de l'atelier a montré que les tâches cachées
(`07_taches/prive/`, 18 Mo) et les verdicts du juge (`99_local/juge/`, 7,4 Mo) n'existent qu'en un
exemplaire, sur un disque : ni l'une ni l'autre ne se refait (cadrage du dépôt public et de
l'organisation, sections 2 et 9).

Alexandre, le 2026-10-26 : garder leur copie en ligne dans `Nimeria_poa`, déjà privé, plutôt que dans
un dépôt à part (entrée 283) ; et un dossier propre, utilisable par n'importe quelle IA (entrée 276).

## Décision

- Une zone nouvelle, `12_coffre/` : des fichiers chiffrés avec `age` et numérotés (`00001.age`),
  leur index chiffré (`index.age`), la clé publique (`destinataire.txt`) et un `README.md`. Rien en
  clair : une IA qui travaille dans l'atelier envoie ce qu'elle lit à son fournisseur. `make coffre`
  (`09_outillage/scripts/coffre.py`) ne rechiffre que ce qui a changé et n'efface rien.
- Deux fichiers nouveaux à la racine : `AGENTS.md`, public, que lisent opencode, Codex et Claude ;
  `ATELIER.md`, privé, les règles d'Alexandre pour l'atelier. `CLAUDE.md` renvoie vers eux.

## Alternatives écartées

- Un dépôt privé à part, `Nimeria2026/module_poa` : une seconde histoire à tenir pour 25 Mo, sans
  gain de sécurité, l'atelier étant déjà privé (entrée 283).
- Les tâches cachées en clair dans git : lues et envoyées par toute IA qui ouvre l'atelier.
- Le coffre dans `99_local/` ou `07_taches/prive/` : hors git, donc hors ligne, ce qu'il doit corriger.
- Un fichier chiffré par fichier de `07_taches/prive/` (763) : un morceau par entrée de premier
  niveau (28) suffit, et le dossier reste lisible.
- Les seules règles dans `CLAUDE.md` : les autres outils ne le lisent pas, c'est la cause de l'essai
  perdu.

## Conséquences

- `arborescence.toml` passe en version 8 et cite l'ADR 0008 : la racine permet `12_coffre/`,
  `AGENTS.md` et `ATELIER.md` (aussi en exceptions de nommage) ; la zone `12_coffre` ne permet que
  `.age`, `.txt` et `.md`.
- `.gitattributes` tient `*.age` pour binaire.
- `make coffre` et `make sauvegarder CLE=<clé USB>` (`09_outillage/scripts/sauvegarder.py`) ;
  l'export public ne copiera jamais `12_coffre/` et refusera tout fichier `.age`.

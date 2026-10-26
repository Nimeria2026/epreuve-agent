# ADR 0005 : l'interface web de la PME, dans 05_pme

Date : 2026-10-13
Statut : accepté

## Problème rencontré

Le 2026-10-13, Alexandre décide de mesurer la durée humaine des tâches par un poste humain, dont
l'interface est une page web (JOURNAL, cent-vingt-et-unième entrée ;
`00_docs/sources/2026-10-13_conception_poste_humain.md`). Ce poste est un client des services de
la PME : il affiche les courriels, les dossiers, le planning et la facturation, et chaque action
passe par les mêmes outils MCP que l'agent. Le plan en version 4 décrit `05_pme/` comme « un
serveur MCP par service, données initiales » : une interface n'est pas un serveur MCP.

## Décision

Étendre le rôle de la zone `05_pme/` à l'interface web de la PME, rangée dans
`05_pme/interface_web/`, en TypeScript comme les services, avec son `package.json`, son `src/` et
ses `tests/`. Les pages sont rendues par le serveur, sans fichier `.html` ni `.css` : les entrées
et les extensions de la zone ne changent pas. Choix d'Alexandre du 2026-10-13.

La même interface pourra servir plus tard aux agents qui passent par l'écran, que le BRIEF
prévoit de mesurer une fois la PME dotée d'une interface web (§3, « Qui peut être mesuré »).

## Alternatives écartées

- Une zone nouvelle au premier niveau : plus séparée, mais une zone de plus pour un client des
  services de la PME, qui en partage le langage, les dépendances et l'espace pnpm.
- Le poste en Python, dans `02_ease/` ou `03_orchestrations/` : la règle 6 sépare le banc de ce
  qu'il mesure, et l'interface appartient à la PME, pas au banc ni aux candidats.

## Conséquences

- `arborescence.toml` passe en version 5, cite l'ADR 0005, et le rôle de `05_pme` nomme
  l'interface web.
- `05_pme/README.md` décrit `interface_web/` ; le BRIEF (§6) aussi.
- `pnpm-workspace.yaml` couvre déjà `05_pme/*` : le paquet entre dans l'espace pnpm sans autre
  changement, après un `make installer`.

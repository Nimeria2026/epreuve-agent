# ADR 0004 : zone des bancs publics d'agents

Date : 2026-10-08
Statut : accepté

## Problème rencontré

Le 2026-10-08, en ouvrant l'étape 7 dans une séance de Claude Code dans le cloud
(`00_docs/sources/2026-10-08_journal_tau2.md`), il a fallu placer le code qui sert τ²-bench à
EASE : un serveur MCP en Python qui importe le paquet `tau2` de Sierra, fait jouer son simulateur
d'utilisateur et note chaque conversation avec l'évaluateur de τ²-bench. Aucune zone du plan en
version 3 ne l'accueille :

- `02_ease/` est le banc ; la règle 6 du BRIEF interdit à EASE d'importer ce qu'il mesure, et
  τ²-bench est un terrain de mesure, comme la PME ;
- `03_orchestrations/` porte les candidats mesurés, qui ne voient jamais les contrôles (règle 5) ;
  or ce serveur tient les critères d'évaluation des tâches ;
- `05_pme/` est la PME fictive Calorelle, en TypeScript, et n'admet pas de `.py` ;
- `04_eke/` est l'outil documentaire de la PME.

## Décision

Ajouter une zone `11_bancs_publics/` : les bancs publics d'agents construits par d'autres,
servis à EASE par MCP. Python, un paquet `bancs_publics` membre de l'espace uv, mêmes entrées et
mêmes extensions que les autres zones Python (`README.md`, `pyproject.toml`, `src/`, `tests/`).
τ²-bench y entre par son commit `v1.0.1` dans les dépendances du paquet ; ses données, qui ne
sont pas dans le paquet, sont récupérées au même commit dans `99_local/`, hors git, empreinte
vérifiée. Choix d'Alexandre du 2026-10-08 (journal de la séance, troisième entrée).

## Alternatives écartées

- Un paquet à part dans `02_ease/src/`, jamais importé par `ease` : pas d'ADR, mais EASE porterait
  τ²-bench et litellm dans ses dépendances, et la frontière de la règle 6 ne serait plus celle
  d'une zone.
- Recopier dans la nouvelle zone le code et les données d'airline : pas de réseau à
  l'installation, mais une copie à tenir à jour à la main, qui divergerait de l'amont.
- `03_orchestrations/` : le serveur connaît les critères d'évaluation, qu'aucun candidat ne doit
  voir.

## Conséquences

- `arborescence.toml` passe en version 4, cite l'ADR 0004 et déclare la zone
  `11_bancs_publics` ; `pyproject.toml` à la racine en fait un membre de l'espace uv, et y étend
  pytest et pyright.
- Le test de frontière d'EASE (`test_ease_n_importe_ni_orchestration_ni_gardien_ni_eke`) interdit
  aussi `tau2` et `bancs_publics`.
- Un autre banc public (le banc de documents d'EKE, par exemple) peut entrer dans la même zone
  sans nouvel ADR.
- `CLAUDE.md` et `BRIEF.md` décrivent l'arborescence : à mettre à jour par la séance du poste
  d'Alexandre à la fusion, la séance du cloud ne les modifiant pas.

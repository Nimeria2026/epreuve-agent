# ADR 0007 : les tests complets avant la poussée, la garde seule avant le commit

Date : 2026-10-18
Statut : accepté

## Problème rencontré

Le crochet avant commit (`09_outillage/hooks/pre-commit`) passait la garde, puis lançait
`make tests` sur toute la copie de travail dès qu'un fichier du commit n'était pas de la
documentation (entrée 119 du JOURNAL). La suite compte 6 203 tests Python collectés le 2026-10-18,
plus ceux de TypeScript. Le 2026-10-17, un commit a tenu le verrou de git (`.git/index.lock`) au
moins douze minutes, de 16 h 26 à 16 h 38 UTC au moins : pendant ce temps, l'autre conversation
ne pouvait ni commiter ni toucher aux fichiers suivis. Les tests portaient aussi sur ce qu'elle
avait laissé en cours dans la copie de travail.

Mesuré le 2026-10-18, fichier par fichier, sur le poste de la séance : les 4 657 tests d'EKE et
des orchestrations passent en 12 secondes. Le temps est dans quelques fichiers d'EASE :
`test_chaine_agent.py` 29 secondes, `test_candidat_externe.py` 25 ; `test_documents.py`,
`test_domivelle_taches.py` et `test_domivelle_dure.py` dépassent chacun 50 secondes, et les
tests des tâches cachées 170 secondes. Les autres fichiers d'EASE n'ont pas été mesurés.

La séance ne pouvait pas non plus commiter elle-même : chacune de ses commandes s'arrête au bout
de 3 minutes, moins que le crochet. Alexandre tapait donc chaque commit.

Alexandre, le 2026-10-18 : « En production, je veux bien comprendre qu'il y ait tous ces tests,
mais lorsqu'on est en conception, c'est un peu trop », puis « on lance juste les commits de
quelques secondes et c'est seulement avant le push qu'on fait les gros tests ».

## Décision

- Avant chaque commit, la garde de l'arborescence seule : quelques secondes.
- Avant chaque poussée, un crochet nouveau, `09_outillage/hooks/pre-push`, lance `make tests` au
  premier plan, sous les yeux de qui pousse, et refuse la poussée si un test échoue. La poussée,
  rare et faite par Alexandre, marque la fin d'un lot. `make tests` reste disponible à tout
  moment, et l'intégration continue relance tout après chaque poussée.
- Rien ne tourne en arrière-plan : un test lancé par une séance l'est au premier plan, et son
  résultat est dit. Avant chaque commit, la séance lance les tests de ce qu'elle a touché.
- La séance peut commiter elle-même ses commits locaux, que les règles d'autonomie d'Alexandre
  autorisent sans validation ; la poussée reste à Alexandre, avec son accord.

## Alternatives écartées

- La garde et les tests du seul dossier touché : un commit d'EASE aurait encore attendu plusieurs
  minutes.
- La garde et ruff : quelques secondes de plus, sans demande d'Alexandre ; `make qualite` et
  l'intégration continue le passent.
- Les tests en parallèle (pytest-xdist) : déjà écartés à l'entrée 119.
- Les tests complets à la demande seulement : rien n'empêcherait de pousser un dépôt cassé avant
  l'intégration continue.
- Une copie de travail et une branche par conversation : plus de verrou partagé, mais des branches
  à fusionner ; inutile quand le verrou ne dure que quelques secondes.

## Conséquences

- `arborescence.toml` passe en version 7 et cite l'ADR 0007 : la zone `09_outillage` permet le
  fichier sans extension `pre-push`.
- `09_outillage/hooks/pre-commit` ne lance plus les tests ; `09_outillage/hooks/pre-push` est
  nouveau ; `make installer-hooks` les active tous deux (même dossier, `core.hooksPath`).
- `09_outillage/scripts/preparer_cloud.sh` : le crochet avant poussée d'une séance dans le cloud
  refuse toujours `main`, puis lance celui du dépôt.
- `CLAUDE.md`, `09_outillage/README.md` et l'aide du `Makefile` disent la nouvelle règle.
- Un commit local peut casser un test sans qu'on le voie aussitôt ; la poussée et l'intégration
  continue le rattrapent.

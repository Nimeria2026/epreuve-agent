# 08_publications

Les résultats publiés, un dossier par publication, nommé `AAAA-MM-JJ_sujet/`, écrit par
`make publier SUJET=<sujet>` et jamais à la main (`02_ease/src/ease/publier.py`) : `manifeste.json`
(chaque run retenu, son rôle, son commit, sa signature, ses empreintes), `donnees.json` (les
chiffres, seule source d'un résultat publié), `cachees.json` (la part des tâches non publiées, en
comptes, sans nom), `README.md`, et `runs/`, chaque run réduit à ses tâches publiques, sans les
journaux du raisonnement du candidat.

Une publication est figée : on ne la modifie jamais. Une erreur découverte après coup donne une
nouvelle publication, qui cite l'ancienne et explique la correction.

Les runs de travail n'entrent pas ici : ils restent dans `99_local/`, hors git ; un run qu'aucun
manifeste ne liste n'est jamais cité comme résultat. Aucune publication à ce jour : la première sera
le constat v1 de Calorelle.

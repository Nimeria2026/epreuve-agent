# Épreuve d'agent

Un banc de mesure d'agents IA. Une entreprise fictive française, Calorelle, et des tâches de bureau
qu'un agent doit mener à bien avec ses outils : ce qu'il réussit, s'il le réussit à chaque fois, en
combien de temps, pour quel coût, et ce qu'il fait quand il ne devrait pas.

Conçu et mené par Alexandre Do. Les constats publiés sont présentés sur
https://nimeria.fr/epreuve-agent.

## Où commencer

- `00_docs/protocole/README.md` : la méthode de mesure, ses règles et ses limites, figée par
  version (étiquette `protocole-v1`).
- `08_publications/` : les publications, chacune avec son manifeste, ses données et les runs qui
  fondent ses chiffres, réduits à leurs tâches publiques.
- `JOURNAL.md` : le journal public, à partir de la version 1 du protocole.
- `AGENTS.md` : installer le banc, le vérifier, mesurer un modèle, en ajouter un ; écrit pour toute
  personne comme pour toute IA qui travaille dans ce dépôt.

## Ce que ce dépôt contient, et ce qu'il ne contient pas

Ce dépôt est l'export, à chaque publication, d'un atelier privé où le banc se construit. Il en
reprend le code, les contrats de données, la PME fictive, les tâches publiques, le protocole, les
décisions d'architecture et les publications.

Il ne contient pas :

- les tâches cachées : une part des tâches n'est jamais publiée, pour mesurer ce qu'aucun modèle
  n'a pu voir ; les publications n'en donnent que des comptes ;
- les notes de travail de l'atelier. Le code et les tâches y renvoient souvent (« JOURNAL, entrée
  N », « BRIEF ») : ces renvois désignent des notes internes, non publiées. Les décisions qui fondent
  la méthode sont reprises dans le protocole, les ADR (`00_docs/adr/`) et le journal public.

## Licences

- Le code : Apache 2.0 (`LICENSE`).
- Les tâches publiques (`07_taches/public/`) et les données des sociétés fictives
  (`05_pme/societes/`) : Creative Commons Attribution, Partage dans les mêmes conditions 4.0
  International (CC BY-SA 4.0). Toute reprise cite « Alexandre Do, Épreuve d'agent » ; toute version
  modifiée se publie sous la même licence.
- Les bancs publics repris dans `11_bancs_publics/` gardent la licence de leurs auteurs.

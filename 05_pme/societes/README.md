# Sociétés

Un dossier par société fictive, et rien d'autre dans chacun que ses données : ses états initiaux
versionnés (`v1/`, `v2/` et les suivants) et ses compléments d'état, un par tâche qui en a besoin
(`complements/<tâche>/`). Les compléments des tâches cachées sont dans
`07_taches/prive/complements/` : à la racine pour Calorelle, dans `<société>/` pour toute autre
société. Les services, dans `05_pme/`, servent toutes les sociétés (ADR 0006).

Une société autre que Calorelle se déclare dans `entreprise/societe.yaml` de chacun de ses états
(contrat `parametres_societe`) : son nom, son domaine, toujours en `.example`, et le dossier des
fiches que lit le service des achats. La messagerie, les achats et EASE (`parametres_societe()`,
`02_ease/src/ease/chargement.py`) le lisent ; un état sans ce fichier est celui de Calorelle. Une
tâche dit sa société par son champ `societe`, `calorelle` par défaut. Reste propre à Calorelle la
mention des PDF que fabrique le service de facturation (`MENTION_FICTIF`), dont Domivelle et
Négovelle ne se servent pas.

EASE trouve le dossier d'une société par `dossier_societe()` (`02_ease/src/ease/chargement.py`),
puis un état par `dossier_version()` et un complément par `dossier_complement()`
(`02_ease/src/ease/pme.py`), Calorelle par défaut ; ce chemin ne s'écrit nulle part ailleurs
dans EASE.
Sous ce dossier, les noms de fichiers sont libres (ADR 0003).

Contenu :

- `calorelle/` : Calorelle, la PME du banc depuis l'étape 2 ; états v1, v2 et v3.
- `domivelle/` : Domivelle, administration de biens ; état v1.
- `negovelle/` : Négovelle, négoce de gros ; état v1, avec `ventes/` pour le service des ventes.
- `gabarit/` : la société gabarit des campagnes, réglée par `variables.yaml` ; état v1 et
  compléments écrits par `make gabarit` (cadrage des interventions, section 11).

## Licence

Les données des sociétés fictives (Calorelle, Domivelle, Négovelle, le gabarit) sont sous licence Creative
Commons Attribution, Partage dans les mêmes conditions 4.0 International (CC BY-SA 4.0,
https://creativecommons.org/licenses/by-sa/4.0/deed.fr) : libres de reprise, y compris
commerciale, à condition de citer « Alexandre Do, Épreuve d'agent » et de publier toute version
modifiée sous la même licence. Toute ressemblance avec une entreprise ou une personne réelle est
fortuite.

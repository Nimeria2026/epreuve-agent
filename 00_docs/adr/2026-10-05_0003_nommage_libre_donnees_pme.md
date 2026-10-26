# ADR 0003 : nommage libre dans les données de la PME

Date : 2026-10-05
Statut : accepté

## Problème rencontré

Le 2026-10-05, en préparant les données initiales v1 de Calorelle (étape 2), la garde a refusé
deux chemins nécessaires aux tâches t01 à t05 :

    05_pme/donnees_initiales/v1/messagerie/boites/comptabilite@calorelle.example/reception/m-cpt-001.json :
      le nom « comptabilite@calorelle.example » ne respecte pas le nommage
    05_pme/donnees_initiales/v1/messagerie/pieces/m-cpt-001/Facture_F-2026-1187.pdf :
      le nom « Facture_F-2026-1187.pdf » ne respecte pas le nommage

Le motif de nommage de l'ADR 0001 (minuscules, chiffres, « _ », « - », « . ») vaut pour le code.
Les données de la PME, elles, doivent ressembler à celles d'une vraie entreprise : une boîte porte
le nom de son adresse, et une pièce jointe garde le nom que son expéditeur lui a donné. La tâche
t01 consiste justement à renommer une facture reçue sous un nom quelconque selon la règle du
manuel ; des données déjà conformes au motif retireraient la difficulté.

## Décision

Ajouter au plan une liste de chemins à nommage libre, `[nommage] libre`, qui contient pour
l'instant `05_pme/donnees_initiales` seul. Sous ces chemins, la garde ne contrôle plus le motif
des noms ; elle contrôle toujours les extensions permises de la zone, et le chemin lui-même reste
soumis au motif.

## Alternatives écartées

- Encoder les noms (remplacer « @ » par « _at_ », mettre les pièces jointes en minuscules) : les
  données ne ressembleraient plus à une vraie messagerie, et la tâche t01 perdrait son piège.
- Ignorer tout `05_pme/donnees_initiales/` dans la garde : on perdrait aussi le contrôle des
  extensions, qui empêche par exemple un exécutable de s'y glisser.
- Mettre les données hors du dépôt : l'état initial doit être versionné pour que les runs soient
  rejouables (règle 1 du BRIEF).

## Conséquences

- `arborescence.toml` passe en version 3, cite l'ADR 0003 et déclare `[nommage] libre`.
- La garde lit cette liste, avec un test qui vérifie qu'un nom libre passe sous le chemin déclaré,
  qu'il est refusé ailleurs, et que les extensions restent contrôlées.

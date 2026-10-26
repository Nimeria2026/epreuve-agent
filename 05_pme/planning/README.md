# 05_pme/planning

Serveur MCP du planning de Calorelle (étape 5, JOURNAL, quatre-vingt-unième entrée). Six outils :

- `lister_techniciens` : les techniciens, leurs compétences, et s'ils sont apprentis ;
- `consulter_planning` : les interventions et les indisponibilités entre deux dates ;
- `chercher_creneaux` : les premiers créneaux libres d'une durée donnée, par pas de 30 minutes ;
- `planifier_intervention`, `deplacer_intervention`, `annuler_intervention`.

Lancement en stdio : `node src/principal.ts --etat <dossier de l'état> --pour <personne>`. Le
serveur lit `<etat>/planning/horaires.yaml` (jours d'intervention, plages, jours fériés), les
techniciens de `<etat>/planning/techniciens/` et les interventions de
`<etat>/planning/interventions/`, un fichier par intervention, conformes aux contrats
`technicien` et `intervention` de `01_contrats/`. Les heures sont celles de Paris ; une heure
donnée sans décalage est lue comme telle.

Droits : lecture pour `planifier`, `lire_planning`, `acces_clients` et `acces_direction` ;
écriture pour `planifier` seulement (le responsable planning). Le logiciel refuse un rendez-vous
hors des heures d'intervention, un jour férié ou en conflit avec un autre rendez-vous ou une
indisponibilité. Il ne connaît pas le manuel : qu'un apprenti parte seul, il le laisse faire,
comme un vrai logiciel de planning. Les indisponibilités n'ont pas de motif ; congés et arrêts
restent au dossier RH.

Tests, à travers le protocole MCP : `pnpm --filter @poa/pme-planning test`.

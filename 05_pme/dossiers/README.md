# 05_pme/dossiers

Serveur MCP des dossiers partagés de Calorelle. Quatre outils : `lister`, `lire`, `deplacer`,
`copier`. Les PDF ne se lisent pas encore : `lire` en donne seulement la taille, en attendant
l'outil documentaire de l'étape 6.

Lancement en stdio : `node src/principal.ts --etat <dossier de l'état> --pour <personne>`. Le
serveur travaille dans `<etat>/dossiers/` et applique les droits de la personne servie à chaque
dossier de premier niveau (`<etat>/entreprise/acces_dossiers.yaml`), fermés par défaut.

Tests, à travers le protocole MCP : `pnpm --filter @poa/pme-dossiers test`.
